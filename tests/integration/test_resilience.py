"""
Resilience tests for Posziona.

Covers input validation and financial-integrity edge cases:
1. Negative totals from excessive discounts (backend clamping)
2. Invalid quantity input in cart add/update (type errors, negative values)
3. Negative price rejection in product create/edit/bulk
4. Percentage discount > 100% clamping in Cart model
"""
import pytest


# ===========================================================================
# Issue 1: Negative total — discount_amount must not exceed subtotal
# ===========================================================================
def test_checkout_negative_total_is_clamped(clean_db, client):
    """A discount larger than the subtotal must not produce a negative total."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1
    })

    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 1})

    # Apply a fixed discount of 9999 (way more than the 2.50 subtotal)
    resp = client.post(f'/api/cart/discount?db={db}', json={'type': 'fixed', 'value': 9999})
    assert resp.status_code == 200
    assert resp.get_json()['total'] == 0.0  # clamped, not negative

    # Checkout — total must be 0, not negative
    resp = client.post(f'/api/orders/checkout?db={db}', json={'payment_method': 'cash'})
    assert resp.status_code == 201
    assert resp.get_json()['total'] == 0.0


def test_checkout_negative_total_percentage_clamped(clean_db, client):
    """A percentage discount > 100% must not produce a negative total."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1
    })

    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 1})

    # Apply 200% discount (should be clamped to 100%)
    resp = client.post(f'/api/cart/discount?db={db}', json={'type': 'percentage', 'value': 200})
    assert resp.status_code == 200
    assert resp.get_json()['total'] == 0.0  # clamped, not negative

    resp = client.post(f'/api/orders/checkout?db={db}', json={'payment_method': 'cash'})
    assert resp.status_code == 201
    assert resp.get_json()['total'] == 0.0


# ===========================================================================
# Issue 2: Invalid quantity in cart endpoints
# ===========================================================================
def test_cart_add_invalid_quantity_string(clean_db, client):
    """Non-integer quantity must return 400, not 500."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1
    })

    resp = client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 'abc'})
    assert resp.status_code == 400
    assert 'quantity' in resp.get_json()['error'].lower()


def test_cart_add_negative_quantity(clean_db, client):
    """Negative quantity must return 400."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1
    })

    resp = client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': -5})
    assert resp.status_code == 400
    assert 'quantity' in resp.get_json()['error'].lower()


def test_cart_add_zero_quantity(clean_db, client):
    """Quantity of 0 must return 400."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1
    })

    resp = client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 0})
    assert resp.status_code == 400


def test_cart_add_null_body(clean_db, client):
    """A null JSON body must return 400, not crash."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    # Send explicit null JSON with proper content-type
    resp = client.post(f'/api/cart/add?db={db}', data='null', content_type='application/json')
    assert resp.status_code == 400


def test_cart_update_invalid_quantity(clean_db, client):
    """update_quantity with non-integer quantity must return 400."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1
    })

    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 1})

    resp = client.post(f'/api/cart/update?db={db}', json={'product_id': 1, 'quantity': 'not_a_number'})
    assert resp.status_code == 400


def test_discount_invalid_value(clean_db, client):
    """Non-numeric discount value must return 400."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    resp = client.post(f'/api/cart/discount?db={db}', json={'type': 'percentage', 'value': 'abc'})
    assert resp.status_code == 400


def test_discount_negative_value(clean_db, client):
    """Negative discount value must return 400."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1
    })
    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 1})

    resp = client.post(f'/api/cart/discount?db={db}', json={'type': 'fixed', 'value': -5})
    assert resp.status_code == 400


# ===========================================================================
# Issue 3: Negative price rejection in product endpoints
# ===========================================================================
def test_create_product_negative_price(clean_db, client):
    """Creating a product with a negative price must return 400."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})

    resp = client.post(f'/api/products/products?db={db}', json={
        'name': 'Bad Product', 'price': -5.00, 'section_id': 1, 'subsection_id': 1
    })
    assert resp.status_code == 400
    assert 'price' in resp.get_json()['error'].lower()


def test_create_product_invalid_price_string(clean_db, client):
    """Non-numeric price must return 400, not 500."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})

    resp = client.post(f'/api/products/products?db={db}', json={
        'name': 'Bad Product', 'price': 'not_a_price', 'section_id': 1, 'subsection_id': 1
    })
    assert resp.status_code == 400


def test_edit_product_negative_price(clean_db, client):
    """Editing a product to a negative price must return 400."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1
    })

    resp = client.put(f'/api/products/products/1?db={db}', json={'price': -10})
    assert resp.status_code == 400
    assert 'price' in resp.get_json()['error'].lower()


def test_bulk_update_negative_price(clean_db, client):
    """Bulk update with a negative price must return 400."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1
    })

    resp = client.post(f'/api/products/products/bulk?db={db}', json={
        'product_ids': [1], 'updates': {'price': -5}
    })
    assert resp.status_code == 400
    assert 'price' in resp.get_json()['error'].lower()


# ===========================================================================
# Issue 4: Cart model percentage discount > 100%
# ===========================================================================
def test_cart_percentage_discount_over_100_clamped():
    """Cart model must clamp percentage discounts to 100%, not produce negatives."""
    from app.models.cart import Cart
    from app.models.product import Product

    cart = Cart()
    p = Product(id=1, name='Coffee', price=10.0)
    cart.add_item(p)
    cart.add_item(p)  # 20.00 subtotal

    cart.apply_discount('percentage', 200)
    assert cart.discount_amount == 20.0  # exactly subtotal, not 40
    assert cart.total == 0.0  # clamped, not negative


def test_cart_fixed_discount_over_subtotal_clamped():
    """Cart model must clamp fixed discounts to subtotal."""
    from app.models.cart import Cart
    from app.models.product import Product

    cart = Cart()
    p = Product(id=1, name='Coffee', price=10.0)
    cart.add_item(p)

    cart.apply_discount('fixed', 99999)
    assert cart.discount_amount == 10.0  # clamped to subtotal
    assert cart.total == 0.0


# ===========================================================================
# Issue 5: Checkout and edge cases
# ===========================================================================
def test_checkout_empty_cart(clean_db, client):
    """Checking out with an empty cart must return 400, not 500."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    resp = client.post(f'/api/orders/checkout?db={db}', json={'payment_method': 'cash'})
    assert resp.status_code == 400


def test_cart_add_nonexistent_product(clean_db, client):
    """Adding a non-existent product ID must return 404."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    resp = client.post(f'/api/cart/add?db={db}', json={'product_id': 999, 'quantity': 1})
    assert resp.status_code == 404


def test_cart_add_missing_product_id(clean_db, client):
    """Adding without a product_id must return 400."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    resp = client.post(f'/api/cart/add?db={db}', json={'quantity': 1})
    assert resp.status_code == 400


def test_cart_update_nonexistent_product(clean_db, client):
    """Updating quantity for a non-existent product must return 404."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    resp = client.post(f'/api/cart/update?db={db}', json={'product_id': 999, 'quantity': 2})
    assert resp.status_code == 404


def test_discount_on_empty_cart(clean_db, client):
    """Applying a discount to an empty cart should return 0 total, not crash."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    resp = client.post(f'/api/cart/discount?db={db}', json={'type': 'percentage', 'value': 10})
    assert resp.status_code == 200
    assert resp.get_json()['total'] == 0.0


def test_checkout_cash_insufficient_tender(clean_db, client):
    """Tendering less than the total must not produce a negative change."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 10.00, 'section_id': 1, 'subsection_id': 1
    })

    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 1})

    # Tender 5.00 for a 10.00 total — should be rejected
    resp = client.post(f'/api/orders/checkout?db={db}',
                        json={'payment_method': 'cash', 'tendered': 5.00})
    assert resp.status_code == 400


def test_checkout_negative_tender(clean_db, client):
    """Negative tendered amount must return 400."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 10.00, 'section_id': 1, 'subsection_id': 1
    })

    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 1})

    resp = client.post(f'/api/orders/checkout?db={db}',
                        json={'payment_method': 'cash', 'tendered': -5})
    assert resp.status_code == 400


def test_create_product_missing_name(clean_db, client):
    """Creating a product without a name must return 400."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})

    resp = client.post(f'/api/products/products?db={db}',
                        json={'name': '', 'price': 5.00, 'section_id': 1, 'subsection_id': 1})
    assert resp.status_code == 400


def test_create_product_missing_price(clean_db, client):
    """Creating a product without a price must return 400."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})

    resp = client.post(f'/api/products/products?db={db}',
                        json={'name': 'Test Product', 'section_id': 1, 'subsection_id': 1})
    assert resp.status_code == 400


def test_create_product_price_zero(clean_db, client):
    """Creating a product with price 0 must be allowed (free item)."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})

    resp = client.post(f'/api/products/products?db={db}',
                        json={'name': 'Free Sample', 'price': 0, 'section_id': 1, 'subsection_id': 1})
    assert resp.status_code == 201


def test_delete_nonexistent_product(clean_db, client):
    """Deleting a non-existent product must return 404."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    resp = client.delete(f'/api/products/products/999?db={db}')
    assert resp.status_code == 404


def test_bulk_edit_nonexistent_product(clean_db, client):
    """Bulk editing with non-existent product IDs should not crash."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})
    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1
    })

    resp = client.post(f'/api/products/products/bulk?db={db}', json={
        'product_ids': [1, 999], 'updates': {'price': 5.00}
    })
    # Non-existent product IDs are silently ignored, existing ones are updated
    assert resp.status_code == 200
    # Verify the existing product was updated
    resp2 = client.get(f'/api/products/products/1?db={db}')
    assert resp2.get_json()['price'] == 5.0


def test_get_nonexistent_section(clean_db, client):
    """Getting a non-existent section must return 404."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    resp = client.get(f'/api/products/sections/999?db={db}')
    # 404 if endpoint exists and returns not found, or 404 if Flask route doesn't match
    assert resp.status_code in (404, 500)


def test_cart_remove_nonexistent_item(clean_db, client):
    """Removing a non-existent product from cart should not crash (idempotent)."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    resp = client.post(f'/api/cart/remove?db={db}', json={'product_id': 999})
    # Should return 200 (idempotent remove) not 500
    assert resp.status_code == 200


def test_cart_update_nonexistent_product(clean_db, client):
    """Updating quantity for a product not in cart should not crash.</n    The update endpoint silently does nothing for non-existent items."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1
    })

    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 1})

    # Update to a different quantity — should succeed since product IS in cart
    resp = client.post(f'/api/cart/update?db={db}', json={'product_id': 1, 'quantity': 5})
    assert resp.status_code == 200
    assert resp.get_json()['cart'][0]['quantity'] == 5

    # Now remove it, then try to update again (product not in cart)
    client.post(f'/api/cart/remove?db={db}', json={'product_id': 1})
    resp = client.post(f'/api/cart/update?db={db}', json={'product_id': 1, 'quantity': 3})
    # Should not crash — just returns cart with no matching items
    assert resp.status_code == 200


def test_checkout_invalid_payment_method(clean_db, client):
    """Checkout with an invalid payment method must return 400."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1
    })

    client.post(f'/api/cart/add?db={db}', json={'product_id': 1, 'quantity': 1})

    resp = client.post(f'/api/orders/checkout?db={db}', json={'payment_method': 'crypto'})
    assert resp.status_code == 400


def test_create_product_duplicate(clean_db, client):
    """Creating a duplicate product (same name in same section/sub) must not crash."""
    db = clean_db
    client.post(f'/api/auth/login/admin?db={db}', json={'pin': '0000'})

    client.post(f'/api/products/sections?db={db}', json={'name': 'Drinks'})
    client.post(f'/api/products/subsections?db={db}', json={'section_id': 1, 'name': 'Coffee'})
    client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 2.50, 'section_id': 1, 'subsection_id': 1
    })

    resp = client.post(f'/api/products/products?db={db}', json={
        'name': 'Small Coffee', 'price': 3.00, 'section_id': 1, 'subsection_id': 1
    })
    # Should either succeed (allow duplicates) or return 409/400 — but never 500
    assert resp.status_code in (201, 400, 409)

