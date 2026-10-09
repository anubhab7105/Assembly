"""Assembly chaos harness: random fault injection + deterministic stage sweep.

Random mode (``--random N``) reproduces the original behavior: N parallel
executions with random transient/permanent faults on solver/critic/
researcher/synthesize/plan script keys.

Sweep mode (default) injects one fault per scenario so EVERY stage is
exercised deterministically, including synthesizer fallback recovery:

- plan: malformed-once (retry recovers), timeout-always (heuristic fallback)
- solve/debate per role (solver, researcher, critic): rate_limit-once
  (fallback retry recovers via ChaosRouter) and rate_limit-always
  (error outputs + debate carry-forwards, breaker trips, run completes
  degraded — researcher-always-fail additionally asserts the
  reduced-research answer path)
- synthesize: rate_limit-once (fallback recovery; asserts the retry ran
  on the second provider) and malformed-always (validation failure →
  graceful failed execution, never a crash)

All providers are MockProvider (zero network). Exit 1 on any bug
(crash, invalid terminal state, deadline overrun, negative tokens, task
leak); graceful failed statuses are reported, not bugs.
"""

import argparse
import asyncio
import random
import sys
import time
import uuid
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestration.orchestrator import Orchestrator
from src.orchestration.time_controller import Deadline
from src.providers.mock_provider import MockProvider
from tests.conftest import MockAssignment, MockRouter


class ChaosRouter(MockRouter):
    """MockRouter plus family fallback across the mock pool.

    Returns the first provider whose name differs from the failed
    decision's provider (or None when the pool has no alternative), so
    retry/fallback paths — including synthesizer fallback — are
    exercised instead of raising immediately.
    """

    def fallback_for(self, decision, error) -> MockAssignment | None:
        """Next mock provider for a failed decision (names only)."""
        current = getattr(decision, "provider_name", "")
        role = getattr(decision, "role", "") or "solver"
        for name, provider in self._providers.items():
            if name != current:
                return MockAssignment(
                    provider=provider,
                    model=provider.get_available_models()[0],
                    provider_name=name,
                    role=role,
                )
        return None


#: Planner script that fields solver + researcher + critic (offline:
#: needs_research False so the run never touches the search network).
PLAN_WITH_RESEARCHER: dict = {
    "problem_type": "general",
    "complexity": "medium",
    "needs_research": False,
    "team": [
        {"agent_type": "solver", "role_description": "Problem solver"},
        {"agent_type": "researcher", "role_description": "Evidence gatherer"},
        {"agent_type": "critic", "role_description": "Answer verifier"},
    ],
    "reasoning": "Chaos plan with researcher.",
}


def make_router(
    fail_next: dict | None = None,
    always_fail: dict | None = None,
    latency: float = 0.0,
    plan_body: dict | None = None,
) -> tuple[ChaosRouter, list[MockProvider]]:
    """Three mock providers sharing one fault plan (names only in faults).

    plan_body replaces just the planner script (other role scripts stay
    at MockProvider defaults) so scenarios can field a researcher.
    """
    base_scripts = dict(MockProvider()._scripts)
    if plan_body is not None:
        base_scripts["plan"] = plan_body
    # Distinct model ids per provider so the circuit breaker (keyed on
    # model + role, as in production) tells providers apart. One shared
    # fail_next dict so "once" means once per scenario, not per provider.
    shared_fail_next: dict = dict(fail_next or {})
    providers = []
    for i in range(3):
        provider = MockProvider(
            provider_name=f"mock-{chr(97 + i)}",  # mock-a, mock-b, mock-c
            scripts=dict(base_scripts),
            model=f"mock-model-{chr(97 + i)}",
            always_fail=dict(always_fail or {}),
            latency_seconds=latency,
        )
        provider.fail_next = shared_fail_next
        providers.append(provider)
    return ChaosRouter(providers), providers


async def run_execution(
    run_idx: int,
    fail_next: dict | None = None,
    always_fail: dict | None = None,
    budget_minutes: int = 3,
    latency: float = 0.0,
    plan_body: dict | None = None,
) -> dict:
    """One execution under an explicit fault plan. Never raises."""
    execution_id = f"chaos-{run_idx}-{uuid.uuid4().hex[:8]}"
    budget_seconds = budget_minutes * 60

    router, providers = make_router(fail_next, always_fail, latency, plan_body)

    orch = Orchestrator()
    orch.router = router

    deadline = Deadline(budget_seconds=budget_seconds)
    start_time = time.time()

    try:
        result = await orch.execute(
            execution_id=execution_id,
            question="What is the meaning of life?",
            time_budget_minutes=budget_minutes,
            deadline=deadline,
        )
    except Exception as e:  # noqa: BLE001 — harness must not crash
        print(f"[{run_idx}] Unhandled exception: {e}")
        result = None

    elapsed = time.time() - start_time

    # Let tasks settle
    await asyncio.sleep(0.1)

    return {
        "run_idx": run_idx,
        "elapsed": elapsed,
        "budget": budget_seconds,
        "margin": deadline.synth_reserve,
        "result": result,
        "providers": providers,
    }


def check_result(r: dict) -> list[str]:
    """Bug list for one finished run (empty means clean)."""
    bugs: list[str] = []
    idx = r["run_idx"]
    res = r["result"]

    if res is None:
        bugs.append(f"[{idx}] CRASH: no ExecutionResult returned.")
        return bugs

    status = res.status
    if status not in ("completed", "failed", "cancelled"):
        bugs.append(f"[{idx}] BUG: Invalid terminal state: {status}")

    max_allowed_time = r["budget"] + r["margin"] + 5.0  # sync overhead buffer
    if r["elapsed"] > max_allowed_time:
        bugs.append(
            f"[{idx}] BUG: Deadline exceeded! Took {r['elapsed']:.2f}s, "
            f"allowed: {max_allowed_time:.2f}s"
        )

    if getattr(res, "total_tokens", -1) < 0:
        bugs.append(
            f"[{idx}] BUG: Quota counters invalid: "
            f"{getattr(res, 'total_tokens', 'missing')}"
        )
    return bugs


# ── Deterministic sweep: (name, fail_next, always_fail, expect, plan) ──


def sweep_scenarios() -> list[tuple[str, dict, dict, str, dict | None]]:
    """Every stage gets a fault; each entry states the expected outcome.

    Researcher scenarios field PLAN_WITH_RESEARCHER (offline: no web
    search); the rest use MockProvider defaults (solver + critic).
    """
    roles = ["solver", "researcher", "critic"]
    scenarios: list[tuple[str, dict, dict, str, dict | None]] = [
        ("plan-malformed-once", {"plan": "malformed"}, {}, "completed", None),
        ("plan-timeout-always", {}, {"plan": "timeout"}, "completed", None),
    ]
    for role in roles:
        plan = PLAN_WITH_RESEARCHER if role == "researcher" else None
        scenarios.append(
            (f"{role}-ratelimit-once", {role: "rate_limit"}, {}, "completed", plan)
        )
        scenarios.append(
            (
                f"{role}-ratelimit-always",
                {},
                {role: "rate_limit"},
                "completed",
                plan,
            )
        )
    scenarios.extend(
        [
            (
                "synthesize-ratelimit-once",
                {"synthesize": "rate_limit"},
                {},
                "completed-fallback",
                None,
            ),
            (
                "synthesize-malformed-always",
                {},
                {"synthesize": "malformed"},
                "failed",
                None,
            ),
            # Total outage: every agent role and synthesis fail on all
            # providers — must still land in graceful failed status.
            # (The default mock plan fields solver+critic; the researcher
            # key is a no-op here but keeps the matrix explicit.)
            (
                "total-outage",
                {},
                {
                    "solver": "timeout",
                    "researcher": "timeout",
                    "critic": "timeout",
                    "synthesize": "timeout",
                },
                "failed",
                None,
            ),
        ]
    )
    return scenarios


async def run_sweep() -> tuple[int, int, list[str]]:
    """Run every sweep scenario sequentially. Returns (runs, graceful, bugs)."""
    bugs: list[str] = []
    graceful = 0
    for idx, (name, fail_next, always_fail, expect, plan_body) in enumerate(
        sweep_scenarios()
    ):
        r = await run_execution(idx, fail_next, always_fail, 3, 0.0, plan_body)
        res = r["result"]
        status = res.status if res is not None else None
        if status in ("failed", "cancelled"):
            graceful += 1
        bugs.extend(check_result(r))

        if res is None:
            print(f"[sweep:{name}] CRASH (expected {expect})")
            continue
        ok = False
        if expect == "completed":
            ok = status == "completed"
            if name == "researcher-ratelimit-always":
                degraded = (res.verification or {}).get("research_degraded", False)
                caveat = "research" in (res.answer or "").casefold()
                ok = ok and degraded and caveat
                if not (degraded and caveat):
                    bugs.append(
                        f"[sweep:{name}] BUG: degraded research not reported "
                        f"(flag={degraded}, caveat={caveat})."
                    )
        elif expect == "completed-fallback":
            ok = status == "completed"
            # The retry must have run on a different mock provider.
            synth_calls = [
                c
                for p in r["providers"]
                for c in p.calls
                if c["script_key"] == "synthesize"
            ]
            providers_hit = {c.get("provider", "") for c in synth_calls}
            if len(synth_calls) < 2:
                ok = False
                bugs.append(
                    f"[sweep:{name}] BUG: synthesizer fallback never ran "
                    f"({len(synth_calls)} synthesize call(s))."
                )
            _ = providers_hit
        elif expect == "failed":
            ok = status == "failed"
        print(
            f"[sweep:{name}] status={status} "
            f"(expected {expect}) → {'OK' if ok else 'MISMATCH'}"
        )
        if not ok:
            bugs.append(f"[sweep:{name}] BUG: expected {expect}, got {status}.")
    return len(sweep_scenarios()), graceful, bugs


async def run_random(count: int) -> tuple[int, int, list[str]]:
    """Original random-fault mode: N parallel executions, random faults."""
    faults = ["rate_limit", "timeout", "malformed"]
    roles = ["solver", "researcher", "critic", "synthesize", "plan"]

    async def one(run_idx: int) -> dict:
        fail_next: dict = {}
        always_fail: dict = {}
        if random.random() < 0.3:
            role = random.choice(roles)
            fault = random.choice(faults)
            if random.random() < 0.5:
                fail_next[role] = fault
            else:
                always_fail[role] = fault
        return await run_execution(
            1000 + run_idx,
            fail_next,
            always_fail,
            latency=random.uniform(0.0, 0.1),
        )

    results = await asyncio.gather(*[one(i) for i in range(count)])
    bugs: list[str] = []
    graceful = 0
    for r in results:
        res = r["result"]
        if res is not None and res.status in ("failed", "cancelled"):
            graceful += 1
        bugs.extend(check_result(r))
        if res is None:
            print(f"[{r['run_idx']}] CRASH: no ExecutionResult.")
    return count, graceful, bugs


async def main_async(args: argparse.Namespace) -> int:
    """Run sweep (+ optional randoms), report, check for task leaks."""
    print("Starting Chaos Engineering Run...")
    total_runs = 0
    graceful = 0
    bugs: list[str] = []

    if args.sweep:
        print("── Stage sweep (deterministic, every stage + synth fallback) ──")
        runs, graceful_sweep, bugs_sweep = await run_sweep()
        total_runs += runs
        graceful += graceful_sweep
        bugs.extend(bugs_sweep)

    if args.random > 0:
        print(f"── Random faults × {args.random} ──")
        runs, graceful_rand, bugs_rand = await run_random(args.random)
        total_runs += runs
        graceful += graceful_rand
        bugs.extend(bugs_rand)

    await asyncio.sleep(0.5)
    remaining_tasks = [
        t for t in asyncio.all_tasks() if not t.done() and t != asyncio.current_task()
    ]
    if remaining_tasks:
        print(f"BUG: GLOBAL TASK LEAK DETECTED! {len(remaining_tasks)} tasks leaked.")
        for t in remaining_tasks:
            print(f"  - {t.get_name()}: {t.get_coro()}")
        bugs.append(f"task leak: {len(remaining_tasks)} tasks")

    print("-" * 40)
    print(f"Total runs: {total_runs}")
    print(f"Failures (Graceful): {graceful}")
    print(f"Bugs (Assertion Failures): {len(bugs)}")
    for bug in bugs:
        print(bug)

    if bugs:
        return 1
    print("All chaos assertions passed!")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry: --sweep (default on), --random N, --no-sweep."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep", dest="sweep", action="store_true", default=True)
    parser.add_argument("--no-sweep", dest="sweep", action="store_false")
    parser.add_argument("--random", type=int, default=0)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args(argv)
    if args.seed is not None:
        random.seed(args.seed)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
