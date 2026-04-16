from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
import uuid
import os
import json
import shutil
import tempfile
import subprocess
from pathlib import Path
import hmac
import hashlib
import base64

from services.ai_service import CourseAIService

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///course_generator.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

CORS(app)
db = SQLAlchemy(app)
ai_service = CourseAIService()

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_ROOT = BASE_DIR / 'user_uploads'
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
ALLOWED_UPLOAD_EXTENSIONS = {'.csv', '.xlsx'}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
CODE_EXECUTION_TIMEOUT_SECONDS = 8
DISALLOWED_CODE_PATTERNS = [
    r'\bimport\s+os\b',
    r'\bimport\s+sys\b',
    r'\bimport\s+subprocess\b',
    r'\bimport\s+socket\b',
    r'\bimport\s+pathlib\b',
    r'\bimport\s+shutil\b',
    r'\bimport\s+requests\b',
    r'\bfrom\s+os\s+import\b',
    r'\bfrom\s+subprocess\s+import\b',
    r'\bopen\s*\(',
    r'\beval\s*\(',
    r'\bexec\s*\(',
    r'__import__\s*\(',
]


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    current_role = db.Column(db.String(120), nullable=True)
    experience_level = db.Column(db.String(50), nullable=True)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    target_role = db.Column(db.String(120), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    experience_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(50), default='generated')
    course_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AssessmentAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    target_role = db.Column(db.String(120), nullable=False)
    score = db.Column(db.Float, nullable=False)
    strengths_json = db.Column(db.Text, nullable=False)
    weaknesses_json = db.Column(db.Text, nullable=False)
    answers_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Certificate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    certificate_id = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    issued_at = db.Column(db.DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# STATELESS HMAC-SIGNED TOKEN SYSTEM
# Tokens are signed with SECRET_KEY so they survive server restarts.
# Format (before base64): "<user_id>:<hmac_sha256_hex>"
# ─────────────────────────────────────────────────────────────────────────────

def _token_signature(payload: str) -> str:
    """Compute HMAC-SHA256 of payload using the app's SECRET_KEY."""
    return hmac.new(
        app.config['SECRET_KEY'].encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def issue_token(user_id: int) -> str:
    """Create a signed, base64-encoded token for the given user_id."""
    payload = str(user_id)
    sig = _token_signature(payload)
    raw = f"{payload}:{sig}"
    return base64.urlsafe_b64encode(raw.encode('utf-8')).decode('utf-8')


def verify_token(token: str):
    """
    Verify a token and return the user_id (int) if valid, else None.
    Constant-time comparison prevents timing attacks.
    """
    try:
        raw = base64.urlsafe_b64decode(token.encode('utf-8')).decode('utf-8')
        payload, provided_sig = raw.rsplit(':', 1)
        expected_sig = _token_signature(payload)
        if hmac.compare_digest(expected_sig, provided_sig):
            return int(payload)
        return None
    except Exception:
        return None


TABLE_CONFIG = {
    'users': {
        'model': User,
        'pk': 'id',
        'label': 'Users',
        'list_fields': ['id', 'full_name', 'email', 'current_role', 'experience_level', 'is_admin', 'created_at'],
        'editable_fields': ['full_name', 'email', 'current_role', 'experience_level', 'is_admin'],
        'create_fields': ['full_name', 'email', 'password', 'current_role', 'experience_level', 'is_admin'],
        'required_fields': ['full_name', 'email', 'password'],
    },
    'courses': {
        'model': Course,
        'pk': 'id',
        'label': 'Courses',
        'list_fields': ['id', 'public_id', 'user_id', 'target_role', 'title', 'experience_type', 'status', 'created_at'],
        'editable_fields': ['user_id', 'target_role', 'title', 'experience_type', 'status', 'course_json'],
        'create_fields': ['user_id', 'target_role', 'title', 'experience_type', 'status', 'course_json'],
        'required_fields': ['user_id', 'target_role', 'title', 'experience_type', 'course_json'],
    },
    'assessment_attempts': {
        'model': AssessmentAttempt,
        'pk': 'id',
        'label': 'Assessment Attempts',
        'list_fields': ['id', 'user_id', 'target_role', 'score', 'strengths_json', 'weaknesses_json', 'answers_json', 'created_at'],
        'editable_fields': ['user_id', 'target_role', 'score', 'strengths_json', 'weaknesses_json', 'answers_json'],
        'create_fields': ['user_id', 'target_role', 'score', 'strengths_json', 'weaknesses_json', 'answers_json'],
        'required_fields': ['user_id', 'target_role', 'score', 'strengths_json', 'weaknesses_json', 'answers_json'],
    },
    'certificates': {
        'model': Certificate,
        'pk': 'id',
        'label': 'Certificates',
        'list_fields': ['id', 'certificate_id', 'user_id', 'course_id', 'issued_at'],
        'editable_fields': ['user_id', 'course_id'],
        'create_fields': ['user_id', 'course_id'],
        'required_fields': ['user_id', 'course_id'],
    },
}


BOOLEAN_FIELDS = {'is_admin'}
INTEGER_FIELDS = {'id', 'user_id', 'course_id'}
FLOAT_FIELDS = {'score'}
JSON_TEXT_FIELDS = {'course_json', 'strengths_json', 'weaknesses_json', 'answers_json'}
READONLY_FIELDS = {'id', 'public_id', 'certificate_id', 'created_at', 'issued_at'}



def serialize_user(user: User) -> dict:
    return {
        'id': user.id,
        'full_name': user.full_name,
        'email': user.email,
        'current_role': user.current_role,
        'experience_level': user.experience_level,
        'is_admin': bool(user.is_admin),
    }



def _normalize_value(field: str, value):
    if value is None:
        return None
    if field in BOOLEAN_FIELDS:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
    if field in INTEGER_FIELDS:
        return int(value)
    if field in FLOAT_FIELDS:
        return float(value)
    if field in JSON_TEXT_FIELDS:
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return value



def serialize_record(table_name: str, record):
    config = TABLE_CONFIG[table_name]
    data = {}
    for field in config['list_fields']:
        value = getattr(record, field)
        if isinstance(value, datetime):
            data[field] = value.isoformat()
        else:
            data[field] = value
    if table_name == 'courses':
        try:
            parsed = json.loads(record.course_json) if record.course_json else None
        except Exception:
            parsed = None
        data['course_json_pretty'] = json.dumps(parsed, indent=2) if parsed is not None else (record.course_json or '')
    if table_name == 'assessment_attempts':
        for key in ['strengths_json', 'weaknesses_json', 'answers_json']:
            raw_value = getattr(record, key)
            try:
                data[f'{key}_pretty'] = json.dumps(json.loads(raw_value), indent=2)
            except Exception:
                data[f'{key}_pretty'] = raw_value or ''
    return data



def auth_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing authorization token'}), 401
        token = auth_header.split(' ', 1)[1]
        user_id = verify_token(token)
        if not user_id:
            return jsonify({'error': 'Invalid or expired token'}), 401
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        request.current_user = user
        return func(*args, **kwargs)
    return wrapper



def admin_required(func):
    @wraps(func)
    @auth_required
    def wrapper(*args, **kwargs):
        if not getattr(request.current_user, 'is_admin', False):
            return jsonify({'error': 'Admin access required'}), 403
        return func(*args, **kwargs)
    return wrapper



def _get_table_config(table_name: str):
    config = TABLE_CONFIG.get(table_name)
    if not config:
        return None, (jsonify({'error': 'Unknown table'}), 404)
    return config, None



def _apply_record_data(record, payload: dict, allowed_fields: list[str], table_name: str, is_create: bool = False):
    config = TABLE_CONFIG[table_name]
    missing = [field for field in config['required_fields'] if is_create and field not in payload]
    if missing:
        return jsonify({'error': f'Missing required fields: {", ".join(missing)}'}), 400

    for field in allowed_fields:
        if field in READONLY_FIELDS or field not in payload:
            continue
        try:
            value = _normalize_value(field, payload.get(field))
        except (TypeError, ValueError):
            return jsonify({'error': f'Invalid value for {field}'}), 400

        if table_name == 'users':
            if field == 'email':
                value = (value or '').lower().strip()
                existing = User.query.filter(User.email == value, User.id != getattr(record, 'id', 0)).first()
                if existing:
                    return jsonify({'error': 'Email already registered'}), 409
            if field == 'password':
                if value:
                    record.set_password(value)
                continue
        setattr(record, field, value)

    if table_name == 'users' and is_create and 'password' not in payload:
        return jsonify({'error': 'password is required'}), 400

    return None


def _user_upload_dir(user_id: int) -> Path:
    path = UPLOAD_ROOT / f'user_{user_id}'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sanitize_filename(filename: str) -> str:
    safe = ''.join(ch if ch.isalnum() or ch in {'-', '_', '.'} else '_' for ch in filename)
    return safe or 'file'


def _list_user_files(user_id: int):
    directory = _user_upload_dir(user_id)
    files = []
    for item in sorted(directory.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if item.is_file():
            files.append({
                'name': item.name,
                'size': item.stat().st_size,
                'uploaded_at': datetime.utcfromtimestamp(item.stat().st_mtime).isoformat(),
                'extension': item.suffix.lower(),
            })
    return files


def _preview_file(path: Path):
    import pandas as pd

    if path.suffix.lower() == '.csv':
        df = pd.read_csv(path)
    elif path.suffix.lower() == '.xlsx':
        df = pd.read_excel(path)
    else:
        raise ValueError('Unsupported file type')

    preview_rows = df.head(20).fillna('').to_dict(orient='records')
    return {
        'columns': list(df.columns.astype(str)),
        'rows': preview_rows,
        'row_count': int(df.shape[0]),
        'column_count': int(df.shape[1]),
        'dtypes': {str(col): str(dtype) for col, dtype in df.dtypes.items()},
    }


def _validate_code(code: str):
    import re

    if not code.strip():
        return 'Please enter Python code to run.'
    if len(code) > 12000:
        return 'Code is too long. Please keep it under 12,000 characters.'
    for pattern in DISALLOWED_CODE_PATTERNS:
        if re.search(pattern, code):
            return 'This code uses a restricted operation. Please remove file-system, system, or dynamic execution calls.'
    return None


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'message': 'AI Course Generator API is running',
        'llm_enabled': ai_service.llm_enabled,
        'model': ai_service.model if ai_service.llm_enabled else None,
    })


@app.route('/api/config', methods=['GET'])
def config():
    return jsonify({
        'llm_enabled': ai_service.llm_enabled,
        'model': ai_service.model if ai_service.llm_enabled else None,
        'suggested_roles': [
            'Data Analyst',
            'Data Engineer',
            'Software Developer',
            'Machine Learning Engineer',
            'Business Analyst',
            'Frontend Developer',
        ],
    })


@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    required_fields = ['full_name', 'email', 'password']
    missing = [field for field in required_fields if not data.get(field)]
    if missing:
        return jsonify({'error': f'Missing fields: {", ".join(missing)}'}), 400

    email = data['email'].strip().lower()
    existing = User.query.filter_by(email=email).first()
    if existing:
        return jsonify({'error': 'Email already registered'}), 409

    user = User(
        full_name=data['full_name'].strip(),
        email=email,
        current_role=(data.get('current_role') or '').strip() or None,
        experience_level=(data.get('experience_level') or '').strip() or None,
        is_admin=False,
    )
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()

    token = issue_token(user.id)
    return jsonify({
        'message': 'Registration successful',
        'token': token,
        'user': serialize_user(user),
    }), 201


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid email or password'}), 401

    token = issue_token(user.id)
    return jsonify({
        'message': 'Login successful',
        'token': token,
        'user': serialize_user(user),
    })


@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    user = User.query.filter_by(email=email, is_admin=True).first()
    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid admin email or password'}), 401

    token = issue_token(user.id)
    return jsonify({
        'message': 'Admin login successful',
        'token': token,
        'user': serialize_user(user),
    })


@app.route('/api/assessment/questions', methods=['POST'])
@auth_required
def get_assessment_questions():
    data = request.get_json() or {}
    target_role = data.get('target_role')
    if not target_role:
        return jsonify({'error': 'target_role is required'}), 400

    questions = ai_service.generate_assessment_questions(target_role)
    return jsonify({'questions': questions})


@app.route('/api/assessment/evaluate', methods=['POST'])
@auth_required
def evaluate_assessment():
    data = request.get_json() or {}
    target_role = data.get('target_role')
    answers = data.get('answers', [])
    questions = data.get('questions', [])

    if not target_role or not isinstance(answers, list) or not answers:
        return jsonify({'error': 'target_role and answers are required'}), 400

    result = ai_service.evaluate_assessment(target_role, answers, questions)

    attempt = AssessmentAttempt(
        user_id=request.current_user.id,
        target_role=target_role,
        score=result['score'],
        strengths_json=json.dumps(result['strengths']),
        weaknesses_json=json.dumps(result['weaknesses']),
        answers_json=json.dumps(answers),
    )
    db.session.add(attempt)
    db.session.commit()

    return jsonify(result)


@app.route('/api/course/generate', methods=['POST'])
@auth_required
def generate_course():
    data = request.get_json() or {}
    target_role = data.get('target_role')
    experience_type = data.get('experience_type', 'beginner')
    current_role = data.get('current_role', '')
    assessment_result = data.get('assessment_result')

    if not target_role:
        return jsonify({'error': 'target_role is required'}), 400

    course_data = ai_service.generate_course(
        target_role=target_role,
        experience_type=experience_type,
        current_role=current_role,
        assessment_result=assessment_result,
    )

    course = Course(
        user_id=request.current_user.id,
        target_role=target_role,
        title=course_data['title'],
        experience_type=experience_type,
        course_json=json.dumps(course_data),
    )
    db.session.add(course)
    db.session.commit()

    return jsonify({
        'message': 'Course generated successfully',
        'course_id': course.public_id,
        'course': course_data,
    })


@app.route('/api/course/my-courses', methods=['GET'])
@auth_required
def my_courses():
    courses = Course.query.filter_by(user_id=request.current_user.id).order_by(Course.created_at.desc()).all()
    return jsonify([
        {
            'course_id': course.public_id,
            'title': course.title,
            'target_role': course.target_role,
            'experience_type': course.experience_type,
            'status': course.status,
            'created_at': course.created_at.isoformat(),
        }
        for course in courses
    ])


@app.route('/api/course/<course_id>', methods=['GET'])
@auth_required
def get_course(course_id):
    course = Course.query.filter_by(public_id=course_id, user_id=request.current_user.id).first()
    if not course:
        return jsonify({'error': 'Course not found'}), 404

    return jsonify({
        'course_id': course.public_id,
        'title': course.title,
        'target_role': course.target_role,
        'experience_type': course.experience_type,
        'status': course.status,
        'course': json.loads(course.course_json),
    })


@app.route('/api/course/<course_id>/complete', methods=['POST'])
@auth_required
def complete_course(course_id):
    course = Course.query.filter_by(public_id=course_id, user_id=request.current_user.id).first()
    if not course:
        return jsonify({'error': 'Course not found'}), 404

    course.status = 'completed'
    existing_certificate = Certificate.query.filter_by(user_id=request.current_user.id, course_id=course.id).first()
    if not existing_certificate:
        existing_certificate = Certificate(user_id=request.current_user.id, course_id=course.id)
        db.session.add(existing_certificate)
    db.session.commit()

    return jsonify({
        'message': 'Course completed successfully',
        'certificate_id': existing_certificate.certificate_id,
    })


@app.route('/api/certificate/<certificate_id>', methods=['GET'])
@auth_required
def get_certificate(certificate_id):
    certificate = Certificate.query.filter_by(certificate_id=certificate_id, user_id=request.current_user.id).first()
    if not certificate:
        return jsonify({'error': 'Certificate not found'}), 404

    course = db.session.get(Course, certificate.course_id)
    user = db.session.get(User, certificate.user_id)
    return jsonify({
        'certificate_id': certificate.certificate_id,
        'student_name': user.full_name,
        'course_title': course.title,
        'target_role': course.target_role,
        'issued_at': certificate.issued_at.isoformat(),
    })


@app.route('/api/dashboard/summary', methods=['GET'])
@auth_required
def dashboard_summary():
    user_id = request.current_user.id
    total_courses = Course.query.filter_by(user_id=user_id).count()
    completed_courses = Course.query.filter_by(user_id=user_id, status='completed').count()
    total_assessments = AssessmentAttempt.query.filter_by(user_id=user_id).count()
    recent_courses = Course.query.filter_by(user_id=user_id).order_by(Course.created_at.desc()).limit(3).all()

    return jsonify({
        'user_name': request.current_user.full_name,
        'stats': {
            'total_courses': total_courses,
            'completed_courses': completed_courses,
            'total_assessments': total_assessments,
        },
        'recent_courses': [
            {
                'course_id': course.public_id,
                'title': course.title,
                'target_role': course.target_role,
                'status': course.status,
                'created_at': course.created_at.isoformat(),
            }
            for course in recent_courses
        ]
    })


# ─────────────────────────────────────────────────────────────────────────────
# CHATBOT ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/chat', methods=['POST'])
@auth_required
def chat():
    """
    LLM-powered chatbot endpoint.

    Request body (JSON):
        message        (str, required)  – The user's current question.
        history        (list, optional) – Previous conversation turns as a list
                                          of {'role': 'user'|'assistant', 'content': '...'}.
        topic_context  (str, optional)  – Current learning context string
                                          (e.g., lesson or module title).

    Response (JSON):
        reply  (str) – The assistant's answer.
    """
    data = request.get_json() or {}

    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'message is required'}), 400

    history = data.get('history')
    if not isinstance(history, list):
        history = []

    topic_context = (data.get('topic_context') or '').strip()

    reply = ai_service.chat(
        message=message,
        history=history,
        topic_context=topic_context,
    )

    return jsonify({'reply': reply})


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/api/files', methods=['GET'])
@auth_required
def list_user_files():
    return jsonify({'files': _list_user_files(request.current_user.id)})


@app.route('/api/files/upload', methods=['POST'])
@auth_required
def upload_user_file():
    uploaded = request.files.get('file')
    if not uploaded or not uploaded.filename:
        return jsonify({'error': 'Please choose a CSV or XLSX file to upload.'}), 400

    original_name = _sanitize_filename(uploaded.filename)
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        return jsonify({'error': 'Only .csv and .xlsx files are supported.'}), 400

    user_dir = _user_upload_dir(request.current_user.id)
    stored_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}_{original_name}"
    destination = user_dir / stored_name
    uploaded.save(destination)

    if destination.stat().st_size > MAX_UPLOAD_BYTES:
        destination.unlink(missing_ok=True)
        return jsonify({'error': 'File is too large. Maximum allowed size is 10 MB.'}), 400

    preview = None
    try:
        preview = _preview_file(destination)
    except Exception as exc:
        destination.unlink(missing_ok=True)
        return jsonify({'error': f'Unable to read the uploaded file: {exc}'}), 400

    return jsonify({
        'message': 'File uploaded successfully',
        'file': {
            'name': stored_name,
            'original_name': original_name,
            'size': destination.stat().st_size,
            'uploaded_at': datetime.utcfromtimestamp(destination.stat().st_mtime).isoformat(),
            'extension': extension,
        },
        'preview': preview,
    }), 201


@app.route('/api/files/<path:filename>/preview', methods=['GET'])
@auth_required
def preview_user_file(filename):
    safe_name = Path(filename).name
    path = _user_upload_dir(request.current_user.id) / safe_name
    if not path.exists() or not path.is_file():
        return jsonify({'error': 'File not found'}), 404
    try:
        preview = _preview_file(path)
    except Exception as exc:
        return jsonify({'error': f'Unable to preview file: {exc}'}), 400
    return jsonify({'file': safe_name, 'preview': preview})


@app.route('/api/code/run', methods=['POST'])
@auth_required
def run_code():
    data = request.get_json() or {}
    code = data.get('code', '')
    selected_files = data.get('files', []) or []

    validation_error = _validate_code(code)
    if validation_error:
        return jsonify({'error': validation_error}), 400

    user_dir = _user_upload_dir(request.current_user.id)
    safe_files = []
    for name in selected_files[:5]:
        safe_name = Path(str(name)).name
        file_path = user_dir / safe_name
        if file_path.exists() and file_path.is_file():
            safe_files.append(file_path)

    runner_source = (
        "import contextlib, io, traceback\n"
        "SAFE_GLOBALS = {'__builtins__': {'print': print, 'range': range, 'len': len, 'enumerate': enumerate, 'sum': sum, 'min': min, 'max': max, 'sorted': sorted, 'list': list, 'dict': dict, 'set': set, 'tuple': tuple, 'int': int, 'float': float, 'str': str, 'bool': bool, 'abs': abs, 'round': round, 'zip': zip, 'map': map, 'filter': filter, 'any': any, 'all': all}}\n"
        "allowed_modules = {'math', 'statistics', 'random', 'json', 'csv', 'pandas', 'numpy', 'openpyxl'}\n"
        "def safe_import(name, globals=None, locals=None, fromlist=(), level=0):\n"
        "    root = name.split('.')[0]\n"
        "    if root not in allowed_modules:\n"
        "        raise ImportError(f'Module {name} is not allowed in the practice lab.')\n"
        "    return __import__(name, globals, locals, fromlist, level)\n"
        "SAFE_GLOBALS['__builtins__']['__import__'] = safe_import\n"
        "code = open('user_code.py', 'r', encoding='utf-8').read()\n"
        "stdout = io.StringIO()\n"
        "stderr = io.StringIO()\n"
        "try:\n"
        "    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):\n"
        "        exec(compile(code, 'user_code.py', 'exec'), SAFE_GLOBALS, {})\n"
        "    print(json.dumps({'status': 'ok', 'stdout': stdout.getvalue(), 'stderr': stderr.getvalue()}))\n"
        "except Exception:\n"
        "    traceback.print_exc(file=stderr)\n"
        "    print(json.dumps({'status': 'error', 'stdout': stdout.getvalue(), 'stderr': stderr.getvalue()}))\n"
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        (temp_path / 'user_code.py').write_text(code, encoding='utf-8')
        (temp_path / 'runner.py').write_text('import json\n' + runner_source, encoding='utf-8')
        for source_file in safe_files:
            shutil.copy2(source_file, temp_path / source_file.name)

        try:
            completed = subprocess.run(
                ['python', '-I', 'runner.py'],
                cwd=temp_path,
                capture_output=True,
                text=True,
                timeout=CODE_EXECUTION_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return jsonify({
                'status': 'timeout',
                'stdout': '',
                'stderr': f'Execution stopped after {CODE_EXECUTION_TIMEOUT_SECONDS} seconds.',
                'available_files': [file.name for file in safe_files],
            }), 200

    output_line = (completed.stdout or '').strip().splitlines()[-1] if (completed.stdout or '').strip() else ''
    try:
        parsed = json.loads(output_line) if output_line else {'status': 'error', 'stdout': '', 'stderr': completed.stderr or 'Unknown execution error'}
    except Exception:
        parsed = {'status': 'error', 'stdout': completed.stdout or '', 'stderr': completed.stderr or 'Unable to parse execution output.'}

    parsed['available_files'] = [file.name for file in safe_files]
    return jsonify(parsed)


@app.route('/api/admin/summary', methods=['GET'])
@admin_required
def admin_summary():
    return jsonify({
        'admin_name': request.current_user.full_name,
        'stats': {
            'total_users': User.query.count(),
            'admin_users': User.query.filter_by(is_admin=True).count(),
            'total_courses': Course.query.count(),
            'completed_courses': Course.query.filter_by(status='completed').count(),
            'assessment_attempts': AssessmentAttempt.query.count(),
            'certificates_issued': Certificate.query.count(),
        },
        'tables': [
            {
                'name': table_name,
                'label': config['label'],
                'fields': config['list_fields'],
                'editable_fields': config['editable_fields'],
                'create_fields': config['create_fields'],
            }
            for table_name, config in TABLE_CONFIG.items()
        ],
    })


@app.route('/api/admin/<table_name>', methods=['GET'])
@admin_required
def admin_list_records(table_name):
    config, error = _get_table_config(table_name)
    if error:
        return error
    query = config['model'].query.order_by(getattr(config['model'], config['pk']).desc())
    records = query.limit(200).all()
    return jsonify({
        'table': table_name,
        'label': config['label'],
        'fields': config['list_fields'],
        'editable_fields': config['editable_fields'],
        'create_fields': config['create_fields'],
        'rows': [serialize_record(table_name, record) for record in records],
    })


@app.route('/api/admin/<table_name>', methods=['POST'])
@admin_required
def admin_create_record(table_name):
    config, error = _get_table_config(table_name)
    if error:
        return error
    payload = request.get_json() or {}
    record = config['model']()
    validation_error = _apply_record_data(record, payload, config['create_fields'], table_name, is_create=True)
    if validation_error:
        return validation_error
    db.session.add(record)
    db.session.commit()
    return jsonify({'message': f'{config["label"][:-1] if config["label"].endswith("s") else config["label"]} created successfully', 'row': serialize_record(table_name, record)}), 201


@app.route('/api/admin/<table_name>/<int:record_id>', methods=['PUT'])
@admin_required
def admin_update_record(table_name, record_id):
    config, error = _get_table_config(table_name)
    if error:
        return error
    record = db.session.get(config['model'], record_id)
    if not record:
        return jsonify({'error': 'Record not found'}), 404
    payload = request.get_json() or {}
    validation_error = _apply_record_data(record, payload, config['editable_fields'] + ['password'], table_name, is_create=False)
    if validation_error:
        return validation_error
    db.session.commit()
    return jsonify({'message': 'Record updated successfully', 'row': serialize_record(table_name, record)})


@app.route('/api/admin/<table_name>/<int:record_id>', methods=['DELETE'])
@admin_required
def admin_delete_record(table_name, record_id):
    config, error = _get_table_config(table_name)
    if error:
        return error
    record = db.session.get(config['model'], record_id)
    if not record:
        return jsonify({'error': 'Record not found'}), 404

    if table_name == 'users' and record.id == request.current_user.id:
        return jsonify({'error': 'You cannot delete the currently logged-in admin account'}), 400

    db.session.delete(record)
    db.session.commit()
    return jsonify({'message': 'Record deleted successfully'})



def ensure_default_admin():
    admin_email = os.getenv('ADMIN_EMAIL', 'admin@aicourse.local').strip().lower()
    admin_password = os.getenv('ADMIN_PASSWORD', 'Admin@12345').strip()
    admin_name = os.getenv('ADMIN_NAME', 'System Administrator').strip() or 'System Administrator'

    existing = User.query.filter_by(email=admin_email).first()
    if existing:
        if not existing.is_admin:
            existing.is_admin = True
            db.session.commit()
        return

    admin_user = User(
        full_name=admin_name,
        email=admin_email,
        current_role='Administrator',
        experience_level='Advanced',
        is_admin=True,
    )
    admin_user.set_password(admin_password)
    db.session.add(admin_user)
    db.session.commit()


with app.app_context():
    db.create_all()
    ensure_default_admin()


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
