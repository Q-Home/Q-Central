import json
import os
import platform
import socket
import subprocess
import time
from pathlib import Path

import psutil
import requests

SERIAL = os.getenv("QBOX_SERIAL", Path("/etc/qbox/serial").read_text().strip() if Path("/etc/qbox/serial").exists() else "QBX-DEV-0000")
CLAIM_TOKEN = os.getenv("QBOX_CLAIM_TOKEN", Path("/etc/qbox/claim_token").read_text().strip() if Path("/etc/qbox/claim_token").exists() else "dev-claim-token")
CENTRAL_URL = os.getenv("QBOX_CENTRAL_URL", "http://qbox-central:8080").rstrip("/")
FIRMWARE = os.getenv("QBOX_FIRMWARE", "dev")
INTERVAL = int(os.getenv("QBOX_HEARTBEAT_INTERVAL", "30"))


def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def zerotier_info():
    node_id = run("zerotier-cli info | awk '{print $3}'")
    ip = run("ip -4 addr show | awk '/zt/{getline; print $2}' | cut -d/ -f1 | head -n1")
    return node_id, ip


def installed_apps():
    # Prefer qbox app manifests. Fall back to Docker compose labels/names.
    manifest_dir = Path("/etc/qbox/apps.d")
    if manifest_dir.exists():
        return sorted([p.stem for p in manifest_dir.glob("*.json")])
    names = run("docker ps --format '{{.Names}}' 2>/dev/null")
    return sorted([x for x in (names or "").splitlines() if x])


def metrics():
    return {
        "hostname": socket.gethostname(),
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage('/').percent,
        "uptime_seconds": int(time.time() - psutil.boot_time()),
    }


def provision():
    zt_node, zt_ip = zerotier_info()
    payload = {
        "serial": SERIAL,
        "claim_token": CLAIM_TOKEN,
        "hostname": socket.gethostname(),
        "model": platform.platform(),
        "firmware": FIRMWARE,
        "zerotier_node_id": zt_node,
        "zerotier_ip": zt_ip,
        "metadata": {"python": platform.python_version()},
    }
    r = requests.post(f"{CENTRAL_URL}/api/provision/request", json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


def heartbeat():
    payload = {
        "serial": SERIAL,
        "claim_token": CLAIM_TOKEN,
        "status": "online",
        "firmware": FIRMWARE,
        "apps": installed_apps(),
        "metrics": metrics(),
    }
    r = requests.post(f"{CENTRAL_URL}/api/heartbeat", json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


def poll_ota():
    r = requests.get(f"{CENTRAL_URL}/api/ota/jobs", params={"serial": SERIAL}, timeout=10)
    r.raise_for_status()
    for job in r.json():
        if job.get("status") != "queued":
            continue
        print(f"[qbox-agent] OTA job: {job}")
        command = job.get("command")
        if command:
            # For safety this test agent only logs commands unless explicitly enabled.
            if os.getenv("QBOX_AGENT_ALLOW_COMMANDS", "false").lower() == "true":
                subprocess.call(command, shell=True)
            else:
                print("[qbox-agent] command execution disabled; set QBOX_AGENT_ALLOW_COMMANDS=true")
        requests.post(f"{CENTRAL_URL}/api/ota/jobs/{job['id']}/done", timeout=10)


def main():
    print(f"[qbox-agent] starting serial={SERIAL} central={CENTRAL_URL}")
    while True:
        try:
            result = provision()
            print("[qbox-agent] provision", json.dumps(result))
            if result.get("authorized"):
                heartbeat()
                poll_ota()
            else:
                print("[qbox-agent] waiting for authorization")
        except Exception as exc:
            print(f"[qbox-agent] error: {exc}")
        time.sleep(INTERVAL)
