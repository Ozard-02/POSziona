"""
Authentication API endpoints.
Handles operator login (PIN-based) and admin access.
"""

from flask import Blueprint, request, jsonify, session
from app.services.auth_service import authenticate_operator, authenticate_admin, log_audit_event
from app.utils.logger import get_logger

logger = get_logger('api.auth')

auth_bp = Blueprint('auth', __name__)


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
    data = request.get_json()
    pin = data.get('pin', '').strip()

    if not pin:
        return jsonify({'error': 'PIN is required'}), 400

    operator = authenticate_operator(db, pin)
    if not operator:
        return jsonify({'error': 'Invalid PIN'}), 403

    # Store operator info in session
    session['operator_id'] = operator['id']
    session['operator_name'] = operator['name']
    session['operator_role'] = operator['role']

    log_audit_event(db, 'operator_login', f"Operator '{operator['name']}' logged in", operator['id'])

    return jsonify({
        'message': 'Login successful',
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
    data = request.get_json()
    pin = data.get('pin', '').strip()

    if not pin:
        return jsonify({'error': 'PIN is required'}), 400

    operator = authenticate_admin(db, pin)
    if not operator:
        return jsonify({'error': 'Invalid admin PIN'}), 403

    session['operator_id'] = operator['id']
    session['operator_name'] = operator['name']
    session['operator_role'] = operator['role']

    log_audit_event(db, 'admin_login', f"Admin '{operator['name']}' logged in", operator['id'])

    return jsonify({
        'message': 'Admin login successful',
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
    from app.services.auth_service import get_all_operators
    db = request.args.get('db', 'default')

    if session.get('operator_role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403

    return jsonify(get_all_operators(db))


@auth_bp.route('/operators', methods=['POST'])
def create_operator():
    """Create a new operator (admin only)."""
    from app.services.auth_service import create_operator
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
        create_operator(db, name, pin, role)
        log_audit_event(db, 'operator_created', f"Operator '{name}' created", session.get('operator_id'))
        return jsonify({'message': f'Operator "{name}" created'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@auth_bp.route('/operators/<int:operator_id>/reset-pin', methods=['POST'])
def reset_pin(operator_id):
    """Reset an operator's PIN (admin only)."""
    from app.services.auth_service import update_operator_pin
    db = request.args.get('db', 'default')

    if session.get('operator_role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403

    data = request.get_json()
    new_pin = data.get('pin', '').strip()

    if not new_pin or not new_pin.isdigit() or len(new_pin) != 4:
        return jsonify({'error': 'Valid 4-digit PIN is required'}), 400

    try:
        update_operator_pin(db, operator_id, new_pin)
        log_audit_event(db, 'pin_reset', f"PIN reset for operator id={operator_id}", session.get('operator_id'))
        return jsonify({'message': 'PIN updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
