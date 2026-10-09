"""Per-recipient debate compression budgets (all offline, no network)."""

import logging
from types import SimpleNamespace

from src.agents.base_agent import AgentOutput
from src.orchestration.debate import DebateManager
from tests.conftest import make_models_yaml


def _config(tmp_path):
    return make_models_yaml(
        tmp_path,
        {
            "groq": [
                {
                    "id": "big",
                    "family": "gpt-oss",
                    "roles": ["solver"],
                    "limits": {"context_tokens": 8000},
                }
            ],
            "tiny": [
                {
                    "id": "small",
                    "family": "qwen",
                    "roles": ["solver"],
                    "limits": {"context_tokens": 2000},
                }
            ],
            "mystery": [
                {
                    "id": "unknown-ctx",
                    "family": "gemini",
                    "roles": ["solver"],
                    "limits": {"context_tokens": None},
                }
            ],
        },
    )


def _load(tmp_path):
    from src.providers.config import load_models_config

    return load_models_config(_config(tmp_path))


def _agent(provider: str, model: str):
    return SimpleNamespace(
        agent_id=f"{provider}-{model}",
        provider=SimpleNamespace(provider_name=provider),
        model=model,
    )


def _output(agent_id: str, chars: int = 6000) -> AgentOutput:
    return AgentOutput(
        agent_id=agent_id,
        position="p" * chars,
        reasoning_summary="r" * chars,
        confidence=0.5,
    )


def test_budget_derives_from_recipient_context(tmp_path) -> None:
    config = _load(tmp_path)
    debate = DebateManager("exec-budget", config)
    # (min(8000, 12000) - 4500 - 500) * 4 // 2 others = 6000 chars each.
    assert debate._per_other_chars(_agent("groq", "big"), 2) == 6000
    compressed = debate._compress_outputs([_output("o1"), _output("o2")], 6000)
    assert len(compressed[0].position) == 4500 + len("... [truncated]")
    assert len(compressed[0].reasoning_summary) == 1500 + len("... [truncated]")
    # Originals untouched.
    assert len(compressed[0].position) < 6000


def test_tiny_context_hits_floor_not_zero(tmp_path) -> None:
    config = _load(tmp_path)
    debate = DebateManager("exec-floor", config)
    # (2000 - 5000) < 0 → MIN_PER_OTHER_CHARS floor.
    assert (
        debate._per_other_chars(_agent("tiny", "small"), 2)
        == DebateManager.MIN_PER_OTHER_CHARS
    )


def test_unknown_context_falls_back_with_warning(tmp_path, caplog) -> None:
    config = _load(tmp_path)
    debate = DebateManager("exec-legacy", config)
    with caplog.at_level(logging.WARNING, logger="assembly"):
        assert debate._per_other_chars(_agent("mystery", "unknown-ctx"), 2) is None
    assert "unknown context window" in caplog.text
    legacy = debate._compress_outputs([_output("o1", 5000)])
    assert len(legacy[0].position) == 1500 + len("... [truncated]")
    assert len(legacy[0].reasoning_summary) == 500 + len("... [truncated]")


def test_no_config_keeps_legacy_caps() -> None:
    debate = DebateManager("exec-none")
    assert debate._per_other_chars(_agent("groq", "big"), 2) is None


async def test_round_uses_recipient_budgets(tmp_path) -> None:
    """Two mock solvers with different contexts get different caps."""
    from src.agents.solver import SolverAgent
    from src.providers.mock_provider import MockProvider

    config = _load(tmp_path)
    big = SolverAgent(
        agent_id="big-01",
        provider=MockProvider(provider_name="groq"),
        model="big",
    )
    # Point the mock's provider name at the tiny-context catalog entry.
    small = SolverAgent(
        agent_id="small-01",
        provider=MockProvider(provider_name="tiny"),
        model="small",
    )
    debate = DebateManager("exec-round", config)
    prior = [
        AgentOutput(agent_id="big-01", position="p" * 20000, confidence=0.6),
        AgentOutput(agent_id="small-01", position="q" * 20000, confidence=0.6),
    ]
    seen: dict[str, int] = {}
    original = debate._agent_critique

    async def _spy(agent, question, others, round_number, timeout_s=None):
        seen[agent.agent_id] = len(others[0].position)
        return prior[0] if agent.agent_id == "big-01" else prior[1]

    debate._agent_critique = _spy  # type: ignore[method-assign]
    try:
        updated = await debate.run_debate_round(
            [big, small], prior, "What is the mock answer?", 1
        )
    finally:
        debate._agent_critique = original  # type: ignore[method-assign]
    assert len(updated) == 2
    # big recipient (one other): 12000-char budget → 9000-char positions.
    assert seen["big-01"] == 9000 + len("... [truncated]")
    # small recipient: floor 1200 → 900-char positions.
    assert seen["small-01"] == 900 + len("... [truncated]")
