"""
Crash-safety: accidental closures lose nothing and break nothing.

- Login cookie survives browser restarts (permanent session), so the
  operator and the unsent cart are still there after a client close.
- SIGTERM checkpoints WALs and exits 0 (systemd/docker/kill).
"""
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_login_cookie_survives_browser_restart(client, clean_db):
    """Session cookie carries Expires (not a browser-session cookie)."""
    r = client.post(f'/api/auth/login?db={clean_db}', json={'pin': '1234'})
    assert r.status_code == 200
    cookies = r.headers.getlist('Set-Cookie')
    assert cookies, 'login must set a session cookie'
    assert any('Expires=' in c for c in cookies), cookies


def test_checkpoint_all_truncates_wal():
    """Kill -9 a writer holding an open connection, then checkpoint.

    Mirrors the shutdown path: -wal left behind with no live connections
    must fold back into the main file, committed rows intact.
    """
    from app.database.connection import _get_party_db_path
    from app.services.backup_service import checkpoint_all

    path = os.path.normpath(_get_party_db_path('ckpt_test'))
    for ext in ('', '-wal', '-shm', '-journal'):
        if os.path.exists(path + ext):
            os.remove(path + ext)

    worker = (
        "import sys, time; sys.path.insert(0, '.');"
        "import sqlite3;"
        "from app.database.connection import _get_party_db_path;"
        "from app.database.schema import PARTY_SCHEMA;"
        "p = _get_party_db_path('ckpt_test');"
        "c = sqlite3.connect(p);"
        "c.execute('PRAGMA journal_mode=WAL');"
        "c.executescript(PARTY_SCHEMA);"
        "c.execute(\"INSERT INTO sections (name) VALUES ('CkptSurvivor')\");"
        "c.commit();"  # committed, connection kept open -> -wal lingers
        "time.sleep(30)"
    )
    proc = subprocess.Popen(
        [sys.executable, '-c', worker],
        cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(4.0)  # imports + one committed write, then idle with -wal
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    try:
        assert os.path.exists(path + '-wal'), 'kill should leave a -wal behind'
        checkpoint_all()
        assert not os.path.exists(path + '-wal'), 'WAL must fold back'
        conn = sqlite3.connect(path)
        try:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == 'ok'
            assert conn.execute(
                "SELECT COUNT(*) FROM sections WHERE name = 'CkptSurvivor'"
            ).fetchone()[0] == 1
        finally:
            conn.close()
    finally:
        for ext in ('', '-wal', '-shm', '-journal'):
            if os.path.exists(path + ext):
                os.remove(path + ext)


def _wait_port(port, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            sock = socket.create_connection(('127.0.0.1', port), timeout=1)
            sock.close()
            return True
        except OSError:
            time.sleep(0.3)
    return False


def test_sigterm_checkpoints_and_exits_zero(tmp_path):
    """Real server: SIGTERM → checkpoint message + exit code 0."""
    try:
        busy = socket.create_connection(('127.0.0.1', 5000), timeout=1)
        busy.close()
        pytest.skip('port 5000 busy (dev server running)')
    except OSError:
        pass
    data_dir = tmp_path / 'sigterm-data'
    env = dict(os.environ, POSZIONA_DATA_DIR=str(data_dir))
    proc = subprocess.Popen(
        [sys.executable, 'scripts/run_pos.py', '--mode', 'server'],
        cwd=REPO_ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        assert _wait_port(5000), 'server did not come up in time'
        proc.send_signal(signal.SIGTERM)
        out = proc.communicate(timeout=20)[0]
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    assert proc.returncode == 0, out
    assert 'Checkpoint' in out, out


# ===========================================================================
# SIGKILL mid-checkout (moved from test_crash_kill9.py — single crash file)
# ===========================================================================
WORKER_KILL9 = """
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
    """SIGKILL a checkout loop: WAL recovery, zero partial orders."""
    from app.database.connection import _get_party_db_path

    path = _get_party_db_path('kill9_test')
    for ext in ('', '-wal', '-shm', '-journal'):
        if os.path.exists(path + ext):
            os.remove(path + ext)

    proc = subprocess.Popen(
        [sys.executable, '-c', WORKER_KILL9],
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
