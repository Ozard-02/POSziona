"""
Database connection management for Posziona.
"""

import sqlite3
import os
import threading
import time

from app.utils.config import PARTY_DB_DIR, TEMPLATES_DB
from app.utils.logger import get_logger
from app.database.schema import get_party_schema, get_templates_schema

logger = get_logger('database')

# Tracks party DB paths already integrity-checked in this process, so the
# (expensive) check runs once per DB per process lifetime, not per request.
_checked_paths = set()
_checked_paths_lock = threading.Lock()


def validate_db_name(db_name):
    """Reject database names that could escape the party directory.

    Raises ValueError on absolute paths, parent-directory references,
    path separators, null bytes, or empty/overlong names. All ?db=
    values and party file operations funnel through here.
    """
    if not isinstance(db_name, str) or not db_name.strip():
        raise ValueError('Invalid database name')
    name = db_name.strip()
    if len(name) > 100:
        raise ValueError('Database name too long')
    if os.path.isabs(name) or '..' in name or '/' in name or '\\' in name or '\x00' in name:
        raise ValueError(f'Invalid database name: {db_name!r}')
    return name


def _get_party_db_path(db_name):
    """Get the full path for a party database file."""
    db_name = validate_db_name(db_name)
    if not db_name.endswith('.db'):
        db_name = f"{db_name}.db"
    return os.path.join(PARTY_DB_DIR, db_name)


def _ensure_party_db_exists(db_name):
    """Ensure a party database exists, creating it from schema if not."""
    db_path = _get_party_db_path(db_name)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    if not os.path.exists(db_path):
        logger.info(f"Creating new party database: {db_path}")
        conn = sqlite3.connect(db_path)
        conn.executescript(get_party_schema())
        conn.commit()
        conn.close()
        _enable_wal(db_path)
        # Initialize default operators (admin + operator)
        _init_default_operators(db_path)
        # Seed default products/sections so the POS UI has visible content
        _init_default_products(db_path)
        # Set a default party name
        party_label = db_name.rsplit('.db', 1)[0] if db_name.endswith('.db') else db_name
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('party_name', party_label))
        conn.commit()
        conn.close()
    else:
        # Existing DB: verify integrity once per process, run migrations
        _verify_integrity_once(db_path)
        # Run migrations on existing databases
        _run_migrations(db_path)

    return db_path


def _verify_integrity_once(db_path):
    """Run PRAGMA integrity_check once per process for a party DB.

    On corruption the file is quarantined aside (.corrupt-<timestamp>)
    for forensics/restore, and a FRESH database is created so the party
    can keep selling. The data itself is recovered via the snapshot
    restore API. A corrupt DB fails every query anyway — refusing to
    start would halt all sales with no benefit.
    """
    with _checked_paths_lock:
        if db_path in _checked_paths:
            return
        _checked_paths.add(db_path)

    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            if row and row[0] == 'ok':
                return
            detail = row[0] if row else 'unknown'
        finally:
            conn.close()
    except Exception as e:
        detail = f'{type(e).__name__}: {e}'

    logger.critical(f"Database corruption detected in {db_path}: {detail}")
    quarantine = f"{db_path}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}"
    try:
        os.rename(db_path, quarantine)
        for ext in ['-wal', '-shm', '-journal']:
            p = db_path + ext
            if os.path.exists(p):
                os.rename(p, quarantine + ext)
    except OSError as e:
        logger.critical(f"Could not quarantine corrupt DB {db_path}: {e}")
        raise RuntimeError(f'Database file is corrupt and cannot be opened: {db_path}')

    logger.critical(f"Quarantined corrupt DB to {quarantine}; recreating fresh database")
    with _checked_paths_lock:
        _checked_paths.discard(db_path)
    # Recreate from scratch via the normal creation path
    _ensure_party_db_exists(os.path.basename(db_path).rsplit('.db', 1)[0])


def _run_migrations(db_path):
    """Run lightweight migrations on existing party databases."""
    conn = sqlite3.connect(db_path)
    try:
        # Add sort_order column to sections if it doesn't exist
        columns = [row[1] for row in conn.execute("PRAGMA table_info(sections)").fetchall()]
        if 'sort_order' not in columns:
            conn.execute("ALTER TABLE sections ADD COLUMN sort_order INTEGER DEFAULT 0")
            # Set initial sort_order based on existing row order
            rows = conn.execute("SELECT id FROM sections ORDER BY id").fetchall()
            for idx, (sid,) in enumerate(rows):
                conn.execute("UPDATE sections SET sort_order = ? WHERE id = ?", (idx, sid))
            conn.commit()
            logger.info(f"Migration: added sort_order to sections in {db_path}")
        # Idempotency keys table for retry-safe checkout (new DBs get it
        # via PARTY_SCHEMA; existing DBs need it created here)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS idempotency_keys (
                key TEXT PRIMARY KEY,
                order_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
            )"""
        )
        conn.commit()
    finally:
        conn.close()


def _init_default_operators(db_path):
    """Initialize default operators for a new party DB."""
    from app.services.auth_service import hash_pin
    admin_hash = hash_pin('0000')
    op_hash = hash_pin('1234')

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO operators (name, pin_hash, role, is_active) VALUES (?, ?, ?, 1)",
            ('admin', admin_hash, 'admin')
        )
        conn.execute(
            "INSERT OR IGNORE INTO operators (name, pin_hash, role, is_active) VALUES (?, ?, ?, 1)",
            ('operator', op_hash, 'operator')
        )
        conn.commit()
        logger.info(f"Initialized default operators for {db_path}")
    finally:
        conn.close()


def _init_default_products(db_path):
    """Initialize default products and sections for a new party DB.

    This ensures the POS interface has visible content on first launch
    instead of rendering an empty product grid.
    """
    conn = sqlite3.connect(db_path)
    try:
        # Check if any products exist — skip if DB already has data
        count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if count > 0:
            return

        # Default section: Drinks
        conn.execute("INSERT INTO sections (name) VALUES (?)", ('Drinks',))
        section_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Subsections under Drinks
        subs = ['Hot Drinks', 'Cold Drinks', 'Soft Drinks']
        sub_ids = {}
        for sub_name in subs:
            conn.execute(
                "INSERT INTO subsections (name, section_id) VALUES (?, ?)",
                (sub_name, section_id)
            )
            sub_ids[sub_name] = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Default tags — visible on POS product buttons
        default_tags = [
            ('Hot', '#e74c3c', '#fff3cd', '#721c24'),
            ('Alcohol', '#6f42c1', '#e8d8f7', '#38006b'),
            ('Popular', '#28a745', '#d4edda', '#152e15'),
            ('Seasonal', '#fd7e14', '#fff3cd', '#721c24'),
        ]
        tag_ids = {}
        for name, color, bg_color, text_color in default_tags:
            conn.execute(
                "INSERT INTO tags (name, color, bg_color, text_color) VALUES (?, ?, ?, ?)",
                (name, color, bg_color, text_color)
            )
            tag_ids[name] = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Default products for each subsection
        products = [
            # Hot Drinks (Hot tag)
            ('Small Coffee', 1.50, sub_ids['Hot Drinks'], 'Hot'),
            ('Large Coffee', 2.00, sub_ids['Hot Drinks'], 'Hot'),
            ('Tea', 1.20, sub_ids['Hot Drinks'], 'Hot'),
            ('Hot Chocolate', 2.50, sub_ids['Hot Drinks'], 'Hot'),
            # Cold Drinks
            ('Bottle Water', 1.00, sub_ids['Cold Drinks'], None),
            ('Soda Can', 1.50, sub_ids['Cold Drinks'], None),
            ('Iced Tea', 1.80, sub_ids['Cold Drinks'], None),
            # Soft Drinks
            ('Orange Juice', 2.00, sub_ids['Soft Drinks'], None),
            ('Lemonade', 1.80, sub_ids['Soft Drinks'], None),
        ]

        for name, price, sub_id, tag_name in products:
            conn.execute(
                "INSERT INTO products (name, price, sku, section_id, subsection_id) VALUES (?, ?, ?, ?, ?)",
                (name, price, None, section_id, sub_id)
            )
            pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            if tag_name and tag_name in tag_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO product_tags (product_id, tag_id) VALUES (?, ?)",
                    (pid, tag_ids[tag_name])
                )

        # Default section: Snacks
        conn.execute("INSERT INTO sections (name) VALUES (?)", ('Snacks',))
        snack_section_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute(
            "INSERT INTO subsections (name, section_id) VALUES (?, ?)",
            ('Savory', snack_section_id)
        )
        savory_sub_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute(
            "INSERT INTO subsections (name, section_id) VALUES (?, ?)",
            ('Sweet', snack_section_id)
        )
        sweet_sub_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        snack_products = [
            ('Chips', 1.50, savory_sub_id),
            ('Pretzels', 1.20, savory_sub_id),
            ('Cookie', 1.00, sweet_sub_id),
            ('Brownie', 1.80, sweet_sub_id),
        ]

        for name, price, sub_id in snack_products:
            conn.execute(
                "INSERT INTO products (name, price, sku, section_id, subsection_id) VALUES (?, ?, ?, ?, ?)",
                (name, price, None, snack_section_id, sub_id)
            )

        conn.commit()
        logger.info(f"Initialized default products for {db_path}")
    finally:
        conn.close()


def _enable_wal(db_path):
    """Enable WAL mode on an existing database."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA wal_autocheckpoint=1000')
        conn.commit()
    finally:
        conn.close()


class PartyDatabase:
    """Context manager for party database connections."""

    def __init__(self, db_name):
        self.db_name = db_name
        self.db_path = None
        self.conn = None

    def __enter__(self):
        self.db_path = _ensure_party_db_exists(self.db_name)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys = ON')
        self.conn.execute('PRAGMA busy_timeout = 10000')  # Wait up to 10s for locks
        self.conn.execute('PRAGMA journal_mode = WAL')
        self.conn.execute('PRAGMA synchronous = NORMAL')  # Faster WAL writes
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            try:
                if exc_type is not None:
                    # An exception is propagating — roll back the pending
                    # transaction explicitly so a failed unit of work never
                    # leaves partial writes behind. Do not mask the original
                    # exception.
                    self.conn.rollback()
            finally:
                self.conn.close()


class TemplatesDatabase:
    """Context manager for the shared templates database."""

    def __init__(self):
        self.db_path = TEMPLATES_DB
        self.conn = None
        self._ensure_exists()

    def _ensure_exists(self):
        """Ensure templates database exists with schema."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        if not os.path.exists(self.db_path):
            logger.info(f"Creating templates database: {self.db_path}")
            conn = sqlite3.connect(self.db_path)
            conn.executescript(get_templates_schema())
            conn.commit()
            conn.close()
            _enable_wal(self.db_path)

    def __enter__(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys = ON')
        self.conn.execute('PRAGMA busy_timeout = 10000')
        self.conn.execute('PRAGMA journal_mode = WAL')
        self.conn.execute('PRAGMA synchronous = NORMAL')
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            try:
                if exc_type is not None:
                    # An exception is propagating — roll back the pending
                    # transaction explicitly so a failed unit of work never
                    # leaves partial writes behind. Do not mask the original
                    # exception.
                    self.conn.rollback()
            finally:
                self.conn.close()
