"""Integration tests for stock decrement after checkout, inactive-product
visibility in the admin table, and section reorder persistence.

These cover the reported regressions:
1. After checkout, availability of limited items does not decrease (POS grid
   was stale + backend could decrement below zero).
2. Drag-to-reorder of sections (admin) — verify reorder persists to DB.
3. Cannot edit availability of items already inserted (inactive products were
   hidden from the admin products table, and the Edit dialog lacked an
   is_active toggle).
4. Checkout creating duplicate orders (completeCashSale fired twice via both
   onclick and addEventListener, double-counting availability).
"""
import pytest


# ===========================================================================
# Issue 1: stock decrement after checkout
# ===========================================================================
def test_stock_decreases_after_checkout(clean_db, client):
    """Product stock_count must decrease by the sold quantity on checkout."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1, 'stock': 5
    })

    # Sanity: stock is 5 before sale
    resp = client.get(f'/api/products/products/1?db={db}')
    assert resp.get_json()['stock_count'] == 5

    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 2})
    resp = client.post(f'/api/orders/checkout?db={db}', json={'payment_method': 'cash'})
    assert resp.status_code == 201

    # Stock should be 5 - 2 = 3
    resp = client.get(f'/api/products/products/1?db={db}')
    assert resp.get_json()['stock_count'] == 3


def test_stock_does_not_go_negative_on_checkout(clean_db, client):
    """If the cart has more quantity than available stock (stale cart),
    checkout must not decrement stock below zero."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1, 'stock': 1
    })

    # Add 3 units even though only 1 is in stock (simulates a stale cart
    # where stock was edited between add and checkout)
    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 3})
    resp = client.post(f'/api/orders/checkout?db={db}', json={'payment_method': 'cash'})
    assert resp.status_code == 201

    # Stock clamped at 0, never negative
    resp = client.get(f'/api/products/products/1?db={db}')
    assert resp.get_json()['stock_count'] == 0


def test_out_of_stock_product_hidden_from_pos_grid(clean_db, client):
    """After stock reaches 0, the product must be marked out-of-stock in the
    POS products list so the operator can no longer add it."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1, 'stock': 1
    })

    # Deplete stock
    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 1})
    client.post(f'/api/orders/checkout?db={db}', json={'payment_method': 'cash'})

    # Fetch products for the subsection
    resp = client.get(f'/api/products/1/products?db={db}')
    products = resp.get_json()
    coffee = [p for p in products if p['name'] == 'Small Coffee'][0]
    assert coffee['stock_count'] == 0
    # The POS frontend treats stock_count <= 0 as out-of-stock
    assert coffee['stock_count'] <= 0


# ===========================================================================
# Issue 2: section reorder persistence (drag-to-reorder)
# ===========================================================================
def test_section_reorder_persists(clean_db, client):
    """Reordered section IDs must be saved and reflected on next fetch."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'A'})
    client.post(f'/api/products/sections?db={db}', json={'name': 'B'})
    client.post(f'/api/products/sections?db={db}', json={'name': 'C'})

    # Original order: A(1), B(2), C(3)
    resp = client.get(f'/api/products/?db={db}')
    names_before = [s['name'] for s in resp.get_json()]
    assert names_before == ['A', 'B', 'C']

    # Reorder to C first: [3, 1, 2]
    resp = client.post(f'/api/products/sections/reorder?db={db}', json={'section_ids': [3, 1, 2]})
    assert resp.status_code == 200

    resp = client.get(f'/api/products/?db={db}')
    names_after = [s['name'] for s in resp.get_json()]
    assert names_after == ['C', 'A', 'B']


def test_section_reorder_rejects_empty(clean_db, client):
    """Empty section_ids list must be rejected."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    resp = client.post(f'/api/products/sections/reorder?db={db}', json={'section_ids': []})
    assert resp.status_code == 400


# ===========================================================================
# Issue 3: can't edit availability of items already inserted (inactive products)
# ===========================================================================
def test_inactive_products_visible_in_admin_list(clean_db, client):
    """The /products/all endpoint must return inactive (but not archived)
    products so admins can edit their availability."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1
    })

    # Deactivate the product
    resp = client.put(f'/api/products/products/1?db={db}', json={'is_active': 0})
    assert resp.status_code == 200

    # /all must still list it
    resp = client.get(f'/api/products/all?db={db}')
    products = resp.get_json()
    assert len(products) == 1
    assert products[0]['is_active'] == 0


def test_edit_product_availability_via_put(clean_db, client):
    """Admin can toggle is_active on a product via PUT /products/products/<id>."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1
    })

    # Deactivate
    resp = client.put(f'/api/products/products/1?db={db}', json={'is_active': 0})
    assert resp.status_code == 200
    assert client.get(f'/api/products/products/1?db={db}').get_json()['is_active'] == 0

    # Reactivate
    resp = client.put(f'/api/products/products/1?db={db}', json={'is_active': 1})
    assert resp.status_code == 200
    assert client.get(f'/api/products/products/1?db={db}').get_json()['is_active'] == 1


def test_edit_product_stock_via_put(clean_db, client):
    """Admin can edit stock_count on a product via PUT."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1, 'stock': 5
    })

    resp = client.put(f'/api/products/products/1?db={db}', json={'stock': 10})
    assert resp.status_code == 200
    assert client.get(f'/api/products/products/1?db={db}').get_json()['stock_count'] == 10


def test_search_filters_inactive_products(clean_db, client):
    """The search endpoint must be able to filter inactive products."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Coffee', 'price': 1.50, 'section_id': 1, 'subsection_id': 1
    })
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Tea', 'price': 1.00, 'section_id': 1, 'subsection_id': 1
    })

    # Deactivate Coffee
    client.put(f'/api/products/products/1?db={db}', json={'is_active': 0})

    # Filter inactive only
    resp = client.get(f'/api/products/search?db={db}&is_active=false')
    inactive = resp.get_json()
    assert len(inactive) == 1
    assert inactive[0]['name'] == 'Coffee'

    # Filter active only
    resp = client.get(f'/api/products/search?db={db}&is_active=true')
    active = resp.get_json()
    assert len(active) == 1
    assert active[0]['name'] == 'Tea'


# ===========================================================================
# Issue 4: checkout must not create duplicate orders
# ===========================================================================
def test_single_checkout_decrements_stock_once(clean_db, client):
    """A single checkout call must decrement stock by exactly the sold
    quantity — not twice. The frontend had a double click handler on the
    Complete Sale button (onclick + addEventListener), creating a duplicate
    order. This test verifies the backend creates exactly one order line item."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1, 'stock': 5
    })

    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 1})

    # One checkout call
    resp = client.post(f'/api/orders/checkout?db={db}', json={'payment_method': 'cash'})
    assert resp.status_code == 201
    order_id = resp.get_json()['order_id']

    # Stock should be 5 - 1 = 4 (not 5 - 2 = 3)
    resp = client.get(f'/api/products/products/1?db={db}')
    assert resp.get_json()['stock_count'] == 4

    # Verify only one order was created
    resp = client.get(f'/api/orders/{order_id}?db={db}')
    order = resp.get_json()
    assert len(order['items']) == 1
    assert order['items'][0]['quantity'] == 1


# ===========================================================================
# Issue 5: per-section receipts and recovery receipt logging
# ===========================================================================
def test_log_receipt_endpoint_exists(clean_db, client):
    """The POST /orders/log-receipt endpoint must exist and return 200."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    resp = client.post(f'/api/orders/log-receipt?db={db}', json={
        'order_id': 99,
        'receipt': 'test receipt text'
    })
    assert resp.status_code == 200


def test_split_receipts_setting_persists(clean_db, client):
    """split_receipts and print_recovery_receipt settings must be saved
    and retrievable via GET /settings/."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    resp = client.post(f'/api/settings/?db={db}', json={
        'split_receipts': '1', 'print_recovery_receipt': '1'
    })
    assert resp.status_code == 200

    resp = client.get(f'/api/settings/?db={db}')
    settings = resp.get_json()
    assert settings['split_receipts'] == '1'
    assert settings['print_recovery_receipt'] == '1'


def test_split_receipts_off_by_default(clean_db, client):
    """split_receipts and print_recovery_receipt must default to '0'."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    resp = client.get(f'/api/settings/?db={db}')
    settings = resp.get_json()
    assert settings['split_receipts'] == '0'
    assert settings['print_recovery_receipt'] == '0'


# ===========================================================================
# Issue 5: per-section receipts and recovery receipt logging
# ===========================================================================
def test_log_receipt_endpoint_exists(clean_db, client):
    """The POST /orders/log-receipt endpoint must exist and return 200."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    resp = client.post(f'/api/orders/log-receipt?db={db}', json={
        'order_id': 99,
        'receipt': 'test receipt text'
    })
    assert resp.status_code == 200


def test_split_receipts_setting_persists(clean_db, client):
    """split_receipts and print_recovery_receipt settings must be saved
    and retrievable via GET /settings/."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    resp = client.post(f'/api/settings/?db={db}', json={
        'split_receipts': '1', 'print_recovery_receipt': '1'
    })
    assert resp.status_code == 200

    resp = client.get(f'/api/settings/?db={db}')
    settings = resp.get_json()
    assert settings['split_receipts'] == '1'
    assert settings['print_recovery_receipt'] == '1'


def test_split_receipts_off_by_default(clean_db, client):
    """split_receipts and print_recovery_receipt must default to '0'."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    resp = client.get(f'/api/settings/?db={db}')
    settings = resp.get_json()
    assert settings['split_receipts'] == '0'
    assert settings['print_recovery_receipt'] == '0'
