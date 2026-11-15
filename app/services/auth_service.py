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


def needs_upgrade(stored_hash):
    """True when a stored hash uses the legacy unsalted format
    (bare SHA-256 hex digest)."""
    return isinstance(stored_hash, str) and '$' not in stored_hash and len(stored_hash) == 64


def verify_pin(provided_pin, stored_hash):
    """Verify a PIN against a stored hash using constant-time comparison.

    Accepts both the current PBKDF2 format and legacy SHA-256 hashes
    (migrated transparently on next successful login).
    """
    if not provided_pin or not stored_hash:
        return False
    try:
        if needs_upgrade(stored_hash):
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

class AmbiguousPinError(ValueError):
    """A PIN matches more than one active operator.

    Only reachable through the PIN-only login (the UI sends the operator
    id). Answering with the first match in `ORDER BY role, name` silently
    attributed the sale — and the audit trail — to the wrong person.
    """


def _upgrade_legacy_hash(conn, row, pin):
    """Rewrite a legacy unsalted hash after a successful verification.

    Conditional on the exact hash we verified: if an admin PIN reset
    committed between our SELECT and this UPDATE, the reset wins (R10)
    instead of being silently overwritten by the old PIN's hash.
    """
    if not needs_upgrade(row['pin_hash']):
        return
    cur = conn.execute(
        "UPDATE operators SET pin_hash = ? WHERE id = ? AND pin_hash = ?",
        (hash_pin(pin), row['id'], row['pin_hash'])
    )
    conn.commit()
    if cur.rowcount:
        logger.info(f"Upgraded legacy PIN hash for '{row['name']}'")


def authenticate_operator_by_id(db_name, operator_id, pin):
    """Verify a PIN against ONE operator (what the login picker sends).

    One PBKDF2 per attempt instead of one per active operator, and the
    identity is explicit: a PIN shared by two operators can no longer
    land on whoever happens to sort first. Returns None for unknown,
    inactive, or wrong PIN (no information about which).
    """
    if not pin:
        return None
    with PartyDatabase(db_name) as conn:
        row = conn.execute(
            "SELECT * FROM operators WHERE id = ? AND is_active = 1",
            (operator_id,)
        ).fetchone()
        if not row or not verify_pin(pin, row['pin_hash']):
            return None
        _upgrade_legacy_hash(conn, row, pin)
        logger.info(f"Operator '{row['name']}' authenticated by id "
                    f"(role={row['role']})")
        return dict(row)


def authenticate_operator(db_name, pin):
    """Authenticate by PIN alone (legacy API path; the UI sends the id).

    Hashes are salted, so matching means verifying the PIN against each
    active operator (tiny table). More than one match is an ERROR, not a
    pick: raise AmbiguousPinError so the caller can ask for the name
    instead of writing the sale under someone else's identity.
    """
    if not pin:
        return None
    with PartyDatabase(db_name) as conn:
        rows = conn.execute(
            "SELECT * FROM operators WHERE is_active = 1"
        ).fetchall()
        matches = [row for row in rows if verify_pin(pin, row['pin_hash'])]
        if len(matches) > 1:
            raise AmbiguousPinError(
                'That PIN is used by more than one operator — '
                'choose your name and try again')
        if not matches:
            return None
        row = matches[0]
        _upgrade_legacy_hash(conn, row, pin)
        logger.info(f"Operator '{row['name']}' authenticated (role={row['role']})")
        return dict(row)


def authenticate_admin(db_name, pin, operator_id=None):
    """Authenticate an admin, by pin-only or by id. None when not admin."""
    operator = (authenticate_operator_by_id(db_name, operator_id, pin)
                if operator_id is not None else authenticate_operator(db_name, pin))
    if operator and operator['role'] == 'admin':
        return operator
    return None


# ============================================================
# OPERATOR MANAGEMENT
# ============================================================

def get_all_operators(db_name):
    """Get all operators (never the PIN hash — it is not needed by the UI)."""
    with PartyDatabase(db_name) as conn:
        rows = conn.execute(
            "SELECT id, name, role, is_active FROM operators ORDER BY role, name"
        ).fetchall()
        return [dict(row) for row in rows]


def get_operator_roster(db_name):
    """Active operators for the login picker (id + name + role only).

    Deliberately public (the login screen needs it before anyone is
    authenticated) and deliberately minimal: no hashes, no inactive
    accounts, no timestamps.
    """
    with PartyDatabase(db_name) as conn:
        rows = conn.execute(
            "SELECT id, name, role FROM operators "
            "WHERE is_active = 1 ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [dict(row) for row in rows]


def create_operator(db_name, name, pin, role='operator'):
    """Create a new operator (names are unique per party, case-insensitive)."""
    with PartyDatabase(db_name) as conn:
        clash = conn.execute(
            "SELECT 1 FROM operators WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        if clash:
            # Two "Mario" would make the login picker and the audit trail
            # ambiguous — the whole point of showing the name.
            raise ValueError(f'An operator named "{name}" already exists')
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
