"""Stock integrity, section reorder, inactive-product editing, receipt settings."""
import pytest


def _seed_stocked_product(client, db, stock=5):
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}',
                json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50,
        'section_id': 1, 'subsection_id': 1, 'stock': stock})


def _stock(client, db):
    return client.get(f'/api/products/products/1?db={db}').get_json()['stock_count']


def test_checkout_decrements_stock_once(clean_db, client):
    """One checkout decrements exactly the sold quantity, in a single order."""
    db = clean_db
    _seed_stocked_product(client, db)
    assert _stock(client, db) == 5

    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 2})
    resp = client.post(f'/api/orders/checkout?db={db}',
                       json={'payment_method': 'cash'})
    assert resp.status_code == 201

    assert _stock(client, db) == 3
    order = client.get(f"/api/orders/{resp.get_json()['order_id']}?db={db}").get_json()
    assert len(order['items']) == 1
    assert order['items'][0]['quantity'] == 2


def test_stock_never_negative_on_checkout(clean_db, client):
    """Stale carts (qty > stock) clamp at 0, never below."""
    db = clean_db
    _seed_stocked_product(client, db, stock=1)

    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 3})
    resp = client.post(f'/api/orders/checkout?db={db}',
                       json={'payment_method': 'cash'})
    assert resp.status_code == 201
    assert _stock(client, db) == 0


def test_depleted_product_flagged_out_of_stock(clean_db, client):
    """Stock 0 is visible in the POS list so the grid can disable the item."""
    db = clean_db
    _seed_stocked_product(client, db, stock=1)
    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 1})
    client.post(f'/api/orders/checkout?db={db}', json={'payment_method': 'cash'})

    products = client.get(f'/api/products/1/products?db={db}').get_json()
    coffee = [p for p in products if p['name'] == 'Small Coffee'][0]
    assert coffee['stock_count'] == 0


def test_section_reorder_persists(clean_db, client):
    """Reordered section ids are saved and reflected on next fetch."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    for name in ('A', 'B', 'C'):
        client.post(f'/api/products/sections?db={db}', json={'name': name})

    resp = client.post(f'/api/products/sections/reorder?db={db}',
                       json={'section_ids': [3, 1, 2]})
    assert resp.status_code == 200

    names = [s['name'] for s in client.get(f'/api/products/?db={db}').get_json()]
    assert names == ['C', 'A', 'B']


def test_section_reorder_rejects_empty(clean_db, client):
    """Empty section_ids list must be rejected."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    resp = client.post(f'/api/products/sections/reorder?db={db}',
                       json={'section_ids': []})
    assert resp.status_code == 400


def test_inactive_products_visible_in_admin_list(clean_db, client):
    """Admin list includes inactive products so availability stays editable."""
    db = clean_db
    _seed_stocked_product(client, db)

    assert client.put(f'/api/products/products/1?db={db}',
                      json={'is_active': 0}).status_code == 200
    products = client.get(f'/api/products/all?db={db}').get_json()
    assert len(products) == 1
    assert products[0]['is_active'] == 0


@pytest.mark.parametrize('field,value', [('is_active', 0), ('stock', 10)])
def test_edit_product_fields_via_put(clean_db, client, field, value):
    """Availability and stock are editable via PUT."""
    db = clean_db
    _seed_stocked_product(client, db)

    assert client.put(f'/api/products/products/1?db={db}',
                      json={field: value}).status_code == 200
    product = client.get(f'/api/products/products/1?db={db}').get_json()
    assert product['stock_count' if field == 'stock' else field] == value


def test_split_receipt_settings(clean_db, client):
    """Receipt toggles default to '0' and round-trip through settings."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    settings = client.get(f'/api/settings/?db={db}').get_json()
    assert settings['split_receipts'] == '0'
    assert settings['print_recovery_receipt'] == '0'

    assert client.post(f'/api/settings/?db={db}', json={
        'split_receipts': '1', 'print_recovery_receipt': '1'}).status_code == 200
    settings = client.get(f'/api/settings/?db={db}').get_json()
    assert settings['split_receipts'] == '1'
    assert settings['print_recovery_receipt'] == '1'
