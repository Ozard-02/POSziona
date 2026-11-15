"""
API blueprint for Posziona.
Registers all sub-blueprints, SSE events endpoint, and health check.
"""

from flask import Blueprint, jsonify, request, session

api_bp = Blueprint('api', __name__)

# SSE (Server-Sent Events) for live updates
from app.utils.events import sse_response  # noqa: E402

# Import and register sub-blueprints
from app.api.products import products_bp
from app.api.cart import cart_bp
from app.api.orders import orders_bp
from app.api.parties import parties_bp
from app.api.auth import auth_bp
from app.api.settings import settings_bp
from app.api.printer import printer_bp

# Register sub-blueprints under their namespaces
api_bp.register_blueprint(products_bp, url_prefix='/products')
api_bp.register_blueprint(cart_bp, url_prefix='/cart')
api_bp.register_blueprint(orders_bp, url_prefix='/orders')
api_bp.register_blueprint(parties_bp, url_prefix='/parties')
api_bp.register_blueprint(auth_bp, url_prefix='/auth')
api_bp.register_blueprint(settings_bp, url_prefix='/settings')
api_bp.register_blueprint(printer_bp, url_prefix='/printer')


@api_bp.before_request
def _enforce_party_binding():
    """A session is authenticated for exactly ONE party database.

    Operator ids (and PINs) are per-party, and `?db=` is client-supplied.
    Without this check a login on party A authorised sales on party B:
    the order was attributed to whoever happens to share that id there,
    and when the id did not exist the sale failed with an opaque 500
    (FOREIGN KEY) that could never succeed on retry.

    Login/logout are exempt — logging in on another party is how an
    operator switches shift. Requests without `?db=` (party list, status,
    SSE) are untouched.
    """
    if not session.get('operator_id'):
        return None
    # Nested blueprints report the full chain ("api.auth"): compare the
    # leaf, not the parent.
    if (request.blueprint or '').split('.')[-1] == 'auth':
        return None
    requested = request.args.get('db')
    if requested is None:
        return None
    if requested != session.get('auth_db'):
        return jsonify({
            'error': 'You are logged in to a different party. '
                     'Log in again to switch party.',
            'code': 'party_mismatch',
        }), 403
    return None


@api_bp.route('/events')
def sse_events():
    """SSE stream for live updates (product availability, etc.).

    POS clients connect here to receive broadcast events in real time.
    """
    return sse_response()


@api_bp.route('/status')
def status():
    """Health check endpoint (kiosk monitoring).

    Reports db_writable=False / status=degraded instead of failing when
    the data directory is not writable — SQLite can't save sales then,
    and the operator must know before taking orders.
    """
    import os
    import shutil
    from app.utils.config import DATA_DIR, PARTY_DB_DIR

    try:
        os.makedirs(PARTY_DB_DIR, exist_ok=True)
        db_writable = os.access(PARTY_DB_DIR, os.W_OK)
    except OSError:
        db_writable = False

    try:
        disk_free_mb = shutil.disk_usage(DATA_DIR).free // (1024 * 1024)
    except OSError:
        disk_free_mb = -1

    degraded = not db_writable
    from app.utils.config import APP_VERSION
    from app.utils.discovery import get_server_name
    from app.utils.events import listener_count
    return jsonify({
        'status': 'degraded' if degraded else 'ok',
        'version': APP_VERSION,
        'server_name': get_server_name(),
        'db_writable': db_writable,
        'disk_free_mb': disk_free_mb,
        'connected_screens': listener_count(),
    })
