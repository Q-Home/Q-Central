import json
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from .db import get_session
from .models import Device, Job
from .security import require_admin

router = APIRouter(prefix="/api/software", tags=["Software Repository"])

GITHUB_REPO = "Q-Home/Q-Central"
AGENT_ASSET_PREFIX = "qbox-agent-"
OTA_STATUSES = ["queued", "downloading", "installing", "rebooting", "accepted", "success", "failed"]
DONE_STATUSES = {"done", "success"}


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Q-Central"})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_release_manifest(url: str | None) -> dict:
    if not url:
        return {}
    try:
        return fetch_json(url)
    except Exception:
        return {}


def normalize_version(value: str | None) -> str | None:
    if not value:
        return value
    return str(value).replace("qbox-agent-", "").lstrip("v")


def normalize_agent_release(release: dict) -> dict | None:
    assets = release.get("assets") or []
    archive = None
    manifest = None
    for asset in assets:
        name = asset.get("name") or ""
        if name.startswith(AGENT_ASSET_PREFIX) and name.endswith(".tar.gz"):
            archive = asset
        if name.startswith(AGENT_ASSET_PREFIX) and name.endswith(".manifest.json"):
            manifest = asset
    if not archive:
        return None
    manifest_url = manifest.get("browser_download_url") if manifest else None
    manifest_data = fetch_release_manifest(manifest_url)
    fallback_version = archive.get("name", "").replace(AGENT_ASSET_PREFIX, "").replace(".tar.gz", "")
    version = manifest_data.get("version") or normalize_version(release.get("tag_name") or release.get("name") or fallback_version)
    return {
        "kind": "agent_update",
        "name": release.get("name") or version,
        "version": normalize_version(version),
        "tag": release.get("tag_name"),
        "draft": release.get("draft", False),
        "prerelease": release.get("prerelease", False),
        "published_at": release.get("published_at"),
        "url": archive.get("browser_download_url"),
        "asset_name": archive.get("name"),
        "size_bytes": archive.get("size") or manifest_data.get("size_bytes"),
        "manifest_url": manifest_url,
        "manifest": manifest_data,
        "html_url": release.get("html_url"),
        "sha256": manifest_data.get("sha256"),
        "ready": bool(archive.get("browser_download_url") and manifest_data.get("sha256")),
    }


def job_payload(job: Job) -> dict:
    try:
        return json.loads(job.payload_json or "{}")
    except Exception:
        return {}


def normalized_job_status(job: Job) -> str:
    if job.status == "done":
        return "success"
    if job.status == "accepted":
        return "rebooting"
    return job.status


def job_row(job: Job) -> dict:
    payload = job_payload(job)
    return {
        "id": job.id,
        "serial": job.serial,
        "kind": job.kind,
        "status": normalized_job_status(job),
        "raw_status": job.status,
        "payload": payload,
        "version": payload.get("version"),
        "batch": payload.get("batch"),
        "rollback": payload.get("rollback", False),
        "result": job.result,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


@router.get("/agent/releases")
def agent_releases(actor: str = Depends(require_admin)):
    try:
        releases = fetch_json(f"https://api.github.com/repos/{GITHUB_REPO}/releases")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"could not fetch GitHub releases: {exc}")
    items = []
    for release in releases:
        item = normalize_agent_release(release)
        if item:
            items.append(item)
    return {"repository": GITHUB_REPO, "releases": items, "count": len(items), "generated_at": datetime.now(timezone.utc).isoformat()}


@router.post("/agent/queue")
def queue_agent_release(body: dict, session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    serials = body.get("serials") or []
    version = body.get("version")
    url = body.get("url")
    sha256 = body.get("sha256")
    batch_size = int(body.get("batch_size") or len(serials) or 1)
    rollback = body.get("rollback", False)
    rollback_from = body.get("rollback_from")
    if not serials or not isinstance(serials, list):
        raise HTTPException(status_code=400, detail="serials list is required")
    if not url or not sha256:
        raise HTTPException(status_code=400, detail="url and sha256 are required")
    rollout_id = f"rollout-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    jobs = []
    for index, serial in enumerate(serials):
        if not session.get(Device, serial):
            raise HTTPException(status_code=404, detail=f"device not found: {serial}")
        batch = index // max(1, batch_size) + 1
        payload = {
            "url": url,
            "sha256": sha256,
            "version": version,
            "source": "software_repository",
            "rollout_id": rollout_id,
            "batch": batch,
            "batch_size": batch_size,
            "rollback": rollback,
            "rollback_from": rollback_from,
        }
        job = Job(serial=serial, kind="agent_update", payload_json=json.dumps(payload), status="queued")
        session.add(job)
        jobs.append(job)
    session.commit()
    for job in jobs:
        session.refresh(job)
    return {"ok": True, "rollout_id": rollout_id, "jobs": [job_row(j) for j in jobs]}


@router.get("/jobs")
def software_jobs(serial: str | None = None, session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    stmt = select(Job).order_by(Job.created_at.desc()).limit(250)
    if serial:
        stmt = select(Job).where(Job.serial == serial).order_by(Job.created_at.desc()).limit(250)
    jobs = session.exec(stmt).all()
    rows = [job_row(job) for job in jobs]
    counters = Counter(row["status"] for row in rows)
    by_rollout = {}
    for row in rows:
        rollout_id = row["payload"].get("rollout_id") or "manual"
        group = by_rollout.setdefault(rollout_id, {"rollout_id": rollout_id, "jobs": [], "counters": Counter()})
        group["jobs"].append(row)
        group["counters"][row["status"]] += 1
    rollouts = []
    for group in by_rollout.values():
        counters_dict = {status: group["counters"].get(status, 0) for status in OTA_STATUSES}
        total = len(group["jobs"])
        finished = counters_dict.get("success", 0) + counters_dict.get("failed", 0)
        progress = round((finished / total) * 100) if total else 0
        latest = max((job.get("updated_at") or job.get("created_at") or "") for job in group["jobs"])
        rollouts.append({"rollout_id": group["rollout_id"], "total": total, "progress_percent": progress, "counters": counters_dict, "latest_at": latest})
    return {
        "jobs": rows,
        "counters": {status: counters.get(status, 0) for status in OTA_STATUSES},
        "success": counters.get("success", 0),
        "failed": counters.get("failed", 0),
        "rollouts": sorted(rollouts, key=lambda r: r["latest_at"], reverse=True),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
