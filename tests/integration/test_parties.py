"""
Tests for party creation from templates.
"""
import os

import pytest

from app.utils.config import PARTY_DB_DIR
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


def test_duplicate_party_excludes_sales_history(clean_db, client):
    """Test that duplicating a party copies catalog data but NOT sales history."""
    db_name = clean_db

    # Login as admin
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    # Create a section, subsection, and product
    client.post(f'/api/products/sections?db={db_name}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db_name}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db_name}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1
    })

    # Create an order directly via the service layer (sales history)
    from app.services.order_service import checkout_order
    order_id, _, _, _ = checkout_order(
        db_name,
        [{'product_id': 1, 'quantity': 2, 'unit_price': 2.50}],
        'cash', 1, 0.0, None
    )
    assert order_id is not None

    # Verify the original party has 1 order
    from app.services.order_service import get_recent_orders
    original_orders = get_recent_orders(db_name, 50)
    assert len(original_orders) >= 1

    # Duplicate the party
    resp = client.post(f'/api/parties/{db_name}/duplicate', json={'name': 'Copy'})
    assert resp.status_code == 200
    new_db = resp.get_json().get('new_name', 'Copy')

    # Verify the duplicated party has the same products
    resp = client.get(f'/api/products/?db={new_db}')
    sections = resp.get_json()
    assert len(sections) == 1
    assert sections[0]['name'] == 'Drinks'

    # Verify NO orders were copied (sales history excluded)
    duplicate_orders = get_recent_orders(new_db, 50)
    assert len(duplicate_orders) == 0, "Sales history should NOT be copied during duplication"


def test_create_empty_refuses_live_party(clean_db, client):
    """Creating a same-named party while it is LIVE is refused, not overwritten."""
    from app.database.connection import PartyDatabase

    db_name = clean_db
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    held = PartyDatabase(db_name)
    held.__enter__()  # deliberately unbalanced: connection stays open
    try:
        resp = client.post('/api/parties/create-empty', json={'name': db_name})
    finally:
        held.__exit__(None, None, None)

    assert resp.status_code == 400
    assert 'in use' in resp.get_json()['error']

    # Once released, the same creation goes through normally
    resp = client.post('/api/parties/create-empty', json={'name': db_name})
    assert resp.status_code == 201


def test_duplicate_is_safe_on_name_edge_cases(clean_db, client):
    """Duplicate refuses self-duplication and live-destination collisions."""
    from app.database.connection import PartyDatabase

    db_name = clean_db
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    # Self-duplication would delete the files and re-copy from a dead path
    resp = client.post(f'/api/parties/{db_name}/duplicate', json={'name': db_name})
    assert resp.status_code == 400
    assert 'onto itself' in resp.get_json()['error']
    assert client.get(f'/api/products/?db={db_name}').status_code == 200

    # Two names that sanitize to the same file: 'Rollo!' / 'Rollo?'
    resp = client.post('/api/parties/create-empty', json={'name': 'Rollo!'})
    assert resp.status_code == 201
    dst = resp.get_json()['db_name']
    assert dst == 'Rollo'

    held = PartyDatabase(dst)
    held.__enter__()  # deliberately unbalanced: connection stays open
    try:
        resp = client.post(f'/api/parties/{db_name}/duplicate',
                           json={'name': 'Rollo?'})
    finally:
        held.__exit__(None, None, None)
    assert resp.status_code == 400
    assert 'in use' in resp.get_json()['error']

    # Tidy: conftest only cleans test_party (this file leaks 'Weekend_Party'
    # by convention too) — remove the second party's files
    from app.services.party_service import _remove_db_files
    _remove_db_files(os.path.join(PARTY_DB_DIR, f'{dst}.db'))
