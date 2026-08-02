"""Integration tests for product search/filter and bulk edit features."""
import pytest


@pytest.fixture
def admin_client(clean_db, client):
    """A client logged in as admin."""
    client.post(f'/api/auth/login/admin?db={clean_db}', json={'pin': '0000'})
    return client


def test_search_by_name(admin_client, clean_db):
    """Test searching products by name."""
    db = clean_db
    # Create a section > subsection > product
    admin_client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    admin_client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    admin_client.post(f'/api/products/products?db={db}', json={
        'name': 'Large Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1
    })
    admin_client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 1.50, 'section_id': 1, 'subsection_id': 1
    })

    # Search for "Coffee"
    resp = admin_client.get(f'/api/products/search?db={db}&search=Coffee')
    assert resp.status_code == 200
    products = resp.get_json()
    names = [p['name'] for p in products]
    assert 'Large Coffee' in names
    assert 'Small Coffee' in names


def test_search_by_sku(admin_client, clean_db):
    """Test searching products by SKU."""
    db = clean_db
    admin_client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    admin_client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    admin_client.post(f'/api/products/products?db={db}', json={
        'name': 'Latte', 'price': 3.00, 'section_id': 1, 'subsection_id': 1, 'sku': 'SKU-001'
    })

    resp = admin_client.get(f'/api/products/search?db={db}&search=SKU-001')
    assert resp.status_code == 200
    products = resp.get_json()
    assert len(products) == 1
    assert products[0]['name'] == 'Latte'


def test_filter_by_section(admin_client, clean_db):
    """Test filtering products by section."""
    db = clean_db
    admin_client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    admin_client.post(f'/api/products/sections?db={db}', json={'name': 'Food'})
    admin_client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    admin_client.post(f'/api/products/subsections?db={db}', json={'section_id': 2, 'name': 'Snacks'})
    admin_client.post(f'/api/products/products?db={db}', json={
        'name': 'Coffee', 'price': 1.50, 'section_id': 1, 'subsection_id': 1
    })
    admin_client.post(f'/api/products/products?db={db}', json={
        'name': 'Chips', 'price': 2.00, 'section_id': 2, 'subsection_id': 2
    })

    resp = admin_client.get(f'/api/products/search?db={db}&section_id=1')
    products = resp.get_json()
    assert len(products) == 1
    assert products[0]['name'] == 'Coffee'


def test_filter_by_subsection(admin_client, clean_db):
    """Test filtering products by subsection."""
    db = clean_db
    admin_client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    admin_client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Hot'})
    admin_client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Cold'})
    admin_client.post(f'/api/products/products?db={db}', json={
        'name': 'Coffee', 'price': 1.50, 'section_id': 1, 'subsection_id': 1
    })
    admin_client.post(f'/api/products/products?db={db}', json={
        'name': 'Soda', 'price': 1.00, 'section_id': 1, 'subsection_id': 2
    })

    resp = admin_client.get(f'/api/products/search?db={db}&subsection_id=2')
    products = resp.get_json()
    assert len(products) == 1
    assert products[0]['name'] == 'Soda'


def test_filter_by_tag(admin_client, clean_db):
    """Test filtering products by tag — products must have ALL specified tags."""
    db = clean_db
    admin_client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    admin_client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    admin_client.post(f'/api/products/products?db={db}', json={
        'name': 'Coffee', 'price': 1.50, 'section_id': 1, 'subsection_id': 1
    })
    admin_client.post(f'/api/products/products?db={db}', json={
        'name': 'Tea', 'price': 1.00, 'section_id': 1, 'subsection_id': 1
    })

    # Create two tags and assign both to Coffee only
    resp = admin_client.post(f'/api/products/tags?db={db}', json={'name': 'Hot', 'color': '#e74c3c'})
    tag1 = resp.get_json()['id']
    resp = admin_client.post(f'/api/products/tags?db={db}', json={'name': 'Popular', 'color': '#27ae60'})
    tag2 = resp.get_json()['id']

    admin_client.post(f'/api/products/1/tags?db={db}', json={'tag_id': tag1})
    admin_client.post(f'/api/products/1/tags?db={db}', json={'tag_id': tag2})
    admin_client.post(f'/api/products/2/tags?db={db}', json={'tag_id': tag1})

    # Filter by tag1 only → both Coffee and Tea
    resp = admin_client.get(f'/api/products/search?db={db}&tag_ids={tag1}')
    products = resp.get_json()
    names = [p['name'] for p in products]
    assert 'Coffee' in names
    assert 'Tea' in names

    # Filter by both tags → only Coffee
    resp = admin_client.get(f'/api/products/search?db={db}&tag_ids={tag1},{tag2}')
    products = resp.get_json()
    assert len(products) == 1
    assert products[0]['name'] == 'Coffee'


def test_filter_by_active_status(admin_client, clean_db):
    """Test filtering by active/inactive status."""
    db = clean_db
    admin_client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    admin_client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    admin_client.post(f'/api/products/products?db={db}', json={
        'name': 'Coffee', 'price': 1.50, 'section_id': 1, 'subsection_id': 1
    })

    # Set product inactive
    resp = admin_client.put(f'/api/products/products/1/status?db={db}', json={'is_active': False})
    assert resp.status_code == 200

    # Search active only → should be empty
    resp = admin_client.get(f'/api/products/search?db={db}&is_active=true')
    assert resp.status_code == 200
    assert len(resp.get_json()) == 0

    # Search inactive only → should have 1
    resp = admin_client.get(f'/api/products/search?db={db}&is_active=false')
    assert resp.status_code == 200
    assert len(resp.get_json()) == 1


def test_bulk_update_price(admin_client, clean_db):
    """Test bulk updating product prices."""
    db = clean_db
    admin_client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    admin_client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    admin_client.post(f'/api/products/products?db={db}', json={
        'name': 'Coffee1', 'price': 1.00, 'section_id': 1, 'subsection_id': 1
    })
    admin_client.post(f'/api/products/products?db={db}', json={
        'name': 'Coffee2', 'price': 2.00, 'section_id': 1, 'subsection_id': 1
    })

    resp = admin_client.post(f'/api/products/products/bulk?db={db}', json={
        'product_ids': [1, 2],
        'updates': {'price': 5.00}
    })
    assert resp.status_code == 200
    assert resp.get_json()['count'] == 2

    # Verify prices updated
    resp = admin_client.get(f'/api/products/search?db={db}')
    for p in resp.get_json():
        assert p['price'] == 5.00


def test_bulk_update_tags(admin_client, clean_db):
    """Test bulk assigning tags to products."""
    db = clean_db
    admin_client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    admin_client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    admin_client.post(f'/api/products/products?db={db}', json={
        'name': 'Coffee1', 'price': 1.00, 'section_id': 1, 'subsection_id': 1
    })
    admin_client.post(f'/api/products/products?db={db}', json={
        'name': 'Coffee2', 'price': 2.00, 'section_id': 1, 'subsection_id': 1
    })

    resp = admin_client.post(f'/api/products/tags?db={db}', json={'name': 'Hot', 'color': '#e74c3c'})
    tag_id = resp.get_json()['id']

    # Bulk assign tag to both products
    resp = admin_client.post(f'/api/products/products/bulk?db={db}', json={
        'product_ids': [1, 2],
        'updates': {'tags': [tag_id]}
    })
    assert resp.status_code == 200

    # Verify both products have the tag
    resp = admin_client.get(f'/api/products/search?db={db}')
    for p in resp.get_json():
        tag_names = [t['name'] for t in p['tags']]
        assert 'Hot' in tag_names


def test_bulk_update_is_active(admin_client, clean_db):
    """Test bulk toggling active status."""
    db = clean_db
    admin_client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    admin_client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    admin_client.post(f'/api/products/products?db={db}', json={
        'name': 'Coffee1', 'price': 1.00, 'section_id': 1, 'subsection_id': 1
    })
    admin_client.post(f'/api/products/products?db={db}', json={
        'name': 'Coffee2', 'price': 2.00, 'section_id': 1, 'subsection_id': 1
    })

    resp = admin_client.post(f'/api/products/products/bulk?db={db}', json={
        'product_ids': [1, 2],
        'updates': {'is_active': False}
    })
    assert resp.status_code == 200

    # Verify both are inactive
    resp = admin_client.get(f'/api/products/search?db={db}&is_active=false')
    assert len(resp.get_json()) == 2


def test_bulk_update_requires_admin(client, clean_db):
    """Test that bulk update requires admin privileges."""
    db = clean_db
    # Login as operator (not admin)
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    from flask import session
    with client.session_transaction() as sess:
        sess['operator_id'] = 2
        sess['operator_name'] = 'operator'
        sess['operator_role'] = 'operator'

    resp = client.post(f'/api/products/products/bulk?db={db}', json={
        'product_ids': [1],
        'updates': {'price': 5.00}
    })
    assert resp.status_code == 403


def test_search_returns_tags(admin_client, clean_db):
    """Test that search results include product tags."""
    db = clean_db
    admin_client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    admin_client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    admin_client.post(f'/api/products/products?db={db}', json={
        'name': 'Coffee', 'price': 1.50, 'section_id': 1, 'subsection_id': 1
    })
    resp = admin_client.post(f'/api/products/tags?db={db}', json={'name': 'Hot', 'color': '#e74c3c'})
    tag_id = resp.get_json()['id']
    admin_client.post(f'/api/products/1/tags?db={db}', json={'tag_id': tag_id})

    resp = admin_client.get(f'/api/products/search?db={db}&search=Coffee')
    products = resp.get_json()
    assert len(products) == 1
    assert len(products[0]['tags']) == 1
    assert products[0]['tags'][0]['name'] == 'Hot'
    assert products[0]['tags'][0]['color'] == '#e74c3c'


def test_search_empty_results(admin_client, clean_db):
    """Test search with no matching results."""
    db = clean_db
    resp = admin_client.get(f'/api/products/search?db={db}&search=nonexistent')
    assert resp.status_code == 200
    assert resp.get_json() == []
