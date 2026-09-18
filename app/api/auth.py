"""
Authentication API endpoints.
Handles operator login (PIN-based) and admin access.
"""

from flask import Blueprint, request, jsonify, session
from app.services.auth_service import (
    authenticate_operator,
    authenticate_admin,
    is_factory_pin,
    log_audit_event,
    get_all_operators,
    create_operator as _create_operator,
    update_operator_pin as _update_operator_pin,
)
from app.utils.rate_limit import check as _rate_check
from app.utils.logger import get_logger

logger = get_logger('api.auth')

auth_bp = Blueprint('auth', __name__)

# 4-digit PINs fall fast to unlimited guessing: throttle FAILED logins per
# IP. Only failures consume budget (a success resets it), so legitimate
# operators who mistype occasionally are never locked out, while sustained
# guessing hits the wall.
_LOGIN_LIMIT = 10
_LOGIN_WINDOW_SECONDS = 60


def _login_failed():
    """Record a failed login; returns a 429 response when throttled, else None."""
    key = f"login:{request.remote_addr}"
    if not _rate_check(key, _LOGIN_LIMIT, _LOGIN_WINDOW_SECONDS):
        logger.warning(f"Login rate limit exceeded for {request.remote_addr}")
        return jsonify({'error': 'Too many login attempts, try again in a minute'}), 429
    return None


def _login_succeeded():
    """Forgive past failures for this IP after a successful login."""
    from app.utils.rate_limit import reset as _rate_reset
    _rate_reset(f"login:{request.remote_addr}")


# ============================================================
# LOGIN / LOGOUT
# ============================================================

@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Authenticate an operator using PIN.
    Returns the operator info if successful.
    """
    db = request.args.get('db', 'default')
    data = request.get_json() or {}
    pin = data.get('pin', '').strip()

    if not pin:
        return jsonify({'error': 'PIN is required'}), 400

    operator = authenticate_operator(db, pin)
    if not operator:
        throttled = _login_failed()
        if throttled:
            return throttled
        return jsonify({'error': 'Invalid PIN'}), 403

    _login_succeeded()

    # Store operator info in session
    session['operator_id'] = operator['id']
    session['operator_name'] = operator['name']
    session['operator_role'] = operator['role']

    log_audit_event(db, 'operator_login', f"Operator '{operator['name']}' logged in", operator['id'])

    return jsonify({
        'message': 'Login successful',
        'must_change_pin': is_factory_pin(pin),
        'operator': {
            'id': operator['id'],
            'name': operator['name'],
            'role': operator['role']
        }
    })


@auth_bp.route('/login/admin', methods=['POST'])
def login_admin():
    """
    Authenticate an admin using PIN.
    Returns the operator info if successful admin.
    """
    db = request.args.get('db', 'default')
    data = request.get_json() or {}
    pin = data.get('pin', '').strip()

    if not pin:
        return jsonify({'error': 'PIN is required'}), 400

    operator = authenticate_admin(db, pin)
    if not operator:
        throttled = _login_failed()
        if throttled:
            return throttled
        return jsonify({'error': 'Invalid admin PIN'}), 403

    _login_succeeded()

    session['operator_id'] = operator['id']
    session['operator_name'] = operator['name']
    session['operator_role'] = operator['role']

    log_audit_event(db, 'admin_login', f"Admin '{operator['name']}' logged in", operator['id'])

    return jsonify({
        'message': 'Admin login successful',
        'must_change_pin': is_factory_pin(pin),
        'operator': {
            'id': operator['id'],
            'name': operator['name'],
            'role': operator['role']
        }
    })


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Log out the current operator."""
    db = request.args.get('db', 'default')
    operator_id = session.get('operator_id')

    if operator_id:
        log_audit_event(db, 'operator_logout', 'Operator logged out', operator_id)

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
def list_operators():
    """List all operators (admin only)."""
    db = request.args.get('db', 'default')

    if session.get('operator_role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403

    return jsonify(get_all_operators(db))


@auth_bp.route('/operators', methods=['POST'])
def create_operator():
    """Create a new operator (admin only)."""
    db = request.args.get('db', 'default')

    if session.get('operator_role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403

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
def reset_pin(operator_id):
    """Reset an operator's PIN (admin only)."""
    db = request.args.get('db', 'default')

    if session.get('operator_role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403

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
