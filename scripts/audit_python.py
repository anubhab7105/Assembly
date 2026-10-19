#!/usr/bin/env python3
"""Fail-closed pip-audit gate with a scoped exception list and CI summary."""
from __future__ import annotations
import json, os, subprocess, sys
from datetime import date
from pathlib import Path
from typing import Any
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version
from packaging.utils import canonicalize_name

ALLOWLIST_PATH = Path(__file__).resolve().parents[1] / "security" / "python-audit-allowlist.json"

def load_allowlist(path: Path = ALLOWLIST_PATH, *, today: date | None = None) -> list[dict[str, Any]]:
    current_date = today or date.today()
    try: entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise ValueError(f"cannot read valid allowlist: {exc}") from exc
    if not isinstance(entries, list): raise ValueError("allowlist must be a JSON array")
    required = {"package", "id", "affected_range", "reason", "compensating_control", "owner", "review_by"}
    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not required.issubset(entry): raise ValueError(f"allowlist entry {index + 1} is missing required fields")
        for field in required:
            if not isinstance(entry[field], str) or not entry[field].strip(): raise ValueError(f"allowlist entry {index + 1} has empty/invalid {field}")
        key = (canonicalize_name(entry["package"]), entry["id"].upper())
        if key in seen: raise ValueError(f"duplicate allowlist entry for {key[0]} {key[1]}")
        seen.add(key)
        try: SpecifierSet(entry["affected_range"])
        except InvalidSpecifier as exc: raise ValueError(f"allowlist entry {index + 1} affected_range must be a valid PEP 440 specifier") from exc
        try: review_by = date.fromisoformat(entry["review_by"])
        except ValueError as exc: raise ValueError(f"allowlist entry {index + 1} review_by must be YYYY-MM-DD") from exc
        if review_by < current_date: raise ValueError(f"expired allowlist exception: {entry['package']} {entry['id']} review date {review_by}")
    return entries

def parse_findings(report: Any) -> list[dict[str, Any]]:
    # pip-audit 2.10+ emits an object with a dependencies array; older releases emitted the array directly.
    if isinstance(report, dict) and isinstance(report.get("dependencies"), list):
        dependencies = report["dependencies"]
    elif isinstance(report, list):
        dependencies = report
    else:
        raise ValueError("pip-audit output has no dependencies array; scanner output is incomplete")
    findings = []
    for item in dependencies:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not isinstance(item.get("version"), str): raise ValueError("pip-audit returned a malformed finding")
        vulns = item.get("vulns")
        if not isinstance(vulns, list): raise ValueError(f"pip-audit output for {item['name']} has no vulnerability list")
        for vuln in vulns:
            if not isinstance(vuln, dict) or not isinstance(vuln.get("id"), str): raise ValueError(f"pip-audit returned malformed vulnerability details for {item['name']}")
            findings.append({"package": item["name"], "version": item["version"], "id": vuln["id"].upper(), "fix_versions": vuln.get("fix_versions", []) if isinstance(vuln.get("fix_versions", []), list) else [], "aliases": vuln.get("aliases", []) if isinstance(vuln.get("aliases", []), list) else []})
    return findings

def evaluate_findings(findings: list[dict[str, Any]], allowlist: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    active = {(canonicalize_name(entry["package"]), entry["id"].upper()): entry for entry in allowlist}
    allowed, blocking = [], []
    for finding in findings:
        candidate_ids = {finding["id"].upper()}
        candidate_ids.update(alias.upper() for alias in finding.get("aliases", []) if isinstance(alias, str))
        exception = None
        for vuln_id in candidate_ids:
            candidate = active.get((canonicalize_name(finding["package"]), vuln_id))
            if candidate is None:
                continue
            try:
                version_matches = Version(finding["version"]) in SpecifierSet(candidate["affected_range"])
            except (InvalidVersion, InvalidSpecifier):
                version_matches = False
            if version_matches:
                exception = candidate
                break
        if exception: allowed.append({**finding, "exception": exception})
        else: blocking.append(finding)
    return allowed, blocking

def render_summary(*, completed: bool, findings: list[dict[str, Any]], allowlisted: list[dict[str, Any]], blocking: list[dict[str, Any]], error: str | None) -> str:
    lines = ["## Python dependency audit", ""]
    if error: lines += ["**Status: AUDIT ERROR — result unknown.**", "", "- Scan completed: no", "- Findings: unknown", f"- Error: {error}", ""]
    elif not completed: lines += ["**Status: AUDIT ERROR — result unknown.**", "", "- Scan completed: no", "- Findings: unknown", ""]
    else: lines += [f"**Status: {'PASS' if not blocking else 'FAIL'}**", "", "- Scan completed: yes", f"- Findings returned: {len(findings)}", f"- Allowlisted findings: {len(allowlisted)}", f"- Unapproved findings: {len(blocking)}", ""]
    if allowlisted:
        lines += ["### Time-bounded exceptions", ""]
        for finding in allowlisted:
            entry = finding["exception"]
            lines.append(f"- `{finding['package']}=={finding['version']}` / `{finding['id']}`: owner `{entry['owner']}`, review by {entry['review_by']}. {entry['reason']}")
        lines.append("")
    if blocking:
        lines += ["### Findings requiring action", ""]
        for finding in blocking: lines.append(f"- `{finding['package']}=={finding['version']}` / `{finding['id']}`; fixes: {', '.join(finding['fix_versions']) or 'no fix version reported'}")
        lines.append("")
    lines.append("A green check means the audit completed and every finding is covered by an active, exact package-and-advisory exception. Scanner or database errors are never treated as a clean scan.")
    return "\n".join(lines) + "\n"

def run_audit(command: list[str] | None = None) -> tuple[int, list[dict[str, Any]]]:
    cmd = command or [sys.executable, "-m", "pip_audit", "--format", "json", "--progress-spinner", "off", "--requirement", "requirements.txt", "--requirement", "requirements-dev.txt"]
    try: result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc: raise RuntimeError(f"pip-audit could not run to completion: {type(exc).__name__}") from exc
    if result.returncode not in (0, 1):
        raise RuntimeError(f"pip-audit execution failed with exit code {result.returncode}; raw stderr omitted to avoid exposing registry credentials")
    if not result.stdout.strip(): raise RuntimeError("pip-audit produced no JSON report; scan status unknown")
    try: report = json.loads(result.stdout)
    except json.JSONDecodeError as exc: raise RuntimeError("pip-audit output was not valid JSON; scan status unknown") from exc
    findings = parse_findings(report)
    if result.returncode == 1 and not findings: raise RuntimeError("pip-audit exited 1 but reported no findings; treating scan as incomplete")
    return result.returncode, findings

def main() -> int:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    completed, findings, allowlisted, blocking, error = False, [], [], [], None
    try:
        exceptions = load_allowlist()
        _scanner_exit, findings = run_audit()
        completed = True
        allowlisted, blocking = evaluate_findings(findings, exceptions)
        exit_code = 1 if blocking else 0
        for f in allowlisted[:20]: print(f"python-audit: ALLOWLISTED {f['package']}=={f['version']} {f['id']} review_by={f['exception']['review_by']}")
        for f in blocking[:20]: print(f"python-audit: BLOCKING {f['package']}=={f['version']} {f['id']}")
        print(f"python-audit: {'PASS' if not exit_code else 'FAIL'} scan_completed=yes findings={len(findings)} allowlisted={len(allowlisted)} blocking={len(blocking)}")
    except (ValueError, RuntimeError) as exc:
        error = str(exc)
        print(f"python-audit: ERROR — scan status unknown: {error}", file=sys.stderr)
        exit_code = 2
    summary = render_summary(completed=completed, findings=findings, allowlisted=allowlisted, blocking=blocking, error=error)
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as stream: stream.write(summary)
        except OSError as exc:
            print(f"python-audit: failed to write GitHub summary: {exc}", file=sys.stderr)
            return 2
    else: print(summary)
    return exit_code

if __name__ == "__main__": raise SystemExit(main())
