"""
Schema-drift tests: an old database missing tables/columns heals itself on open.
"""
import os
import sqlite3

from app.utils.config import PARTY_DB_DIR


def _cleanup(basename):
    from app.database import connection as conn_mod
    from app.database.connection import _get_party_db_path
    try:
        path = _get_party_db_path(basename)
    except ValueError:
        return
    for ext in ('', '-wal', '-shm', '-journal'):
        p = path + ext
        if os.path.exists(p):
            os.remove(p)
    with conn_mod._checked_paths_lock:
        conn_mod._checked_paths.discard(path)


def test_missing_tables_and_columns_are_recreated():
    from app.database.connection import PartyDatabase, _get_party_db_path

    db_name = 'drift_heal_test'
    _cleanup(db_name)
    try:
        with PartyDatabase(db_name):
            pass
        path = _get_party_db_path(db_name)

        # Simulate an old database: drop whole tables + one column
        conn = sqlite3.connect(path)
        conn.execute("DROP TABLE tags")
        conn.execute("DROP TABLE idempotency_keys")
        try:
            conn.execute("ALTER TABLE products DROP COLUMN stock_count")
            dropped = True
        except sqlite3.Error:
            dropped = False  # ancient SQLite — table-drop assertions still count
        conn.commit()
        conn.close()

        # Reopen → everything healed, app queries work
        with PartyDatabase(db_name) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            assert 'tags' in tables
            assert 'idempotency_keys' in tables
            if dropped:
                cols = {r[1] for r in conn.execute("PRAGMA table_info(products)")}
                assert 'stock_count' in cols
            conn.execute("SELECT * FROM sections").fetchall()
            conn.execute("SELECT * FROM products").fetchall()
    finally:
        _cleanup(db_name)
