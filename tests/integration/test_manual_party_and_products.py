"""
Tests for manual (non-template) party creation and manual product creation.
"""
import pytest


@pytest.mark.parametrize('dates', [
    {'start_date': '2024-07-01', 'end_date': '2024-07-05'},
    {},
])
def test_create_empty_party(clean_db, client, dates):
    """Empty parties are created with or without dates (defaults filled in)."""
    db_name = clean_db

    # Login as admin
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    # Create an empty party
    body = {'name': 'Manual Party'}
    body.update(dates)
    resp = client.post('/api/parties/create-empty', json=body)
    assert resp.status_code == 201
    data = resp.get_json()
    assert data['db_name'] == 'Manual Party'
    assert data['party_name'] == 'Manual Party'

    # Verify the party DB was created and has default products
    resp = client.get(f'/api/products/?db=Manual Party')
    sections = resp.get_json()
    assert len(sections) > 0  # Should have default seed sections
    assert sections[0]['name'] == 'Drinks'

    # Verify party settings
    from app.services.party_service import get_party_settings
    settings = get_party_settings('Manual Party')
    assert settings['party_name'] == 'Manual Party'
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
