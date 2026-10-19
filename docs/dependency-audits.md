# Dependency audit policy

CI reports dependency audits as **PASS**, **FAIL** (completed scan with unapproved findings), or **ERROR / unknown** (scanner, advisory database, network, timeout, or report failure). Audit errors exit nonzero and are never converted to success.

## Python

CI runs `python scripts/audit_python.py`, which invokes `pip-audit --format json` against both `requirements.txt` and `requirements-dev.txt` (the declared production and development dependency trees), rather than auditing unrelated packages preinstalled in the runner. A completed scan can return exit 1 because findings exist; the wrapper parses the JSON to distinguish this from a tool failure. All findings block unless an exact package + advisory exception is listed in `security/python-audit-allowlist.json`. Each exception must document its affected range, reason, compensating control, owner, and future review date. Expired or malformed exceptions block.

## npm

From `frontend/`, CI runs `npm run audit:high` and `npm run audit:test`. The gate fails closed on registry errors, malformed reports, unknown advisories, or an exception that does not match both package and GHSA.

## Local / offline use

Both scanners require network access to package registry/advisory services. Offline or proxy-blocked runs have an unknown result and exit nonzero; they are not clean scans. Unit tests use mocked reports and require no network, live credentials, or provider calls.
