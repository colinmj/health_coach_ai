from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from api.auth import create_token, hash_password, verify_password
from db.schema import get_connection

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthRequest(BaseModel):
    email: str
    password: str


@router.post("/register", status_code=201)
def register(body: AuthRequest) -> dict:
    """Create a new user account and return a JWT."""
    if len(body.password.encode()) > 72:
        raise HTTPException(status_code=422, detail="Password must be 72 characters or fewer")
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = %s", (body.email,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        row = conn.execute(
            """
            INSERT INTO users (email, password_hash)
            VALUES (%s, %s)
            RETURNING id
            """,
            (body.email, hash_password(body.password)),
        ).fetchone()
        assert row is not None
        conn.commit()
        user_id = row["id"]

    return {"token": create_token(user_id), "user_id": user_id}


@router.post("/login")
def login(body: AuthRequest) -> dict:
    """Verify credentials and return a JWT."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE email = %s", (body.email,)
        ).fetchone()

    if not row or not row["password_hash"] or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return {"token": create_token(row["id"]), "user_id": row["id"]}
