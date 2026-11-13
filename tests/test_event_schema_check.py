"""Offline command-line checks for the committed frontend event contract."""

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORTER = PROJECT_ROOT / "scripts" / "export_event_schema.py"


def run_export(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(EXPORTER), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=PROJECT_ROOT,
    )


def test_check_accepts_committed_artifact_without_writing() -> None:
    artifact = PROJECT_ROOT / "frontend" / "event-schema.json"
    before = artifact.read_bytes()
    modified = artifact.stat().st_mtime_ns
    result = run_export("--check")
    assert result.returncode == 0, result.stderr
    assert "up to date" in result.stdout
    assert artifact.read_bytes() == before
    assert artifact.stat().st_mtime_ns == modified


@pytest.mark.parametrize("change", ["payload", "event_type", "formatting"])
def test_check_rejects_stale_artifact_without_writing(tmp_path, change) -> None:
    import json

    artifact = tmp_path / "event-schema.json"
    generated = run_export("--out", str(artifact))
    assert generated.returncode == 0, generated.stderr
    bundle = json.loads(artifact.read_text(encoding="utf-8"))
    if change == "payload":
        bundle["payloads"]["timer.tick"]["properties"]["seconds_remaining"]["title"] = (
            "Stale"
        )
    elif change == "event_type":
        bundle["event_types"].append("obsolete.event")
    artifact.write_text(
        json.dumps(bundle, indent=4 if change == "formatting" else 2) + "\n",
        encoding="utf-8",
    )
    before = artifact.read_bytes()
    modified = artifact.stat().st_mtime_ns
    result = run_export("--check", "--out", str(artifact))
    assert result.returncode == 1
    assert "out of date" in result.stderr
    assert "python scripts/export_event_schema.py" in result.stderr
    assert "---" in result.stderr and "+++" in result.stderr
    assert artifact.read_bytes() == before
    assert artifact.stat().st_mtime_ns == modified


def test_check_rejects_missing_artifact_without_creating_it(tmp_path) -> None:
    artifact = tmp_path / "missing.json"
    result = run_export("--check", "--out", str(artifact))
    assert result.returncode == 1
    assert "Cannot read" in result.stderr
    assert "python scripts/export_event_schema.py" in result.stderr
    assert not artifact.exists()


def test_check_rejects_unreadable_path(tmp_path) -> None:
    result = run_export("--check", "--out", str(tmp_path))
    assert result.returncode == 1
    assert "Cannot read" in result.stderr
    assert tmp_path.is_dir()


def test_generate_then_check_uses_lf_even_with_windows_text_defaults(
    tmp_path, monkeypatch
) -> None:
    import os
    import runpy

    original_write_text = Path.write_text

    def windows_write_text(self, data, encoding=None, errors=None, newline=None):
        # Emulate Windows' default text-file translation without claiming a
        # Windows run. An explicit newline policy must still be respected.
        return original_write_text(
            self,
            data,
            encoding=encoding,
            errors=errors,
            newline="\r\n" if newline is None else newline,
        )

    monkeypatch.setattr(Path, "write_text", windows_write_text)
    monkeypatch.setattr(os, "linesep", "\r\n")
    artifact = tmp_path / "schema with spaces.json"
    main = runpy.run_path(str(EXPORTER))["main"]
    monkeypatch.setattr(sys, "argv", [str(EXPORTER), "--out", str(artifact)])
    assert main() == 0
    generated = artifact.read_bytes()
    modified = artifact.stat().st_mtime_ns
    assert b"\r\n" not in generated
    monkeypatch.setattr(sys, "argv", [str(EXPORTER), "--out", str(artifact), "--check"])
    assert main() == 0
    assert artifact.read_bytes() == generated
    assert artifact.stat().st_mtime_ns == modified


def test_check_accepts_crlf_checkout_without_writing(tmp_path) -> None:
    artifact = tmp_path / "schema with spaces.json"
    generated = run_export("--out", str(artifact))
    assert generated.returncode == 0, generated.stderr
    artifact.write_bytes(artifact.read_bytes().replace(b"\n", b"\r\n"))
    before = artifact.read_bytes()
    modified = artifact.stat().st_mtime_ns
    result = run_export("--check", "--out", str(artifact))
    assert result.returncode == 0, result.stderr
    assert "up to date" in result.stdout
    assert artifact.read_bytes() == before
    assert artifact.stat().st_mtime_ns == modified


def test_check_rejects_crlf_schema_drift_without_writing(tmp_path) -> None:
    import json

    artifact = tmp_path / "event-schema.json"
    generated = run_export("--out", str(artifact))
    assert generated.returncode == 0, generated.stderr
    bundle = json.loads(artifact.read_bytes())
    bundle["event_types"].append("obsolete.event")
    artifact.write_bytes(
        (json.dumps(bundle, indent=2) + "\n").replace("\n", "\r\n").encode()
    )
    before = artifact.read_bytes()
    modified = artifact.stat().st_mtime_ns
    result = run_export("--check", "--out", str(artifact))
    assert result.returncode == 1
    assert "out of date" in result.stderr
    assert "obsolete.event" in result.stderr
    assert artifact.read_bytes() == before
    assert artifact.stat().st_mtime_ns == modified
