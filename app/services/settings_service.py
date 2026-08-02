"""
Settings service for Party POS.
Handles application and party-level settings.
"""

from app.services.party_service import get_party_settings, update_party_setting
from app.utils.logger import get_logger

logger = get_logger('services.settings')


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
    'receipt_header': '',
    'receipt_footer': 'Thank you for your purchase!',
    'auto_logout_minutes': 0,  # 0 = no auto-logout
    'snapshot_interval_minutes': 5,
    'split_receipts': '0',  # 1 = print one receipt per section
    'print_recovery_receipt': '0',  # 1 = print/display the recovery receipt
}


def get_effective_settings(db_name):
    """
    Get all settings for a party, merged with defaults.
    Returns a dict of key -> value, using defaults for missing keys.
    """
    party_settings = get_party_settings(db_name)
    result = DEFAULT_SETTINGS.copy()
    result.update(party_settings)
    return result


def update_setting(db_name, key, value):
    """Update a single setting for the active party."""
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
