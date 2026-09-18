"""
Retry-safe atomic checkout tests.

- Retrying a sale with the same idempotency key never duplicates the order.
- Order + payment land in a single transaction (no order without payment).
- Client errors (bad tendered) create nothing.
- SSE broadcast failures never fail the sale.
"""
import pytest


def _setup_product(client, db_name, stock=10):
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    client.post(f'/api/products/sections?db={db_name}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db_name}',
                json={'section_id': 1, 'name': 'Coffee'})
    resp = client.post(f'/api/products/products?db={db_name}', json={
        'name': 'Coffee', 'price': 2.50,
        'section_id': 1, 'subsection_id': 1, 'stock': stock,
    })
    assert resp.status_code == 201
    return resp.get_json()['id']


def _fill_cart(client, db_name, product_id, qty=2):
    resp = client.post(f'/api/cart/add?db={db_name}',
                       json={'product_id': product_id, 'quantity': qty})
    assert resp.status_code == 200


def _summary(client, db_name):
    return client.get(f'/api/orders/report/summary?db={db_name}').get_json()


def test_retry_same_key_creates_single_order(clean_db, client):
    """POST checkout twice with the same key → exactly one order, one stock decrement."""
    db_name = clean_db
    pid = _setup_product(client, db_name, stock=10)
    _fill_cart(client, db_name, pid, qty=2)

    key = 'test-key-001'
    r1 = client.post(f'/api/orders/checkout?db={db_name}',
                     json={'payment_method': 'cash', 'tendered': 5.0,
                           'idempotency_key': key})
    assert r1.status_code == 201
    assert r1.get_json()['replayed'] is False
    order_id = r1.get_json()['order_id']

    # Simulate operator retry after a (perceived) failure: refill the
    # session cart the same way and POST again with the same key.
    _fill_cart(client, db_name, pid, qty=2)
    r2 = client.post(f'/api/orders/checkout?db={db_name}',
                     json={'payment_method': 'cash', 'tendered': 5.0,
                           'idempotency_key': key})
    assert r2.status_code == 201
    assert r2.get_json()['replayed'] is True
    assert r2.get_json()['order_id'] == order_id

    assert _summary(client, db_name)['total_orders'] == 1

    # Stock decremented exactly once (10 - 2, not 10 - 4)
    from app.services.product_service import get_product_by_id
    assert get_product_by_id(db_name, pid)['stock_count'] == 8


def test_different_keys_create_different_orders(clean_db, client):
    """Two sales with different keys → two orders (no over-dedup)."""
    db_name = clean_db
    pid = _setup_product(client, db_name, stock=10)

    for key in ('test-key-a', 'test-key-b'):
        _fill_cart(client, db_name, pid, qty=1)
        r = client.post(f'/api/orders/checkout?db={db_name}',
                        json={'payment_method': 'cash', 'idempotency_key': key})
        assert r.status_code == 201
        assert r.get_json()['replayed'] is False

    assert _summary(client, db_name)['total_orders'] == 2


def test_payment_recorded_atomically_with_order(clean_db, client):
    """Payment row exists with the same total as the order (single transaction)."""
    db_name = clean_db
    pid = _setup_product(client, db_name, stock=10)
    _fill_cart(client, db_name, pid, qty=2)

    r = client.post(f'/api/orders/checkout?db={db_name}',
                    json={'payment_method': 'cash', 'tendered': 10.0,
                          'idempotency_key': 'test-key-pay'})
    assert r.status_code == 201
    order_id = r.get_json()['order_id']
    assert r.get_json()['total'] == 5.0

    from app.services.order_service import get_order_details
    details = get_order_details(db_name, order_id)
    assert len(details['payments']) == 1
    assert details['payments'][0]['amount'] == details['order']['total'] == 5.0
    assert details['payments'][0]['change_due'] == 5.0


def test_bad_tendered_creates_nothing(clean_db, client):
    """Under-tendered cash → 400 and zero orders (validation before any write)."""
    db_name = clean_db
    pid = _setup_product(client, db_name, stock=10)
    _fill_cart(client, db_name, pid, qty=2)

    r = client.post(f'/api/orders/checkout?db={db_name}',
                    json={'payment_method': 'cash', 'tendered': 1.0})
    assert r.status_code == 400
    assert _summary(client, db_name)['total_orders'] == 0

    from app.services.product_service import get_product_by_id
    assert get_product_by_id(db_name, pid)['stock_count'] == 10


def test_broadcast_failure_does_not_fail_sale(clean_db, client, monkeypatch):
    """If SSE broadcast explodes, the sale still succeeds exactly once."""
    import app.api.orders as orders_api

    def boom(*args, **kwargs):
        raise RuntimeError('SSE down')

    monkeypatch.setattr(orders_api, 'broadcast', boom)

    db_name = clean_db
    pid = _setup_product(client, db_name, stock=10)
    _fill_cart(client, db_name, pid, qty=2)

    r = client.post(f'/api/orders/checkout?db={db_name}',
                    json={'payment_method': 'card', 'idempotency_key': 'test-key-sse'})
    assert r.status_code == 201
    assert _summary(client, db_name)['total_orders'] == 1
