"""
Integration tests for API endpoints: the end-to-end workflow plus the few
contract pins that live nowhere else (server tag, logged-out auth shape).
"""


def test_server_name_setting_roundtrip(client, clean_db):
    """server_name survives the settings allowlist (device-global tag)."""
    r = client.post('/api/settings/?db=test_party', json={'server_name': 'CASSA-1'})
    assert r.status_code == 200
    data = client.get('/api/settings/?db=test_party').get_json()
    assert data['server_name'] == 'CASSA-1'


def test_auth_status_not_logged_in(client):
    """Logged-out auth status shape (only test pinning it; app.js relies on it)."""
    resp = client.get('/api/auth/status?db=default')
    assert resp.status_code == 200
    assert resp.get_json()['logged_in'] is False


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
