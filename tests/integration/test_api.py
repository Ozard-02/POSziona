"""
Integration tests for API endpoints.
"""
import json
import pytest


def test_status_endpoint(client):
    """Test API status endpoint."""
    resp = client.get('/api/status')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert data['version'] == '0.1.0'


def test_login_page(client):
    """Test login page loads."""
    resp = client.get('/')
    assert resp.status_code == 200


def test_pos_page(client):
    """Test POS page loads."""
    resp = client.get('/pos')
    assert resp.status_code == 200


def test_admin_page(client):
    """Test admin page loads."""
    resp = client.get('/admin')
    assert resp.status_code == 200


def test_auth_status_not_logged_in(client):
    """Test auth status when not logged in."""
    resp = client.get('/api/auth/status?db=default')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['logged_in'] == False


def test_admin_login_and_auth(clean_db, client):
    """Test admin login flow."""
    db_name = clean_db
    
    # Login as admin
    resp = client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'operator' in data
    assert data['operator']['role'] == 'admin'
    
    # Check auth status
    resp = client.get(f'/api/auth/status?db={db_name}')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['logged_in'] == True
    assert data['operator']['role'] == 'admin'


def test_section_crud(clean_db, client):
    """Test section creation and retrieval."""
    db_name = clean_db
    
    # Login as admin first
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    
    # Create section
    resp = client.post(f'/api/products/sections?db={db_name}', json={'name': 'Drinks'})
    assert resp.status_code == 201
    assert 'created' in resp.get_json()['message']
    
    # Get sections
    resp = client.get(f'/api/products/?db={db_name}')
    assert resp.status_code == 200
    sections = resp.get_json()
    assert len(sections) == 1
    assert sections[0]['name'] == 'Drinks'


def test_full_pos_workflow(clean_db, client):
    """Test the complete POS workflow: sections → products → cart → checkout."""
    db_name = clean_db
    
    # Login as admin
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    
    # Create section > subsection
    client.post(f'/api/products/sections?db={db_name}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db_name}', json={'section_id': 1, 'name': 'Coffee'})
    
    # Create product
    resp = client.post(f'/api/products/products?db={db_name}', json={
        'name': 'Small Coffee', 'price': 2.50,
        'section_id': 1, 'subsection_id': 1
    })
    assert resp.status_code == 201
    
    # Get products
    resp = client.get(f'/api/products/1/products?db={db_name}')
    assert resp.status_code == 200
    products = resp.get_json()
    assert len(products) == 1
    assert products[0]['name'] == 'Small Coffee'
    assert products[0]['price'] == 2.50
    
    # Add to cart
    resp = client.post(f'/api/cart/add?db={db_name}', json={'product_id': 1, 'quantity': 2})
    assert resp.status_code == 200
    cart_data = resp.get_json()
    assert cart_data['total'] == 5.0
    
    # Update cart quantity
    resp = client.post(f'/api/cart/update?db={db_name}', json={'product_id': 1, 'quantity': 3})
    assert resp.status_code == 200
    assert resp.get_json()['total'] == 7.5
    
    # Apply discount
    resp = client.post(f'/api/cart/discount?db={db_name}', json={'type': 'percentage', 'value': 10})
    assert resp.status_code == 200
    assert resp.get_json()['total'] == 6.75
    
    # Checkout
    resp = client.post(f'/api/orders/checkout?db={db_name}', json={'payment_method': 'cash'})
    assert resp.status_code == 201
    order_data = resp.get_json()
    assert order_data['order_id'] is not None
    assert order_data['payment_method'] == 'cash'
    
    # Check sales summary
    resp = client.get(f'/api/orders/report/summary?db={db_name}')
    assert resp.status_code == 200
    summary = resp.get_json()
    assert summary['total_orders'] == 1
    assert summary['total_revenue'] > 0
    
    # Check items sold
    resp = client.get(f'/api/orders/report/items?db={db_name}')
    assert resp.status_code == 200
    items = resp.get_json()
    assert len(items) == 1
    assert items[0]['product_name'] == 'Small Coffee'
    assert items[0]['total_quantity'] == 3
    # Dashboard fields: price, stock, availability, product_id
    assert items[0]['product_id'] == 1
    assert items[0]['current_price'] == 2.50
    assert items[0]['stock_count'] is None  # unlimited
    assert items[0]['is_active'] == 1


def test_dashboard_item_availability_update(clean_db, client):
    """Test right-click context menu flow: toggle product availability from the items report."""
    db_name = clean_db

    # Setup: create product, checkout order so it appears in items report
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    client.post(f'/api/products/sections?db={db_name}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db_name}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db_name}', json={
        'name': 'Small Coffee', 'price': 2.50,
        'section_id': 1, 'subsection_id': 1
    })
    client.post(f'/api/cart/add?db={db_name}', json={'product_id': 1, 'quantity': 2})
    client.post(f'/api/orders/checkout?db={db_name}', json={'payment_method': 'cash'})

    # Item should be available
    resp = client.get(f'/api/orders/report/items?db={db_name}')
    assert resp.get_json()[0]['is_active'] == 1

    # Disable product via PUT (mirrors the right-click "Set Unavailable" action)
    resp = client.put(f'/api/products/products/1?db={db_name}', json={'is_active': 0})
    assert resp.status_code == 200

    # Now item should be unavailable
    resp = client.get(f'/api/orders/report/items?db={db_name}')
    assert resp.get_json()[0]['is_active'] == 0


def test_clear_cart(clean_db, client):
    """Test cart clearing."""
    db_name = clean_db
    
    # Setup: create product and add to cart
    client.post(f'/api/auth/login/admin?db={db_name}', json={'pin': '0000'})
    client.post(f'/api/products/sections?db={db_name}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db_name}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db_name}', json={
        'name': 'Small Coffee', 'price': 2.50,
        'section_id': 1, 'subsection_id': 1
    })
    client.post(f'/api/cart/add?db={db_name}', json={'product_id': 1, 'quantity': 1})
    
    # Clear cart
    resp = client.post(f'/api/cart/clear?db={db_name}', method='POST')
    assert resp.status_code == 200
    
    # Check cart is empty
    resp = client.get(f'/api/cart/?db={db_name}')
    assert resp.status_code == 200
    cart = resp.get_json()
    assert cart['total'] == 0.0
