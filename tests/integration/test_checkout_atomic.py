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


def test_mid_transaction_crash_rolls_back_everything(clean_db, client):
    """A failure halfway through checkout (bad product FK) leaves zero trace."""
    from app.services.order_service import checkout_order

    db_name = clean_db
    _setup_product(client, db_name, stock=10)

    with pytest.raises(Exception):
        checkout_order(
            db_name,
            [{'product_id': 99999, 'quantity': 1, 'unit_price': 1.0}],
            'cash', 1, idempotency_key='test-key-crash')

    assert _summary(client, db_name)['total_orders'] == 0
    # ...including no orphaned idempotency key (retry starts clean)
    from app.services.order_service import checkout_order as co2
    _fill_cart(client, db_name, 1, qty=1)
    order_id, total, _, replayed = co2(
        db_name, [{'product_id': 1, 'quantity': 1, 'unit_price': 2.50}],
        'cash', 1, idempotency_key='test-key-crash')
    assert replayed is False
    assert _summary(client, db_name)['total_orders'] == 1


def test_concurrent_same_key_single_order(clean_db, client):
    """10 threads retrying the same sale at once → exactly 1 order."""
    import threading
    from app.services.order_service import checkout_order, get_sales_summary

    db_name = clean_db
    _setup_product(client, db_name, stock=100)

    results, errors = [], []

    def attempt():
        try:
            results.append(checkout_order(
                db_name, [{'product_id': 1, 'quantity': 1, 'unit_price': 2.50}],
                'cash', 1, idempotency_key='test-key-race'))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=attempt) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 10
    assert {r[0] for r in results} == {results[0][0]}  # all got the same order
    assert get_sales_summary(db_name)['total_orders'] == 1


def test_concurrent_checkouts_never_oversell(clean_db, client):
    """10 threads × qty 2 against stock 5: exactly 2 sales land (R13).

    Replaces the old clamp-at-0 contract: a sale that cannot be covered by
    the shelf must be REFUSED, never silently recorded and clamped.
    """
    import threading
    from app.services.order_service import checkout_order
    from app.services.product_service import get_product_by_id

    db_name = clean_db
    _setup_product(client, db_name, stock=5)

    ok = []
    refused = []
    other = []
    lock = threading.Lock()

    def attempt(i):
        try:
            checkout_order(
                db_name, [{'product_id': 1, 'quantity': 2, 'unit_price': 2.50}],
                'cash', 1, idempotency_key=f'test-key-load-{i}')
            with lock:
                ok.append(i)
        except ValueError:
            with lock:
                refused.append(i)
        except Exception as e:  # noqa: BLE001
            with lock:
                other.append(e)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert other == []
    assert len(ok) == 2, ok            # floor(stock 5 / qty 2)
    assert len(ok) + len(refused) == 10
    assert get_product_by_id(db_name, 1)['stock_count'] == 1
    summary = client.get(f'/api/orders/report/summary?db={db_name}').get_json()
    assert summary['total_orders'] == 2


def test_recap_csv_sections_share_one_snapshot(clean_db, client, monkeypatch):
    """A sale committing mid-recap must not split the sections (R18).

    Old code opened one connection per section: summary could say one
    order while items/recent (read later) already showed two.
    """
    import csv
    import io

    import app.services.order_service as osvc
    from app.database.connection import PartyDatabase

    db_name = clean_db
    pid = _setup_product(client, db_name, stock=10)
    _fill_cart(client, db_name, pid, qty=1)
    r = client.post(f'/api/orders/checkout?db={db_name}',
                    json={'payment_method': 'cash'})
    assert r.status_code == 201

    real_summary = osvc._sales_summary

    def summary_then_concurrent_sale(conn, date_filter=None):
        result = real_summary(conn, date_filter)  # first read pins the snapshot
        # Another connection sells one more while the recap is running
        osvc.checkout_order(
            db_name,
            [{'product_id': pid, 'quantity': 1, 'unit_price': 2.50,
              'name': 'Coffee'}],
            'cash', 1)
        return result

    monkeypatch.setattr(osvc, '_sales_summary',
                        summary_then_concurrent_sale)

    csv_text = osvc.build_recap_csv(db_name)

    rows = list(csv.reader(io.StringIO(csv_text)))
    assert ['Total Orders', '1'] in rows          # pre-sale snapshot
    item_header = rows.index([
        'Product Name', 'SKU', 'Section', 'Subsection', 'Quantity Sold',
        'Total Amount', 'Current Price', 'Current Stock', 'Active'])
    assert rows[item_header + 1][4] == '1'        # same snapshot
    ridx = rows.index([
        'Order ID', 'Timestamp', 'Operator', 'Guest', 'Total', 'Discount',
        'Payment Method'])
    assert len([r for r in rows[ridx + 1:] if r]) == 1

    # ... while the concurrent sale DID land in the database.
    with PartyDatabase(db_name) as conn:
        assert conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0] == 2


def test_loser_reread_sees_winner_commit(clean_db, client):
    """The idempotency race fallback relies on rollback giving a fresh read.

    Simulates the exact interleaving: loser SELECTs (miss — winner hasn't
    committed), winner commits, loser INSERTs the key (IntegrityError),
    loser rolls back and re-reads → must see the winner's order.
    """
    import sqlite3
    from app.database.connection import _get_party_db_path

    db_name = clean_db
    _setup_product(client, db_name, stock=10)
    path = _get_party_db_path(db_name)

    loser = sqlite3.connect(path)
    try:
        miss = loser.execute(
            "SELECT order_id FROM idempotency_keys WHERE key = 'test-key-fresh'"
        ).fetchone()
        assert miss is None

        # Winner commits through the public path while loser holds its snapshot
        _fill_cart(client, db_name, 1, qty=1)
        r = client.post(f'/api/orders/checkout?db={db_name}',
                        json={'payment_method': 'cash',
                              'idempotency_key': 'test-key-fresh'})
        assert r.status_code == 201
        winner_id = r.get_json()['order_id']

        # Loser now hits the duplicate key...
        with pytest.raises(sqlite3.IntegrityError):
            loser.execute(
                "INSERT INTO idempotency_keys (key, order_id) VALUES (?, ?)",
                ('test-key-fresh', 999999))
        loser.rollback()

        # ...and its re-read must observe the winner (fresh snapshot)
        row = loser.execute(
            "SELECT order_id FROM idempotency_keys WHERE key = 'test-key-fresh'"
        ).fetchone()
        assert row is not None
        assert row[0] == winner_id
    finally:
        loser.close()
