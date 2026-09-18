# Project Structure

Verified against the real tree on 2026-09-18.

```
posziona/
├── app/                          # Main application package
│   ├── __init__.py               # Flask app factory create_app()
│   ├── main.py                   # Entry point: server+client / server / client modes + pywebview
│   ├── api/                      # REST API (Flask blueprints, thin)
│   │   ├── __init__.py           # Registers sub-blueprints + GET /api/events (SSE) + /api/status
│   │   ├── auth.py               # PIN login/logout, operator mgmt
│   │   ├── products.py           # Products, sections, subsections, tags, CSV import/export
│   │   ├── cart.py               # Session-based cart: add/remove/update/discount
│   │   ├── orders.py             # Checkout, order history, reports, delete (restores stock)
│   │   ├── parties.py            # Party CRUD, duplicate (catalog only), date edit
│   │   └── settings.py           # Party settings get/set
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py         # PartyDatabase + TemplatesDatabase ctx managers, seeds operators
│   │   ├── schema.py             # PARTY_SCHEMA + TEMPLATES_SCHEMA (WAL, FK, indexes)
│   │   └── templates_db.py       # Template CRUD (sections, products, tags, settings)
│   ├── models/                   # Dataclass-style helpers (services return plain dicts)
│   │   ├── __init__.py           # BaseModel (from_row/to_dict)
│   │   ├── product.py            # Product + stock/availability helpers
│   │   ├── cart.py               # Cart + CartItem (in-memory, discount logic)
│   │   ├── operator.py           # Operator (admin/operator roles)
│   │   └── tag.py                # Tag + styling rules
│   ├── services/                 # Business logic + SQL
│   │   ├── __init__.py
│   │   ├── product_service.py    # Catalog, sections, tags, CSV, search (ALL-tags filter)
│   │   ├── order_service.py      # create_order, record_payment, sales summaries, delete+restore
│   │   ├── party_service.py      # Party create from template/empty, duplicate, delete
│   │   ├── settings_service.py   # DEFAULT_SETTINGS + get_effective_settings()
│   │   └── auth_service.py       # PIN hashing (SHA-256), verification, audit log
│   ├── ui/
│   │   ├── templates/            # Jinja2 pages
│   │   │   ├── base.html
│   │   │   ├── login.html        # PIN entry (root route /)
│   │   │   ├── pos.html          # Sections sidebar + product grid + cart + bottom bar
│   │   │   ├── admin.html        # Products, parties, operators, tags, settings
│   │   │   └── dashboard.html    # Reports + print
│   │   └── static/
│   │       ├── css/style.css
│   │       └── js/
│   │           ├── app.js            # fetchJSON, formatCurrency, auth check
│   │           ├── pos.js            # Sections/products/cart/checkout, SSE sync, Shift+L / Shift+Click
│   │           ├── admin.js          # Dashboard, products, tags, parties (data-i18n)
│   │           ├── dashboard.js      # Report generation, printing
│   │           └── translations.js   # i18n (en/it)
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── config.py             # HOST, PORT, DATA_DIR, PARTY_DB_DIR, DEFAULT_CURRENCY
│   │   ├── events.py             # SSE broadcaster: broadcast(), sse_response(), prune/heartbeat
│   │   └── logger.py             # Logging → app/logs/pos.log
│   ├── logs/                     # Runtime logs (pos.log; .gitkeep tracked)
│   └── data/                     # Runtime data (gitignored): parties/*.db, templates.db, backups/
├── scripts/
│   ├── run_pos.py                # Launcher (--mode all|server|client, --server-url)
│   └── entry_point.py            # PyInstaller entry point (frozen path handling)
├── tests/
│   ├── conftest.py               # app/client/clean_db fixtures (fresh test_party.db, wipe templates)
│   ├── unit/test_models.py
│   └── integration/              # test_api, test_parties, test_products_search_bulk, test_csv_import,
│                                 # test_stock_and_availability, test_tags, test_orders,
│                                 # test_default_tags_and_zero_total, test_manual_party_and_products,
│                                 # test_resilience
├── docs/
│   └── requirements.md           # Feature requirements + MVP scope + unicenta lessons
├── .github/                      # CI builds
├── AppImageBuilder.yml
├── build_linux.sh / build_onefile.spec    # Linux onefile binary
├── build_exe.bat / build_exe.spec / build_onefile.spec  # Windows EXE
├── pyproject.toml                # name posziona 0.1.0, Flask + pywebview + flask-cors
├── pytest.ini                    # testpaths=tests, python_files=test_*.py
├── requirements.txt / requirements-dev.txt
├── README.md                     # Quick start
├── PLAN.md                       # Phases + status
├── ARCHITECTURE.md               # Layers, DB strategy, SSE, flows
└── CODEBASE_EXPLANATION.md       # Long-form walkthrough (partly stale, see Notes)
```

### Notes
- `data/` is gitignored (runtime DBs + backups).
- There is **no** `app/models/order.py` or `app/models/party.py` — order/party logic lives in `order_service.py` / `party_service.py` returning dicts. (Older docs mention them; they don't exist.)
- There is **no** `payment_service.py` / `report_service.py` — payments = `order_service.record_payment()`, reports = `order_service.get_sales_summary()` etc.
- There is **no** `app/utils/helpers.py` — helpers live in services + `config.py`.
- `db` scoping is `?db=<name>` query param, frontend currently hardcodes `default`.
- `index.html` was removed — `/` renders `login.html` directly.
