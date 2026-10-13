"""Till reconciliation: counted vs expected cash + history."""
import pytest


def _setup(client, db):
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}',
                json={'section_id': 1, 'name': 'Coffee'})


def _sell(client, db, name, price, method, tendered=None):
    r = client.post(f'/api/products/products?db={db}', json={
        'name': name, 'price': price, 'section_id': 1, 'subsection_id': 1})
    pid = r.get_json()['id']
    client.post(f'/api/cart/add?db={db}', json={'product_id': pid, 'quantity': 1})
    body = {'payment_method': method}
    if tendered is not None:
        body['tendered'] = tendered
    r = client.post(f'/api/orders/checkout?db={db}', json=body)
    assert r.status_code == 201, r.get_json()


def test_cash_count_math_and_history(clean_db, client):
    """Expected = cash sales only; difference = counted - expected; listed."""
    db = clean_db
    _setup(client, db)
    _sell(client, db, 'CashItem', 10.00, 'cash', tendered=10.00)
    _sell(client, db, 'CardItem', 5.00, 'card')

    r = client.get(f'/api/orders/cash-counts/expected?db={db}')
    assert r.get_json()['expected_cash'] == 10.00

    r = client.post(f'/api/orders/cash-counts?db={db}',
                    json={'counted': 12.00, 'note': 'evening close'})
    assert r.status_code == 201
    row = r.get_json()
    assert row['expected_cash'] == 10.00
    assert row['counted_cash'] == 12.00
    assert row['difference'] == 2.00
    assert row['operator_name'] == 'admin'

    history = client.get(f'/api/orders/cash-counts?db={db}').get_json()
    assert len(history) == 1
    assert history[0]['note'] == 'evening close'


@pytest.mark.parametrize('body,status', [
    ({}, 400),
    ({'counted': -5}, 400),
    ({'counted': 'lots'}, 400),
])
def test_cash_count_validation(clean_db, client, body, status):
    """Missing/negative/nonnumeric counts are rejected."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    r = client.post(f'/api/orders/cash-counts?db={db}', json=body)
    assert r.status_code == status


def test_cash_counts_require_login(clean_db, client):
    """Logged-out till counts are rejected."""
    db = clean_db
    assert client.get(f'/api/orders/cash-counts?db={db}').status_code == 403
    assert client.get(f'/api/orders/cash-counts/expected?db={db}').status_code == 403
    assert client.post(f'/api/orders/cash-counts?db={db}',
                       json={'counted': 1}).status_code == 403
