"""
Tests for CSV import functionality.
"""
import pytest

from app.services.product_service import import_products_from_csv
from app.database.connection import PartyDatabase


def test_csv_import(clean_db, client):
    """Test CSV import of products."""
    db_name = clean_db
    
    # Login as admin
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    
    # Import products via CSV
    csv_rows = [
        {'name': 'Small Coffee', 'price': 2.50, 'section': 'Drinks', 'subsection': 'Coffee', 'sku': 'COF-S'},
        {'name': 'Big Coffee', 'price': 3.50, 'section': 'Drinks', 'subsection': 'Coffee', 'sku': 'COF-B'},
        {'name': 'Tea', 'price': 2.00, 'section': 'Drinks', 'subsection': 'Hot Drinks', 'stock': 10},
        {'name': 'Water', 'price': 1.00, 'section': 'Drinks', 'subsection': 'Cold', 'stock': None},
    ]
    
    resp = client.post(f'/api/products/import-csv?db={db_name}', json={'rows': csv_rows})
    assert resp.status_code == 201
    assert 'Imported 4 products' in resp.get_json()['message']
    
    # Verify sections created
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
        if p['name'] == 'Small Coffee':
            assert p['stock_count'] is None  # unlimited
        if p['name'] == 'Big Coffee':
            assert p['stock_count'] is None  # unlimited


def test_csv_import_duplicate_sections(clean_db, client):
    """Test that CSV import doesn't create duplicate sections."""
    db_name = clean_db
    
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    
    # Import products with same section/subsection
    csv_rows = [
        {'name': 'Item A', 'price': 1.00, 'section': 'Food', 'subsection': 'Main'},
        {'name': 'Item B', 'price': 2.00, 'section': 'Food', 'subsection': 'Main'},
        {'name': 'Item C', 'price': 3.00, 'section': 'Food', 'subsection': 'Sides'},
    ]
    
    resp = client.post(f'/api/products/import-csv?db={db_name}', json={'rows': csv_rows})
    assert resp.status_code == 201
    
    # Should have 1 section, 2 subsections (Main, Sides)
    resp = client.get(f'/api/products/?db={db_name}')
    sections = resp.get_json()
    assert len(sections) == 1
    assert len(sections[0]['subsections']) == 2
    
    # Should have 3 products total
    total_products = 0
    for sub in sections[0]['subsections']:
        sub_id = sub['id']
        resp = client.get(f'/api/products/{sub_id}/products?db={db_name}')
        total_products += len(resp.get_json())
    assert total_products == 3
