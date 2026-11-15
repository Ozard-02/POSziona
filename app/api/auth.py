"""
Authentication API endpoints.
Handles operator login (PIN-based) and admin access.
"""

from flask import Blueprint, request, jsonify, session
from app.api.guard import require_admin
from app.services.auth_service import (
    AmbiguousPinError,
    authenticate_operator,
    authenticate_operator_by_id,
    authenticate_admin,
    is_factory_pin,
    log_audit_event,
    get_all_operators,
    get_operator_roster,
    create_operator as _create_operator,
    update_operator_pin as _update_operator_pin,
)
from app.utils.rate_limit import check as _rate_check
from app.utils.session_lock import forget_session
from app.utils.logger import get_logger

logger = get_logger('api.auth')

auth_bp = Blueprint('auth', __name__)

# 4-digit PINs fall fast to unlimited guessing: throttle login ATTEMPTS
# per IP. The check happens BEFORE the PIN is verified (and a success
# resets the budget), so a correct PIN is also refused once the window is
# spent — otherwise the limiter would only decorate the response while
# every guess still got a full PBKDF2 verification (i.e. unlimited
# brute force at hashing speed).
_LOGIN_LIMIT = 10
_LOGIN_WINDOW_SECONDS = 60


def _login_attempt_allowed():
    """Consume one attempt; returns a 429 response when throttled, else None."""
    key = f"login:{request.remote_addr}"
    if not _rate_check(key, _LOGIN_LIMIT, _LOGIN_WINDOW_SECONDS):
        logger.warning(f"Login rate limit exceeded for {request.remote_addr}")
        return jsonify({
            'error': 'Too many login attempts, try again in a minute',
            'code': 'throttled',
        }), 429
    return None


def _login_succeeded():
    """Forgive past attempts for this IP after a successful login."""
    from app.utils.rate_limit import reset as _rate_reset
    _rate_reset(f"login:{request.remote_addr}")


def _operator_id_from(data):
    """Parse the optional operator id from the body. Raises ValueError."""
    raw = data.get('operator_id')
    if raw is None or raw == '':
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError('operator_id must be a number')


def _authenticate(db, pin, operator_id, admin_only):
    """Run the right verification. Returns (operator or None, error or None).

    With an operator id the PIN is checked against that one account (one
    PBKDF2, explicit identity). Without it we fall back to the legacy
    PIN-only scan, which must report ambiguity instead of guessing.
    """
    try:
        if admin_only:
            return authenticate_admin(db, pin, operator_id=operator_id), None
        if operator_id is not None:
            return authenticate_operator_by_id(db, operator_id, pin), None
        return authenticate_operator(db, pin), None
    except AmbiguousPinError as e:
        return None, (jsonify({'error': str(e), 'code': 'ambiguous_pin'}), 400)


# ============================================================
# LOGIN / LOGOUT
# ============================================================

def _establish_session(db, operator):
    """Store the authenticated identity, bound to the party it came from.

    The party DB is part of the login: operator ids are per-party, so a
    session not bound to the party it authenticated against would sell on
    an unrelated DB under someone else's id (see api/__init__.py
    `_enforce_party_binding`). The cookie is permanent (24 h) so closing
    the browser/client never wipes the login — or the unsent cart.
    """
    session['operator_id'] = operator['id']
    session['operator_name'] = operator['name']
    session['operator_role'] = operator['role']
    session['auth_db'] = db
    session.permanent = True


def _login_response(db, operator, pin, message):
    return jsonify({
        'message': message,
        # Factory PIN: the UI sends the operator to the admin panel to
        # change it before the shift starts.
        'must_change_pin': is_factory_pin(pin),
        'operator': {
            'id': operator['id'],
            'name': operator['name'],
            'role': operator['role']
        }
    })


@auth_bp.route('/login', methods=['POST'])
def login():
    """Authenticate an operator: body {pin} and optionally {operator_id}.

    The UI always sends operator_id (its picker makes the identity
    explicit). {pin} alone still works for API clients, but an ambiguous
    PIN is refused instead of attributed to whoever sorts first.
    """
    db = request.args.get('db', 'default')
    data = request.get_json() or {}
    pin = str(data.get('pin', '')).strip()

    if not pin:
        return jsonify({'error': 'PIN is required'}), 400
    try:
        operator_id = _operator_id_from(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    throttled = _login_attempt_allowed()
    if throttled:
        return throttled

    operator, error = _authenticate(db, pin, operator_id, admin_only=False)
    if error:
        return error
    if not operator:
        return jsonify({'error': 'Invalid PIN', 'code': 'invalid_pin'}), 403

    _login_succeeded()
    _establish_session(db, operator)
    log_audit_event(db, 'operator_login',
                    f"Operator '{operator['name']}' logged in", operator['id'])
    return _login_response(db, operator, pin, 'Login successful')


@auth_bp.route('/login/admin', methods=['POST'])
def login_admin():
    """Authenticate an admin (body {pin}, optionally {operator_id}).

    Kept for scripts/older clients; the UI uses /login and routes by the
    role it gets back.
    """
    db = request.args.get('db', 'default')
    data = request.get_json() or {}
    pin = str(data.get('pin', '')).strip()

    if not pin:
        return jsonify({'error': 'PIN is required'}), 400
    try:
        operator_id = _operator_id_from(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    throttled = _login_attempt_allowed()
    if throttled:
        return throttled

    operator, error = _authenticate(db, pin, operator_id, admin_only=True)
    if error:
        return error
    if not operator:
        return jsonify({'error': 'Invalid admin PIN', 'code': 'invalid_pin'}), 403

    _login_succeeded()
    _establish_session(db, operator)
    log_audit_event(db, 'admin_login',
                    f"Admin '{operator['name']}' logged in", operator['id'])
    return _login_response(db, operator, pin, 'Admin login successful')


@auth_bp.route('/operators/roster', methods=['GET'])
def operator_roster():
    """Active operators of a party, for the login picker.

    Public by necessity (the login screen has no session yet) and minimal:
    id, name, role. No PIN hashes, no inactive accounts.
    """
    db = request.args.get('db', 'default')
    return jsonify(get_operator_roster(db))


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Log out the current operator."""
    db = request.args.get('db', 'default')
    operator_id = session.get('operator_id')

    if operator_id:
        log_audit_event(db, 'operator_logout', 'Operator logged out', operator_id)
        # No server-side cart truth should outlive the login it belonged to
        forget_session((db, operator_id))

    session.clear()
    return jsonify({'message': 'Logged out'})


@auth_bp.route('/status', methods=['GET'])
def get_auth_status():
    """Check if an operator is logged in."""
    if 'operator_id' in session:
        return jsonify({
            'logged_in': True,
            'operator': {
                'id': session.get('operator_id'),
                'name': session.get('operator_name'),
                'role': session.get('operator_role')
            }
        })
    return jsonify({'logged_in': False})


# ============================================================
# OPERATOR MANAGEMENT (Admin only)
# ============================================================

@auth_bp.route('/operators', methods=['GET'])
@require_admin
def list_operators():
    """List all operators (admin only)."""
    db = request.args.get('db', 'default')


    return jsonify(get_all_operators(db))


@auth_bp.route('/operators', methods=['POST'])
@require_admin
def create_operator():
    """Create a new operator (admin only)."""
    db = request.args.get('db', 'default')


    data = request.get_json()
    name = data.get('name', '').strip()
    pin = data.get('pin', '').strip()
    role = data.get('role', 'operator')

    if not name or not pin or not pin.isdigit() or len(pin) != 4:
        return jsonify({'error': 'Valid name and 4-digit PIN are required'}), 400

    try:
        _create_operator(db, name, pin, role)
        log_audit_event(db, 'operator_created', f"Operator '{name}' created", session.get('operator_id'))
        return jsonify({'message': f'Operator "{name}" created'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@auth_bp.route('/operators/<int:operator_id>/reset-pin', methods=['POST'])
@require_admin
def reset_pin(operator_id):
    """Reset an operator's PIN (admin only)."""
    db = request.args.get('db', 'default')


    data = request.get_json()
    new_pin = data.get('pin', '').strip()

    if not new_pin or not new_pin.isdigit() or len(new_pin) != 4:
        return jsonify({'error': 'Valid 4-digit PIN is required'}), 400

    try:
        _update_operator_pin(db, operator_id, new_pin)
        log_audit_event(db, 'pin_reset', f"PIN reset for operator id={operator_id}", session.get('operator_id'))
        return jsonify({'message': 'PIN updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
