"""Consensus engine tests (docs/WORKFLOW.md section 6).

Synthetic positions cover: unanimous-early, split, converging,
thrashing, and failed-agent scenarios — plus the family-vote rule,
exact stopping conditions, the adversarial round, and report shape.
All LLM calls go through MockProvider (offline).
"""

from types import SimpleNamespace

import pytest

from src.agents.base_agent import AgentOutput
from src.agents.critic import CriticAgent
from src.core.config import settings
from src.orchestration.consensus import (
    ADVERSARIAL,
    DEBATE,
    FINALIZE,
    FORCE_FINALIZE,
    ConsensusConfig,
    ConsensusEngine,
)
from src.orchestration.orchestrator import Orchestrator
from src.providers.mock_provider import MockProvider


def _out(
    agent_id: str,
    position: str,
    family: str,
    agent_type: str = "solver",
    confidence: float = 0.85,
    n_evidence: int = 3,
    sourced_evidence: bool = True,
    n_sources: int = 0,
    supports: tuple = (),
    disagrees_with: tuple = (),
    failed_round=None,
) -> AgentOutput:
    evidence = [
        {
            "claim": f"{agent_id} claim {i}",
            "source_id": f"s{i}" if sourced_evidence else "",
        }
        for i in range(n_evidence)
    ]
    sources = [
        {
            "title": f"T{i}",
            "url": f"https://example.com/{agent_id}/{i}",
            "snippet": "excerpt",
        }
        for i in range(n_sources)
    ]
    return AgentOutput(
        agent_id=agent_id,
        agent_type=agent_type,
        position=position,
        reasoning_summary="summary",
        confidence=confidence,
        evidence=evidence,
        supports=list(supports),
        disagrees_with=list(disagrees_with),
        remaining_uncertainty=[],
        sources=sources,
        provider="mock",
        model="mock-model",
        family=family,
        tokens_used=10,
        latency_ms=5.0,
    )


def _unanimous(outputs_family_each=True):
    """Three solvers, same position, mutual support, sourced evidence."""
    fams = ("fam-a", "fam-b", "fam-c") if outputs_family_each else ("fam-x",) * 3
    ids = ("agent_01", "agent_02", "agent_03")
    return [
        _out(
            aid,
            "The answer is 42.",
            fam,
            supports=tuple(i for i in ids if i != aid),
            n_sources=1,
        )
        for aid, fam in zip(ids, fams)
    ]


# ── Config ────────────────────────────────────────────────────────


def test_weights_live_in_settings_config() -> None:
    assert (
        settings.consensus_w_agreement,
        settings.consensus_w_confidence,
        settings.consensus_w_evidence,
        settings.consensus_w_contradiction,
        settings.consensus_w_stability,
    ) == (0.30, 0.20, 0.25, 0.15, 0.10)
    assert settings.consensus_finalize_threshold == 0.85
    assert settings.consensus_new_info_threshold == 0.15
    cfg = ConsensusConfig.from_settings()
    assert cfg.w_agreement == 0.30
    assert cfg.finalize_threshold == 0.85


def test_custom_weights_rescale_score() -> None:
    outputs = _unanimous()
    engine = ConsensusEngine()
    full = engine.evaluate(outputs, 1)
    only_agreement = ConsensusEngine(
        ConsensusConfig(
            w_agreement=1.0,
            w_confidence=0.0,
            w_evidence=0.0,
            w_contradiction=0.0,
            w_stability=0.0,
        )
    ).evaluate(outputs, 1)
    assert only_agreement.score == pytest.approx(full.factors["agreement"])
    assert only_agreement.score == pytest.approx(1.0)


def test_score_formula_exact() -> None:
    a = _out(
        "agent_01",
        "Paris.",
        "fam-a",
        confidence=1.0,
        supports=("agent_02",),
        n_sources=1,
    )
    b = _out(
        "agent_02",
        "Paris.",
        "fam-b",
        confidence=1.0,
        supports=("agent_01",),
        n_sources=1,
    )
    engine = ConsensusEngine()
    engine.evaluate([a, b], 1)  # prime history; round 1 is all-new
    report = engine.evaluate([a, b], 2)
    assert report.factors == {
        "agreement": 1.0,
        "calibrated_confidence": 1.0,
        "evidence_quality": 1.0,
        "contradiction_ratio": 0.0,
        "stability": 1.0,
    }
    assert report.score == pytest.approx(1.0)
    assert report.decision == FINALIZE
    assert report.new_info_rate == pytest.approx(0.0)


# ── Family-vote agreement (WORKFLOW 6.5) ───────────────────────────


def test_same_family_counts_as_one_vote() -> None:
    solvers = [
        _out(
            f"solver_0{i}",
            "Answer A.",
            "fam-x",
            supports=tuple(f"solver_0{j}" for j in (1, 2, 3) if j != i),
        )
        for i in (1, 2, 3)
    ]
    critic = _out(
        "critic_01",
        "Answer B.",
        "fam-y",
        agent_type="critic",
        disagrees_with=("solver_01", "solver_02", "solver_03"),
    )
    report = ConsensusEngine().evaluate([*solvers, critic], 1)
    # Cross-family pairs: X→Y silent, Y→X disagrees ⇒ one decided pair.
    assert report.factors["agreement"] == pytest.approx(0.0)
    assert report.factors["contradiction_ratio"] == pytest.approx(0.5)
    # A naive agent-counted vote would report 6 supports / 9 edges ≈ 0.67.
    assert report.agreement_count == 6
    assert report.disagreement_count == 3


def test_distinct_families_each_vote() -> None:
    report = ConsensusEngine().evaluate(_unanimous(), 1)
    assert report.factors["agreement"] == pytest.approx(1.0)
    assert report.factors["contradiction_ratio"] == pytest.approx(0.0)


def test_position_fallback_without_edges() -> None:
    a = _out("agent_01", "Same.", "fam-a")
    b = _out("agent_02", "Same.", "fam-b")
    c = _out("agent_03", "Different.", "fam-c")
    report = ConsensusEngine().evaluate([a, b, c], 1)
    assert report.factors["agreement"] == pytest.approx(2 / 3)


# ── Stopping decisions (section 6 table) ──────────────────────────


def test_unanimous_early_triggers_adversarial() -> None:
    report = ConsensusEngine().evaluate(_unanimous(), 1)
    assert report.score >= 0.85
    assert report.decision == ADVERSARIAL
    assert "round 1" in report.reason


def test_high_score_round1_never_finalizes() -> None:
    # Even a perfect round-1 score must challenge first, not finalize.
    report = ConsensusEngine().evaluate(_unanimous(), 1)
    assert report.decision != FINALIZE


def test_all_agree_no_evidence_triggers_adversarial_late() -> None:
    outputs = [
        _out(
            aid,
            "The answer is 42.",
            fam,
            supports=("agent_02",),
            n_evidence=3,
            sourced_evidence=False,
        )
        for aid, fam in (
            ("agent_01", "fam-a"),
            ("agent_02", "fam-b"),
            ("agent_03", "fam-c"),
        )
    ]
    outputs[1] = _out(
        "agent_02",
        "The answer is 42.",
        "fam-b",
        supports=("agent_01",),
        n_evidence=3,
        sourced_evidence=False,
    )
    outputs[2] = _out(
        "agent_03",
        "The answer is 42.",
        "fam-c",
        supports=("agent_01",),
        n_evidence=3,
        sourced_evidence=False,
    )
    engine = ConsensusEngine()
    engine.evaluate(outputs, 1)
    report = engine.evaluate(outputs, 2)
    assert report.decision == ADVERSARIAL
    assert "no external evidence" in report.reason


def test_all_agree_with_evidence_finalizes() -> None:
    engine = ConsensusEngine()
    engine.evaluate(_unanimous(), 1)
    report = engine.evaluate(_unanimous(), 2)
    assert report.decision == FINALIZE
    assert "0.85" not in report.reason  # threshold rendered as 85%
    assert "85%" in report.reason


def test_split_team_debates_with_open_disagreements() -> None:
    a = _out(
        "agent_01", "P1.", "fam-a", supports=("agent_02",), disagrees_with=("agent_03",)
    )
    b = _out(
        "agent_02", "P1.", "fam-b", supports=("agent_01",), disagrees_with=("agent_04",)
    )
    c = _out(
        "agent_03", "P2.", "fam-c", supports=("agent_04",), disagrees_with=("agent_01",)
    )
    d = _out(
        "agent_04", "P2.", "fam-d", supports=("agent_03",), disagrees_with=("agent_02",)
    )
    report = ConsensusEngine().evaluate([a, b, c, d], 1)
    assert report.decision == DEBATE
    assert len(report.open_disagreements) == 4
    entry = report.open_disagreements[0]
    assert set(entry) == {
        "agent_id",
        "agent_type",
        "family",
        "disagrees_with",
        "position",
    }
    assert "disagreement" in report.reason


def test_partial_convergence_keeps_debating() -> None:
    engine = ConsensusEngine()
    engine.evaluate(
        [
            _out("agent_01", "P1.", "fam-a", disagrees_with=("agent_02",)),
            _out("agent_02", "P2.", "fam-b", disagrees_with=("agent_01",)),
        ],
        1,
    )
    report = engine.evaluate(
        [
            _out("agent_01", "P1.", "fam-a", supports=("agent_02",), n_sources=1),
            _out("agent_02", "P1.", "fam-b", supports=("agent_01",), n_sources=1),
        ],
        2,
    )
    # Only agent_02 moved: half the team changed its mind.
    assert report.factors["stability"] == pytest.approx(0.5)
    assert report.new_info_rate == pytest.approx(0.5)
    assert report.decision == DEBATE


def test_converging_stability_counts_unchanged() -> None:
    engine = ConsensusEngine()
    first = [
        _out("agent_01", "P1.", "fam-a", n_sources=1),
        _out("agent_02", "P1.", "fam-b", n_sources=1),
    ]
    engine.evaluate(first, 1)
    report = engine.evaluate(first, 2)  # identical positions round 2
    assert report.new_info_rate == pytest.approx(0.0)
    assert report.factors["stability"] == pytest.approx(1.0)
    assert report.decision == FINALIZE


def test_thrashing_keeps_debating() -> None:
    engine = ConsensusEngine()
    last = None
    for round_number, pos in enumerate(["P1.", "P2.", "P3."], start=1):
        last = engine.evaluate(
            [
                _out("agent_01", pos, "fam-a", disagrees_with=("agent_02",)),
                _out("agent_02", pos + "?", "fam-b", disagrees_with=("agent_01",)),
            ],
            round_number,
        )
    assert last is not None
    assert last.factors["stability"] == pytest.approx(0.0)
    assert last.decision == DEBATE


def test_failed_agent_excluded_from_stability() -> None:
    engine = ConsensusEngine()
    engine.evaluate(
        [_out("agent_01", "P1.", "fam-a"), _out("agent_02", "P1.", "fam-b")],
        1,
    )
    stale = _out("agent_01", "P1.", "fam-a")  # carry-forward, looks stable
    stale.failed_round = 2
    moved = _out("agent_02", "P2.", "fam-b")
    report = engine.evaluate([stale, moved], 2)
    # Without Fix D the stale output would fake 50% stability.
    assert report.new_info_rate == pytest.approx(1.0)
    assert report.factors["stability"] == pytest.approx(0.0)


def test_force_finalize_paths() -> None:
    outputs = _unanimous()
    forced = ConsensusEngine().evaluate(outputs, 2, force_finalize=True)
    assert forced.decision == FORCE_FINALIZE
    assert "expired" in forced.reason

    no_time = ConsensusEngine().evaluate(outputs, 2, time_for_round=False)
    assert no_time.decision == FORCE_FINALIZE
    assert "time" in no_time.reason.lower()

    no_quota = ConsensusEngine().evaluate(outputs, 2, quota_ok=False)
    assert no_quota.decision == FORCE_FINALIZE
    assert "Quota" in no_quota.reason


def test_empty_outputs_debate() -> None:
    report = ConsensusEngine().evaluate([], 1)
    assert report.score == 0.0
    assert report.decision == DEBATE
    assert report.reason != ""


# ── Adversarial round (WORKFLOW 5b) ───────────────────────────────


class _RecordingProvider(MockProvider):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.seen_messages: list[str] = []

    async def generate(self, messages, **kwargs):
        self.seen_messages.append("\n".join(m.content for m in messages))
        return await super().generate(messages, **kwargs)


def _counter_script():
    return {
        "position": "Counterargument: 42 is wrong because the premise fails.",
        "reasoning_summary": "Assuming the consensus is wrong, the opposite holds.",
        "confidence": 0.65,
        "evidence": [{"claim": "Counter-claim.", "source_id": ""}],
        "supports": [],
        "disagrees_with": ["agent_01"],
        "remaining_uncertainty": ["Needs verification."],
        "sources": [],
    }


def test_select_adversarial_critic_needs_different_family() -> None:
    solo_critic = SimpleNamespace(agent_id="c1", agent_type="critic", family="fam-x")
    outputs = _out("s1", "P.", "fam-x"), _out("s2", "P.", "fam-x")
    assert (
        ConsensusEngine.select_adversarial_critic([solo_critic], list(outputs)) is None
    )
    outsider = SimpleNamespace(agent_id="c2", agent_type="critic", family="fam-y")
    assert (
        ConsensusEngine.select_adversarial_critic([outsider], list(outputs)) is outsider
    )
    assert ConsensusEngine.select_adversarial_critic([], list(outputs)) is None


async def test_adversarial_round_replaces_and_rescores() -> None:
    provider = _RecordingProvider(scripts={"critic": _counter_script()})
    critic = CriticAgent(
        agent_id="agent_02", provider=provider, model="m", family="fam-c"
    )
    solvers = [
        _out("agent_01", "The answer is X.", "fam-s", n_sources=1),
        _out("agent_03", "The answer is X.", "fam-s", n_sources=1),
    ]
    prior_critic = _out(
        "agent_02",
        "The answer is X.",
        "fam-c",
        agent_type="critic",
        n_sources=1,
    )
    outputs = [solvers[0], prior_critic, solvers[1]]
    engine = ConsensusEngine()
    engine.evaluate(outputs, 1)  # baseline history

    updated, report = await engine.adversarial_round(
        critic, "Is X the answer?", outputs, 1
    )
    assert len(updated) == 3
    challenged = next(o for o in updated if o.agent_id == "agent_02")
    assert "Counterargument" in challenged.position
    assert challenged.family == "fam-c"
    # The strike used the assume-wrong prompt, not a plain critique.
    assert provider.seen_messages, "critic was never called"
    assert "assume the current consensus is wrong" in provider.seen_messages[0].lower()
    # Re-scored with adversarial triggers off and history updated.
    assert isinstance(report.new_info_rate, float)
    assert report.decision != ADVERSARIAL
    # The failed-then-fixed path is covered; Fix D state stays consistent.
    assert engine._previous_positions["agent_02"] == challenged.position


async def test_adversarial_round_none_without_critic() -> None:
    engine = ConsensusEngine()
    assert await engine.adversarial_round(None, "Q?", _unanimous(), 1) is None


# ── Report shape ────────────────────────────────────────────────


def test_report_shape_and_dict() -> None:
    report = ConsensusEngine().evaluate(_unanimous(), 1)
    assert set(report.factors) == {
        "agreement",
        "calibrated_confidence",
        "evidence_quality",
        "contradiction_ratio",
        "stability",
    }
    assert 0.0 <= report.score <= 1.0
    assert report.decision in (FINALIZE, DEBATE, ADVERSARIAL, FORCE_FINALIZE)
    assert report.reason != ""
    assert report.round_number == 1
    dumped = report.to_dict()
    assert dumped["decision"] == report.decision
    assert dumped["factors"]["agreement"] == pytest.approx(report.factors["agreement"])
    assert isinstance(dumped["open_disagreements"], list)


def test_positions_never_logged(fake_key, caplog) -> None:
    import logging

    outputs = [_out("agent_01", f"Secret answer {fake_key}", "fam-a")]
    with caplog.at_level(logging.INFO, logger="assembly"):
        ConsensusEngine().evaluate(outputs, 1)
    assert fake_key not in caplog.text


# ── Orchestrator wiring: full strike when families differ ───────


class _FamilyRouter:
    """Minimal stub: solver→fam-s, critic→fam-c (distinct families)."""

    def __init__(self):
        self._providers = {
            "mock-s": MockProvider(provider_name="mock-s"),
            "mock-c": MockProvider(provider_name="mock-c"),
        }

    def get_available_providers(self):
        return list(self._providers)

    def route(self, agent_type="solver", *args, **kwargs):
        name = "mock-c" if agent_type == "critic" else "mock-s"
        family = "fam-c" if agent_type == "critic" else "fam-s"
        return self._decision(agent_type, name, family)

    def route_for_planning(self):
        return self._decision("planner", "mock-s", "fam-s")

    def _decision(self, agent_type, name, family):
        provider = self._providers[name]
        return SimpleNamespace(
            provider=provider,
            model="mock-model",
            provider_name=name,
            family=family,
            role=agent_type,
            reason="test",
        )

    def route_team(self, team, *args, **kwargs):
        decisions = []
        for spec in team:
            if spec.get("agent_type") == "critic":
                decisions.append(self._decision("critic", "mock-c", "fam-c"))
            else:
                decisions.append(self._decision(spec["agent_type"], "mock-s", "fam-s"))
        return SimpleNamespace(
            decisions=decisions,
            warnings=[],
            degraded=False,
            families=["fam-s", "fam-c"],
        )


async def test_orchestrator_runs_adversarial_strike() -> None:
    solver_script = {
        "position": "Answer A.",
        "reasoning_summary": "Solver view.",
        "confidence": 0.9,
        "evidence": [
            {"claim": "Solver claim 1.", "source_id": "s1"},
            {"claim": "Solver claim 2.", "source_id": "s2"},
            {"claim": "Solver claim 3.", "source_id": ""},
        ],
        "supports": ["agent_02"],
        "disagrees_with": [],
        "remaining_uncertainty": [],
        "sources": [{"title": "T", "url": "https://example.com/t", "snippet": "x"}],
    }
    critic_script = {
        "position": "Answer B.",
        "reasoning_summary": "Critic view, agrees with solver.",
        "confidence": 0.9,
        "evidence": [
            {"claim": "Critic claim 1.", "source_id": "s2"},
            {"claim": "Critic claim 2.", "source_id": "s3"},
            {"claim": "Critic claim 3.", "source_id": ""},
        ],
        "supports": ["agent_01"],
        "disagrees_with": [],
        "remaining_uncertainty": [],
        "sources": [{"title": "U", "url": "https://example.com/u", "snippet": "y"}],
    }
    plan_script = {
        "problem_type": "general",
        "complexity": "medium",
        "needs_research": False,
        "team": [
            {"agent_type": "solver", "role_description": "s"},
            {"agent_type": "critic", "role_description": "c"},
        ],
        "reasoning": "test plan",
    }
    router = _FamilyRouter()
    router._providers["mock-s"]._scripts.update(
        {
            "solver": solver_script,
            "plan": plan_script,
            "synthesize": {
                "position": "FINAL: Answer A wins on stronger evidence.",
                "reasoning_summary": "Synthesis.",
                "confidence": 0.9,
                "evidence": [{"claim": "Solver claim.", "source_id": "s1"}],
                "supports": [],
                "disagrees_with": [],
                "remaining_uncertainty": [],
                "sources": [
                    {"title": "T", "url": "https://example.com/t", "snippet": "x"}
                ],
            },
        }
    )
    router._providers["mock-c"]._scripts.update({"critic": critic_script})

    orch = Orchestrator()
    orch.router = router
    events: list[dict] = []

    async def on_progress(event: dict) -> None:
        events.append(event)

    result = await orch.execute(
        execution_id="test-adv-strike",
        question="Which answer?",
        time_budget_minutes=3,
        on_progress=on_progress,
    )
    assert result.status == "completed"
    adversarial_events = [
        e
        for e in events
        if e["event_type"] == "round.started"
        and "Adversarial" in e["data"].get("goal", "")
    ]
    assert adversarial_events, "expected an adversarial round.started event"
    critic_calls = [
        c for c in router._providers["mock-c"].calls if c["script_key"] == "critic"
    ]
    assert len(critic_calls) >= 2  # independent solve + adversarial strike
    decisions = {
        e["data"]["decision"] for e in events if e["event_type"] == "consensus.updated"
    }
    assert decisions <= {FINALIZE, DEBATE, ADVERSARIAL, FORCE_FINALIZE}
