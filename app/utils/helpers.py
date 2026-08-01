"""
Utility helper functions.
"""
import os
import uuid
from .config import PARTY_DB_DIR


def get_party_db_path(party_name):
    """Get the database file path for a given party."""
    safe_name = "".join(c for c in party_name if c.isalnum() or c in (' ', '-', '_'))
    filename = f"{safe_name}.db"
    return os.path.join(PARTY_DB_DIR, filename)


def generate_id():
    """Generate a unique ID string."""
    return str(uuid.uuid4())


def format_currency(amount, currency='€'):
    """Format a monetary amount for display."""
    return f"{currency}{amount:.2f}"


def is_valid_pin(pin):
    """Validate a PIN code (4 digits)."""
    if not pin:
        return False
    return pin.isdigit() and len(pin) == 4
