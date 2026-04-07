"""Clerk-based auth utilities and FastAPI dependency.

Verifies Clerk session JWTs (RS256) via the JWKS endpoint.
On first login, creates a local users row and maps clerk_user_id → int id.
The internal integer user_id is preserved for all downstream queries.
"""

import logging
import os
import time

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from db.schema import get_connection, set_current_user_id

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=True)

# ── JWKS cache ────────────────────────────────────────────────────────────────

_jwks_cache: dict | None = None
_jwks_fetched_at: float = 0.0
_JWKS_TTL = 3600  # seconds


def _get_jwks() -> dict:
    global _jwks_cache, _jwks_fetched_at
    now = time.time()
    if _jwks_cache is None or now - _jwks_fetched_at > _JWKS_TTL:
        url = os.environ["CLERK_JWKS_URL"]
        try:
            resp = httpx.get(url, timeout=10)
            resp.raise_for_status()
            _jwks_cache = resp.json()
            _jwks_fetched_at = now
        except Exception as exc:
            logger.error("Failed to fetch JWKS from %s: %s", url, exc, exc_info=True)
            raise
    return _jwks_cache


# ── User provisioning ─────────────────────────────────────────────────────────

def _get_clerk_user_email(clerk_user_id: str) -> str:
    """Fetch the user's primary email from Clerk's Backend API."""
    secret = os.environ.get("CLERK_SECRET_KEY", "")
    if not secret:
        return f"{clerk_user_id}@clerk.local"
    try:
        resp = httpx.get(
            f"https://api.clerk.com/v1/users/{clerk_user_id}",
            headers={"Authorization": f"Bearer {secret}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            primary_id = data.get("primary_email_address_id")
            for ea in data.get("email_addresses", []):
                if ea["id"] == primary_id:
                    return ea["email_address"]
    except Exception:
        pass
    return f"{clerk_user_id}@clerk.local"


def _get_or_create_user(clerk_user_id: str) -> int:
    """Return the local int user_id for a Clerk user, creating a row if needed."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE clerk_user_id = %s",
            (clerk_user_id,),
        ).fetchone()
        if row:
            return row["id"]

        email = _get_clerk_user_email(clerk_user_id)
        new_row = conn.execute(
            """
            INSERT INTO users (clerk_user_id, email)
            VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET clerk_user_id = EXCLUDED.clerk_user_id
            RETURNING id
            """,
            (clerk_user_id, email),
        ).fetchone()
        assert new_row is not None
        conn.commit()
        return new_row["id"]


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> int:
    """Verify a Clerk session JWT and return the local integer user_id.

    On first sign-in, provisions a new users row automatically.
    Also sets the db.schema ContextVar so agent tools can resolve the user.
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = credentials.credentials
    try:
        jwks = _get_jwks()
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            options={"verify_aud": False, "verify_exp": False},
        )
        # Manual expiry check with 30s clock-skew leeway
        exp = payload.get("exp")
        if exp is not None and time.time() > exp + 30:
            raise JWTError("Token has expired")
        clerk_user_id: str | None = payload.get("sub")
        if not clerk_user_id:
            logger.warning("JWT validation failed: missing sub claim")
            raise credentials_exc
    except JWTError as exc:
        logger.warning("JWT validation failed: %s", exc)
        raise credentials_exc
    except Exception as exc:
        logger.error("Unexpected error during auth (not a JWT issue): %s", exc, exc_info=True)
        raise credentials_exc

    user_id = _get_or_create_user(clerk_user_id)
    set_current_user_id(user_id)
    return user_id
