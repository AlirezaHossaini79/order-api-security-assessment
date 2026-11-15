import json
import os
import re
import threading
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import psycopg


TOKENS = {'lab-alice': 'alice', 'lab-bob': 'bob', 'lab-ops': 'ops'}
DB_PASSWORD = Path(os.environ.get('DB_PASSWORD_FILE', '/run/secrets/db_app_password')).read_text().strip()
state = {'delay_ms': 0, 'business_fail': False, 'release': 'v1'}
counts = defaultdict(int)
duration_sum = 0.0
duration_count = 0
lock = threading.Lock()


def db():
    return psycopg.connect(host=os.environ.get('DB_HOST', 'db'),
                           dbname=os.environ.get('DB_NAME', 'lab'),
                           user=os.environ.get('DB_USER', 'lab_app'),
                           password=DB_PASSWORD, connect_timeout=3)


def init():
    for _ in range(40):
        try:
            with db() as connection:
                connection.execute('SELECT id, owner, item, request_key FROM orders LIMIT 0')
            return
        except psycopg.Error:
            time.sleep(1)
    raise RuntimeError('database unavailable at startup')


class Handler(BaseHTTPRequestHandler):
    def route_label(self):
        path = urlsplit(self.path).path
        if re.fullmatch(r'/orders/[0-9]+', path):
            return '/orders/:id'
        return path if path in {'/orders', '/live', '/ready', '/metrics', '/debug/config', '/lab/control'} else '/unknown'

    def log_message(self, fmt, *args):
        # Never log user-controlled URLs, authorization headers or database errors.
        print(json.dumps({'event': 'http', 'route': self.route_label(), 'method': self.command}), flush=True)

    def send(self, status, value, typ='application/json'):
        data = (json.dumps(value) if typ == 'application/json' else value).encode()
        self.send_response(status)
        self.send_header('Content-Type', typ)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if status == 401:
            self.send_header('WWW-Authenticate', 'Bearer')
        self.end_headers()
        self.wfile.write(data)
        return status

    def body(self):
        length = int(self.headers.get('Content-Length', '0'))
        if length < 0 or length > 16384 or self.headers.get('Transfer-Encoding'):
            raise ValueError('invalid body size')
        value = json.loads(self.rfile.read(length) or b'{}')
        if not isinstance(value, dict):
            raise ValueError('JSON object required')
        return value

    def do_GET(self):
        self.run_request()

    def do_POST(self):
        self.run_request()

    def run_request(self):
        global duration_sum, duration_count
        start = time.monotonic()
        status = 500
        try:
            status = self.route()
        except (psycopg.Error, OSError):
            status = self.send(503, {'error': 'dependency unavailable'})
        except (ValueError, TypeError, OverflowError):
            status = self.send(400, {'error': 'invalid request'})
        except Exception:
            status = self.send(500, {'error': 'internal error'})
        finally:
            with lock:
                counts[(self.route_label(), str(status))] += 1
                duration_sum += time.monotonic() - start
                duration_count += 1

    def route(self):
        path = urlsplit(self.path).path
        if path in {'/live', '/ready'}:
            if self.command != 'GET':
                return self.send(405, {'error': 'method not allowed'})
            if path == '/live':
                with lock:
                    release = state['release']
                return self.send(200, {'alive': True, 'release': release})
            with db() as connection:
                connection.execute('SELECT 1')
            return self.send(200, {'ready': True})

        authorization = self.headers.get('Authorization', '')
        actor = TOKENS.get(authorization[7:]) if authorization.startswith('Bearer ') else None
        if not actor:
            return self.send(401, {'error': 'authentication required'})

        if path in {'/lab/control', '/debug/config', '/metrics'}:
            if actor != 'ops':
                return self.send(403, {'error': 'forbidden'})
            if path == '/lab/control':
                if self.command != 'POST':
                    return self.send(405, {'error': 'method not allowed'})
                body = self.body()
                if set(body) - set(state):
                    raise ValueError('unknown control')
                if 'delay_ms' in body and (type(body['delay_ms']) is not int or not 0 <= body['delay_ms'] <= 10000):
                    raise ValueError('invalid delay')
                if 'business_fail' in body and type(body['business_fail']) is not bool:
                    raise ValueError('invalid failure flag')
                if 'release' in body and (not isinstance(body['release'], str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,64}', body['release'])):
                    raise ValueError('invalid release label')
                with lock:
                    state.update(body)
                    result = dict(state)
                return self.send(200, result)
            if self.command != 'GET':
                return self.send(405, {'error': 'method not allowed'})
            if path == '/debug/config':
                return self.send(200, {'mode': 'synthetic-lab'})
            with lock:
                lines = ['# TYPE lab_http_requests_total counter']
                for (route, status), count in counts.items():
                    lines.append('lab_http_requests_total{path=' + json.dumps(route) + ',status="' + status + '"} ' + str(count))
                lines += ['# TYPE lab_http_request_duration_seconds summary',
                          'lab_http_request_duration_seconds_sum ' + str(duration_sum),
                          'lab_http_request_duration_seconds_count ' + str(duration_count)]
            return self.send(200, '\n'.join(lines) + '\n', 'text/plain')

        if path == '/orders':
            if self.command != 'POST':
                return self.send(405, {'error': 'method not allowed'})
            body = self.body()
            item = body.get('item')
            request_key = self.headers.get('Idempotency-Key', '')
            if not isinstance(item, str) or not item.strip() or len(item) > 1000 or len(request_key) > 128:
                raise ValueError('invalid order')
            with lock:
                delay_ms, business_fail = state['delay_ms'], state['business_fail']
            time.sleep(delay_ms / 1000)
            if business_fail:
                return self.send(200, {'ok': False, 'error': 'order rejected'})
            with db() as connection:
                row = connection.execute('INSERT INTO orders(owner,item,request_key) VALUES (%s,%s,%s) RETURNING id',
                                         (actor, item, request_key)).fetchone()
            return self.send(201, {'ok': True, 'id': row[0]})

        if re.fullmatch(r'/orders/[0-9]+', path):
            if self.command != 'GET':
                return self.send(405, {'error': 'method not allowed'})
            order_id = int(path.rsplit('/', 1)[1])
            if order_id > 9223372036854775807:
                return self.send(404, {'error': 'missing'})
            with db() as connection:
                row = connection.execute('SELECT id,owner,item,request_key FROM orders WHERE id=%s AND (owner=%s OR %s)',
                                         (order_id, actor, actor == 'ops')).fetchone()
            if not row:
                return self.send(404, {'error': 'missing'})
            return self.send(200, dict(zip(['id', 'owner', 'item', 'request_key'], row)))
        return self.send(404, {'error': 'missing'})


if __name__ == '__main__':
    init()
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
