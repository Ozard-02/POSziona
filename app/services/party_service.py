"""
Party service for Posziona.
Handles party creation from templates, settings, and party lifecycle.
"""

import os
import sqlite3
from datetime import datetime

from app.database.connection import (
    PartyDatabase, _init_default_operators, _init_default_products,
    validate_db_name, _lifecycle_lock,
)
from app.database import templates_db
from app.database.schema import get_party_schema
from app.utils.config import PARTY_DB_DIR
from app.utils.logger import get_logger

logger = get_logger('services.parties')


# ============================================================
# PARTY CRUD
# ============================================================

def _remove_db_files(db_path):
    """Remove a DB file and its WAL/SHM sidecars if present."""
    if os.path.exists(db_path):
        os.remove(db_path)
        for ext in ['-wal', '-shm']:
            ext_path = db_path + ext
            if os.path.exists(ext_path):
                os.remove(ext_path)

def create_party_from_template(party_name, template_id, start_date=None, end_date=None):
    """
    Create a new party database from a template.
    Copies template's products, sections, subsections, tags, and settings.
    Returns the party DB name.
    """
    # Get template data
    template = templates_db.get_template(template_id)
    if not template:
        raise ValueError(f"Template id={template_id} not found")

    template_products = templates_db.get_template_products(template_id)
    template_settings = templates_db.get_template_settings(template_id)
    template_tags = templates_db.get_template_tags(template_id)
    template_product_tag_names = templates_db.get_template_product_tag_names(template_id)
    # Determine DB filename from party name
    safe_name = "".join(c for c in party_name if c.isalnum() or c in (' ', '-', '_'))
    db_name = f"{safe_name}"

    # Create party DB using schema
    db_path = os.path.join(PARTY_DB_DIR, f"{db_name}.db")

    with _lifecycle_lock:
        # Remove existing DB if it exists (fresh creation from template)
        _remove_db_files(db_path)

        with sqlite3.connect(db_path) as conn:
            # Apply schema
            conn.executescript(get_party_schema())
            conn.execute('PRAGMA journal_mode=WAL')

            # Copy sections and subsections
            section_map = {}  # template_section_id -> new_section_id
            subsection_map = {}  # template_subsection_id -> new_subsection_id

            # Collect unique sections from template products
            sections_seen = {}
            for product in template_products:
                sec_name = product['section']
                if sec_name and sec_name not in sections_seen:
                    cur = conn.execute(
                        "INSERT INTO sections (name) VALUES (?)", (sec_name,)
                    )
                    sections_seen[sec_name] = cur.lastrowid

            # Collect unique subsections
            sub_seen = {}
            for product in template_products:
                sub_name = product['subsection']
                sec_name = product['section']
                sec_id = sections_seen.get(sec_name)
                key = (sec_name, sub_name)
                if key not in sub_seen:
                    cur = conn.execute(
                        "INSERT INTO subsections (name, section_id) VALUES (?, ?)",
                        (sub_name, sec_id)
                    )
                    sub_seen[key] = cur.lastrowid

            # Copy template tags to party tags
            template_tag_id_map = {}  # template_tag_id -> party_tag_id
            for ttag in template_tags:
                cur = conn.execute(
                    "INSERT INTO tags (name, color, bg_color, text_color) VALUES (?, ?, ?, ?)",
                    (ttag['name'], ttag['color'], ttag['bg_color'], ttag['text_color'])
                )
                template_tag_id_map[ttag['id']] = cur.lastrowid

            # Insert products and track their new IDs
            template_product_id_map = {}  # template_product_id -> party_product_id
            for product in template_products:
                sec_id = sections_seen.get(product['section'])
                sub_id = sub_seen.get((product['section'], product['subsection']))
                cur = conn.execute(
                    """INSERT INTO products (name, price, sku, section_id, subsection_id, stock_count)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (product['name'], product['price'], product['sku'],
                     sec_id, sub_id, product['stock_count'])
                )
                template_product_id_map[product['template_product_id']] = cur.lastrowid

            # Link products to their tags (resolved via tag name)
            # Build a name -> party_tag_id map
            tag_name_to_party_id = {}
            for ttag in template_tags:
                tag_name_to_party_id[ttag['name']] = template_tag_id_map[ttag['id']]

            for tpl_product_id, tag_names in template_product_tag_names.items():
                party_product_id = template_product_id_map.get(tpl_product_id)
                if party_product_id is None:
                    continue
                for tag_name in tag_names:
                    party_tag_id = tag_name_to_party_id.get(tag_name)
                    if party_tag_id:
                        conn.execute(
                            "INSERT OR IGNORE INTO product_tags (product_id, tag_id) VALUES (?, ?)",
                            (party_product_id, party_tag_id)
                        )

            # Copy settings
            for key, value in template_settings.items():
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?)",
                    (key, value)
                )

            # Set party metadata
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                ('party_name', party_name)
            )
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                ('start_date', start_date or datetime.now().strftime('%Y-%m-%d'))
            )
            if end_date:
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?)",
                    ('end_date', end_date)
                )

            conn.commit()

    logger.info(f"Created party '{party_name}' from template id={template_id}")
    return db_name


def get_party_settings(db_name):
    """Get all settings for a party."""
    with PartyDatabase(db_name) as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {row[0]: row[1] for row in rows}


def update_party_setting(db_name, key, value):
    """Update a party setting."""
    with PartyDatabase(db_name) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit()


def list_parties():
    """List all party database files."""
    if not os.path.exists(PARTY_DB_DIR):
        return []

    parties = []
    for filename in os.listdir(PARTY_DB_DIR):
        if filename.endswith('.db'):
            party_name = filename[:-3]
            filepath = os.path.join(PARTY_DB_DIR, filename)
            stats = os.stat(filepath)
            parties.append({
                'name': party_name,
                'modified': datetime.fromtimestamp(stats.st_mtime).isoformat(),
                'size': stats.st_size
            })
    return parties


def delete_party(db_name):
    """Delete a party database and its associated files.

    Refuses (with a clear error) when the DB has live connections —
    deleting the file mid-party would break running checkouts.
    """
    from app.database.connection import _get_party_db_path, open_count
    validate_db_name(db_name)
    with _lifecycle_lock:
        db_path = _get_party_db_path(db_name)
        live = open_count(db_path)
        if live > 0:
            raise RuntimeError(
                f'Party "{db_name}" is in use (' + str(live) + ' open connections) — '
                'close POS clients using it, then retry')
        if os.path.exists(db_path):
            os.remove(db_path)
            # Remove WAL and SHM files if they exist
            for ext in ['-wal', '-shm']:
                path = db_path + ext
                if os.path.exists(path):
                    os.remove(path)
            logger.info(f"Deleted party '{db_name}'")


def create_empty_party(party_name, start_date=None, end_date=None):
    """
    Create a new empty party database (no template required).
    Returns the party DB name.
    """
    safe_name = "".join(c for c in party_name if c.isalnum() or c in (' ', '-', '_'))
    db_name = f"{safe_name}"

    db_path = os.path.join(PARTY_DB_DIR, f"{db_name}.db")

    with _lifecycle_lock:
        # Remove existing DB if it exists
        _remove_db_files(db_path)

        with sqlite3.connect(db_path) as conn:
            conn.executescript(get_party_schema())
            conn.execute('PRAGMA journal_mode=WAL')
            conn.commit()

        # Seed default operators and products for the new DB
        _init_default_operators(db_path)
        _init_default_products(db_path)

    # Set party metadata
    with PartyDatabase(db_name) as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)",
            ('party_name', party_name)
        )
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)",
            ('start_date', start_date or datetime.now().strftime('%Y-%m-%d'))
        )
        if end_date:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                ('end_date', end_date)
            )
        conn.commit()

    logger.info(f"Created empty party '{party_name}' (db={db_name})")
    return db_name


def _duplicate_party_files(src_path, dst_path):
    """Copy catalog tables from src to a fresh dst DB. Call with _lifecycle_lock held."""
    # Remove destination if it already exists (fresh copy)
    if os.path.exists(dst_path):
        for ext in ['', '-wal', '-shm']:
            p = dst_path + ext
            if os.path.exists(p):
                os.remove(p)

    # Tables to copy (catalog/items only — no sales history)
    catalog_tables = [
        'sections', 'subsections', 'products',
        'tags', 'product_tags',
        'operators',
        'settings',
    ]

    # Create new DB with schema, then copy catalog data from source
    with sqlite3.connect(dst_path) as dst_conn:
        dst_conn.executescript(get_party_schema())
        dst_conn.execute('PRAGMA journal_mode=WAL')

        src_conn = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
        try:
            for table in catalog_tables:
                rows = src_conn.execute(f"SELECT * FROM {table}").fetchall()
                if not rows:
                    continue
                # Get column count to build placeholders
                col_count = len(rows[0])
                placeholders = ', '.join(['?'] * col_count)
                dst_conn.executemany(
                    f"INSERT INTO {table} VALUES ({placeholders})",
                    rows
                )
        finally:
            src_conn.close()

        dst_conn.commit()


def duplicate_party(original_name, new_name, start_date=None, end_date=None):
    """
    Duplicate an existing party by copying only the catalog/item data
    (sections, subsections, products, tags, product_tags, operators, settings)
    — NOT the sales history (orders, order_items, payments, audit_log).

    Optionally sets start_date / end_date on the duplicated party's
    settings table (overriding the original's dates).
    """
    # Determine source path
    src_db_name = original_name.replace('.db', '') if original_name.endswith('.db') else original_name
    validate_db_name(src_db_name)
    src_path = os.path.join(PARTY_DB_DIR, f"{src_db_name}.db")

    if not os.path.exists(src_path):
        raise FileNotFoundError(f"Party '{original_name}' not found")

    # Sanitize new_name to determine the destination DB name
    safe_name = "".join(c for c in new_name if c.isalnum() or c in (' ', '-', '_'))
    validate_db_name(safe_name)
    dst_path = os.path.join(PARTY_DB_DIR, f"{safe_name}.db")

    with _lifecycle_lock:
        _duplicate_party_files(src_path, dst_path)

    # Override party name and optionally dates in settings
    db_name_for_path = safe_name
    with PartyDatabase(db_name_for_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ('party_name', new_name)
        )
        if start_date:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ('start_date', start_date)
            )
        if end_date:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ('end_date', end_date)
            )
        conn.commit()

    logger.info(f"Duplicated party '{original_name}' to '{safe_name}' (catalog only, no sales history)")
    return safe_name
