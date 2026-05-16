import json
import urllib.request
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from .db import get_session
from .models import Device, Job
from .security import require_admin

router = APIRouter(prefix="/api/software", tags=["Software Repository"])

GITHUB_REPO = "Q-Home/Q-Central"
AGENT_ASSET_PREFIX = "qbox-agent-"


def github_api(url: str):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Q-Central"})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


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
    version = release.get("tag_name") or release.get("name") or archive.get("name", "").replace(AGENT_ASSET_PREFIX, "").replace(".tar.gz", "")
    return {
        "kind": "agent_update",
        "name": release.get("name") or version,
        "version": str(version).lstrip("v"),
        "tag": release.get("tag_name"),
        "draft": release.get("draft", False),
        "prerelease": release.get("prerelease", False),
        "published_at": release.get("published_at"),
        "url": archive.get("browser_download_url"),
        "asset_name": archive.get("name"),
        "size_bytes": archive.get("size"),
        "manifest_url": manifest.get("browser_download_url") if manifest else None,
        "html_url": release.get("html_url"),
        "sha256": None,
    }


def job_payload(job: Job) -> dict:
    try:
        return json.loads(job.payload_json or "{}")
    except Exception:
        return {}


@router.get("/agent/releases")
def agent_releases(actor: str = Depends(require_admin)):
    try:
        releases = github_api(f"https://api.github.com/repos/{GITHUB_REPO}/releases")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"could not fetch GitHub releases: {exc}")
    items = []
    for release in releases:
        item = normalize_agent_release(release)
        if item:
            items.append(item)
    return {"repository": GITHUB_REPO, "releases": items, "count": len(items)}


@router.post("/agent/queue")
def queue_agent_release(body: dict, session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    serials = body.get("serials") or []
    version = body.get("version")
    url = body.get("url")
    sha256 = body.get("sha256")
    if not serials or not isinstance(serials, list):
        raise HTTPException(status_code=400, detail="serials list is required")
    if not url or not sha256:
        raise HTTPException(status_code=400, detail="url and sha256 are required")
    jobs = []
    for serial in serials:
        if not session.get(Device, serial):
            raise HTTPException(status_code=404, detail=f"device not found: {serial}")
        payload = {"url": url, "sha256": sha256, "version": version, "source": "software_repository"}
        job = Job(serial=serial, kind="agent_update", payload_json=json.dumps(payload), status="queued")
        session.add(job)
        jobs.append(job)
    session.commit()
    for job in jobs:
        session.refresh(job)
    return {"ok": True, "jobs": [{"id": j.id, "serial": j.serial, "status": j.status} for j in jobs]}


@router.get("/jobs")
def software_jobs(serial: str | None = None, session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    stmt = select(Job).order_by(Job.created_at.desc()).limit(100)
    if serial:
        stmt = select(Job).where(Job.serial == serial).order_by(Job.created_at.desc()).limit(100)
    jobs = session.exec(stmt).all()
    return {
        "jobs": [
            {
                "id": job.id,
                "serial": job.serial,
                "kind": job.kind,
                "status": job.status,
                "payload": job_payload(job),
                "result": job.result,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            }
            for job in jobs
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
