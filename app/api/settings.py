"""
Settings API endpoints.
Handles party-level settings like default payment method, currency, tax rate, etc.
"""

from flask import Blueprint, request, jsonify
from app.api.guard import require_admin
from app.services.settings_service import (
    DEFAULT_SETTINGS, get_effective_settings, get_setting, update_setting)
from app.utils.events import broadcast

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/default-payment', methods=['GET'])
def get_default_payment():
    """Get the default payment method setting for the active party."""
    db = request.args.get('db', 'default')
    method = get_setting(db, 'default_payment_method', 'cash')
    return jsonify({'default_payment_method': method if method else None})


@settings_bp.route('/default-payment', methods=['POST'])
@require_admin
def set_default_payment():
    """Set the default payment method for the active party."""
    db = request.args.get('db', 'default')
    data = request.get_json() or {}
    method = data.get('method')

    if method is not None and method != 'none':
        update_setting(db, 'default_payment_method', method)
    else:
        update_setting(db, 'default_payment_method', '')

    broadcast('settings_update', {
        'db': db,
        'key': 'default_payment_method',
        'value': method or None
    })
    return jsonify({'message': 'Default payment method updated', 'method': method or None})


@settings_bp.route('/', methods=['GET'])
def get_settings():
    """Get all effective settings for the active party."""
    db = request.args.get('db', 'default')
    return jsonify(get_effective_settings(db))


@settings_bp.route('/', methods=['POST'])
@require_admin
def update_settings():
    """Update multiple settings at once (admin only).

    Admin-gated like every other mutating route: printer_path is opened
    for writing by the print endpoints, so an open settings write would
    let any device on the LAN point it at an arbitrary file.
    """
    db = request.args.get('db', 'default')
    data = request.get_json() or {}

    for key, value in data.items():
        if key in DEFAULT_SETTINGS:
            # Preserve None (stored as NULL = "unset") instead of the
            # string 'None', which would e.g. become a bogus printer path.
            value = None if value is None else str(value)
            update_setting(db, key, value)
            broadcast('settings_update', {
                'db': db,
                'key': key,
                'value': value
            })

    return jsonify({'message': 'Settings updated'})
