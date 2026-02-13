from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from .models import db, bcrypt
from .config import Config
from .routes import auth_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # ✅ Enable CORS fully (for Postman & React)
    CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

    # ✅ Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    JWTManager(app)

    # ✅ Register Blueprints
    app.register_blueprint(auth_bp)

    # ✅ Create DB tables
    with app.app_context():
        db.create_all()

    return app