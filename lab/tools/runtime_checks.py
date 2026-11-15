"""Verify actual container and DB privileges without printing credentials."""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--project', default='hr-hosseini')
parser.add_argument('--evidence', required=True)
args = parser.parse_args()
compose = ['docker', 'compose', '-p', args.project, '-f', str(Path(__file__).resolve().parents[1] / 'compose.yaml')]
checks = []


def run(command):
    return subprocess.check_output(command, text=True).strip()


def check(name, condition, actual):
    checks.append({'name': name, 'passed': bool(condition), 'actual': actual})
    print(('PASS ' if condition else 'FAIL ') + name)


api_id = run(compose + ['ps', '-q', 'api'])
db_id = run(compose + ['ps', '-q', 'db'])
api = json.loads(run(['docker', 'inspect', api_id]))[0]
database = json.loads(run(['docker', 'inspect', db_id]))[0]
check('API uses non-root UID', api['Config']['User'] == '10001:10001', api['Config']['User'])
check('API root filesystem is read-only', api['HostConfig']['ReadonlyRootfs'], api['HostConfig']['ReadonlyRootfs'])
check('API drops all capabilities', 'ALL' in api['HostConfig']['CapDrop'], api['HostConfig']['CapDrop'])
check('API cannot gain privileges', 'no-new-privileges:true' in api['HostConfig']['SecurityOpt'], api['HostConfig']['SecurityOpt'])
check('DB has no published port', not database['HostConfig'].get('PortBindings'), database['HostConfig'].get('PortBindings'))
env_names = [value.split('=', 1)[0] for value in api['Config']['Env']]
check('API environment contains no DSN/password value', 'DATABASE_URL' not in env_names and 'POSTGRES_PASSWORD' not in env_names, env_names)
secret_names = [Path(m['Destination']).name for m in api['Mounts'] if m['Destination'].startswith('/run/secrets/')]
check('API mounts only application credential', secret_names == ['db_app_password'], secret_names)
networks = list(database['NetworkSettings']['Networks'])
internal = [json.loads(run(['docker', 'network', 'inspect', name]))[0]['Internal'] for name in networks]
check('DB is on internal networks only', bool(internal) and all(internal), dict(zip(networks, internal)))
probe = '''import json, app
with app.db() as c:
    row = c.execute("SELECT current_user, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
    permissions = c.execute("SELECT has_table_privilege(current_user, 'orders', 'SELECT'), has_table_privilege(current_user, 'orders', 'INSERT'), has_table_privilege(current_user, 'orders', 'UPDATE'), has_table_privilege(current_user, 'orders', 'DELETE'), has_schema_privilege(current_user, 'public', 'CREATE')").fetchone()
print(json.dumps({'role': row, 'permissions': permissions}))'''
db_permissions = json.loads(run(compose + ['exec', '-T', 'api', 'python', '-c', probe]))
check('DB app role has no admin attributes', db_permissions['role'] == ['lab_app', False, False, False, False, False], db_permissions['role'])
check('DB allows SELECT/INSERT only, no schema creation', db_permissions['permissions'] == [True, True, False, False, False], db_permissions['permissions'])
target = Path(args.evidence)
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps({'time_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                             'command': ' '.join(sys.argv), 'checks': checks,
                             'passed': all(c['passed'] for c in checks)}, indent=2), encoding='utf-8')
sys.exit(0 if all(c['passed'] for c in checks) else 1)
