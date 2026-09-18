"""
Operational-safety tests: lifecycle guards, health endpoint, audit trail.
"""
import sqlite3


def test_delete_refuses_live_db(clean_db, client):
    """Deleting a party with open connections fails instead of pulling the file."""
    from app.database.connection import PartyDatabase

    db_name = clean_db
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
