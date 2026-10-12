"""
LAN discovery: beacon round-trip over loopback (no real LAN needed).
"""
import threading
import time

from app.utils import discovery


TEST_PORT = 42199  # discovery listener port (≠ server ports)


def test_beacon_round_trip():
    """One beacon sent to loopback is discovered with name+url."""
    results = []
    listener = threading.Thread(
        target=lambda: results.extend(discovery.discover(timeout=3, port=TEST_PORT)),
        daemon=True,
    )
    listener.start()
    time.sleep(0.3)
    discovery.send_beacon(5000, dest=('127.0.0.1', TEST_PORT))
    discovery.send_beacon(5000, dest=('127.0.0.1', TEST_PORT))  # duplicate
    discovery.send_beacon(5001, dest=('127.0.0.1', TEST_PORT))  # second server
    listener.join(timeout=10)

    by_port = {s['port']: s for s in results}
    assert set(by_port) == {5000, 5001}, results
    assert by_port[5000]['url'] == 'http://127.0.0.1:5000/'
    assert by_port[5000]['host'] == '127.0.0.1'
    assert by_port[5000]['name']


def test_garbage_datagrams_ignored():
    """Non-beacon UDP noise never becomes a suggestion."""
    import socket
    results = []
    listener = threading.Thread(
        target=lambda: results.extend(discovery.discover(timeout=2, port=TEST_PORT)),
        daemon=True,
    )
    listener.start()
    time.sleep(0.3)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(b'hello?', ('127.0.0.1', TEST_PORT))
        sock.sendto(b'{"magic": "something-else"}', ('127.0.0.1', TEST_PORT))
        sock.sendto(b'{"magic": "posziona-v1", "port": 99999}', ('127.0.0.1', TEST_PORT))
    finally:
        sock.close()
    listener.join(timeout=10)
    assert results == [], results


def test_beacon_opt_out(monkeypatch):
    """POSZIONA_NO_BEACON=1 → loop returns an already-stopped event."""
    monkeypatch.setenv('POSZIONA_NO_BEACON', '1')
    stop = discovery.start_beacon_loop(5000)
    assert stop.is_set()


def test_lan_ip_is_plain_ipv4():
    """get_lan_ip returns dotted IPv4 (loopback when offline)."""
    import re
    ip = discovery.get_lan_ip()
    assert re.fullmatch(r'\d{1,3}(\.\d{1,3}){3}', ip), ip


def test_lan_ip_prefers_default_route_over_docker(monkeypatch):
    """Live bug 2026-10-12: hint showed 172.17.0.1 (docker0), not Wi-Fi."""
    monkeypatch.setattr(discovery, '_default_route_ip',
                        lambda: '192.168.178.171')
    monkeypatch.setattr(discovery, '_local_ipv4s',
                        lambda: {'172.17.0.1', '192.168.178.171'})
    assert discovery.get_lan_ip() == '192.168.178.171'


def test_lan_ip_falls_back_when_offline(monkeypatch):
    """No route and no interfaces → loopback."""
    monkeypatch.setattr(discovery, '_default_route_ip', lambda: None)
    monkeypatch.setattr(discovery, '_local_ipv4s', lambda: set())
    assert discovery.get_lan_ip() == '127.0.0.1'


def test_broadcast_targets_cover_all_interfaces(monkeypatch):
    """Limited broadcast always; directed /24 per local interface."""
    monkeypatch.setattr(discovery, '_local_ipv4s',
                        lambda: {'192.168.1.10', '10.0.0.5'})
    targets = discovery._broadcast_targets()
    hosts = {t[0] for t in targets}
    assert '255.255.255.255' in hosts
    assert '192.168.1.255' in hosts
    assert '10.0.0.255' in hosts
    assert all(t[1] == discovery.DISCOVERY_PORT for t in targets)


def test_server_binds_all_interfaces():
    """Remote clients need 0.0.0.0 (loopback-only rejects LAN)."""
    from app.utils.config import BIND_HOST
    import os
    assert BIND_HOST == os.environ.get('POSZIONA_BIND_HOST', '0.0.0.0')

def test_beacon_loop_emits(monkeypatch):
    """Loop sends immediately, then periodically, until stopped."""
    monkeypatch.delenv('POSZIONA_NO_BEACON', raising=False)
    sent = []
    monkeypatch.setattr(discovery, 'send_beacon',
                        lambda port: sent.append(port))
    stop = discovery.start_beacon_loop(5000, interval=0.2)
    time.sleep(0.7)
    stop.set()
    assert len(sent) >= 2, sent
    assert sent == [5000] * len(sent)


def test_discover_menu_shows_tag_and_version(monkeypatch, capsys):
    """Picker lists friendly tags (+version when the server sends one)."""
    import builtins
    import app.main as main_mod

    servers = [
        {'name': 'CASSA-1', 'host': '192.168.1.10', 'port': 5000,
         'url': 'http://192.168.1.10:5000/', 'version': '0.1.4'},
        {'name': 'oldbox', 'host': '192.168.1.11', 'port': 5000,
         'url': 'http://192.168.1.11:5000/'},
    ]
    monkeypatch.setattr('app.utils.discovery.discover', lambda *a, **k: servers)
    monkeypatch.setattr(builtins, 'input', lambda *a: '1')

    assert main_mod._discover_or_ask_server() == 'http://192.168.1.10:5000/'
    out = capsys.readouterr().out
    assert 'CASSA-1' in out and '(v0.1.4)' in out and 'oldbox' in out


def test_discover_menu_picks_server(monkeypatch, capsys):
    """Client offers found servers numbered; choice returns its URL."""
    import builtins
    import app.main as main_mod

    servers = [
        {'name': 'cassa1', 'host': '192.168.1.10', 'port': 5000,
         'url': 'http://192.168.1.10:5000/'},
        {'name': 'cassa2', 'host': '192.168.1.11', 'port': 5000,
         'url': 'http://192.168.1.11:5000/'},
    ]
    monkeypatch.setattr('app.utils.discovery.discover', lambda *a, **k: servers)
    monkeypatch.setattr(builtins, 'input', lambda *a: '2')

    assert main_mod._discover_or_ask_server() == 'http://192.168.1.11:5000/'
    out = capsys.readouterr().out
    assert 'cassa1' in out and 'cassa2' in out


def test_discover_fallback_to_manual(monkeypatch):
    """No beacons → manual entry still works (old behaviour)."""
    import builtins
    import app.main as main_mod

    monkeypatch.setattr('app.utils.discovery.discover', lambda *a, **k: [])
    monkeypatch.setattr(builtins, 'input', lambda *a: '192.168.1.99:5000')
    monkeypatch.setattr(main_mod, '_server_reachable', lambda *a, **k: True)

    assert main_mod._discover_or_ask_server() == 'http://192.168.1.99:5000/'


def test_normalize_bare_ip_gets_default_port():
    """Bare IP/hostname → :5000 appended (was: port 80 dead page)."""
    import app.main as main_mod

    assert main_mod._normalize_server_url('192.168.178.128') == \
        'http://192.168.178.128:5000/'
    assert main_mod._normalize_server_url('http://192.168.178.128') == \
        'http://192.168.178.128:5000/'
    assert main_mod._normalize_server_url('cassa1') == \
        'http://cassa1:5000/'


def test_normalize_keeps_explicit_port_and_path():
    """Explicit port/path untouched."""
    import app.main as main_mod

    assert main_mod._normalize_server_url('192.168.1.10:5000') == \
        'http://192.168.1.10:5000/'
    assert main_mod._normalize_server_url('http://192.168.1.10:5001/pos') == \
        'http://192.168.1.10:5001/pos/'
    assert main_mod._normalize_server_url('http://192.168.1.10:5000/') == \
        'http://192.168.1.10:5000/'


def test_discover_menu_empty_picks_first(monkeypatch):
    """Enter on the menu selects server 1, as the prompt promises."""
    import builtins
    import app.main as main_mod

    servers = [
        {'name': 'cassa1', 'host': '192.168.1.10', 'port': 5000,
         'url': 'http://192.168.1.10:5000/'},
        {'name': 'cassa2', 'host': '192.168.1.11', 'port': 5000,
         'url': 'http://192.168.1.11:5000/'},
    ]
    monkeypatch.setattr('app.utils.discovery.discover', lambda *a, **k: servers)
    monkeypatch.setattr(builtins, 'input', lambda *a: '')

    assert main_mod._discover_or_ask_server() == 'http://192.168.1.10:5000/'


def test_manual_unreachable_reprompts_then_accepts(monkeypatch, capsys):
    """Dead IP → hint + re-prompt; reachable IP → returned normalized."""
    import builtins
    import app.main as main_mod

    monkeypatch.setattr('app.utils.discovery.discover', lambda *a, **k: [])
    answers = iter(['192.168.178.128', '192.168.178.128:5000'])
    monkeypatch.setattr(builtins, 'input', lambda *a: next(answers))
    probes = iter([False, True])
    monkeypatch.setattr(main_mod, '_server_reachable',
                        lambda *a, **k: next(probes))

    assert main_mod._discover_or_ask_server() == \
        'http://192.168.178.128:5000/'
    out = capsys.readouterr().out
    assert 'Cannot reach' in out


def test_beacon_payload_has_tag_and_version():
    """Beacon announces the server tag + release (client picker needs both)."""
    import json
    import app.utils.discovery as disc
    from app.utils.config import APP_VERSION

    payload = json.loads(disc._beacon_payload(5000).decode('utf-8'))
    assert payload['magic'] == disc.MAGIC
    assert payload['port'] == 5000
    assert payload['version'] == APP_VERSION
    assert payload['name']


def test_server_name_defaults_to_hostname(monkeypatch):
    """No tag configured → machine hostname (old installs keep working)."""
    import socket
    import app.utils.discovery as disc

    monkeypatch.setattr('app.services.settings_service.get_device_settings',
                        lambda: {})
    assert disc.get_server_name() == socket.gethostname()


def test_server_name_uses_device_setting(monkeypatch):
    """Admin-set tag wins over hostname."""
    import app.utils.discovery as disc

    monkeypatch.setattr('app.services.settings_service.get_device_settings',
                        lambda: {'server_name': '  CASSA-1 '})
    assert disc.get_server_name() == 'CASSA-1'


def test_discover_returns_version():
    """discover() surfaces beacon version (None-tolerant for old servers)."""
    import threading
    import time
    import app.utils.discovery as disc
    from app.utils.config import APP_VERSION

    port = 42201
    results = []
    listener = threading.Thread(
        target=lambda: results.extend(disc.discover(timeout=3, port=port)),
        daemon=True,
    )
    listener.start()
    time.sleep(0.3)
    disc.send_beacon(5000, dest=('127.0.0.1', port))
    listener.join(timeout=10)

    assert len(results) == 1
    assert results[0]['version'] == APP_VERSION
    assert results[0]['name']


def test_server_reachable_loopback():
    """Probe: open port reachable, closed port not (real sockets)."""
    import socket
    import app.main as main_mod

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)
    open_url = f'http://127.0.0.1:{srv.getsockname()[1]}/'
    try:
        assert main_mod._server_reachable(open_url) is True
    finally:
        srv.close()
    assert main_mod._server_reachable('http://127.0.0.1:9/') is False
