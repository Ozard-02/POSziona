"""
Active-party contract: sales land in the selected party's DB.

The UI (login dropdown, POS/admin switchers) picks the party purely via
?db=<name>. These tests pin the backend side of that contract: login
authenticates against the chosen party's operators, and checkout writes
orders/stock/audit into that party's DB only.
"""

from app.database import templates_db

PARTY = 'sel_party_test'


def _make_party(client):
    # Lifecycle routes are admin-only (R5)
    login = client.post('/api/auth/login/admin?db=default', json={'pin': '0000'})
    assert login.status_code == 200, 'party setup needs admin login'
    r = client.post('/api/parties/templates', json={'name': 'sel_tpl_test'})
    assert r.status_code == 201
    tid = r.get_json()['id']
    r = client.post('/api/parties/', json={'name': PARTY, 'template_id': tid})
    assert r.status_code == 201, r.get_json()
    return tid


def _setup_product(client, stock=10):
    client.post(f'/api/auth/login/admin?db={PARTY}', json={'pin': '0000'})
    client.post(f'/api/products/sections?db={PARTY}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={PARTY}',
                json={'section_id': 1, 'name': 'Coffee'})
    resp = client.post(f'/api/products/products?db={PARTY}', json={
        'name': 'Coffee', 'price': 2.50,
        'section_id': 1, 'subsection_id': 1, 'stock': stock,
    })
    assert resp.status_code == 201
    return resp.get_json()['id']


def _cleanup(tid):
    # Teardown via services: works regardless of session cookies, and
    # party deletion needs zero live connections (requests are done).
    from app.services.party_service import delete_party
    try:
        delete_party(PARTY)
    except FileNotFoundError:
        pass
    templates_db.delete_template(tid)


def test_login_uses_selected_party_operators(client, clean_db):
    """Operator PIN authenticates against the chosen party's DB."""
    tid = _make_party(client)
    try:
        r = client.post(f'/api/auth/login?db={PARTY}', json={'pin': '1234'})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['operator']['role'] == 'operator'
    finally:
        _cleanup(tid)


def test_sale_lands_in_selected_party_only(client, clean_db):
    """Checkout with ?db=P writes the order into P, nowhere else."""
    tid = _make_party(client)
    try:
        pid = _setup_product(client)
        r = client.post(f'/api/cart/add?db={PARTY}',
                        json={'product_id': pid, 'quantity': 2})
        assert r.status_code == 200
        r = client.post(f'/api/orders/checkout?db={PARTY}',
                        json={'payment_method': 'cash', 'tendered': 5.0,
                              'idempotency_key': 'sel-party-key-1'})
        assert r.status_code == 201, r.get_json()

        mine = client.get(f'/api/orders/report/summary?db={PARTY}').get_json()
        assert mine['total_orders'] == 1

        others = client.get('/api/orders/report/summary?db=default').get_json()
        assert others['total_orders'] == 0
    finally:
        _cleanup(tid)
