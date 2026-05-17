import argparse
import json
import os
import platform
import re
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
STARTED_AT = time.time()


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


def read_file(path, default=None):
    try:
        p = Path(path)
        if p.exists():
            return p.read_text(errors='ignore').strip()
    except Exception:
        pass
    return default


def parse_key_value_file(path):
    data = {}
    text = read_file(path, '') or ''
    for line in text.splitlines():
        if '=' not in line or line.strip().startswith('#'):
            continue
        key, value = line.split('=', 1)
        data[key.strip()] = value.strip().strip('"')
    return data


def first_existing(paths):
    for path in paths:
        value = read_file(path)
        if value:
            return value
    return None


def agent_version(cfg):
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
    return cfg.get('agent_version', 'unknown')


def os_release():
    data = parse_key_value_file('/etc/os-release')
    lsb = parse_key_value_file('/etc/lsb-release')
    data.update({f'lsb_{k.lower()}': v for k, v in lsb.items()})
    return {
        'id': data.get('ID'),
        'name': data.get('NAME'),
        'pretty_name': data.get('PRETTY_NAME'),
        'version': data.get('VERSION'),
        'version_id': data.get('VERSION_ID'),
        'version_codename': data.get('VERSION_CODENAME') or data.get('DEBIAN_CODENAME') or data.get('lsb_distrib_codename'),
        'debian_codename': data.get('VERSION_CODENAME') or data.get('DEBIAN_CODENAME') or data.get('lsb_distrib_codename'),
        'debian_version': read_file('/etc/debian_version'),
        'kernel': platform.release(),
        'architecture': platform.machine(),
    }


def dietpi_info():
    candidates = [
        '/boot/dietpi/.version',
        '/DietPi/dietpi/.version',
        '/etc/dietpi/.version',
        '/var/lib/dietpi/.version',
    ]
    raw = first_existing(candidates)
    info = {'installed': bool(raw), 'raw': raw, 'version': None, 'branch': None}
    if raw:
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith('G_DIETPI_VERSION_CORE='):
                info['core'] = line.split('=', 1)[1].strip().strip('"')
            elif line.startswith('G_DIETPI_VERSION_SUB='):
                info['sub'] = line.split('=', 1)[1].strip().strip('"')
            elif line.startswith('G_DIETPI_VERSION_RC='):
                info['rc'] = line.split('=', 1)[1].strip().strip('"')
            elif line.startswith('G_GITBRANCH='):
                info['branch'] = line.split('=', 1)[1].strip().strip('"')
        if info.get('core') and info.get('sub'):
            info['version'] = '.'.join([info.get('core'), info.get('sub'), info.get('rc') or '0'])
        else:
            match = re.search(r'(\d+\.\d+(?:\.\d+)?)', raw)
            if match:
                info['version'] = match.group(1)
    cmd_version = sh('command -v dietpi-launcher >/dev/null 2>&1 && dietpi-launcher 2>/dev/null | head -n 1 || true', timeout=5)
    if cmd_version and not info.get('version'):
        match = re.search(r'(\d+\.\d+(?:\.\d+)?)', cmd_version)
        if match:
            info['version'] = match.group(1)
    return info


def loxberry_info():
    paths = [
        '/opt/loxberry/config/system/general.json',
        '/opt/loxberry/config/system/general.cfg',
        '/opt/loxberry/config/system/lbversion.cfg',
        '/opt/loxberry/system/version',
        '/etc/loxberry_version',
    ]
    raw_values = {path: read_file(path) for path in paths if read_file(path)}
    version = None
    name = None
    for path, raw in raw_values.items():
        if raw.strip().startswith('{'):
            try:
                data = json.loads(raw)
                version = version or data.get('version') or data.get('lbversion') or data.get('LBVERSION')
                name = name or data.get('name') or data.get('hostname')
            except Exception:
                pass
        for pattern in [r'LBVERSION\s*=\s*["\']?([^"\'\n]+)', r'VERSION\s*=\s*["\']?([^"\'\n]+)', r'(\d+\.\d+(?:\.\d+)?)']:
            match = re.search(pattern, raw)
            if match and not version:
                version = match.group(1).strip()
    lbhome = os.environ.get('LBHOME') or ('/opt/loxberry' if Path('/opt/loxberry').exists() else None)
    return {
        'installed': bool(lbhome or raw_values),
        'version': version,
        'name': name,
        'home': lbhome,
        'raw_sources': list(raw_values.keys()),
    }


def board_info():
    model = read_file('/proc/device-tree/model') or read_file('/sys/firmware/devicetree/base/model') or read_file('/sys/class/dmi/id/product_name')
    serial = read_file('/proc/device-tree/serial-number') or read_file('/sys/class/dmi/id/product_serial')
    vendor = read_file('/sys/class/dmi/id/sys_vendor')
    return {'model': model, 'serial': serial, 'vendor': vendor}


def hardware_platform(cfg):
    configured = cfg.get('hardware_platform') or cfg.get('platform')
    board = board_info().get('model') or ''
    hay = f'{configured or ""} {cfg.get("model") or ""} {board}'.lower()
    if 'nanopi' in hay or 'r5c' in hay:
        return 'nanopi-r5c'
    if 'raspberry' in hay or 'pi 5' in hay:
        return 'raspberry-pi-5'
    if 'andino' in hay or 'din' in hay:
        return 'andino-x1'
    return configured or 'generic-arm64'


def zerotier_node_id():
    out = sh('zerotier-cli info 2>/dev/null', timeout=5)
    parts = out.split()
    return parts[2] if len(parts) >= 3 else None


def zerotier_status():
    info = sh('zerotier-cli info 2>/dev/null', timeout=5)
    networks = sh('zerotier-cli listnetworks -j 2>/dev/null', timeout=8)
    parsed = []
    try:
        data = json.loads(networks) if networks else []
        for n in data:
            parsed.append({'id': n.get('nwid') or n.get('id'), 'name': n.get('name'), 'status': n.get('status'), 'assigned_addresses': n.get('assignedAddresses') or [], 'mac': n.get('mac')})
    except Exception:
        parsed = []
    return {'info': info, 'node_id': zerotier_node_id(), 'networks': parsed}


def ip_addr():
    return sh("hostname -I | awk '{print $1}'", timeout=5) or None


def network_addresses():
    result = []
    for iface, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if getattr(addr, 'family', None) == socket.AF_INET:
                result.append({'interface': iface, 'address': addr.address, 'netmask': addr.netmask})
    return result


def docker_available():
    return sh('command -v docker >/dev/null 2>&1 && echo yes || echo no', timeout=5) == 'yes'


def docker_containers():
    if not docker_available():
        return []
    out = sh("docker ps -a --format '{{json .}}' 2>/dev/null", timeout=20)
    containers = []
    for line in out.splitlines():
        try:
            item = json.loads(line)
            containers.append({'id': item.get('ID'), 'name': item.get('Names'), 'image': item.get('Image'), 'status': item.get('Status'), 'state': item.get('State'), 'ports': item.get('Ports')})
        except Exception:
            continue
    return containers


def docker_stats():
    if not docker_available():
        return []
    out = sh("docker stats --no-stream --format '{{json .}}' 2>/dev/null", timeout=25)
    stats = []
    for line in out.splitlines():
        try:
            item = json.loads(line)
            stats.append({'name': item.get('Name'), 'cpu': item.get('CPUPerc'), 'memory': item.get('MemUsage'), 'memory_percent': item.get('MemPerc'), 'net_io': item.get('NetIO'), 'block_io': item.get('BlockIO'), 'pids': item.get('PIDs')})
        except Exception:
            continue
    return stats


def installed_apps():
    return [c['name'] for c in docker_containers() if c.get('state') == 'running' and c.get('name')]


def disk_usage():
    disks = []
    seen = set()
    for part in psutil.disk_partitions(all=False):
        if part.mountpoint in seen:
            continue
        seen.add(part.mountpoint)
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({'device': part.device, 'mountpoint': part.mountpoint, 'fstype': part.fstype, 'total_gb': round(usage.total / 1024 / 1024 / 1024, 2), 'used_gb': round(usage.used / 1024 / 1024 / 1024, 2), 'free_gb': round(usage.free / 1024 / 1024 / 1024, 2), 'percent': usage.percent})
        except Exception:
            continue
    return disks


def metrics():
    cfg = load()
    boot_time = psutil.boot_time()
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    root_disk = psutil.disk_usage('/')
    net = psutil.net_io_counters()
    cpu_freq = psutil.cpu_freq()
    load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else (None, None, None)
    os_info = os_release()
    dietpi = dietpi_info()
    loxberry = loxberry_info()
    board = board_info()
    return {
        'hostname': socket.gethostname(),
        'fqdn': socket.getfqdn(),
        'platform': platform.platform(),
        'system': platform.system(),
        'machine': platform.machine(),
        'python_version': platform.python_version(),
        'agent_version': agent_version(cfg),
        'hardware_platform': hardware_platform(cfg),
        'board_model': board.get('model'),
        'board_serial': board.get('serial'),
        'board_vendor': board.get('vendor'),
        'os': os_info,
        'os_pretty_name': os_info.get('pretty_name'),
        'os_name': os_info.get('name'),
        'os_version': os_info.get('version'),
        'os_version_id': os_info.get('version_id'),
        'debian_codename': os_info.get('debian_codename'),
        'debian_version': os_info.get('debian_version'),
        'kernel': os_info.get('kernel'),
        'dietpi': dietpi,
        'dietpi_installed': dietpi.get('installed'),
        'dietpi_version': dietpi.get('version'),
        'loxberry': loxberry,
        'loxberry_installed': loxberry.get('installed'),
        'loxberry_version': loxberry.get('version'),
        'agent_uptime_seconds': int(time.time() - STARTED_AT),
        'boot_time': int(boot_time),
        'uptime_seconds': int(time.time() - boot_time),
        'cpu_percent': psutil.cpu_percent(interval=0.3),
        'cpu_count': psutil.cpu_count(),
        'cpu_freq_mhz': round(cpu_freq.current, 1) if cpu_freq else None,
        'load_avg': {'1m': load_avg[0], '5m': load_avg[1], '15m': load_avg[2]},
        'mem_percent': vm.percent,
        'mem_total_mb': round(vm.total / 1024 / 1024, 1),
        'mem_available_mb': round(vm.available / 1024 / 1024, 1),
        'swap_percent': swap.percent,
        'disk_percent': root_disk.percent,
        'disk_total_gb': round(root_disk.total / 1024 / 1024 / 1024, 2),
        'disk_free_gb': round(root_disk.free / 1024 / 1024 / 1024, 2),
        'disks': disk_usage(),
        'network': {'addresses': network_addresses(), 'bytes_sent': net.bytes_sent, 'bytes_recv': net.bytes_recv, 'packets_sent': net.packets_sent, 'packets_recv': net.packets_recv},
        'docker': {'available': docker_available(), 'containers': docker_containers(), 'stats': docker_stats()},
        'zerotier': zerotier_status(),
        'timestamp': int(time.time()),
    }


def provision(cfg):
    payload = {'serial': cfg['serial'], 'claim_token': cfg['claim_token'], 'model': cfg.get('model'), 'firmware': cfg.get('firmware', agent_version(cfg)), 'zerotier_node_id': zerotier_node_id(), 'ip_address': ip_addr()}
    r = requests.post(cfg['central_url'].rstrip('/') + '/api/provision', json=payload, timeout=15)
    r.raise_for_status()
    data = r.json()
    TOKEN.write_text(data['agent_token'])
    TOKEN.chmod(0o600)
    cfg.pop('claim_token', None)
    CONFIG.write_text(json.dumps(cfg, indent=2))
    return data


def report_job_result(cfg, token, job_id, status, output):
    requests.post(cfg['central_url'].rstrip('/') + f'/api/jobs/{job_id}/result', headers={'X-Agent-Token': token}, json={'status': status, 'output': str(output)[-6000:]}, timeout=20).raise_for_status()


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
    live_metrics = metrics()
    payload = {'serial': cfg['serial'], 'firmware': cfg.get('firmware', agent_version(cfg)), 'ip_address': ip_addr(), 'apps': installed_apps(), 'metrics': live_metrics}
    r = requests.post(cfg['central_url'].rstrip('/') + '/api/agent/heartbeat', headers={'X-Agent-Token': token}, json=payload, timeout=20)
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
