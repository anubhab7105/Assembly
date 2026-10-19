from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch
import pytest
from scripts.audit_python import evaluate_findings, load_allowlist, parse_findings, render_summary, run_audit

def report_with_vuln():
    return [{"name":"demo-package","version":"1.2.3","vulns":[{"id":"PYSEC-2025-0001","fix_versions":["1.2.4"],"aliases":["GHSA-abcd-efgh-ijkl"]}]}]

class Result:
    def __init__(self, code, payload=None, stderr=""):
        self.returncode = code
        self.stdout = "" if payload is None else json.dumps(payload)
        self.stderr = stderr

def test_audit_targets_declared_manifests():
    from scripts.audit_python import run_audit
    with patch("scripts.audit_python.subprocess.run", return_value=Result(0, [])) as mocked:
        run_audit()
    command = mocked.call_args.args[0]
    assert command[-4:] == ["--requirement", "requirements.txt", "--requirement", "requirements-dev.txt"]

def test_clean_scan():
    assert parse_findings([]) == []
    with patch("scripts.audit_python.subprocess.run", return_value=Result(0, [])): assert run_audit()[0] == 0

def test_scan_finding_does_not_get_misread_as_tool_failure():
    with patch("scripts.audit_python.subprocess.run", return_value=Result(1, report_with_vuln())):
        code, findings = run_audit()
    assert code == 1 and findings[0]["package"] == "demo-package"

def test_unapproved_finding_blocks_and_summary_is_actionable():
    findings = parse_findings(report_with_vuln())
    allowed, blocking = evaluate_findings(findings, [])
    summary = render_summary(completed=True, findings=findings, allowlisted=allowed, blocking=blocking, error=None)
    assert len(blocking) == 1 and "Status: FAIL" in summary and "demo-package==1.2.3" in summary and "1.2.4" in summary

def test_exact_package_and_advisory_exception_only():
    findings = parse_findings(report_with_vuln())
    exception = {"package":"demo-package","id":"PYSEC-2025-0001","affected_range":">=1.0,<1.3","reason":"Temporary hold pending upstream fix.","compensating_control":"Development-only package not deployed in runtime.","owner":"assembly-maintainers","review_by":"2099-01-01"}
    allowed, blocking = evaluate_findings(findings, [exception])
    assert len(allowed) == 1 and blocking == []
    allowed, blocking = evaluate_findings([{**findings[0],"package":"other-package"}], [exception])
    assert allowed == [] and len(blocking) == 1
    out_of_range = [{**findings[0], "version": "2.0.0"}]
    allowed, blocking = evaluate_findings(out_of_range, [exception])
    assert allowed == [] and len(blocking) == 1

def test_exception_can_match_canonical_alias_but_is_version_bounded():
    findings = parse_findings(report_with_vuln())
    exception = {"package":"demo-package","id":"GHSA-abcd-efgh-ijkl","affected_range":">=1.0,<1.3","reason":"Temporary hold pending upstream fix.","compensating_control":"Development-only package not deployed in runtime.","owner":"assembly-maintainers","review_by":"2099-01-01"}
    allowed, blocking = evaluate_findings(findings, [exception])
    assert len(allowed) == 1 and blocking == []

def test_expired_exception_fails_closed(tmp_path: Path):
    path = tmp_path / "allowlist.json"
    path.write_text(json.dumps([{"package":"demo-package","id":"PYSEC-2025-0001","affected_range":">=1.0","reason":"temporary","compensating_control":"control","owner":"maintainer","review_by":"2025-01-01"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="expired allowlist"): load_allowlist(path, today=date(2026,10,19))

def test_invalid_affected_range_fails_closed(tmp_path: Path):
    path = tmp_path / "allowlist.json"
    path.write_text(json.dumps([{"package":"demo-package","id":"PYSEC-2025-0001","affected_range":"*","reason":"temporary","compensating_control":"control","owner":"maintainer","review_by":"2099-01-01"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="affected_range"):
        load_allowlist(path)

def test_malformed_exception_fails_closed(tmp_path: Path):
    path = tmp_path / "allowlist.json"
    path.write_text(json.dumps([{"package":"demo-package","id":"PYSEC-2025-0001"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="missing required fields"): load_allowlist(path)

def test_tool_error_and_network_error_fail_unknown():
    with patch("scripts.audit_python.subprocess.run", return_value=Result(2,None,"registry offline")):
        with pytest.raises(RuntimeError, match="execution failed"): run_audit()
    with patch("scripts.audit_python.subprocess.run", side_effect=OSError("offline")):
        with pytest.raises(RuntimeError, match="could not run"): run_audit()
    from subprocess import TimeoutExpired
    with patch("scripts.audit_python.subprocess.run", side_effect=TimeoutExpired("pip-audit", 300)):
        with pytest.raises(RuntimeError, match="could not run"): run_audit()

def test_invalid_or_missing_json_is_not_clean():
    with patch("scripts.audit_python.subprocess.run", return_value=Result(1, [])):
        with pytest.raises(RuntimeError, match="reported no findings"): run_audit()
    with patch("scripts.audit_python.subprocess.run", return_value=Result(0,None)):
        with pytest.raises(RuntimeError, match="no JSON report"): run_audit()

def test_summary_distinguishes_unknown_state():
    summary = render_summary(completed=False, findings=[], allowlisted=[], blocking=[], error="registry unavailable")
    assert "AUDIT ERROR" in summary and "result unknown" in summary

def test_current_pip_audit_json_envelope_is_supported():
    report = {"dependencies": report_with_vuln(), "fixes": []}
    assert parse_findings(report)[0]["id"] == "PYSEC-2025-0001"

def test_malformed_pip_audit_envelope_is_not_clean():
    with pytest.raises(ValueError, match="dependencies array"):
        parse_findings({"results": []})
