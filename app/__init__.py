"""
Flask application factory for Party POS.
"""
from flask import Flask
from flask_cors import CORS
import os


def create_app(config_class=None):
    """Create and configure the Flask application."""
    app = Flask(__name__, 
                static_folder=os.path.join(os.path.dirname(__file__), 'ui', 'static'),
                template_folder=os.path.join(os.path.dirname(__file__), 'ui', 'templates'))
    
    if config_class:
        app.config.from_object(config_class)
    else:
        app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
        app.config['DATABASE_DIR'] = 'data'

    # Configure session cookies for proper persistence
    # These ensure cookies are sent correctly in all contexts (including pywebview)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours
    
    CORS(app)
    
    # Register blueprints
    from app.api import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Register routes
    @app.route('/')
    def index():
        from flask import render_template
        return render_template('login.html')

    @app.route('/pos')
    def pos():
        from flask import render_template
        return render_template('pos.html', party_name='Party')

    @app.route('/admin')
    def admin():
        from flask import render_template
        return render_template('admin.html')
    
    return app
