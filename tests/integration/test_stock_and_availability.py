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


def test_stale_cart_over_stock_is_refused(clean_db, client):
    """A stale cart above available stock refuses the sale, stock untouched.

    (Replaces the old clamp-at-0 contract: silently recording a sale of
    goods that are not on the shelf was the oversell bug — R13.)
    """
    db = clean_db
    _seed_stocked_product(client, db, stock=1)

    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 3})
    resp = client.post(f'/api/orders/checkout?db={db}',
                       json={'payment_method': 'cash'})
    assert resp.status_code == 400
    assert 'stock' in resp.get_json()['error'].lower()
    assert _stock(client, db) == 1
    summary = client.get(f'/api/orders/report/summary?db={db}').get_json()
    assert summary['total_orders'] == 0


def test_last_unit_concurrent_checkouts_sell_once(clean_db, client, app):
    """Two parallel checkouts of the last unit: exactly one sale (R13)."""
    import threading

    db = clean_db
    _seed_stocked_product(client, db, stock=1)

    # Two separate screens with DIFFERENT operators (same operator means
    # the same shared cart by design — the session locks merge it)
    c1, c2 = app.test_client(), app.test_client()
    assert c1.post(f'/api/auth/login/admin?db={db}',
                   json={'pin': '0000'}).status_code == 200
    assert c2.post(f'/api/auth/login?db={db}',
                   json={'pin': '1234'}).status_code == 200
    for c in (c1, c2):
        resp = c.post(f'/api/cart/add?db={db}',
                      json={'product_id': 1, 'quantity': 1})
        assert resp.status_code == 200

    barrier = threading.Barrier(2)
    codes = []
    lock = threading.Lock()

    def _checkout(c):
        barrier.wait(timeout=5)
        resp = c.post(f'/api/orders/checkout?db={db}',
                      json={'payment_method': 'cash'})
        with lock:
            codes.append(resp.status_code)

    threads = [threading.Thread(target=_checkout, args=(c,)) for c in (c1, c2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert sorted(codes) == [201, 400], codes
    assert _stock(client, db) == 0
    summary = client.get(f'/api/orders/report/summary?db={db}').get_json()
    assert summary['total_orders'] == 1


def test_void_order_restores_stock_summed_per_product(clean_db, client):
    """Same product on two order lines: the void restores the FULL amount.

    Legacy/API-crafted orders can hold the product twice; a scalar
    subquery used to restore only the first line (R19).
    """
    from app.database.connection import PartyDatabase
    from app.services.order_service import delete_order_by_id

    db = clean_db
    _seed_stocked_product(client, db, stock=10)  # product id 1

    with PartyDatabase(db) as conn:
        conn.execute(
            "INSERT INTO orders (subtotal, total, payment_method, operator_id) "
            "VALUES (7.5, 7.5, 'cash', 1)")
        oid = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
            "VALUES (?, 1, 2, 2.5)", (oid,))
        conn.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
            "VALUES (?, 1, 1, 2.5)", (oid,))
        # Stock after that 3-unit sale
        conn.execute("UPDATE products SET stock_count = stock_count - 3 "
                     "WHERE id = 1")
        conn.commit()

    assert _stock(client, db) == 7
    assert delete_order_by_id(db, oid) is True
    assert _stock(client, db) == 10, 'restored 2+1, not just the first line'


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
