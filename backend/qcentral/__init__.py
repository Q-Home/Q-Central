import json
from datetime import datetime, timezone

from sqlalchemy import event

from .models import AuditLog, Job

ACTIVE_AGENT_UPDATE_STATUSES = {
    "downloading",
    "verifying",
    "installing",
    "rebooting",
    "running",
    "in_progress",
}

FINAL_AGENT_UPDATE_STATUSES = {
    "success",
    "failed",
    "done",
    "cancelled",
}


def _safe_json(value):
    if not value:
        return {}
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normalize_version(value):
    if value is None:
        return None
    value = str(value).strip()
    if value.startswith("qbox-agent-"):
        value = value[len("qbox-agent-"):]
    if value.startswith("v"):
        value = value[1:]
    return value or None


@event.listens_for(AuditLog, "after_insert")
def _complete_agent_update_from_heartbeat(mapper, connection, target):
    if target.event != "heartbeat" or not target.serial:
        return

    detail = _safe_json(target.detail)
    metrics = detail.get("metrics") if isinstance(detail.get("metrics"), dict) else {}
    current_version = _normalize_version(
        metrics.get("agent_version") or metrics.get("version")
    )
    if not current_version:
        return

    job_table = Job.__table__
    rows = connection.execute(
        job_table.select()
        .where(job_table.c.serial == target.serial)
        .where(job_table.c.kind == "agent_update")
        .order_by(job_table.c.created_at.desc())
    ).mappings().all()

    for job in rows:
        status = job.get("status")
        if status in FINAL_AGENT_UPDATE_STATUSES:
            continue
        if status not in ACTIVE_AGENT_UPDATE_STATUSES:
            continue

        payload = _safe_json(job.get("payload_json"))
        target_version = _normalize_version(
            payload.get("version") or payload.get("target_version")
        )
        if not target_version or target_version != current_version:
            continue

        result = {
            "status": "success",
            "progress": 100,
            "message": f"Heartbeat confirmed agent version {current_version}",
            "agent_version": current_version,
            "completed_by": "heartbeat",
        }
        connection.execute(
            job_table.update()
            .where(job_table.c.id == job.get("id"))
            .values(
                status="success",
                result=json.dumps(result)[:4000],
                updated_at=datetime.now(timezone.utc),
            )
        )
