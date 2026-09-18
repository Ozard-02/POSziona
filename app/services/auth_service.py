"""
Authentication service for Posziona.
Handles PIN-based login for operators and admin access.
"""

import hashlib
import hmac
import secrets
from app.database.connection import PartyDatabase
from app.utils.logger import get_logger

logger = get_logger('auth')

# PBKDF2 cost: high enough to make 4-digit PIN guessing expensive,
# low enough (~50ms) for old kiosk hardware on every login.
_PBKDF2_ITERATIONS = 100_000

# Factory PINs shipped in every fresh database. Logins using one get a
# must_change_pin flag so the UI can force a change (see api/auth.py).
_FACTORY_PINS = ('0000', '1234')


# ============================================================
# PIN HASHING & VERIFICATION
# ============================================================

def hash_pin(pin):
    """Hash a PIN with salted PBKDF2-SHA256 (stdlib, offline-friendly).

    Format: pbkdf2$<iterations>$<salt_hex>$<hash_hex>
    """
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', pin.encode('utf-8'), salt, _PBKDF2_ITERATIONS)
    return f'pbkdf2${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}'


def _is_legacy_hash(stored_hash):
    """Legacy format was a bare unsalted SHA-256 hex digest."""
    return isinstance(stored_hash, str) and '$' not in stored_hash and len(stored_hash) == 64


def needs_upgrade(stored_hash):
    """True when a stored hash uses the legacy unsalted format."""
    return _is_legacy_hash(stored_hash)


def verify_pin(provided_pin, stored_hash):
    """Verify a PIN against a stored hash using constant-time comparison.

    Accepts both the current PBKDF2 format and legacy SHA-256 hashes
    (migrated transparently on next successful login).
    """
    if not provided_pin or not stored_hash:
        return False
    try:
        if _is_legacy_hash(stored_hash):
            computed = hashlib.sha256(provided_pin.encode('utf-8')).hexdigest()
            return hmac.compare_digest(computed, stored_hash)
        parts = stored_hash.split('$')
        if len(parts) != 4 or parts[0] != 'pbkdf2':
            return False
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected = parts[3]
        computed = hashlib.pbkdf2_hmac(
            'sha256', provided_pin.encode('utf-8'), salt, iterations
        ).hex()
        return hmac.compare_digest(computed, expected)
    except (ValueError, TypeError):
        return False


def is_factory_pin(pin):
    """True if the provided PIN is one of the shipped factory defaults."""
    return any(hmac.compare_digest(pin, factory) for factory in _FACTORY_PINS)


# ============================================================
# OPERATOR AUTHENTICATION
# ============================================================

def authenticate_operator(db_name, pin):
    """
    Authenticate an operator using their PIN.
    Returns the operator dict if valid, None otherwise.

    Hashes are salted, so matching means verifying the PIN against each
    active operator (tiny table — negligible cost). A successful login
    with a legacy unsalted hash transparently upgrades it to PBKDF2.
    """
    with PartyDatabase(db_name) as conn:
        rows = conn.execute(
            "SELECT * FROM operators WHERE is_active = 1"
        ).fetchall()

        for row in rows:
            if verify_pin(pin, row['pin_hash']):
                if needs_upgrade(row['pin_hash']):
                    conn.execute(
                        "UPDATE operators SET pin_hash = ? WHERE id = ?",
                        (hash_pin(pin), row['id'])
                    )
                    conn.commit()
                    logger.info(f"Upgraded legacy PIN hash for '{row['name']}'")
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
