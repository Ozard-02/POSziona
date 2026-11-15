"""API exposure: no implicit party creation, narrow CORS, body limits.

Every one of these is reachable from any device on the party Wi-Fi, so
they are pinned here rather than left to review.
"""
import os
import uuid

from app import create_app
from app.utils.config import PARTY_DB_DIR


def test_unknown_party_is_a_404_and_creates_nothing(client):
    """`?db=` is client-supplied: an unknown name must not mint a seeded DB
    (one file + two PBKDF2 hashes per request is a free disk/CPU fill)."""
    ghost = 'ghost-' + uuid.uuid4().hex[:8]
    r = client.get(f'/api/products/?db={ghost}')
    assert r.status_code == 404
    assert 'does not exist' in r.get_json()['error']
    assert not os.path.exists(os.path.join(PARTY_DB_DIR, ghost + '.db'))


def test_fresh_install_can_still_log_in_to_default(tmp_path, monkeypatch):
    """A brand-new install has no party at all: the `default` fallback must
    still be created on demand, or nobody can log in the first time."""
    from app.database import connection as conn_mod
    monkeypatch.setattr(conn_mod, 'PARTY_DB_DIR', str(tmp_path))

    app = create_app()
    c = app.test_client()
    r = c.post('/api/auth/login?db=default', json={'pin': '1234'})
    assert r.status_code == 200, r.get_json()
    assert (tmp_path / 'default.db').exists()


def test_status_is_the_only_cross_origin_endpoint(client):
    """The login page probes /api/status on another server; nothing else in
    the API should answer a foreign Origin."""
    r = client.get('/api/status', headers={'Origin': 'https://evil.example'})
    assert r.headers.get('Access-Control-Allow-Origin') == '*'
    r = client.get('/api/products/', headers={'Origin': 'https://evil.example'})
    assert 'Access-Control-Allow-Origin' not in r.headers
    r = client.options('/api/orders/checkout',
                       headers={'Origin': 'https://evil.example',
                                'Access-Control-Request-Method': 'POST'})
    assert 'Access-Control-Allow-Origin' not in r.headers


def test_oversized_body_is_a_json_413(client):
    body = b'{"rows": [' + b'{"x": 1},' * 1_100_000 + b'{}]}'  # > 8 MB
    r = client.post('/api/cart/add?db=default', data=body,
                    content_type='application/json')
    assert r.status_code == 413
    assert r.is_json
    assert 'too large' in r.get_json()['error']


def test_non_json_post_gets_json_not_an_html_page(client):
    r = client.post('/api/cart/add?db=default', data='product_id=1')
    assert r.status_code == 415
    assert r.is_json


def test_party_configuration_is_not_public(clean_db, client):
    """Printer path, receipt text and the snapshot list belong to the
    admin panel; the login page never asks for them."""
    assert client.get(f'/api/parties/{clean_db}/settings').status_code == 403
    assert client.get('/api/parties/backups').status_code == 403
    assert client.get(f'/api/settings/?db={clean_db}').status_code == 403


def test_settings_are_available_to_a_logged_in_screen(clean_db, client):
    assert client.post(f'/api/auth/login?db={clean_db}',
                       json={'pin': '1234'}).status_code == 200
    r = client.get(f'/api/settings/?db={clean_db}')
    assert r.status_code == 200
    assert 'currency' in r.get_json()
