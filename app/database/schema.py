"""
Database schema definitions for Party POS.
"""

# ============================================================
# PARTY DATABASE SCHEMA
# ============================================================
# One SQLite database per party. Contains all runtime data.

PARTY_SCHEMA = """
-- ----------------------------------------------------------
-- Product Organization (2-level hierarchy)
-- ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS subsections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    section_id INTEGER NOT NULL,
    FOREIGN KEY (section_id) REFERENCES sections(id),
    UNIQUE(name, section_id)
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    sku TEXT,
    section_id INTEGER NOT NULL,
    subsection_id INTEGER NOT NULL,
    stock_count INTEGER,           -- NULL = unlimited
    is_active BOOLEAN DEFAULT 1,
    is_archived BOOLEAN DEFAULT 0, -- archived, not deleted, if sold
    FOREIGN KEY (section_id) REFERENCES sections(id),
    FOREIGN KEY (subsection_id) REFERENCES subsections(id)
);

-- ----------------------------------------------------------
-- Operators & Auth
-- ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS operators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    pin_hash TEXT NOT NULL,        -- hashed PIN
    role TEXT DEFAULT 'operator',  -- 'operator' or 'admin'
    is_active BOOLEAN DEFAULT 1
);

-- ----------------------------------------------------------
-- Orders & Sales
-- ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    subtotal REAL NOT NULL,
    discount_amount REAL DEFAULT 0.0,
    discount_type TEXT,            -- 'percentage' or 'fixed'
    total REAL NOT NULL,
    payment_method TEXT NOT NULL,
    operator_id INTEGER,
    FOREIGN KEY (operator_id) REFERENCES operators(id)
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,      -- price at time of sale
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    method TEXT NOT NULL,
    amount REAL NOT NULL,
    tendered REAL,
    change_due REAL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
);

-- ----------------------------------------------------------
-- Tags & Styling Rules
-- Tags are assigned to products. Each tag can have a style rule
-- (e.g. background color) that is applied to products carrying it.
-- ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#3498db',       -- default tag color
    bg_color TEXT,                       -- optional product background override
    text_color TEXT,                     -- optional text color override
    is_active BOOLEAN DEFAULT 1,
    UNIQUE(name)
);

CREATE TABLE IF NOT EXISTS product_tags (
    product_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (product_id, tag_id),
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_product_tags_product ON product_tags(product_id);
CREATE INDEX IF NOT EXISTS idx_product_tags_tag ON product_tags(tag_id);

-- ----------------------------------------------------------
-- Audit & Settings
-- ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    action TEXT NOT NULL,
    details TEXT,
    operator_id INTEGER,
    FOREIGN KEY (operator_id) REFERENCES operators(id)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- ----------------------------------------------------------
-- Indexes
-- ----------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_products_section ON products(section_id);
CREATE INDEX IF NOT EXISTS idx_products_subsection ON products(subsection_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
"""


# ============================================================
# TEMPLATES DATABASE SCHEMA
# ============================================================
# Shared app-level store for party templates.
# Lives outside any single party DB so it persists across parties.

TEMPLATES_SCHEMA = """
-- ----------------------------------------------------------
-- Templates (reusable party configurations)
-- ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS template_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS template_subsections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL,
    section_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS template_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL,
    section_id INTEGER,
    subsection_id INTEGER,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    sku TEXT,
    stock_count INTEGER,           -- NULL = unlimited
    FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS template_settings (
    template_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE CASCADE,
    PRIMARY KEY (template_id, key)
);

-- Template tags (definitions transferred to party DB on party creation)
CREATE TABLE IF NOT EXISTS template_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#3498db',
    bg_color TEXT,
    text_color TEXT,
    FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE CASCADE,
    UNIQUE(template_id, name)
);

-- Template-product-tag assignments
CREATE TABLE IF NOT EXISTS template_product_tags (
    template_product_id INTEGER NOT NULL,
    template_tag_id INTEGER NOT NULL,
    PRIMARY KEY (template_product_id, template_tag_id),
    FOREIGN KEY (template_product_id) REFERENCES template_products(id) ON DELETE CASCADE,
    FOREIGN KEY (template_tag_id) REFERENCES template_tags(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_template_tags_template ON template_tags(template_id);
CREATE INDEX IF NOT EXISTS idx_template_product_tags_product ON template_product_tags(template_product_id);

-- ----------------------------------------------------------
-- Indexes
-- ----------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_template_products_template ON template_products(template_id);
"""


# ============================================================
# EXPORT FUNCTIONS
# ============================================================

def get_party_schema():
    """Return the party database schema SQL."""
    return PARTY_SCHEMA


def get_templates_schema():
    """Return the templates database schema SQL."""
    return TEMPLATES_SCHEMA
