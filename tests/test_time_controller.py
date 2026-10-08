"""Time controller tests: deadlines, cancellation, task leaks, states.

Pure Deadline/StateMachine logic runs on a FakeClock (no sleeping).
Enforcement paths use real clocks with short budgets. All provider I/O
is MockProvider — zero network.
"""

import asyncio
import logging
import time

import pytest

from src.agents.solver import SolverAgent
from src.orchestration.agent_manager import AgentManager
from src.orchestration.debate import DebateManager
from src.orchestration.time_controller import (
    DEFAULT_CALL_TIMEOUT_S,
    MIN_CALL_TIMEOUT_S,
    Deadline,
    ExecState,
    FakeClock,
    InvalidStateTransition,
    StateMachine,
    TaskTracker,
)
from src.providers.mock_provider import MockProvider

# ── FakeClock + Deadline (no sleeping) ─────────────────────────────────


def test_deadline_remaining_and_expiry() -> None:
    clock = FakeClock(start=100.0)
    deadline = Deadline(budget_seconds=60.0, clock=clock)
    assert deadline.remaining() == pytest.approx(60.0)
    assert deadline.elapsed() == pytest.approx(0.0)
    assert not deadline.expired
    clock.advance(10.0)
    assert deadline.remaining() == pytest.approx(50.0)
    assert deadline.elapsed() == pytest.approx(10.0)
    clock.advance(50.0)
    assert deadline.remaining() == pytest.approx(0.0)
    assert deadline.expired
    clock.advance(5.0)
    assert deadline.remaining() == pytest.approx(0.0)  # never negative


def test_synth_reserve_is_max_25s_or_12_percent() -> None:
    assert Deadline(180.0, clock=FakeClock()).synth_reserve == pytest.approx(25.0)
    assert Deadline(900.0, clock=FakeClock()).synth_reserve == pytest.approx(108.0)
    assert Deadline(60.0, clock=FakeClock()).synth_reserve == pytest.approx(25.0)


def test_can_start_round_needs_round_plus_reserve() -> None:
    clock = FakeClock()
    deadline = Deadline(180.0, clock=clock)  # reserve 25s
    assert deadline.can_start_round(30.0)
    clock.advance(180.0 - 25.0 - 30.0 + 0.5)
    assert not deadline.can_start_round(30.0)
    assert deadline.should_synthesize_now() is False
    clock.advance(100.0)
    assert deadline.should_synthesize_now()


def test_timeout_for_call_shrinks_with_remaining() -> None:
    clock = FakeClock()
    deadline = Deadline(600.0, clock=clock)
    assert deadline.timeout_for_call() == pytest.approx(DEFAULT_CALL_TIMEOUT_S)
    assert deadline.timeout_for_call(10.0) == pytest.approx(10.0)
    # Burn almost everything: timeout collapses toward the floor, not zero.
    clock.advance(600.0)
    assert deadline.timeout_for_call() == pytest.approx(MIN_CALL_TIMEOUT_S)
    assert deadline.timeout_for_call(30.0) == pytest.approx(MIN_CALL_TIMEOUT_S)


def test_synthesis_timeout_has_floor() -> None:
    clock = FakeClock()
    deadline = Deadline(600.0, clock=clock)
    assert deadline.synthesis_timeout() == pytest.approx(600.0)
    clock.advance(600.0)
    assert deadline.synthesis_timeout() == pytest.approx(5.0)


def test_cancel_flag_and_raise() -> None:
    deadline = Deadline(60.0, clock=FakeClock())
    assert not deadline.cancel_requested
    deadline.raise_if_cancelled()  # no-op when not flagged
    deadline.request_cancel()
    assert deadline.cancel_requested
    with pytest.raises(asyncio.CancelledError):
        deadline.raise_if_cancelled()


# ── State machine (docs/WORKFLOW.md section 2) ─────────────────────────


def test_happy_path_transitions() -> None:
    sm = StateMachine()
    assert sm.state == ExecState.CREATED
    path = [
        ExecState.CAPACITY_CHECK,
        ExecState.PLANNING,
        ExecState.TEAM_READY,
        ExecState.SOLVING,
        ExecState.EVALUATING,
        ExecState.SYNTHESIZING,
        ExecState.COMPLETED,
    ]
    for state in path:
        sm.transition(state)
    assert sm.state == ExecState.COMPLETED
    assert sm.terminal
    assert sm.history == [ExecState.CREATED, *path]


def test_debate_loop_transitions() -> None:
    sm = StateMachine()
    for state in (
        ExecState.CAPACITY_CHECK,
        ExecState.PLANNING,
        ExecState.TEAM_READY,
        ExecState.SOLVING,
        ExecState.EVALUATING,
    ):
        sm.transition(state)
    sm.transition(ExecState.DEBATING)
    sm.transition(ExecState.EVALUATING)
    sm.transition(ExecState.DEBATING)
    sm.transition(ExecState.EVALUATING)
    sm.transition(ExecState.SYNTHESIZING)
    assert not sm.terminal
    sm.transition(ExecState.COMPLETED)
    assert sm.terminal


def test_abnormal_exits_from_anywhere() -> None:
    for terminal in (ExecState.CANCELLED, ExecState.FAILED_PARTIAL):
        for start in (
            ExecState.CAPACITY_CHECK,
            ExecState.SOLVING,
            ExecState.EVALUATING,
            ExecState.DEBATING,
            ExecState.SYNTHESIZING,
        ):
            sm = StateMachine()
            # Walk legally to the start state.
            order = [
                ExecState.CAPACITY_CHECK,
                ExecState.PLANNING,
                ExecState.TEAM_READY,
                ExecState.SOLVING,
            ]
            for state in order:
                if state == start:
                    break
                sm.transition(state)
            if start in (ExecState.EVALUATING, ExecState.DEBATING):
                sm.transition(ExecState.EVALUATING)
                if start == ExecState.DEBATING:
                    sm.transition(ExecState.DEBATING)
            if start == ExecState.SYNTHESIZING:
                sm.transition(ExecState.EVALUATING)
                sm.transition(ExecState.SYNTHESIZING)
            sm.transition(terminal)
            assert sm.terminal


def test_illegal_transitions_raise() -> None:
    sm = StateMachine()
    with pytest.raises(InvalidStateTransition):
        sm.transition(ExecState.SOLVING)  # CREATED → SOLVING skips phases
    sm.transition(ExecState.CAPACITY_CHECK)
    with pytest.raises(InvalidStateTransition):
        sm.transition(ExecState.COMPLETED)  # nothing is done yet
    sm2 = StateMachine()
    for state in (
        ExecState.CAPACITY_CHECK,
        ExecState.PLANNING,
        ExecState.TEAM_READY,
        ExecState.SOLVING,
        ExecState.EVALUATING,
        ExecState.SYNTHESIZING,
        ExecState.COMPLETED,
    ):
        sm2.transition(state)
    with pytest.raises(InvalidStateTransition):
        sm2.transition(ExecState.CANCELLED)  # terminal states are final


# ── TaskTracker: no orphaned tasks ─────────────────────────────────────


async def test_tracker_completes_cleanly() -> None:
    async with TaskTracker(owner="test") as tracker:
        t1 = tracker.create(asyncio.sleep(0.01), name="assembly:test:a")
        t2 = tracker.create(asyncio.sleep(0.01), name="assembly:test:b")
        await asyncio.gather(t1, t2)
    assert len(tracker) == 0


async def test_tracker_cancels_stragglers_and_drains() -> None:
    tracker = TaskTracker(owner="test")
    ran = []

    async def straggler() -> None:
        try:
            await asyncio.sleep(30.0)
        except asyncio.CancelledError:
            ran.append("cancelled")
            raise

    t = tracker.create(straggler(), name="assembly:test:straggler")
    await asyncio.sleep(0)
    assert tracker.cancel_all() == 1
    await tracker.drain()
    assert t.cancelled()
    assert ran == ["cancelled"]
    assert len(tracker) == 0


async def test_tracker_context_exit_cleans_up() -> None:
    async with TaskTracker(owner="test") as tracker:
        tracker.create(asyncio.sleep(30.0), name="assembly:test:leak")
        tracker.create(asyncio.sleep(30.0), name="assembly:test:leak2")
        await asyncio.sleep(0)
        assert len(tracker) == 2
    assert len(tracker) == 0


async def test_no_task_leaks_after_bulk_cancel() -> None:
    before = {
        t for t in asyncio.all_tasks() if (t.get_name() or "").startswith("assembly:")
    }
    tracker = TaskTracker(owner="test")
    for i in range(5):
        tracker.create(asyncio.sleep(30.0), name=f"assembly:test:leak-{i}")
    await asyncio.sleep(0)
    tracker.cancel_all()
    await tracker.drain()
    after = {
        t for t in asyncio.all_tasks() if (t.get_name() or "").startswith("assembly:")
    }
    assert after <= before


# ── Quota counters stay correct under cancellation ─────────────────────


async def test_quota_lease_released_on_cancel(tmp_path) -> None:
    """A cancelled holder must free its semaphore slot and in-flight count."""
    from src.providers.quota import QuotaLimiter

    # Unknown provider → no limits configured → no DB touched at all.
    limiter = QuotaLimiter(max_in_flight=1)

    async def hold_lease() -> None:
        async with await limiter.acquire("lease-test-p", "k1"):
            await asyncio.sleep(30.0)

    first = asyncio.create_task(hold_lease(), name="assembly:test:holder")
    await asyncio.sleep(0.05)  # let it acquire the only slot
    assert limiter._in_flight.get("lease-test-p", 0) == 1

    second = asyncio.create_task(hold_lease(), name="assembly:test:waiter")
    await asyncio.sleep(0.05)  # waiter blocks on the semaphore
    assert not second.done()

    first.cancel()
    second.cancel()
    await asyncio.gather(first, second, return_exceptions=True)

    assert limiter._in_flight.get("lease-test-p", 0) == 0
    assert limiter._slot_for("lease-test-p")._value == 1
    # And the limiter is immediately reusable (no leaked permit).
    async with await limiter.acquire("lease-test-p", "k1"):
        pass
    assert limiter._in_flight.get("lease-test-p", 0) == 0


# ── Per-call timeouts in manager + debate ─────────────────────────────


def _slow_manager() -> tuple:
    from tests.conftest import MockRouter

    providers = [
        MockProvider(provider_name="mock-a", latency_seconds=5.0),
        MockProvider(provider_name="mock-b", latency_seconds=5.0),
    ]
    router = MockRouter(providers)
    manager = AgentManager(router, "exec-timeout")
    return manager, providers


async def test_independent_solve_timeout_produces_fallbacks() -> None:
    manager, _ = _slow_manager()
    agents = [
        SolverAgent(
            agent_id="agent_01", provider=manager.router._providers["mock-a"], model="m"
        ),
        SolverAgent(
            agent_id="agent_02", provider=manager.router._providers["mock-b"], model="m"
        ),
    ]
    started = time.monotonic()
    outputs = await manager.run_all_independent(agents, "Q?", timeout_s=0.1)
    elapsed = time.monotonic() - started
    assert elapsed < 2.0  # stragglers cut off, not awaited for 5s
    assert len(outputs) == 2
    assert all(o.confidence == 0.1 for o in outputs)
    assembly_tasks = [
        t for t in asyncio.all_tasks() if (t.get_name() or "").startswith("assembly:")
    ]
    assert assembly_tasks == []


async def test_independent_solve_without_timeout_unchanged() -> None:
    from tests.conftest import MockRouter

    router = MockRouter([MockProvider(provider_name="mock-a")])
    manager = AgentManager(router, "exec-no-timeout")
    agents = [
        SolverAgent(
            agent_id="agent_01", provider=router._providers["mock-a"], model="m"
        ),
    ]
    outputs = await manager.run_all_independent(agents, "What is the mock answer?")
    assert outputs[0].confidence == pytest.approx(0.9)
    assert "42" in outputs[0].position


async def test_debate_round_timeout_carries_forward() -> None:
    from tests.conftest import MockRouter

    router = MockRouter([MockProvider(provider_name="mock-a")])
    manager = AgentManager(router, "exec-prior")
    agents = [
        SolverAgent(
            agent_id="agent_01", provider=router._providers["mock-a"], model="m"
        ),
        SolverAgent(
            agent_id="agent_02", provider=router._providers["mock-a"], model="m"
        ),
    ]
    prior = await manager.run_all_independent(agents, "What is the mock answer?")
    assert len(prior) == 2
    # Slow critiques now: the round must time out per agent, not hang.
    for agent in agents:
        agent.provider = MockProvider(provider_name="slow", latency_seconds=5.0)
    debate = DebateManager("exec-debate-timeout")
    started = time.monotonic()
    updated = await debate.run_debate_round(
        agents, prior, "What is the mock answer?", 2, timeout_s=0.1
    )
    elapsed = time.monotonic() - started
    assert elapsed < 2.0
    assert len(updated) == 2
    assert all(o.failed_round == 2 for o in updated)  # stale carry-forward, Fix D
    assembly_tasks = [
        t for t in asyncio.all_tasks() if (t.get_name() or "").startswith("assembly:")
    ]
    assert assembly_tasks == []


# ── Orchestrator: hard cutoff, cancel, states ─────────────────────────


async def test_deadline_cutoff_skips_debate(orchestrator) -> None:
    from src.orchestration.time_controller import Deadline

    events: list[dict] = []

    async def on_progress(event: dict) -> None:
        events.append(event)

    started = time.monotonic()
    result = await orchestrator.execute(
        execution_id="test-exec-cutoff",
        question="What is the mock answer?",
        time_budget_minutes=3,
        on_progress=on_progress,
        deadline=Deadline(budget_seconds=0.2),
    )
    elapsed = time.monotonic() - started
    # Expired deadline → straight to synthesis with round-1 positions.
    # (debate_rounds counts evaluations; 1 = initial evaluate, no debate
    # rounds were launched — see the missing DEBATING state below.)
    assert result.status == "completed"
    assert result.debate_rounds == 1
    assert "FINAL MOCK ANSWER" in result.answer
    assert elapsed < 30.0
    states = [e["data"].get("state") for e in events if "state" in e["data"]]
    assert ExecState.SYNTHESIZING.value in states
    assert ExecState.DEBATING.value not in states


async def test_state_transitions_emitted_in_order(orchestrator) -> None:
    events: list[dict] = []

    async def on_progress(event: dict) -> None:
        events.append(event)

    result = await orchestrator.execute(
        execution_id="test-exec-states",
        question="What is the mock answer?",
        time_budget_minutes=3,
        on_progress=on_progress,
    )
    assert result.status == "completed"
    states = [e["data"]["state"] for e in events if "state" in e["data"]]
    assert states[0] == ExecState.CAPACITY_CHECK.value
    assert states[-1] == ExecState.COMPLETED.value
    for required in (
        ExecState.PLANNING.value,
        ExecState.TEAM_READY.value,
        ExecState.SOLVING.value,
        ExecState.EVALUATING.value,
        ExecState.SYNTHESIZING.value,
    ):
        assert required in states


async def test_orchestrator_cancel(orchestrator) -> None:
    # Slow down EVERYTHING: MockRouter always routes to the first provider,
    # so the latency must live on the providers it actually uses.
    for provider in orchestrator.router._providers.values():
        provider.latency_seconds = 30.0

    events: list[dict] = []

    async def on_progress(event: dict) -> None:
        events.append(event)

    task = asyncio.create_task(
        orchestrator.execute(
            execution_id="test-exec-cancel",
            question="What is the mock answer?",
            time_budget_minutes=3,
            on_progress=on_progress,
        ),
        name="assembly:test:execute",
    )
    await asyncio.sleep(0.3)  # let planning start (and hang in latency)
    assert orchestrator.request_cancel("test-exec-cancel") is True
    task.cancel()
    result = await task
    assert result.status == "cancelled"
    assert "test-exec-cancel" not in orchestrator._deadlines
    assert any(
        e["event_type"] == "status_update" and e["data"].get("status") == "cancelled"
        for e in events
    )
    leftovers = [
        t
        for t in asyncio.all_tasks()
        if (t.get_name() or "").startswith("assembly:test-exec-cancel")
    ]
    assert leftovers == []


async def test_request_cancel_unknown_is_false(orchestrator) -> None:
    assert orchestrator.request_cancel("no-such-execution") is False


async def test_provider_keys_never_leak(orchestrator, fake_key, caplog) -> None:
    """BYOK hygiene on the new paths: per-request keys appear in no logs,
    events, or results — even when routing falls back on the fake key."""
    events: list[dict] = []

    async def on_progress(event: dict) -> None:
        events.append(event)

    with caplog.at_level(logging.INFO, logger="assembly"):
        result = await orchestrator.execute(
            execution_id="test-exec-keys",
            question="What is the mock answer?",
            time_budget_minutes=3,
            on_progress=on_progress,
            provider_keys={"groq": fake_key},
        )

    assert result.status in ("completed", "failed", "cancelled")
    assert fake_key not in str(events)
    assert fake_key not in caplog.text
    assert fake_key not in (result.answer or "")


# ── API: POST /api/executions/{id}/cancel ─────────────────────────────


def _authed_client(monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import src.api.executions as exec_mod
    from src.database.base import Base, get_db
    from src.main import app

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(exec_mod, "SessionLocal", testing_session)
    client = TestClient(app)
    signup = client.post(
        "/api/auth/signup",
        json={
            "email": "cancel@test.local",
            "name": "Cancel",
            "password": "password123",
        },
    )
    assert signup.status_code == 200, signup.text
    client.headers.update({"Authorization": f"Bearer {signup.json()['access_token']}"})
    return client


def _slow_router():
    from tests.conftest import MockRouter

    return MockRouter([MockProvider(provider_name="mock-slow", latency_seconds=10.0)])


def _poll_status(client, execution_id: str, timeout_s: float = 15.0) -> str:
    deadline = time.monotonic() + timeout_s
    status = ""
    while time.monotonic() < deadline:
        gotten = client.get(f"/api/executions/{execution_id}")
        assert gotten.status_code == 200, gotten.text
        status = gotten.json()["status"]
        if status in ("completed", "failed", "failed_partial", "cancelled"):
            return status
        time.sleep(0.2)
    return status


def test_api_cancel_flow(monkeypatch) -> None:
    """Slow runs cannot survive a bare-TestClient request teardown (each
    request gets its own portal loop), so they must settle as CANCELLED —
    never stuck, never leaked. Cancelling the settled run is idempotent.
    """
    import src.api.executions as exec_mod

    client = _authed_client(monkeypatch)
    monkeypatch.setattr(exec_mod._orchestrator, "router", _slow_router())

    created = client.post(
        "/api/executions/",
        json={"question": "What is the mock answer?", "time_budget_minutes": 3},
    )
    assert created.status_code == 200, created.text
    execution_id = created.json()["id"]

    # The run was torn down with its request portal: settled, not stuck.
    assert _poll_status(client, execution_id) == "cancelled"
    assert execution_id not in exec_mod._run_tasks

    # Idempotent: cancelling a settled run reports its terminal status.
    again = client.post(f"/api/executions/{execution_id}/cancel")
    assert again.status_code == 200
    assert again.json() == {"id": execution_id, "status": "cancelled"}


async def test_api_cancel_live_task(monkeypatch) -> None:
    """Live-cancel path: a tracked in-flight task on a foreign loop is
    interrupted thread-safely and the endpoint reports "cancelling"."""
    import src.api.executions as exec_mod

    client = _authed_client(monkeypatch)
    monkeypatch.setattr(exec_mod._orchestrator, "router", _slow_router())

    created = client.post(
        "/api/executions/",
        json={"question": "What is the mock answer?", "time_budget_minutes": 3},
    )
    execution_id = created.json()["id"]

    # Simulate an in-flight run owned by another loop: inject a stand-in
    # task and mark the row non-terminal, as a live run would be.
    db = exec_mod.SessionLocal()
    try:
        from src.database.models import Execution as ExecutionModel

        row = db.query(ExecutionModel).filter(ExecutionModel.id == execution_id).first()
        row.status = "solving"
        db.commit()
    finally:
        db.close()

    task = asyncio.create_task(asyncio.sleep(30.0))
    exec_mod._run_tasks[execution_id] = task
    try:
        cancelled = client.post(f"/api/executions/{execution_id}/cancel")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json() == {"id": execution_id, "status": "cancelling"}
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        exec_mod._run_tasks.pop(execution_id, None)


def test_api_cancel_unknown_is_404(monkeypatch) -> None:
    client = _authed_client(monkeypatch)
    response = client.post("/api/executions/does-not-exist/cancel")
    assert response.status_code == 404


def test_api_cancel_forbidden_for_other_user(monkeypatch) -> None:
    import src.api.executions as exec_mod

    client = _authed_client(monkeypatch)
    monkeypatch.setattr(exec_mod._orchestrator, "router", _slow_router())

    created = client.post(
        "/api/executions/",
        json={"question": "What is the mock answer?", "time_budget_minutes": 3},
    )
    execution_id = created.json()["id"]

    other = client.post(
        "/api/auth/signup",
        json={"email": "other@test.local", "name": "Other", "password": "password123"},
    )
    assert other.status_code == 200
    client.headers.update({"Authorization": f"Bearer {other.json()['access_token']}"})
    forbidden = client.post(f"/api/executions/{execution_id}/cancel")
    assert forbidden.status_code == 403

    # Cleanup: cancel as the owner so no background task lingers.
    owner_token = client.post(
        "/api/auth/login",
        json={"email": "cancel@test.local", "password": "password123"},
    )
    assert owner_token.status_code == 200, owner_token.text
    client.headers.update(
        {"Authorization": f"Bearer {owner_token.json()['access_token']}"}
    )
    client.post(f"/api/executions/{execution_id}/cancel")
    assert _poll_status(client, execution_id) == "cancelled"
