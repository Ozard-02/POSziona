# Party POS — Codebase Structure & Logic

## Overview

Party POS is a **desktop Point of Sale (POS) application** built with Python (Flask backend) and pywebview (native desktop shell). It's designed for parties, events, and pop-up venues to manage product catalogs, operator authentication, cart-based ordering, and checkout with tax/discount support.

The app runs as a **hybrid desktop app**: a Flask server runs in a background thread, and a pywebview window loads the web UI as a native desktop window. This gives the simplicity of a web frontend with the packaging benefits of a desktop application (including an AppImage build for Linux).

---

## Directory Layout

```
party-pos/
│
├── app/                          # Main application package
│   ├── __init__.py              # Flask app factory — create_app()
│   ├── main.py                  # Entry point — launches Flask + pywebview
│   │
│   ├── api/                     # REST API layer (Flask Blueprints)
│   │   ├── __init__.py          # Blueprint registry & health check
│   │   ├── auth.py              # Operator login/logout, admin management
│   │   ├── products.py          # Product CRUD, sections, tags, CSV import/export
│   │   ├── cart.py              # Session-based cart operations
│   │   ├── orders.py            # Checkout flow, order history, reports
│   │   ├── parties.py           # Party lifecycle (create, delete, duplicate)
│   │   └── settings.py          # Party-level settings (currency, tax, etc.)
│   │
│   ├── services/                # Business logic layer
│   │   ├── auth_service.py      # PIN hashing/verification, operator CRUD
│   │   ├── product_service.py   # Product catalog operations
│   │   ├── order_service.py     # Order creation, payment recording, reports
│   │   ├── party_service.py     # Party DB creation/deletion from templates
│   │   ├── settings_service.py  # Settings defaults & merging
│   │   └── __init__.py
│   │
│   ├── database/                # Data persistence layer
│   │   ├── __init__.py
│   │   ├── connection.py         # PartyDatabase & TemplatesDatabase context managers
│   │   ├── schema.py            # SQL schema definitions (2 DBs: party + templates)
│   │   └── templates_db.py       # Template CRUD operations (shared across parties)
│   │
│   ├── models/                  # Data model abstractions
│   │   ├── __init__.py           # BaseModel base class
│   │   ├── product.py            # Product model
│   │   ├── operator.py           # Operator model (PIN-based auth)
│   │   ├── tag.py                # Tag model (styling rules)
│   │   ├── cart.py               # Cart + CartItem models (in-memory)
│   │   └── order.py              # Order model (not present in filesystem listing)
│   │
│   ├── ui/                      # Frontend assets
│   │   ├── templates/            # Jinja2 HTML templates
│   │   │   ├── base.html         # Layout skeleton (shared)
│   │   │   ├── login.html        # PIN entry screen
│   │   │   ├── pos.html          # Main point-of-sale interface
│   │   │   ├── dashboard.html    # Admin dashboard
│   │   │   └── admin.html        # Admin management panel
│   │   └── static/
│   │       ├── css/style.css     # Application styles
│   │       └── js/               # Vanilla JS modules
│   │           ├── app.js        # App bootstrap / router
│   │           ├── pos.js        # POS screen logic (cart, checkout)
│   │           ├── dashboard.js  # Dashboard reporting / stats
│   │           ├── admin.js      # Admin panel management
│   │           └── translations.js # i18n (en/it)
│   │
│   ├── utils/                   # Shared utilities
│   │   ├── __init__.py
│   │   ├── config.py             # App config constants (HOST, PORT, paths)
│   │   └── logger.py             # Logging setup (file + console)
│   │
│   ├── data/                     # Runtime data
│   │   ├── parties/*.db          # One SQLite DB per party
│   │   ├── templates.db          # Shared template definitions
│   │   └── backups/              # (empty, for future backup feature)
│   │
│   └── logs/                     # Application logs
│       └── pos.log
│
├── scripts/                     # Build & run scripts
│   ├── entry_point.py           # PyInstaller entry point
│   └── run_pos.py               # Alternative launcher
│
├── tests/                       # Test suite
│   ├── conftest.py              # Fixtures & test config
│   ├── unit/                    # Unit tests (models)
│   │   ├── test_models.py
│   └── integration/              # Integration tests (API flows)
│       ├── test_api.py
│       ├── test_parties.py
│       ├── test_products_search_bulk.py
│       ├── test_csv_import.py
│       ├── test_stock_and_availability.py
│       ├── test_tags.py
│       ├── test_orders.py
│       ├── test_default_tags_and_zero_total.py
│       ├── test_manual_party_and_products.py
│       └── test_resilience.py
│
├── requirements.txt             # Production dependencies
├── requirements-dev.txt         # Development dependencies
├── pyproject.toml               # Project metadata & tooling config
├── pytest.ini                   # Pytest configuration
├── build_appimage.sh            # Linux AppImage build script
├── build_exe.spec               # PyInstaller spec
├── README.md
└── STRUCTURE.md (or CODEBASE_EXPLANATION.md — this file)
```

---

## Architecture: Layers

The application follows a **layered (n-tier) architecture**:

```
┌─────────────────────────────────────────────────────────┐
│                    UI (Browser / pywebview)              │
│  HTML templates + vanilla JS calling REST API           │
├─────────────────────────────────────────────────────────┤
│                    API Layer (Flask Blueprints)          │
│  app/api/*.py — Request parsing, auth checks, JSON I/O  │
├─────────────────────────────────────────────────────────┤
│                  Service Layer (Business Logic)          │
│  app/services/*.py — Domain logic, validation, queries  │
├─────────────────────────────────────────────────────────┤
│                Database Layer (SQLite Access)            │
│  app/database/* — Connection management, schema, queries│
├─────────────────────────────────────────────────────────┤
│              Models (Data Abstractions)                  │
│  app/models/*.py — BaseModel with from_row/to_dict       │
└─────────────────────────────────────────────────────────┘
```

### Key Design Patterns

1. **Flask App Factory** (`app/__init__.py::create_app()`): Creates a Flask app, configures CORS, registers the API blueprint, and maps root routes to HTML templates.

2. **Blueprint Registry** (`app/api/__init__.py`): All API sub-blueprints are imported and registered under `/api/*` prefixes.

3. **Context Manager DB Access** (`PartyDatabase`, `TemplatesDatabase`): Wraps SQLite connections with `with` statements, ensuring proper cleanup. Uses `check_same_thread=False` so Flask's threaded server can share connections.

4. **Dual Database Strategy**: 
   - **Templates DB** (`data/templates.db`): A shared, global database storing reusable party templates (products, sections, tags, settings). Used as a blueprint for new parties.
   - **Party DBs** (`data/parties/<name>.db`): One SQLite database per party, created from a template or empty. All runtime transactional data (orders, payments, cart is session-based) lives here.

---

## Core Data Models

### Operators
- **PIN-based authentication** (4-digit numeric PIN)
- Two default roles: `admin` (full access) and `operator` (POS access only)
- PINs are **SHA-256 hashed** with constant-time comparison (`hmac.compare_digest`)
- Default credentials: admin PIN `0000`, operator PIN `1234`

### Products
- Stored in a **2-level hierarchy**: Sections → Subsections → Products
- Each product has: name, price, SKU, stock count (NULL = unlimited), active/archived flags
- **Tags** are assignable to products and carry styling rules (background color, text color)
- Products can be soft-deleted (archived) if they have order history, or hard-deleted if never sold

### Cart
- **Session-based** (not persisted to database)
- Stores line items with unit price captured at add-time (price snapshot)
- Supports quantity updates, discounts (percentage or fixed), and stock validation
- Cart is cleared after checkout

### Orders
- Created from the cart at checkout
- Captures: subtotal, discount amount/type, total, payment method, operator ID
- Each order has multiple `order_items` (product_id, quantity, unit_price at time of sale)
- Payments table records cash/card/wallet/tab transactions with tendered/change
- **Stock is decremented** at checkout with a `MAX(0, stock - qty)` guard
- Orders can be deleted (admin only), which **restores stock**

### Parties
- Each party = its own SQLite database file
- Can be created from a **template** (copies products, sections, tags, settings) or as **empty** (seeds default Drinks/Snacks)
- Can be **duplicated** (file copy) or **deleted** (removes .db, .db-wal, .db-shm)
- Party settings stored as key-value pairs in a `settings` table, merged with defaults via `get_effective_settings()`

### Templates
- Global definitions reused across parties
- Same structure as party DB (sections, subsections, products, tags, settings) but in the shared `templates.db`
- Template products reference sections/subsections by name (resolved during party creation)
- Template product-tag assignments use tag **names** (not IDs) for portability

---

## How It Works: Request Flow

### 1. Startup (`app/main.py`)

The app supports three modes:

| Mode | Behavior |
|------|----------|
| **all** (default) | Starts Flask server in a daemon thread, then opens a pywebview window pointing to `http://127.0.0.1:5000/` |
| **server** | Starts Flask only; no desktop window — for remote browser access |
| **client** | Opens pywebview only; connects to an existing server (auto-detects localhost, or prompts for IP) |

```python
# Simplified startup flow
app = create_app()
server_thread = Thread(target=app.run, daemon=True)
server_thread.start()
# Wait for server to be ready (socket connect check)
webview.create_window(title="Party POS", url="http://127.0.0.1:5000/")
webview.start()  # Blocks — runs the pywebview event loop
```

### 2. UI Layer (`app/ui/`)

- **Login screen**: Prompts for a 4-digit PIN → `POST /api/auth/login` → stores operator info in Flask session
- **POS screen** (`pos.html` + `pos.js`): Main ordering interface — product grid, cart sidebar, checkout button
- **Dashboard** (`dashboard.html` + `dashboard.js`): Sales reports, recent orders, items sold
- **Admin panel** (`admin.html` + `admin.js`): Product/tag/operator management, party settings, CSV import/export

JS modules communicate with the Flask API via `fetch()`, and routing is handled client-side (simple page show/hide based on auth state and current view).

### 3. API Layer (`app/api/*.py`)

Each API file is a Flask Blueprint with routes under `/api/<resource>/`:

```
POST   /api/auth/login          → authenticate_operator
POST   /api/orders/checkout     → create_order + record_payment
GET    /api/products/           → list sections with subsections
GET    /api/products/<sub_id>/products → list products in subsection
POST   /cart/add                → add item to session cart
GET    /api/orders/report/summary → sales summary query
POST   /api/parties/            → create party from template
```

**Key patterns:**
- All DB-scoped endpoints accept `?db=<party_db_name>` as a query parameter
- `db` defaults to `"default"` if not provided
- Admin-only endpoints check `session.get('operator_role') == 'admin'`
- Cart operations manipulate Flask session data (not the database)
- Errors are caught and returned as `{'error': message}` with appropriate HTTP status codes

### 4. Service Layer (`app/services/*.py`)

Contains the actual business logic — database queries, calculations, and state transitions. The API layer is thin: it parses requests, calls service functions, and formats responses.

**Notable logic:**
- `product_service.search_products()`: Complex filtering with dynamic WHERE clauses, tag-based filtering (products must have ALL specified tags), and batched tag fetching
- `order_service.create_order()`: Calculates subtotal, clamps discount to subtotal (defensive against API bypass), decrements stock atomically
- `order_service.delete_order_by_id()`: Restores stock using a correlated subquery, cascades deletes (payments → order_items → orders)
- `settings_service.get_effective_settings()`: Merges `DEFAULT_SETTINGS` with party-specific overrides

### 5. Database Layer (`app/database/`)

- **`connection.py`**: `PartyDatabase` and `TemplatesDatabase` are context managers that ensure a party DB exists (creating from schema + seeding if new), run migrations on existing DBs, and provide a connection with `Row` factory and foreign keys enabled.
- **`schema.py`**: Defines two SQL schema strings — `PARTY_SCHEMA` (runtime data) and `TEMPLATES_SCHEMA` (reusable definitions). Uses WAL mode for concurrent access.
- **`templates_db.py`**: Pure CRUD functions for templates — create, read, update, delete templates and their associated sections, products, tags, and settings.

---

## Data Flow Examples

### Adding an Item to the Cart
```
Browser (pos.js)
  → fetch('POST /api/cart/add', {product_id, quantity})
  ↓
Flask cart.py:add_to_cart()
  → validates product_id, quantity, stock
  → loads product via product_service.get_product_by_id()
  → appends/merges item in session['cart']
  → returns updated cart + total
```

### Checkout
```
Browser (pos.js → checkout button)
  → fetch('POST /api/orders/checkout', {payment_method, tendered})
  ↓
Flask orders.py:checkout()
  → reads session cart + cart_discount
  → validates operator, payment method
  → calls order_service.create_order()
    → inserts orders row (subtotal, discount, total, method, operator_id)
    → inserts order_items rows (product_id, qty, unit_price)
    → decrements stock (MAX(0, stock - qty) guard)
    → commits transaction
  → calls order_service.record_payment() if tendered provided
  → clears session cart + discount
  → returns order_id + total
```

### Creating a Party from Template
```
Browser (admin.js)
  → fetch('POST /api/parties', {template_id, name, start_date, end_date})
  ↓
Flask parties.py:create_party()
  → calls party_service.create_party_from_template()
    → loads template data from templates_db (products, tags, settings)
    → creates new .db file, applies PARTY_SCHEMA
    → copies sections/subsections (by name), tags, products
    → resolves template tag names → party tag IDs for product-tag links
    → copies settings, sets party_name/start_date/end_date
    → enables WAL mode
  → returns {message, db_name, party_name}
```

---

## Configuration & Environment

| Setting | Source | Default |
|---------|--------|---------|
| `HOST` | `app/utils/config.py` | `127.0.0.1` |
| `PORT` | `app/utils/config.py` | `5000` |
| `DEBUG` | `app/utils/config.py` | `False` |
| `DEFAULT_CURRENCY` | `app/utils/config.py` | `€` |
| Party-specific settings (currency, tax_rate, payment methods, etc.) | Per-party `settings` table | `DEFAULT_SETTINGS` dict |

---

## Build & Distribution

- **`build_appimage.sh`**: Builds a portable Linux AppImage using PyInstaller + appimage-builder
- **`build_exe.spec`**: PyInstaller spec for Windows EXE packaging
- **`scripts/run_pos.py`**: Alternative launcher with command-line argument support
- **`scripts/entry_point.py`**: PyInstaller entry point (imports `app.main`)
- The app bundles Flask, pywebview, PyInstaller, and all dependencies into a single executable

---

## Testing

```
pytest tests/ -v
```

Tests are organized into:
- **`tests/unit/`**: Model tests (test_models.py — BaseModel, Product, Cart, etc.)
- **`tests/integration/`**: Full API endpoint tests, database integration, edge cases

Test DBs are created fresh per test session via `conftest.py` fixtures, and cleaned up automatically.
