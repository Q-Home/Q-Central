import json
from datetime import datetime, timezone
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from .config import get_settings
from .db import get_session, init_db
from .models import AuditLog, Device, DeviceStatus, Job

ALLOWED_JOB_KINDS = {"agent_update", "app_update", "app_restart", "compose_pull", "shell"}
from .schemas import HeartbeatRequest, JobCreateRequest, ProvisionRequest, ProvisionResponse, RegisterSerialRequest, RegisterSerialResponse
from .security import hash_secret, new_token, require_admin, require_agent_token, verify_secret
from .zerotier import authorize_member

settings = get_settings()
limiter = Limiter(key_func=get_remote_address, default_limits=["240/minute"])
app = FastAPI(title="Q-Central API", version="1.0.0")
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=False, allow_methods=["GET", "POST", "PATCH"], allow_headers=["*"])


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    raise HTTPException(status_code=429, detail="rate limit exceeded")


@app.on_event("startup")
def startup() -> None:
    init_db()


def audit(session: Session, event: str, actor: str, serial: str | None = None, detail: str | None = None) -> None:
    session.add(AuditLog(event=event, actor=actor, serial=serial, detail=detail))


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "q-central"}


@app.post("/api/serials", response_model=RegisterSerialResponse)
@limiter.limit("30/minute")
def register_serial(request: Request, body: RegisterSerialRequest, session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    existing = session.get(Device, body.serial)
    if existing:
        raise HTTPException(status_code=409, detail="serial already exists")
    claim_token = new_token("claim")
    device = Device(
        serial=body.serial,
        claim_token_hash=hash_secret(claim_token),
        name=body.name,
        customer=body.customer,
        site=body.site,
        model=body.model,
    )
    session.add(device)
    audit(session, "serial_registered", actor, body.serial)
    session.commit()
    return RegisterSerialResponse(serial=body.serial, claim_token=claim_token)


@app.get("/api/devices")
def list_devices(session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    return session.exec(select(Device).order_by(Device.updated_at.desc())).all()


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
    required = {"serial", "url"}
    missing = required - set(body)
    if missing:
        raise HTTPException(status_code=400, detail=f"missing fields: {sorted(missing)}")
    serial = body["serial"]
    if not session.get(Device, serial):
        raise HTTPException(status_code=404, detail="device not found")
    payload = {"url": body["url"], "sha256": body.get("sha256"), "version": body.get("version")}
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
