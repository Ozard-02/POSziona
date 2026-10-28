"""
Thermal printer API: push preformatted receipt text to ESC/POS device.

The browser builds receipt text (pos.js buildReceipt); these endpoints
only convert + send. Operator login required (paper costs money);
port detection is admin-only.
"""
from flask import Blueprint, request, jsonify, session

from app.api.guard import require_admin

from app.services.printer_service import (
    build_test_ticket, detect_serial, print_text,
    resolve_device, DEFAULT_COLS,
)

printer_bp = Blueprint('printer', __name__)


def _require_operator():
    if not session.get('operator_id'):
        return jsonify({'error': 'Operator not logged in'}), 403
    return None


@printer_bp.route('/print', methods=['POST'])
def print_receipt():
    """Print client-formatted receipt text on the configured printer."""
    denied = _require_operator()
    if denied:
        return denied
    db = request.args.get('db', 'default')
    data = request.get_json() or {}
    try:
        result = print_text(db, data.get('text', ''), cut=data.get('cut'))
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 500


@printer_bp.route('/test', methods=['POST'])
def test_print():
    """Print a sample ticket (admin settings 'test print' button)."""
    denied = _require_operator()
    if denied:
        return denied
    db = request.args.get('db', 'default')
    try:
        _, _, cols, _ = resolve_device(db)
    except ValueError:
        cols = DEFAULT_COLS
    try:
        result = print_text(db, build_test_ticket(cols))
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 500


@printer_bp.route('/detect', methods=['POST'])
@require_admin
def detect_printer():
    """Probe a serial path for an answering ESC/POS printer (admin only).

    Body: {"path": "/dev/ttyUSB0"}. Returns {"baud": N} or 400 when
    nothing answers (wrong cable, printer off, brltty holding the port).
    Admin-only like the printer settings it feeds: it opens the given
    path read/write and writes probe bytes to any serial device.
    """
    data = request.get_json() or {}
    path = (data.get('path') or '').strip()
    if not path:
        return jsonify({'error': 'Serial path required'}), 400
    try:
        baud = detect_serial(path)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 500
    if baud is None:
        return jsonify({'error': f'No printer answers on {path}'}), 400
    return jsonify({'baud': baud, 'path': path})

