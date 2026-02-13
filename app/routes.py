# from flask import Blueprint, render_template

# main = Blueprint('main', __name__)


# @main.route('/')
# def index():
#     return render_template('index.html')


# app.py

from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, jwt_required, get_jwt_identity
)
from .models import db, User

auth_bp = Blueprint('auth', __name__)

# ------------------ SIGNUP ------------------
@auth_bp.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    full_name = data.get('full_name')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'learner')

    if not all([full_name, email, password]):
        return jsonify({'error': 'Please fill in all required fields'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 400

    new_user = User(full_name=full_name, email=email, password=password, role=role)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': 'User registered successfully'}), 201


# ------------------ LOGIN ------------------
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not all([email, password]):
        return jsonify({'error': 'Email and password are required'}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid email or password'}), 401

    # token = create_access_token(identity={'email': user.email, 'role': user.role})
    token = create_access_token(identity=str(user.id))
    return jsonify({
        'message': 'Login successful',
        'access_token': token,
        'user': {
            'full_name': user.full_name,
            'email': user.email,
            'role': user.role
        }
    }), 200


# ------------------ PROFILE (Protected) ------------------
@auth_bp.route('/profile', methods=['GET'])
@jwt_required()
def profile():
    current_user = get_jwt_identity()
    return jsonify({'logged_in_as': current_user}), 200