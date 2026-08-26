"""Simple Flask server for multi-user clause annotation.

Endpoints:
- GET /api/next -> returns next unannotated clause JSON
- POST /api/save -> save annotation {id, numeric_distance, distance_unit, feature, qualitative_flag, note, annotator}
- GET /api/export -> returns all annotations JSON
- GET / -> serves index_server.html

Run:
  python tools/labeler/server.py

This is intentionally minimal and uses a JSON file for persistence: `tools/labeler/data/annotations_db.json`.
"""
from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
import os
import json
from pathlib import Path
from datetime import datetime
import io
import csv

APP_ROOT = Path(__file__).parent
DATA_DIR = APP_ROOT / 'data'
SEED_FILE = DATA_DIR / 'seed_clauses.json'
IMPORTED_FILE = DATA_DIR / 'imported_from_outputs.json'
DB_FILE = DATA_DIR / 'annotations_db.json'
USERS_FILE = Path(os.environ.get('LABELER_USERS_FILE', DATA_DIR / 'users.json'))
SESSIONS_FILE = DATA_DIR / 'sessions.json'
OUTPUTS_ROOT = APP_ROOT.parent / 'outputs'

os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__, static_folder=str(APP_ROOT))
CORS(app)

from werkzeug.security import check_password_hash
import uuid
import time


def load_users():
    if not USERS_FILE.exists():
        return []
    try:
        return json.loads(USERS_FILE.read_text(encoding='utf-8'))
    except Exception:
        return []


def _read_sessions():
    if not SESSIONS_FILE.exists():
        return {}
    try:
        return json.loads(SESSIONS_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _write_sessions(s):
    SESSIONS_FILE.write_text(json.dumps(s, indent=2), encoding='utf-8')


def create_session(username, role, ttl=86400):
    sessions = _read_sessions()
    token = uuid.uuid4().hex
    sessions[token] = {'username': username, 'role': role, 'expires': int(time.time()) + ttl}
    _write_sessions(sessions)
    return token


def verify_token(token):
    if not token:
        return None
    sessions = _read_sessions()
    info = sessions.get(token)
    if not info:
        return None
    if int(time.time()) > info.get('expires', 0):
        # expired
        sessions.pop(token, None)
        _write_sessions(sessions)
        return None
    return info


def require_auth(fn):
    def wrapper(*args, **kwargs):
        auth = request.headers.get('Authorization') or request.cookies.get('X-Auth-Token')
        token = None
        if auth and auth.lower().startswith('bearer '):
            token = auth.split(None, 1)[1]
        elif auth:
            token = auth
        info = verify_token(token)
        if not info:
            return jsonify({'error': 'authentication required'}), 401
        request._auth_user = info
        return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


def require_admin(fn):
    def wrapper(*args, **kwargs):
        auth = request.headers.get('Authorization') or request.cookies.get('X-Auth-Token')
        token = None
        if auth and auth.lower().startswith('bearer '):
            token = auth.split(None, 1)[1]
        elif auth:
            token = auth
        info = verify_token(token)
        if not info or info.get('role') != 'admin':
            return jsonify({'error': 'admin required'}), 403
        request._auth_user = info
        return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


def load_seed():
    items = []
    for p in (SEED_FILE, IMPORTED_FILE):
        if p.exists():
            try:
                items += json.loads(p.read_text(encoding='utf-8'))
            except Exception:
                continue
    return items


def init_db():
    if DB_FILE.exists():
        try:
            db = json.loads(DB_FILE.read_text(encoding='utf-8'))
            return db
        except Exception:
            pass
    # build db from seed
    items = load_seed()
    db = []
    for i, it in enumerate(items):
        entry = dict(it)
        entry.setdefault('id', f'item-{i+1}')
        entry.setdefault('annotated', False)
        entry.setdefault('annotation', {})
        db.append(entry)
    DB_FILE.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding='utf-8')
    return db


def save_db(db):
    DB_FILE.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding='utf-8')


@app.route('/')
def index():
    return send_from_directory(str(APP_ROOT), 'index_server.html')


@app.route('/api/next')
def api_next():
    db = init_db()
    for it in db:
        if not it.get('annotated'):
            return jsonify({
                'id': it['id'],
                'clause_text': it.get('clause_text')
            })
    return jsonify({'id': None, 'message': 'no more items'})


@app.route('/api/login', methods=['POST'])
def api_login():
    payload = request.get_json(force=True)
    if not payload or 'username' not in payload or 'password' not in payload:
        return jsonify({'error': 'username and password required'}), 400
    users = load_users()
    for u in users:
        if u.get('username') == payload['username']:
            if check_password_hash(u.get('password_hash', ''), payload['password']):
                token = create_session(u['username'], u.get('role', 'annotator'))
                resp = jsonify({'ok': True, 'token': token, 'role': u.get('role', 'annotator')})
                # set cookie for convenience
                resp.set_cookie('X-Auth-Token', token, httponly=True)
                return resp
            else:
                return jsonify({'error': 'invalid credentials'}), 401
    return jsonify({'error': 'user not found'}), 404


@app.route('/api/logout', methods=['POST'])
def api_logout():
    auth = request.headers.get('Authorization') or request.cookies.get('X-Auth-Token')
    token = None
    if auth and auth.lower().startswith('bearer '):
        token = auth.split(None, 1)[1]
    elif auth:
        token = auth
    sessions = _read_sessions()
    if token and token in sessions:
        sessions.pop(token, None)
        _write_sessions(sessions)
    resp = jsonify({'ok': True})
    resp.delete_cookie('X-Auth-Token')
    return resp


@app.route('/api/save', methods=['POST'])
@require_auth
def api_save():
    payload = request.get_json(force=True)
    if not payload or 'id' not in payload:
        return jsonify({'error': 'id required'}), 400
    db = init_db()
    auth_user = getattr(request, '_auth_user', {})
    annotator_name = auth_user.get('username')
    for it in db:
        if it.get('id') == payload['id']:
            it['annotated'] = True
            it['annotation'] = payload.get('annotation', {})
            it['annotation'].setdefault('annotator', payload.get('annotator') or annotator_name)
            it['annotation'].setdefault('timestamp', datetime.utcnow().isoformat() + 'Z')
            save_db(db)
            return jsonify({'ok': True})
    return jsonify({'error': 'id not found'}), 404


@app.route('/api/export')
def api_export():
    db = init_db()
    return jsonify(db)


@app.route('/api/export.csv')
def api_export_csv():
    db = init_db()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'clause_text', 'annotated', 'annotator', 'numeric_distance', 'distance_unit', 'feature', 'qualitative_flag', 'note', 'timestamp', 'reviewed', 'reviewer', 'review_timestamp'])
    for it in db:
        ann = it.get('annotation', {}) or {}
        clause = it.get('clause_text') or ''
        # replace newlines to keep CSV tidy
        clause = clause.replace('\n', ' ').replace('\r', ' ')
        writer.writerow([
            it.get('id', ''),
            clause,
            '1' if it.get('annotated') else '0',
            ann.get('annotator', ''),
            ann.get('numeric_distance', ''),
            ann.get('distance_unit', ''),
            ann.get('feature', ''),
            ann.get('qualitative_flag', ''),
            ann.get('note', ''),
            ann.get('timestamp', ''),
            '1' if it.get('reviewed') else '0',
            it.get('reviewer', ''),
            it.get('review_timestamp', ''),
        ])
    csv_text = output.getvalue()
    return Response(csv_text, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=annotations_export.csv'})


@app.route('/api/uploads')
def api_uploads():
    root = OUTPUTS_ROOT
    runs = []
    if root.exists() and root.is_dir():
        for child in sorted(root.iterdir()):
            if child.is_dir():
                info = {'run': child.name, 'files': []}
                for f in child.iterdir():
                    if f.is_file():
                        info['files'].append({'name': f.name, 'path': str(f.relative_to(APP_ROOT.parent))})
                runs.append(info)
            elif child.is_file():
                runs.append({'run': child.name, 'files': [{'name': child.name, 'path': str(child.relative_to(APP_ROOT.parent))}]})
    return jsonify(runs)


@app.route('/outputs/<path:subpath>')
def serve_output_file(subpath):
    # serve files stored under repo outputs/ directory
    target = OUTPUTS_ROOT
    full = target / subpath
    if not full.exists():
        return jsonify({'error': 'not found'}), 404
    # send from parent outputs directory
    return send_from_directory(str(target), subpath)


@app.route('/api/status')
def api_status():
    db = init_db()
    total = len(db)
    annotated = sum(1 for it in db if it.get('annotated'))
    return jsonify({'total': total, 'annotated': annotated, 'remaining': total-annotated})


@app.route('/api/list')
def api_list():
    db = init_db()
    return jsonify(db)


@app.route('/api/requeue', methods=['POST'])
@require_admin
def api_requeue():
    payload = request.get_json(force=True)
    if not payload or 'id' not in payload:
        return jsonify({'error': 'id required'}), 400
    db = init_db()
    for it in db:
        if it.get('id') == payload['id']:
            it['annotated'] = False
            it['annotation'] = {}
            save_db(db)
            return jsonify({'ok': True})
    return jsonify({'error': 'id not found'}), 404


@app.route('/api/requeue_bulk', methods=['POST'])
@require_admin
def api_requeue_bulk():
    payload = request.get_json(force=True)
    ids = payload.get('ids') if payload else None
    if not ids or not isinstance(ids, list):
        return jsonify({'error': 'ids (list) required'}), 400
    db = init_db()
    updated = 0
    for it in db:
        if it.get('id') in ids:
            it['annotated'] = False
            it['annotation'] = {}
            updated += 1
    save_db(db)
    return jsonify({'ok': True, 'updated': updated})


@app.route('/api/requeue_all', methods=['POST'])
@require_admin
def api_requeue_all():
    db = init_db()
    for it in db:
        it['annotated'] = False
        it['annotation'] = {}
    save_db(db)
    return jsonify({'ok': True, 'updated': len(db)})


@app.route('/admin')
def admin_ui():
    return send_from_directory(str(APP_ROOT), 'admin.html')


@app.route('/api/review', methods=['POST'])
@require_admin
def api_review():
    payload = request.get_json(force=True)
    if not payload or 'id' not in payload:
        return jsonify({'error': 'id required'}), 400
    reviewer = payload.get('reviewer', 'reviewer')
    db = init_db()
    for it in db:
        if it.get('id') == payload['id']:
            it['reviewed'] = True
            it['reviewer'] = reviewer
            it['review_timestamp'] = datetime.utcnow().isoformat() + 'Z'
            save_db(db)
            return jsonify({'ok': True})
    return jsonify({'error': 'id not found'}), 404


@app.route('/api/unreview', methods=['POST'])
def api_unreview():
    payload = request.get_json(force=True)
    if not payload or 'id' not in payload:
        return jsonify({'error': 'id required'}), 400
    db = init_db()
    for it in db:
        if it.get('id') == payload['id']:
            it['reviewed'] = False
            it.pop('reviewer', None)
            it.pop('review_timestamp', None)
            save_db(db)
            return jsonify({'ok': True})
    return jsonify({'error': 'id not found'}), 404


@app.route('/api/review_bulk', methods=['POST'])
@require_admin
def api_review_bulk():
    payload = request.get_json(force=True)
    ids = payload.get('ids') if payload else None
    reviewer = payload.get('reviewer', 'reviewer')
    if not ids or not isinstance(ids, list):
        return jsonify({'error': 'ids (list) required'}), 400
    db = init_db()
    updated = 0
    for it in db:
        if it.get('id') in ids:
            it['reviewed'] = True
            it['reviewer'] = reviewer
            it['review_timestamp'] = datetime.utcnow().isoformat() + 'Z'
            updated += 1
    save_db(db)
    return jsonify({'ok': True, 'updated': updated})


if __name__ == '__main__':
    init_db()
    print('Serving labeler on http://127.0.0.1:5000/')
    app.run(host='127.0.0.1', port=5000)
