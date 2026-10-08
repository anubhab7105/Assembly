"""
Assembly — Final composer (docs/WORKFLOW.md section 6, final-answer wording).

Deterministic post-processing of the synthesizer output. No LLM calls:
everything here is a pure function of the team outputs, the consensus
score, and the cited sources, so it is cheap to unit-test.

- Confidence bands follow WORKFLOW section 6 exactly:
  score >= 0.85 → High (state the answer normally),
  0.60–0.85 → Moderate (answer + main remaining uncertainty),
  below 0.60 → Low (leading answer + main alternative + no-consensus note).
- The numbered Sources list contains ONLY sources referenced by evidence
  in the final answer ([n] markers in the text or numeric evidence
  source_ids). Every [n] marker left in the text is guaranteed to map to
  a real source; orphan markers become [?] with a warning.
- `VerificationSummary` records what the team actually did: agents,
  families, rounds, disagreements resolved, sources verified.
"""

import re
from dataclasses import dataclass, field

from src.agents.base_agent import AgentOutput, SourceRef

# Score bands from WORKFLOW section 6 ("Final answer wording").
HIGH_BAND = 0.85
MODERATE_BAND = 0.60

LABEL_HIGH = "High"
LABEL_MODERATE = "Moderate"
LABEL_LOW = "Low"

#: Markers like [2] that are part of a Markdown link ([2](url)) are links,
#: not citations — never touch those.
CITATION_RE = re.compile(r"\[(\d+)\](?!\()")

#: Evidence source_ids that count as references: "2" or "[2]".
EVIDENCE_REF_RE = re.compile(r"^\[?(\d+)\]?$")

#: Prefix of the attribution footer synthesize() appends; the composer
#: lifts it off the body and re-attaches it after its own sections.
FOOTER_MARKER = "\n\n---\n🤖 This answer was assembled by "

MAX_NOTE_CHARS = 500
MAX_POSITION_QUOTE_CHARS = 500


def confidence_label_for_score(score: float) -> str:
    """High / Moderate / Low per the WORKFLOW section 6 bands."""
    clamped = min(1.0, max(0.0, score))
    if clamped >= HIGH_BAND:
        return LABEL_HIGH
    if clamped >= MODERATE_BAND:
        return LABEL_MODERATE
    return LABEL_LOW


def attribution_footer(agent_count: int, providers_used: list[str] | None) -> str:
    """Standard agent-attribution footer (shared with SynthesizerAgent)."""
    providers = providers_used or []
    provider_names = {
        "gemini": "Gemini",
        "groq": "Groq",
        "cerebras": "Cerebras",
        "openrouter": "OpenRouter",
        "huggingface": "Hugging Face",
    }
    display_names = [provider_names.get(p, p.title()) for p in providers]
    providers_str = ", ".join(display_names) if display_names else "multiple providers"
    return (
        f"\n\n---\n🤖 This answer was assembled by {agent_count} "
        f"AI agents powered by {providers_str}."
    )


def split_footer(text: str) -> tuple[str, str]:
    """Split a trailing attribution footer off the answer body.

    Returns (body, footer). The footer is empty when the marker is absent
    (e.g. direct unit-test inputs), in which case the caller rebuilds it.
    """
    index = text.rfind(FOOTER_MARKER)
    if index == -1:
        return text, ""
    return text[:index].rstrip(), text[index:]


def collect_citation_indices(text: str) -> list[int]:
    """1-based [n] citation indices in order of first appearance."""
    seen: list[int] = []
    for match in CITATION_RE.finditer(text or ""):
        index = int(match.group(1))
        if index not in seen:
            seen.append(index)
    return seen


def evidence_referenced_indices(evidence: list) -> list[int]:
    """Numeric evidence source_ids ("2" or "[2]") as 1-based indices."""
    indices: list[int] = []
    for item in evidence or []:
        raw = item.source_id if hasattr(item, "source_id") else item.get("source_id", "")
        match = EVIDENCE_REF_RE.match(str(raw or "").strip())
        if match:
            index = int(match.group(1))
            if index not in indices:
                indices.append(index)
    return indices


def renumber_citations(
    text: str, valid_old_indices: list[int]
) -> tuple[str, list[str]]:
    """Remap surviving [n] markers to a dense 1..K numbering.

    Markers pointing outside the surviving set become [?] so no dangling
    reference remains. Returns (rewritten text, warnings).
    """
    mapping = {old: new for new, old in enumerate(valid_old_indices, start=1)}
    warnings: list[str] = []

    def _replace(match: re.Match) -> str:
        old = int(match.group(1))
        if old in mapping:
            return f"[{mapping[old]}]"
        warnings.append(
            f"Citation [{old}] had no matching source and was flagged as [?]."
        )
        return "[?]"

    return CITATION_RE.sub(_replace, text or ""), warnings


def format_source_entry(number: int, source: SourceRef) -> str:
    """One numbered Markdown source line."""
    title = (source.title or "").strip() or "Untitled source"
    url = (source.url or "").strip()
    snippet = (source.snippet or "").strip()
    if url:
        line = f"{number}. [{title}]({url})"
    else:
        line = f"{number}. {title}"
    if snippet:
        line += f" — {snippet}"
    return line


def build_uncertainty_note(
    uncertainties: list[str],
    open_disagreements: list[dict],
    average_confidence: float,
) -> str:
    """Bulleted 'what is uncertain' note; never empty when called."""
    lines = [str(item).strip() for item in uncertainties or [] if str(item).strip()]
    for item in open_disagreements or []:
        agent_id = item.get("agent_id", "?")
        family = item.get("family", "?")
        targets = item.get("disagrees_with", [])
        position = str(item.get("position", ""))[:MAX_NOTE_CHARS]
        lines.append(f"{agent_id} ({family}) disputes {targets}: {position}")
    if not lines:
        lines.append(
            f"Team confidence averaged {average_confidence:.0%} with limited "
            "supporting evidence."
        )
    return "\n".join(f"- {line}" for line in lines)


def build_alternatives_note(agent_outputs: list[AgentOutput]) -> str:
    """Strongest non-leading position, or an honest no-alternative note."""
    tallies: dict[str, dict] = {}
    for output in agent_outputs or []:
        position = (output.position or "").strip()
        if not position:
            continue
        entry = tallies.setdefault(
            position, {"holders": [], "confidence": 0.0}
        )
        entry["holders"].append(output.agent_id or "?")
        entry["confidence"] += output.confidence or 0.0
    if len(tallies) < 2:
        return (
            "No distinct alternative emerged; the low score reflects limited "
            "confidence and evidence rather than open disagreement."
        )
    ranked = sorted(
        tallies.items(),
        key=lambda kv: (len(kv[1]["holders"]), kv[1]["confidence"]),
        reverse=True,
    )
    alternative, info = ranked[1]
    holders = ", ".join(info["holders"])
    total = sum(len(info_["holders"]) for _, info_ in ranked)
    return (
        f"Alternative (held by {len(info['holders'])} of {total} "
        f"agents — {holders}): {alternative[:MAX_POSITION_QUOTE_CHARS]}"
    )


@dataclass(frozen=True)
class VerificationSummary:
    """What the team actually did, in numbers."""

    agents: int = 0
    families: int = 0
    rounds: int = 0
    disagreements_resolved: int = 0
    sources_verified: int = 0
    citations_checked: int = 0
    citations_dropped: int = 0

    def to_dict(self) -> dict:
        return {
            "agents": self.agents,
            "families": self.families,
            "rounds": self.rounds,
            "disagreements_resolved": self.disagreements_resolved,
            "sources_verified": self.sources_verified,
            "citations_checked": self.citations_checked,
            "citations_dropped": self.citations_dropped,
        }


@dataclass(frozen=True)
class ComposedAnswer:
    """Final user-facing answer bundle."""

    answer_markdown: str
    confidence_label: str
    uncertainty_note: str  # "" at High band
    alternatives_note: str  # "" at/above 0.60
    sources: list[SourceRef] = field(default_factory=list)
    verification: VerificationSummary = field(default_factory=VerificationSummary)
    warnings: list[str] = field(default_factory=list)
    score: float = 0.0


def compose_final_answer(
    agent_outputs: list[AgentOutput],
    consensus_score: float,
    open_disagreements: list[dict],
    sources_pool: list[SourceRef],
    debate_rounds: int,
    disagreements_resolved: int = 0,
    agent_count: int | None = None,
    providers_used: list[str] | None = None,
    synth_position: str = "",
    synth_uncertainty: list[str] | None = None,
    synth_evidence: list | None = None,
) -> ComposedAnswer:
    """Assemble the final Markdown answer with validated citations.

    Args:
        agent_outputs: the team's final outputs (for counts, confidence,
            and the alternatives analysis).
        consensus_score: final consensus score; drives the label and
            which notes appear.
        open_disagreements: consensus report's open disagreements.
        sources_pool: candidate sources (synthesizer's, else the team's);
            only [n]-referenced ones survive into the answer.
        debate_rounds: rounds run (verification summary).
        disagreements_resolved: disagreements opened then resolved.
        agent_count: team size for the footer (defaults to len(outputs)).
        providers_used: provider names for the footer.
        synth_position: synthesizer answer text (may carry its footer).
        synth_uncertainty: synthesizer remaining_uncertainty items.
        synth_evidence: synthesizer evidence items (source_ids count as refs).
    """
    score = min(1.0, max(0.0, consensus_score or 0.0))
    label = confidence_label_for_score(score)
    pool = list(sources_pool or [])

    body, _old_footer = split_footer(synth_position or "")
    body = body.strip()

    # References in order of first appearance: text markers first, then
    # numeric evidence source_ids (both count as "referenced by evidence").
    referenced: list[int] = []
    for index in collect_citation_indices(body) + evidence_referenced_indices(
        synth_evidence
    ):
        if index not in referenced:
            referenced.append(index)
    valid_old = [index for index in referenced if 1 <= index <= len(pool)]
    dropped = [index for index in referenced if index not in valid_old]

    rewritten_body, rewrite_warnings = renumber_citations(body, valid_old)
    warnings = list(rewrite_warnings)
    if dropped:
        warnings.append(
            f"Dropped {len(dropped)} citation(s) with no matching source: "
            + ", ".join(f"[{index}]" for index in dropped)
            + "."
        )
    final_sources = [pool[index - 1] for index in valid_old]

    uncertainties = [str(item) for item in (synth_uncertainty or [])]
    if label == LABEL_HIGH:
        uncertainty_note = ""
    else:
        confidences = [o.confidence or 0.0 for o in agent_outputs or []]
        average = sum(confidences) / len(confidences) if confidences else 0.0
        uncertainty_note = build_uncertainty_note(
            uncertainties, open_disagreements or [], average
        )

    if score < MODERATE_BAND:
        alternatives_note = build_alternatives_note(agent_outputs)
    else:
        alternatives_note = ""

    families = {o.family for o in agent_outputs or [] if o.family}
    resolved = max(0, disagreements_resolved or 0)
    verification = VerificationSummary(
        agents=len(agent_outputs or []),
        families=len(families),
        rounds=max(0, debate_rounds or 0),
        disagreements_resolved=resolved,
        sources_verified=len(final_sources),
        citations_checked=len(referenced),
        citations_dropped=len(dropped),
    )

    sections = [rewritten_body] if rewritten_body else []
    sections.append(
        f"**Confidence: {label}** — team consensus {score:.0%}."
    )
    if uncertainty_note:
        sections.append("### What is uncertain\n" + uncertainty_note)
    if alternatives_note:
        sections.append("### Main alternative\n" + alternatives_note)
    if final_sources:
        lines = [
            format_source_entry(number, source)
            for number, source in enumerate(final_sources, start=1)
        ]
        sections.append("### Sources\n" + "\n".join(lines))

    if agent_count is None:
        agent_count = len(agent_outputs or [])
    answer_markdown = "\n\n".join(sections) + attribution_footer(
        agent_count, providers_used
    )

    # Post-condition: every surviving [n] marker maps to a real source.
    orphans = [
        index
        for index in collect_citation_indices(answer_markdown)
        if not 1 <= index <= len(final_sources)
    ]
    if orphans:
        warnings.append(
            "Internal error: unmapped citations remain: "
            + ", ".join(f"[{index}]" for index in orphans)
            + "."
        )

    return ComposedAnswer(
        answer_markdown=answer_markdown,
        confidence_label=label,
        uncertainty_note=uncertainty_note,
        alternatives_note=alternatives_note,
        sources=final_sources,
        verification=verification,
        warnings=warnings,
        score=score,
    )
