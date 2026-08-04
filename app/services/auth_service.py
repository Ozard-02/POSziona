"""
Authentication service for Posziona.
Handles PIN-based login for operators and admin access.
"""

import hashlib
import hmac
from app.database.connection import PartyDatabase
from app.utils.logger import get_logger

logger = get_logger('auth')


# ============================================================
# PIN HASHING & VERIFICATION
# ============================================================

def hash_pin(pin):
    """Hash a PIN using SHA-256."""
    return hashlib.sha256(pin.encode('utf-8')).hexdigest()


def verify_pin(provided_pin, stored_hash):
    """Verify a PIN against a stored hash using constant-time comparison."""
    if not provided_pin or not stored_hash:
        return False
    computed = hash_pin(provided_pin)
    return hmac.compare_digest(computed, stored_hash)


# ============================================================
# OPERATOR AUTHENTICATION
# ============================================================

def authenticate_operator(db_name, pin):
    """
    Authenticate an operator using their PIN.
    Returns the operator dict if valid, None otherwise.
    """
    with PartyDatabase(db_name) as conn:
        row = conn.execute(
            "SELECT * FROM operators WHERE pin_hash = ? AND is_active = 1",
            (hash_pin(pin),)
        ).fetchone()

        if row:
            logger.info(f"Operator '{row['name']}' authenticated (role={row['role']})")
            return dict(row)
        return None


def authenticate_admin(db_name, pin):
    """
    Authenticate an admin using their PIN.
    Returns the operator dict if valid admin, None otherwise.
    """
    operator = authenticate_operator(db_name, pin)
    if operator and operator['role'] == 'admin':
        return operator
    return None


# ============================================================
# OPERATOR MANAGEMENT
# ============================================================

def get_all_operators(db_name):
    """Get all operators."""
    with PartyDatabase(db_name) as conn:
        rows = conn.execute(
            "SELECT id, name, role, is_active, pin_hash FROM operators ORDER BY role, name"
        ).fetchall()
        return [dict(row) for row in rows]


def get_operator_by_id(db_name, operator_id):
    """Get an operator by ID."""
    with PartyDatabase(db_name) as conn:
        row = conn.execute(
            "SELECT * FROM operators WHERE id = ?", (operator_id,)
        ).fetchone()
        return dict(row) if row else None


def create_operator(db_name, name, pin, role='operator'):
    """Create a new operator."""
    with PartyDatabase(db_name) as conn:
        conn.execute(
            "INSERT INTO operators (name, pin_hash, role, is_active) VALUES (?, ?, ?, 1)",
            (name, hash_pin(pin), role)
        )
        conn.commit()
        logger.info(f"Created operator '{name}' (role={role})")


def update_operator_pin(db_name, operator_id, new_pin):
    """Update an operator's PIN."""
    with PartyDatabase(db_name) as conn:
        conn.execute(
            "UPDATE operators SET pin_hash = ? WHERE id = ?",
            (hash_pin(new_pin), operator_id)
        )
        conn.commit()


def log_audit_event(db_name, action, details, operator_id=None):
    """Log an audit event."""
    with PartyDatabase(db_name) as conn:
        conn.execute(
            "INSERT INTO audit_log (action, details, operator_id) VALUES (?, ?, ?)",
            (action, details, operator_id)
        )
        conn.commit()
