import json
import urllib.request

BASE = 'http://127.0.0.1:5000'

def post(path, data, token=None):
    url = BASE + path
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode('utf-8')

def get(path, token=None):
    url = BASE + path
    req = urllib.request.Request(url, method='GET')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode('utf-8')

def main():
    print('Logging in as admin...')
    try:
        r = post('/api/login', {'username':'admin','password':'S-qy2iWWgzyFqRvf'})
        j = json.loads(r)
        token = j.get('token')
        print('Login response:', j)
    except Exception as e:
        print('Login failed:', e)
        return

    print('Fetching list...')
    try:
        r = get('/api/list', token=token)
        items = json.loads(r)
        print('Items count:', len(items))
    except Exception as e:
        print('List failed:', e)
        return

    print('Calling requeue_all...')
    try:
        r = post('/api/requeue_all', {}, token=token)
        print('requeue_all response:', r)
    except Exception as e:
        print('requeue_all failed:', e)

    # pick up to 2 ids and mark reviewed
    ids = [it.get('id') for it in items[:2]]
    if ids:
        print('Reviewing ids:', ids)
        try:
            r = post('/api/review_bulk', {'ids': ids, 'reviewer': 'smoketester'}, token=token)
            print('review_bulk response:', r)
        except Exception as e:
            print('review_bulk failed:', e)

    print('Smoke test done.')

if __name__ == '__main__':
    main()
