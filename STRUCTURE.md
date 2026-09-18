# Project Structure

Verified against the real tree on 2026-09-18.

```
posziona/
├── app/                          # Main application package
│   ├── __init__.py               # Flask app factory create_app() + JSON error handlers
│   ├── main.py                   # Entry point: server+client / server / client modes + pywebview
│   ├── api/                      # REST API (Flask blueprints, thin)
│   │   ├── __init__.py           # Registers sub-blueprints + GET /api/events (SSE) + /api/status (health)
│   │   ├── auth.py               # PIN login/logout (rate-limited), operator mgmt
│   │   ├── products.py           # Products, sections, subsections, tags, CSV import/export
│   │   ├── cart.py               # Session-based cart: add/remove/update/discount (discounts audited)
│   │   ├── orders.py             # Atomic checkout, history, reports, delete (restores stock, audited)
│   │   ├── parties.py            # Party CRUD, duplicate (catalog only), backups/restore, date edit
│   │   └── settings.py           # Party settings get/set
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py         # PartyDatabase + TemplatesDatabase ctx managers (rollback on error),
│   │   │                         # validate_db_name, integrity quarantine, schema-drift guard,
│   │   │                         # open-counts + lifecycle lock
│   │   ├── schema.py             # PARTY_SCHEMA (+idempotency_keys) + TEMPLATES_SCHEMA (WAL, FK, indexes)
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
│   │   ├── order_service.py      # checkout_order (atomic + idempotent), sales summaries, delete+restore
│   │   ├── party_service.py      # Party create from template/empty, duplicate, delete (locked, guarded)
│   │   ├── backup_service.py     # VACUUM INTO snapshots, prune/restore, background scheduler
│   │   ├── settings_service.py   # DEFAULT_SETTINGS + get_effective_settings()
│   │   └── auth_service.py       # PBKDF2 PIN hashing (+legacy upgrade), verification, audit log
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
│   │           ├── app.js            # fetchJSON, formatCurrency, auth check, toast errors
│   │           ├── pos.js            # Sections/products/cart/checkout (idempotency key), SSE sync, Shift+L / Shift+Click
│   │           ├── admin.js          # Dashboard, products, tags, parties (data-i18n)
│   │           ├── dashboard.js      # Report generation, printing
│   │           └── translations.js   # i18n (en/it)
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── config.py             # HOST, PORT, DATA_DIR, PARTY_DB_DIR, per-install SECRET_KEY
│   │   ├── events.py             # SSE broadcaster: broadcast(), sse_response(), prune/heartbeat
│   │   ├── rate_limit.py         # In-memory fixed-window throttle (login endpoints)
│   │   └── logger.py             # Rotating logs → app/logs/pos.log (5MB × 4)
│   ├── logs/                     # Runtime logs (pos.log; .gitkeep tracked)
│   └── data/                     # Runtime data (gitignored): parties/*.db, templates.db, backups/
├── scripts/
│   ├── run_pos.py                # Launcher (--mode all|server|client, --server-url)
│   └── entry_point.py            # PyInstaller entry point (frozen path handling)
├── tests/
│   ├── conftest.py               # app/client/clean_db fixtures (fresh test_party.db, wipe templates)
│   ├── unit/test_models.py
│   └── integration/              # test_api, test_parties, test_products_search_bulk, test_csv_import,
│                                 # test_stock_and_availability, test_tags,
│                                 # test_default_tags_and_zero_total, test_manual_party_and_products,
│                                 # test_resilience, test_checkout_atomic, test_backups,
│                                 # test_auth_hardening, test_schema_drift, test_ops_safety
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
- `data/` is gitignored (runtime DBs + backups + `.secret_key` for session signing).
- `data/backups/` holds timestamped `VACUUM INTO` snapshots (see backup scheduler).
- There is **no** `app/models/order.py` or `app/models/party.py` — order/party logic lives in `order_service.py` / `party_service.py` returning dicts. (Older docs mention them; they don't exist.)
- There is **no** `payment_service.py` / `report_service.py` — checkout = `order_service.checkout_order()` (atomic + idempotent), reports = `order_service.get_sales_summary()` etc.
- There is **no** `app/utils/helpers.py` — helpers live in services + `config.py`.
- `db` scoping is `?db=<name>` query param, validated by `validate_db_name()` (traversal rejected with 400); frontend currently hardcodes `default`.
- `index.html` was removed — `/` renders `login.html` directly.
