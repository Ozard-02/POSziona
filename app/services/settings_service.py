"""
Settings service for Posziona.
Handles application and party-level settings.

Two tiers:
- DEVICE settings (the counter hardware/venue: printer, language,
  currency, payment defaults, cashier toggles) live ONCE in the shared
  templates DB and apply to every party. Editing them on any party
  changes them everywhere.
- PARTY settings (receipt content, operators, snapshots) live in each
  party DB as before.

Reads merge DEFAULTS < device < party. Writes route by key; writing a
device key also deletes any stale party-level row (migrate-on-write),
so old per-party values can never shadow the global one.
"""
import sqlite3

from app.services.party_service import get_party_settings, update_party_setting
from app.utils.config import TEMPLATES_DB
from app.utils.logger import get_logger

logger = get_logger('services.settings')

# Device-level: invariant across parties.
GLOBAL_KEYS = frozenset({
    'currency',
    'tax_rate',
    'default_payment_method',
    'skip_cash_tender',
    'auto_checkout',
    'language',
    'printer_model',
    'printer_path',
    'printer_baud',
    'printer_cols',
    'printer_cut',
    'auto_logout_minutes',
    'server_name',
})


# ============================================================
# DEFAULT SETTINGS
# ============================================================

DEFAULT_SETTINGS = {
    'currency': '€',
    'tax_rate': '0.0',
    'default_payment_method': 'cash',  # None to skip, or a method name
    'skip_cash_tender': '0',  # Skip cash tender screen, auto-accept exact amount
    'auto_checkout': '0',  # When both skip_cash_tender and auto_checkout are set, checkout goes straight to receipt
    'language': 'en',  # Supported: en, it
    'default_operator_id': None,
    'printer_model': None,
    'printer_path': '',  # '' = disabled (browser print); 'auto' or device path
    'printer_baud': '9600',  # serial only (/dev/ttyUSB*, /dev/ttyS*)
    'printer_cols': '42',  # receipt width, safe default for 80mm
    'printer_cut': '1',  # 1 = partial cut after receipt
    'receipt_header': '',
    'receipt_footer': 'Thank you for your purchase!',
    'auto_logout_minutes': 0,  # 0 = no auto-logout
    'snapshot_interval_minutes': 5,
    'snapshot_keep_count': 12,  # how many snapshots to retain
    'split_receipts': '0',  # 1 = print one receipt per section
    'print_recovery_receipt': '0',  # 1 = print/display the recovery receipt
    'server_name': '',  # tag shown to connecting clients ('' = machine hostname)
}


def get_device_settings():
    """All device-level settings from the shared DB (missing = {})."""
    import os
    if not os.path.exists(TEMPLATES_DB):
        return {}
    conn = sqlite3.connect(TEMPLATES_DB)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS global_settings "
            "(key TEXT PRIMARY KEY, value TEXT)"
        )
        rows = conn.execute("SELECT key, value FROM global_settings").fetchall()
        return {row[0]: row[1] for row in rows}
    finally:
        conn.close()


def update_device_setting(key, value):
    """Write one device-level setting to the shared DB."""
    import os
    os.makedirs(os.path.dirname(TEMPLATES_DB), exist_ok=True)
    conn = sqlite3.connect(TEMPLATES_DB)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS global_settings "
            "(key TEXT PRIMARY KEY, value TEXT)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO global_settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit()
    finally:
        conn.close()


def get_effective_settings(db_name):
    """
    Get all settings for a party, merged with defaults.
    Precedence: DEFAULTS < device (all parties) < party (this party).
    Returns a dict of key -> value, using defaults for missing keys.
    """
    result = DEFAULT_SETTINGS.copy()
    result.update(get_device_settings())
    result.update(get_party_settings(db_name))
    return result


def update_setting(db_name, key, value):
    """Update a single setting: device keys go global, rest stay per-party.

    Writing a device key also removes any stale party-level row, so an
    old per-party value can never shadow the global one.
    """
    if key in GLOBAL_KEYS:
        update_device_setting(key, value)
        from app.database.connection import PartyDatabase
        with PartyDatabase(db_name) as conn:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            conn.commit()
        return
    return update_party_setting(db_name, key, value)


def get_setting(db_name, key, default=None):
    """Get a single setting value, falling back to default."""
    settings = get_effective_settings(db_name)
    return settings.get(key, default)


def get_default_payment_method(db_name):
    """Get the default payment method (returns None if not set)."""
    settings = get_effective_settings(db_name)
    method = settings.get('default_payment_method', 'cash')
    return method if method else None
