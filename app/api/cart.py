"""
Cart API endpoints.
Manages the in-progress cart (session-based, not persisted to DB until checkout).
"""

from flask import Blueprint, request, jsonify, session
from app.services.product_service import get_product_by_id
from app.services.settings_service import get_effective_settings
from app.utils.logger import get_logger

logger = get_logger('api.cart')

cart_bp = Blueprint('cart', __name__)


# ============================================================
# CART OPERATIONS
# ============================================================

@cart_bp.route('/', methods=['GET'])
def get_cart():
    """Get the current cart from session."""
    cart = session.get('cart', [])
    return jsonify({'items': cart, 'total': _calculate_total(cart)})


@cart_bp.route('/add', methods=['POST'])
def add_to_cart():
    """Add a product to the cart."""
    db = request.args.get('db', 'default')
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = int(data.get('quantity', 1))

    if not product_id:
        return jsonify({'error': 'product_id is required'}), 400

    product = get_product_by_id(db, product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    # Check stock
    if product.get('stock_count') is not None and product['stock_count'] <= 0:
        return jsonify({'error': 'Product out of stock'}), 400

    cart = session.get('cart', [])

    # Check if product already in cart
    existing = None
    for item in cart:
        if item['product_id'] == product_id:
            existing = item
            break

    if existing:
        existing['quantity'] += quantity
        existing['line_total'] = existing['quantity'] * existing['unit_price']
    else:
        cart.append({
            'product_id': product_id,
            'name': product['name'],
            'unit_price': product['price'],
            'quantity': quantity,
            'line_total': product['price'] * quantity
        })

    session['cart'] = cart
    return jsonify({'cart': cart, 'total': _calculate_total(cart)})


@cart_bp.route('/remove', methods=['POST'])
def remove_from_cart():
    """Remove a product from the cart."""
    data = request.get_json()
    product_id = data.get('product_id')

    if not product_id:
        return jsonify({'error': 'product_id is required'}), 400

    cart = session.get('cart', [])
    cart = [item for item in cart if item['product_id'] != product_id]
    session['cart'] = cart

    return jsonify({'cart': cart, 'total': _calculate_total(cart)})


@cart_bp.route('/update', methods=['POST'])
def update_quantity():
    """Update quantity of an item in the cart."""
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = int(data.get('quantity', 1))

    if quantity < 1:
        quantity = 1

    cart = session.get('cart', [])
    for item in cart:
        if item['product_id'] == product_id:
            item['quantity'] = quantity
            item['line_total'] = item['quantity'] * item['unit_price']
            break

    session['cart'] = cart
    return jsonify({'cart': cart, 'total': _calculate_total(cart)})


@cart_bp.route('/clear', methods=['POST'])
def clear_cart():
    """Clear the entire cart."""
    session['cart'] = []
    return jsonify({'message': 'Cart cleared', 'total': 0.0})


@cart_bp.route('/discount', methods=['POST'])
def apply_discount():
    """Apply a discount to the cart."""
    data = request.get_json()
    discount_type = data.get('type')  # 'percentage' or 'fixed'
    discount_value = float(data.get('value', 0))

    settings = get_effective_settings(request.args.get('db', 'default'))
    cart = session.get('cart', [])
    subtotal = _calculate_total(cart)

    discount_amount = 0
    if discount_type == 'percentage':
        discount_amount = subtotal * (discount_value / 100)
    elif discount_type == 'fixed':
        discount_amount = min(discount_value, subtotal)

    session['cart_discount'] = {
        'type': discount_type,
        'amount': discount_amount,
        'value': discount_value
    }

    total = subtotal - discount_amount
    return jsonify({
        'subtotal': subtotal,
        'discount_amount': discount_amount,
        'total': total
    })


@cart_bp.route('/remove-discount', methods=['POST'])
def remove_discount():
    """Remove any applied discount."""
    session.pop('cart_discount', None)
    cart = session.get('cart', [])
    subtotal = _calculate_total(cart)
    return jsonify({'subtotal': subtotal, 'total': subtotal})


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _calculate_total(cart):
    """Calculate total from cart items."""
    subtotal = sum(item['line_total'] for item in cart)
    discount = session.get('cart_discount', {}).get('amount', 0)
    return subtotal - discount
