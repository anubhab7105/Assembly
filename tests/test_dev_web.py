"""Unit tests for the managed one-command local web launcher."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Self

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dev_web.py"
SPEC = importlib.util.spec_from_file_location("assembly_dev_web", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
dev_web = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dev_web)


class FakeProcess:
    """Minimal Popen stand-in that records every lifecycle call in order."""

    def __init__(
        self,
        name: str,
        *,
        events: list[str] | None = None,
        returncode: int | None = None,
        timeout_waits: int = 0,
    ) -> None:
        self.name = name
        self.events = events if events is not None else []
        self.returncode = returncode
        self.timeout_waits = timeout_waits

    def _record(self, action: str, timeout: float | None = None) -> None:
        if action == "wait":
            self.events.append(f"{self.name}.wait(timeout={timeout})")
        else:
            self.events.append(f"{self.name}.{action}")

    def poll(self) -> int | None:
        self._record("poll")
        return self.returncode

    def terminate(self) -> None:
        self._record("terminate")

    def wait(self, timeout: float | None = None) -> int:
        self._record("wait", timeout)
        if self.timeout_waits:
            self.timeout_waits -= 1
            raise subprocess.TimeoutExpired(self.name, timeout)
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def kill(self) -> None:
        self._record("kill")
        self.returncode = -9


class FakeClock:
    """Deterministic monotonic clock whose sleep only advances time."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeHTTPResponse:
    def __init__(self, status: int = 200) -> None:
        self.status = status

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


def _patch_popen(
    monkeypatch: pytest.MonkeyPatch,
    fake_popen: Callable[..., FakeProcess],
) -> None:
    """Replace only the launcher's subprocess surface, keeping TimeoutExpired."""
    monkeypatch.setattr(
        dev_web,
        "subprocess",
        SimpleNamespace(
            Popen=fake_popen,
            TimeoutExpired=subprocess.TimeoutExpired,
        ),
    )


def _patch_main(
    monkeypatch: pytest.MonkeyPatch,
    *,
    popen: Callable[..., FakeProcess],
    args: tuple[str, ...] = (),
) -> None:
    monkeypatch.setattr(sys, "argv", ["dev_web.py", "--no-browser", *args])
    monkeypatch.setattr(dev_web, "_free_port", lambda host, port: True)
    _patch_popen(monkeypatch, popen)


def _popen_sequence(*processes: FakeProcess) -> Callable[..., FakeProcess]:
    remaining = iter(processes)

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        return next(remaining)

    return fake_popen


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


def test_frontend_environment_does_not_receive_provider_keys() -> None:
    backend_env, frontend_env = dev_web._prepare_child_env(
        {
            "GROQ_API_KEY": "sensitive-canary",
            "TAVILY_API_KEY": "search-canary",
            "UNRELATED_SETTING": "preserved",
            "CORS_ALLOW_LIST": "https://example.test",
        },
        backend_host="127.0.0.1",
        backend_port=8001,
        frontend_host="127.0.0.1",
        frontend_port=3001,
    )

    assert backend_env["APP_MODE"] == "dev"
    assert backend_env["PORT"] == "8001"
    assert "http://127.0.0.1:3001" in backend_env["CORS_ALLOW_LIST"]
    assert backend_env["GROQ_API_KEY"] == "sensitive-canary"
    assert "GROQ_API_KEY" not in frontend_env
    assert "TAVILY_API_KEY" not in frontend_env
    assert frontend_env["NEXT_PUBLIC_API_URL"] == "http://127.0.0.1:8001"
    assert frontend_env["NEXT_PUBLIC_APP_MODE"] == "web"
    assert frontend_env["UNRELATED_SETTING"] == "preserved"


def test_rehearsal_report_keeps_unrun_attempts_explicit() -> None:
    report = (SCRIPT.parents[1] / "docs" / "hosted-rehearsal.md").read_text(
        encoding="utf-8"
    )
    assert report.count("| NOT RUN |") == 10
    assert "**not** evidence of a hosted live run" in report
    assert "Never paste credentials" in report


def test_backend_is_terminated_when_frontend_cannot_be_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    backend = FakeProcess("backend", events=events)
    commands: list[list[str]] = []

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        commands.append(command)
        if len(commands) == 1:
            return backend
        raise OSError("npm is unavailable")

    _patch_main(monkeypatch, popen=fake_popen)

    assert dev_web.main() == 1
    assert len(commands) == 2
    assert backend.events == [
        "backend.poll",
        "backend.terminate",
        "backend.wait(timeout=8)",
    ]


def test_both_children_are_terminated_when_readiness_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    backend = FakeProcess("backend", events=events)
    frontend = FakeProcess("frontend", events=events)
    clock = FakeClock()
    _patch_main(
        monkeypatch,
        popen=_popen_sequence(backend, frontend),
        args=("--ready-timeout", "5"),
    )
    monkeypatch.setattr(dev_web, "time", clock)

    def fake_urlopen(*args: object, **kwargs: object) -> FakeHTTPResponse:
        raise OSError("connection refused")

    monkeypatch.setattr(dev_web.urllib.request, "urlopen", fake_urlopen)

    assert dev_web.main() == 1
    assert clock.now >= 5
    assert [event for event in events if not event.endswith(".poll")] == [
        "frontend.terminate",
        "frontend.wait(timeout=8)",
        "backend.terminate",
        "backend.wait(timeout=8)",
    ]


def test_running_child_is_terminated_when_the_other_exits_before_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    backend = FakeProcess("backend", events=events, returncode=2)
    frontend = FakeProcess("frontend", events=events)
    _patch_main(monkeypatch, popen=_popen_sequence(backend, frontend))

    assert dev_web.main() == 1
    assert "backend.terminate" not in events
    assert "backend.kill" not in events
    assert [event for event in events if event.startswith("frontend.")] == [
        "frontend.poll",
        "frontend.terminate",
        "frontend.wait(timeout=8)",
    ]


def test_backend_is_terminated_when_frontend_exits_after_backend_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    backend = FakeProcess("backend", events=events)
    frontend = FakeProcess("frontend", events=events, returncode=3)
    ready_checks: list[str] = []
    _patch_main(monkeypatch, popen=_popen_sequence(backend, frontend))

    def fake_urlopen(url: str, *args: object, **kwargs: object) -> FakeHTTPResponse:
        ready_checks.append(url)
        return FakeHTTPResponse()

    monkeypatch.setattr(dev_web.urllib.request, "urlopen", fake_urlopen)

    assert dev_web.main() == 1
    assert len(ready_checks) == 1
    assert ready_checks[0].endswith("/health")
    assert "frontend.terminate" not in events
    assert [event for event in events if not event.endswith(".poll")] == [
        "backend.terminate",
        "backend.wait(timeout=8)",
    ]


def test_stubborn_child_is_killed_during_failed_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    backend = FakeProcess("backend", events=events, timeout_waits=1)
    commands: list[list[str]] = []

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        commands.append(command)
        if len(commands) == 1:
            return backend
        raise OSError("npm is unavailable")

    _patch_main(monkeypatch, popen=fake_popen)

    assert dev_web.main() == 1
    assert backend.events == [
        "backend.poll",
        "backend.terminate",
        "backend.wait(timeout=8)",
        "backend.kill",
        "backend.wait(timeout=4)",
    ]


def test_terminate_falls_back_to_kill_when_wait_times_out() -> None:
    process = FakeProcess("backend", timeout_waits=1)

    dev_web._terminate(process, "backend")

    assert process.events == [
        "backend.poll",
        "backend.terminate",
        "backend.wait(timeout=8)",
        "backend.kill",
        "backend.wait(timeout=4)",
    ]


def test_terminate_does_not_kill_when_child_exits_in_time() -> None:
    process = FakeProcess("frontend")

    dev_web._terminate(process, "frontend")

    assert process.events == [
        "frontend.poll",
        "frontend.terminate",
        "frontend.wait(timeout=8)",
    ]
    assert "frontend.kill" not in process.events


def test_terminate_ignores_missing_and_already_exited_children() -> None:
    dev_web._terminate(None, "frontend")
    process = FakeProcess("backend", returncode=0)

    dev_web._terminate(process, "backend")

    assert process.events == ["backend.poll"]
