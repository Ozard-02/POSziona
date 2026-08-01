"""
Product service for Party POS.
Handles product catalog, sections, subsections, and stock management.
"""

from app.database.connection import PartyDatabase
from app.utils.logger import get_logger

logger = get_logger('services.products')


# ============================================================
# SECTION OPERATIONS
# ============================================================

def get_sections(db_name):
    """Get all sections."""
    with PartyDatabase(db_name) as conn:
        rows = conn.execute("SELECT * FROM sections ORDER BY name").fetchall()
        return [dict(row) for row in rows]


def get_subsections(db_name, section_id):
    """Get all subsections for a given section."""
    with PartyDatabase(db_name) as conn:
        rows = conn.execute(
            "SELECT * FROM subsections WHERE section_id = ? ORDER BY name",
            (section_id,)
        ).fetchall()
        return [dict(row) for row in rows]


def get_all_sections_with_subsections(db_name):
    """Get all sections with their subsections (2-level tree)."""
    with PartyDatabase(db_name) as conn:
        rows = conn.execute(
            """
            SELECT s.id as section_id, s.name as section_name,
                   ss.id as subsection_id, ss.name as subsection_name
            FROM sections s
            LEFT JOIN subsections ss ON s.id = ss.section_id
            ORDER BY s.name, ss.name
            """
        ).fetchall()

        sections = {}
        for row in rows:
            sid = row['section_id']
            if sid not in sections:
                sections[sid] = {
                    'id': sid,
                    'name': row['section_name'],
                    'subsections': []
                }
            if row['subsection_id']:
                sections[sid]['subsections'].append({
                    'id': row['subsection_id'],
                    'name': row['subsection_name']
                })

        return list(sections.values())


def create_section(db_name, name):
    """Create a new section."""
    with PartyDatabase(db_name) as conn:
        conn.execute("INSERT INTO sections (name) VALUES (?)", (name,))
        conn.commit()
        logger.info(f"Created section '{name}'")


def create_subsection(db_name, section_id, name):
    """Create a new subsection under a section."""
    with PartyDatabase(db_name) as conn:
        conn.execute(
            "INSERT INTO subsections (name, section_id) VALUES (?, ?)",
            (name, section_id)
        )
        conn.commit()


# ============================================================
# PRODUCT OPERATIONS
# ============================================================

def get_products_by_subsection(db_name, subsection_id):
    """Get all active products in a subsection, including their tags."""
    with PartyDatabase(db_name) as conn:
        rows = conn.execute(
            """
            SELECT p.* FROM products p
            WHERE p.subsection_id = ? AND p.is_active = 1 AND p.is_archived = 0
            ORDER BY p.name
            """,
            (subsection_id,)
        ).fetchall()
        products = [dict(row) for row in rows]
        # Fetch tags for each product in a single query
        if products:
            product_ids = [p['id'] for p in products]
            placeholders = ','.join('?' * len(product_ids))
            tag_rows = conn.execute(
                f"""
                SELECT pt.product_id, t.id, t.name, t.color, t.bg_color, t.text_color
                FROM product_tags pt
                JOIN tags t ON pt.tag_id = t.id
                WHERE pt.product_id IN ({placeholders}) AND t.is_active = 1
                """,
                product_ids
            ).fetchall()
            # Group tags by product_id
            tags_by_product = {}
            for row in tag_rows:
                pid = row['product_id']
                if pid not in tags_by_product:
                    tags_by_product[pid] = []
                tags_by_product[pid].append(dict(row))
            for p in products:
                p['tags'] = tags_by_product.get(p['id'], [])
        else:
            for p in products:
                p['tags'] = []
        return products


def get_all_products(db_name):
    """Get all active products with their section and subsection names."""
    with PartyDatabase(db_name) as conn:
        rows = conn.execute(
            """
            SELECT p.*, s.name as section_name, ss.name as subsection_name
            FROM products p
            JOIN sections s ON p.section_id = s.id
            JOIN subsections ss ON p.subsection_id = ss.id
            WHERE p.is_active = 1 AND p.is_archived = 0
            ORDER BY s.name, ss.name, p.name
            """
        ).fetchall()
        return [dict(row) for row in rows]


def get_product_by_id(db_name, product_id):
    """Get a single product by ID, including its tags."""
    with PartyDatabase(db_name) as conn:
        row = conn.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        if not row:
            return None
        product = dict(row)
        # Fetch tags
        tag_rows = conn.execute(
            """
            SELECT t.id, t.name, t.color, t.bg_color, t.text_color
            FROM product_tags pt
            JOIN tags t ON pt.tag_id = t.id
            WHERE pt.product_id = ? AND t.is_active = 1
            """,
            (product_id,)
        ).fetchall()
        product['tags'] = [dict(row) for row in tag_rows]
        return product


def create_product(db_name, name, price, section_id, subsection_id, sku=None, stock=None):
    """Create a new product."""
    with PartyDatabase(db_name) as conn:
        conn.execute(
            """INSERT INTO products (name, price, sku, section_id, subsection_id, stock_count)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, price, sku, section_id, subsection_id, stock)
        )
        conn.commit()
        product_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        logger.info(f"Created product '{name}' (id={product_id})")
        return product_id


def update_product(db_name, product_id, name=None, price=None, sku=None,
                   section_id=None, subsection_id=None, stock=None):
    """Update product fields. Only price and stock can change during active party."""
    with PartyDatabase(db_name) as conn:
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if price is not None:
            updates.append("price = ?")
            params.append(price)
        if sku is not None:
            updates.append("sku = ?")
            params.append(sku)
        if section_id is not None:
            updates.append("section_id = ?")
            params.append(section_id)
        if subsection_id is not None:
            updates.append("subsection_id = ?")
            params.append(subsection_id)
        if stock is not None:
            updates.append("stock_count = ?")
            params.append(stock)

        if not updates:
            return

        params.append(product_id)
        conn.execute(
            f"UPDATE products SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()


def decrement_stock(db_name, product_id):
    """Decrement a product's stock by 1."""
    with PartyDatabase(db_name) as conn:
        conn.execute(
            """UPDATE products
               SET stock_count = stock_count - 1
               WHERE id = ? AND stock_count > 0""",
            (product_id,)
        )
        conn.commit()


def archive_product(db_name, product_id):
    """Archive a product (hide from POS without deleting)."""
    with PartyDatabase(db_name) as conn:
        conn.execute(
            "UPDATE products SET is_active = 0, is_archived = 1 WHERE id = ?",
            (product_id,)
        )
        conn.commit()


def delete_product(db_name, product_id):
    """Delete a product (only if never sold)."""
    with PartyDatabase(db_name) as conn:
        # Check if product has ever been sold
        sold = conn.execute(
            "SELECT COUNT(*) as count FROM order_items WHERE product_id = ?",
            (product_id,)
        ).fetchone()

        if sold['count'] > 0:
            # Can't delete — archive instead
            archive_product(db_name, product_id)
            return False
        else:
            conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
            conn.commit()
            return True


def import_products_from_csv(db_name, csv_rows):
    """
    Import products from CSV rows.
    Expected columns: name, price, section, subsection, sku (opt), stock (opt)
    Uses a single database connection to avoid FK constraint issues.
    """
    with PartyDatabase(db_name) as conn:
        for row in csv_rows:
            name = row.get('name', '').strip()
            price = float(row.get('price', 0))
            section = row.get('section', '').strip()
            subsection = row.get('subsection', '').strip()
            sku = str(row.get('sku', '')).strip() or None
            stock_val = row.get('stock')
            if stock_val is not None:
                if isinstance(stock_val, str):
                    stock_val = stock_val.strip()
                stock = int(stock_val) if stock_val else None
            else:
                stock = None

            # Get or create section
            sec = conn.execute(
                "SELECT id FROM sections WHERE name = ?", (section,)
            ).fetchone()
            if sec:
                section_id = sec[0]
            else:
                conn.execute("INSERT INTO sections (name) VALUES (?)", (section,))
                section_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # Get or create subsection
            sub = conn.execute(
                "SELECT id FROM subsections WHERE name = ? AND section_id = ?",
                (subsection, section_id)
            ).fetchone()
            if sub:
                subsection_id = sub[0]
            else:
                conn.execute(
                    "INSERT INTO subsections (name, section_id) VALUES (?, ?)",
                    (subsection, section_id)
                )
                subsection_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # Insert product
            conn.execute(
                """INSERT INTO products (name, price, sku, section_id, subsection_id, stock_count)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (name, price, sku, section_id, subsection_id, stock)
            )

        conn.commit()
        logger.info(f"Imported {len(csv_rows)} products from CSV")


# ============================================================
# TAG OPERATIONS
# ============================================================

def get_all_tags(db_name):
    """Get all active tags."""
    with PartyDatabase(db_name) as conn:
        rows = conn.execute(
            "SELECT * FROM tags WHERE is_active = 1 ORDER BY name"
        ).fetchall()
        return [dict(row) for row in rows]


def get_tag_by_id(db_name, tag_id):
    """Get a single tag by ID."""
    with PartyDatabase(db_name) as conn:
        row = conn.execute(
            "SELECT * FROM tags WHERE id = ?", (tag_id,)
        ).fetchone()
        return dict(row) if row else None


def create_tag(db_name, name, color='#3498db', bg_color=None, text_color=None):
    """Create a new tag with optional styling rules."""
    with PartyDatabase(db_name) as conn:
        conn.execute(
            "INSERT INTO tags (name, color, bg_color, text_color) VALUES (?, ?, ?, ?)",
            (name, color, bg_color, text_color)
        )
        conn.commit()
        tag_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        logger.info(f"Created tag '{name}' (id={tag_id})")
        return tag_id


def update_tag(db_name, tag_id, name=None, color=None, bg_color=None,
               text_color=None, is_active=None):
    """Update tag fields and styling rules."""
    with PartyDatabase(db_name) as conn:
        updates = []
        params = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if color is not None:
            updates.append("color = ?")
            params.append(color)
        if bg_color is not None:
            updates.append("bg_color = ?")
            params.append(bg_color)
        if text_color is not None:
            updates.append("text_color = ?")
            params.append(text_color)
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(is_active)

        if not updates:
            return

        params.append(tag_id)
        conn.execute(
            f"UPDATE tags SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()


def delete_tag(db_name, tag_id):
    """Delete a tag (removes it from all products)."""
    with PartyDatabase(db_name) as conn:
        conn.execute("DELETE FROM product_tags WHERE tag_id = ?", (tag_id,))
        conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        conn.commit()
        logger.info(f"Deleted tag id={tag_id}")


def get_product_tags(db_name, product_id):
    """Get all tags assigned to a product."""
    with PartyDatabase(db_name) as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.name, t.color, t.bg_color, t.text_color
            FROM product_tags pt
            JOIN tags t ON pt.tag_id = t.id
            WHERE pt.product_id = ? AND t.is_active = 1
            """,
            (product_id,)
        ).fetchall()
        return [dict(row) for row in rows]


def assign_tag_to_product(db_name, product_id, tag_id):
    """Assign a tag to a product."""
    with PartyDatabase(db_name) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO product_tags (product_id, tag_id) VALUES (?, ?)",
            (product_id, tag_id)
        )
        conn.commit()
        logger.info(f"Assigned tag id={tag_id} to product id={product_id}")


def remove_tag_from_product(db_name, product_id, tag_id):
    """Remove a tag from a product."""
    with PartyDatabase(db_name) as conn:
        conn.execute(
            "DELETE FROM product_tags WHERE product_id = ? AND tag_id = ?",
            (product_id, tag_id)
        )
        conn.commit()


def set_product_tags(db_name, product_id, tag_ids):
    """Replace all tag assignments for a product with the given tag IDs."""
    with PartyDatabase(db_name) as conn:
        conn.execute("DELETE FROM product_tags WHERE product_id = ?", (product_id,))
        for tag_id in tag_ids:
            conn.execute(
                "INSERT OR IGNORE INTO product_tags (product_id, tag_id) VALUES (?, ?)",
                (product_id, tag_id)
            )
        conn.commit()


def get_all_product_tags(db_name):
    """Get all product-tag assignments as a list of (product_id, tag_id) tuples."""
    with PartyDatabase(db_name) as conn:
        rows = conn.execute(
            "SELECT product_id, tag_id FROM product_tags"
        ).fetchall()
        return [(row[0], row[1]) for row in rows]
