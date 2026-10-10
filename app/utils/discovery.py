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


def _beacon_payload(port):
    return json.dumps({
        'magic': MAGIC,
        'name': socket.gethostname(),
        'port': port,
    }).encode('utf-8')


def send_beacon(port, dest=('255.255.255.255', DISCOVERY_PORT)):
    """Emit one announcement datagram (best effort, never raises)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(_beacon_payload(port), dest)
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
