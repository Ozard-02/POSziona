"""
Thermal printing without hardware: the device is a temp file.

Bytes asserted: ESC @ init, sanitized text, alignment, partial cut.
"""
import os
import threading

import pytest

from app.services import printer_service as prn


def test_build_bytes_envelope():
    data = prn.build_bytes('Riga 1\nRiga 2', cols=42, cut=True)
    assert data.startswith(b'\x1b@')          # init
    assert b'\x1ba\x00' in data               # left align
    assert b'Riga 1\nRiga 2\n' in data
    assert data.endswith(b'\x1bd\x04\x1dV\x01')  # feed + partial cut


def test_build_bytes_no_cut():
    data = prn.build_bytes('x', cut=False)
    assert b'\x1dV' not in data


def test_sanitize_euro_accents_width():
    assert prn.sanitize_line('Caffè €5,00', 42) == 'Caffe EUR5,00'
    assert prn.sanitize_line('TÈ È Ù', 42) == 'TE E U'
    assert prn.sanitize_line('x' * 100, 42) == 'x' * 42
    assert prn.sanitize_line('A\tB', 42) == 'A B'


def test_resolve_rejects_bad_config(monkeypatch):
    import app.services.settings_service as settings_mod
    monkeypatch.setattr(settings_mod, 'get_effective_settings',
                        lambda db: {'printer_path': ''})
    with pytest.raises(ValueError):
        prn.resolve_device('any')
    monkeypatch.setattr(settings_mod, 'get_effective_settings',
                        lambda db: {'printer_path': '/dev/usb/lp0',
                                    'printer_baud': '777'})
    with pytest.raises(ValueError):
        prn.resolve_device('any')


def test_resolve_auto_empty(monkeypatch):
    import app.services.settings_service as settings_mod
    import glob as glob_mod
    monkeypatch.setattr(settings_mod, 'get_effective_settings',
                        lambda db: {'printer_path': 'auto'})
    monkeypatch.setattr(glob_mod, 'glob', lambda pattern: [])
    with pytest.raises(ValueError):
        prn.resolve_device('any')


def test_open_serial_rejects_baud():
    with pytest.raises(ValueError):
        prn._open_serial('/dev/ttyUSB0', 12345)


pty = pytest.importorskip('pty')


def _responder(master_fd, stop):
    """Fake ESC/POS printer: answer DLE EOT with one status byte."""
    import select as select_mod
    while not stop.is_set():
        r, _, _ = select_mod.select([master_fd], [], [], 0.2)
        if not r:
            continue
        try:
            data = os.read(master_fd, 64)
        except OSError:
            return
        if not data:
            return
        if b'\x10\x04' in data:
            try:
                os.write(master_fd, b'\x12')
            except OSError:
                return


def test_detect_serial_finds_baud():
    master, slave = pty.openpty()
    stop = threading.Event()
    t = threading.Thread(target=_responder, args=(master, stop), daemon=True)
    t.start()
    try:
        assert prn.detect_serial(os.ttyname(slave)) == 9600
    finally:
        stop.set()
        t.join(timeout=5)
        os.close(master)
        os.close(slave)


def test_detect_serial_silence_returns_none():
    master, slave = pty.openpty()  # held open, never answers
    try:
        assert prn.detect_serial(os.ttyname(slave),
                                 bauds=(9600,), timeout=0.2) is None
    finally:
        os.close(master)
        os.close(slave)


def _login(client, db_name):
    r = client.post(f'/api/auth/login?db={db_name}', json={'pin': '1234'})
    assert r.status_code == 200


def _set_path(client, db_name, path):
    r = client.post(f'/api/settings/?db={db_name}', json={'printer_path': path})
    assert r.status_code == 200


def test_print_endpoint_writes_bytes(client, clean_db, tmp_path):
    """End to end: setting → endpoint → ESC/POS bytes in fake device."""
    db_name = clean_db
    _login(client, db_name)
    fake = tmp_path / 'lp0'
    fake.write_bytes(b'')
    _set_path(client, db_name, str(fake))

    r = client.post(f'/api/printer/print?db={db_name}',
                    json={'text': 'TOTALE Caffè €5'})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['printed'] is True

    data = fake.read_bytes()
    assert data.startswith(b'\x1b@')
    assert b'TOTALE Caffe EUR5' in data
    assert data.endswith(b'\x1dV\x01')


def test_test_endpoint_uses_ticket(client, clean_db, tmp_path):
    db_name = clean_db
    _login(client, db_name)
    fake = tmp_path / 'lp0'
    fake.write_bytes(b'')
    _set_path(client, db_name, str(fake))

    r = client.post(f'/api/printer/test?db={db_name}')
    assert r.status_code == 200, r.get_json()
    assert b'prova stampa' in fake.read_bytes()


def test_print_requires_login(client, clean_db):
    r = client.post(f'/api/printer/print?db={clean_db}', json={'text': 'x'})
    assert r.status_code == 403


def test_print_unconfigured(client, clean_db):
    db_name = clean_db
    _login(client, db_name)
    r = client.post(f'/api/printer/print?db={db_name}', json={'text': 'x'})
    assert r.status_code == 400


def test_detect_endpoint_finds_printer(client, clean_db):
    """Full stack: endpoint → serial probe → baud (fake printer on pty)."""
    import threading
    db_name = clean_db
    _login(client, db_name)
    master, slave = pty.openpty()
    stop = threading.Event()
    t = threading.Thread(target=_responder, args=(master, stop), daemon=True)
    t.start()
    try:
        r = client.post(f'/api/printer/detect?db={db_name}',
                        json={'path': os.ttyname(slave)})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['baud'] == 9600
    finally:
        stop.set()
        t.join(timeout=5)
        os.close(master)
        os.close(slave)


def test_detect_endpoint_silence(client, clean_db):
    db_name = clean_db
    _login(client, db_name)
    r = client.post(f'/api/printer/detect?db={db_name}',
                    json={'path': '/dev/ttyUSB99'})
    assert r.status_code in (400, 500), r.get_json()
