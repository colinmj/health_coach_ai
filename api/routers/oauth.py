"""OAuth2 flow endpoints for Whoop and Withings.

Flow:
  1. Frontend calls GET /oauth/{provider}/start (authenticated) → returns { url }
  2. Frontend redirects browser to url
  3. Provider redirects to GET /oauth/{provider}/callback
  4. Tokens are stored in user_integrations; browser is sent to FRONTEND_URL
"""

import os
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt

from api.auth import _ALGORITHM, _secret, get_current_user_id
from db.schema import get_connection

router = APIRouter(prefix="/oauth", tags=["oauth"])

_PROVIDERS: dict[str, dict] = {
    "oura": {
        "auth_url": "https://cloud.ouraring.com/oauth/authorize",
        "token_url": "https://api.ouraring.com/oauth/token",
        "scopes": "daily heartrate spo2 personal workout",
        "client_id_env": "OURA_CLIENT_ID",
        "client_secret_env": "OURA_CLIENT_SECRET",
        "redirect_uri_env": "OURA_REDIRECT_URI",
    },
    "whoop": {
        "auth_url": "https://api.prod.whoop.com/oauth/oauth2/auth",
        "token_url": "https://api.prod.whoop.com/oauth/oauth2/token",
        "scopes": "offline read:cycles read:recovery read:sleep read:workout",
        "client_id_env": "WHOOP_CLIENT_ID",
        "client_secret_env": "WHOOP_CLIENT_SECRET",
        "redirect_uri_env": "WHOOP_REDIRECT_URI",
    },
    "withings": {
        "auth_url": "https://account.withings.com/oauth2_user/authorize2",
        "token_url": "https://wbsapi.withings.net/v2/oauth2",
        "scopes": "user.metrics",
        "client_id_env": "WITHINGS_CLIENT_ID",
        "client_secret_env": "WITHINGS_CLIENT_SECRET",
        "redirect_uri_env": "WITHINGS_REDIRECT_URI",
    },
    "strava": {
        "auth_url": "https://www.strava.com/oauth/authorize",
        "token_url": "https://www.strava.com/oauth/token",
        "scopes": "activity:read_all",
        "client_id_env": "STRAVA_CLIENT_ID",
        "client_secret_env": "STRAVA_CLIENT_SECRET",
        "redirect_uri_env": "STRAVA_REDIRECT_URI",
    },
}


def _make_state(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        "nonce": secrets.token_hex(8),
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGORITHM)


def _verify_state(state: str) -> int:
    try:
        payload = jwt.decode(state, _secret(), algorithms=[_ALGORITHM])
        return int(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")


def _exchange_tokens(provider: str, code: str) -> dict:
    cfg = _PROVIDERS[provider]
    client_id = os.environ[cfg["client_id_env"]]
    client_secret = os.environ[cfg["client_secret_env"]]
    redirect_uri = os.environ[cfg["redirect_uri_env"]]

    if provider == "withings":
        resp = httpx.post(cfg["token_url"], data={
            "action": "requesttoken",
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        })
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") != 0:
            raise HTTPException(status_code=400, detail=f"Withings token error: {body}")
        return body["body"]
    else:
        resp = httpx.post(cfg["token_url"], data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        })
        resp.raise_for_status()
        return resp.json()


@router.get("/{provider}/start")
def oauth_start(provider: str, user_id: int = Depends(get_current_user_id)) -> dict:
    """Return the provider auth URL. Frontend redirects the browser to it."""
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")

    cfg = _PROVIDERS[provider]
    params = {
        "client_id": os.environ[cfg["client_id_env"]],
        "redirect_uri": os.environ[cfg["redirect_uri_env"]],
        "response_type": "code",
        "scope": cfg["scopes"],
        "state": _make_state(user_id),
    }
    return {"url": f"{cfg['auth_url']}?{urllib.parse.urlencode(params)}"}


@router.get("/{provider}/callback")
def oauth_callback(provider: str, code: str, state: str):
    """Receive the OAuth callback, store tokens, redirect to frontend."""
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")

    user_id = _verify_state(state)
    tokens = _exchange_tokens(provider, code)
    cfg = _PROVIDERS[provider]

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_integrations (user_id, source, auth_type, access_token, refresh_token)
            VALUES (%s, %s, 'oauth', %s, %s)
            ON CONFLICT (user_id, source) DO UPDATE SET
                access_token  = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token
            """,
            (user_id, provider, tokens["access_token"], tokens.get("refresh_token")),
        )
        conn.commit()

    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:5173")
    return RedirectResponse(f"{frontend_url}/onboarding?connected={provider}")
