import argparse
import json
import os
import socket
import subprocess
import time
from pathlib import Path

import psutil
import requests

CONFIG = Path('/etc/qbox-agent/config.json')
TOKEN = Path('/etc/qbox-agent/agent-token')
VERSION_FILE = Path('/etc/qbox-agent/version')
LOCK = Path('/run/qbox-agent-job.lock')


def sh(cmd, timeout=120):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT, timeout=timeout).strip()
    except subprocess.CalledProcessError as exc:
        return (exc.output or str(exc)).strip()
    except Exception as exc:
        return str(exc)


def run_checked(args, timeout=300, cwd=None):
    proc = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False, cwd=cwd)
    output = (proc.stdout or '') + (proc.stderr or '')
    return proc.returncode, output.strip()


def load():
    return json.loads(CONFIG.read_text())


def agent_version(cfg):
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
    return cfg.get('agent_version', 'unknown')


def zerotier_node_id():
    out = sh('zerotier-cli info 2>/dev/null', timeout=5)
    parts = out.split()
    return parts[2] if len(parts) >= 3 else None


def ip_addr():
    return sh("hostname -I | awk '{print $1}'", timeout=5) or None


def installed_apps():
    out = sh('docker ps --format {{.Names}} 2>/dev/null', timeout=10)
    return [x for x in out.splitlines() if x]


def metrics():
    return {
        'hostname': socket.gethostname(),
        'cpu_percent': psutil.cpu_percent(),
        'mem_percent': psutil.virtual_memory().percent,
        'disk_percent': psutil.disk_usage('/').percent,
        'agent_version': agent_version(load()),
    }


def provision(cfg):
    payload = {
        'serial': cfg['serial'],
        'claim_token': cfg['claim_token'],
        'model': cfg.get('model'),
        'firmware': cfg.get('firmware', agent_version(cfg)),
        'zerotier_node_id': zerotier_node_id(),
        'ip_address': ip_addr(),
    }
    r = requests.post(cfg['central_url'].rstrip('/') + '/api/provision', json=payload, timeout=15)
    r.raise_for_status()
    data = r.json()
    TOKEN.write_text(data['agent_token'])
    TOKEN.chmod(0o600)
    cfg.pop('claim_token', None)
    CONFIG.write_text(json.dumps(cfg, indent=2))
    return data


def report_job_result(cfg, token, job_id, status, output):
    requests.post(
        cfg['central_url'].rstrip('/') + f'/api/jobs/{job_id}/result',
        headers={'X-Agent-Token': token},
        json={'status': status, 'output': str(output)[-6000:]},
        timeout=20,
    ).raise_for_status()


def acquire_lock():
    if LOCK.exists():
        raise RuntimeError('another qbox-agent job is already running')
    LOCK.write_text(str(os.getpid()))


def release_lock():
    try:
        LOCK.unlink(missing_ok=True)
    except Exception:
        pass


def validate_compose_path(path):
    allowed_roots = ['/storage/dockers', '/opt/qbox-apps']
    real = os.path.realpath(path)
    if not any(real == root or real.startswith(root + '/') for root in allowed_roots):
        raise ValueError(f'compose path not allowed: {real}')
    return real


def job_compose_pull(payload):
    path = validate_compose_path(payload.get('path', '/storage/dockers'))
    compose_file = payload.get('compose_file')
    cmd = ['docker', 'compose']
    if compose_file:
        cmd += ['-f', os.path.join(path, compose_file)]
    cmd += ['pull']
    rc1, out1 = run_checked(cmd, timeout=900, cwd=path)
    if rc1 != 0:
        return 'failed', out1
    cmd[-1] = 'up'
    cmd += ['-d', '--remove-orphans']
    rc2, out2 = run_checked(cmd, timeout=900, cwd=path)
    return ('done' if rc2 == 0 else 'failed'), out1 + '\n' + out2


def job_app_update(payload):
    return job_compose_pull(payload)


def job_app_restart(payload):
    path = validate_compose_path(payload.get('path', '/storage/dockers'))
    service = payload.get('service')
    if not service:
        raise ValueError('service is required')
    rc, out = run_checked(['docker', 'compose', 'restart', service], timeout=300, cwd=path)
    return ('done' if rc == 0 else 'failed'), out


def job_agent_update(payload):
    url = payload.get('url')
    sha256 = payload.get('sha256')
    if not url or not sha256:
        raise ValueError('url and sha256 are required')
    version = payload.get('version')
    cmd = ['systemd-run', '--unit=qbox-agent-self-update', '--collect', '/opt/qbox-agent/update-agent.sh', '--url', url, '--sha256', sha256]
    if version:
        cmd += ['--version', version]
    rc, out = run_checked(cmd, timeout=60)
    return ('accepted' if rc == 0 else 'failed'), out or 'self-update scheduled through systemd-run'


def run_job(cfg, token, job):
    payload = json.loads(job['payload_json']) if isinstance(job.get('payload_json'), str) else job.get('payload_json', {})
    try:
        acquire_lock()
        kind = job['kind']
        if kind == 'agent_update':
            status, output = job_agent_update(payload)
        elif kind == 'app_update':
            status, output = job_app_update(payload)
        elif kind == 'app_restart':
            status, output = job_app_restart(payload)
        elif kind == 'compose_pull':
            status, output = job_compose_pull(payload)
        else:
            status, output = 'unknown', f'unknown job kind: {kind}'
    except Exception as exc:
        status, output = 'failed', str(exc)
    finally:
        release_lock()
    report_job_result(cfg, token, job['id'], status, output)


def heartbeat(cfg):
    token = TOKEN.read_text().strip()
    payload = {
        'serial': cfg['serial'],
        'firmware': cfg.get('firmware', agent_version(cfg)),
        'ip_address': ip_addr(),
        'apps': installed_apps(),
        'metrics': metrics(),
    }
    r = requests.post(cfg['central_url'].rstrip('/') + '/api/agent/heartbeat', headers={'X-Agent-Token': token}, json=payload, timeout=15)
    r.raise_for_status()
    for job in r.json().get('jobs', []):
        run_job(cfg, token, job)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--provision', action='store_true')
    args = parser.parse_args()
    cfg = load()
    if args.provision or not TOKEN.exists():
        provision(cfg)
    while True:
        heartbeat(load())
        if args.once:
            break
        time.sleep(int(load().get('interval', 60)))


if __name__ == '__main__':
    main()
