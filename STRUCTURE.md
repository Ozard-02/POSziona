# Project Structure

```
party-pos/
├── app/                    # Main application package
│   ├── __init__.py         # Flask app factory, route definitions
│   ├── main.py             # Entry point with pywebview launcher
│   ├── api/                # REST API endpoints (Flask blueprints)
│   │   ├── __init__.py     # Registers all sub-blueprints + health status
│   │   ├── products.py     # Products, sections, subsections, tags CRUD
│   │   ├── cart.py         # Session-based cart: add/remove/update/discount
│   │   ├── orders.py       # Checkout, order history, sales reports
│   │   ├── parties.py      # Party CRUD, template management, party settings
│   │   ├── auth.py         # Operator/PIN login, admin access, operator mgmt
│   │   └── settings.py     # Party settings: currency, payment, snapshots
│   ├── database/           # Database layer
│   │   ├── __init__.py     # Package init
│   │   ├── connection.py   # PartyDatabase + TemplatesDatabase context managers
│   │   ├── schema.py       # SQL schema for party + templates DBs
│   │   └── templates_db.py # Template CRUD operations (sections, products, tags)
│   ├── models/             # Data models (dataclass-style, base on Row)
│   │   ├── __init__.py     # BaseModel base class
│   │   ├── product.py      # Product model with stock/availability helpers
│   │   ├── cart.py         # Cart + CartItem with discount logic
│   │   ├── order.py        # Order, OrderItem, Payment models
│   │   ├── party.py        # Party model
│   │   ├── operator.py     # Operator model (admin/operator roles)
│   ├── services/           # Business logic
│   │   ├── __init__.py     # Package init
│   │   ├── product_service.py  # Product catalog, sections, tags, CSV import
│   │   ├── order_service.py    # Order creation, payments, sales reports
│   │   ├── party_service.py    # Party CRUD, templates→parties, settings
│   │   ├── settings_service.py # Default settings, setting get/set
│   │   └── auth_service.py    # PIN hashing, operator auth, audit logging
│   ├── ui/                 # Web UI (HTML/CSS/JS templates)
│   │   ├── templates/      # Jinja2 HTML templates
│   │   │   ├── base.html   # Base template (layout, scripts, styles)
│   │   │   ├── login.html  # Operator login screen (embedded inline JS)
│   │   │   ├── pos.html    # POS screen: sections sidebar, products grid, cart
│   │   │   ├── dashboard.html # Sales dashboard with report filters
│   │   │   └── admin.html  # Admin panel: products, parties, operators, tags
│   │   └── static/         # Static assets
│   │       ├── css/
│   │       │   └── style.css  # All CSS (no inline styles in templates)
│   │       └── js/
│   │           ├── app.js      # Shared utilities (formatCurrency, fetchJSON, auth check)
│   │           ├── pos.js      # POS screen: sections, products, cart, checkout
│   │           ├── admin.js    # Admin panel: dashboard, products, tags, parties
│   │           └── dashboard.js # Report generation, printing
│   └── utils/              # Utilities
│       ├── __init__.py     # Package init
│       ├── config.py       # Configuration (paths, secrets, defaults)
│       ├── logger.py       # Logging setup
│       └── helpers.py      # General helpers (party paths, currency, PIN validation)
├── data/                   # Runtime data (gitignored)
│   ├── parties/            # Individual party SQLite databases
│   ├── templates.db        # Shared templates database
│   └── backups/            # Periodic snapshots
├── tests/                  # Test suite
│   ├── __init__.py
│   ├── conftest.py         # Pytest fixtures
│   ├── unit/               # Unit tests (models, schema validation)
│   ├── integration/        # Integration tests (full workflow, auth, CRUD)
│   └── fixtures/           # Test data
├── docs/                   # Documentation
│   └── requirements.md     # Feature requirements
├── scripts/                # Utility scripts
│   └── run_pos.py          # Launch script (starts Flask + pywebview)
├── .gitignore
├── requirements.txt        # Python dependencies (Flask, pywebview, etc.)
├── requirements-dev.txt    # Development dependencies (pytest, etc.)
├── pyproject.toml          # Project metadata
├── pytest.ini              # Pytest configuration
└── README.md               # Project README with setup & usage
```

### Notes
- **data/** directory and its contents are gitignored (contains runtime databases and backups)
- **templates.db** is the shared app-level store for party templates
- Each party gets its own SQLite file in **data/parties/** created from a template
- **index.html** was removed — the root route renders **login.html** directly
- Static assets use CSS classes instead of inline styles for maintainability
- The `db` parameter is passed as a query string `?db=<name>` to all API endpoints (currently hardcoded to 'default' in the frontend)
- Models exist as dataclass-style classes but services return plain dicts from SQLite rows
- `payment_service.py` and `report_service.py` are in the old STRUCTURE.md but don't exist — payment logic lives in `order_service.py`'s `record_payment()`, and reports live in `order_service.py`'s `get_sales_summary()` etc.