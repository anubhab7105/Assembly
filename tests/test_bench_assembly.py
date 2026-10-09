"""Offline tests for bench/run_assembly.py --pin-team helpers (no network)."""

from types import SimpleNamespace

import pytest

from bench.run_assembly import (
    PIN_MAX_WAIT_CAP_SECONDS,
    _answered_families,
    _check_pin_wait,
    _cooling_providers,
    _has_quota_signal,
    _pin_wait_line,
    _quota_wait_seconds,
    _routed_families,
    parse_args,
)


def test_parse_args_pin_team_defaults() -> None:
    args = parse_args([])
    assert args.pin_team is False
    assert args.pin_families is None


def test_parse_args_pin_team_flags() -> None:
    args = parse_args(["--pin-team", "--pin-families", "gemini,qwen", "--tier", "5"])
    assert args.pin_team is True
    assert args.pin_families == "gemini,qwen"


def test_answered_families_prefers_successful_calls() -> None:
    result = SimpleNamespace(
        call_log=[
            {"family": "gemini", "total_tokens": 100},
            {"family": "nemotron", "total_tokens": 200},
            {"family": "gpt-oss", "total_tokens": 0},
            {"family": "unknown", "total_tokens": 50},
            {"family": "", "total_tokens": 10},
        ],
        routing=[{"family": "gemini"}, {"family": "gpt-oss"}],
    )
    assert _answered_families(result) == ["gemini", "nemotron"]
    assert _routed_families(result) == ["gemini", "gpt-oss"]


def test_answered_families_falls_back_to_routing() -> None:
    result = SimpleNamespace(call_log=[], routing=[{"family": "qwen"}])
    assert _answered_families(result) == ["qwen"]


def test_has_quota_signal() -> None:
    assert _has_quota_signal([{"type": "RateLimited", "message": "x"}]) is True
    assert _has_quota_signal([{"type": "Warning", "message": "quota spent"}]) is True
    assert _has_quota_signal([{"type": "Warning", "message": "all good"}]) is False
    assert _has_quota_signal([]) is False


def test_quota_wait_seconds() -> None:
    router = SimpleNamespace(
        quota_snapshot=lambda: [
            {"provider": "a", "cooldown_seconds": 12.0},
            {"provider": "b", "cooldown_seconds": 0.0},
        ]
    )
    assert _quota_wait_seconds(router) == 12.0
    assert _quota_wait_seconds(SimpleNamespace()) == 0.0


def test_pin_wait_cap_accepts_up_to_24h() -> None:
    assert _check_pin_wait(1.0) == 1.0
    assert _check_pin_wait(86400.0) == 86400.0
    assert PIN_MAX_WAIT_CAP_SECONDS == 86400.0
    with pytest.raises(SystemExit):
        _check_pin_wait(0.0)
    with pytest.raises(SystemExit):
        _check_pin_wait(-5.0)
    with pytest.raises(SystemExit):
        _check_pin_wait(86400.0 + 1)


def test_cooling_providers_names_who_is_cooling() -> None:
    router = SimpleNamespace(
        quota_snapshot=lambda: [
            {"provider": "groq", "cooldown_seconds": 90.0},
            {"provider": "gemini", "cooldown_seconds": 0.0},
        ]
    )
    assert _cooling_providers(router) == ["groq"]
    assert _cooling_providers(SimpleNamespace()) == []


def test_pin_wait_line_names_provider_and_time() -> None:
    line = _pin_wait_line(["groq"], 90.0)
    assert line.startswith("waiting for groq quota until ")
    multi = _pin_wait_line(["groq", "openrouter"], 60.0)
    assert multi.startswith("waiting for groq, openrouter quota until ")
    assert "T" in line  # ISO-8601 timestamp trails the provider names
