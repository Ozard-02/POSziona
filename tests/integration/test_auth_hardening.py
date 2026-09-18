"""
Auth hardening tests: salted hashes, legacy migration, rate limiting,
factory-PIN flag, and JSON error responses.
"""
import hashlib

import pytest

from app.utils import rate_limit


@pytest.fixture(autouse=True)
def clean_rate_limiter():
    rate_limit.reset()
    yield
    rate_limit.reset()


def test_new_hash_format_and_login(clean_db, client):
    from app.services.auth_service import hash_pin, needs_upgrade, verify_pin
    h = hash_pin('5678')
    assert h.startswith('pbkdf2$')
    assert not needs_upgrade(h)
    assert verify_pin('5678', h)
    assert not verify_pin('0000', h)


def test_legacy_hash_login_upgrades(clean_db, client):
    """Old unsalted SHA-256 hashes keep working once, then get upgraded."""
    import sqlite3
    from app.database.connection import _get_party_db_path
    from app.services.auth_service import needs_upgrade

    db_name = clean_db
    legacy = hashlib.sha256('9999'.encode()).hexdigest()
    conn = sqlite3.connect(_get_party_db_path(db_name))
    conn.execute(
        "INSERT INTO operators (name, pin_hash, role, is_active) VALUES (?, ?, 'operator', 1)",
        ('legacy-op', legacy),
    )
    conn.commit()
    conn.close()

    r = client.post(f'/api/auth/login?db={db_name}', json={'pin': '9999'})
    assert r.status_code == 200

    conn = sqlite3.connect(_get_party_db_path(db_name))
    stored = conn.execute(
        "SELECT pin_hash FROM operators WHERE name = 'legacy-op'").fetchone()[0]
    conn.close()
    assert not needs_upgrade(stored)
    assert stored != legacy


def test_login_rate_limited(clean_db, client):
    db_name = clean_db
    for _ in range(10):
        r = client.post(f'/api/auth/login?db={db_name}', json={'pin': '9999'})
        assert r.status_code == 403  # wrong PIN
    r = client.post(f'/api/auth/login?db={db_name}', json={'pin': '9999'})
    assert r.status_code == 429
    assert 'error' in r.get_json()


def test_factory_pin_flag(clean_db, client):
    db_name = clean_db
    r = client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    assert r.status_code == 200
    assert r.get_json()['must_change_pin'] is True

    # After changing to a non-factory PIN the flag clears
    client.post(f'/api/auth/operators?db={db_name}',
                json={'name': 'op2', 'pin': '5678', 'role': 'operator'})
    client.post(f'/api/auth/logout?db={db_name}')
    rate_limit.reset()
    r = client.post(f'/api/auth/login?db={db_name}', json={'pin': '5678'})
    assert r.status_code == 200
    assert r.get_json()['must_change_pin'] is False


def test_json_error_responses(client):
    # Malformed JSON body → JSON 400, not an HTML page
    r = client.post('/api/auth/login?db=default', data='{broken',
                    content_type='application/json')
    assert r.status_code == 400
    assert 'error' in r.get_json()

    # Unknown route → JSON 404
    r = client.get('/api/no-such-thing')
    assert r.status_code == 404
    assert 'error' in r.get_json()

    # Garbage limit → JSON 400
    r = client.get('/api/orders/recent?db=default&limit=abc')
    assert r.status_code == 400
    assert 'error' in r.get_json()
