"""Flask web application for the UI"""
from flask import Flask
from app.core.config import settings


def create_app():
    """Create Flask application"""
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.secret_key = settings.FLASK_SECRET_KEY
    app.debug = settings.FLASK_DEBUG

    # Register blueprints
    from app.web.routes import main_bp, workflow_bp, api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(workflow_bp, url_prefix='/workflow')
    app.register_blueprint(api_bp, url_prefix='/api/v1')

    return app
