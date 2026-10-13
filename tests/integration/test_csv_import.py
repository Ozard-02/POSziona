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
