"""Login hardening: throttle ordering and the party a session belongs to.

These are the field-facing guarantees of the login:
- the throttle must stop GUESSING, not just decorate the reply;
- a session is authenticated against ONE party DB (operator ids and
  PINs are per-party, `?db=` is client-supplied);
- sales figures (the party recap) are admin-only;
- PIN hashes never leave the server.
"""
import os

import pytest

from app.database.connection import PARTY_DB_DIR
from app.services.party_service import create_empty_party
from app.utils import rate_limit

# db name is derived from the party name (see _sanitize_party_name)



@pytest.fixture
def second_party(clean_db):
    """A second, independent party DB (seeded like a fresh install)."""
    db_name = create_empty_party('bp other party')
    yield db_name
    for ext in ('', '-wal', '-shm'):
        path = os.path.join(PARTY_DB_DIR, db_name + ext)
        if os.path.exists(path):
            os.remove(path)


def _login(client, db, pin):
    return client.post(f'/api/auth/login?db={db}', json={'pin': pin})


def test_throttle_refuses_even_a_correct_pin(clean_db, client):
    """The limiter runs BEFORE verification: once the window is spent, a
    correct PIN must not be served either — otherwise every guess still
    gets a full hash comparison and the PIN is brute-forceable at speed."""
    rate_limit.reset()
    try:
        for _ in range(10):
            assert _login(client, clean_db, '9999').status_code == 403
        r = _login(client, clean_db, '1234')  # the real operator PIN
        assert r.status_code == 429
        assert 'error' in r.get_json()
    finally:
        rate_limit.reset()


def test_recap_csv_is_admin_only(clean_db, client):
    """Revenue, per-product totals and operator/guest names: same rule as
    every other sales report (admin), not "anyone on the LAN"."""
    assert client.get(f'/api/parties/{clean_db}/recap').status_code == 403
    _login(client, clean_db, '1234')  # operator
    assert client.get(f'/api/parties/{clean_db}/recap').status_code == 403
    client.post('/api/auth/logout?db=' + clean_db)
    _login(client, clean_db, '0000')  # admin
    r = client.get(f'/api/parties/{clean_db}/recap')
    assert r.status_code == 200
    assert b'Sales Summary' in r.data


def test_session_is_bound_to_the_party_it_logged_in(clean_db, second_party, client):
    """A login on party A must not authorise party B: the sale would be
    attributed to whoever shares that operator id there (or die on the FK)."""
    assert _login(client, clean_db, '1234').status_code == 200
    r = client.post(f'/api/cart/add?db={second_party}', json={'product_id': 1})
    assert r.status_code == 403
    assert r.get_json()['code'] == 'party_mismatch'
    r = client.post(f'/api/orders/checkout?db={second_party}', json={'payment_method': 'cash'})
    assert r.status_code == 403
    assert r.get_json()['code'] == 'party_mismatch'


def test_logging_in_to_another_party_switches_the_session(clean_db, second_party, client):
    """Switching party is a new login, and it must then work end to end."""
    assert _login(client, clean_db, '1234').status_code == 200
    assert _login(client, second_party, '1234').status_code == 200
    assert client.post(f'/api/cart/add?db={second_party}',
                       json={'product_id': 1}).status_code == 200
    r = client.post(f'/api/orders/checkout?db={second_party}',
                    json={'payment_method': 'cash'})
    assert r.status_code == 201


def test_requests_without_a_party_still_work(clean_db, client):
    """The POS party picker and the login page call these with no ?db=:
    they must not be caught by the binding check."""
    _login(client, clean_db, '1234')
    assert client.get('/api/parties/').status_code == 200
    assert client.get('/api/status').status_code == 200
    assert client.get('/api/auth/status').get_json()['logged_in'] is True


def test_operator_list_never_returns_pin_hashes(clean_db, client):
    _login(client, clean_db, '0000')
    r = client.get(f'/api/auth/operators?db={clean_db}')
    assert r.status_code == 200
    operators = r.get_json()
    assert operators
    assert all('pin_hash' not in op for op in operators)
