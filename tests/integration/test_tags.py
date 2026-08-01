"""
Integration tests for tag management API endpoints.
"""
import pytest


def test_create_and_list_tags(clean_db, client):
    """Test creating tags and listing them."""
    db_name = clean_db

    # Login as admin
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    # Create a tag with styling rules
    resp = client.post(f'/api/products/tags?db={db_name}', json={
        'name': 'Hot',
        'color': '#e74c3c',
        'bg_color': '#ffecec',
        'text_color': '#c0392b'
    })
    assert resp.status_code == 201

    # Create another tag
    resp = client.post(f'/api/products/tags?db={db_name}', json={
        'name': 'Alcohol',
        'color': '#9b59b6'
    })
    assert resp.status_code == 201

    # List tags — ordered by name alphabetically
    resp = client.get(f'/api/products/tags?db={db_name}')
    assert resp.status_code == 200
    tags = resp.get_json()
    assert len(tags) == 2
    tag_names = [t['name'] for t in tags]
    assert 'Hot' in tag_names
    assert 'Alcohol' in tag_names
    hot_tag = next(t for t in tags if t['name'] == 'Hot')
    assert hot_tag['color'] == '#e74c3c'
    assert hot_tag['bg_color'] == '#ffecec'
    assert hot_tag['text_color'] == '#c0392b'
    alc_tag = next(t for t in tags if t['name'] == 'Alcohol')
    assert alc_tag['color'] == '#9b59b6'


def test_update_tag_styling(clean_db, client):
    """Test updating a tag's background color (the styling rule)."""
    db_name = clean_db
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    # Create tag
    resp = client.post(f'/api/products/tags?db={db_name}', json={
        'name': 'Featured',
        'color': '#f39c12'
    })
    tag_id = resp.get_json()['id']

    # Update with bg_color and text_color
    resp = client.put(f'/api/products/tags/{tag_id}?db={db_name}', json={
        'bg_color': '#fff3cd',
        'text_color': '#856404'
    })
    assert resp.status_code == 200

    # Verify
    resp = client.get(f'/api/products/tags/{tag_id}?db={db_name}')
    tag = resp.get_json()
    assert tag['bg_color'] == '#fff3cd'
    assert tag['text_color'] == '#856404'


def test_assign_and_remove_tags_on_product(clean_db, client):
    """Test assigning tags to a product and removing them."""
    db_name = clean_db
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    # Create section > subsection > product
    client.post(f'/api/products/sections?db={db_name}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db_name}', json={'section_id': 1, 'name': 'Hot'})
    resp = client.post(f'/api/products/products?db={db_name}', json={
        'name': 'Hot Coffee', 'price': 2.50,
        'section_id': 1, 'subsection_id': 1
    })
    product_id = resp.get_json()['id']

    # Create a tag
    resp = client.post(f'/api/products/tags?db={db_name}', json={
        'name': 'Hot',
        'color': '#e74c3c',
        'bg_color': '#ffecec'
    })
    tag_id = resp.get_json()['id']

    # Assign tag to product
    resp = client.post(f'/api/products/{product_id}/tags?db={db_name}', json={'tag_id': tag_id})
    assert resp.status_code == 200

    # Get product tags
    resp = client.get(f'/api/products/{product_id}/tags?db={db_name}')
    tags = resp.get_json()
    assert len(tags) == 1
    assert tags[0]['name'] == 'Hot'
    assert tags[0]['bg_color'] == '#ffecec'

    # Remove tag from product
    resp = client.delete(f'/api/products/{product_id}/tags/{tag_id}?db={db_name}')
    assert resp.status_code == 200

    # Verify removed
    resp = client.get(f'/api/products/{product_id}/tags?db={db_name}')
    tags = resp.get_json()
    assert len(tags) == 0


def test_product_includes_tags_in_listing(clean_db, client):
    """Test that products returned by subsection include their tags."""
    db_name = clean_db
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    # Create section > subsection > product
    client.post(f'/api/products/sections?db={db_name}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db_name}', json={'section_id': 1, 'name': 'Hot'})
    client.post(f'/api/products/products?db={db_name}', json={
        'name': 'Espresso', 'price': 1.50,
        'section_id': 1, 'subsection_id': 1
    })

    # Create a tag and assign it
    resp = client.post(f'/api/products/tags?db={db_name}', json={
        'name': 'Strong', 'color': '#e67e22', 'bg_color': '#fef5e7'
    })
    tag_id = resp.get_json()['id']
    client.post(f'/api/products/1/tags?db={db_name}', json={'tag_id': tag_id})

    # Get products in subsection — should include tags
    resp = client.get(f'/api/products/1/products?db={db_name}')
    products = resp.get_json()
    assert len(products) == 1
    assert len(products[0]['tags']) == 1
    assert products[0]['tags'][0]['name'] == 'Strong'
    assert products[0]['tags'][0]['bg_color'] == '#fef5e7'


def test_create_tag_requires_admin(clean_db, client):
    """Test that tag creation requires admin role."""
    db_name = clean_db
    # Don't login as admin — login as regular operator
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    # Clear session to simulate non-admin
    from flask import session
    with client.session_transaction() as sess:
        sess['operator_id'] = 2
        sess['operator_name'] = 'operator'
        sess['operator_role'] = 'operator'

    resp = client.post(f'/api/products/tags?db={db_name}', json={'name': 'Test'})
    assert resp.status_code == 403


def test_create_tag_without_auth(clean_db, client):
    """Test that tag creation without admin session with require_admin=0 works."""
    db_name = clean_db

    resp = client.post(
        f'/api/products/tags?db={db_name}&require_admin=0',
        json={'name': 'NoAuth'}
    )
    assert resp.status_code == 201

    resp = client.get(f'/api/products/tags?db={db_name}')
    tags = resp.get_json()
    assert len(tags) == 1
    assert tags[0]['name'] == 'NoAuth'


def test_delete_tag_removes_from_products(clean_db, client):
    """Test that deleting a tag removes it from all products."""
    db_name = clean_db
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})

    # Setup product
    client.post(f'/api/products/sections?db={db_name}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db_name}', json={'section_id': 1, 'name': 'Hot'})
    client.post(f'/api/products/products?db={db_name}', json={
        'name': 'Coffee', 'price': 2.00,
        'section_id': 1, 'subsection_id': 1
    })

    # Create and assign tag
    resp = client.post(f'/api/products/tags?db={db_name}', json={'name': 'Caffeinated'})
    tag_id = resp.get_json()['id']
    client.post(f'/api/products/1/tags?db={db_name}', json={'tag_id': tag_id})

    # Delete tag
    resp = client.delete(f'/api/products/tags/{tag_id}?db={db_name}')
    assert resp.status_code == 200

    # Verify product no longer has the tag
    resp = client.get(f'/api/products/1/tags?db={db_name}')
    assert resp.status_code == 200
    assert len(resp.get_json()) == 0
