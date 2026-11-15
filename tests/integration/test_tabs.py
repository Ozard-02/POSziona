"""Open tabs: the money charged to a guest must be collectable.

A tab sale is an order with `payment_method='tab'` and no payment row.
Before this, nothing could close it: the money never reached the till
expected-cash figure and the payment report was short.
"""
import pytest

from app.database.connection import PartyDatabase
from app.services.order_service import expected_cash_total, list_open_tabs


def _login(client, db, pin='1234'):
    assert client.post(f'/api/auth/login?db={db}', json={'pin': pin}).status_code == 200


def _product(client, db, price=2.50):
    """Catalog setup is admin work (every catalog route is admin-only)."""
    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}',
                json={'section_id': 1, 'name': 'Coffee'})
    r = client.post(f'/api/products/products?db={db}', json={
        'name': 'Coffee', 'price': price, 'section_id': 1, 'subsection_id': 1})
    assert r.status_code == 201, r.get_json()
    return r.get_json()['id']


def _open_tab(client, db, guest='Tavolo 3'):
    """Admin sets the counter up, then the OPERATOR opens the tab."""
    _login(client, db, '0000')
    pid = _product(client, db)
    _login(client, db, '1234')
    assert client.post(f'/api/cart/add?db={db}',
                       json={'product_id': pid, 'quantity': 2}).status_code == 200
    r = client.post(f'/api/orders/checkout?db={db}',
                    json={'payment_method': 'tab', 'guest_name': guest})
    assert r.status_code == 201, r.get_json()
    return r.get_json()['order_id'], r.get_json()['total']


def test_tab_is_listed_until_it_is_settled(clean_db, client):
    _login(client, clean_db)
    order_id, total = _open_tab(client, clean_db, 'Tavolo 3')

    tabs = client.get(f'/api/orders/tabs?db={clean_db}').get_json()
    assert len(tabs) == 1
    assert tabs[0]['id'] == order_id
    assert tabs[0]['guest_name'] == 'Tavolo 3'
    assert tabs[0]['total'] == total
    assert tabs[0]['operator_name'] == 'operator'

    r = client.post(f'/api/orders/{order_id}/settle?db={clean_db}',
                    json={'payment_method': 'card'})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['total'] == total
    assert client.get(f'/api/orders/tabs?db={clean_db}').get_json() == []


def test_settling_records_the_payment_and_the_real_method(clean_db, client):
    _login(client, clean_db)
    order_id, total = _open_tab(client, clean_db)

    r = client.post(f'/api/orders/{order_id}/settle?db={clean_db}',
                    json={'payment_method': 'cash', 'tendered': 10.0})
    assert r.status_code == 200
    assert r.get_json()['change_due'] == round(10.0 - total, 2)

    with PartyDatabase(clean_db) as conn:
        method = conn.execute(
            "SELECT payment_method FROM orders WHERE id = ?", (order_id,)
        ).fetchone()[0]
        payments = conn.execute(
            "SELECT method, amount, tendered, change_due FROM payments WHERE order_id = ?",
            (order_id,)).fetchall()
    assert method == 'cash'
    assert len(payments) == 1
    assert payments[0]['amount'] == total
    assert payments[0]['tendered'] == 10.0

    # The cash is now really in the drawer as far as the till is concerned.
    assert expected_cash_total(clean_db) == total


def test_a_tab_cannot_be_settled_twice(clean_db, client):
    _login(client, clean_db)
    order_id, _ = _open_tab(client, clean_db)
    assert client.post(f'/api/orders/{order_id}/settle?db={clean_db}',
                       json={'payment_method': 'card'}).status_code == 200
    r = client.post(f'/api/orders/{order_id}/settle?db={clean_db}',
                    json={'payment_method': 'cash'})
    assert r.status_code == 400
    assert 'not an open tab' in r.get_json()['error']
    # Still exactly one payment.
    with PartyDatabase(clean_db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM payments WHERE order_id = ?", (order_id,)
        ).fetchone()[0] == 1


@pytest.mark.parametrize('body,needle', [
    ({'payment_method': 'tab'}, 'must be one of'),
    ({'payment_method': 'bitcoin'}, 'must be one of'),
    ({}, 'must be one of'),
    ({'payment_method': 'cash', 'tendered': 0.5}, 'at least the total'),
    ({'payment_method': 'cash', 'tendered': -1}, 'non-negative'),
])
def test_bad_settlement_is_a_client_error(clean_db, client, body, needle):
    _login(client, clean_db)
    order_id, _ = _open_tab(client, clean_db)
    r = client.post(f'/api/orders/{order_id}/settle?db={clean_db}', json=body)
    assert r.status_code == 400
    assert needle in r.get_json()['error']
    # Nothing was written by a refused settlement.
    with PartyDatabase(clean_db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM payments WHERE order_id = ?", (order_id,)
        ).fetchone()[0] == 0


def test_unknown_order_is_a_client_error(clean_db, client):
    _login(client, clean_db)
    r = client.post(f'/api/orders/999/settle?db={clean_db}',
                    json={'payment_method': 'cash'})
    assert r.status_code == 400
    assert 'not found' in r.get_json()['error']


def test_settling_needs_a_login(clean_db, client):
    _login(client, clean_db)
    order_id, _ = _open_tab(client, clean_db)
    client.post(f'/api/auth/logout?db={clean_db}')
    assert client.get(f'/api/orders/tabs?db={clean_db}').status_code == 403
    assert client.post(f'/api/orders/{order_id}/settle?db={clean_db}',
                       json={'payment_method': 'cash'}).status_code == 403


def test_settling_does_not_touch_stock_or_totals(clean_db, client):
    """The sale already happened: settling only records the money."""
    _login(client, clean_db)
    order_id, total = _open_tab(client, clean_db)
    with PartyDatabase(clean_db) as conn:
        before = conn.execute("SELECT total, stock_count FROM orders o, products p "
                              "WHERE o.id = ? AND p.id = 1", (order_id,)).fetchone()
    client.post(f'/api/orders/{order_id}/settle?db={clean_db}',
                json={'payment_method': 'wallet'})
    with PartyDatabase(clean_db) as conn:
        after = conn.execute("SELECT total FROM orders WHERE id = ?",
                             (order_id,)).fetchone()
        stock = conn.execute("SELECT stock_count FROM products WHERE id = 1").fetchone()
    assert after['total'] == before['total'] == total
    assert stock['stock_count'] == before['stock_count']
