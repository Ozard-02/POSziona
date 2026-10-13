"""
LAN discovery + client server-picking. One behavior per test; slow UDP
round-trips merged so the file pays the ~3s listen cost once.
"""
import threading
import time

import pytest

from app.utils import discovery


TEST_PORT = 42199  # discovery listener port (≠ server ports)


def test_beacon_round_trip():
    """Loopback beacons are discovered with url/host/name/version; dupes collapse."""
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
    first = by_port[5000]
    assert first['url'] == 'http://127.0.0.1:5000/'
    assert first['host'] == '127.0.0.1'
    assert first['name']
    assert first['version']  # None-tolerant for old servers, present for ours


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


@pytest.mark.parametrize('route_ip,local_ips,expected', [
    ('192.168.178.171', {'172.17.0.1', '192.168.178.171'}, '192.168.178.171'),
    (None, set(), '127.0.0.1'),
])
def test_get_lan_ip(monkeypatch, route_ip, local_ips, expected):
    """Default-route IP wins over docker bridges; loopback when offline."""
    monkeypatch.setattr(discovery, '_default_route_ip', lambda: route_ip)
    monkeypatch.setattr(discovery, '_local_ipv4s', lambda: set(local_ips))
    assert discovery.get_lan_ip() == expected


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


def _two_servers(version=None):
    second = {'name': 'cassa2', 'host': '192.168.1.11', 'port': 5000,
              'url': 'http://192.168.1.11:5000/'}
    first = {'name': 'CASSA-1', 'host': '192.168.1.10', 'port': 5000,
             'url': 'http://192.168.1.10:5000/'}
    if version:
        first['version'] = version
    return [first, second]


@pytest.mark.parametrize('answer,expected_url,expected_out', [
    ('1', 'http://192.168.1.10:5000/', ['CASSA-1', '(v0.1.4)', 'cassa2']),
    ('2', 'http://192.168.1.11:5000/', ['CASSA-1', 'cassa2']),
    ('', 'http://192.168.1.10:5000/', []),  # Enter picks server 1, as promised
])
def test_discover_menu_selection(monkeypatch, capsys, answer, expected_url, expected_out):
    """Numbered picker returns the chosen server; Enter means 1."""
    import builtins
    import app.main as main_mod

    monkeypatch.setattr('app.utils.discovery.discover',
                        lambda *a, **k: _two_servers(version='0.1.4'))
    monkeypatch.setattr(builtins, 'input', lambda *a: answer)

    assert main_mod._discover_or_ask_server() == expected_url
    out = capsys.readouterr().out
    assert all(marker in out for marker in expected_out)


@pytest.mark.parametrize('answers,probes,expected_url,expected_out', [
    # No beacons → manual entry works.
    (['192.168.1.99:5000'], [True], 'http://192.168.1.99:5000/', []),
    # Dead IP → hint + re-prompt; reachable IP → normalized.
    (['192.168.178.128', '192.168.178.128:5000'], [False, True],
     'http://192.168.178.128:5000/', ['Cannot reach']),
    # Garbage re-asks, then accepts.
    (['\x1b[A', '192.168.1.5:5000'], [True],
     'http://192.168.1.5:5000/', ['Not a valid address']),
    # Blank re-prompts — never a silent local server (split-brain guard).
    (['', '192.168.1.5'], [True], 'http://192.168.1.5:5000/', ['Ctrl-C']),
])
def test_manual_entry_flows(monkeypatch, capsys, answers, probes,
                            expected_url, expected_out):
    """Manual server entry: fallback, reprompt, garbage and blank handling."""
    import builtins
    import app.main as main_mod

    monkeypatch.setattr('app.utils.discovery.discover', lambda *a, **k: [])
    monkeypatch.setattr(builtins, 'input', lambda *a: answers.pop(0))
    monkeypatch.setattr(main_mod, '_server_reachable',
                        lambda *a, **k: probes.pop(0))

    assert main_mod._discover_or_ask_server() == expected_url
    out = capsys.readouterr().out
    assert all(marker in out for marker in expected_out)


@pytest.mark.parametrize('raw,expected', [
    ('192.168.178.128', 'http://192.168.178.128:5000/'),
    ('http://192.168.178.128', 'http://192.168.178.128:5000/'),
    ('cassa1', 'http://cassa1:5000/'),
    ('192.168.1.10:5000', 'http://192.168.1.10:5000/'),
    ('http://192.168.1.10:5001/pos', 'http://192.168.1.10:5001/pos/'),
    ('', None),
    ('   ', None),
    ('\x1b[A', None),
    ('http://[::1', None),
])
def test_normalize_server_url(raw, expected):
    """Bare hosts gain :5000 (was: port-80 dead page); garbage → None, never raises."""
    import app.main as main_mod

    assert main_mod._normalize_server_url(raw) == expected


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


@pytest.mark.parametrize('device_settings,expected', [
    ({}, None),  # None → caller falls back to hostname
    ({'server_name': '  CASSA-1 '}, 'CASSA-1'),
])
def test_server_name_source(monkeypatch, device_settings, expected):
    """Admin-set tag wins; empty config falls back to machine hostname."""
    import socket
    import app.utils.discovery as disc

    monkeypatch.setattr('app.services.settings_service.get_device_settings',
                        lambda: device_settings)
    assert disc.get_server_name() == (expected or socket.gethostname())


def test_explicit_garbage_server_url_exits(monkeypatch, capsys):
    """--server-url garbage → exit 1 with example, not a traceback."""
    import pytest
    import app.main as main_mod

    with pytest.raises(SystemExit) as exc_info:
        main_mod.run_client_only(server_url='\x1b[A')
    assert exc_info.value.code == 1
    assert 'Example' in capsys.readouterr().out


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
