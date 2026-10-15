"""Microsoft Entra OIDC login; Microsoft tokens never leave the API."""
import time
from datetime import datetime, timezone
from uuid import UUID

import httpx
from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.starlette_client import OAuth
from authlib.jose.errors import JoseError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from .config import get_settings
from .db import get_session
from .models import AuditLog, User, UserRole
from .security import SESSION_COOKIE_NAME, create_admin_session

router = APIRouter(tags=["Auth"])
settings = get_settings()
oauth = OAuth()
issuer = f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0"
if settings.entra_configured:
    oauth.register(
        "entra", client_id=str(settings.entra_client_id),
        client_secret=settings.entra_client_secret,
        server_metadata_url=issuer + "/.well-known/openid-configuration",
        client_kwargs={"scope": "openid profile email", "code_challenge_method": "S256",
                       "token_endpoint_auth_method": "client_secret_post"},
    )


def identity_from_claims(claims: dict) -> tuple[str, UserRole]:
    """Accept only assigned administrators from the configured tenant."""
    if claims.get("tid") != str(settings.entra_tenant_id):
        raise ValueError("incorrect tenant")
    oid = str(UUID(claims.get("oid", "")))
    roles = claims.get("roles", [])
    if not isinstance(roles, list):
        raise ValueError("invalid roles")
    if "QCentral.SuperAdmin" in roles:
        role = UserRole.superadmin
    elif "QCentral.Admin" in roles:
        role = UserRole.admin
    else:
        raise ValueError("Q-Central administrator role required")
    return f"entra:{settings.entra_tenant_id}:{oid}", role


@router.get("/api/auth/config")
@router.get("/auth/config")
def auth_config():
    return {"provider": settings.auth_mode, "configured": settings.auth_mode == "local" or settings.entra_configured}


@router.get("/api/auth/entra/login")
@router.get("/auth/entra/login")
async def entra_login(request: Request):
    if settings.auth_mode != "entra" or not settings.entra_configured:
        raise HTTPException(status_code=503, detail="Entra authentication is not configured")
    request.session.clear()
    try:
        response = await oauth.entra.authorize_redirect(request, settings.entra_redirect_uri)
    except (OAuthError, httpx.HTTPError, ValueError):
        raise HTTPException(status_code=503, detail="Microsoft login is temporarily unavailable")
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/api/auth/entra/callback")
@router.get("/auth/entra/callback")
async def entra_callback(request: Request, session: Session = Depends(get_session)):
    if settings.auth_mode != "entra" or not settings.entra_configured:
        raise HTTPException(status_code=503, detail="Entra authentication is not configured")
    try:
        token = await oauth.entra.authorize_access_token(
            request, claims_options={"iss": {"essential": True, "value": issuer},
                                    "exp": {"essential": True}, "nbf": {"essential": True}},
        )
        claims = token.get("userinfo")
        if not claims:
            raise ValueError("missing ID token")
        username, role = identity_from_claims(claims)
        expires_at = min(int(claims["exp"]), int(time.time()) + settings.entra_session_minutes * 60)
        if expires_at <= int(time.time()):
            raise ValueError("expired ID token")
    except (OAuthError, JoseError, httpx.HTTPError, ValueError, TypeError, KeyError):
        request.session.clear()
        session.add(AuditLog(event="entra_login_failed", actor="anonymous"))
        session.commit()
        response = RedirectResponse(str(settings.external_url).rstrip("/") + "/?auth_error=entra", status_code=303)
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")
        response.headers["Cache-Control"] = "no-store"
        return response
    request.session.clear()
    user = session.get(User, username)
    if user is None:
        # No local credential can authenticate this identity.
        user = User(username=username, credential_hash="", role=role)
    user.role = role
    user.full_name = claims.get("name")
    user.email = claims.get("email") or claims.get("preferred_username")
    user.is_active = True
    user.last_login_at = datetime.now(timezone.utc)
    user.updated_at = user.last_login_at
    session.add(user)
    session.add(AuditLog(event="entra_login_success", actor=username))
    session.commit()
    response = RedirectResponse(str(settings.external_url), status_code=303)
    response.set_cookie(SESSION_COOKIE_NAME, create_admin_session(username, provider="entra", expires_at=expires_at),
                        httponly=True, secure=True, samesite="strict", max_age=max(1, expires_at - int(time.time())), path="/")
    response.headers["Cache-Control"] = "no-store"
    return response
