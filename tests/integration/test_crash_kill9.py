"""
Real crash test: SIGKILL a process looping checkouts, then verify the DB.

No inference from transaction boundaries — actually kill -9 mid-write and
assert WAL recovery leaves a healthy DB with zero partial orders (every
order has items + a matching payment).
"""
import os
import signal
import sqlite3
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WORKER = """
import sys, time
sys.path.insert(0, '.')
from app.database.connection import PartyDatabase
from app.services.order_service import checkout_order

# Seed one product (unlimited stock keeps the math exact)
with PartyDatabase('kill9_test') as conn:
    conn.execute("INSERT OR IGNORE INTO sections (id, name) VALUES (1, 'S')")
    conn.execute("INSERT OR IGNORE INTO subsections (id, name, section_id) VALUES (1, 'SS', 1)")
    conn.execute("INSERT OR IGNORE INTO products (id, name, price, section_id, subsection_id) VALUES (1, 'P', 2.5, 1, 1)")
    conn.execute("INSERT OR IGNORE INTO operators (id, name, pin_hash, role, is_active) VALUES (1, 'op', 'x', 'operator', 1)")
    conn.commit()

i = 0
while True:
    checkout_order(
        'kill9_test',
        [{'product_id': 1, 'quantity': 1, 'unit_price': 2.50}],
        'cash', 1, tendered=2.50, idempotency_key=f'kill9-{i}')
    i += 1
"""


def test_kill9_mid_checkout_recovers_cleanly():
    from app.database.connection import _get_party_db_path

    # Fresh victim DB
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..', '..',
        'app', 'data', 'parties', 'kill9_test.db')
    path = os.path.normpath(path)
    for ext in ('', '-wal', '-shm', '-journal'):
        if os.path.exists(path + ext):
            os.remove(path + ext)

    proc = subprocess.Popen(
        [sys.executable, '-c', WORKER],
        cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(2.0)  # let it complete many checkouts (likely mid-one at kill)
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()

    # WAL recovery on next open + integrity must pass
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == 'ok'

        orders = conn.execute("SELECT id, total FROM orders").fetchall()
        assert len(orders) > 0, "worker should have completed sales before the kill"
        for oid, total in orders:
            items = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(quantity * unit_price), 0)"
                " FROM order_items WHERE order_id = ?", (oid,)).fetchone()
            assert items[0] >= 1, f"order {oid} has no items (partial order!)"
            pay = conn.execute(
                "SELECT amount FROM payments WHERE order_id = ?", (oid,)).fetchall()
            assert len(pay) == 1, f"order {oid} has {len(pay)} payments"
            assert pay[0][0] == total, f"order {oid} payment mismatch"
    finally:
        conn.close()
        for ext in ('', '-wal', '-shm', '-journal'):
            if os.path.exists(path + ext):
                os.remove(path + ext)
