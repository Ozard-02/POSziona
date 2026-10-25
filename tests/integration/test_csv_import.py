"""
Tests for CSV import functionality.
"""


def test_csv_import(clean_db, client):
    """Import creates sections/subsections/products with stock, deduped."""
    db_name = clean_db

    # Login as admin
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    # Import products via CSV (shared section, one row per subsection,
    # plus a nameless row that must be skipped, not counted)
    csv_rows = [
        {'name': 'Small Coffee', 'price': 2.50, 'section': 'Drinks', 'subsection': 'Coffee', 'sku': 'COF-S'},
        {'name': 'Big Coffee', 'price': 3.50, 'section': 'Drinks', 'subsection': 'Coffee', 'sku': 'COF-B'},
        {'name': 'Tea', 'price': 2.00, 'section': 'Drinks', 'subsection': 'Hot Drinks', 'stock': 10},
        {'name': 'Water', 'price': 1.00, 'section': 'Drinks', 'subsection': 'Cold', 'stock': None},
        {'name': '', 'price': 1.00, 'section': 'Drinks', 'subsection': 'Cold'},
    ]

    resp = client.post(f'/api/products/import-csv?db={db_name}', json={'rows': csv_rows})
    assert resp.status_code == 201
    assert resp.get_json()['count'] == 4  # nameless row skipped, not counted
    assert 'Imported 4 products' in resp.get_json()['message']

    # One section, deduped; three subsections incl. the empty-name row's
    resp = client.get(f'/api/products/?db={db_name}')
    sections = resp.get_json()
    assert len(sections) == 1  # Only 'Drinks' section
    assert sections[0]['name'] == 'Drinks'
    assert len(sections[0]['subsections']) == 3  # Coffee + Cold + Hot Drinks

    # Verify products in Coffee subsection
    coffee_sub_id = None
    for sub in sections[0]['subsections']:
        if sub['name'] == 'Coffee':
            coffee_sub_id = sub['id']

    resp = client.get(f'/api/products/{coffee_sub_id}/products?db={db_name}')
    products = resp.get_json()
    assert len(products) == 2
    names = [p['name'] for p in products]
    assert 'Small Coffee' in names
    assert 'Big Coffee' in names

    # Verify stock counts
    for p in products:
        if p['name'] in ('Small Coffee', 'Big Coffee'):
            assert p['stock_count'] is None  # unlimited


def test_concurrent_imports_share_lookups_without_failing(clean_db):
    """Two concurrent importers share section/subsection/tag (R12).

    Lookup columns are UNIQUE: the loser of the SELECT-then-INSERT race
    must re-select instead of aborting the whole import.
    """
    import threading
    from app.database.connection import PartyDatabase
    from app.services.product_service import import_products_from_csv

    db_name = clean_db
    errors = []
    counts = []
    barrier = threading.Barrier(2)

    def _rows(tag):
        return [
            {'name': f'{tag}-P{i}', 'price': 1.0, 'section': 'Bulk',
             'subsection': 'Rows', 'tags': 'bulk'}
            for i in range(300)
        ]

    def _import(tag):
        try:
            barrier.wait(timeout=5)
            counts.append(import_products_from_csv(db_name, _rows(tag)))
        except Exception as e:  # noqa: BLE001 — collected, asserted below
            errors.append(e)

    threads = [threading.Thread(target=_import, args=(f'T{n}',)) for n in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == []
    assert sorted(counts) == [300, 300]
    with PartyDatabase(db_name) as conn:
        assert conn.execute("SELECT COUNT(*) FROM sections").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM subsections").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 600
