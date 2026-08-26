"""Create a user entry compatible with werkzeug.check_password_hash without external deps.

Usage:
  python tools/labeler/create_user_no_deps.py username password [role]

This writes to tools/labeler/data/users.json appending the new user.
"""
import sys
import json
import os
import hashlib
import secrets
from pathlib import Path

DATA_DIR = Path(__file__).parent / 'data'
USERS_FILE = DATA_DIR / 'users.json'

def make_pbkdf2_hash(password, iterations=150000):
    salt = secrets.token_hex(8)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations)
    return f'pbkdf2:sha256:{iterations}${salt}${dk.hex()}'

def main():
    if len(sys.argv) < 3:
        print('Usage: create_user_no_deps.py username password [role]')
        return
    username = sys.argv[1]
    password = sys.argv[2]
    role = sys.argv[3] if len(sys.argv) > 3 else 'annotator'
    DATA_DIR.mkdir(exist_ok=True)
    users = []
    if USERS_FILE.exists():
        try:
            users = json.loads(USERS_FILE.read_text(encoding='utf-8'))
        except Exception:
            users = []
    pwd_hash = make_pbkdf2_hash(password)
    users.append({'username': username, 'password_hash': pwd_hash, 'role': role})
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding='utf-8')
    print(f'Created user {username} with role {role}.')

if __name__ == '__main__':
    main()
