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
from .software import router as software_router, stripped_router as stripped_software_router, software_jobs_snapshot
from .zerotier import authorize_member

ALLOWED_JOB_KINDS = {"agent_update", "app_update", "app_restart", "compose_pull"}
ADMIN_ROLES = {"superadmin", "admin"}

settings = get_settings()
limiter = Limiter(key_func=get_remote_address, default_limits=["240/minute"])
app = FastAPI(title="Q-Central API", version="1.2.3")
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True, allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type", "Authorization", "X-Agent-Token", "X-Portal-Token"])
app.include_router(software_router)
app.include_router(stripped_software_router)


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


def device_payload(device: Device, session: Session) -> dict:
    metrics, apps = latest_device_heartbeat(session, device.serial)
    last_seen = as_utc_naive(device.last_seen)
    return {"serial": device.serial, "name": device.name, "customer": device.customer, "site": device.site, "model": device.model, "status": normalized_device_status(device), "authorized": device.authorized, "firmware": device.firmware, "target_firmware": device.target_firmware, "agent_version": metrics.get("agent_version"), "hostname": metrics.get("hostname"), "ip_address": device.ip_address, "zerotier_node_id": device.zerotier_node_id, "zerotier_network_id": device.zerotier_network_id, "last_seen": last_seen.isoformat() if last_seen else None, "apps": apps, "metrics": metrics, "cpu_percent": metrics.get("cpu_percent"), "mem_percent": metrics.get("mem_percent"), "disk_percent": metrics.get("disk_percent")}


portal_device_payload = device_payload


@app.websocket("/api/software/ws")
@app.websocket("/software/ws")
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
@app.post("/auth/login", tags=["Auth"])
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
@app.post("/auth/logout", tags=["Auth"])
def logout(response: Response, actor: str = Depends(require_admin), session: Session = Depends(get_session)):
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    audit(session, "admin_logout", actor)
    session.commit()
    return {"ok": True}


@app.get("/api/auth/me", tags=["Auth"])
@app.get("/auth/me", tags=["Auth"])
def me(actor: str = Depends(require_admin), session: Session = Depends(get_session)):
    return user_payload(current_user(session, actor))


@app.get("/api/profile", tags=["Profile"])
@app.get("/profile", tags=["Profile"])
def profile(actor: str = Depends(require_admin), session: Session = Depends(get_session)):
    return user_payload(current_user(session, actor))


@app.post("/api/profile/change-password", tags=["Profile"])
@app.post("/profile/change-password", tags=["Profile"])
def change_profile_password(body: ProfileUpdateRequest, actor: str = Depends(require_admin), session: Session = Depends(get_session)):
    user = current_user(session, actor)
    if not verify_secret(body.current_value, user.credential_hash):
        raise HTTPException(status_code=401, detail="current credential is invalid")
    if len(body.new_value) < 10:
        raise HTTPException(status_code=400, detail="new credential must be at least 10 characters")
    user.credential_hash = hash_secret(body.new_value)
    user.updated_at = datetime.now(timezone.utc)
    session.add(user)
    audit(session, "profile_password_changed", actor)
    session.commit()
    return {"ok": True}


@app.get("/api/users", tags=["RBAC"])
@app.get("/users", tags=["RBAC"])
def list_users(actor: str = Depends(require_admin), session: Session = Depends(get_session)):
    require_admin_role(session, actor)
    users = session.exec(select(User).order_by(User.username)).all()
    return [user_payload(u) for u in users]


@app.post("/api/users", tags=["RBAC"])
@app.post("/users", tags=["RBAC"])
def create_user(body: UserCreateRequest, actor: str = Depends(require_admin), session: Session = Depends(get_session)):
    require_admin_role(session, actor)
    if session.get(User, body.username):
        raise HTTPException(status_code=409, detail="user already exists")
    if body.role not in [r.value for r in UserRole]:
        raise HTTPException(status_code=400, detail="invalid role")
    if len(body.initial_value) < 10:
        raise HTTPException(status_code=400, detail="initial credential must be at least 10 characters")
    user = User(username=body.username, credential_hash=hash_secret(body.initial_value), role=UserRole(body.role), full_name=body.full_name, email=body.email, is_active=body.is_active)
    session.add(user)
    audit(session, "user_created", actor, detail=json.dumps({"username": body.username, "role": body.role})[:500])
    session.commit()
    session.refresh(user)
    return user_payload(user)


@app.patch("/api/users/{username}", tags=["RBAC"])
@app.patch("/users/{username}", tags=["RBAC"])
def update_user(username: str, body: UserUpdateRequest, actor: str = Depends(require_admin), session: Session = Depends(get_session)):
    require_admin_role(session, actor)
    user = session.get(User, username)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    if body.role is not None:
        if body.role not in [r.value for r in UserRole]:
            raise HTTPException(status_code=400, detail="invalid role")
        user.role = UserRole(body.role)
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.email is not None:
        user.email = body.email
    if body.is_active is not None:
        if username == actor and not body.is_active:
            raise HTTPException(status_code=400, detail="cannot disable yourself")
        user.is_active = body.is_active
    if body.new_value:
        if len(body.new_value) < 10:
            raise HTTPException(status_code=400, detail="new credential must be at least 10 characters")
        user.credential_hash = hash_secret(body.new_value)
    user.updated_at = datetime.now(timezone.utc)
    session.add(user)
    audit(session, "user_updated", actor, detail=json.dumps({"username": username})[:500])
    session.commit()
    session.refresh(user)
    return user_payload(user)


@app.get("/api/devices", tags=["Devices"])
@app.get("/devices", tags=["Devices"])
def list_devices(session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    devices = session.exec(select(Device).order_by(Device.updated_at.desc())).all()
    return [device_payload(device, session) for device in devices]


@app.get("/api/monitoring/overview", tags=["Monitoring"])
@app.get("/monitoring/overview", tags=["Monitoring"])
def monitoring_overview(session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    devices = session.exec(select(Device).order_by(Device.updated_at.desc())).all()
    rows = [device_payload(device, session) for device in devices]
    totals = {"devices": len(rows), "online": 0, "offline": 0, "stale": 0, "pending": 0, "alerts": 0}
    for row in rows:
        status = row.get("status")
        if status == "online":
            totals["online"] += 1
        elif status == "stale":
            totals["stale"] += 1
            totals["online"] += 1
        elif status == "pending":
            totals["pending"] += 1
        else:
            totals["offline"] += 1
        if status not in {"online", "pending"}:
            totals["alerts"] += 1
        if any(isinstance(row.get(key), (int, float)) and row.get(key) >= 90 for key in ["cpu_percent", "mem_percent", "disk_percent"]):
            totals["alerts"] += 1
    return {"totals": totals, "devices": rows, "generated_at": datetime.utcnow().isoformat()}


@app.post("/api/serials", response_model=RegisterSerialResponse, tags=["Devices"])
@app.post("/serials", response_model=RegisterSerialResponse, tags=["Devices"])
@limiter.limit("30/minute")
def register_serial(request: Request, body: RegisterSerialRequest, session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    existing = session.get(Device, body.serial)
    if existing:
        raise HTTPException(status_code=409, detail="serial already exists")
    claim_token = new_token("claim")
    device = Device(serial=body.serial, claim_token_hash=hash_secret(claim_token), name=body.name, customer=body.customer, site=body.site, model=body.model)
    session.add(device)
    audit(session, "serial_registered", actor, body.serial)
    session.commit()
    return RegisterSerialResponse(serial=body.serial, claim_token=claim_token)


@app.post("/api/provision", response_model=ProvisionResponse, tags=["Agent"])
@app.post("/provision", response_model=ProvisionResponse, tags=["Agent"])
@limiter.limit("20/minute")
async def provision(request: Request, body: ProvisionRequest, session: Session = Depends(get_session)):
    device = session.get(Device, body.serial)
    if not device or not verify_secret(body.claim_token, device.claim_token_hash):
        raise HTTPException(status_code=401, detail="invalid serial or claim token")
    if device.status == DeviceStatus.disabled:
        raise HTTPException(status_code=403, detail="device disabled")
    agent_token = new_token("agent")
    device.agent_token_hash = hash_secret(agent_token)
    device.model = body.model or device.model
    device.firmware = body.firmware or device.firmware
    device.ip_address = body.ip_address or device.ip_address
    device.zerotier_node_id = body.zerotier_node_id or device.zerotier_node_id
    device.zerotier_network_id = settings.zerotier_network_id
    device.authorized = settings.auto_authorize
    device.status = DeviceStatus.online if settings.auto_authorize else DeviceStatus.pending
    device.last_seen = datetime.now(timezone.utc)
    device.updated_at = datetime.now(timezone.utc)
    if settings.auto_authorize and body.zerotier_node_id:
        try:
            await authorize_member(body.zerotier_node_id)
        except Exception as exc:
            audit(session, "zerotier_authorize_failed", "system", body.serial, str(exc))
    audit(session, "device_provisioned", "agent", body.serial)
    session.add(device)
    session.commit()
    return ProvisionResponse(serial=device.serial, authorized=device.authorized, agent_token=agent_token, central_url=str(settings.external_url))


@app.post("/api/agent/heartbeat", tags=["Agent"])
@app.post("/agent/heartbeat", tags=["Agent"])
@limiter.limit("120/minute")
def heartbeat(request: Request, body: HeartbeatRequest, session: Session = Depends(get_session), token: str = Depends(require_agent_token)):
    device = session.get(Device, body.serial)
    if not device or not verify_secret(token, device.agent_token_hash):
        raise HTTPException(status_code=401, detail="invalid agent token")
    device.status = DeviceStatus.online
    device.firmware = body.firmware or device.firmware
    device.ip_address = body.ip_address or device.ip_address
    device.last_seen = datetime.now(timezone.utc)
    device.updated_at = datetime.now(timezone.utc)
    session.add(device)
    audit(session, "heartbeat", "agent", body.serial, json.dumps({"apps": body.apps, "metrics": body.metrics})[:5000])
    session.commit()
    jobs = session.exec(select(Job).where(Job.serial == body.serial, Job.status == "queued").order_by(Job.created_at)).all()
    return {"ok": True, "jobs": jobs}


@app.post("/api/jobs", tags=["Jobs"])
@app.post("/jobs", tags=["Jobs"])
def create_job(body: JobCreateRequest, session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    if body.kind not in ALLOWED_JOB_KINDS:
        raise HTTPException(status_code=400, detail=f"unsupported job kind: {body.kind}")
    if body.kind == "agent_update" and not body.payload.get("sha256"):
        raise HTTPException(status_code=400, detail="sha256 is required for agent_update jobs")
    if not session.get(Device, body.serial):
        raise HTTPException(status_code=404, detail="device not found")
    job = Job(serial=body.serial, kind=body.kind, payload_json=json.dumps(body.payload))
    session.add(job)
    audit(session, "job_created", actor, body.serial, body.kind)
    session.commit()
    session.refresh(job)
    return job


@app.post("/api/jobs/agent-update", tags=["Jobs"])
@app.post("/jobs/agent-update", tags=["Jobs"])
def create_agent_update_job(body: dict, session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    required = {"serial", "url", "sha256"}
    missing = required - set(body)
    if missing:
        raise HTTPException(status_code=400, detail=f"missing fields: {sorted(missing)}")
    serial = body["serial"]
    if not session.get(Device, serial):
        raise HTTPException(status_code=404, detail="device not found")
    payload = {"url": body["url"], "sha256": body["sha256"], "version": body.get("version")}
    job = Job(serial=serial, kind="agent_update", payload_json=json.dumps(payload))
    session.add(job)
    audit(session, "agent_update_queued", actor, serial, json.dumps(payload))
    session.commit()
    session.refresh(job)
    return job


@app.post("/api/jobs/{job_id}/result", tags=["Jobs"])
@app.post("/jobs/{job_id}/result", tags=["Jobs"])
def job_result(job_id: int, result: dict, session: Session = Depends(get_session), token: str = Depends(require_agent_token)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    device = session.get(Device, job.serial)
    if not device or not verify_secret(token, device.agent_token_hash):
        raise HTTPException(status_code=401, detail="invalid agent token")
    job.status = result.get("status", "done")
    job.result = json.dumps(result)[:4000]
    job.updated_at = datetime.now(timezone.utc)
    session.add(job)
    audit(session, "job_result", "agent", job.serial, job.result)
    session.commit()
    return {"ok": True}


@app.get("/api/portal/device/{serial}", tags=["Portal API"])
@app.get("/portal/device/{serial}", tags=["Portal API"])
def portal_device(serial: str, session: Session = Depends(get_session), actor: str = Depends(require_portal_token)):
    device = session.get(Device, serial)
    if not device:
        raise HTTPException(status_code=404, detail="device not found")
    return portal_device_payload(device, session)


@app.get("/api/portal/devices", tags=["Portal API"])
@app.get("/portal/devices", tags=["Portal API"])
def portal_devices(customer: str | None = None, site: str | None = None, session: Session = Depends(get_session), actor: str = Depends(require_portal_token)):
    stmt = select(Device).order_by(Device.updated_at.desc())
    if customer:
        stmt = stmt.where(Device.customer == customer)
    if site:
        stmt = stmt.where(Device.site == site)
    devices = session.exec(stmt).all()
    return {"devices": [portal_device_payload(d, session) for d in devices], "count": len(devices)}
