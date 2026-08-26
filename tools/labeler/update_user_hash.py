"""Update or add a user in tools/labeler/data/users.json with a new pbkdf2 password hash.

Usage:
  python tools/labeler/update_user_hash.py username [password]

If password is omitted, a secure random password is generated and printed.
The script replaces any existing user entry with the same username.
"""
import sys
import json
import secrets
import hashlib
from pathlib import Path

DATA_DIR = Path(__file__).parent / 'data'
USERS_FILE = DATA_DIR / 'users.json'

def make_pbkdf2_hash(password, iterations=150000):
    salt = secrets.token_hex(8)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations)
    return f'pbkdf2:sha256:{iterations}${salt}${dk.hex()}'

def load_users():
    if not USERS_FILE.exists():
        return []
    try:
        return json.loads(USERS_FILE.read_text(encoding='utf-8'))
    except Exception:
        return []

def save_users(users):
    DATA_DIR.mkdir(exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding='utf-8')

def update_user(username, password, role='annotator'):
    users = load_users()
    pwd_hash = make_pbkdf2_hash(password)
    # remove existing with same username
    users = [u for u in users if u.get('username') != username]
    users.append({'username': username, 'password_hash': pwd_hash, 'role': role})
    save_users(users)

def main():
    if len(sys.argv) < 2:
        print('Usage: update_user_hash.py username [password]')
        return
    username = sys.argv[1]
    password = sys.argv[2] if len(sys.argv) > 2 else None
    role = sys.argv[3] if len(sys.argv) > 3 else None
    if not password:
        # generate a secure random password
        password = secrets.token_urlsafe(12)
    if not role:
        # try to preserve existing role if present
        users = load_users()
        for u in users:
            if u.get('username') == username and 'role' in u:
                role = u['role']
                break
        if not role:
            role = 'annotator'
    update_user(username, password, role)
    print(f'Updated user: {username}')
    print(f'Password: {password}')

if __name__ == '__main__':
    main()
