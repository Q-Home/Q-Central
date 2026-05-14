import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

DB_PATH = os.getenv("QBOX_DB", "/data/central.db")

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

@contextmanager
def db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            serial TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            claim_token TEXT NOT NULL,
            customer TEXT,
            site TEXT,
            model TEXT,
            zerotier_node_id TEXT,
            zerotier_ip TEXT,
            authorized INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'registered',
            firmware TEXT,
            apps TEXT NOT NULL DEFAULT '[]',
            last_seen TEXT,
            metadata TEXT NOT NULL DEFAULT '{}'
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ota_jobs (
            id TEXT PRIMARY KEY,
            serial TEXT NOT NULL,
            target_firmware TEXT,
            app TEXT,
            command TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

def row_to_device(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["authorized"] = bool(d["authorized"])
    d["apps"] = json.loads(d.get("apps") or "[]")
    d["metadata"] = json.loads(d.get("metadata") or "{}")
    return d

def get_device(serial: str):
    with db() as conn:
        row = conn.execute("SELECT * FROM devices WHERE serial=?", (serial,)).fetchone()
        return row_to_device(row) if row else None

def list_devices():
    with db() as conn:
        return [row_to_device(r) for r in conn.execute("SELECT * FROM devices ORDER BY serial").fetchall()]

def upsert_device(device: dict[str, Any]):
    with db() as conn:
        conn.execute("""
        INSERT INTO devices(serial,name,claim_token,customer,site,model,zerotier_node_id,zerotier_ip,authorized,status,firmware,apps,last_seen,metadata)
        VALUES(:serial,:name,:claim_token,:customer,:site,:model,:zerotier_node_id,:zerotier_ip,:authorized,:status,:firmware,:apps,:last_seen,:metadata)
        ON CONFLICT(serial) DO UPDATE SET
          name=excluded.name, claim_token=excluded.claim_token, customer=excluded.customer,
          site=excluded.site, model=excluded.model, zerotier_node_id=excluded.zerotier_node_id,
          zerotier_ip=excluded.zerotier_ip, authorized=excluded.authorized, status=excluded.status,
          firmware=excluded.firmware, apps=excluded.apps, last_seen=excluded.last_seen, metadata=excluded.metadata
        """, {
            **device,
            "authorized": 1 if device.get("authorized") else 0,
            "apps": json.dumps(device.get("apps", [])),
            "metadata": json.dumps(device.get("metadata", {})),
        })

def update_device(serial: str, updates: dict[str, Any]):
    current = get_device(serial)
    if not current:
        return None
    current.update(updates)
    upsert_device(current)
    return get_device(serial)

def insert_ota(job: dict[str, Any]):
    t = now_iso()
    job = {**job, "created_at": t, "updated_at": t}
    with db() as conn:
        conn.execute("""
        INSERT INTO ota_jobs(id,serial,target_firmware,app,command,status,created_at,updated_at)
        VALUES(:id,:serial,:target_firmware,:app,:command,:status,:created_at,:updated_at)
        """, job)

def list_ota(serial: str | None = None):
    with db() as conn:
        if serial:
            rows = conn.execute("SELECT * FROM ota_jobs WHERE serial=? ORDER BY created_at", (serial,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM ota_jobs ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

def mark_ota_done(job_id: str):
    with db() as conn:
        conn.execute("UPDATE ota_jobs SET status='done', updated_at=? WHERE id=?", (now_iso(), job_id))
