"""
Order API endpoints.
Handles checkout, order history, and order details.
"""

from flask import Blueprint, request, jsonify, session
from app.services.order_service import (
    create_order,
    record_payment,
    get_recent_orders,
    get_order_details,
    get_sales_summary,
    get_items_sold_summary,
)
from app.services.settings_service import get_default_payment_method
from app.utils.logger import get_logger

logger = get_logger('api.orders')

orders_bp = Blueprint('orders', __name__)


# ============================================================
# CHECKOUT
# ============================================================

@orders_bp.route('/checkout', methods=['POST'])
def checkout():
    """
    Finalize the cart into an order.
    If no payment method is provided and a default exists, uses the default.
    """
    db = request.args.get('db', 'default')
    data = request.get_json() or {}

    cart = session.get('cart', [])
    if not cart:
        return jsonify({'error': 'Cart is empty'}), 400

    # Get operator from session (set during login)
    operator_id = session.get('operator_id')
    if not operator_id:
        return jsonify({'error': 'Operator not logged in'}), 403

    # Determine payment method
    payment_method = data.get('payment_method')
    if not payment_method:
        default_method = get_default_payment_method(db)
        if default_method:
            payment_method = default_method
        else:
            return jsonify({'error': 'Payment method required'}), 400

    # Get discount info from session
    cart_discount = session.get('cart_discount', {})
    discount_amount = cart_discount.get('amount', 0.0)
    discount_type = cart_discount.get('type')

    # Build cart items for order creation
    cart_items = []
    for item in cart:
        cart_items.append({
            'product_id': item['product_id'],
            'quantity': item['quantity'],
            'unit_price': item['unit_price']
        })

    try:
        # Create the order
        order_id = create_order(
            db, cart_items, payment_method, operator_id,
            discount_amount, discount_type
        )

        # Record payment if provided
        total = sum(item['line_total'] for item in cart) - discount_amount
        tendered = data.get('tendered')

        if tendered is not None:
            record_payment(db, order_id, payment_method, total, tendered)

        # Clear cart and discount
        session['cart'] = []
        session.pop('cart_discount', None)

        return jsonify({
            'message': 'Order created',
            'order_id': order_id,
            'total': total,
            'payment_method': payment_method
        }), 201

    except Exception as e:
        logger.error(f"Checkout error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================
# ORDER HISTORY (Admin)
# ============================================================

@orders_bp.route('/recent', methods=['GET'])
def recent_orders():
    """Get recent orders (admin only)."""
    db = request.args.get('db', 'default')
    limit = int(request.args.get('limit', 50))
    return jsonify(get_recent_orders(db, limit))


@orders_bp.route('/<int:order_id>', methods=['GET'])
def order_details(order_id):
    """Get full details of an order (admin only)."""
    db = request.args.get('db', 'default')
    order = get_order_details(db, order_id)
    if not order:
        return jsonify({'error': 'Order not found'}), 404
    return jsonify(order)


# ============================================================
# REPORTS (Admin)
# ============================================================

@orders_bp.route('/report/summary', methods=['GET'])
def sales_report():
    """Get sales summary."""
    db = request.args.get('db', 'default')
    return jsonify(get_sales_summary(db))


@orders_bp.route('/report/items', methods=['GET'])
def items_report():
    """Get recap of all items sold."""
    db = request.args.get('db', 'default')
    return jsonify(get_items_sold_summary(db))
