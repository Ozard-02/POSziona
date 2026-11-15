"""Money precision and hostile-input guards around a sale.

Both are cheap to get wrong and expensive in the field: totals that do
not match the printed receipt, and a session poisoned by a single
malformed request.
"""
import pytest

from app.services.order_service import checkout_order, record_cash_count
from app.services.printer_service import MAX_RECEIPT_CHARS, print_text


def _login(client, db, pin='1234'):
    assert client.post(f'/api/auth/login?db={db}', json={'pin': pin}).status_code == 200


def _product(client, db, price, stock=None):
    """Create the catalog scaffolding (clean_db only seeds operators)."""
    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}',
                json={'section_id': 1, 'name': 'Coffee'})
    body = {'name': 'Thing', 'price': price, 'section_id': 1, 'subsection_id': 1}
    if stock is not None:
        body['stock'] = stock
    r = client.post(f'/api/products/products?db={db}', json=body)
    assert r.status_code == 201, r.get_json()
    return r.get_json()['id']


def test_stored_amounts_have_no_float_noise(clean_db, client):
    """3 x 1.10 is 3.30 on the receipt, in the DB and in the CSV."""
    _login(client, clean_db, '0000')
    pid = _product(client, clean_db, 1.10)
    client.post(f'/api/cart/add?db={clean_db}', json={'product_id': pid, 'quantity': 3})

    r = client.post(f'/api/orders/checkout?db={clean_db}',
                    json={'payment_method': 'cash', 'tendered': 5.0})
    assert r.status_code == 201, r.get_json()
    assert r.get_json()['total'] == 3.30

    from app.database.connection import PartyDatabase
    with PartyDatabase(clean_db) as conn:
        order = dict(conn.execute(
            "SELECT subtotal, total FROM orders ORDER BY id DESC LIMIT 1").fetchone())
        payment = dict(conn.execute(
            "SELECT amount, change_due FROM payments ORDER BY id DESC LIMIT 1").fetchone())
    assert order == {'subtotal': 3.30, 'total': 3.30}
    assert payment == {'amount': 3.30, 'change_due': 1.70}

    csv_text = client.get(f'/api/parties/{clean_db}/recap').data.decode()
    assert '3.3000000000000003' not in csv_text


def test_cash_count_is_rounded(clean_db):
    """The till difference is exactly the amount on the slip."""
    row = record_cash_count(clean_db, 0.1 + 0.2, operator_id=1)
    assert row['difference'] == 0.3


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity'])
def test_non_finite_discount_is_rejected(clean_db, client, value):
    """`NaN` used to be stored in the session and serialized back as a bare
    NaN token: invalid JSON, so every later cart read broke the POS screen."""
    _login(client, clean_db)
    r = client.post(f'/api/cart/discount?db={clean_db}',
                    data='{"type":"percentage","value":' + value + '}',
                    content_type='application/json')
    assert r.status_code == 400
    cart = client.get(f'/api/cart/?db={clean_db}')
    assert cart.status_code == 200
    assert b'NaN' not in cart.data


def test_cash_count_rejects_nan(clean_db, client):
    _login(client, clean_db)
    r = client.post(f'/api/orders/cash-counts?db={clean_db}',
                    data='{"counted": NaN}', content_type='application/json')
    assert r.status_code == 400


def test_print_refuses_an_absurd_receipt(clean_db, monkeypatch):
    """A broken client must not push megabytes at a thermal printer."""
    import app.services.printer_service as ps
    monkeypatch.setattr(ps, 'resolve_device',
                        lambda db: ('/tmp/unused-printer', 9600, 42, True))
    with pytest.raises(ValueError) as exc:
        print_text(clean_db, 'x' * (MAX_RECEIPT_CHARS + 1))
    assert 'too long' in str(exc.value)


def test_logged_receipt_is_truncated_not_lost(clean_db, client, caplog):
    _login(client, clean_db)
    r = client.post(f'/api/orders/log-receipt?db={clean_db}',
                    json={'order_id': 1, 'receipt': 'R' * 20000})
    assert r.status_code == 200
    assert 'receipt truncated' in caplog.text
