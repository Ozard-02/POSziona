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


def test_legacy_upgrade_does_not_clobber_concurrent_reset(clean_db, monkeypatch):
    """An admin PIN reset landing in the upgrade window must win (R10)."""
    import sqlite3
    import app.services.auth_service as auth
    from app.database.connection import _get_party_db_path

    db_name = clean_db
    legacy = hashlib.sha256('9999'.encode()).hexdigest()
    path = _get_party_db_path(db_name)
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO operators (name, pin_hash, role, is_active) "
        "VALUES (?, ?, 'operator', 1)", ('legacy-op', legacy))
    conn.commit()
    conn.close()

    new_hash = auth.hash_pin('4321')
    real_verify = auth.verify_pin

    def verify_with_concurrent_reset(pin, stored_hash):
        ok = real_verify(pin, stored_hash)
        if ok:
            # The admin reset commits from ANOTHER connection exactly in
            # the vulnerable window (after verify, before the upgrade).
            c = sqlite3.connect(path)
            c.execute("UPDATE operators SET pin_hash = ? WHERE name = 'legacy-op'",
                      (new_hash,))
            c.commit()
            c.close()
        return ok

    monkeypatch.setattr(auth, 'verify_pin', verify_with_concurrent_reset)
    result = auth.authenticate_operator(db_name, '9999')
    assert result is not None  # the typed PIN was valid when verified

    conn = sqlite3.connect(path)
    stored = conn.execute(
        "SELECT pin_hash FROM operators WHERE name = 'legacy-op'").fetchone()[0]
    conn.close()
    assert stored == new_hash, 'the concurrent reset must not be overwritten'


def test_login_rate_limited(clean_db, client):
    db_name = clean_db
    for _ in range(10):
        r = client.post(f'/api/auth/login?db={db_name}', json={'pin': '9999'})
        assert r.status_code == 403  # wrong PIN
    r = client.post(f'/api/auth/login?db={db_name}', json={'pin': '9999'})
    assert r.status_code == 429
    assert 'error' in r.get_json()


def test_expired_rate_limit_counters_are_swept():
    """Successful logins never revisit their key: the table must not grow
    forever with every client IP ever seen (R16)."""
    import time as _time

    rate_limit.reset()
    try:
        now = _time.time()
        with rate_limit._lock:
            for i in range(50):
                rate_limit._counters[f'old-{i}'] = [now - 10_000, 5]
            rate_limit._counters['fresh'] = [now, 1]

        original = rate_limit._SWEEP_THRESHOLD
        rate_limit._SWEEP_THRESHOLD = 10  # table already past the valve
        try:
            assert rate_limit.check('new', limit=3, window_seconds=60) is True
        finally:
            rate_limit._SWEEP_THRESHOLD = original

        with rate_limit._lock:
            keys = set(rate_limit._counters)
        assert not any(k.startswith('old-') for k in keys), keys
        assert {'fresh', 'new'} <= keys
    finally:
        rate_limit.reset()


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
