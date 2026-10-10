"""
Thermal printing without hardware: the device is a temp file.

Bytes asserted: ESC @ init, sanitized text, alignment, partial cut.
"""
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
