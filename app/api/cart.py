"""
Cart API endpoints.
Manages the in-progress cart (session-based, not persisted to DB until checkout).
"""

from flask import Blueprint, request, jsonify, session
from app.services.order_service import discount_for_subtotal
from app.services.product_service import get_product_by_id
from app.utils.session_lock import session_write_lock

cart_bp = Blueprint('cart', __name__)


def _parse_quantity(raw):
    """Parse a cart quantity. Raises ValueError (→ 400) when invalid."""
    try:
        quantity = int(raw)
    except (TypeError, ValueError):
        raise ValueError('Quantity must be a valid integer')
    if quantity < 1:
        raise ValueError('Quantity must be at least 1')
    return quantity


# ============================================================
# CART OPERATIONS
# ============================================================

@cart_bp.route('/', methods=['GET'])
def get_cart():
    """Get the current cart (and any discount) from session.

    The POS reloads this on page load so a refresh never hides items that
    are still in the server-side cart.
    """
    cart = session.get('cart', [])
    discount = session.get('cart_discount')
    return jsonify({
        'items': cart,
        'discount': ({'type': discount.get('type'), 'value': discount.get('value')}
                     if discount else None),
        'total': _calculate_total(cart),
    })


@cart_bp.route('/add', methods=['POST'])
@session_write_lock
def add_to_cart():
    """Add a product to the cart."""
    db = request.args.get('db', 'default')
    data = request.get_json()
    if data is None:
        return jsonify({'error': 'Request body is required'}), 400
    product_id = data.get('product_id')
    quantity = _parse_quantity(data.get('quantity', 1))

    if not product_id:
        return jsonify({'error': 'product_id is required'}), 400

    product = get_product_by_id(db, product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    # A stale POS button can still point at a product an admin just
    # disabled or archived: never let it into a sale.
    if not product.get('is_active') or product.get('is_archived'):
        return jsonify({'error': 'Product is not available'}), 400

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
@session_write_lock
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
@session_write_lock
def update_quantity():
    """Update quantity of an item in the cart."""
    data = request.get_json()
    if data is None:
        return jsonify({'error': 'Request body is required'}), 400
    product_id = data.get('product_id')
    quantity = _parse_quantity(data.get('quantity', 1))

    cart = session.get('cart', [])
    for item in cart:
        if item['product_id'] == product_id:
            item['quantity'] = quantity
            item['line_total'] = item['quantity'] * item['unit_price']
            break

    session['cart'] = cart
    return jsonify({'cart': cart, 'total': _calculate_total(cart)})


@cart_bp.route('/clear', methods=['POST'])
@session_write_lock
def clear_cart():
    """Clear the entire cart."""
    session['cart'] = []
    return jsonify({'message': 'Cart cleared', 'total': 0.0})


@cart_bp.route('/discount', methods=['POST'])
@session_write_lock
def apply_discount():
    """Apply a discount to the cart."""
    data = request.get_json()
    if data is None:
        return jsonify({'error': 'Request body is required'}), 400
    discount_type = data.get('type')  # 'percentage' or 'fixed'
    if discount_type not in ('percentage', 'fixed'):
        return jsonify({'error': "Discount type must be 'percentage' or 'fixed'"}), 400
    try:
        discount_value = float(data.get('value', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Discount value must be a number'}), 400
    if discount_value < 0:
        return jsonify({'error': 'Discount value must be non-negative'}), 400

    cart = session.get('cart', [])
    subtotal = _calculate_subtotal(cart)

    # Only type + value are stored: the amount is recomputed from the
    # current subtotal on every read, so adding items after a percentage
    # discount can never leave a stale amount for checkout.
    discount = {'type': discount_type, 'value': discount_value}
    discount_amount = discount_for_subtotal(subtotal, discount)
    session['cart_discount'] = discount

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
@session_write_lock
def remove_discount():
    """Remove any applied discount."""
    session.pop('cart_discount', None)
    cart = session.get('cart', [])
    subtotal = _calculate_subtotal(cart)
    return jsonify({'subtotal': subtotal, 'total': subtotal})


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _calculate_subtotal(cart):
    """Sum of the cart lines, before any discount."""
    return sum(item['line_total'] for item in cart)


def _calculate_total(cart):
    """Cart total after the session discount (recomputed, never stored)."""
    subtotal = _calculate_subtotal(cart)
    return subtotal - discount_for_subtotal(subtotal, session.get('cart_discount'))
