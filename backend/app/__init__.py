from flask import Flask
import os
import utilities.logging_config as logging_config
from app.routes import bp

def create_app():
    # Configure logging to write to backend/app.log (one level up from app/)
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    log_path = os.path.join(backend_dir, "app.log")
    logging_config.configure(log_file=log_path, add_console=False)
    app = Flask(__name__)
    app.register_blueprint(bp, url_prefix="/api")
    return app
