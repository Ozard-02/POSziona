"""
Two-tier settings: device keys are invariant across parties.

- Writing a device key (printer, language, currency...) on party A is
  visible on party B.
- Party keys (receipt header, snapshot cadence...) stay isolated.
- Writing a device key deletes stale party-level rows (migrate-on-write)
  so old per-party values can never shadow the global one.
"""
import pytest

from app.services.settings_service import (
    get_effective_settings, update_setting,
)


@pytest.fixture
def two_parties(client):
    login = client.post('/api/auth/login/admin?db=default', json={'pin': '0000'})
    assert login.status_code == 200, 'two_parties fixture needs admin'
    r = client.post('/api/parties/templates', json={'name': 'scope_tpl'})
    tid = r.get_json()['id']
    for name in ('scope_a', 'scope_b'):
        r = client.post('/api/parties/', json={'name': name, 'template_id': tid})
        assert r.status_code == 201, r.get_json()
    yield ('scope_a', 'scope_b')
    client.delete('/api/parties/scope_a')
    client.delete('/api/parties/scope_b')
    client.delete(f'/api/parties/templates/{tid}')


def test_device_setting_visible_everywhere(client, clean_db, two_parties):
    a, b = two_parties
    update_setting(a, 'printer_path', '/dev/ttyUSB9')
    update_setting(a, 'language', 'it')
    assert get_effective_settings(b)['printer_path'] == '/dev/ttyUSB9'
    assert get_effective_settings(b)['language'] == 'it'
    assert get_effective_settings(a)['printer_path'] == '/dev/ttyUSB9'


def test_party_setting_stays_isolated(client, clean_db, two_parties):
    a, b = two_parties
    update_setting(a, 'receipt_header', 'Festa A')
    assert get_effective_settings(a)['receipt_header'] == 'Festa A'
    assert get_effective_settings(b)['receipt_header'] == ''


def test_migrate_on_write_removes_party_shadow(client, clean_db, two_parties):
    """Old per-party row for a device key must not survive the write."""
    from app.services.party_service import get_party_settings
    a, b = two_parties
    # Simulate a pre-tier value stored per-party (as v0.1.x did).
    from app.services.party_service import update_party_setting
    update_party_setting(a, 'printer_baud', '19200')

    update_setting(a, 'printer_baud', '9600')  # device-level write

    assert 'printer_baud' not in get_party_settings(a)
    assert get_effective_settings(a)['printer_baud'] == '9600'
    assert get_effective_settings(b)['printer_baud'] == '9600'


def test_device_cache_reads_and_ttl(monkeypatch, clean_db):
    """Device settings: own writes visible immediately, TTL re-reads externally."""
    import sqlite3
    import time
    from app.services import settings_service as ss
    from app.utils.config import TEMPLATES_DB

    ss.update_device_setting('server_name', 'C1')
    assert ss.get_device_settings()['server_name'] == 'C1'

    # External write (raw sqlite): still hidden inside the TTL window
    conn = sqlite3.connect(TEMPLATES_DB)
    conn.execute(
        "INSERT OR REPLACE INTO global_settings (key, value) "
        "VALUES ('server_name', 'C2')")
    conn.commit()
    conn.close()
    assert ss.get_device_settings()['server_name'] == 'C1'

    # TTL elapsed → re-read surfaces the external value
    monkeypatch.setattr(ss, 'DEVICE_CACHE_TTL', 0.0)
    time.sleep(0.002)
    assert ss.get_device_settings()['server_name'] == 'C2'

    # Teardown: drop the row and drop the cache
    conn = sqlite3.connect(TEMPLATES_DB)
    conn.execute("DELETE FROM global_settings WHERE key = 'server_name'")
    conn.commit()
    conn.close()
    ss._invalidate_device_cache()
