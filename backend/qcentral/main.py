import json
from datetime import datetime, timedelta, timezone
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from .config import get_settings
from .db import get_session, init_db
from .models import AuditLog, Device, DeviceStatus, Job
from .schemas import HeartbeatRequest, JobCreateRequest, LoginRequest, ProvisionRequest, ProvisionResponse, RegisterSerialRequest, RegisterSerialResponse
from .security import SESSION_COOKIE_NAME, authenticate_admin, create_admin_session, hash_secret, new_token, require_admin, require_agent_token, require_portal_token, verify_secret
from .zerotier import authorize_member

ALLOWED_JOB_KINDS = {"agent_update", "app_update", "app_restart", "compose_pull"}

settings = get_settings()
limiter = Limiter(key_func=get_remote_address, default_limits=["240/minute"])
app = FastAPI(title="Q-Central API", version="1.0.0")
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True, allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type", "Authorization", "X-Agent-Token", "X-Portal-Token"])


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    raise HTTPException(status_code=429, detail="rate limit exceeded")


@app.on_event("startup")
def startup() -> None:
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


def latest_device_heartbeat(session: Session, serial: str) -> tuple[dict, list[str]]:
    last_hb = session.exec(
        select(AuditLog)
        .where(AuditLog.serial == serial, AuditLog.event == "heartbeat")
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    ).first()
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
    return {
        "serial": device.serial,
        "name": device.name,
        "customer": device.customer,
        "site": device.site,
        "model": device.model,
        "status": normalized_device_status(device),
        "authorized": device.authorized,
        "firmware": device.firmware,
        "target_firmware": device.target_firmware,
        "agent_version": metrics.get("agent_version"),
        "hostname": metrics.get("hostname"),
        "ip_address": device.ip_address,
        "last_seen": last_seen.isoformat() if last_seen else None,
        "apps": apps,
        "metrics": {
            "cpu_percent": metrics.get("cpu_percent"),
            "mem_percent": metrics.get("mem_percent"),
            "disk_percent": metrics.get("disk_percent"),
        },
        "zerotier": {
            "node_id": device.zerotier_node_id,
            "network_id": device.zerotier_network_id,
        },
    }


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "q-central"}


@app.post("/api/auth/login")
@limiter.limit("5/minute")
def login(request: Request, response: Response, body: LoginRequest, session: Session = Depends(get_session)):
    ip = client_ip(request)
    supplied = getattr(body, "credential", None) or getattr(body, "password", None)
    if not supplied or not authenticate_admin(body.username, supplied):
        audit(session, "admin_login_failed", body.username, detail=ip)
        session.commit()
        raise HTTPException(status_code=401, detail="invalid login")
    token = create_admin_session(body.username)
    response.set_cookie(SESSION_COOKIE_NAME, token, httponly=True, secure=True, samesite="strict", max_age=settings.session_minutes * 60, path="/")
    audit(session, "admin_login_success", body.username, detail=ip)
    session.commit()
    return {"ok": True, "username": body.username, "expires_in": settings.session_minutes * 60}


@app.post("/api/auth/logout")
def logout(response: Response, actor: str = Depends(require_admin), session: Session = Depends(get_session)):
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    audit(session, "admin_logout", actor)
    session.commit()
    return {"ok": True}


@app.get("/api/auth/me")
def me(actor: str = Depends(require_admin)):
    return {"username": actor, "role": "admin"}


@app.get("/api/portal/device/{serial}")
@limiter.limit("120/minute")
def portal_device(request: Request, serial: str, session: Session = Depends(get_session), actor: str = Depends(require_portal_token)):
    device = session.get(Device, serial)
    if not device:
        raise HTTPException(status_code=404, detail="device not found")
    audit(session, "portal_device_lookup", actor, serial, client_ip(request))
    session.commit()
    return portal_device_payload(device, session)


@app.get("/api/portal/devices")
@limiter.limit("120/minute")
def portal_devices(request: Request, customer: str | None = None, site: str | None = None, session: Session = Depends(get_session), actor: str = Depends(require_portal_token)):
    stmt = select(Device).order_by(Device.updated_at.desc())
    if customer:
        stmt = stmt.where(Device.customer == customer)
    if site:
        stmt = stmt.where(Device.site == site)
    devices = session.exec(stmt).all()
    audit(session, "portal_devices_lookup", actor, detail=json.dumps({"customer": customer, "site": site, "count": len(devices), "ip": client_ip(request)})[:500])
    session.commit()
    return {"devices": [portal_device_payload(d, session) for d in devices], "count": len(devices)}


@app.get("/api/portal/customer/{customer}/devices")
@limiter.limit("120/minute")
def portal_customer_devices(request: Request, customer: str, session: Session = Depends(get_session), actor: str = Depends(require_portal_token)):
    devices = session.exec(select(Device).where(Device.customer == customer).order_by(Device.updated_at.desc())).all()
    audit(session, "portal_customer_lookup", actor, detail=json.dumps({"customer": customer, "count": len(devices), "ip": client_ip(request)})[:500])
    session.commit()
    return {"customer": customer, "devices": [portal_device_payload(d, session) for d in devices], "count": len(devices)}


@app.post("/api/serials", response_model=RegisterSerialResponse)
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


@app.get("/api/devices")
def list_devices(session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    return session.exec(select(Device).order_by(Device.updated_at.desc())).all()


@app.get("/api/monitoring/overview")
def monitoring_overview(session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    devices = session.exec(select(Device).order_by(Device.updated_at.desc())).all()
    online_cutoff = datetime.utcnow() - timedelta(minutes=10)
    rows = []
    totals = {"devices": len(devices), "online": 0, "offline": 0, "stale": 0, "pending": 0, "alerts": 0}
    for device in devices:
        last_seen = as_utc_naive(device.last_seen)
        db_status = device.status.value if hasattr(device.status, "value") else str(device.status)
        is_db_online = device.status == DeviceStatus.online or db_status == "online"
        is_recent = bool(last_seen and last_seen >= online_cutoff)
        is_pending = device.status == DeviceStatus.pending or db_status == "pending"
        is_stale = bool(is_db_online and last_seen and not is_recent)
        is_online = bool(is_db_online and (is_recent or last_seen is None))
        if is_pending:
            totals["pending"] += 1
        elif is_stale:
            totals["stale"] += 1
            totals["online"] += 1
        elif is_online:
            totals["online"] += 1
        else:
            totals["offline"] += 1
        metrics, apps = latest_device_heartbeat(session, device.serial)
        cpu = metrics.get("cpu_percent")
        mem = metrics.get("mem_percent")
        disk = metrics.get("disk_percent")
        if any(isinstance(v, (int, float)) and v >= 90 for v in [cpu, mem, disk]):
            totals["alerts"] += 1
        if is_stale or (not is_online and not is_pending):
            totals["alerts"] += 1
        row_status = "stale" if is_stale else "online" if is_online else db_status
        rows.append({"serial": device.serial, "name": device.name, "customer": device.customer, "site": device.site, "status": row_status, "last_seen": last_seen.isoformat() if last_seen else None, "firmware": device.firmware, "ip_address": device.ip_address, "cpu_percent": cpu, "mem_percent": mem, "disk_percent": disk, "agent_version": metrics.get("agent_version"), "hostname": metrics.get("hostname"), "apps": apps})
    return {"totals": totals, "devices": rows, "generated_at": datetime.utcnow().isoformat()}


@app.post("/api/provision", response_model=ProvisionResponse)
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


@app.post("/api/agent/heartbeat")
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
    audit(session, "heartbeat", "agent", body.serial, json.dumps({"apps": body.apps, "metrics": body.metrics})[:500])
    session.commit()
    jobs = session.exec(select(Job).where(Job.serial == body.serial, Job.status == "queued").order_by(Job.created_at)).all()
    return {"ok": True, "jobs": jobs}


@app.post("/api/jobs")
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


@app.post("/api/jobs/agent-update")
def create_agent_update_job(body: dict, session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    required = {"serial", "url", "sha256"}
    missing = required - set(body)
    if missing:
        raise HTTPException(status_code=400, detail=f"missing fields: {sorted(missing)}")
    if not str(body.get("sha256") or "").strip():
        raise HTTPException(status_code=400, detail="sha256 is required")
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


@app.post("/api/jobs/app-update")
def create_app_update_job(body: dict, session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    required = {"serial", "path"}
    missing = required - set(body)
    if missing:
        raise HTTPException(status_code=400, detail=f"missing fields: {sorted(missing)}")
    serial = body["serial"]
    if not session.get(Device, serial):
        raise HTTPException(status_code=404, detail="device not found")
    payload = {"path": body["path"], "compose_file": body.get("compose_file")}
    job = Job(serial=serial, kind="app_update", payload_json=json.dumps(payload))
    session.add(job)
    audit(session, "app_update_queued", actor, serial, json.dumps(payload))
    session.commit()
    session.refresh(job)
    return job


@app.post("/api/jobs/{job_id}/result")
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
