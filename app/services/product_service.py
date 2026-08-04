"""
Product service for Posziona.
Handles product catalog, sections, subsections, and stock management.
"""

from app.database.connection import PartyDatabase
from app.utils.logger import get_logger

logger = get_logger('services.products')

# Sentinel for distinguishing "argument not provided" from "argument is None".
# Used so that stock=None (unlimited) can be explicitly set on products.
_UNSET = object()


# ============================================================
# SECTION OPERATIONS
# ============================================================

def get_sections(db_name):
    """Get all sections."""
    with PartyDatabase(db_name) as conn:
        rows = conn.execute("SELECT * FROM sections ORDER BY sort_order, name").fetchall()
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
            SELECT s.id as section_id, s.name as section_name, s.sort_order as section_sort_order,
                   ss.id as subsection_id, ss.name as subsection_name
            FROM sections s
            LEFT JOIN subsections ss ON s.id = ss.section_id
            ORDER BY s.sort_order, s.name, ss.name
            """
        ).fetchall()

        sections = {}
        for row in rows:
            sid = row['section_id']
            if sid not in sections:
                sections[sid] = {
                    'id': sid,
                    'name': row['section_name'],
                    'sort_order': row['section_sort_order'],
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
        # Get the max sort_order to append at the end
        max_order = conn.execute("SELECT MAX(sort_order) FROM sections").fetchone()[0]
        sort_order = (max_order or 0) + 1
        conn.execute(
            "INSERT INTO sections (name, sort_order) VALUES (?, ?)",
            (name, sort_order)
        )
        conn.commit()
        logger.info(f"Created section '{name}'")


def reorder_sections(db_name, section_ids):
    """Reorder sections by setting sort_order based on the provided order.
    Args:
        db_name: Party database name.
        section_ids: List of section IDs in the desired order.
    """
    with PartyDatabase(db_name) as conn:
        for idx, sid in enumerate(section_ids):
            conn.execute(
                "UPDATE sections SET sort_order = ? WHERE id = ?",
                (idx, sid)
            )
        conn.commit()
        logger.info(f"Reordered {len(section_ids)} sections")


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
    """Get all non-archived products with their section and subsection names.

    Inactive products (is_active = 0) are included so they remain visible and
    editable in the admin products table — previously they were filtered out,
    making it impossible to edit availability of items that had been marked
    unavailable (e.g. after checkout depleted stock).
    """
    with PartyDatabase(db_name) as conn:
        rows = conn.execute(
            """
            SELECT p.*, s.name as section_name, ss.name as subsection_name
            FROM products p
            JOIN sections s ON p.section_id = s.id
            JOIN subsections ss ON p.subsection_id = ss.id
            WHERE p.is_archived = 0
            ORDER BY s.sort_order, s.name, ss.name, p.name
            """
        ).fetchall()
        return [dict(row) for row in rows]


def search_products(db_name, search=None, section_id=None, subsection_id=None,
                    tag_ids=None, is_active=None, include_archived=False):
    """
    Search and filter products.

    Args:
        db_name: Party database name.
        search: Free-text search on product name and SKU (case-insensitive).
        section_id: Filter by section ID.
        subsection_id: Filter by subsection ID.
        tag_ids: List of tag IDs — products must have ALL of these tags.
        is_active: If True/False, filter by active/inactive products.
        include_archived: If True, also include archived products.

    Returns:
        List of product dicts with section_name, subsection_name, and tags.
    """
    with PartyDatabase(db_name) as conn:
        where_clauses = []
        params = []

        if not include_archived:
            where_clauses.append("p.is_archived = 0")

        if is_active is not None:
            where_clauses.append(f"p.is_active = {1 if is_active else 0}")

        if section_id is not None:
            where_clauses.append("p.section_id = ?")
            params.append(section_id)

        if subsection_id is not None:
            where_clauses.append("p.subsection_id = ?")
            params.append(subsection_id)

        if search:
            where_clauses.append("(p.name LIKE ? OR (p.sku IS NOT NULL AND p.sku LIKE ?))")
            like = f"%{search}%"
            params.extend([like, like])

        where_sql = " AND ".join(where_clauses)

        base_query = f"""
            SELECT p.*, s.name as section_name, ss.name as subsection_name
            FROM products p
            JOIN sections s ON p.section_id = s.id
            JOIN subsections ss ON p.subsection_id = ss.id
            WHERE {where_sql}
            ORDER BY s.sort_order, s.name, ss.name, p.name
        """

        rows = conn.execute(base_query, params).fetchall()
        products = [dict(row) for row in rows]

        if not products:
            return products

        # If tag_ids are specified, filter to products that have ALL those tags
        if tag_ids:
            product_ids = [p['id'] for p in products]
            placeholders = ','.join('?' * len(product_ids))
            tag_placeholders = ','.join('?' * len(tag_ids))

            # Subquery: count how many of the requested tags each product has
            # A product matches if it has all requested tags (count == len(tag_ids))
            matched_rows = conn.execute(
                f"""
                SELECT product_id FROM product_tags
                WHERE product_id IN ({placeholders}) AND tag_id IN ({tag_placeholders})
                GROUP BY product_id
                HAVING COUNT(DISTINCT tag_id) = ?
                """,
                product_ids + tag_ids + [len(tag_ids)]
            ).fetchall()
            matched_ids = {row['product_id'] for row in matched_rows}
            products = [p for p in products if p['id'] in matched_ids]

        if not products:
            return products

        # Fetch tags for all products in a single query
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
            tags_by_product[pid].append({
                'id': row['id'],
                'name': row['name'],
                'color': row['color'],
                'bg_color': row['bg_color'],
                'text_color': row['text_color']
            })

        for p in products:
            p['tags'] = tags_by_product.get(p['id'], [])

        return products


def update_product_status(db_name, product_id, is_active=None, is_archived=None):
    """Update product active/archived status."""
    with PartyDatabase(db_name) as conn:
        updates = []
        params = []
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if is_active else 0)
        if is_archived is not None:
            updates.append("is_archived = ?")
            params.append(1 if is_archived else 0)

        if not updates:
            return

        params.append(product_id)
        conn.execute(
            f"UPDATE products SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()


def bulk_update_products(db_name, product_ids, updates):
    """
    Apply updates to multiple products.

    Args:
        db_name: Party database name.
        product_ids: List of product IDs to update.
        updates: Dict of field names to new values. Supported keys:
                 name, price, sku, section_id, subsection_id, stock,
                 is_active, is_archived, tags (list of tag IDs).

    Returns:
        Number of products updated.
    """
    if not product_ids:
        return 0

    with PartyDatabase(db_name) as conn:
        count = 0
        placeholders = ','.join('?' * len(product_ids))

        # Handle tags separately if present
        tag_ids = updates.pop('tags', None)
        if tag_ids is not None:
            # Clear existing and set new tags for all selected products
            conn.execute(
                f"DELETE FROM product_tags WHERE product_id IN ({placeholders})",
                product_ids
            )
            for pid in product_ids:
                for tid in tag_ids:
                    conn.execute(
                        "INSERT OR IGNORE INTO product_tags (product_id, tag_id) VALUES (?, ?)",
                        (pid, tid)
                    )

        # Build SET clause for other fields
        set_clauses = []
        params = []
        for key, value in updates.items():
            if key in ('name', 'price', 'sku', 'section_id', 'subsection_id', 'stock'):
                col = key if key != 'stock' else 'stock_count'
                set_clauses.append(f"{col} = ?")
                params.append(value)
            elif key == 'stock_count':
                set_clauses.append("stock_count = ?")
                params.append(value)

            elif key in ('is_active',):
                col = 'is_active'
                set_clauses.append(f"{col} = ?")
                params.append(1 if value else 0)
            elif key in ('is_archived',):
                col = 'is_archived'
                set_clauses.append(f"{col} = ?")
                params.append(1 if value else 0)

        if set_clauses:
            params.extend(product_ids)
            set_sql = ", ".join(set_clauses)
            conn.execute(
                f"UPDATE products SET {set_sql} WHERE id IN ({placeholders})",
                params
            )

        conn.commit()
        count = len(product_ids)
        logger.info(f"Bulk updated {count} products")
        return count


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
                   section_id=None, subsection_id=None, stock=_UNSET,
                   is_active=None):
    """Update product fields.
    
    Uses _UNSET sentinel for stock so that stock=None (unlimited) can be
    explicitly set. Other fields use None as 'not provided'.
    """
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
        if stock is not _UNSET:
            updates.append("stock_count = ?")
            params.append(stock)
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if is_active else 0)

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
        # Check if product exists
        exists = conn.execute(
            "SELECT id FROM products WHERE id = ?",
            (product_id,)
        ).fetchone()
        if not exists:
            return None  # Product doesn't exist

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
    Expected columns: name, price, section, subsection, sku (opt), stock (opt), tags (opt)
    Tags should be comma-separated tag names within a single CSV cell.
    Uses a single database connection to avoid FK constraint issues.
    """
    with PartyDatabase(db_name) as conn:
        imported_count = 0
        for row in csv_rows:
            name = row.get('name', '').strip() if isinstance(row.get('name'), str) else str(row.get('name', '')).strip()
            if not name:
                continue  # Skip rows with empty names

            # Resilient price parsing
            try:
                price = float(row.get('price', 0))
            except (TypeError, ValueError):
                price = 0.0

            if price < 0:
                price = 0.0

            section = row.get('section', '').strip() if isinstance(row.get('section'), str) else str(row.get('section', '')).strip()
            subsection = row.get('subsection', '').strip() if isinstance(row.get('subsection'), str) else str(row.get('subsection', '')).strip()
            sku = str(row.get('sku', '')).strip() or None
            stock_val = row.get('stock')
            if stock_val is not None:
                if isinstance(stock_val, str):
                    stock_val = stock_val.strip()
                try:
                    stock = int(stock_val) if stock_val else None
                except (TypeError, ValueError):
                    stock = None
            else:
                stock = None

            # Parse tags — comma-separated within the cell, handled by CSV parser
            tags_raw = row.get('tags', '')
            if tags_raw and isinstance(tags_raw, str):
                tag_names = [t.strip() for t in tags_raw.split(',') if t.strip()]
            else:
                tag_names = []

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
            cursor = conn.execute(
                """INSERT INTO products (name, price, sku, section_id, subsection_id, stock_count)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (name, price, sku, section_id, subsection_id, stock)
            )
            product_id = cursor.lastrowid

            # Assign tags — get or create each tag, then link
            for tag_name in tag_names:
                tag = conn.execute(
                    "SELECT id FROM tags WHERE name = ? AND is_active = 1",
                    (tag_name,)
                ).fetchone()
                if tag:
                    tag_id = tag[0]
                else:
                    # Create new tag if it doesn't exist
                    conn.execute(
                        "INSERT INTO tags (name, color, bg_color, text_color, is_active) VALUES (?, ?, ?, ?, 1)",
                        (tag_name, '#ffffff', '#3498db', '#000000')
                    )
                    tag_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

                # Link tag to product
                conn.execute(
                    "INSERT OR IGNORE INTO product_tags (product_id, tag_id) VALUES (?, ?)",
                    (product_id, tag_id)
                )

            imported_count += 1

        conn.commit()
        logger.info(f"Imported {imported_count} products from CSV")


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



