"""
Templates database operations.
"""

from app.database.connection import TemplatesDatabase
from app.utils.logger import get_logger

logger = get_logger('database.templates')


# ============================================================
# TEMPLATE CRUD OPERATIONS
# ============================================================

def create_template(name, description=""):
    """Create a new party template."""
    with TemplatesDatabase() as conn:
        conn.execute(
            "INSERT INTO templates (name, description) VALUES (?, ?)",
            (name, description)
        )
        conn.commit()
        template_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        logger.info(f"Created template '{name}' (id={template_id})")
        return template_id


def get_template(template_id):
    """Get a single template by ID."""
    with TemplatesDatabase() as conn:
        row = conn.execute(
            "SELECT * FROM templates WHERE id = ?", (template_id,)
        ).fetchone()
        return dict(row) if row else None


def get_all_templates():
    """Get all templates."""
    with TemplatesDatabase() as conn:
        rows = conn.execute(
            "SELECT * FROM templates ORDER BY name"
        ).fetchall()
        return [dict(row) for row in rows]


def delete_template(template_id):
    """Delete a template and all its associated data."""
    with TemplatesDatabase() as conn:
        conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))
        conn.commit()
        logger.info(f"Deleted template id={template_id}")


# ============================================================
# TEMPLATE PRODUCTS
# ============================================================

def add_template_product(template_id, name, price, section, subsection, sku=None, stock=None):
    """Add a product to a template, creating sections/subsections as needed."""
    with TemplatesDatabase() as conn:
        # Get or create section
        section_row = conn.execute(
            "SELECT id FROM template_sections WHERE template_id = ? AND name = ?",
            (template_id, section)
        ).fetchone()

        if section_row:
            section_id = section_row[0]
        else:
            conn.execute(
                "INSERT INTO template_sections (template_id, name) VALUES (?, ?)",
                (template_id, section)
            )
            section_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Get or create subsection
        sub_row = conn.execute(
            "SELECT id FROM template_subsections WHERE template_id = ? AND section_id = ? AND name = ?",
            (template_id, section_id, subsection)
        ).fetchone()

        if sub_row:
            subsection_id = sub_row[0]
        else:
            conn.execute(
                "INSERT INTO template_subsections (template_id, section_id, name) VALUES (?, ?, ?)",
                (template_id, section_id, subsection)
            )
            subsection_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Insert product
        conn.execute(
            "INSERT INTO template_products (template_id, section_id, subsection_id, name, price, sku, stock_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (template_id, section_id, subsection_id, name, price, sku, stock)
        )
        conn.commit()
        logger.debug(f"Added product '{name}' to template id={template_id}")


def get_template_products(template_id):
    """Get all products for a template."""
    with TemplatesDatabase() as conn:
        rows = conn.execute(
            """
            SELECT p.id as template_product_id, p.name, p.price, p.sku, p.stock_count,
                   s.name as section, ss.name as subsection
            FROM template_products p
            JOIN template_sections s ON p.section_id = s.id
            JOIN template_subsections ss ON p.subsection_id = ss.id
            WHERE p.template_id = ?
            ORDER BY s.name, ss.name, p.name
            """,
            (template_id,)
        ).fetchall()
        return [dict(row) for row in rows]


# ============================================================
# TEMPLATE SETTINGS
# ============================================================

def set_template_setting(template_id, key, value):
    """Set a setting for a template."""
    with TemplatesDatabase() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO template_settings (template_id, key, value) VALUES (?, ?, ?)",
            (template_id, key, value)
        )
        conn.commit()


def get_template_settings(template_id):
    """Get all settings for a template."""
    with TemplatesDatabase() as conn:
        rows = conn.execute(
            "SELECT key, value FROM template_settings WHERE template_id = ?",
            (template_id,)
        ).fetchall()
        return {row[0]: row[1] for row in rows}


# ============================================================
# TEMPLATE TAGS
# ============================================================

def add_template_tag(template_id, name, color='#3498db', bg_color=None, text_color=None):
    """Add a tag definition to a template."""
    with TemplatesDatabase() as conn:
        cur = conn.execute(
            "INSERT INTO template_tags (template_id, name, color, bg_color, text_color) VALUES (?, ?, ?, ?, ?)",
            (template_id, name, color, bg_color, text_color)
        )
        conn.commit()
        return cur.lastrowid


def get_template_tags(template_id):
    """Get all tags defined on a template."""
    with TemplatesDatabase() as conn:
        rows = conn.execute(
            "SELECT id, name, color, bg_color, text_color FROM template_tags WHERE template_id = ? ORDER BY name",
            (template_id,)
        ).fetchall()
        return [dict(row) for row in rows]


def set_template_product_tags(template_id, template_product_id, tag_names):
    """Assign tags (by name) to a template product, creating tags as needed."""
    with TemplatesDatabase() as conn:
        # Collect existing template tags
        existing = {}
        rows = conn.execute(
            "SELECT id, name FROM template_tags WHERE template_id = ?",
            (template_id,)
        ).fetchall()
        for row in rows:
            existing[row['name']] = row['id']

        for tag_name in tag_names:
            if tag_name in existing:
                tag_id = existing[tag_name]
            else:
                cur = conn.execute(
                    "INSERT INTO template_tags (template_id, name) VALUES (?, ?)",
                    (template_id, tag_name)
                )
                tag_id = cur.lastrowid
            # Link tag to product
            conn.execute(
                "INSERT OR IGNORE INTO template_product_tags (template_product_id, template_tag_id) VALUES (?, ?)",
                (template_product_id, tag_id)
            )
        conn.commit()


def get_template_product_tag_names(template_id):
    """Get a mapping of template_product_id -> list of tag names."""
    with TemplatesDatabase() as conn:
        rows = conn.execute(
            """
            SELECT tpt.template_product_id, tt.name
            FROM template_product_tags tpt
            JOIN template_tags tt ON tpt.template_tag_id = tt.id
            WHERE tt.template_id = ?
            """,
            (template_id,)
        ).fetchall()
        result = {}
        for row in rows:
            pid = row['template_product_id']
            result.setdefault(pid, []).append(row['name'])
        return result
