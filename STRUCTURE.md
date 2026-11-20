# Project Structure

Verified against the real tree on 2026-09-18.

```
posziona/
├── app/                          # Main application package
│   ├── __init__.py               # Flask app factory create_app(): JSON error handlers, 8 MB body cap,
│   │                             # CORS header only on GET /api/status (login-page server probe)
│   ├── main.py                   # Entry point: server+client / server / client modes + pywebview (no-GUI fallback: distro hint + browser auto-open, LAN discovery, single parse_args() for all launchers)
│   ├── api/                      # REST API (Flask blueprints, thin)
│   │   ├── __init__.py           # Registers sub-blueprints + GET /api/events (SSE) + /api/status (health)
│   │   │                         # + before_request: session is bound to ONE party (?db= mismatch → 403)
│   │   ├── auth.py               # PIN login/logout by operator id (picker; PIN-only legacy path
│   │   │                         # refuses ambiguous PINs), roster for the login screen,
│   │   │                         # operator mgmt (throttle checked BEFORE verification)
│   │   ├── products.py           # Products, sections, subsections, tags, CSV import/export
│   │   ├── cart.py               # Session-based cart: add/remove/update/discount (discounts audited)
│   │   ├── orders.py             # Atomic checkout (tab guest name), history, reports, delete (restores stock,
│   │   │                         # audited), open tabs + settle (operator level)
│   │   ├── printer.py            # Thermal print: text→ESC/POS→device, test ticket, baud detect (admin-only)
│   │   ├── parties.py            # Party CRUD, duplicate (catalog only), backups/restore, date edit,
│   │   │                         # recap CSV (admin-only, like every sales figure)
│   │   ├── settings.py           # Party settings get/set
│   │   └── guard.py              # is_admin() + @require_admin + @require_operator (single guard source)
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py         # PartyDatabase + TemplatesDatabase ctx managers (rollback on error),
│   │   │                         # validate_db_name, NO implicit party creation (PartyNotFoundError,
│   │   │                         # create=True for owners; default fallback), integrity quarantine, schema-drift guard,
│   │   │                         # open-counts + lifecycle lock
│   │   ├── schema.py             # PARTY_SCHEMA (+idempotency_keys) + TEMPLATES_SCHEMA (WAL, FK, indexes)
│   │   └── templates_db.py       # Template CRUD (sections, products, tags, settings)
│   ├── models/                   # REMOVED in Phase R (was dead in prod — services return dicts)
│   ├── services/                 # Business logic + SQL
│   │   ├── __init__.py
│   │   ├── product_service.py    # Catalog, sections, tags, CSV, search (ALL-tags filter)
│   │   ├── order_service.py      # checkout_order (atomic + idempotent, tab guest name, money rounded to
│   │   │                         # 2 decimals at the write boundary), list_open_tabs + settle_tab
│   │   │                         # (BEGIN IMMEDIATE, flips the method, records the payment), summaries/CSV, delete+restore
│   │   ├── party_service.py      # Party create from template/empty, duplicate, delete (locked, guarded)
│   │   │                         # (template-created parties get default operators: login-ready)
│   │   ├── backup_service.py     # VACUUM INTO snapshots (quick_check, due parties only), prune/restore,
│   │   │                         # background scheduler (hourly prune, 5-min interval cache;
│   │   │                         # atomic publish via .tmp+rename; checkpoint_all() for shutdown)
│   │   ├── printer_service.py    # ESC/POS raw (USB lp / serial termios), ASCII-safe, no deps
│   │   ├── settings_service.py   # DEFAULT_SETTINGS + get_effective_settings()
│   │   │                         # (device keys global in shared DB, party keys per DB;
│   │   │                         #  WAL+busy_timeout conn, short-TTL device cache)
│   │   └── auth_service.py       # PBKDF2 PIN hashing (+legacy upgrade), verification by id,
│   │   │                         # ambiguous-PIN refusal, unique operator names, audit log
│   ├── ui/
│   │   ├── templates/            # Jinja2 pages
│   │   │   ├── base.html
│   │   │   ├── login.html        # party + operator picker + PIN (root route /), keyboard-first
│   │   │   ├── pos.html          # Sections sidebar + product grid + cart + bottom bar
│   │   │   ├── admin.html        # Products, parties, operators, tags, settings
│   │   │   └── dashboard.html    # Reports (admin-only data) + till close (any operator) + print
│   │   └── static/
│   │       ├── css/style.css          # "banco pulito" tokens + one component system (shells, buttons, tables, modals)
│   │       └── js/
│   │           ├── app.js            # fetchJSON, formatCurrency, escapeHtml, auth check, toasts, banner
│   │           │                   # + active-party helpers (get/set/switch, cart cleared on switch)
│   │           ├── pos.js            # Sections/products/cart/checkout (idempotency key), SSE sync, Shift+L / Shift+Click
│   │           │                   # + cart restored from the session on load
│   │           │                   # + party switcher (uses active party, header shows it)
│   │           ├── admin.js          # Dashboard, products, tags, parties (data-i18n)
│   │           ├── dashboard.js      # Report generation, printing
│   │           └── translations.js   # i18n (en/it)
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── config.py             # HOST, PORT, DATA_DIR, PARTY_DB_DIR, per-install SECRET_KEY (frozen builds: DATA_DIR=~/.posziona, POSZIONA_DATA_DIR wins)
│   │   ├── events.py             # SSE broadcaster: broadcast(), sse_response(), prune/heartbeat,
│   │   │                         # 50-listener cap (503 past it)
│   │   │                         # (yields OUTSIDE listener lock, idle listeners stay fresh)
│   │   ├── session_lock.py       # Serializes cart/session writes per (party, operator):
│   │   │                         # lock + re-center onto server truth (parallel adds never lost)
│   │   ├── rate_limit.py         # In-memory fixed-window throttle (login attempts, consumed
│   │   │                         # before the PIN is verified)
│   │   ├── instance_lock.py      # Single-server OS lock (split-brain guard)
│   │   ├── discovery.py          # LAN UDP beacon (server) + discover() (client) + default
│   │   │                         # TCP /24 fallback scan (POSZIONA_NO_TCP_SCAN=1 opts out);
│   │   │                         # opt-out POSZIONA_NO_BEACON
│   │   └── logger.py             # Rotating logs → app/logs/pos.log (5MB × 4); frozen → DATA_DIR/logs
│   ├── logs/                     # Runtime logs (pos.log; .gitkeep tracked)
│   └── data/                     # Runtime data (gitignored): parties/*.db, templates.db, backups/
├── scripts/
│   ├── run_pos.py                # Launcher (path bootstrap + parse_args from app.main)
│   └── entry_point.py            # PyInstaller entry point (frozen path handling + parse_args)
├── tests/                        # 309 tests, prune-hard: one behavior per test (see PLAN.md Phase R)
│   ├── conftest.py               # app/client/clean_db fixtures (fresh test_party.db, wipe templates
│   │                             # + settings/session caches — module caches must not leak across tests)
│   ├── unit/test_frozen_config.py  # frozen DATA_DIR default + POSZIONA_DATA_DIR override
│   ├── unit/test_gui_fallback.py   # lazy pywebview, Qt retry, --gui-check doctor, syswin auto-setup
│   ├── unit/test_events.py         # SSE liveness: yield outside lock, idle heartbeat freshness
│   ├── unit/test_discovery.py      # UDP beacon round-trip, menu pick, TCP /24 fallback scan, opt-outs
│   ├── unit/test_admin_settings_ui.py  # settings scope grouping, no dead knobs, i18n keys
│   ├── unit/test_printer.py        # ESC/POS bytes vs fake device file, API end-to-end, admin-only detect
│   ├── unit/test_startup_modes.py  # mode prompt, no silent servers, login identity
│   ├── unit/test_login_template.py # login shell markers, node --check inline JS
│   ├── integration/test_party_selection.py  # sale+login land in selected party DB only
│   ├── integration/test_crash_safety.py     # cookie, SIGTERM exit 0, WAL kill, kill9 loop
│   └── integration/              # test_api, test_parties, test_products_search_bulk, test_csv_import,
│                                 # test_stock_and_availability, test_tags,
│                                 # test_default_tags_and_zero_total, test_manual_party_and_products,
│                                 # test_resilience, test_checkout_atomic, test_backups,
│                                 # test_auth_hardening, test_schema_drift, test_ops_safety,
│                                 # test_instance_lock, test_settings_scope,
│                                 # test_review_fixes (admin-only settings/reports, live discount,
│                                 # tendered validation, snapshot robustness)
├── docs/
│   ├── requirements.md           # Feature requirements + MVP scope + unicenta lessons
│   └── ui.md                     # UI contract: tokens, shells, responsive targets, verification
├── .github/                      # CI builds
├── AppImageBuilder.yml
├── build_linux.sh / build_onefile.spec    # Linux onefile binary
├── build_exe.bat / build_exe.spec / build_onefile.spec  # Windows EXE
├── pyproject.toml                # name posziona 0.2.1, Flask + pywebview (+ pyserial/pywin32 for printers)
├── pytest.ini                    # testpaths=tests, python_files=test_*.py
├── requirements.txt / requirements-dev.txt
├── README.md                     # Quick start
├── PLAN.md                       # Phases + status
├── ARCHITECTURE.md               # Layers, DB strategy, SSE, flows
└── CODEBASE_EXPLANATION.md       # Long-form walkthrough (partly stale, see Notes)
```

### Notes
- `docs/ui.md` is the UI contract (tokens, shells, responsive targets, verification). The templates and `style.css` follow it; keep them in sync.
- `data/` is gitignored (runtime DBs + backups + `.secret_key` for session signing). This is the *source-mode* location (`app/data/`); **frozen builds** (PyInstaller/AppImage/EXE) use `~/.posziona/` instead, because the bundle's temp dir is wiped on exit — `POSZIONA_DATA_DIR` env var overrides both.
- `data/backups/` holds timestamped `VACUUM INTO` snapshots (see backup scheduler).
- There is **no** `app/models/` (removed Phase R: dead in prod) — order/party logic lives in `order_service.py` / `party_service.py` returning dicts. (Older docs mention models; they're gone.)
- There is **no** `payment_service.py` / `report_service.py` — checkout = `order_service.checkout_order()` (atomic + idempotent), reports = `order_service.get_sales_summary()` etc.
- There is **no** `app/utils/helpers.py` — helpers live in services + `config.py`.
- `db` scoping is `?db=<name>` query param, validated by `validate_db_name()` (traversal rejected with 400); frontend currently hardcodes `default`.
- `index.html` was removed — `/` renders `login.html` directly.
