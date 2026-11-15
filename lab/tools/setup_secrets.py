"""Generate local-only credentials. Existing files are never overwritten."""
import os
import secrets
from pathlib import Path

directory = Path(__file__).resolve().parents[1] / 'secrets'
directory.mkdir(mode=0o700, exist_ok=True)
for name in ['db_admin_password', 'db_app_password']:
    path = directory / name
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        print(name + ': retained existing file')
        continue
    with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
        output.write(secrets.token_urlsafe(32) + '\n')
    print(name + ': generated (value not displayed)')
