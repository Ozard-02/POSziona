"""
Integration tests for tag management API endpoints.
"""
import pytest


def test_create_update_list_tags(clean_db, client):
    """Tags are created with styling, updated, and listed alphabetically."""
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
    tag_id = resp.get_json()['id']

    # Update its styling
    resp = client.put(f'/api/products/tags/{tag_id}?db={db_name}', json={
        'bg_color': '#fff3cd',
        'text_color': '#856404'
    })
    assert resp.status_code == 200

    # List tags — styling round-trips
    tags = client.get(f'/api/products/tags?db={db_name}').get_json()
    hot_tag = next(t for t in tags if t['name'] == 'Hot')
    assert hot_tag['color'] == '#e74c3c'
    assert hot_tag['bg_color'] == '#fff3cd'
    assert hot_tag['text_color'] == '#856404'


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


def test_tag_mutations_require_admin_session(clean_db, client):
    """Operators (and logged-out clients) get 403 on every tag mutation."""
    db_name = clean_db
    client.post(f'/api/auth/login?db={db_name}', json={'pin': '1234'})

    assert client.post(f'/api/products/tags?db={db_name}',
                       json={'name': 'Test'}).status_code == 403

    client.post(f'/api/auth/logout?db={db_name}')
    assert client.post(f'/api/products/tags?db={db_name}',
                       json={'name': 'Test'}).status_code == 403


def test_tag_mutations_reject_unauthenticated(clean_db, client):
    """Tag mutations require an admin session — no query-param bypass."""
    db_name = clean_db
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    client.post(f'/api/products/sections?db={db_name}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db_name}', json={'section_id': 1, 'name': 'Hot'})
    client.post(f'/api/products/products?db={db_name}', json={
        'name': 'Coffee', 'price': 2.00, 'section_id': 1, 'subsection_id': 1})
    tag_id = client.post(
        f'/api/products/tags?db={db_name}', json={'name': 'Strong'}).get_json()['id']
    client.post(f'/api/auth/logout?db={db_name}')

    # None of these may succeed without an admin session, even with require_admin=0.
    assert client.post(
        f'/api/products/tags?db={db_name}&require_admin=0',
        json={'name': 'NoAuth'}).status_code == 403
    assert client.post(
        f'/api/products/1/tags?db={db_name}&require_admin=0',
        json={'tag_id': tag_id}).status_code == 403
    assert client.delete(
        f'/api/products/1/tags/{tag_id}?db={db_name}&require_admin=0').status_code == 403
    assert client.put(
        f'/api/products/1/tags?db={db_name}&require_admin=0',
        json={'tags': []}).status_code == 403


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
