# Party POS System
A lightweight, offline Point of Sale application for parties/events.

## Quick Start

```bash
# Setup (one-time)
cd party-pos
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or venv\Scripts\activate  # Windows
pip install -r requirements.txt

# Run
python scripts/run_pos.py
```

## Tech Stack

- **Backend**: Python + Flask
- **UI**: pywebview (native desktop window wrapping Flask app)
- **Database**: SQLite (one file per party + one shared templates DB)
- **Frontend**: HTML/CSS/JS served by Flask

## Structure

See `STRUCTURE.md` for full project layout.

## Status: In Development - Core + API + Models + UI structure complete

<!-- 
TODO_PROGRESS_TRACKER
=====================
DONE (Core infrastructure):
[x] requirements.txt
[x] requirements-dev.txt
[x] pyproject.toml
[x] .gitignore
[x] app/__init__.py          # Flask app factory
[x] app/main.py              # Entry point with pywebview
[x] app/utils/config.py      # Configuration
[x] app/utils/logger.py      # Logging setup
[x] app/utils/helpers.py     # Helper functions
[x] scripts/run_pos.py       # Launch script
[x] app/api/__init__.py      # API blueprint with status check
[x] app/ui/templates/base.html
[x] app/ui/templates/login.html
[x] app/ui/templates/pos.html
[x] app/ui/templates/admin.html
[x] app/ui/static/css/style.css
[x] app/ui/static/js/app.js
[x] app/ui/static/js/pos.js
[x] pytest.ini

DONE (Database layer):
[x] app/database/connection.py  # PartyDatabase, TemplatesDatabase, snapshots
[x] app/database/schema.py      # Party + templates schemas
[x] app/database/templates_db.py # Template CRUD operations

DONE (Services):
[x] app/services/__init__.py
[x] app/services/auth_service.py    # PIN auth, operator management
[x] app/services/product_service.py  # Product catalog, sections, imports
[x] app/services/order_service.py    # Cart→order, payments, reports
[x] app/services/party_service.py    # Party CRUD, templates→parties
[x] app/services/settings_service.py # Settings management

DONE (API Endpoints):
[x] app/api/__init__.py      # Registers all sub-blueprints
[x] app/api/products.py      # Sections, subsections, products, CSV import
[x] app/api/cart.py          # Session-based cart, discounts
[x] app/api/orders.py        # Checkout, order history, reports
[x] app/api/parties.py       # Party CRUD, template management
[x] app/api/auth.py          # Operator/PIN login, admin access

DONE (Models):
[x] app/models/__init__.py   # BaseModel base class
[x] app/models/product.py    # Product, display name/price, stock checks
[x] app/models/cart.py       # Cart, CartItem, discounts, totals
[x] app/models/order.py      # Order, OrderItem, Payment
[x] app/models/party.py      # Party model
[x] app/models/operator.py   # Operator (admin/operator roles)
[x] app/models/audit_log.py  # AuditLogEntry

DONE (UI Templates):
[x] app/ui/templates/base.html
[x] app/ui/templates/login.html
[x] app/ui/templates/pos.html
[x] app/ui/templates/admin.html
[x] app/ui/static/css/style.css
[x] app/ui/static/js/app.js (base utilities)
[x] app/ui/static/js/pos.js (POS screen logic)
[x] app/ui/static/js/admin.js (admin panel logic)

TESTS (Priority 6):
[x] tests/conftest.py
[x] tests/unit/test_models.py   # 6 tests - models, schema validation
[x] tests/integration/test_api.py # 9 tests - full workflow, auth, CRUD
[x] tests/integration/test_csv_import.py # 2 CSV import tests
[x] tests/integration/test_parties.py # 2 party creation/duplication tests

NEXT_TASK: None - MVP infrastructure 95% complete, ready for pywebview launcher test

ROADMAP (In Progress):
[x] Dashboard items sold now displays Price, Stock, and Available columns (in addition to Qty)
[x] Right-click on any item row in the Sales Dashboard opens a context menu to:
    - Edit Price (in-place prompt, updates product price live)
    - Set Available / Set Unavailable (toggles product is_active flag live)
[x] Product edit API now supports is_active (availability) updates via PUT /products/products/<id>

FUTURE ROADMAP (planned):
[ ] Operator can edit availability and price directly while viewing item properties in the dashboard
[ ] Items in the dashboard display both quantity sold and current stock / availability status
[ ] Right-click on an item in the dashboard to change its properties (price, availability, stock)
-->
