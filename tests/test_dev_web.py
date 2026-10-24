"""Unit tests for the managed one-command local web launcher."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dev_web.py"
SPEC = importlib.util.spec_from_file_location("assembly_dev_web", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
dev_web = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dev_web)


def test_port_check_rejects_ports_that_are_already_bound() -> None:
    import socket

    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        host, port = server.getsockname()
        assert not dev_web._free_port(host, port)


def test_port_check_accepts_an_available_loopback_port() -> None:
    with __import__("socket").socket() as server:
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
    assert dev_web._free_port("127.0.0.1", port)


def test_command_construction_does_not_use_shell() -> None:
    cmd = dev_web._command([sys.executable, "-m", "uvicorn", "src.main:app"])
    assert cmd == [sys.executable, "-m", "uvicorn", "src.main:app"]


def test_rehearsal_report_keeps_unrun_attempts_explicit() -> None:
    report = (SCRIPT.parents[1] / "docs" / "hosted-rehearsal.md").read_text(encoding="utf-8")
    assert report.count("| NOT RUN |") == 10
    assert "does not prove live hosted" in report
    assert "never include" in report
