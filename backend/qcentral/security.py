import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Header, HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SESSION_COOKIE_NAME = "qcentral_session"
JWT_ALGORITHM = "HS256"


def hash_secret(secret: str) -> str:
    return pwd_context.hash(secret)


def verify_secret(secret: str, hashed: str | None) -> bool:
    return bool(hashed) and pwd_context.verify(secret, hashed)


def new_token(prefix: str = "qct") -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def create_admin_session(username: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.session_minutes)
    payload = {"sub": username, "role": "admin", "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def verify_admin_session(token: str | None) -> str:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing admin session")
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin session")
    if payload.get("role") != "admin" or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin session")
    return str(payload["sub"])


def authenticate_admin(username: str, supplied_value: str) -> bool:
    settings = get_settings()
    if not secrets.compare_digest(username, settings.admin_username):
        return False
    return verify_secret(supplied_value, settings.admin_credential_hash)


def require_admin(
    qcentral_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> str:
    bearer = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization.split(" ", 1)[1].strip()
    return verify_admin_session(qcentral_session or bearer)


def require_agent_token(x_agent_token: str | None = Header(default=None)) -> str:
    if not x_agent_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing agent token")
    return x_agent_token


def require_portal_token(
    authorization: str | None = Header(default=None),
    x_portal_token: str | None = Header(default=None),
) -> str:
    expected_hash = os.getenv("Q_CENTRAL_PORTAL_TOKEN_HASH")
    if not expected_hash:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="portal api not configured")
    supplied = x_portal_token
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization.split(" ", 1)[1].strip()
    if not supplied or not verify_secret(supplied, expected_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid portal token")
    return "q-portal"
