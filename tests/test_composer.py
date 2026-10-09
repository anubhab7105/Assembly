"""Final composer tests: bands, citations, notes, verification summary.

All offline via MockProvider (custom synthesize scripts) or pure synthetic
AgentOutput lists — no network, no real keys.
"""

import json
import re

from src.agents.base_agent import AgentOutput, EvidenceItem, SourceRef
from src.orchestration.composer import (
    attribution_footer,
    build_alternatives_note,
    build_uncertainty_note,
    collect_citation_indices,
    compose_final_answer,
    confidence_label_for_score,
    evidence_referenced_indices,
    renumber_citations,
    split_footer,
)


def _output(
    agent_id="agent_01",
    position="The answer is 42.",
    confidence=0.9,
    family="mock-fam",
    agent_type="solver",
    evidence=(),
    disagrees_with=(),
    sources=(),
):
    return AgentOutput(
        agent_id=agent_id,
        agent_type=agent_type,
        position=position,
        confidence=confidence,
        evidence=[EvidenceItem(claim=c, source_id=s) for c, s in evidence],
        disagrees_with=list(disagrees_with),
        sources=[SourceRef(**s) for s in sources],
        family=family,
    )


def _source(title="T", url="https://example.com/x", snippet="Excerpt."):
    return SourceRef(title=title, url=url, snippet=snippet)


# ── Confidence bands (WORKFLOW section 6) ────────────────────────────


def test_confidence_bands_exact_edges() -> None:
    assert confidence_label_for_score(1.0) == "High"
    assert confidence_label_for_score(0.85) == "High"
    assert confidence_label_for_score(0.849) == "Moderate"
    assert confidence_label_for_score(0.60) == "Moderate"
    assert confidence_label_for_score(0.599) == "Low"
    assert confidence_label_for_score(0.0) == "Low"
    # Out-of-range inputs clamp instead of crashing.
    assert confidence_label_for_score(1.5) == "High"
    assert confidence_label_for_score(-0.2) == "Low"


def test_high_band_has_no_notes() -> None:
    composed = compose_final_answer(
        agent_outputs=[_output()],
        consensus_score=0.9,
        open_disagreements=[],
        sources_pool=[],
        debate_rounds=1,
        synth_position="The answer is 42.",
    )
    assert composed.confidence_label == "High"
    assert composed.uncertainty_note == ""
    assert composed.alternatives_note == ""
    assert "What is uncertain" not in composed.answer_markdown
    assert "Main alternative" not in composed.answer_markdown
    assert "**Confidence: High**" in composed.answer_markdown


def test_moderate_band_has_uncertainty_only() -> None:
    composed = compose_final_answer(
        agent_outputs=[_output(confidence=0.7)],
        consensus_score=0.7,
        open_disagreements=[],
        sources_pool=[],
        debate_rounds=2,
        synth_position="The answer is probably 42.",
        synth_uncertainty=["The second digit is a guess."],
    )
    assert composed.confidence_label == "Moderate"
    assert "The second digit is a guess." in composed.uncertainty_note
    assert "What is uncertain" in composed.answer_markdown
    assert "Main alternative" not in composed.answer_markdown
    assert composed.alternatives_note == ""


def test_low_band_has_both_notes() -> None:
    team = [
        _output("agent_01", "The answer is 42.", 0.6, family="fam-a"),
        _output("agent_02", "The answer is 42.", 0.6, family="fam-b"),
        _output("agent_03", "The answer is 43.", 0.5, family="fam-c"),
    ]
    composed = compose_final_answer(
        agent_outputs=team,
        consensus_score=0.5,
        open_disagreements=[
            {
                "agent_id": "agent_03",
                "agent_type": "critic",
                "family": "fam-c",
                "disagrees_with": ["agent_01"],
                "position": "The answer is 43.",
            }
        ],
        sources_pool=[],
        debate_rounds=2,
        synth_position="Leaning 42.",
        synth_uncertainty=[],
    )
    assert composed.confidence_label == "Low"
    assert "What is uncertain" in composed.answer_markdown
    assert "Main alternative" in composed.answer_markdown
    assert "43" in composed.alternatives_note
    assert "agent_03" in composed.alternatives_note


def test_low_band_without_rival_falls_back_honestly() -> None:
    composed = compose_final_answer(
        agent_outputs=[_output(confidence=0.4)],
        consensus_score=0.4,
        open_disagreements=[],
        sources_pool=[],
        debate_rounds=1,
        synth_position="Maybe 42.",
    )
    assert "No distinct alternative" in composed.alternatives_note
    assert "Main alternative" in composed.answer_markdown


def test_uncertainty_fallback_without_inputs() -> None:
    note = build_uncertainty_note([], [], 0.5)
    assert "50%" in note


def test_alternatives_picks_strongest_minority() -> None:
    team = [
        _output("a1", "Lead.", 0.9, family="f1"),
        _output("a2", "Lead.", 0.9, family="f2"),
        _output("a3", "Alt X.", 0.7, family="f3"),
        _output("a4", "Alt Y.", 0.4, family="f4"),
    ]
    note = build_alternatives_note(team)
    assert "Alt X." in note
    assert "Alt Y." not in note
    assert "a3" in note


# ── Citations: collection, renumbering, validation ───────────────────


def test_collect_citation_indices_in_appearance_order() -> None:
    assert collect_citation_indices("See [3] and [1], again [3].") == [3, 1]
    assert collect_citation_indices("No markers here.") == []
    # Markdown links are links, not citations.
    assert collect_citation_indices("See [1](https://example.com).") == []


def test_evidence_source_ids_count_as_references() -> None:
    evidence = [
        EvidenceItem(claim="c1", source_id="[2]"),
        EvidenceItem(claim="c2", source_id="3"),
        EvidenceItem(claim="c3", source_id=""),
        EvidenceItem(claim="c4", source_id="s1"),
    ]
    assert evidence_referenced_indices(evidence) == [2, 3]


def test_renumber_dense_and_flag_orphans() -> None:
    text, warnings = renumber_citations("A [3] then [1], bad [9].", [3, 1])
    assert text == "A [1] then [2], bad [?]."
    assert any("[9]" in w for w in warnings)


def test_cited_sources_only_and_renumbered() -> None:
    pool = [_source(title=f"T{i}", url=f"https://example.com/{i}") for i in range(3)]
    composed = compose_final_answer(
        agent_outputs=[_output()],
        consensus_score=0.9,
        open_disagreements=[],
        sources_pool=pool,
        debate_rounds=1,
        synth_position="Claim one [3] and claim two [1].",
    )
    assert [s.title for s in composed.sources] == ["T2", "T0"]
    assert "Claim one [1] and claim two [2]." in composed.answer_markdown
    assert "### Sources" in composed.answer_markdown
    assert "\n1. [T2](https://example.com/2)" in composed.answer_markdown
    assert "\n2. [T0](https://example.com/0)" in composed.answer_markdown
    # Every surviving [n] maps to a real source.
    for marker in re.findall(r"\[(\d+)\](?!\()", composed.answer_markdown):
        assert 1 <= int(marker) <= len(composed.sources)


def test_orphan_citation_neutralized_with_warning() -> None:
    pool = [_source(title="Only")]
    composed = compose_final_answer(
        agent_outputs=[_output()],
        consensus_score=0.9,
        open_disagreements=[],
        sources_pool=pool,
        debate_rounds=1,
        synth_position="Real [1], phantom [9].",
    )
    assert "Real [1], phantom [?]." in composed.answer_markdown
    assert len(composed.sources) == 1
    assert any("[9]" in w for w in composed.warnings)
    assert composed.verification.citations_dropped == 1
    assert composed.verification.citations_checked == 2


def test_unreferenced_pool_sources_excluded() -> None:
    pool = [_source(title="Used"), _source(title="Unused")]
    composed = compose_final_answer(
        agent_outputs=[_output()],
        consensus_score=0.9,
        open_disagreements=[],
        sources_pool=pool,
        debate_rounds=1,
        synth_position="Only this [1].",
    )
    assert [s.title for s in composed.sources] == ["Used"]
    assert "Unused" not in composed.answer_markdown


def test_no_references_reports_unused_sources() -> None:
    composed = compose_final_answer(
        agent_outputs=[_output()],
        consensus_score=0.9,
        open_disagreements=[],
        sources_pool=[_source()],
        debate_rounds=1,
        synth_position="Bare answer, no markers.",
    )
    assert composed.sources == []
    assert "No external sources were used." in composed.answer_markdown
    assert composed.verification.external_sources_used is False


def test_empty_pool_reports_no_external_sources() -> None:
    composed = compose_final_answer(
        agent_outputs=[_output()],
        consensus_score=0.9,
        open_disagreements=[],
        sources_pool=[],
        debate_rounds=1,
        synth_position="Bare answer.",
    )
    assert composed.sources == []
    assert "No external sources were used." in composed.answer_markdown
    assert composed.verification.external_sources_used is False


def test_markdown_link_bodies_untouched() -> None:
    pool = [_source(title="T", url="https://example.com/t")]
    text = "Read [the docs](https://example.com/t) for details."
    composed = compose_final_answer(
        agent_outputs=[_output()],
        consensus_score=0.9,
        open_disagreements=[],
        sources_pool=pool,
        debate_rounds=1,
        synth_position=text,
    )
    assert text in composed.answer_markdown
    assert composed.sources == []


# ── Verification summary + footer ────────────────────────────────────


def test_verification_summary_counts() -> None:
    team = [
        _output("agent_01", "P.", 0.8, family="fam-a"),
        _output("agent_02", "P.", 0.8, family="fam-a"),
        _output("agent_03", "Q.", 0.6, family="fam-b"),
    ]
    composed = compose_final_answer(
        agent_outputs=team,
        consensus_score=0.7,
        open_disagreements=[],
        sources_pool=[_source()],
        debate_rounds=3,
        disagreements_resolved=2,
        synth_position="P. [1]",
    )
    assert composed.verification.to_dict() == {
        "agents": 3,
        "families": 2,
        "rounds": 3,
        "disagreements_resolved": 2,
        "sources_verified": 1,
        "citations_checked": 1,
        "citations_dropped": 0,
        "research_degraded": False,
        "research_failures": 0,
        "circuit_breaker_trips": [],
        "external_sources_used": True,
    }


def test_footer_rebuilt_once_at_end() -> None:
    footer = attribution_footer(2, ["groq"])
    assert "assembled by 2 AI agents" in footer
    assert "Groq" in footer
    composed = compose_final_answer(
        agent_outputs=[_output(), _output(agent_id="agent_02")],
        consensus_score=0.9,
        open_disagreements=[],
        sources_pool=[],
        debate_rounds=1,
        providers_used=["groq"],
        synth_position="Body." + footer,
    )
    assert composed.answer_markdown.count("assembled by 2 AI agents") == 1
    assert composed.answer_markdown.rstrip().endswith(footer.strip())
    assert composed.answer_markdown.startswith("Body.")


async def test_footer_matches_synthesizer_format() -> None:
    from src.agents.synthesizer import SynthesizerAgent
    from src.providers.mock_provider import MockProvider

    agent = SynthesizerAgent(agent_id="agent_09", provider=MockProvider(), model="m")
    result = await agent.synthesize(
        question="Q?",
        agent_outputs=[
            _output(
                sources=[{"title": "S", "url": "https://example.com/s", "snippet": "x"}]
            )
        ],
        consensus_score=0.9,
        debate_rounds=1,
        providers_used=["groq"],
    )
    body, footer = split_footer(result.position)
    assert body  # footer split leaves a non-empty body
    assert footer == attribution_footer(1, ["groq"])


def test_split_footer_without_marker() -> None:
    body, footer = split_footer("Just text, no footer.")
    assert body == "Just text, no footer."
    assert footer == ""


# ── Orchestrator wiring: composed answer end to end ──────────────────


async def test_orchestrator_answer_is_composed(orchestrator) -> None:
    events: list[dict] = []

    async def on_progress(event: dict) -> None:
        events.append(event)

    result = await orchestrator.execute(
        execution_id="test-exec-composed",
        question="What is the mock answer?",
        time_budget_minutes=3,
        on_progress=on_progress,
    )
    assert result.status == "completed"
    assert "FINAL MOCK ANSWER" in result.answer
    assert "**Confidence: High**" in result.answer
    assert "assembled by 2 AI agents" in result.answer
    assert result.verification["agents"] == 2
    assert result.verification["rounds"] >= 1
    assert result.verification["sources_verified"] == len(result.sources)
    completed = [e for e in events if e["event_type"] == "execution.completed"]
    assert len(completed) == 1
    assert completed[0]["data"]["verification"] == result.verification


async def test_orchestrator_low_band_answer_shape() -> None:
    """Force a low score via always-disagreeing mocks: notes must appear."""
    from types import SimpleNamespace

    from src.orchestration.orchestrator import Orchestrator
    from src.providers.mock_provider import MockProvider

    def _team(position: str, confidence: float, disagrees: list) -> dict:
        return {
            "position": position,
            "reasoning_summary": "Mock reasoning.",
            "confidence": confidence,
            "evidence": [{"claim": "c", "source_id": ""}],
            "supports": [],
            "disagrees_with": disagrees,
            "remaining_uncertainty": ["Mock caveat."],
            "sources": [],
        }

    providers = {
        "mock-plan": MockProvider(
            scripts={
                "plan": {
                    "problem_type": "general",
                    "complexity": "medium",
                    "needs_research": False,
                    "team": [
                        {"agent_type": "solver", "role_description": "s"},
                        {"agent_type": "critic", "role_description": "c"},
                    ],
                    "reasoning": "test plan",
                }
            },
            provider_name="mock-plan",
        ),
        "mock-s": MockProvider(
            scripts={
                "solver": _team("Answer A is right.", 0.4, ["agent_02"]),
                "default": _team("Answer A is right.", 0.4, ["agent_02"]),
            },
            provider_name="mock-s",
        ),
        "mock-c": MockProvider(
            scripts={
                "critic": _team("Answer B is right.", 0.4, ["agent_01"]),
                "default": _team("Answer B is right.", 0.4, ["agent_01"]),
            },
            provider_name="mock-c",
        ),
        "mock-synth": MockProvider(
            scripts={
                "synthesize": {
                    "position": "Leaning A, weakly [1].",
                    "reasoning_summary": "Weak synthesis.",
                    "confidence": 0.4,
                    "evidence": [{"claim": "c", "source_id": ""}],
                    "supports": [],
                    "disagrees_with": [],
                    "remaining_uncertainty": ["Everything is uncertain."],
                    "sources": [
                        {
                            "title": "S1",
                            "url": "https://example.com/1",
                            "snippet": "s1",
                        }
                    ],
                }
            },
            provider_name="mock-synth",
        ),
    }
    role_map = {
        "planner": "mock-plan",
        "solver": "mock-s",
        "critic": "mock-c",
        "researcher": "mock-s",
        "synthesizer": "mock-synth",
    }

    def _decision(agent_type: str):
        name = role_map.get(agent_type, "mock-s")
        return SimpleNamespace(
            provider=providers[name],
            model="mock-model",
            provider_name=name,
            family=f"fam-{name}",
            role=agent_type,
            reason="test",
        )

    class RoleRouter:
        def route(self, agent_type="solver", **kwargs):
            return _decision(agent_type)

        def route_for_planning(self):
            return _decision("planner")

        def route_team(self, team, *args, **kwargs):
            return SimpleNamespace(
                decisions=[
                    _decision(spec.get("agent_type", "solver")) for spec in team
                ],
                warnings=[],
                degraded=False,
                families=[],
            )

        def get_available_providers(self):
            return list(providers)

    orch = Orchestrator()
    orch.router = RoleRouter()
    result = await orch.execute(
        execution_id="test-exec-lowband",
        question="Which answer?",
        time_budget_minutes=3,
    )
    assert result.status == "completed"
    assert "**Confidence: Low**" in result.answer
    assert "What is uncertain" in result.answer
    assert "Main alternative" in result.answer
    assert "Answer B is right." in result.answer
    assert "### Sources" in result.answer
    assert "https://example.com/1" in result.answer
    assert result.verification["rounds"] >= 1


# ── Key-leak scan (AGENTS.md section 5) ──────────────────────────────


async def test_composed_output_leaks_no_keys(orchestrator, fake_key, caplog) -> None:
    """Provider keys must not appear in the composed answer, sources,
    verification summary, warnings, events, or logs."""
    import logging

    events: list[dict] = []

    async def on_progress(event: dict) -> None:
        events.append(event)

    with caplog.at_level(logging.INFO, logger="assembly"):
        result = await orchestrator.execute(
            execution_id="test-exec-composed-keys",
            question="What is the mock answer?",
            time_budget_minutes=3,
            on_progress=on_progress,
            provider_keys={"groq": fake_key},
        )

    assert result.status in ("completed", "failed", "cancelled")
    assert fake_key not in (result.answer or "")
    assert fake_key not in json.dumps(result.sources)
    assert fake_key not in json.dumps(result.verification)
    assert fake_key not in json.dumps(getattr(result, "warnings", []))
    assert fake_key not in json.dumps(events)
    assert fake_key not in caplog.text
