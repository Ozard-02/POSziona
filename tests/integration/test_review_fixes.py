"""
Regression tests for the 2026-10-28 review fixes.

- Settings writes and sales reports are admin-only (printer_path is
  opened for writing; reports are reachable from the whole LAN).
- A cart discount follows the cart: percentage re-applies to the current
  subtotal, so screen total, tendered and charged total always agree.
- Disabled/archived products can't be added through a stale POS button.
- Snapshot retention is a device-global setting the scheduler honours.
- CSV-imported tags get a visible badge colour.
- Bulk stock 0 still reaches the POS screens.
- Tab sales keep the guest name the POS asks for.
- One unreadable DB doesn't block the other parties' snapshots.
"""
import os

import pytest


def _admin(client, db):
    r = client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    assert r.status_code == 200


def _product(client, db, price=10.0, stock=None):
    _admin(client, db)
    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}',
                json={'section_id': 1, 'name': 'Beer'})
    r = client.post(f'/api/products/products?db={db}', json={
        'name': 'Beer', 'price': price, 'section_id': 1,
        'subsection_id': 1, 'stock': stock})
    assert r.status_code == 201
    return r.get_json()['id']


# ---- settings are admin-only ------------------------------------------

@pytest.mark.parametrize('url, body', [
    ('/api/settings/?db=test_party', {'printer_path': '/tmp/evil'}),
    ('/api/settings/default-payment?db=test_party', {'method': 'card'}),
    ('/api/parties/test_party/settings', {'receipt_header': 'x'}),
])
def test_settings_writes_need_admin(clean_db, client, url, body):
    assert client.post(url, json=body).status_code == 403
    # A plain operator is not enough either
    client.post('/api/auth/login?db=test_party', json={'pin': '1234'})
    assert client.post(url, json=body).status_code == 403
    _admin(client, 'test_party')
    assert client.post(url, json=body).status_code == 200


@pytest.mark.parametrize('url', [
    '/api/orders/report/summary?db=test_party',
    '/api/orders/report/items?db=test_party',
    '/api/orders/report/export-csv?db=test_party',
    '/api/orders/recent?db=test_party',
    '/api/orders/1?db=test_party',
])
def test_sales_reports_need_admin(clean_db, client, url):
    assert client.get(url).status_code == 403
    client.post('/api/auth/login?db=test_party', json={'pin': '1234'})
    assert client.get(url).status_code == 403
    _admin(client, 'test_party')
    assert client.get(url).status_code in (200, 404)  # 404: no order 1 yet


def test_log_receipt_needs_login(clean_db, client):
    url = '/api/orders/log-receipt?db=test_party'
    assert client.post(url, json={'receipt': 'x'}).status_code == 403
    client.post('/api/auth/login?db=test_party', json={'pin': '1234'})
    assert client.post(url, json={'receipt': 'x'}).status_code == 200


# ---- discount follows the cart ----------------------------------------

def test_percentage_discount_reapplies_after_cart_changes(clean_db, client):
    db = clean_db
    pid = _product(client, db, price=10.0)
    client.post(f'/api/cart/add?db={db}', json={'product_id': pid})
    r = client.post(f'/api/cart/discount?db={db}',
                    json={'type': 'percentage', 'value': 10})
    assert r.get_json()['total'] == pytest.approx(9.0)

    # Adding a second item after the discount: 10% of 20, not of 10
    r = client.post(f'/api/cart/add?db={db}', json={'product_id': pid})
    assert r.get_json()['total'] == pytest.approx(18.0)

    # The POS screen tenders exactly what it shows; the server must agree
    r = client.post(f'/api/orders/checkout?db={db}',
                    json={'payment_method': 'cash', 'tendered': 18.0})
    assert r.status_code == 201, r.get_json()
    assert r.get_json()['total'] == pytest.approx(18.0)


def test_fixed_discount_never_exceeds_shrunk_cart(clean_db, client):
    db = clean_db
    pid = _product(client, db, price=3.0)
    client.post(f'/api/cart/add?db={db}', json={'product_id': pid, 'quantity': 2})
    client.post(f'/api/cart/discount?db={db}', json={'type': 'fixed', 'value': 5})
    r = client.post(f'/api/cart/update?db={db}', json={'product_id': pid, 'quantity': 1})
    assert r.get_json()['total'] == pytest.approx(0.0)


def test_get_cart_returns_items_and_discount(clean_db, client):
    """The POS restores the cart (and discount) from here after a reload."""
    db = clean_db
    pid = _product(client, db, price=4.0)
    client.post(f'/api/cart/add?db={db}', json={'product_id': pid})
    client.post(f'/api/cart/discount?db={db}', json={'type': 'percentage', 'value': 50})
    data = client.get(f'/api/cart/?db={db}').get_json()
    assert [i['product_id'] for i in data['items']] == [pid]
    assert data['discount'] == {'type': 'percentage', 'value': 50.0}
    assert data['total'] == pytest.approx(2.0)


def test_unknown_discount_type_rejected(clean_db, client):
    db = clean_db
    pid = _product(client, db)
    client.post(f'/api/cart/add?db={db}', json={'product_id': pid})
    r = client.post(f'/api/cart/discount?db={db}', json={'type': 'bogus', 'value': 5})
    assert r.status_code == 400


def test_garbage_tendered_is_a_client_error(clean_db, client):
    db = clean_db
    pid = _product(client, db)
    client.post(f'/api/cart/add?db={db}', json={'product_id': pid})
    r = client.post(f'/api/orders/checkout?db={db}',
                    json={'payment_method': 'cash', 'tendered': 'ten'})
    assert r.status_code == 400


def test_float_exact_tender_is_accepted(clean_db, client):
    """0.1 + 0.2 tendered against a 0.3 cart is the exact amount, not short."""
    db = clean_db
    pid = _product(client, db, price=0.1)
    client.post(f'/api/cart/add?db={db}', json={'product_id': pid, 'quantity': 3})
    r = client.post(f'/api/orders/checkout?db={db}',
                    json={'payment_method': 'cash', 'tendered': 0.3})
    assert r.status_code == 201, r.get_json()


def test_tab_sale_keeps_guest_name(clean_db, client):
    """The POS asks who a tab belongs to: the name must be stored."""
    db = clean_db
    pid = _product(client, db)
    client.post(f'/api/cart/add?db={db}', json={'product_id': pid})
    r = client.post(f'/api/orders/checkout?db={db}',
                    json={'payment_method': 'tab', 'guest_name': '  Marco  '})
    assert r.status_code == 201, r.get_json()
    assert r.get_json()['guest_name'] == 'Marco'
    recent = client.get(f'/api/orders/recent?db={db}').get_json()
    assert recent[0]['guest_name'] == 'Marco'

    # Ignored for non-tab sales
    client.post(f'/api/cart/add?db={db}', json={'product_id': pid})
    r = client.post(f'/api/orders/checkout?db={db}',
                    json={'payment_method': 'card', 'guest_name': 'X'})
    assert r.get_json()['guest_name'] is None


# ---- unavailable products stay out of the cart ------------------------

def test_inactive_product_cannot_be_added(clean_db, client):
    db = clean_db
    pid = _product(client, db)
    client.put(f'/api/products/products/{pid}?db={db}', json={'is_active': 0})
    r = client.post(f'/api/cart/add?db={db}', json={'product_id': pid})
    assert r.status_code == 400


# ---- snapshot retention is device-global -------------------------------

def test_snapshot_keep_count_reaches_the_scheduler(clean_db, client):
    from app.services import backup_service
    _admin(client, clean_db)
    r = client.post(f'/api/settings/?db={clean_db}', json={'snapshot_keep_count': '3'})
    assert r.status_code == 200
    assert backup_service._keep_count() == 3


# ---- CSV-imported tags are visible ------------------------------------

def test_csv_import_tags_use_visible_defaults(clean_db, client):
    from app.services.product_service import import_products_from_csv, get_all_tags
    import_products_from_csv(clean_db, [{
        'name': 'Spritz', 'price': '5', 'section': 'Bar',
        'subsection': 'Cocktails', 'tags': 'Imported'}])
    tag = next(t for t in get_all_tags(clean_db) if t['name'] == 'Imported')
    assert tag['color'] == '#3498db'
    assert tag['bg_color'] is None and tag['text_color'] is None


# ---- bulk stock 0 is broadcast ----------------------------------------

def test_bulk_stock_zero_is_broadcast(clean_db, client, monkeypatch):
    from app.api import products as products_api
    sent = []
    monkeypatch.setattr(products_api, 'broadcast',
                        lambda kind, data: sent.append((kind, data)))
    pid = _product(client, clean_db, stock=5)
    r = client.post(f'/api/products/products/bulk?db={clean_db}',
                    json={'product_ids': [pid], 'updates': {'stock': 0}})
    assert r.status_code == 200
    kind, data = sent[-1]
    assert kind == 'bulk_product_update'
    assert data['stock_count'] == 0


# ---- snapshots survive one bad DB -------------------------------------

def test_snapshot_skips_unreadable_party(clean_db, tmp_path, monkeypatch):
    from app.services import backup_service
    from app.utils.config import PARTY_DB_DIR
    monkeypatch.setattr(backup_service, 'BACKUP_DIR', str(tmp_path / 'backups'))
    bad = os.path.join(PARTY_DB_DIR, 'zz_not_a_database.db')
    with open(bad, 'wb') as f:
        f.write(b'this is not sqlite' * 100)
    try:
        name = backup_service.run_snapshots(keep=5)
        files = os.listdir(tmp_path / 'backups' / name)
        assert 'test_party.db' in files
        assert 'zz_not_a_database.db' not in files
    finally:
        os.remove(bad)
