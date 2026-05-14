import os
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .models import SerialCreate, ProvisionRequest, ProvisionResponse, Heartbeat, CustomerMapping, OtaJob, AppInstall
from .store import init_db, get_device, list_devices, upsert_device, update_device, insert_ota, list_ota, mark_ota_done, now_iso

AUTO_AUTHORIZE = os.getenv("QBOX_AUTO_AUTHORIZE", "true").lower() == "true"
ZT_NETWORK_ID = os.getenv("QBOX_ZEROTIER_NETWORK_ID", "8056c2e21c000001")

app = FastAPI(title="Q-Box Central API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "ok", "service": "qbox-central-api"}

@app.get("/api/devices")
def api_devices():
    return list_devices()

@app.post("/api/serials")
def create_serial(payload: SerialCreate):
    existing = get_device(payload.serial)
    device = {
        "serial": payload.serial,
        "name": payload.name,
        "claim_token": payload.claim_token,
        "customer": payload.customer,
        "site": payload.site,
        "model": payload.model,
        "zerotier_node_id": existing.get("zerotier_node_id") if existing else None,
        "zerotier_ip": existing.get("zerotier_ip") if existing else None,
        "authorized": existing.get("authorized", False) if existing else False,
        "status": existing.get("status", "registered") if existing else "registered",
        "firmware": existing.get("firmware") if existing else None,
        "apps": existing.get("apps", []) if existing else [],
        "last_seen": existing.get("last_seen") if existing else None,
        "metadata": existing.get("metadata", {}) if existing else {},
    }
    upsert_device(device)
    return get_device(payload.serial)

@app.get("/api/devices/{serial}")
def api_device(serial: str):
    device = get_device(serial)
    if not device:
        raise HTTPException(status_code=404, detail="Unknown serial")
    return device

@app.post("/api/provision/request", response_model=ProvisionResponse)
def provision_request(payload: ProvisionRequest):
    device = get_device(payload.serial)
    if not device:
        return ProvisionResponse(accepted=False, authorized=False, message="Serial is not registered")
    if payload.claim_token != device["claim_token"]:
        return ProvisionResponse(accepted=False, authorized=False, message="Invalid claim token")

    authorized = bool(device["authorized"] or AUTO_AUTHORIZE)
    status = "authorized" if authorized else "pending"
    updated = update_device(payload.serial, {
        "name": device["name"] if device["name"] != "Unclaimed Q-Box" else payload.hostname,
        "model": payload.model or device.get("model"),
        "firmware": payload.firmware or device.get("firmware"),
        "zerotier_node_id": payload.zerotier_node_id or device.get("zerotier_node_id"),
        "zerotier_ip": payload.zerotier_ip or device.get("zerotier_ip"),
        "authorized": authorized,
        "status": status,
        "last_seen": now_iso(),
        "metadata": {**device.get("metadata", {}), **payload.metadata},
    })

    return ProvisionResponse(
        accepted=True,
        authorized=authorized,
        message="Authorized" if authorized else "Pending manual authorization",
        config={
            "serial": payload.serial,
            "zerotier_network_id": ZT_NETWORK_ID,
            "heartbeat_interval_seconds": 30,
            "ota_poll_interval_seconds": 60,
            "device": updated,
        },
    )

@app.post("/api/provision/authorize/{serial}")
def authorize(serial: str):
    device = update_device(serial, {"authorized": True, "status": "authorized"})
    if not device:
        raise HTTPException(status_code=404, detail="Unknown serial")
    return device

@app.post("/api/devices/{serial}/customer")
def map_customer(serial: str, payload: CustomerMapping):
    device = update_device(serial, {"customer": payload.customer, "site": payload.site, "name": payload.name or get_device(serial)["name"]})
    if not device:
        raise HTTPException(status_code=404, detail="Unknown serial")
    return device

@app.post("/api/heartbeat")
def heartbeat(payload: Heartbeat):
    device = get_device(payload.serial)
    if not device or payload.claim_token != device["claim_token"]:
        raise HTTPException(status_code=403, detail="Invalid device credentials")
    return update_device(payload.serial, {
        "status": "online",
        "firmware": payload.firmware or device.get("firmware"),
        "apps": payload.apps,
        "last_seen": now_iso(),
        "metadata": {**device.get("metadata", {}), "last_metrics": payload.metrics},
    })

@app.get("/api/ota/jobs")
def ota_jobs(serial: str | None = None):
    return list_ota(serial)

@app.post("/api/ota/deploy")
def ota_deploy(serial: str, target_firmware: str | None = None, command: str | None = None):
    job = OtaJob(id=str(uuid.uuid4()), serial=serial, target_firmware=target_firmware, command=command, status="queued")
    insert_ota(job.model_dump())
    return job

@app.post("/api/ota/jobs/{job_id}/done")
def ota_done(job_id: str):
    mark_ota_done(job_id)
    return {"status": "done", "id": job_id}

@app.post("/api/apps/install")
def install_app(payload: AppInstall):
    device = get_device(payload.serial)
    if not device:
        raise HTTPException(status_code=404, detail="Unknown serial")
    apps = set(device.get("apps", []))
    apps.add(payload.app)
    return update_device(payload.serial, {"apps": sorted(apps)})
