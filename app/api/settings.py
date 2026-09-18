"""
Settings API endpoints.
Handles party-level settings like default payment method, currency, tax rate, etc.
"""

from flask import Blueprint, request, jsonify
from app.services.settings_service import get_effective_settings, get_setting, update_setting
from app.utils.events import broadcast
from app.utils.logger import get_logger

logger = get_logger('api.settings')

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/default-payment', methods=['GET'])
def get_default_payment():
    """Get the default payment method setting for the active party."""
    db = request.args.get('db', 'default')
    method = get_setting(db, 'default_payment_method', 'cash')
    return jsonify({'default_payment_method': method if method else None})


@settings_bp.route('/default-payment', methods=['POST'])
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
def update_settings():
    """Update multiple settings at once."""
    db = request.args.get('db', 'default')
    data = request.get_json() or {}

    for key, value in data.items():
        if key in [
            'currency', 'tax_rate', 'default_payment_method',
            'skip_cash_tender', 'auto_checkout', 'language',
            'default_operator_id', 'printer_model',
            'receipt_header', 'receipt_footer',
            'auto_logout_minutes', 'snapshot_interval_minutes',
            'snapshot_keep_count',
            'split_receipts', 'print_recovery_receipt',
        ]:
            update_setting(db, key, str(value))
            broadcast('settings_update', {
                'db': db,
                'key': key,
                'value': str(value)
            })

    return jsonify({'message': 'Settings updated'})
