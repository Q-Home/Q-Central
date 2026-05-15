import secrets
from passlib.context import CryptContext
from fastapi import Header, HTTPException, status, Depends
from .config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_secret(secret: str) -> str:
    return pwd_context.hash(secret)


def verify_secret(secret: str, hashed: str | None) -> bool:
    return bool(hashed) and pwd_context.verify(secret, hashed)


def new_token(prefix: str = "qct") -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def require_admin(x_admin_token: str | None = Header(default=None)) -> str:
    settings = get_settings()
    if not x_admin_token or not secrets.compare_digest(x_admin_token, settings.admin_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token")
    return "admin"


def require_agent_token(x_agent_token: str | None = Header(default=None)) -> str:
    if not x_agent_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing agent token")
    return x_agent_token
