"""Login identity: the operator is chosen, never guessed from the PIN.

Why this exists: `authenticate_operator` scanned every active operator and
returned the FIRST whose PIN matched. Two operators sharing a 4-digit PIN
(the normal case when admins pick them by hand) attributed the sale — and
the audit trail — to whoever sorted first. The UI now sends the operator
id; the PIN-only path is still served for API clients but refuses to
guess.
"""
import os

import pytest

from app.database.connection import PartyDatabase
from app.services.auth_service import create_operator


def _login(client, db, pin, operator_id=None, admin=False):
    body = {'pin': pin}
    if operator_id is not None:
        body['operator_id'] = operator_id
    path = '/api/auth/login/admin' if admin else '/api/auth/login'
    return client.post(f'{path}?db={db}', json=body)


def _operator_id(db, name):
    with PartyDatabase(db) as conn:
        return conn.execute(
            "SELECT id FROM operators WHERE name = ?", (name,)).fetchone()[0]


def _add_operator(db, name, pin, role='operator'):
    create_operator(db, name, pin, role)
    return _operator_id(db, name)


# ============================================================
# Roster (the login picker's data)
# ============================================================

def test_roster_lists_active_operators_without_secrets(clean_db, client):
    _add_operator(clean_db, 'Mario', '1111')
    _add_operator(clean_db, 'Anna', '2222')
    with PartyDatabase(clean_db) as conn:  # deactivate one
        conn.execute("UPDATE operators SET is_active = 0 WHERE name = 'Anna'")
        conn.commit()

    r = client.get(f'/api/auth/operators/roster?db={clean_db}')
    assert r.status_code == 200
    roster = r.get_json()
    names = [op['name'] for op in roster]
    assert 'Mario' in names and 'Anna' not in names
    assert set(roster[0]) == {'id', 'name', 'role'}  # never pin_hash


def test_roster_of_unknown_party_is_a_404(clean_db, client):
    r = client.get('/api/auth/operators/roster?db=no-such-party')
    assert r.status_code == 404


# ============================================================
# Login by operator id
# ============================================================

def test_login_by_id_verifies_only_that_operator(clean_db, client):
    mario = _add_operator(clean_db, 'Mario', '1111')
    r = _login(client, clean_db, '1111', operator_id=mario)
    assert r.status_code == 200
    assert r.get_json()['operator']['name'] == 'Mario'

    # Mario's PIN must NOT log in Anna, even though it is a valid PIN in
    # the party (that is what the old scan did).
    anna = _add_operator(clean_db, 'Anna', '1111')
    client.post(f'/api/auth/logout?db={clean_db}')
    assert _login(client, clean_db, '1111', operator_id=anna).status_code == 200
    assert _login(client, clean_db, '9999', operator_id=anna).status_code == 403


def test_inactive_operator_cannot_log_in_by_id(clean_db, client):
    mario = _add_operator(clean_db, 'Mario', '1111')
    with PartyDatabase(clean_db) as conn:
        conn.execute("UPDATE operators SET is_active = 0 WHERE id = ?", (mario,))
        conn.commit()
    r = _login(client, clean_db, '1111', operator_id=mario)
    assert r.status_code == 403
    assert r.get_json()['code'] == 'invalid_pin'


def test_unknown_operator_id_is_refused(clean_db, client):
    assert _login(client, clean_db, '1234', operator_id=9999).status_code == 403


def test_bad_operator_id_type_is_a_client_error(clean_db, client):
    assert _login(client, clean_db, '1234', operator_id='abc').status_code == 400


# ============================================================
# PIN-only fallback: never guess
# ============================================================

def test_shared_pin_is_ambiguous_on_the_pin_only_path(clean_db, client):
    mario = _add_operator(clean_db, 'Mario', '1111')
    anna = _add_operator(clean_db, 'Anna', '1111')

    r = _login(client, clean_db, '1111')  # no operator_id
    assert r.status_code == 400
    assert r.get_json()['code'] == 'ambiguous_pin'
    assert 'more than one operator' in r.get_json()['error']

    # Both can still log in by choosing their name.
    assert _login(client, clean_db, '1111', operator_id=mario).status_code == 200
    client.post(f'/api/auth/logout?db={clean_db}')
    assert _login(client, clean_db, '1111', operator_id=anna).status_code == 200


def test_admin_login_accepts_the_operator_id_too(clean_db, client):
    boss = _add_operator(clean_db, 'Boss', '7777', role='admin')
    r = _login(client, clean_db, '7777', operator_id=boss, admin=True)
    assert r.status_code == 200
    assert r.get_json()['operator']['role'] == 'admin'
    # A non-admin id is still refused by the admin route.
    op = _add_operator(clean_db, 'Tizio', '8888')
    assert _login(client, clean_db, '8888', operator_id=op, admin=True).status_code == 403


# ============================================================
# Operator names
# ============================================================

@pytest.mark.parametrize('name', ['Mario', 'mario', 'MARIO'])
def test_operator_names_are_unique_case_insensitively(clean_db, client, name):
    """Two 'Mario' would make the picker and the audit trail ambiguous."""
    create_operator(clean_db, 'Mario', '1111')
    with pytest.raises(ValueError):
        create_operator(clean_db, name, '2222')


def test_duplicate_name_is_a_400_on_the_api(clean_db, client):
    assert client.post(f'/api/auth/login/admin?db={clean_db}',
                       json={'pin': '0000'}).status_code == 200
    r = client.post(f'/api/auth/operators?db={clean_db}',
                    json={'name': 'Mario', 'pin': '1111'})
    assert r.status_code == 201
    r = client.post(f'/api/auth/operators?db={clean_db}',
                    json={'name': 'mario', 'pin': '2222'})
    assert r.status_code == 400
    assert 'already exists' in r.get_json()['error']
