"""
Tests for manual (non-template) party creation and manual product creation.
"""
import pytest


def test_create_empty_party(clean_db, client):
    """Test creating a party without a template."""
    db_name = clean_db

    # Login as admin
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    # Create an empty party
    resp = client.post('/api/parties/create-empty', json={
        'name': 'Manual Party',
        'start_date': '2024-07-01',
        'end_date': '2024-07-05'
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert data['db_name'] == 'Manual Party'
    assert data['party_name'] == 'Manual Party'

    # Verify the party DB was created and has default products
    resp = client.get(f'/api/products/?db=Manual Party')
    sections = resp.get_json()
    assert len(sections) > 0  # Should have default seed sections
    assert sections[0]['name'] == 'Drinks'


def test_create_empty_party_no_dates(clean_db, client):
    """Test creating a party without start/end dates."""
    db_name = clean_db

    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    resp = client.post('/api/parties/create-empty', json={
        'name': 'Quick Party'
    })
    assert resp.status_code == 201

    # Verify party settings
    from app.services.party_service import get_party_settings
    settings = get_party_settings('Quick Party')
    assert settings['party_name'] == 'Quick Party'
    assert 'start_date' in settings


def test_create_empty_party_missing_name(clean_db, client):
    """Test that creating a party without a name fails."""
    db_name = clean_db

    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    resp = client.post('/api/parties/create-empty', json={
        'name': ''
    })
    assert resp.status_code == 400
    assert 'required' in resp.get_json()['error'].lower()


def test_create_empty_party_with_template_still_works(clean_db, client):
    """Ensure the original template-based party creation still works."""
    db_name = clean_db

    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    from app.database import templates_db
    template_id = templates_db.create_template('Event Template', 'A test template')
    templates_db.add_template_product(
        template_id, 'Burger', 8.50, 'Food', 'Mains', 'BGR-1'
    )

    resp = client.post('/api/parties/', json={
        'name': 'Templated Party',
        'template_id': template_id
    })
    assert resp.status_code == 201
    assert 'db_name' in resp.get_json()


def test_create_product_with_new_section_and_subsection(clean_db, client):
    """Test creating a product while also creating new section and subsection inline."""
    db_name = clean_db

    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    # Create a new section
    resp = client.post(f'/api/products/sections?db={db_name}', json={'name': 'Desserts'})
    assert resp.status_code in (201, 200)

    # Create a new subsection under Desserts
    resp = client.get(f'/api/products/?db={db_name}')
    sections = resp.get_json()
    dessert_section = next(s for s in sections if s['name'] == 'Desserts')
    sub_resp = client.post(f'/api/products/subsections?db={db_name}', json={
        'section_id': dessert_section['id'],
        'name': 'Cakes'
    })
    assert sub_resp.status_code in (201, 200)

    # Create a product in the new section/subsection
    resp = client.get(f'/api/products/?db={db_name}')
    sections = resp.get_json()
    dessert_section = next(s for s in sections if s['name'] == 'Desserts')
    cakes_sub = next((sub for sub in dessert_section['subsections'] if sub['name'] == 'Cakes'), None)

    resp = client.post(f'/api/products/products?db={db_name}', json={
        'name': 'Chocolate Cake',
        'price': 4.50,
        'section_id': dessert_section['id'],
        'subsection_id': cakes_sub['id'],
        'sku': 'CAKE-CHOC',
        'stock': 15
    })
    assert resp.status_code == 201

    # Verify product appears in the subsection listing
    resp = client.get(f'/api/products/?db={db_name}')
    sections = resp.get_json()
    assert any(s['name'] == 'Desserts' for s in sections)


def test_export_products_csv(clean_db, client):
    """Test CSV export of products."""
    db_name = clean_db

    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    # Add a product to export
    client.post(f'/api/products/sections?db={db_name}', json={'name': 'Drinks'})
    resp = client.get(f'/api/products/?db={db_name}')
    sections = resp.get_json()
    drinks_section = next(s for s in sections if s['name'] == 'Drinks')

    client.post(f'/api/products/subsections?db={db_name}', json={
        'section_id': drinks_section['id'],
        'name': 'Hot'
    })
    resp = client.get(f'/api/products/?db={db_name}')
    sections = resp.get_json()
    drinks_section = next(s for s in sections if s['name'] == 'Drinks')

    sub_id = drinks_section['subsections'][0]['id']

    client.post(f'/api/products/products?db={db_name}', json={
        'name': 'Latte',
        'price': 2.75,
        'section_id': drinks_section['id'],
        'subsection_id': sub_id,
        'sku': 'LAT-1'
    })

    # Export
    resp = client.get(f'/api/products/export?db={db_name}')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'csv' in data
    assert 'Latte' in data['csv']
    assert 'Drinks' in data['csv']
    assert 'Cakes' not in data['csv']
