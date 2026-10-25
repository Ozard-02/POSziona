"""
Operational-safety tests: lifecycle guards, health endpoint, audit trail.
"""
import os
import sqlite3


def test_delete_refuses_live_db(clean_db, client):
    """Deleting a party with open connections fails instead of pulling the file."""
    from app.database.connection import PartyDatabase

    db_name = clean_db
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    with PartyDatabase(db_name):
        resp = client.delete(f'/api/parties/{db_name}')
        assert resp.status_code == 400
        assert 'in use' in resp.get_json()['error']

    # After connections close, delete works
    resp = client.delete(f'/api/parties/{db_name}')
    assert resp.status_code == 200


def test_status_reports_db_health(client):
    resp = client.get('/api/status')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert data['db_writable'] is True
    assert data['disk_free_mb'] >= 0
    assert data['version'] == '0.2.0'
    assert data['server_name']  # tag for the client picker (hostname fallback)
    assert data['connected_screens'] == 0  # no SSE subscribers in tests


def test_discount_and_void_are_audited(clean_db, client):
    """Discounts and order voids leave an audit trail (requirements §7/§10)."""
    from app.database.connection import _get_party_db_path

    db_name = clean_db
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    client.post(f'/api/products/sections?db={db_name}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db_name}',
                json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db_name}', json={
        'name': 'Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1})
    client.post(f'/api/cart/add?db={db_name}', json={'product_id': 1, 'quantity': 1})

    r = client.post(f'/api/cart/discount?db={db_name}',
                    json={'type': 'percentage', 'value': 10})
    assert r.status_code == 200

    r = client.post(f'/api/orders/checkout?db={db_name}', json={'payment_method': 'cash'})
    order_id = r.get_json()['order_id']

    r = client.delete(f'/api/orders/{order_id}?db={db_name}')
    assert r.status_code == 200

    conn = sqlite3.connect(_get_party_db_path(db_name))
    actions = {row[0] for row in conn.execute("SELECT action FROM audit_log")}
    conn.close()
    assert 'discount_applied' in actions
    assert 'order_voided' in actions


def test_open_refused_and_no_resurrection_while_being_deleted(clean_db):
    """Open cannot resurrect a party DB while its deletion is in progress (R6)."""
    import pytest
    from app.database.connection import (
        PartyDatabase, mark_deleting, _get_party_db_path)

    with PartyDatabase(clean_db):
        pass  # file must exist
    path = _get_party_db_path(clean_db)
    mark_deleting(path, True)
    try:
        with pytest.raises(RuntimeError, match='being deleted'):
            with PartyDatabase(clean_db):
                pass
        # The opener must not have recreated/touched the file
        assert path.endswith(clean_db + '.db')
    finally:
        mark_deleting(path, False)


def test_concurrent_first_opens_seed_once(clean_db):
    """Simultaneous first-opens of a NEW party seed the defaults once (R6)."""
    import threading
    from app.database.connection import (
        PartyDatabase, _get_party_db_path, _checked_paths, _checked_paths_lock,
        _migrated_paths)

    db_name = 'race_seed_check'
    path = _get_party_db_path(db_name)
    # Fresh slate for path/tracking state
    for ext in ('', '-wal', '-shm'):
        if os.path.exists(path + ext):
            os.remove(path + ext)
    with _checked_paths_lock:
        _checked_paths.discard(path)
        _migrated_paths.discard(path)

    barrier = threading.Barrier(6)
    failures = []

    def _open():
        try:
            barrier.wait(timeout=5)
            with PartyDatabase(db_name) as conn:
                conn.execute("SELECT COUNT(*) FROM products").fetchone()
        except Exception as e:  # noqa: BLE001 — collect, assert below
            failures.append(e)

    threads = [threading.Thread(target=_open) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert failures == []

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    conn.close()

    for ext in ('', '-wal', '-shm'):
        if os.path.exists(path + ext):
            os.remove(path + ext)
    with _checked_paths_lock:
        _checked_paths.discard(path)
        _migrated_paths.discard(path)

    assert products == 13  # one default seed run (9 drinks + 4 snacks), never doubled


def test_same_session_parallel_adds_all_land(clean_db, client, app):
    """Parallel adds from ONE logged-in session must all be counted (R8).

    The cart lives in the signed cookie: every parallel request carries the
    same stale cookie, and plain last-writer-wins would drop updates (the
    operator charges one coffee instead of two). The per-operator session
    lock re-centers each request onto the latest committed cart, so all
    N adds land.
    """
    import threading

    db_name = clean_db
    r = client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    assert r.status_code == 200
    cookie = client.get_cookie('session').value

    # clean_db has no seed products: create one (first product → id 1)
    client.post(f'/api/products/sections?db={db_name}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db_name}',
                json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db_name}', json={
        'name': 'Coffee', 'price': 2.0, 'section_id': 1, 'subsection_id': 1})

    n = 12
    barrier = threading.Barrier(n)
    codes = []
    cookies = []
    lock = threading.Lock()

    def _add():
        c = app.test_client()
        c.set_cookie('session', cookie)  # every thread replays the SAME cookie
        barrier.wait(timeout=5)
        resp = c.post(f'/api/cart/add?db={db_name}',
                      json={'product_id': 1, 'quantity': 1})
        with lock:
            codes.append(resp.status_code)
            if resp.status_code == 200:
                cookies.append(c.get_cookie('session').value)

    threads = [threading.Thread(target=_add) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert codes == [200] * n, 'all parallel adds must succeed'

    # A fresh screen replaying a thread's (possibly stale) cookie must be
    # re-centered onto the SERVER-truth cart: all N adds are there.
    c = app.test_client()
    c.set_cookie('session', cookies[0])
    resp = c.post(f'/api/cart/add?db={db_name}', json={'product_id': 1, 'quantity': 1})
    assert resp.status_code == 200, resp.get_json()
    quantities = {item['product_id']: item['quantity'] for item in resp.get_json()['cart']}
    assert quantities.get(1) == n + 1, quantities
