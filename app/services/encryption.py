import os

from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    key = os.environ["BLOODWORK_ENCRYPTION_KEY"]
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(value: str | float | int | None) -> str | None:
    if value is None:
        return None
    return _get_fernet().encrypt(str(value).encode()).decode()


def decrypt(token: str | None) -> str | None:
    if token is None:
        return None
    return _get_fernet().decrypt(token.encode()).decode()
