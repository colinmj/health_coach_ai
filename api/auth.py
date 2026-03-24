"""JWT auth utilities and FastAPI dependency."""

import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import bcrypt
from jose import JWTError, jwt

from db.schema import set_current_user_id

_ALGORITHM = "HS256"
_TOKEN_EXPIRE_DAYS = 30

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _secret() -> str:
    s = os.environ.get("JWT_SECRET")
    if not s:
        raise RuntimeError("JWT_SECRET is not set in .env")
    return s


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(days=_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGORITHM)


def get_current_user_id(token: str = Depends(_oauth2_scheme)) -> int:
    """FastAPI dependency — decodes JWT and sets the ContextVar for this request."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise credentials_exc
        user_id = int(user_id_str)
    except (JWTError, ValueError):
        raise credentials_exc

    set_current_user_id(user_id)
    return user_id
