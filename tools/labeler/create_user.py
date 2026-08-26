"""Utility to create a user entry with a password hash for tools/labeler/users.json

Usage:
  python tools/labeler/create_user.py username password [role]
Example:
  python tools/labeler/create_user.py annotator1 s3cret annotator
"""
import sys
import json
from pathlib import Path
from werkzeug.security import generate_password_hash

DATA_DIR = Path(__file__).parent / 'data'
USERS_FILE = DATA_DIR / 'users.json'

def main():
    if len(sys.argv) < 3:
        print('Usage: create_user.py username password [role]')
        return
    username = sys.argv[1]
    password = sys.argv[2]
    role = sys.argv[3] if len(sys.argv) > 3 else 'annotator'
    os = __import__('os')
    DATA_DIR.mkdir(exist_ok=True)
    users = []
    if USERS_FILE.exists():
        try:
            users = json.loads(USERS_FILE.read_text(encoding='utf-8'))
        except Exception:
            users = []
    pwd_hash = generate_password_hash(password)
    users.append({'username': username, 'password_hash': pwd_hash, 'role': role})
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding='utf-8')
    print(f'Created user {username} with role {role}.')

if __name__ == '__main__':
    main()
