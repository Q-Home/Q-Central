import json
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from .config import get_settings
from .db import get_session
from .models import Device, Job
from .security import require_admin

router = APIRouter(prefix="/api/software", tags=["Software Repository"])
stripped_router = APIRouter(prefix="/software", tags=["Software Repository"])

AGENT_ASSET_PREFIX = "qbox-agent-"
MAX_RELEASES = 30
OTA_STATUSES = ["queued", "downloading", "installing", "rebooting", "success", "failed"]
STATUS_PROGRESS = {"queued": 0, "downloading": 25, "installing": 60, "rebooting": 85, "accepted": 85, "done": 100, "success": 100, "failed": 100}


def github_repo() -> str:
    return get_settings().software_github_repo


def fetch_json(url: str):
    settings = get_settings()
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Q-Central"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    req = urllib.request.Request(url, headers=headers)
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


def release_sort_key(item: dict) -> tuple:
    published = item.get("published_at") or ""
    version = item.get("version") or ""
    parts = []
    for part in str(version).replace("-", ".").split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return (published, parts)


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
    return {"kind": "agent_update", "name": release.get("name") or version, "version": normalize_version(version), "tag": release.get("tag_name"), "draft": release.get("draft", False), "prerelease": release.get("prerelease", False), "published_at": release.get("published_at"), "url": archive.get("browser_download_url"), "asset_name": archive.get("name"), "size_bytes": archive.get("size") or manifest_data.get("size_bytes"), "manifest_url": manifest_url, "manifest": manifest_data, "html_url": release.get("html_url"), "sha256": manifest_data.get("sha256"), "ready": bool(archive.get("browser_download_url") and manifest_data.get("sha256"))}


def safe_json(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {"output": value}
    except Exception:
        return {"output": value}


def job_payload(job: Job) -> dict:
    return safe_json(job.payload_json)


def job_result(job: Job) -> dict:
    return safe_json(job.result)


def normalized_job_status(job: Job) -> str:
    if job.status == "done":
        return "success"
    if job.status == "accepted":
        return "rebooting"
    return job.status


def job_progress(job: Job) -> int:
    result = job_result(job)
    if isinstance(result.get("progress"), int):
        return max(0, min(100, result["progress"]))
    return STATUS_PROGRESS.get(normalized_job_status(job), 0)


def job_row(job: Job) -> dict:
    payload = job_payload(job)
    result = job_result(job)
    return {"id": job.id, "serial": job.serial, "kind": job.kind, "status": normalized_job_status(job), "raw_status": job.status, "progress_percent": job_progress(job), "stage": result.get("stage") or normalized_job_status(job), "payload": payload, "version": payload.get("version"), "batch": payload.get("batch"), "batch_size": payload.get("batch_size"), "rollout_id": payload.get("rollout_id"), "rollback": payload.get("rollback", False), "rollback_from": payload.get("rollback_from"), "result": result, "result_text": result.get("output") or job.result, "created_at": job.created_at.isoformat() if job.created_at else None, "updated_at": job.updated_at.isoformat() if job.updated_at else None}


def software_jobs_snapshot(session: Session, serial: str | None = None) -> dict:
    stmt = select(Job).order_by(Job.created_at.desc()).limit(250)
    if serial:
        stmt = select(Job).where(Job.serial == serial).order_by(Job.created_at.desc()).limit(250)
    jobs = session.exec(stmt).all()
    rows = [job_row(job) for job in jobs]
    counters = Counter(row["status"] for row in rows)
    by_rollout = {}
    for row in rows:
        rollout_id = row.get("rollout_id") or "manual"
        group = by_rollout.setdefault(rollout_id, {"rollout_id": rollout_id, "jobs": [], "counters": Counter()})
        group["jobs"].append(row)
        group["counters"][row["status"]] += 1
    rollouts = []
    for group in by_rollout.values():
        counters_dict = {status: group["counters"].get(status, 0) for status in OTA_STATUSES}
        total = len(group["jobs"])
        progress = round(sum(job.get("progress_percent", 0) for job in group["jobs"]) / total) if total else 0
        latest = max((job.get("updated_at") or job.get("created_at") or "") for job in group["jobs"])
        rollouts.append({"rollout_id": group["rollout_id"], "total": total, "progress_percent": progress, "counters": counters_dict, "latest_at": latest})
    return {"jobs": rows, "counters": {status: counters.get(status, 0) for status in OTA_STATUSES}, "success": counters.get("success", 0), "failed": counters.get("failed", 0), "rollouts": sorted(rollouts, key=lambda r: r["latest_at"], reverse=True), "generated_at": datetime.now(timezone.utc).isoformat()}


def _agent_releases():
    try:
        releases = fetch_json(f"https://api.github.com/repos/{github_repo()}/releases")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"could not fetch GitHub releases: {exc}")
    items = []
    for release in releases:
        item = normalize_agent_release(release)
        if item:
            items.append(item)
    items = sorted(items, key=release_sort_key, reverse=True)[:MAX_RELEASES]
    for index, item in enumerate(items):
        item["latest"] = index == 0
        item["channel"] = "beta" if item.get("prerelease") else "stable"
    return {"repository": github_repo(), "releases": items, "latest": items[0] if items else None, "count": len(items), "generated_at": datetime.now(timezone.utc).isoformat()}


def _queue_agent_release(body: dict, session: Session):
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
        payload = {"url": url, "sha256": sha256, "version": version, "source": "software_repository", "rollout_id": rollout_id, "batch": batch, "batch_size": batch_size, "rollback": rollback, "rollback_from": rollback_from, "canary": body.get("canary", False), "maintenance_window": body.get("maintenance_window"), "auto_rollback": body.get("auto_rollback", False)}
        job = Job(serial=serial, kind="agent_update", payload_json=json.dumps(payload), status="queued")
        session.add(job)
        jobs.append(job)
    session.commit()
    for job in jobs:
        session.refresh(job)
    return {"ok": True, "rollout_id": rollout_id, "jobs": [job_row(j) for j in jobs]}


def _rollback_agent_release(body: dict, session: Session):
    body["rollback"] = True
    body["rollback_from"] = body.get("rollback_from") or body.get("current_version")
    return _queue_agent_release(body, session)


@router.get("/agent/releases")
@stripped_router.get("/agent/releases")
def agent_releases(actor: str = Depends(require_admin)):
    return _agent_releases()


@router.post("/agent/queue")
@stripped_router.post("/agent/queue")
def queue_agent_release(body: dict, session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    return _queue_agent_release(body, session)


@router.post("/agent/rollback")
@stripped_router.post("/agent/rollback")
def rollback_agent_release(body: dict, session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    return _rollback_agent_release(body, session)


@router.get("/jobs")
@stripped_router.get("/jobs")
def software_jobs(serial: str | None = None, session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    return software_jobs_snapshot(session, serial)
