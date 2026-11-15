"""Safe HTTP checks for this synthetic lab; standard library only."""
import argparse
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def redact(value):
    if isinstance(value, dict):
        return {k: ('[REDACTED]' if k.lower() in {'database_url', 'dsn', 'password'} else redact(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return re.sub(r'postgres(?:ql)?://[^\s"\']+', '[REDACTED_DSN]', value)
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:18080')
    parser.add_argument('--expect', choices=['vulnerable', 'fixed'], default='fixed')
    parser.add_argument('--evidence', required=True)
    args = parser.parse_args()
    records, checks = [], []

    def request(method, path, actor=None, body=None, token=None):
        headers = {}
        if actor or token:
            headers['Authorization'] = 'Bearer ' + (token or 'lab-' + actor)
        payload = None
        if body is not None:
            headers['Content-Type'] = 'application/json'
            payload = json.dumps(body).encode()
        req = urllib.request.Request(args.url.rstrip('/') + path, data=payload, headers=headers, method=method)
        try:
            response = urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read().decode()
            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                result = raw
            status = response.status
            records.append({'time_utc': now(), 'request': {'method': method, 'path': path,
                            'actor': actor, 'headers': {k: ('[REDACTED]' if k == 'Authorization' else v)
                            for k, v in headers.items()}, 'body': body},
                            'response': {'status': status, 'body': redact(result)}})
            return status, result

    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})
        print(('PASS ' if condition else 'FAIL ') + name, flush=True)

    try:
        created = {}
        for actor in ['alice', 'bob']:
            status, body = request('POST', '/orders', actor, {'item': actor + '-private-check'})
            check(actor + ' creates order', status == 201 and body.get('ok') is True)
            created[actor] = body['id']

        status, body = request('GET', '/orders/' + str(created['bob']), 'alice')
        check('alice cannot read bob' if args.expect == 'fixed' else 'reproduce cross-user disclosure',
              status in (403, 404) and 'owner' not in body if args.expect == 'fixed'
              else status == 200 and body.get('owner') == 'bob')
        status, body = request('GET', '/debug/config')
        leaked = isinstance(body, dict) and 'database_url' in body
        check('anonymous config denied' if args.expect == 'fixed' else 'reproduce DSN disclosure',
              status == 401 and not leaked if args.expect == 'fixed' else status == 200 and leaked)
        status, _ = request('POST', '/lab/control', body={})
        check('anonymous control denied' if args.expect == 'fixed' else 'reproduce unprotected control',
              status == (401 if args.expect == 'fixed' else 200))

        marker = 'synthetic-query-marker'
        request('GET', '/live?probe=' + marker)
        status, metrics = request('GET', '/metrics', 'ops' if args.expect == 'fixed' else None)
        check('metrics query data absent' if args.expect == 'fixed' else 'reproduce query data in public metrics',
              status == 200 and (marker not in metrics if args.expect == 'fixed' else marker in metrics))

        if args.expect == 'fixed':
            for actor in ['alice', 'bob']:
                own = '/orders/' + str(created[actor])
                other = '/orders/' + str(created['bob' if actor == 'alice' else 'alice'])
                status, body = request('GET', own, actor)
                check(actor + ' reads own order', status == 200 and body.get('owner') == actor)
                status, body = request('GET', other, actor)
                check(actor + ' cannot read other owner', status in (403, 404) and 'item' not in body)
                status, body = request('GET', own, 'ops')
                check('ops reads ' + actor + ' order', status == 200 and body.get('owner') == actor)
                for method, path, data in [('POST', '/lab/control', {}), ('GET', '/debug/config', None),
                                           ('GET', '/metrics', None)]:
                    status, _ = request(method, path, actor, data)
                    check(actor + ' denied ' + path, status == 403)
            for method, path, data in [('POST', '/orders', {'item': 'unauthorized'}),
                                       ('GET', '/orders/' + str(created['alice']), None),
                                       ('POST', '/lab/control', {}), ('GET', '/debug/config', None),
                                       ('GET', '/metrics', None)]:
                for token in [None, 'invalid-token']:
                    status, _ = request(method, path, body=data, token=token)
                    check(('missing' if token is None else 'invalid') + ' token denied ' + path, status == 401)
            status, _ = request('POST', '/lab/control', 'ops', {})
            check('ops control works', status == 200)
            status, body = request('POST', '/lab/control', 'ops', {'delay_ms': -1})
            check('control rejects invalid values', status == 400)
            status, body = request('GET', '/debug/config', 'ops')
            check('ops config contains no DSN or password', status == 200 and
                  not any(word in json.dumps(body).lower() for word in ['postgres', 'database_url', 'password', 'dsn']))
            status, _ = request('POST', '/orders', 'alice', {'item': {'invalid': True}})
            check('invalid item rejected', status == 400)
            status, _ = request('POST', '/orders/' + str(created['alice']), 'alice', {})
            check('order read rejects POST', status == 405)
            for path in ['/live', '/ready']:
                status, _ = request('GET', path)
                check(path + ' remains available', status == 200)
    except Exception as exc:
        check('test execution: ' + type(exc).__name__ + ': ' + str(exc), False)
    report = {'time_utc': now(), 'command': ' '.join(sys.argv), 'base_url': args.url,
              'expect': args.expect, 'checks': checks, 'requests': records,
              'passed': all(c['passed'] for c in checks)}
    target = Path(args.evidence)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{sum(c["passed"] for c in checks)}/{len(checks)} checks passed; evidence: {target}')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
