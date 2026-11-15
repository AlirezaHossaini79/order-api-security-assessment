# Evidence

All JSON evidence includes a UTC timestamp, command and individual results. HTTP evidence preserves response content except deliberate redaction of Authorization and database credentials. No real secret is included.

- `before.json`: synthetic baseline, 6 checks demonstrating the original issues.
- `after.json`: 35 security and functionality checks against the deployed fixed lab.
- `runtime.json`: 10 checks of actual Docker/DB privileges on that deployment.
- `clean-security.json`: 35 security/functionality checks with new volume and credentials.
- `clean-runtime.json`: 10 runtime checks on that isolated clean deployment.
- `clean-run.log`: timestamped raw setup/build/test/100-request traffic output and teardown for the temporary project only.

Use `lab/tests/security_checks.py`, `lab/tools/runtime_checks.py` and `lab/tools/verify_clean.py` to reproduce. The complete invocation is also recorded inside each result. A successful `--expect vulnerable` run means reproduction of the defects, not that the application was secure.
