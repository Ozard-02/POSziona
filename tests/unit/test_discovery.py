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

    assert main_mod._discover_or_ask_server() == 'http://192.168.1.99:5000/'
