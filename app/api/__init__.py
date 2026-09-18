"""
API blueprint for Posziona.
Registers all sub-blueprints, SSE events endpoint, and health check.
"""

from flask import Blueprint, jsonify

api_bp = Blueprint('api', __name__)

# SSE (Server-Sent Events) for live updates
from app.utils.events import sse_response, broadcast  # noqa: E402

# Import and register sub-blueprints
from app.api.products import products_bp
from app.api.cart import cart_bp
from app.api.orders import orders_bp
from app.api.parties import parties_bp
from app.api.auth import auth_bp
from app.api.settings import settings_bp

# Register sub-blueprints under their namespaces
api_bp.register_blueprint(products_bp, url_prefix='/products')
api_bp.register_blueprint(cart_bp, url_prefix='/cart')
api_bp.register_blueprint(orders_bp, url_prefix='/orders')
api_bp.register_blueprint(parties_bp, url_prefix='/parties')
api_bp.register_blueprint(auth_bp, url_prefix='/auth')
api_bp.register_blueprint(settings_bp, url_prefix='/settings')


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
    return jsonify({
        'status': 'degraded' if degraded else 'ok',
        'version': '0.1.1',
        'db_writable': db_writable,
        'disk_free_mb': disk_free_mb,
    })
