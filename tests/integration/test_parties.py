"""
Tests for party creation from templates.
"""
import pytest
from app.database import templates_db


def test_create_party_from_template(clean_db, client):
    """Test creating a party from a template."""
    db_name = clean_db
    
    # Login as admin
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    
    # Create a template with products
    template_id = templates_db.create_template('Weekend Party', 'Test party template')
    assert template_id is not None
    
    # Add products to template
    templates_db.add_template_product(
        template_id, 'Small Coffee', 2.50, 'Drinks', 'Coffee', 'COF-S'
    )
    templates_db.add_template_product(
        template_id, 'Big Coffee', 3.50, 'Drinks', 'Coffee', 'COF-B'
    )
    templates_db.add_template_product(
        template_id, 'Tea', 2.00, 'Drinks', 'Hot Drinks', None
    )
    
    # Create party from template
    resp = client.post('/api/parties/', json={
        'name': 'Weekend Party',
        'template_id': template_id,
        'start_date': '2024-06-01',
        'end_date': '2024-06-02'
    })
    assert resp.status_code == 201
    
    new_party = resp.get_json()
    # db_name may have been sanitized
    new_db = new_party['db_name']
    
    # Verify products were copied
    resp = client.get(f'/api/products/?db={new_db}')
    sections = resp.get_json()
    assert len(sections) == 1
    assert sections[0]['name'] == 'Drinks'
    
    # Verify products in Coffee subsection
    coffee_sub_id = None
    for sub in sections[0]['subsections']:
        if sub['name'] == 'Coffee':
            coffee_sub_id = sub['id']
    
    resp = client.get(f'/api/products/{coffee_sub_id}/products?db={new_db}')
    products = resp.get_json()
    assert len(products) == 2


def test_duplicate_party(clean_db, client):
    """Test duplicating an existing party."""
    db_name = clean_db
    
    # Login as admin
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    
    # Create section and product
    client.post(f'/api/products/sections?db={db_name}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db_name}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db_name}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1
    })
    
    # Duplicate the party
    resp = client.post(f'/api/parties/{db_name}/duplicate', json={'name': 'Copy'})
    assert resp.status_code == 200
    assert 'duplicated' in resp.get_json()['message'].lower()
    
    # Get the actual db_name from the returned message
    new_db = resp.get_json().get('new_name', 'Copy')
    
    # Verify the duplicated party has the same products
    resp = client.get(f'/api/products/?db={new_db}')
    sections = resp.get_json()
    assert len(sections) == 1
    assert sections[0]['name'] == 'Drinks'
