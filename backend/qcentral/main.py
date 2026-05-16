import asyncio
import json
from datetime import datetime, timedelta, timezone
from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from .config import get_settings
from .db import get_session
from .models import AuditLog, Device, DeviceStatus, Job, User, UserRole
from .schemas import HeartbeatRequest, JobCreateRequest, LoginRequest, ProfileUpdateRequest, ProvisionRequest, ProvisionResponse, RegisterSerialRequest, RegisterSerialResponse, UserCreateRequest, UserUpdateRequest
from .security import SESSION_COOKIE_NAME, authenticate_admin, create_admin_session, hash_secret, new_token, require_admin, require_agent_token, require_portal_token, verify_secret
from .software import router as software_router, software_jobs_snapshot
from .zerotier import authorize_member

ALLOWED_JOB_KINDS = {"agent_update", "app_update", "app_restart", "compose_pull"}
ADMIN_ROLES = {"superadmin", "admin"}

settings = get_settings()
limiter = Limiter(key_func=get_remote_address, default_limits=["240/minute"])
app = FastAPI(title="Q-Central API", version="1.2.0")
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True, allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type", "Authorization", "X-Agent-Token", "X-Portal-Token"])
app.include_router(software_router)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    raise HTTPException(status_code=429, detail="rate limit exceeded")


@app.on_event("startup")
def startup() -> None:
    from .db import init_db
    init_db()


def audit(session: Session, event: str, actor: str, serial: str | None = None, detail: str | None = None) -> None:
    session.add(AuditLog(event=event, actor=actor, serial=serial, detail=detail))


def client_ip(request: Request) -> str:
    return request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "unknown")


def safe_json(value: str | None) -> dict:
    if not value:
        return {}
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def as_utc_naive(value):
    if not value:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def user_payload(user: User) -> dict:
    return {"username": user.username, "role": user.role.value if hasattr(user.role, "value") else str(user.role), "full_name": user.full_name, "email": user.email, "is_active": user.is_active, "mfa_enabled": user.mfa_enabled, "created_at": user.created_at.isoformat() if user.created_at else None, "updated_at": user.updated_at.isoformat() if user.updated_at else None, "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None}


def get_or_bootstrap_user(session: Session, username: str) -> User | None:
    user = session.get(User, username)
    if user:
        return user
    if username == settings.admin_username:
        user = User(username=settings.admin_username, credential_hash=settings.admin_credential_hash, role=UserRole.superadmin, full_name="Initial admin", is_active=True)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    return None


def current_user(session: Session, actor: str) -> User:
    user = get_or_bootstrap_user(session, actor)
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="inactive or unknown user")
    return user


def require_admin_role(session: Session, actor: str) -> User:
    user = current_user(session, actor)
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="admin role required")
    return user


def latest_device_heartbeat(session: Session, serial: str) -> tuple[dict, list[str]]:
    last_hb = session.exec(select(AuditLog).where(AuditLog.serial == serial, AuditLog.event == "heartbeat").order_by(AuditLog.created_at.desc()).limit(1)).first()
    hb_detail = safe_json(last_hb.detail if last_hb else None)
    metrics = hb_detail.get("metrics") if isinstance(hb_detail.get("metrics"), dict) else {}
    apps = hb_detail.get("apps") if isinstance(hb_detail.get("apps"), list) else []
    return metrics, apps


def normalized_device_status(device: Device) -> str:
    last_seen = as_utc_naive(device.last_seen)
    online_cutoff = datetime.utcnow() - timedelta(minutes=10)
    db_status = device.status.value if hasattr(device.status, "value") else str(device.status)
    if db_status == "online" and last_seen and last_seen < online_cutoff:
        return "stale"
    return db_status


def portal_device_payload(device: Device, session: Session) -> dict:
    metrics, apps = latest_device_heartbeat(session, device.serial)
    last_seen = as_utc_naive(device.last_seen)
    return {"serial": device.serial, "name": device.name, "customer": device.customer, "site": device.site, "model": device.model, "status": normalized_device_status(device), "authorized": device.authorized, "firmware": device.firmware, "target_firmware": device.target_firmware, "agent_version": metrics.get("agent_version"), "hostname": metrics.get("hostname"), "ip_address": device.ip_address, "last_seen": last_seen.isoformat() if last_seen else None, "apps": apps, "metrics": {"cpu_percent": metrics.get("cpu_percent"), "mem_percent": metrics.get("mem_percent"), "disk_percent": metrics.get("disk_percent")}, "zerotier": {"node_id": device.zerotier_node_id, "network_id": device.zerotier_network_id}}


@app.websocket("/api/software/ws")
async def software_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            with next(get_session()) as session:
                snapshot = software_jobs_snapshot(session)
            await websocket.send_json(snapshot)
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        return


@app.get("/healthz", tags=["System"])
def healthz():
    return {"ok": True, "service": "q-central"}


@app.post("/api/auth/login", tags=["Auth"])
@limiter.limit("5/minute")
def login(request: Request, response: Response, body: LoginRequest, session: Session = Depends(get_session)):
    ip = client_ip(request)
    supplied = getattr(body, "credential", None) or getattr(body, "password", None)
    user = session.get(User, body.username)
    if user and user.is_active and supplied and verify_secret(supplied, user.credential_hash):
        user.last_login_at = datetime.now(timezone.utc)
        user.updated_at = datetime.now(timezone.utc)
        session.add(user)
        token = create_admin_session(user.username)
        response.set_cookie(SESSION_COOKIE_NAME, token, httponly=True, secure=True, samesite="strict", max_age=settings.session_minutes * 60, path="/")
        audit(session, "admin_login_success", user.username, detail=ip)
        session.commit()
        return {"ok": True, **user_payload(user), "expires_in": settings.session_minutes * 60}
    if supplied and authenticate_admin(body.username, supplied):
        user = get_or_bootstrap_user(session, body.username)
        if user:
            user.last_login_at = datetime.now(timezone.utc)
            session.add(user)
        token = create_admin_session(body.username)
        response.set_cookie(SESSION_COOKIE_NAME, token, httponly=True, secure=True, samesite="strict", max_age=settings.session_minutes * 60, path="/")
        audit(session, "admin_login_success", body.username, detail=ip)
        session.commit()
        return {"ok": True, **user_payload(user), "expires_in": settings.session_minutes * 60}
    audit(session, "admin_login_failed", body.username, detail=ip)
    session.commit()
    raise HTTPException(status_code=401, detail="invalid login")


@app.post("/api/auth/logout", tags=["Auth"])
def logout(response: Response, actor: str = Depends(require_admin), session: Session = Depends(get_session)):
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    audit(session, "admin_logout", actor)
    session.commit()
    return {"ok": True}
