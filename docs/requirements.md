# Posziona System - Requirements

## Overview
A lightweight, PC-based Point of Sale application for parties/events. Runs as a web app on localhost across 2+ laptops, each with an independent local SQLite database. Designed to be simple, fast, and plug-and-play — no complex setup, no Java runtime, no MySQL server.

## Platform & Deployment
- **Runtime**: Python + Flask (backend) + HTML/CSS/JS (frontend served locally)
- **UI Container**: pywebview (native desktop window wrapping the Flask app)
  - Lightweight alternative to Electron — uses system webview, minimal overhead
  - Opens in its own window (not a browser tab), fullscreen/kiosk-ready
  - Cross-platform: Windows/macOS/Linux
- **Cross-platform**: Runs identically on Windows and Linux with minimal code duplication
- **Deployment**: Each laptop runs its own Flask server on localhost + pywebview wrapper
- **Database**: Separate SQLite file per party (no MySQL, no connection timeouts)
- **Future**: Central server sync (a laptop can act as both client and server)

## Core Features

### 1. Product Catalog
- Products organized in 2-level sections: Section > Subsection > Products
  - Example: Drinks > Coffee > Small Coffee, Big Coffee
- Text-only products (no images)
- Each variant is a separate item (Small Coffee ≠ Big Coffee)
- Product fields: name, price, SKU, stock count (optional)
- Per-product daily stock limit (decreases with each sale, unlimited option)
- Import products from CSV
- Manage products via admin mode

### 2. POS Workflow (Operator)
1. Select a product from the grid (organized by section > subsection)
2. Item is added to cart with default quantity 1 (single click)
3. Cart updates live with item total
4. "Checkout" button proceeds to payment
5. If default payment method toggle is set: skip payment selection
6. If not set: select payment method (cash, card, etc.)
7. Print/display receipt
8. Return to main screen with empty cart

### 3. UI Layout
- **Left sidebar**: product sections (2 levels: section > subsection)
  - Click a subsection to load products into the central grid
- **Central grid**: products in the selected subsection
  - Product buttons with name + price (text only)
  - Large, touch-friendly buttons
  - Scrollable if more products than fit
- **Right sidebar**: current order recap
  - List of items in cart
  - Quantity, price, line total
  - Running subtotal
  - Updates in real-time
- **Bottom bar**: action buttons
  - "Checkout" / "Pay" button
  - "Clear" / "New Order" button
  - "Discount" / "Notes" buttons (optional)
- **No search bar**: all items visible, organized by sections
- **Touch-optimized**: large buttons, minimal typing

### 4. Cart Management
- Add items with single click (default qty 1)
- Adjust quantity or remove items before finalizing
- Apply discounts (percentage or fixed amount)
- Order notes (e.g., "no ice", "extra spicy")
- Save/retrieve open tabs (for running balances)
- Clear cart / new order

### 5. Checkout & Payment
- Multiple payment methods:
  - Cash (enter amount given, calculate change)
  - Card (record only — actual payment handled externally)
  - Digital wallet / QR code (record only)
  - "On tab" / account-based (for known guests)
- **Default payment method toggle**: set one method as default, skip selection screen
  - Still allow override when needed
- Tender screen: enter amount received, show change due
- Print/display receipt
- Refund / return support

### 6. Receipt / Bill
- Text-only receipt (no images or logos)
- Header: party name, date
- Itemized list with prices and totals
- Tax breakdown (if applicable)
- Footer: thank you message or social handles
- Thermal receipt printer support (model TBD — user will specify later)
- "Bill" vs "Receipt" distinction:
  - Bill: itemized list before payment
  - Receipt: proof of payment

### 7. Sales Tracking & Reporting
- Real-time sales dashboard (total revenue, items sold)
- Sales by section / product
- Hourly sales breakdown
- Payment method totals (cash vs card vs other)
- End-of-party report (Z report)
- Export sales data as CSV
- Refund history
- **Item insertion log**: track every product added/removed from cart with
  timestamp, operator, and reason (discount, void, correction)
- **Daily logging with metrics**: per-day summary log (total transactions,
  total revenue, top products, payment method breakdown)
- **Recap of all items sold**: list of every item sold and total amount earned

### 8. Party Management
- Create parties by name and dates
- Each party has its own SQLite database file
- Duplicate parties (copy an existing party to create a new one)
- Assign dates to parties
- Switch between parties

### 9. Admin Mode
- Separate admin login (PIN or password)
- Manage products, sections, prices
- Import products from CSV
- Manage parties (create, duplicate, assign dates)
- View reports (items sold, total amount earned, sales dashboard)
- Configure settings (payment methods, default toggle, tax rates)
- All data kept in the database (no external files except exports/backups)

### 10. User Roles & Security
- Operator mode (standard POS use)
- Admin mode (settings, reports, product management)
- PIN or password login
- Activity log (who did what)

### 11. Settings & Configuration
- Party name and details
- Tax rate(s) (single or tiered)
- Currency
- Printer selection and configuration (deferred — thermal printer model TBD)
- Payment methods (cash, card, digital wallet, tab)
- Default payment method toggle
- Receipt template (text-only)
- Backup / restore (periodic snapshots)

## Technical Requirements

### Database
- SQLite (one file per party)
- WAL mode for concurrent access
- Automatic checkpoints
- Periodic snapshots (copy DB file to backup folder)
- Schema tables:
  - `products` (id, name, price, sku, section_id, subsection_id, daily_limit, stock_count)
  - `sections` (id, name)
  - `subsections` (id, name, section_id)
  - `cart_items` (id, product_id, quantity, price, order_id)
  - `orders` (id, timestamp, total, payment_method, operator_id)
  - `payments` (id, order_id, method, amount, tendered, change_due)
  - `parties` (id, name, start_date, end_date)
  - `settings` (key, value)
  - `audit_log` (id, timestamp, action, details, operator_id)
  - `daily_sales` (date, total_revenue, total_transactions, top_products)

### Hardware Integration (deferred)
- Thermal receipt printer (ESC/POS) — model TBD
- Barcode scanner (optional)
- Card reader (optional — record only, no actual payment processing)
- Cash drawer (optional)

### Resilience
- SQLite WAL mode + auto-checkpoints
- Periodic snapshots (configurable interval)
- No data loss if system crashes mid-party

## MVP Scope
Must-have features for first release:
1. Product catalog (SQLite, hardcoded products for now)
2. 2-level section organization (section > subsection > products)
3. Add to cart with single click (default qty 1, no search bar)
4. View/edit cart (adjust qty, remove items)
5. Checkout with default payment method toggle (skip selection if set)
6. Payment method selection if toggle not set (cash, card, etc.)
7. Text-only receipt display on screen (thermal printer later)
8. Sales counter (running total of sales for the session)
9. Separate SQLite DB per party, WAL mode, periodic snapshots
10. Party management (create party by name + dates, duplicate parties)
11. Admin mode (separate login, manage products, view reports)
12. Import products from CSV
13. All data in database (nothing external)

## Future Enhancements (v2+)
- Thermal receipt printing (when printer is specified)
- Full reports (items sold, total amount earned)
- Product stock limits
- Discounts
- Customer-facing display (secondary screen)
- Central server sync (a laptop can be both client and server)
- Multi-date party support
- Pre-order via QR code
- Loyalty / punch card system
- Gift cards
- Multi-language support
- Dark mode for low-light environments

## Constraints
- No internet required (fully offline)
- No Java runtime (unlike unicenta POS)
- No MySQL server (unlike unicenta POS)
- No complex setup — download, run, start selling
- Text-only UI elements (no images for products)
- Thermal receipt printer only (no inkjet/laser)
- Single operator at a time per laptop (no concurrent operators)

## Lessons from unicenta POS (what to avoid)
- Java-based with font rendering issues
- MySQL connection timeout problems
- Rigid UI layout requiring XML editing
- Complex setup requiring database configuration
- Steep learning curve for customization
- Cash close errors and missing reports
- No easy backup/restore procedure
