"""Run in an isolated temporary project, then remove only its new resources."""
import datetime as dt
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

source = Path(__file__).resolve().parents[1]
evidence = source.parent / 'evidence'
evidence.mkdir(exist_ok=True)
project = 'hr-hosseini-check-' + uuid.uuid4().hex[:10]
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
environment = dict(os.environ, LAB_BIND_ADDRESS='127.0.0.1', LAB_PORT=str(port))
log_path = evidence / 'clean-run.log'
with tempfile.TemporaryDirectory(prefix='hosseini-clean-') as temp, log_path.open('w', encoding='utf-8') as log:
    target = Path(temp) / 'lab'
    shutil.copytree(source, target, ignore=shutil.ignore_patterns('secrets', '.env', '__pycache__', '*.before-public-port'))
    compose = ['docker', 'compose', '-p', project, '-f', str(target / 'compose.yaml')]

    def run(command):
        log.write('\nUTC: ' + dt.datetime.now(dt.timezone.utc).isoformat() + '\nCOMMAND: ' + json.dumps(command) + '\n')
        log.flush()
        result = subprocess.run(command, cwd=target, env=environment, stdout=log, stderr=subprocess.STDOUT)
        log.flush()
        if result.returncode:
            raise RuntimeError('command failed: ' + command[0])

    try:
        # Random project ID and empty source copy: no existing volume or secrets reused.
        run([sys.executable, 'tools/setup_secrets.py'])
        run(compose + ['up', '-d', '--build'])
        base = 'http://127.0.0.1:' + str(port)
        run([sys.executable, 'tools/smoke.py', '--url', base])
        run([sys.executable, 'tests/security_checks.py', '--url', base, '--expect', 'fixed', '--evidence', str(evidence / 'clean-security.json')])
        run([sys.executable, 'tools/runtime_checks.py', '--project', project, '--evidence', str(evidence / 'clean-runtime.json')])
        run([sys.executable, 'tools/control.py', '--url', base])
        run([sys.executable, 'tools/traffic.py', '--url', base, '--requests', '100', '--workers', '5'])
        log.write('\nPASS: clean startup, security, runtime privileges, ops helper, sample traffic\n')
        print('PASS: clean environment; raw log: ' + str(log_path))
    finally:
        # Only the unique temporary project created by this invocation is removed.
        run(compose + ['down', '-v'])
