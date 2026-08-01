# Project Structure

```
party-pos/
├── app/                    # Main application package
│   ├── __init__.py         # App factory, Flask app creation
│   ├── main.py             # Application entry point
│   ├── api/                # REST API endpoints
│   │   ├── __init__.py
│   │   ├── products.py     # Product-related endpoints
│   │   ├── cart.py         # Cart management endpoints
│   │   ├── orders.py       # Order/checkout endpoints
│   │   ├── payments.py     # Payment processing endpoints
│   │   ├── reports.py      # Reporting endpoints
│   │   ├── parties.py      # Party management endpoints
│   │   └── auth.py         # Authentication endpoints (admin PIN)
│   ├── database/           # Database layer
│   │   ├── __init__.py
│   │   ├── connection.py   # SQLite connection management (WAL mode)
│   │   ├── schema.py       # Database schema definitions
│   │   ├── templates_db.py # Templates database operations
│   │   └── snapshots.py    # Backup/snapshot logic
│   ├── models/             # Data models (lightweight ORMs or dataclasses)
│   │   ├── __init__.py
│   │   ├── product.py
│   │   ├── cart.py
│   │   ├── order.py
│   │   ├── party.py
│   │   └── operator.py
│   ├── services/           # Business logic
│   │   ├── __init__.py
│   │   ├── product_service.py
│   │   ├── cart_service.py
│   │   ├── order_service.py
│   │   ├── payment_service.py
│   │   ├── report_service.py
│   │   └── party_service.py
│   ├── ui/                 # Web UI (HTML/CSS/JS templates)
│   │   ├── templates/      # Jinja2 HTML templates
│   │   │   ├── base.html
│   │   │   ├── index.html
│   │   │   ├── products.html
│   │   │   ├── cart.html
│   │   │   ├── checkout.html
│   │   │   ├── receipts.html
│   │   │   ├── reports.html
│   │   │   ├── admin_products.html
│   │   │   ├── admin_parties.html
│   │   │   ├── admin_settings.html
│   │   │   └── login.html
│   │   └── static/         # Static assets
│   │       ├── css/
│   │       │   └── style.css
│   │       ├── js/
│   │       │   ├── app.js          # Main frontend logic
│   │       │   ├── pos.js          # POS screen logic
│   │       │   ├── cart.js         # Cart management
│   │       │   ├── admin.js        # Admin panel logic
│   │       │   └── utils.js        # Helper functions
│   │       └── assets/             # Images, icons (minimal)
│   └── utils/              # Utilities
│       ├── __init__.py
│       ├── config.py       # Configuration management
│       ├── logger.py       # Logging setup
│       └── helpers.py      # General helper functions
├── data/                   # Runtime data (gitignored)
│   ├── parties/            # Individual party SQLite databases
│   ├── templates.db        # Shared templates database
│   └── backups/            # Periodic snapshots
├── tests/                  # Test suite
│   ├── __init__.py
│   ├── conftest.py         # Pytest fixtures
│   ├── unit/               # Unit tests
│   ├── integration/        # Integration tests
│   └── fixtures/           # Test data
├── docs/                   # Documentation
│   ├── requirements.md     # This file's source / requirements
│   ├── STRUCTURE.md        # Project structure (this file)
│   ├── architecture.md     # Architecture overview
│   └── api-spec.md         # API specification
├── scripts/                # Utility scripts
│   ├── setup.py            # Initial setup script
│   ├── run_pos.py          # Launch script
│   └── dev.py              # Development helper
├── .gitignore
├── requirements.txt        # Python dependencies
├── pyproject.toml          # Project metadata (if using modern packaging)
└── README.md               # Project README
```

### Notes
- **data/** directory and its contents should be gitignored (contains runtime databases and backups)
- **templates.db** is the shared app-level store for party templates
- Each party gets its own SQLite file in **data/parties/** created from a template
- **tests/** should mirror the app structure for easy navigation
- Static assets are kept minimal (text-only UI as required)
