"""
Resilience: input validation + financial-integrity edges. One behavior per test.

Setup helper kills the 5-line seed boilerplate; parametrization covers the
value matrix instead of one test per value.
"""
import pytest


def _seed_product(client, db, price=2.50):
    """Login as admin + create section/subsection/product (id 1)."""
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}',
                json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': price,
        'section_id': 1, 'subsection_id': 1})
    return 1


def _checkout(client, db, **kwargs):
    body = {'payment_method': 'cash'}
    body.update(kwargs)
    return client.post(f'/api/orders/checkout?db={db}', json=body)


@pytest.mark.parametrize('dtype,value', [('fixed', 9999), ('percentage', 200)])
def test_excessive_discount_clamps_total_to_zero(clean_db, client, dtype, value):
    """Discounts beyond the subtotal clamp the total at 0, never negative."""
    db = clean_db
    _seed_product(client, db)
    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 1})

    resp = client.post(f'/api/cart/discount?db={db}',
                       json={'type': dtype, 'value': value})
    assert resp.status_code == 200
    assert resp.get_json()['total'] == 0.0

    resp = _checkout(client, db)
    assert resp.status_code == 201
    assert resp.get_json()['total'] == 0.0


@pytest.mark.parametrize('quantity', ['abc', -5, 0])
def test_cart_add_rejects_bad_quantity(clean_db, client, quantity):
    """Non-integer or < 1 quantities on add return 400, not 500."""
    db = clean_db
    _seed_product(client, db)

    resp = client.post(f'/api/cart/add?db={db}',
                       json={'product_id': 1, 'quantity': quantity})
    assert resp.status_code == 400
    assert 'quantity' in resp.get_json()['error'].lower()


def test_cart_add_null_body(clean_db, client):
    """A null JSON body must return 400, not crash."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    resp = client.post(f'/api/cart/add?db={db}', data='null',
                       content_type='application/json')
    assert resp.status_code == 400


@pytest.mark.parametrize('quantity', ['not_a_number', 0, -2])
def test_cart_update_rejects_bad_quantity(clean_db, client, quantity):
    """Non-integer or < 1 quantities on update return 400."""
    db = clean_db
    _seed_product(client, db)
    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 1})

    resp = client.post(f'/api/cart/update?db={db}',
                       json={'product_id': 1, 'quantity': quantity})
    assert resp.status_code == 400


@pytest.mark.parametrize('dtype,value', [('percentage', 'abc'), ('fixed', -5)])
def test_discount_rejects_bad_value(clean_db, client, dtype, value):
    """Non-numeric or negative discount values return 400."""
    db = clean_db
    _seed_product(client, db)
    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 1})

    resp = client.post(f'/api/cart/discount?db={db}',
                       json={'type': dtype, 'value': value})
    assert resp.status_code == 400


@pytest.mark.parametrize('via', ['create', 'create_string', 'edit', 'bulk'])
def test_product_price_validation(clean_db, client, via):
    """Negative or non-numeric prices are rejected on every write path."""
    db = clean_db
    _seed_product(client, db)

    if via == 'create':
        resp = client.post(f'/api/products/products?db={db}', json={
            'name': 'Bad', 'price': -5.00, 'section_id': 1, 'subsection_id': 1})
    elif via == 'create_string':
        resp = client.post(f'/api/products/products?db={db}', json={
            'name': 'Bad', 'price': 'not_a_price',
            'section_id': 1, 'subsection_id': 1})
    elif via == 'edit':
        resp = client.put(f'/api/products/products/1?db={db}', json={'price': -10})
    else:
        resp = client.post(f'/api/products/products/bulk?db={db}', json={
            'product_ids': [1], 'updates': {'price': -5}})
    assert resp.status_code == 400
    assert 'price' in resp.get_json()['error'].lower()


def test_checkout_empty_cart(clean_db, client):
    """Checking out with an empty cart must return 400, not 500."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    assert _checkout(client, db).status_code == 400


@pytest.mark.parametrize('method,url,body', [
    ('POST', '/api/cart/add?db={db}', {'product_id': 999, 'quantity': 1}),
    ('DELETE', '/api/products/products/999?db={db}', None),
    ('GET', '/api/products/sections/999?db={db}', None),
])
def test_unknown_ids_return_404(clean_db, client, method, url, body):
    """Unknown product/section ids are 404 on every endpoint (never 500)."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    resp = client.open(url.format(db=db), method=method, json=body)
    assert resp.status_code == 404


def test_cart_update_missing_item_is_noop(clean_db, client):
    """Updating an item not in the cart changes nothing (200, cart intact)."""
    db = clean_db
    _seed_product(client, db)
    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 1})

    resp = client.post(f'/api/cart/update?db={db}',
                       json={'product_id': 1, 'quantity': 5})
    assert resp.status_code == 200
    assert resp.get_json()['cart'][0]['quantity'] == 5

    client.post(f'/api/cart/remove?db={db}', json={'product_id': 1})
    resp = client.post(f'/api/cart/update?db={db}',
                       json={'product_id': 1, 'quantity': 3})
    assert resp.status_code == 200


def test_discount_on_empty_cart(clean_db, client):
    """Applying a discount to an empty cart should return 0 total, not crash."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    resp = client.post(f'/api/cart/discount?db={db}',
                       json={'type': 'percentage', 'value': 10})
    assert resp.status_code == 200
    assert resp.get_json()['total'] == 0.0


@pytest.mark.parametrize('tendered', [5.00, -5])
def test_checkout_rejects_bad_tender(clean_db, client, tendered):
    """Under-tendered or negative cash amounts are rejected (no negative change)."""
    db = clean_db
    _seed_product(client, db, price=10.00)
    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 1})

    resp = _checkout(client, db, tendered=tendered)
    assert resp.status_code == 400


@pytest.mark.parametrize('body', [
    {'name': '', 'price': 5.00, 'section_id': 1, 'subsection_id': 1},
    {'name': 'Test Product', 'section_id': 1, 'subsection_id': 1},
])
def test_create_product_missing_fields(clean_db, client, body):
    """Products without a name or without a price are rejected."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}',
                json={'section_id': 1, 'name': 'Coffee'})

    resp = client.post(f'/api/products/products?db={db}', json=body)
    assert resp.status_code == 400


def test_create_product_price_zero(clean_db, client):
    """Price 0 is allowed (free item)."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}',
                json={'section_id': 1, 'name': 'Coffee'})

    resp = client.post(f'/api/products/products?db={db}', json={
        'name': 'Free Sample', 'price': 0, 'section_id': 1, 'subsection_id': 1})
    assert resp.status_code == 201


def test_bulk_edit_nonexistent_product(clean_db, client):
    """Bulk editing unknown ids skips them; known products still update."""
    db = clean_db
    _seed_product(client, db)

    resp = client.post(f'/api/products/products/bulk?db={db}', json={
        'product_ids': [1, 999], 'updates': {'price': 5.00}})
    assert resp.status_code == 200
    resp2 = client.get(f'/api/products/products/1?db={db}')
    assert resp2.get_json()['price'] == 5.0


def test_cart_remove_nonexistent_item(clean_db, client):
    """Removing an absent item is idempotent (200, not 500)."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    resp = client.post(f'/api/cart/remove?db={db}', json={'product_id': 999})
    assert resp.status_code == 200


def test_checkout_invalid_payment_method(clean_db, client):
    """Unknown payment methods are rejected."""
    db = clean_db
    _seed_product(client, db)
    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 1})

    resp = _checkout(client, db, payment_method='crypto')
    assert resp.status_code == 400


def test_create_duplicate_product_allowed(clean_db, client):
    """Same name twice creates two products (no UNIQUE on names) — never 500."""
    db = clean_db
    _seed_product(client, db)

    resp = client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 3.00, 'section_id': 1, 'subsection_id': 1})
    assert resp.status_code == 201


def test_create_duplicate_section_rejected(clean_db, client):
    """Duplicate section/subsection names are 400 (UNIQUE), never 500."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})

    resp = client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    assert resp.status_code == 400
    client.post(f'/api/products/subsections?db={db}',
                json={'section_id': 1, 'name': 'Coffee'})
    resp = client.post(f'/api/products/subsections?db={db}',
                       json={'section_id': 1, 'name': 'Coffee'})
    assert resp.status_code == 400
