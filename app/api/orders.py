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
    delete_order_by_id,
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

    # Validate payment method
    valid_methods = ['cash', 'card', 'wallet', 'tab']
    if payment_method not in valid_methods:
        return jsonify({'error': f'Invalid payment method. Must be one of: {", ".join(valid_methods)}'}), 400

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
            if tendered < 0:
                return jsonify({'error': 'Tendered amount must be non-negative'}), 400
            if payment_method == 'cash' and tendered < total:
                return jsonify({'error': 'Tendered amount must be at least the total due'}), 400

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
# ORDER MANAGEMENT (Admin)
# ============================================================

@orders_bp.route('/<int:order_id>', methods=['DELETE'])
def delete_order(order_id):
    """Delete or revoke an order (admin only).
    If the order has stock-counted products, stock is restored."""
    db = request.args.get('db', 'default')
    if session.get('operator_role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    try:
        result = delete_order_by_id(db, order_id)
        if result:
            return jsonify({'message': f'Order {order_id} revoked'})
        else:
            return jsonify({'error': 'Order not found'}), 404
    except Exception as e:
        logger.error(f"Order deletion error: {e}")
        return jsonify({'error': str(e)}), 500

@orders_bp.route('/report/summary', methods=['GET'])
def sales_report():
    """Get sales summary. Optional ?date=YYYY-MM-DD for daily filter."""
    db = request.args.get('db', 'default')
    date_filter = request.args.get('date')
    return jsonify(get_sales_summary(db, date_filter))


@orders_bp.route('/report/items', methods=['GET'])
def items_report():
    """Get recap of all items sold. Optional ?date=YYYY-MM-DD for daily filter."""
    db = request.args.get('db', 'default')
    date_filter = request.args.get('date')
    return jsonify(get_items_sold_summary(db, date_filter))


@orders_bp.route('/report/recent', methods=['GET'])
def recent_orders_report():
    """Get recent orders for the report view. Optional ?date=YYYY-MM-DD."""
    db = request.args.get('db', 'default')
    date_filter = request.args.get('date')
    limit = int(request.args.get('limit', 50))
    return jsonify(get_recent_orders(db, limit, date_filter))


@orders_bp.route('/log-receipt', methods=['POST'])
def log_receipt():
    """Log a recovery receipt to server logs (always saved, regardless of
    whether it is displayed to the user)."""
    db = request.args.get('db', 'default')
    data = request.get_json() or {}
    order_id = data.get('order_id')
    receipt_text = data.get('receipt', '')
    logger.info(f"Recovery receipt saved — order_id={order_id}\n{receipt_text}")
    return jsonify({'message': 'Receipt logged'}), 200
