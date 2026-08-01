"""
Tests for default tag seeding and 0.00 total checkout edge cases.
"""
import pytest
import os
import sqlite3

from app.database.connection import PartyDatabase, _get_party_db_path, PARTY_DB_DIR


def test_default_tags_seeded_on_new_db(client):
    """Test that a new party DB gets default tags seeded via auto-creation."""
    db_name = 'tags_test_party'

    # Login as admin (this triggers _ensure_party_db_exists which seeds default products + tags)
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    # Trigger product loading which uses PartyDatabase (DB auto-created here)
    resp = client.get(f'/api/products/?db={db_name}')
    assert resp.status_code == 200

    # Now check tags
    resp = client.get(f'/api/products/tags?db={db_name}')
    tags = resp.get_json()
    tag_names = [t['name'] for t in tags]
    assert 'Hot' in tag_names
    assert 'Popular' in tag_names

    # Cleanup
    db_path = _get_party_db_path(db_name)
    for ext in ['', '-wal', '-shm']:
        p = db_path + ext
        if os.path.exists(p):
            os.remove(p)


def test_default_tags_assigned_to_default_products(client):
    """Test that default products have tags assigned."""
    db_name = 'tags_assign_test_party'

    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    # Trigger DB init by loading sections
    resp = client.get(f'/api/products/?db={db_name}')
    assert resp.status_code == 200

    # Products in the Hot Drinks subsection should have the 'Hot' tag
    sections = resp.get_json()
    hot_drinks = None
    for section in sections:
        for sub in section.get('subsections', []):
            if sub['name'] == 'Hot Drinks':
                hot_drinks = sub['id']
                break

    assert hot_drinks is not None

    resp = client.get(f'/api/products/{hot_drinks}/products?db={db_name}')
    products = resp.get_json()
    assert len(products) > 0

    # At least some products should have the 'Hot' tag
    products_with_tags = [p for p in products if p.get('tags') and len(p['tags']) > 0]
    assert len(products_with_tags) > 0
    tag_names = set()
    for p in products_with_tags:
        for t in p['tags']:
            tag_names.add(t['name'])
    assert 'Hot' in tag_names

    # Cleanup
    db_path = _get_party_db_path(db_name)
    for ext in ['', '-wal', '-shm']:
        p = db_path + ext
        if os.path.exists(p):
            os.remove(p)


def test_zero_total_checkout_card(clean_db, client):
    """Test checkout with 0.00 total (after 100% discount) works for card."""
    db_name = clean_db

    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    # Setup product
    client.post(f'/api/products/sections?db={db_name}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db_name}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db_name}', json={
        'name': 'Free Coffee', 'price': 5.00, 'section_id': 1, 'subsection_id': 1
    })

    # Add to cart
    client.post(f'/api/cart/add?db={db_name}', json={'product_id': 1, 'quantity': 1})

    # Apply 100% discount to make total 0.00
    resp = client.post(f'/api/cart/discount?db={db_name}', json={'type': 'percentage', 'value': 100})
    assert resp.get_json()['total'] == 0.0

    # Checkout with card
    resp = client.post(f'/api/orders/checkout?db={db_name}', json={'payment_method': 'card'})
    assert resp.status_code == 201
    assert resp.get_json()['total'] == 0.0


def test_zero_total_checkout_cash(clean_db, client):
    """Test checkout with 0.00 total for cash payment."""
    db_name = clean_db

    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    # Setup product
    client.post(f'/api/products/sections?db={db_name}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db_name}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db_name}', json={
        'name': 'Free Coffee', 'price': 5.00, 'section_id': 1, 'subsection_id': 1
    })

    # Add to cart and apply 100% discount
    client.post(f'/api/cart/add?db={db_name}', json={'product_id': 1, 'quantity': 1})
    client.post(f'/api/cart/discount?db={db_name}', json={'type': 'percentage', 'value': 100})

    # Checkout with cash, tendered=0
    resp = client.post(f'/api/orders/checkout?db={db_name}', json={
        'payment_method': 'cash', 'tendered': 0
    })
    assert resp.status_code == 201
    assert resp.get_json()['total'] == 0.0

    # Verify order exists in recent orders
    resp = client.get(f'/api/orders/recent?db={db_name}')
    orders = resp.get_json()
    assert len(orders) == 1
    assert orders[0]['total'] == 0.0