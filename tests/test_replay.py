"""Record & replay tests: full determinism offline, zero network.

Covers the recording file format, FIFO replay order + exhaustion,
simulated delays, error record/replay, provider identity delegation,
family preservation, full record→replay answer equality, and the
mandatory key-leak scan.
"""

import json
import logging
import time

import pytest

from src.orchestration.orchestrator import Orchestrator
from src.providers.base import ChatMessage, ProviderResponse
from src.providers.errors import ProviderDown, RateLimited
from src.providers.mock_provider import MockProvider
from src.providers.replay_provider import (
    RECORDING_VERSION,
    RecordingProvider,
    RecordingRouter,
    ReplayExhaustedError,
    ReplayProvider,
    classify_record_error,
    load_recording,
    raise_recorded_error,
    replay_router_for,
    response_from_record,
    response_to_record,
    save_recording,
)
from tests.conftest import MockRouter


def _messages(text: str = "hello") -> list[ChatMessage]:
    return [ChatMessage(role="user", content=text)]


def _record(
    provider: str = "groq",
    model: str = "openai/gpt-oss-20b",
    content: str = '{"position": "42"}',
    latency_ms: float = 0.0,
) -> dict:
    return {
        "provider": provider,
        "model": model,
        "temperature": 0.2,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": "hi"}],
        "response": {
            "content": content,
            "model": model,
            "provider": provider,
            "input_tokens": 10,
            "output_tokens": 20,
            "total_tokens": 30,
            "finish_reason": "stop",
        },
        "error": None,
        "latency_ms": latency_ms,
    }


# ── Recording format ────────────────────────────────────────────────


def test_save_and_load_round_trip(tmp_path) -> None:
    path = tmp_path / "run.json"
    records = [_record(), _record(provider="cerebras", content='{"position": "43"}')]
    saved = save_recording(path, records, question="Q?", time_budget_minutes=3)
    assert saved == path
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == RECORDING_VERSION
    assert data["question"] == "Q?"
    assert data["time_budget_minutes"] == 3
    assert len(data["records"]) == 2
    loaded = load_recording(path)
    assert loaded["records"] == records


def test_load_rejects_bad_files(tmp_path) -> None:
    missing = tmp_path / "nope.json"
    with pytest.raises(ValueError, match="cannot load"):
        load_recording(missing)
    bad_version = tmp_path / "badver.json"
    bad_version.write_text(json.dumps({"version": 999, "records": []}))
    with pytest.raises(ValueError, match="unsupported"):
        load_recording(bad_version)
    bad_shape = tmp_path / "badshape.json"
    bad_shape.write_text(json.dumps({"version": RECORDING_VERSION}))
    with pytest.raises(TypeError, match="'records' must be a list"):
        load_recording(bad_shape)
    bad_record = tmp_path / "badrec.json"
    bad_record.write_text(json.dumps({"version": RECORDING_VERSION, "records": [{}]}))
    with pytest.raises(TypeError, match="record 0 invalid"):
        load_recording(bad_record)
    empty_response = tmp_path / "empty.json"
    empty_response.write_text(
        json.dumps(
            {
                "version": RECORDING_VERSION,
                "records": [{"messages": [], "response": None, "error": None}],
            }
        )
    )
    with pytest.raises(ValueError, match="no response or error"):
        load_recording(empty_response)


def test_response_serialization_round_trip() -> None:
    original = ProviderResponse(
        content="hi",
        model="m",
        provider="p",
        input_tokens=1,
        output_tokens=2,
        total_tokens=3,
    )
    restored = response_from_record({"response": response_to_record(original)})
    assert restored == original


# ── RecordingProvider ───────────────────────────────────────────────


async def test_recording_provider_captures_success() -> None:
    inner = MockProvider(provider_name="mock-a")
    records: list = []
    provider = RecordingProvider(inner, records, family="mock")
    response = await provider.generate(_messages(), model="mock-model")
    assert "42" in response.content
    assert len(records) == 1
    record = records[0]
    assert record["provider"] == "mock-a"
    assert record["model"] == "mock-model"
    assert record["messages"] == [{"role": "user", "content": "hello"}]
    assert record["response"]["total_tokens"] == 30
    assert record["error"] is None
    assert record["latency_ms"] >= 0.0
    # Identity delegation: attribution behaves like the inner provider.
    assert provider.provider_name == "mock-a"
    assert provider.get_available_models() == ["mock-model"]
    assert provider.is_available() is True
    assert provider.family == "mock"


async def test_recording_provider_captures_error_and_reraises() -> None:
    inner = MockProvider(scripts={"solver": "x"}, always_fail={"solver": "timeout"})
    records: list = []
    provider = RecordingProvider(inner, records)

    class _Agent:  # minimal stand-in routing solver text at the mock
        pass

    with pytest.raises(TimeoutError):
        await provider.generate(
            [ChatMessage(role="system", content="independently analyze and solve")]
        )
    assert len(records) == 1
    assert records[0]["response"] is None
    assert records[0]["error"]["type"] == "timeout"


def test_classify_and_raise_recorded_errors() -> None:
    assert classify_record_error(RateLimited("p", "slow")) == "rate_limit"
    assert classify_record_error(TimeoutError("t")) == "timeout"
    assert classify_record_error(ValueError("?")) == "error"
    with pytest.raises(TimeoutError):
        raise_recorded_error("p", {"type": "timeout", "message": "t"})
    with pytest.raises(RateLimited):
        raise_recorded_error("p", {"type": "rate_limit", "message": "slow"})
    with pytest.raises(ProviderDown):
        raise_recorded_error("p", {"type": "provider_down", "message": "down"})


# ── ReplayProvider: order, exhaustion, delays ───────────────────────


async def test_replay_returns_records_in_order() -> None:
    import collections

    queue = collections.deque([_record(content="first"), _record(content="second")])
    provider = ReplayProvider(queue, provider_name="groq", delay_scale=0.0)
    first = await provider.generate(_messages())
    second = await provider.generate(_messages())
    assert "first" in first.content
    assert "second" in second.content
    assert first.model == "openai/gpt-oss-20b"
    assert provider.remaining == 0
    assert len(provider.calls) == 2


async def test_replay_exhaustion_fails_loudly() -> None:
    import collections

    provider = ReplayProvider(collections.deque([]), delay_scale=0.0)
    with pytest.raises(ReplayExhaustedError, match="ran out of recorded responses"):
        await provider.generate(_messages())


async def test_replay_replays_recorded_error() -> None:
    import collections

    record = _record()
    record["response"] = None
    record["error"] = {"type": "timeout", "message": "boom"}
    provider = ReplayProvider(collections.deque([record]), delay_scale=0.0)
    with pytest.raises(TimeoutError, match="boom"):
        await provider.generate(_messages())


async def test_replay_simulated_delays() -> None:
    import collections

    record = _record(latency_ms=300.0)
    instant = ReplayProvider(collections.deque([record]), delay_scale=0.0)
    started = time.monotonic()
    await instant.generate(_messages())
    assert time.monotonic() - started < 0.25

    paced = ReplayProvider(collections.deque([_record(latency_ms=300.0)]))
    started = time.monotonic()
    await paced.generate(_messages())
    assert time.monotonic() - started >= 0.25


# ── Full record → replay determinism ────────────────────────────────


async def _recorded_run(tmp_path, question="What is the mock answer?"):
    """Run a mock execution under RecordingRouter; return (result, path)."""
    orch = Orchestrator()
    mock_router = MockRouter(
        [
            MockProvider(provider_name="mock-a"),
            MockProvider(provider_name="mock-b"),
            MockProvider(provider_name="mock-c"),
        ]
    )
    recorder = RecordingRouter(mock_router)
    orch.router = recorder
    result = await orch.execute(
        execution_id="test-record-run",
        question=question,
        time_budget_minutes=3,
    )
    path = tmp_path / "run.json"
    recorder.save(path, question=question, time_budget_minutes=3)
    return result, path, recorder


async def test_record_then_replay_reproduces_answer(tmp_path) -> None:
    recorded, path, recorder = await _recorded_run(tmp_path)
    assert recorded.status == "completed"
    assert recorder.records, "expected model calls to be recorded"

    data = load_recording(path)
    replay_router = replay_router_for(data["records"], delay_scale=0.0)

    orch = Orchestrator()
    orch.router = replay_router
    replayed = await orch.execute(
        execution_id="test-replay-run",
        question="What is the mock answer?",
        time_budget_minutes=3,
    )
    assert replayed.status == "completed"
    assert replayed.answer == recorded.answer
    assert replayed.consensus_score == recorded.consensus_score
    assert replay_router.remaining == 0


async def test_replay_router_families_and_providers(tmp_path) -> None:
    _, path, _ = await _recorded_run(tmp_path)
    data = load_recording(path)
    router = replay_router_for(data["records"], delay_scale=0.0)
    assert set(router.get_available_providers()) <= {"mock-a", "mock-b", "mock-c"}
    assert router.get_live_count() >= 1
    # Families come from the recording, so diversity accounting replays too.
    routing = router.route_team([{"agent_type": "solver"}, {"agent_type": "critic"}])
    assert [d.provider_name for d in routing.decisions] == ["mock-a", "mock-a"]
    assert {d.family for d in routing.decisions} == {"mock"}


# ── CLI scripts ─────────────────────────────────────────────────────


def test_cli_help_exits_zero() -> None:
    """Both CLIs wire argparse correctly (no keys needed for --help)."""
    import subprocess
    import sys

    for script in ("scripts/record_run.py", "scripts/replay_run.py"):
        completed = subprocess.run(
            [sys.executable, script, "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert "Usage" in completed.stdout or "usage" in completed.stdout


async def test_record_script_writes_recording(monkeypatch, tmp_path) -> None:
    """record_run() with a mock-backed orchestrator writes a valid file."""
    import scripts.record_run as record_mod
    from src.orchestration.orchestrator import Orchestrator
    from tests.conftest import MockRouter

    orch = Orchestrator()
    orch.router = MockRouter(
        [
            MockProvider(provider_name="mock-a"),
            MockProvider(provider_name="mock-b"),
            MockProvider(provider_name="mock-c"),
        ]
    )
    monkeypatch.setattr(record_mod, "Orchestrator", lambda: orch)
    out = tmp_path / "cli-run.json"
    code = await record_mod.record_run("What is the mock answer?", 3, out)
    assert code == 0
    data = load_recording(out)
    assert len(data["records"]) > 0
    assert data["question"] == "What is the mock answer?"
    assert data["time_budget_minutes"] == 3


async def test_replay_script_replays_recording(tmp_path, capsys) -> None:
    """replay_run() plays a file back end to end, offline."""
    import scripts.replay_run as replay_mod

    _, path, _ = await _recorded_run(tmp_path)
    code = await replay_mod.replay_run(path, 0.0, None, None)
    assert code == 0
    printed = capsys.readouterr().out
    assert "FINAL MOCK ANSWER" in printed
    assert "Status: completed" in printed


# ── Key-leak scan (AGENTS.md section 5) ─────────────────────────────


async def test_recording_carries_no_keys(
    mock_router, fake_key: str, monkeypatch, caplog
) -> None:
    """Recording a run must capture no key material — not in the file,
    not in logs. The fake key sits in env (like test_key_leak.py) while
    the mock run executes under the recorder."""

    monkeypatch.setenv("GEMINI_API_KEY", fake_key)
    recorder = RecordingRouter(mock_router)
    orch = Orchestrator()
    orch.router = recorder
    with caplog.at_level(logging.INFO, logger="assembly"):
        result = await orch.execute(
            execution_id="test-record-leak",
            question="What is the mock answer?",
            time_budget_minutes=3,
        )
    assert result.status == "completed"
    blob = json.dumps(recorder.records)
    assert fake_key not in blob
    # Structural guarantee: records hold exactly the documented schema —
    # there is no field where key material could hide.
    allowed_record_keys = {
        "provider",
        "model",
        "family",
        "temperature",
        "max_tokens",
        "messages",
        "response",
        "error",
        "latency_ms",
    }
    allowed_response_keys = {
        "content",
        "model",
        "provider",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "reasoning_tokens",
        "finish_reason",
    }
    for record in recorder.records:
        assert set(record) <= allowed_record_keys, set(record)
        assert set(record["response"] or {}) <= allowed_response_keys
        for message in record["messages"]:
            assert set(message) == {"role", "content"}
    assert fake_key not in caplog.text
