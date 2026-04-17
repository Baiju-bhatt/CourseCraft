from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps
from dotenv import load_dotenv
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
from io import BytesIO
from xml.sax.saxutils import escape
from urllib.parse import quote_plus
import re

import requests

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from services.ai_service import CourseAIService

load_dotenv()

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


YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY', '').strip()
YOUTUBE_SEARCH_URL = 'https://www.googleapis.com/youtube/v3/search'
YOUTUBE_VIDEOS_URL = 'https://www.googleapis.com/youtube/v3/videos'
YOUTUBE_MAX_RESULTS = 3
VIDEO_CACHE = {}
VIDEO_CACHE_LIMIT = 250


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


class CourseProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    progress_json = db.Column(db.Text, nullable=False, default='{}')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'course_id', name='uq_user_course_progress'),)


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

def _safe_text(value, default=''):
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        return ', '.join(_safe_text(item) for item in value if item is not None)
    if isinstance(value, dict):
        return _safe_text(json.dumps(value, ensure_ascii=False))
    return str(value).strip()


def _build_pdf_filename(course_title: str) -> str:
    cleaned = ''.join(ch if ch.isalnum() or ch in {'-', '_'} else '_' for ch in _safe_text(course_title, 'course'))
    cleaned = '_'.join(part for part in cleaned.split('_') if part) or 'course'
    return f'{cleaned[:80]}_course.pdf'

def _build_ics_filename(course_title: str) -> str:
    cleaned = ''.join(ch if ch.isalnum() or ch in {'-', '_'} else '_' for ch in _safe_text(course_title, 'course_schedule'))
    cleaned = '_'.join(part for part in cleaned.split('_') if part) or 'course_schedule'
    return f'{cleaned[:80]}_schedule.ics'



def _default_progress_for_course(course_data: dict) -> dict:
    modules = course_data.get('modules') or []
    return {
        'completed_lessons': {},
        'quiz_results': {},
        'quiz_answers': {},
        'lesson_notes': {},
        'capstone_submitted': False,
        'capstone_file_name': '',
        'certificate_id': None,
        'updated_at': datetime.utcnow().isoformat(),
    }


def _sanitize_progress_payload(course_data: dict, payload: dict) -> dict:
    base = _default_progress_for_course(course_data)
    if not isinstance(payload, dict):
        return base
    modules = course_data.get('modules') or []
    valid_lesson_keys = set()
    for mi, module in enumerate(modules):
        for li, _lesson in enumerate(module.get('lessons') or []):
            valid_lesson_keys.add(f'{mi}-{li}')
    cleaned_completed = {}
    for key, value in (payload.get('completed_lessons') or {}).items():
        if key in valid_lesson_keys:
            cleaned_completed[key] = bool(value)
    cleaned_notes = {}
    for key, value in (payload.get('lesson_notes') or {}).items():
        if key in valid_lesson_keys and isinstance(value, str):
            cleaned_notes[key] = value[:6000]
    cleaned_quiz_results = {}
    cleaned_quiz_answers = {}
    for mi, module in enumerate(modules):
        mk = str(mi)
        quiz = module.get('quiz') or []
        if mk in (payload.get('quiz_answers') or {}):
            module_answers = {}
            for qidx, val in (payload['quiz_answers'].get(mk) or {}).items():
                try:
                    qi = int(qidx)
                except Exception:
                    continue
                if 0 <= qi < len(quiz) and isinstance(val, str):
                    module_answers[str(qi)] = val[:500]
            cleaned_quiz_answers[mk] = module_answers
        if mk in (payload.get('quiz_results') or {}):
            res = payload['quiz_results'].get(mk) or {}
            cleaned_quiz_results[mk] = {
                'score': int(res.get('score') or 0),
                'correct': int(res.get('correct') or 0),
                'total': int(res.get('total') or len(quiz)),
                'submitted': bool(res.get('submitted')),
                'passed': bool(res.get('passed')),
                'details': res.get('details') if isinstance(res.get('details'), dict) else {},
            }
    base.update({
        'completed_lessons': cleaned_completed,
        'lesson_notes': cleaned_notes,
        'quiz_answers': cleaned_quiz_answers,
        'quiz_results': cleaned_quiz_results,
        'capstone_submitted': bool(payload.get('capstone_submitted')),
        'capstone_file_name': _safe_text(payload.get('capstone_file_name')),
        'certificate_id': payload.get('certificate_id') if payload.get('certificate_id') else None,
        'updated_at': datetime.utcnow().isoformat(),
    })
    return base


def _progress_summary(course_data: dict, progress: dict) -> dict:
    modules = course_data.get('modules') or []
    completed_lessons = progress.get('completed_lessons') or {}
    quiz_results = progress.get('quiz_results') or {}
    total_lessons = sum(len(module.get('lessons') or []) for module in modules)
    completed_count = sum(1 for value in completed_lessons.values() if value)
    module_progress = []
    unlocked_next = True
    completed_module_count = 0
    completed_quiz_count = 0
    for mi, module in enumerate(modules):
        lessons = module.get('lessons') or []
        lesson_total = len(lessons)
        lesson_completed = sum(1 for li, _ in enumerate(lessons) if completed_lessons.get(f'{mi}-{li}'))
        quiz_state = quiz_results.get(str(mi)) or {}
        quiz_done = bool(quiz_state.get('submitted'))
        quiz_passed = bool(quiz_state.get('passed'))
        if quiz_done:
            completed_quiz_count += 1
        module_complete = lesson_total > 0 and lesson_completed == lesson_total and quiz_passed
        if module_complete:
            completed_module_count += 1
        unlocked = True if mi == 0 else module_progress[mi-1]['module_complete']
        module_progress.append({
            'module_index': mi,
            'lesson_total': lesson_total,
            'lesson_completed': lesson_completed,
            'quiz_done': quiz_done,
            'quiz_passed': quiz_passed,
            'module_complete': module_complete,
            'unlocked': unlocked,
        })
    total_track_units = total_lessons + len(modules) + (1 if course_data.get('final_capstone') or course_data.get('capstone') else 0)
    completed_units = completed_count + completed_quiz_count + (1 if progress.get('capstone_submitted') else 0)
    progress_percent = round((completed_units / total_track_units) * 100) if total_track_units else 0
    eligible_for_certificate = completed_module_count == len(modules) and progress_percent >= 80
    return {
        'total_lessons': total_lessons,
        'completed_lessons_count': completed_count,
        'completed_quizzes_count': completed_quiz_count,
        'completed_module_count': completed_module_count,
        'progress_percent': progress_percent,
        'module_progress': module_progress,
        'eligible_for_certificate': eligible_for_certificate,
    }


def _get_or_create_progress(user_id: int, course: Course, course_data: dict):
    record = CourseProgress.query.filter_by(user_id=user_id, course_id=course.id).first()
    if not record:
        record = CourseProgress(user_id=user_id, course_id=course.id, progress_json=json.dumps(_default_progress_for_course(course_data)))
        db.session.add(record)
        db.session.commit()
    try:
        progress = json.loads(record.progress_json or '{}')
    except Exception:
        progress = _default_progress_for_course(course_data)
    progress = _sanitize_progress_payload(course_data, progress)
    return record, progress

def _ics_escape(value) -> str:
    text = _safe_text(value)
    return text.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\r\n', '\\n').replace('\n', '\\n')

def _parse_start_datetime(start_date: str, start_time: str) -> datetime:
    date_part = datetime.strptime(start_date, '%Y-%m-%d').date()
    time_part = datetime.strptime(start_time, '%H:%M').time()
    return datetime.combine(date_part, time_part)


def _schedule_datetimes(start_date: str, start_time: str, sessions_per_week: int, event_count: int):
    start_dt = _parse_start_datetime(start_date, start_time)
    sessions_per_week = max(1, min(7, int(sessions_per_week)))
    weekday_patterns = {
        1: [0],
        2: [0, 3],
        3: [0, 2, 4],
        4: [0, 1, 3, 4],
        5: [0, 1, 2, 3, 4],
        6: [0, 1, 2, 3, 4, 5],
        7: [0, 1, 2, 3, 4, 5, 6],
    }
    pattern = weekday_patterns[sessions_per_week]
    dates = []
    week_offset = 0
    first_weekday = start_dt.weekday()
    start_clock = start_dt.time()

    while len(dates) < event_count:
        for weekday in pattern:
            day_delta = weekday - first_weekday + (week_offset * 7)
            candidate_date = start_dt.date() + timedelta(days=day_delta)
            candidate_dt = datetime.combine(candidate_date, start_clock)
            if candidate_dt < start_dt:
                continue
            dates.append(candidate_dt)
            if len(dates) >= event_count:
                break
        week_offset += 1
    return dates


def _build_course_schedule_events(course_record: Course, course_data: dict, start_date: str, start_time: str, sessions_per_week: int, session_minutes: int):
    modules = course_data.get('modules') or []
    session_minutes = max(15, min(240, int(session_minutes)))
    events = []
    items = []

    for index, module in enumerate(modules, start=1):
        lessons = module.get('lessons') or []
        lesson_titles = [lesson.get('title') for lesson in lessons if lesson.get('title')]
        description_lines = []
        if module.get('module_summary'):
            description_lines.append(module.get('module_summary'))
        if module.get('learning_objectives'):
            description_lines.append('Learning objectives: ' + '; '.join([_safe_text(item) for item in module.get('learning_objectives') if item]))
        if lesson_titles:
            description_lines.append('Lessons: ' + '; '.join(lesson_titles[:8]))
        if module.get('assignment', {}).get('title'):
            description_lines.append('Assignment: ' + _safe_text(module.get('assignment', {}).get('title')))
        items.append({
            'title': f"{_safe_text(course_data.get('title') or course_record.title)} - Module {module.get('module_number') or index}: {_safe_text(module.get('title') or f'Module {index}')}",
            'description': '\n'.join(description_lines),
        })

    final_capstone = course_data.get('final_capstone') or {}
    capstone_title = _safe_text(final_capstone.get('title'))
    if capstone_title:
        capstone_lines = []
        if final_capstone.get('description'):
            capstone_lines.append(_safe_text(final_capstone.get('description')))
        deliverables = final_capstone.get('deliverables') or []
        if deliverables:
            capstone_lines.append('Deliverables: ' + '; '.join([_safe_text(item) for item in deliverables if item]))
        items.append({
            'title': f"{_safe_text(course_data.get('title') or course_record.title)} - Final Capstone",
            'description': '\n'.join(capstone_lines) or capstone_title,
        })

    datetimes = _schedule_datetimes(start_date, start_time, sessions_per_week, len(items))
    for idx, item in enumerate(items):
        start_dt = datetimes[idx]
        end_dt = start_dt + timedelta(minutes=session_minutes)
        events.append({
            'uid': f"{course_record.public_id}-{idx+1}@ai-course-generator",
            'title': item['title'],
            'description': item['description'],
            'start': start_dt,
            'end': end_dt,
        })
    return events


def _course_schedule_ics(course_record: Course, course_data: dict, start_date: str, start_time: str, sessions_per_week: int, session_minutes: int) -> BytesIO:
    events = _build_course_schedule_events(course_record, course_data, start_date, start_time, sessions_per_week, session_minutes)
    now_utc = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//AI Course Generator//Study Schedule//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'X-WR-CALNAME:' + _ics_escape((_safe_text(course_data.get('title') or course_record.title) + ' Study Schedule')),
    ]

    for event in events:
        lines.extend([
            'BEGIN:VEVENT',
            'UID:' + event['uid'],
            'DTSTAMP:' + now_utc,
            'DTSTART:' + event['start'].strftime('%Y%m%dT%H%M%S'),
            'DTEND:' + event['end'].strftime('%Y%m%dT%H%M%S'),
            'SUMMARY:' + _ics_escape(event['title']),
            'DESCRIPTION:' + _ics_escape(event['description']),
            'END:VEVENT',
        ])

    lines.append('END:VCALENDAR')
    return BytesIO('\r\n'.join(lines).encode('utf-8'))


def _pdf_page(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 9)
    canvas.setFillColor(colors.HexColor('#6b7280'))
    canvas.drawRightString(doc.pagesize[0] - 0.6 * inch, 0.45 * inch, f'Page {canvas.getPageNumber()}')
    canvas.restoreState()


def _course_pdf_buffer(course_record: Course, course_data: dict, user: User) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.7 * inch,
        title=_safe_text(course_data.get('title') or course_record.title),
        author='AI Course Generator',
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CourseTitle',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=28,
        alignment=TA_CENTER,
        spaceAfter=10,
        textColor=colors.HexColor('#111827'),
    )
    subtitle_style = ParagraphStyle(
        'CourseSubtitle',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=10.5,
        leading=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#4b5563'),
        spaceAfter=6,
    )
    section_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=20,
        textColor=colors.HexColor('#111827'),
        spaceBefore=10,
        spaceAfter=8,
    )
    subheading_style = ParagraphStyle(
        'SubHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12.5,
        leading=16,
        textColor=colors.HexColor('#1f2937'),
        spaceBefore=8,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        'BodyCopy',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=10.2,
        leading=14.2,
        textColor=colors.HexColor('#1f2937'),
        spaceAfter=6,
    )
    small_style = ParagraphStyle(
        'SmallCopy',
        parent=body_style,
        fontSize=9.4,
        leading=12.8,
        textColor=colors.HexColor('#4b5563'),
    )

    story = []
    title = _safe_text(course_data.get('title') or course_record.title)
    overview = _safe_text(course_data.get('overview'))
    target_role = _safe_text(course_record.target_role)
    experience_type = _safe_text(course_data.get('experience_type') or course_record.experience_type).title()
    estimated_duration = _safe_text(course_data.get('estimated_duration'))
    focus_topics = course_data.get('focus_topics') or []
    generation_source = 'Hugging Face LLM' if course_data.get('generation_source') == 'llm' else 'Fallback Generator'

    story.append(Spacer(1, 0.35 * inch))
    story.append(Paragraph(escape(title), title_style))
    story.append(Paragraph(escape(f'Target Role: {target_role}'), subtitle_style))
    story.append(Paragraph(escape(f'Learning Track: {experience_type}'), subtitle_style))
    if estimated_duration:
        story.append(Paragraph(escape(f'Estimated Duration: {estimated_duration}'), subtitle_style))
    story.append(Paragraph(escape(f'Generated for: {user.full_name}'), subtitle_style))
    story.append(Paragraph(escape(f'Created on: {course_record.created_at.strftime("%B %d, %Y")}'), subtitle_style))
    story.append(Spacer(1, 0.2 * inch))

    if focus_topics:
        story.append(Paragraph('Focus Topics', section_style))
        topic_items = [ListItem(Paragraph(escape(_safe_text(item)), body_style)) for item in focus_topics if _safe_text(item)]
        if topic_items:
            story.append(ListFlowable(topic_items, bulletType='bullet', leftIndent=18))
            story.append(Spacer(1, 0.08 * inch))

    if overview:
        story.append(Paragraph('Course Overview', section_style))
        story.append(Paragraph(escape(overview), body_style))

    certificate_criteria = course_data.get('certificate_criteria') or []
    if certificate_criteria:
        story.append(Paragraph('Certificate Criteria', section_style))
        criteria_items = [ListItem(Paragraph(escape(_safe_text(item)), body_style)) for item in certificate_criteria if _safe_text(item)]
        if criteria_items:
            story.append(ListFlowable(criteria_items, bulletType='bullet', leftIndent=18))
            story.append(Spacer(1, 0.08 * inch))

    modules = course_data.get('modules') or []
    if modules:
        story.append(PageBreak())
        story.append(Paragraph('Course Curriculum', section_style))

    for module_index, module in enumerate(modules, start=1):
        module_title = _safe_text(module.get('title'), f'Module {module_index}')
        module_number = module.get('module_number') or module_index
        story.append(Paragraph(escape(f'Module {module_number}: {module_title}'), section_style))

        module_summary = _safe_text(module.get('module_summary'))
        if module_summary:
            story.append(Paragraph(escape(module_summary), body_style))

        objectives = module.get('learning_objectives') or []
        if objectives:
            story.append(Paragraph('Learning Objectives', subheading_style))
            objective_items = [ListItem(Paragraph(escape(_safe_text(item)), body_style)) for item in objectives if _safe_text(item)]
            if objective_items:
                story.append(ListFlowable(objective_items, bulletType='bullet', leftIndent=18))
                story.append(Spacer(1, 0.08 * inch))

        lessons = module.get('lessons') or []
        for lesson_index, lesson in enumerate(lessons, start=1):
            lesson_title = _safe_text(lesson.get('title'), f'Lesson {lesson_index}')
            lesson_format = _safe_text(lesson.get('format'))
            lesson_duration = _safe_text(lesson.get('duration'))
            meta_bits = [bit for bit in [lesson_format.title() if lesson_format else '', lesson_duration] if bit]
            story.append(Paragraph(escape(f'Lesson {lesson_index}: {lesson_title}'), subheading_style))
            if meta_bits:
                story.append(Paragraph(escape(' • '.join(meta_bits)), small_style))

            lesson_summary = _safe_text(lesson.get('summary'))
            if lesson_summary:
                story.append(Paragraph(escape(lesson_summary), body_style))

            takeaways = lesson.get('key_takeaways') or []
            if takeaways:
                story.append(Paragraph('Key Takeaways', subheading_style))
                takeaway_items = [ListItem(Paragraph(escape(_safe_text(item)), body_style)) for item in takeaways if _safe_text(item)]
                if takeaway_items:
                    story.append(ListFlowable(takeaway_items, bulletType='bullet', leftIndent=18))
                    story.append(Spacer(1, 0.06 * inch))

            sections = lesson.get('content_sections') or []
            if sections:
                story.append(Paragraph('Content', subheading_style))
                for section in sections:
                    heading = _safe_text(section.get('heading'))
                    body = _safe_text(section.get('body'))
                    if heading:
                        story.append(Paragraph(escape(heading), ParagraphStyle('MiniHeading', parent=body_style, fontName='Helvetica-Bold', spaceAfter=3, spaceBefore=2)))
                    if body:
                        story.append(Paragraph(escape(body), body_style))

            example = lesson.get('example') or {}
            if isinstance(example, dict) and any(_safe_text(example.get(key)) for key in ['title', 'scenario']):
                story.append(Paragraph('Worked Example', subheading_style))
                example_title = _safe_text(example.get('title'))
                example_scenario = _safe_text(example.get('scenario'))
                if example_title:
                    story.append(Paragraph(escape(example_title), ParagraphStyle('ExampleHeading', parent=body_style, fontName='Helvetica-Bold')))
                if example_scenario:
                    story.append(Paragraph(escape(example_scenario), body_style))
                example_steps = example.get('steps') or []
                if example_steps:
                    step_items = [ListItem(Paragraph(escape(_safe_text(item)), body_style)) for item in example_steps if _safe_text(item)]
                    if step_items:
                        story.append(ListFlowable(step_items, bulletType='1', leftIndent=18))
                        story.append(Spacer(1, 0.06 * inch))

            practice_task = _safe_text(lesson.get('practice_task'))
            if practice_task:
                story.append(Paragraph('Practice Task', subheading_style))
                story.append(Paragraph(escape(practice_task), body_style))

        quiz = module.get('quiz') or []
        if quiz:
            story.append(Paragraph('Module Quiz', subheading_style))
            for question_index, question in enumerate(quiz, start=1):
                difficulty = _safe_text(question.get('difficulty'))
                question_text = _safe_text(question.get('question'))
                if question_text:
                    label = f'Q{question_index}' + (f' ({difficulty})' if difficulty else '')
                    story.append(Paragraph(escape(f'{label}: {question_text}'), ParagraphStyle('QuestionStyle', parent=body_style, fontName='Helvetica-Bold', spaceBefore=4, spaceAfter=4)))
                options = question.get('options') or []
                option_items = [ListItem(Paragraph(escape(_safe_text(option)), body_style)) for option in options if _safe_text(option)]
                if option_items:
                    story.append(ListFlowable(option_items, bulletType='bullet', leftIndent=18))
                    story.append(Spacer(1, 0.04 * inch))
                answer = _safe_text(question.get('answer'))
                explanation = _safe_text(question.get('explanation'))
                if answer:
                    story.append(Paragraph(escape(f'Answer: {answer}'), small_style))
                if explanation:
                    story.append(Paragraph(escape(f'Explanation: {explanation}'), small_style))

        assignment = module.get('assignment') or {}
        if isinstance(assignment, dict) and any(_safe_text(assignment.get(key)) for key in ['title', 'description']):
            story.append(Paragraph('Module Assignment', subheading_style))
            assignment_title = _safe_text(assignment.get('title'))
            assignment_description = _safe_text(assignment.get('description'))
            if assignment_title:
                story.append(Paragraph(escape(assignment_title), ParagraphStyle('AssignmentHeading', parent=body_style, fontName='Helvetica-Bold')))
            if assignment_description:
                story.append(Paragraph(escape(assignment_description), body_style))
            deliverables = assignment.get('deliverables') or []
            if deliverables:
                deliverable_items = [ListItem(Paragraph(escape(_safe_text(item)), body_style)) for item in deliverables if _safe_text(item)]
                if deliverable_items:
                    story.append(ListFlowable(deliverable_items, bulletType='bullet', leftIndent=18))
                    story.append(Spacer(1, 0.06 * inch))
            submission_type = _safe_text(assignment.get('submission_type'))
            if submission_type:
                story.append(Paragraph(escape(f'Submission Type: {submission_type}'), small_style))

    capstone = course_data.get('capstone') or {}
    if isinstance(capstone, dict) and any(_safe_text(capstone.get(key)) for key in ['title', 'description']):
        story.append(PageBreak())
        story.append(Paragraph('Capstone Project', section_style))
        capstone_title = _safe_text(capstone.get('title'))
        capstone_description = _safe_text(capstone.get('description'))
        if capstone_title:
            story.append(Paragraph(escape(capstone_title), subheading_style))
        if capstone_description:
            story.append(Paragraph(escape(capstone_description), body_style))
        deliverables = capstone.get('deliverables') or []
        if deliverables:
            deliverable_items = [ListItem(Paragraph(escape(_safe_text(item)), body_style)) for item in deliverables if _safe_text(item)]
            if deliverable_items:
                story.append(ListFlowable(deliverable_items, bulletType='bullet', leftIndent=18))

    doc.build(story, onFirstPage=_pdf_page, onLaterPages=_pdf_page)
    buffer.seek(0)
    return buffer



def _clean_search_text(value) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9+\s-]', ' ', str(value or ''))
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _course_video_query(course_data: dict, module: dict, lesson: dict) -> str:
    raw = ' '.join([
        _clean_search_text(module.get('title') or ''),
        _clean_search_text(lesson.get('title') or ''),
        ' '.join(_clean_search_text((section.get('heading') or '')) for section in (lesson.get('content_sections') or [])[:2]),
    ]).lower()
    tokens = []
    stop = {'core', 'ideas', 'vocabulary', 'why', 'matters', 'apply', 'real', 'world', 'delivery', 'personalized', 'upskilling', 'track', 'concepts', 'strengthen', 'production', 'style', 'decisions'}
    for token in re.split(r'[^a-z0-9]+', raw):
        if len(token) >= 4 and token not in stop and token not in tokens:
            tokens.append(token)
    role = _clean_search_text(course_data.get('target_role') or '')
    focused = ' '.join(tokens[:6])
    return ' '.join(part for part in [focused, role, 'tutorial course explained'] if part).strip()


def _video_cache_get(cache_key):
    return VIDEO_CACHE.get(cache_key)


def _video_cache_set(cache_key, value):
    if len(VIDEO_CACHE) >= VIDEO_CACHE_LIMIT:
        oldest_key = next(iter(VIDEO_CACHE))
        VIDEO_CACHE.pop(oldest_key, None)
    VIDEO_CACHE[cache_key] = value


def _youtube_enabled() -> bool:
    return bool(YOUTUBE_API_KEY)


def _score_video_result(item: dict, query_terms: set, banned_terms: set | None = None) -> int:
    haystack = f"{item.get('title', '')} {item.get('description', '')} {item.get('channel_title', '')}".lower()
    score = 0
    educational_terms = ['tutorial', 'course', 'explained', 'lesson', 'learn', 'training', 'full course']
    preferred_terms = ['sql', 'schema', 'database', 'modeling', 'warehouse', 'etl', 'pipeline', 'quality', 'reliability', 'cloud', 'platform']
    banned_terms = banned_terms or set()
    for term in query_terms:
        if term and term in haystack:
            score += 5 if term in preferred_terms else 3
    for term in educational_terms:
        if term in haystack:
            score += 2
    for banned in banned_terms:
        if banned in haystack:
            score -= 10
    if 'shorts' in haystack or '#shorts' in haystack or 'pt' in (item.get('duration') or '').lower():
        score -= 5
    if len((item.get('title') or '').split()) < 3:
        score -= 2
    return score


def _search_youtube_videos(query: str, max_results: int = YOUTUBE_MAX_RESULTS) -> dict:
    if not _youtube_enabled():
        return {
            'videos': [],
            'query': query,
            'enabled': False,
            'fallback_search_url': f'https://www.youtube.com/results?search_query={quote_plus(query)}',
            'message': 'Video recommendations are not configured yet. Add YOUTUBE_API_KEY on the backend to load embedded YouTube videos automatically.',
        }

    cache_key = query.lower().strip()
    cached = _video_cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        search_response = requests.get(
            YOUTUBE_SEARCH_URL,
            params={
                'part': 'snippet',
                'q': query,
                'type': 'video',
                'maxResults': max(max_results * 3, 9),
                'videoEmbeddable': 'true',
                'safeSearch': 'moderate',
                'relevanceLanguage': 'en',
                'videoDuration': 'medium',
                'order': 'relevance',
                'key': YOUTUBE_API_KEY,
            },
            timeout=12,
        )
        search_response.raise_for_status()
        search_payload = search_response.json()
    except requests.RequestException:
        return {
            'videos': [],
            'query': query,
            'enabled': True,
            'message': 'Unable to fetch videos from YouTube right now. Please try again in a moment.',
        }

    raw_items = search_payload.get('items') or []
    video_ids = [item.get('id', {}).get('videoId') for item in raw_items if item.get('id', {}).get('videoId')]
    durations = {}
    if video_ids:
        try:
            details_response = requests.get(
                YOUTUBE_VIDEOS_URL,
                params={
                    'part': 'contentDetails',
                    'id': ','.join(video_ids),
                    'key': YOUTUBE_API_KEY,
                },
                timeout=12,
            )
            details_response.raise_for_status()
            detail_payload = details_response.json()
            durations = {
                item.get('id'): item.get('contentDetails', {}).get('duration')
                for item in detail_payload.get('items') or []
            }
        except requests.RequestException:
            durations = {}

    query_terms = {term for term in re.split(r'\s+', query.lower()) if len(term) > 2}
    banned_terms = {'rag', 'agentic', 'devops', 'marketing', 'presentation', 'powerpoint', 'ai tools', 'chatgpt'}
    videos = []
    for item in raw_items:
        video_id = item.get('id', {}).get('videoId')
        snippet = item.get('snippet') or {}
        if not video_id:
            continue
        thumbnails = snippet.get('thumbnails') or {}
        thumbnail_url = (
            (thumbnails.get('high') or {}).get('url')
            or (thumbnails.get('medium') or {}).get('url')
            or (thumbnails.get('default') or {}).get('url')
        )
        video_data = {
            'video_id': video_id,
            'title': snippet.get('title') or 'YouTube Video',
            'description': snippet.get('description') or '',
            'channel_title': snippet.get('channelTitle') or 'YouTube',
            'published_at': snippet.get('publishedAt'),
            'thumbnail_url': thumbnail_url,
            'watch_url': f'https://www.youtube.com/watch?v={video_id}',
            'embed_url': f'https://www.youtube.com/embed/{video_id}',
            'duration': durations.get(video_id),
        }
        video_data['score'] = _score_video_result(video_data, query_terms, banned_terms)
        videos.append(video_data)

    videos.sort(key=lambda item: item.get('score', 0), reverse=True)
    result = {
        'videos': videos[:max_results],
        'query': query,
        'enabled': True,
        'message': 'Recommended videos loaded successfully.' if videos else 'No relevant videos were found for this lesson yet.',
    }
    _video_cache_set(cache_key, result)
    return result


def _get_course_module_lesson(course_data: dict, module_index: int, lesson_index: int):
    modules = course_data.get('modules') or []
    if module_index < 0 or module_index >= len(modules):
        raise IndexError('Module index out of range')
    module = modules[module_index]
    lessons = module.get('lessons') or []
    if lesson_index < 0 or lesson_index >= len(lessons):
        raise IndexError('Lesson index out of range')
    lesson = lessons[lesson_index]
    return module, lesson


@app.route('/api/course/<course_id>/videos', methods=['GET'])
@auth_required
def get_course_videos(course_id):
    course = Course.query.filter_by(public_id=course_id, user_id=request.current_user.id).first()
    if not course:
        return jsonify({'error': 'Course not found'}), 404

    try:
        module_index = int(request.args.get('module_index', 0))
        lesson_index = int(request.args.get('lesson_index', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'module_index and lesson_index must be integers'}), 400

    try:
        course_data = json.loads(course.course_json)
        module, lesson = _get_course_module_lesson(course_data, module_index, lesson_index)
    except IndexError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception:
        return jsonify({'error': 'Unable to read course data'}), 500

    query = _course_video_query(course_data, module, lesson)
    result = _search_youtube_videos(query)
    return jsonify({
        'module_index': module_index,
        'lesson_index': lesson_index,
        'lesson_title': lesson.get('title'),
        'module_title': module.get('title'),
        **result,
    })


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'message': 'AI Course Generator API is running',
        'llm_enabled': ai_service.llm_enabled,
        'model': ai_service.model if ai_service.llm_enabled else None,
        'youtube_enabled': _youtube_enabled(),
    })


@app.route('/api/config', methods=['GET'])
def config():
    return jsonify({
        'llm_enabled': ai_service.llm_enabled,
        'model': ai_service.model if ai_service.llm_enabled else None,
        'youtube_enabled': _youtube_enabled(),
        'suggested_roles': [
            'Data Engineer',
            'Data Scientist',
            'AI Developer',
            'ML Engineer',
            'Machine Learning Engineer',
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

    course_data = json.loads(course.course_json)
    _record, progress = _get_or_create_progress(request.current_user.id, course, course_data)
    summary = _progress_summary(course_data, progress)
    return jsonify({
        'course_id': course.public_id,
        'title': course.title,
        'target_role': course.target_role,
        'experience_type': course.experience_type,
        'status': course.status,
        'course': course_data,
        'progress': progress,
        'progress_summary': summary,
    })


@app.route('/api/course/<course_id>/export-pdf', methods=['GET'])
@auth_required
def export_course_pdf(course_id):
    course = Course.query.filter_by(public_id=course_id, user_id=request.current_user.id).first()
    if not course:
        return jsonify({'error': 'Course not found'}), 404

    try:
        course_data = json.loads(course.course_json)
    except Exception:
        return jsonify({'error': 'Unable to read course data for PDF export'}), 500

    pdf_buffer = _course_pdf_buffer(course, course_data, request.current_user)
    filename = _build_pdf_filename(course_data.get('title') or course.title)
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf',
    )


@app.route('/api/course/<course_id>/export-schedule', methods=['GET'])
@auth_required
def export_course_schedule(course_id):
    course = Course.query.filter_by(public_id=course_id, user_id=request.current_user.id).first()
    if not course:
        return jsonify({'error': 'Course not found'}), 404

    try:
        course_data = json.loads(course.course_json)
    except json.JSONDecodeError:
        return jsonify({'error': 'Course content is invalid and could not be exported'}), 500

    start_date = (request.args.get('start_date') or '').strip()
    start_time = (request.args.get('start_time') or '19:00').strip()
    sessions_per_week = request.args.get('sessions_per_week', '3').strip()
    session_minutes = request.args.get('session_minutes', '60').strip()

    if not start_date:
        return jsonify({'error': 'start_date is required'}), 400

    try:
        datetime.strptime(start_date, '%Y-%m-%d')
        datetime.strptime(start_time, '%H:%M')
        sessions_per_week_int = max(1, min(7, int(sessions_per_week)))
        session_minutes_int = max(15, min(240, int(session_minutes)))
    except ValueError:
        return jsonify({'error': 'Invalid schedule options provided'}), 400

    ics_buffer = _course_schedule_ics(course, course_data, start_date, start_time, sessions_per_week_int, session_minutes_int)
    ics_buffer.seek(0)
    filename = _build_ics_filename(course_data.get('title') or course.title)
    return send_file(ics_buffer, mimetype='text/calendar; charset=utf-8', as_attachment=True, download_name=filename)



@app.route('/api/course/<course_id>/progress', methods=['GET'])
@auth_required
def get_course_progress(course_id):
    course = Course.query.filter_by(public_id=course_id, user_id=request.current_user.id).first()
    if not course:
        return jsonify({'error': 'Course not found'}), 404
    course_data = json.loads(course.course_json)
    record, progress = _get_or_create_progress(request.current_user.id, course, course_data)
    summary = _progress_summary(course_data, progress)
    return jsonify({'progress': progress, 'summary': summary})


@app.route('/api/course/<course_id>/progress', methods=['PUT'])
@auth_required
def save_course_progress(course_id):
    course = Course.query.filter_by(public_id=course_id, user_id=request.current_user.id).first()
    if not course:
        return jsonify({'error': 'Course not found'}), 404
    course_data = json.loads(course.course_json)
    payload = request.get_json() or {}
    record, _existing = _get_or_create_progress(request.current_user.id, course, course_data)
    progress = _sanitize_progress_payload(course_data, payload)
    summary = _progress_summary(course_data, progress)
    if summary['eligible_for_certificate']:
        existing_certificate = Certificate.query.filter_by(user_id=request.current_user.id, course_id=course.id).first()
        if not existing_certificate:
            existing_certificate = Certificate(user_id=request.current_user.id, course_id=course.id)
            db.session.add(existing_certificate)
            db.session.flush()
        progress['certificate_id'] = existing_certificate.certificate_id
        course.status = 'completed'
    record.progress_json = json.dumps(progress)
    db.session.add(record)
    db.session.commit()
    return jsonify({'message': 'Progress saved', 'progress': progress, 'summary': summary})


@app.route('/api/certificate/<certificate_id>/download', methods=['GET'])
@auth_required
def download_certificate(certificate_id):
    certificate = Certificate.query.filter_by(certificate_id=certificate_id, user_id=request.current_user.id).first()
    if not certificate:
        return jsonify({'error': 'Certificate not found'}), 404
    course = db.session.get(Course, certificate.course_id)
    user = db.session.get(User, certificate.user_id)
    from reportlab.lib.pagesizes import landscape
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = []
    story.append(Spacer(1, 24))
    story.append(Paragraph('Certificate of Completion', ParagraphStyle('ct', parent=styles['Title'], fontSize=28, alignment=TA_CENTER, textColor=colors.HexColor('#0f172a'))))
    story.append(Spacer(1, 16))
    story.append(Paragraph('This certifies that', ParagraphStyle('p1', parent=styles['BodyText'], alignment=TA_CENTER, fontSize=14)))
    story.append(Spacer(1, 8))
    story.append(Paragraph(_safe_text(user.full_name), ParagraphStyle('p2', parent=styles['Title'], alignment=TA_CENTER, fontSize=24, textColor=colors.HexColor('#0f766e'))))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f'has successfully completed the course <b>{escape(course.title)}</b>', ParagraphStyle('p3', parent=styles['BodyText'], alignment=TA_CENTER, fontSize=15, leading=22)))
    story.append(Spacer(1, 18))
    story.append(Paragraph(f'Target Role: {escape(course.target_role)}', ParagraphStyle('p4', parent=styles['BodyText'], alignment=TA_CENTER, fontSize=13)))
    story.append(Spacer(1, 24))
    story.append(Paragraph(f'Issued on {certificate.issued_at.strftime('%B %d, %Y')}  •  Certificate ID: {certificate.certificate_id}', ParagraphStyle('p5', parent=styles['BodyText'], alignment=TA_CENTER, fontSize=11, textColor=colors.HexColor('#475569'))))
    doc.build(story)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=f'certificate_{certificate.certificate_id}.pdf')


@app.route('/api/course/<course_id>/complete', methods=['POST'])
@auth_required
def complete_course(course_id):
    course = Course.query.filter_by(public_id=course_id, user_id=request.current_user.id).first()
    if not course:
        return jsonify({'error': 'Course not found'}), 404

    course_data = json.loads(course.course_json)
    _record, progress = _get_or_create_progress(request.current_user.id, course, course_data)
    summary = _progress_summary(course_data, progress)
    if not summary['eligible_for_certificate']:
        return jsonify({'error': 'Finish all modules, pass quizzes, and complete the capstone before final completion.'}), 400
    course.status = 'completed'
    existing_certificate = Certificate.query.filter_by(user_id=request.current_user.id, course_id=course.id).first()
    if not existing_certificate:
        existing_certificate = Certificate(user_id=request.current_user.id, course_id=course.id)
        db.session.add(existing_certificate)
    progress['certificate_id'] = existing_certificate.certificate_id
    record = CourseProgress.query.filter_by(user_id=request.current_user.id, course_id=course.id).first()
    if record:
        record.progress_json = json.dumps(progress)
        db.session.add(record)
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
