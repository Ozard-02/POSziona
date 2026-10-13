"""
LAN server discovery for Posziona clients (stdlib only).

Devices must share the same Wi-Fi/LAN. The server emits a tiny UDP
broadcast beacon every few seconds; a client with no --server-url
listens briefly at startup and offers the found servers as a numbered
menu (manual entry stays as fallback — some networks block broadcasts).

Payload is just an announcement (host name + port), no auth: the LAN is
already trusted to reach the POS port. Set POSZIONA_NO_BEACON=1 to stay
silent (e.g. untrusted networks).
"""
import json
import os
import socket
import threading
import time

DISCOVERY_PORT = 42137
MAGIC = 'posziona-v1'
BEACON_INTERVAL = 2.0
LISTEN_WINDOW = 5.0


def _local_ipv4s():
    """Non-loopback IPv4 addresses of this machine (stdlib only)."""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith('127.'):
                ips.add(ip)
    except socket.gaierror:
        pass
    # IP of the default-route interface (_default_route_ip never raises).
    route_ip = _default_route_ip()
    if route_ip:
        ips.add(route_ip)
    return ips


def _default_route_ip():
    """IP of the default-route interface (connect sends no packets)."""
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(('8.8.8.8', 80))
            ip = probe.getsockname()[0]
            if ip and not ip.startswith('127.'):
                return ip
        finally:
            probe.close()
    except OSError:
        pass
    return None


def get_server_name():
    """Friendly tag this server announces to clients.

    Admin → System → server name (device-global setting); falls back to
    the machine hostname so old installs still announce something useful.
    Never raises — beacons must not die on a locked DB.
    """
    try:
        from app.services.settings_service import get_device_settings
        name = (get_device_settings().get('server_name') or '').strip()
        if name:
            return name
    except Exception:
        pass
    return socket.gethostname()


def get_lan_ip():
    """Best-guess LAN IP to show other devices (loopback if offline).

    Prefers the default-route interface: alphabetical fallback kept
    picking docker/virtual bridges (e.g. 172.17.0.1) over the real Wi-Fi
    address (seen live 2026-10-12: hint showed docker0, server was on
    192.168.178.x).
    """
    primary = _default_route_ip()
    if primary:
        return primary
    ips = _local_ipv4s()
    if not ips:
        return '127.0.0.1'
    # Deterministic otherwise.
    return sorted(ips, key=lambda ip: (ip.startswith('169.254.'), ip))[0]


def _broadcast_targets():
    """Where to send beacons: limited broadcast + per-interface /24.

    The limited broadcast covers the common single-Wi-Fi case. The
    directed /24s cover multi-homed machines (ethernet + Wi-Fi) and
    hotspots whose interface is not the default route. /24 is a guess —
    wrong mask only means one redundant datagram every 2 s.
    """
    targets = [('255.255.255.255', DISCOVERY_PORT)]
    for ip in _local_ipv4s():
        parts = ip.split('.')
        if len(parts) == 4:
            targets.append(('.'.join(parts[:3] + ['255']), DISCOVERY_PORT))
    seen = set()
    return [t for t in targets if not (t in seen or seen.add(t))]


def _beacon_payload(port):
    from app.utils.config import APP_VERSION
    return json.dumps({
        'magic': MAGIC,
        'name': get_server_name(),
        'port': port,
        'version': APP_VERSION,
    }).encode('utf-8')


def send_beacon(port, dest=None):
    """Emit one announcement datagram per broadcast target.

    Best effort, never raises. `dest` overrides targets (tests).
    """
    payload = _beacon_payload(port)
    targets = [dest] if dest else _broadcast_targets()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            for target in targets:
                try:
                    sock.sendto(payload, target)
                except OSError:
                    pass
        finally:
            sock.close()
    except OSError:
        pass


def discover(timeout=LISTEN_WINDOW, port=DISCOVERY_PORT):
    """Listen for beacons; return [{'name', 'host', 'port', 'url'}...].

    Duplicates collapsed, sorted by host for a stable menu.
    """
    found = {}
    deadline = time.time() + timeout
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass  # macOS-only / unavailable — REUSEADDR suffices
        sock.bind(('0.0.0.0', port))
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            sock.settimeout(min(remaining, 1.0))
            try:
                data, addr = sock.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                msg = json.loads(data.decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(msg, dict) or msg.get('magic') != MAGIC:
                continue
            try:
                srv_port = int(msg.get('port', 0))
            except (TypeError, ValueError):
                continue
            if not 0 < srv_port < 65536:
                continue
            host = addr[0]
            found[(host, srv_port)] = {
                'name': str(msg.get('name', host)),
                'host': host,
                'port': srv_port,
                'url': f'http://{host}:{srv_port}/',
                # Absent on pre-0.1.4 servers — display tolerates None.
                'version': msg.get('version'),
            }
    except OSError:
        pass  # port busy (another client discovering) → no suggestions
    finally:
        sock.close()
    return sorted(found.values(), key=lambda s: (s['host'], s['port']))


def start_beacon_loop(port, interval=BEACON_INTERVAL):
    """Emit beacons in a daemon thread until the returned event is set."""
    if os.environ.get('POSZIONA_NO_BEACON'):
        stop = threading.Event()
        stop.set()  # already stopped: beacon disabled
        return stop
    stop = threading.Event()

    def _loop():
        send_beacon(port)  # announce immediately, then periodically
        while not stop.wait(interval):
            send_beacon(port)

    threading.Thread(target=_loop, daemon=True).start()
    return stop
