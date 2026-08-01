"""
Order service for Party POS.
Handles cart management, checkout, orders, and payments.
"""

from app.database.connection import PartyDatabase
from app.utils.logger import get_logger

logger = get_logger('services.orders')


# ============================================================
# ORDER CREATION & CHECKOUT
# ============================================================

def create_order(db_name, cart_items, payment_method, operator_id,
                 discount_amount=0.0, discount_type=None):
    """
    Finalize a cart into a completed order.
    cart_items: list of dicts with product_id, quantity, unit_price
    Returns the order_id.
    """
    with PartyDatabase(db_name) as conn:
        # Calculate totals
        subtotal = sum(item['quantity'] * item['unit_price'] for item in cart_items)
        total = subtotal - discount_amount

        # Create order
        conn.execute(
            """INSERT INTO orders (subtotal, discount_amount, discount_type, total,
               payment_method, operator_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (subtotal, discount_amount, discount_type, total, payment_method, operator_id)
        )
        order_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Create order items
        for item in cart_items:
            conn.execute(
                """INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                   VALUES (?, ?, ?, ?)""",
                (order_id, item['product_id'], item['quantity'], item['unit_price'])
            )

            # Decrement stock if product has a stock count
            conn.execute(
                """UPDATE products
                   SET stock_count = CASE
                       WHEN stock_count IS NOT NULL THEN stock_count - ?
                       ELSE NULL
                   END
                   WHERE id = ?""",
                (item['quantity'], item['product_id'])
            )

        conn.commit()
        logger.info(f"Order created: id={order_id}, total={total}, items={len(cart_items)}")
        return order_id


def record_payment(db_name, order_id, method, amount, tendered=None):
    """Record a payment for an order."""
    change_due = None
    if tendered is not None and method == 'cash':
        change_due = tendered - amount

    with PartyDatabase(db_name) as conn:
        conn.execute(
            """INSERT INTO payments (order_id, method, amount, tendered, change_due)
               VALUES (?, ?, ?, ?, ?)""",
            (order_id, method, amount, tendered, change_due)
        )
        conn.commit()
        logger.info(f"Payment recorded: order={order_id}, method={method}, amount={amount}")


# ============================================================
# REPORTING QUERIES
# ============================================================

def get_sales_summary(db_name, date_filter=None):
    """Get basic sales summary for the session."""
    with PartyDatabase(db_name) as conn:
        where_clause = "WHERE DATE(timestamp) = ?" if date_filter else ""
        params = [date_filter] if date_filter else []

        result = conn.execute(
            f"""SELECT
                  COUNT(*) as total_orders,
                  COALESCE(SUM(total), 0) as total_revenue,
                  COALESCE(SUM(discount_amount), 0) as total_discounts
                FROM orders {where_clause}""",
            params
        ).fetchone()

        return dict(result) if result else {
            'total_orders': 0,
            'total_revenue': 0.0,
            'total_discounts': 0.0
        }


def get_items_sold_summary(db_name):
    """Get a recap of all items sold with quantities and totals."""
    with PartyDatabase(db_name) as conn:
        rows = conn.execute(
            """
            SELECT
                p.name as product_name,
                p.sku,
                s.name as section,
                ss.name as subsection,
                SUM(oi.quantity) as total_quantity,
                SUM(oi.quantity * oi.unit_price) as total_amount
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            JOIN sections s ON p.section_id = s.id
            JOIN subsections ss ON p.subsection_id = ss.id
            GROUP BY p.id
            ORDER BY total_amount DESC
            """
        ).fetchall()

        return [dict(row) for row in rows]


def get_recent_orders(db_name, limit=50):
    """Get recent orders for admin review."""
    with PartyDatabase(db_name) as conn:
        rows = conn.execute(
            """
            SELECT
                o.id, o.timestamp, o.total, o.payment_method,
                o.subtotal, o.discount_amount,
                op.name as operator_name
            FROM orders o
            LEFT JOIN operators op ON o.operator_id = op.id
            ORDER BY o.timestamp DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


def get_order_details(db_name, order_id):
    """Get full details of a single order."""
    with PartyDatabase(db_name) as conn:
        order = conn.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ).fetchone()

        if not order:
            return None

        items = conn.execute(
            """
            SELECT oi.*, p.name as product_name
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = ?
            """,
            (order_id,)
        ).fetchall()

        payments = conn.execute(
            "SELECT * FROM payments WHERE order_id = ?", (order_id,)
        ).fetchall()

        return {
            'order': dict(order),
            'items': [dict(item) for item in items],
            'payments': [dict(p) for p in payments]
        }
