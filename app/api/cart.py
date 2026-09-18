"""
Cart API endpoints.
Manages the in-progress cart (session-based, not persisted to DB until checkout).
"""

from flask import Blueprint, request, jsonify, session
from app.services.product_service import get_product_by_id
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
    if data is None:
        return jsonify({'error': 'Request body is required'}), 400
    product_id = data.get('product_id')
    quantity_raw = data.get('quantity', 1)
    try:
        quantity = int(quantity_raw)
    except (TypeError, ValueError):
        return jsonify({'error': 'Quantity must be a valid integer'}), 400
    if quantity < 1:
        return jsonify({'error': 'Quantity must be at least 1'}), 400

    if not product_id:
        return jsonify({'error': 'product_id is required'}), 400

    product = get_product_by_id(db, product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    # Check stock
    if product.get('stock_count') is not None and product['stock_count'] <= 0:
        return jsonify({'error': 'Product out of stock'}), 400

    cart = session.get('cart', [])
    # Check if product already in cart — if so, validate combined quantity against stock
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
    db = request.args.get('db', 'default')
    data = request.get_json()
    if data is None:
        return jsonify({'error': 'Request body is required'}), 400
    product_id = data.get('product_id')
    quantity_raw = data.get('quantity', 1)
    try:
        quantity = int(quantity_raw)
    except (TypeError, ValueError):
        return jsonify({'error': 'Quantity must be a valid integer'}), 400
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
    if data is None:
        return jsonify({'error': 'Request body is required'}), 400
    discount_type = data.get('type')  # 'percentage' or 'fixed'
    try:
        discount_value = float(data.get('value', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Discount value must be a number'}), 400
    if discount_value < 0:
        return jsonify({'error': 'Discount value must be non-negative'}), 400

    cart = session.get('cart', [])
    subtotal = _calculate_total(cart)

    discount_amount = 0
    if discount_type == 'percentage':
        # Clamp to 100% to prevent negative totals from direct API calls
        discount_amount = subtotal * (min(discount_value, 100) / 100)
    elif discount_type == 'fixed':
        discount_amount = min(discount_value, subtotal)

    session['cart_discount'] = {
        'type': discount_type,
        'amount': discount_amount,
        'value': discount_value
    }

    from app.services.auth_service import log_audit_event
    try:
        log_audit_event(
            request.args.get('db', 'default'),
            'discount_applied',
            f'{discount_type} discount value={discount_value} amount={discount_amount:.2f}',
            session.get('operator_id'))
    except Exception:
        # Audit must never break discounting
        pass

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
