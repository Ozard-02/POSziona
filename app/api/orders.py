"""
Order API endpoints.
Handles checkout, order history, and order details.
"""

from flask import Blueprint, request, jsonify, session, Response
from app.api.guard import require_admin
from app.services.order_service import (
    build_recap_csv,
    checkout_order,
    expected_cash_total,
    list_cash_counts,
    record_cash_count,
    get_recent_orders,
    get_order_details,
    get_sales_summary,
    get_items_sold_summary,
    delete_order_by_id,
)
from app.services.product_service import get_product_by_id
from app.services.settings_service import get_default_payment_method
from app.services.auth_service import log_audit_event
from app.utils.events import broadcast
from app.utils.logger import get_logger

logger = get_logger('api.orders')

orders_bp = Blueprint('orders', __name__)


def _parse_limit(raw, default=50, maximum=500):
    """Parse a ?limit= value defensively (garbage → ValueError → 400)."""
    try:
        limit = int(raw if raw is not None else default)
    except (TypeError, ValueError):
        raise ValueError(f'Invalid limit: {raw!r}')
    if limit < 1 or limit > maximum:
        raise ValueError(f'Limit must be between 1 and {maximum}')
    return limit


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

    # One idempotency key per sale (generated client-side). Retrying the
    # same sale with the same key returns the original order instead of
    # creating a duplicate — safe after network/server failures.
    idempotency_key = request.headers.get('X-Idempotency-Key') or data.get('idempotency_key')
    tendered = data.get('tendered')

    try:
        # Atomic checkout: order + items + stock + payment in ONE commit.
        # Either the whole sale lands or nothing does.
        order_id, total, updated_stocks, replayed = checkout_order(
            db, cart_items, payment_method, operator_id,
            discount_amount, discount_type,
            tendered=tendered, idempotency_key=idempotency_key
        )
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Checkout error: {e}")
        return jsonify({'error': 'Checkout failed, no sale was recorded. It is safe to retry.'}), 500

    # Best-effort live sync: broadcast failures must never fail the sale
    # (the order is already committed) nor trigger a client retry that
    # could confuse the operator. Retries are idempotent anyway.
    try:
        for product_id, stock_count in updated_stocks.items():
            product = get_product_by_id(db, product_id)
            broadcast('product_update', {
                'product_id': product_id,
                'db': db,
                'stock_count': stock_count,
                'is_active': 1 if (product and product.get('is_active')) else 0,
                'is_archived': 1 if (product and product.get('is_archived')) else 0
            })
    except Exception as e:
        logger.warning(f"Checkout broadcast failed (sale {order_id} is safe): {e}")

    # Clear cart and discount (also on replay — the retried sale already
    # owns these items, so keeping them would risk a double sale)
    session['cart'] = []
    session.pop('cart_discount', None)

    return jsonify({
        'message': 'Order created',
        'order_id': order_id,
        'total': total,
        'payment_method': payment_method,
        'replayed': replayed
    }), 201


# ============================================================
# ORDER HISTORY (Admin)
# ============================================================

@orders_bp.route('/recent', methods=['GET'])
def recent_orders():
    """Get recent orders (admin only)."""
    db = request.args.get('db', 'default')
    limit = _parse_limit(request.args.get('limit'))
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
@require_admin
def delete_order(order_id):
    """Delete or revoke an order (admin only).
    If the order has stock-counted products, stock is restored."""
    db = request.args.get('db', 'default')
    try:
        result = delete_order_by_id(db, order_id)
        if result:
            log_audit_event(
                db, 'order_voided',
                f'Order {order_id} revoked by admin', session.get('operator_id'))
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


@orders_bp.route('/log-receipt', methods=['POST'])
def log_receipt():
    """Log a recovery receipt to server logs (always saved, regardless of
    whether it is displayed to the user)."""
    data = request.get_json() or {}
    order_id = data.get('order_id')
    receipt_text = data.get('receipt', '')
    logger.info(f"Recovery receipt saved — order_id={order_id}\n{receipt_text}")
    return jsonify({'message': 'Receipt logged'}), 200


# ============================================================
# CASH COUNTS (till reconciliation, any logged-in operator)
# ============================================================
@orders_bp.route('/cash-counts', methods=['GET'])
def get_cash_counts():
    """Past till counts, newest first."""
    db = request.args.get('db', 'default')
    if not session.get('operator_id'):
        return jsonify({'error': 'Operator not logged in'}), 403
    return jsonify(list_cash_counts(db))


@orders_bp.route('/cash-counts/expected', methods=['GET'])
def get_expected_cash():
    """Cash sales total awaiting count. Optional ?date=YYYY-MM-DD."""
    db = request.args.get('db', 'default')
    if not session.get('operator_id'):
        return jsonify({'error': 'Operator not logged in'}), 403
    return jsonify({'expected_cash': expected_cash_total(db, request.args.get('date'))})


@orders_bp.route('/cash-counts', methods=['POST'])
def add_cash_count():
    """Close the till: body {"counted": <drawer cash>, "note"?, "date"?}."""
    db = request.args.get('db', 'default')
    operator_id = session.get('operator_id')
    if not operator_id:
        return jsonify({'error': 'Operator not logged in'}), 403
    data = request.get_json() or {}
    if 'counted' not in data:
        return jsonify({'error': 'counted is required'}), 400
    try:
        row = record_cash_count(db, data['counted'], operator_id,
                                data.get('note'), data.get('date'))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    log_audit_event(db, 'cash_count',
                    f"Till counted: expected {row['expected_cash']}, "
                    f"counted {row['counted_cash']}", operator_id)
    return jsonify(row), 201


# ============================================================
# EXPORT RECAP (Admin)
# ============================================================
@orders_bp.route('/report/export-csv', methods=['GET'])
def export_csv():
    """Export items sold summary as CSV.
    Optional ?date=YYYY-MM-DD for daily filter.
    """
    db = request.args.get('db', 'default')
    date_filter = request.args.get('date')

    csv_text = build_recap_csv(db, date_filter)
    return Response(
        csv_text,
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename="party-recap.csv"'
        }
    )
