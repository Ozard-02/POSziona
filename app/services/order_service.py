"""
Order service for Posziona.
Handles cart management, checkout, orders, and payments.
"""

import sqlite3

from app.database.connection import PartyDatabase
from app.utils.logger import get_logger

logger = get_logger('services.orders')


# ============================================================
# ORDER CREATION & CHECKOUT
# ============================================================

def checkout_order(db_name, cart_items, payment_method, operator_id,
                   discount_amount=0.0, discount_type=None,
                   tendered=None, idempotency_key=None):
    """
    Atomic, retry-safe checkout.

    Order + order_items + stock decrement + payment are written in a
    SINGLE transaction: either the whole sale lands or nothing does.
    A mid-checkout crash or error can therefore never leave a partial
    order behind, and a client retry can never duplicate the sale.

    Retry safety comes from `idempotency_key` (one UUID per sale,
    generated client-side): if the key was already used, the original
    order is returned unchanged (replayed=True) instead of creating
    a second order.

    Returns (order_id, total, updated_stocks, replayed).
    Raises ValueError for client errors (empty cart, bad tendered).
    """
    if not cart_items:
        raise ValueError('Cart is empty')

    with PartyDatabase(db_name) as conn:
        # Opportunistic prune of old idempotency keys (older than 7 days)
        # so the table stays tiny on low-end machines.
        conn.execute(
            "DELETE FROM idempotency_keys WHERE created_at < datetime('now', '-7 days')"
        )

        if idempotency_key:
            row = conn.execute(
                """SELECT o.id, o.total FROM idempotency_keys k
                   JOIN orders o ON o.id = k.order_id
                   WHERE k.key = ?""",
                (idempotency_key,)
            ).fetchone()
            if row:
                logger.info(f"Checkout replayed: key={idempotency_key}, order={row['id']}")
                return row['id'], row['total'], {}, True

        # Calculate totals server-side (single source of truth — the
        # payment record must match the order, never the session cart)
        subtotal = sum(item['quantity'] * item['unit_price'] for item in cart_items)
        # Clamp discount to subtotal to prevent negative totals from
        # direct API calls that bypass the frontend's Math.min guard
        discount_amount = min(discount_amount, subtotal)
        total = subtotal - discount_amount

        # Validate tendered before writing anything
        change_due = None
        if tendered is not None:
            if tendered < 0:
                raise ValueError('Tendered amount must be non-negative')
            if payment_method == 'cash' and tendered < total:
                raise ValueError('Tendered amount must be at least the total due')
            if payment_method == 'cash':
                change_due = tendered - total

        # Create order
        conn.execute(
            """INSERT INTO orders (subtotal, discount_amount, discount_type, total,
               payment_method, operator_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (subtotal, discount_amount, discount_type, total, payment_method, operator_id)
        )
        order_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Create order items and decrement stock
        for item in cart_items:
            conn.execute(
                """INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                   VALUES (?, ?, ?, ?)""",
                (order_id, item['product_id'], item['quantity'], item['unit_price'])
            )

            # Atomically decrement stock. Uses MAX(0, ...) to clamp at 0
            # rather than going negative. The WHERE clause ensures this is
            # atomic — concurrent checkouts for the same product will each
            # update the row sequentially (SQLite serializes via WAL + busy_timeout),
            # so stock_count - quantity is always computed against the latest value.
            conn.execute(
                """UPDATE products
                   SET stock_count = CASE
                       WHEN stock_count IS NOT NULL THEN MAX(0, stock_count - ?)
                       ELSE NULL
                   END
                   WHERE id = ?""",
                (item['quantity'], item['product_id'])
            )

        # Record payment in the SAME transaction (an order must never
        # exist without its payment, or vice versa)
        if tendered is not None:
            conn.execute(
                """INSERT INTO payments (order_id, method, amount, tendered, change_due)
                   VALUES (?, ?, ?, ?, ?)""",
                (order_id, payment_method, total, tendered, change_due)
            )

        # Remember the idempotency key only after everything succeeded.
        # A concurrent retry may have committed the same key first —
        # treat the duplicate-key error as a replay, not a failure.
        if idempotency_key:
            try:
                conn.execute(
                    "INSERT INTO idempotency_keys (key, order_id) VALUES (?, ?)",
                    (idempotency_key, order_id)
                )
            except sqlite3.IntegrityError:
                conn.rollback()
                row = conn.execute(
                    """SELECT o.id, o.total FROM idempotency_keys k
                       JOIN orders o ON o.id = k.order_id
                       WHERE k.key = ?""",
                    (idempotency_key,)
                ).fetchone()
                if row:
                    logger.info(f"Checkout raced, replaying: key={idempotency_key}")
                    return row['id'], row['total'], {}, True
                raise

        # Fetch updated stock counts for broadcast
        updated_stocks = {}
        for item in cart_items:
            row = conn.execute(
                "SELECT stock_count FROM products WHERE id = ?", (item['product_id'],)
            ).fetchone()
            if row:
                updated_stocks[item['product_id']] = row['stock_count']

        conn.commit()
        logger.info(f"Order created: id={order_id}, total={total}, items={len(cart_items)}")
        return order_id, total, updated_stocks, False


def create_order(db_name, cart_items, payment_method, operator_id,
                 discount_amount=0.0, discount_type=None):
    """
    Finalize a cart into a completed order (no payment recorded).
    Kept for backwards compatibility — new code should use checkout_order().
    Returns (order_id, updated_stocks).
    """
    order_id, _total, updated_stocks, _replayed = checkout_order(
        db_name, cart_items, payment_method, operator_id,
        discount_amount, discount_type
    )
    return order_id, updated_stocks


def record_payment(db_name, order_id, method, amount, tendered=None):
    """Record a payment for an order."""
    change_due = None
    if tendered is not None and method == 'cash':
        if tendered < amount:
            raise ValueError('Tendered amount must be at least the total due')
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


def get_items_sold_summary(db_name, date_filter=None):
    """Get a recap of all items sold with quantities and totals.
    Optionally filter by a specific date (YYYY-MM-DD).
    """
    with PartyDatabase(db_name) as conn:
        date_clause = "WHERE DATE(o.timestamp) = ?" if date_filter else ""
        params = [date_filter] if date_filter else []

        rows = conn.execute(
            f"""
            SELECT
                p.id as product_id,
                p.name as product_name,
                p.sku,
                s.name as section,
                ss.name as subsection,
                SUM(oi.quantity) as total_quantity,
                SUM(oi.quantity * oi.unit_price) as total_amount,
                p.price as current_price,
                p.stock_count,
                p.is_active
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.id
            JOIN products p ON oi.product_id = p.id
            JOIN sections s ON p.section_id = s.id
            JOIN subsections ss ON p.subsection_id = ss.id
            {date_clause}
            GROUP BY p.id
            ORDER BY total_amount DESC
            """,
            params
        ).fetchall()

        return [dict(row) for row in rows]


def get_recent_orders(db_name, limit=50, date_filter=None):
    """Get recent orders for admin review. Optionally filter by date."""
    with PartyDatabase(db_name) as conn:
        date_clause = "WHERE DATE(o.timestamp) = ?" if date_filter else ""
        date_param = [date_filter] if date_filter else []

        rows = conn.execute(
            f"""
            SELECT
                o.id, o.timestamp, o.total, o.payment_method,
                o.subtotal, o.discount_amount,
                op.name as operator_name
            FROM orders o
            LEFT JOIN operators op ON o.operator_id = op.id
            {date_clause}
            ORDER BY o.timestamp DESC
            LIMIT ?
            """,
            date_param + [limit]
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


# ============================================================
# ORDER MANAGEMENT
# ============================================================

def delete_order_by_id(db_name, order_id):
    """Delete or revoke an order.
    Restores stock for products that have a stock count.
    Returns True if the order was found and deleted, False otherwise.
    """
    with PartyDatabase(db_name) as conn:
        # Check if order exists
        order = conn.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ).fetchone()

        if not order:
            return False

        # Restore stock for products with stock_count
        conn.execute(
            """
            UPDATE products
            SET stock_count = CASE
                WHEN stock_count IS NOT NULL THEN stock_count + (
                    SELECT oi.quantity
                    FROM order_items oi
                    WHERE oi.product_id = products.id
                      AND oi.order_id = ?
                )
                ELSE NULL
            END
            WHERE id IN (
                SELECT product_id FROM order_items WHERE order_id = ?
            )
            """,
            (order_id, order_id)
        )

        # Delete related records first (payments, order_items), then the order
        conn.execute("DELETE FROM payments WHERE order_id = ?", (order_id,))
        conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))

        conn.commit()
        logger.info(f"Order deleted: id={order_id}")
        return True
