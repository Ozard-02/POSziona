"""
Flask application factory for Posziona.
"""
import os

from flask import Flask, jsonify, render_template
from flask_cors import CORS

from app.utils.logger import get_logger


def create_app(config_class=None):
    """Create and configure the Flask application."""
    app = Flask(__name__,
                static_folder=os.path.join(os.path.dirname(__file__), 'ui', 'static'),
                template_folder=os.path.join(os.path.dirname(__file__), 'ui', 'templates'))

    if config_class:
        app.config.from_object(config_class)
    else:
        from app.utils.config import get_secret_key
        app.config['SECRET_KEY'] = get_secret_key()
        app.config['DATABASE_DIR'] = 'data'

    # Configure session cookies for proper persistence
    # These ensure cookies are sent correctly in all contexts (including pywebview)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

    CORS(app)

    # Validation errors (bad ?db= names, bad input) are client errors —
    # always JSON, never an HTML stack page the kiosk UI can't parse.
    @app.errorhandler(ValueError)
    def handle_value_error(e):
        return jsonify({'error': str(e)}), 400

    @app.errorhandler(400)
    def handle_bad_request(e):
        # Covers malformed JSON bodies (Flask raises BadRequest) etc.
        return jsonify({'error': 'Bad request'}), 400

    @app.errorhandler(404)
    def handle_not_found(e):
        return jsonify({'error': 'Not found'}), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(e):
        return jsonify({'error': 'Method not allowed'}), 405

    @app.errorhandler(500)
    def handle_internal_error(e):
        # Safety net: no stack trace or HTML ever leaks to the kiosk —
        # the UI can parse this and (for checkout) safely retry.
        logger = get_logger('app')
        logger.error(f"Unhandled error: {e}")
        return jsonify({'error': 'Internal server error. It is safe to retry.'}), 500

    # Register blueprints
    from app.api import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    # Register routes
    @app.route('/')
    def index():
        return render_template('login.html')

    @app.route('/pos')
    def pos():
        return render_template('pos.html', party_name='Posziona')

    @app.route('/admin')
    def admin():
        return render_template('admin.html')

    @app.route('/dashboard')
    def dashboard():
        return render_template('dashboard.html')

    return app
