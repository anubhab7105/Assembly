"""Assembly — debate stagnation guard (FR-5).

RoundDelta is computed from data we already have — no extra LLM calls:
position changes, confidence shifts above a configurable epsilon, new
evidence/sources, disagreements opened/resolved, contradiction change,
plus the existing new_info_rate/stability signals.

A stagnant round runs the adversarial strike once (if not yet run),
otherwise forces finalization with an uncertainty note. Plain debate
never follows a stagnant round. Rounds with failed-agent carry-forwards
never count as "no change".
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.config import settings


@dataclass
class StagnationConfig:
    """Thresholds for meaningful debate change (env-overridable)."""

    conf_epsilon: float = 0.05
    contradiction_epsilon: float = 0.05
    enabled: bool = True

    @classmethod
    def from_settings(cls) -> StagnationConfig:
        return cls(
            conf_epsilon=float(settings.stagnation_conf_epsilon),
            contradiction_epsilon=float(settings.stagnation_contradiction_epsilon),
            enabled=bool(settings.stagnation_enabled),
        )


@dataclass
class RoundDelta:
    """Change between two consecutive debate rounds (no LLM calls)."""

    position_changes: int = 0
    confidence_shift: float = 0.0
    new_evidence: int = 0
    new_sources: int = 0
    disagreements_opened: int = 0
    disagreements_resolved: int = 0
    contradiction_delta: float = 0.0
    new_info_rate: float = 0.0
    has_failure: bool = False
    stagnant: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "position_changes": self.position_changes,
            "confidence_shift": round(self.confidence_shift, 4),
            "new_evidence": self.new_evidence,
            "new_sources": self.new_sources,
            "disagreements_opened": self.disagreements_opened,
            "disagreements_resolved": self.disagreements_resolved,
            "contradiction_delta": round(self.contradiction_delta, 4),
            "new_info_rate": round(self.new_info_rate, 4),
            "has_failure": self.has_failure,
            "stagnant": self.stagnant,
            "reason": self.reason,
        }


def _evidence_keys(outputs: list) -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {}
    for o in outputs:
        claims: set[str] = set()
        for e in getattr(o, "evidence", []) or []:
            claim = getattr(e, "claim", "")
            claims.add(str(claim))
        keys[str(getattr(o, "agent_id", ""))] = claims
    return keys


def _source_keys(outputs: list) -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {}
    for o in outputs:
        urls: set[str] = set()
        for s in getattr(o, "sources", []) or []:
            url = s.get("url", "") if isinstance(s, dict) else getattr(s, "url", "")
            urls.add(str(url))
        keys[str(getattr(o, "agent_id", ""))] = urls
    return keys


def _disagreement_edges(outputs: list) -> set[tuple[str, tuple[str, ...]]]:
    edges: set[tuple[str, tuple[str, ...]]] = set()
    for o in outputs:
        targets = tuple(
            sorted(str(t) for t in (getattr(o, "disagrees_with", []) or []))
        )
        if targets:
            edges.add((str(getattr(o, "agent_id", "")), targets))
    return edges


def compute_round_delta(
    prev_outputs: list,
    curr_outputs: list,
    prev_contradiction: float = 0.0,
    curr_contradiction: float = 0.0,
    new_info_rate: float = 0.0,
    round_number: int = 0,
    config: StagnationConfig | None = None,
) -> RoundDelta:
    """Compare two rounds using recorded outputs only (no LLM calls)."""
    cfg = config or StagnationConfig.from_settings()
    delta = RoundDelta(new_info_rate=float(new_info_rate or 0.0))

    # Failed-agent carry-forwards must not count as "no change".
    for o in curr_outputs or []:
        if (
            int(getattr(o, "failed_round", 0) or 0) == int(round_number or 0)
            and int(round_number or 0) > 0
        ):
            delta.has_failure = True
            break

    prev_by_id = {str(getattr(o, "agent_id", "")): o for o in (prev_outputs or [])}
    curr_by_id = {str(getattr(o, "agent_id", "")): o for o in (curr_outputs or [])}
    common = [aid for aid in curr_by_id if aid in prev_by_id]

    for aid in common:
        prev = prev_by_id[aid]
        curr = curr_by_id[aid]
        if str(getattr(prev, "position", "")) != str(getattr(curr, "position", "")):
            delta.position_changes += 1

    shifts: list[float] = []
    for aid in common:
        try:
            prev_c = float(
                getattr(prev_by_id[aid], "calibrated_confidence", 0.0) or 0.0
            )
            curr_c = float(
                getattr(curr_by_id[aid], "calibrated_confidence", 0.0) or 0.0
            )
        except (TypeError, ValueError):
            continue
        shifts.append(abs(curr_c - prev_c))
    delta.confidence_shift = sum(shifts) / len(shifts) if shifts else 0.0

    prev_ev = _evidence_keys(prev_outputs or [])
    curr_ev = _evidence_keys(curr_outputs or [])
    for aid in common:
        delta.new_evidence += len(
            (curr_ev.get(aid) or set()) - (prev_ev.get(aid) or set())
        )

    prev_src = _source_keys(prev_outputs or [])
    curr_src = _source_keys(curr_outputs or [])
    for aid in common:
        delta.new_sources += len(
            (curr_src.get(aid) or set()) - (prev_src.get(aid) or set())
        )

    prev_edges = _disagreement_edges(prev_outputs or [])
    curr_edges = _disagreement_edges(curr_outputs or [])
    delta.disagreements_opened = len(curr_edges - prev_edges)
    delta.disagreements_resolved = len(prev_edges - curr_edges)

    try:
        delta.contradiction_delta = abs(
            float(curr_contradiction) - float(prev_contradiction)
        )
    except (TypeError, ValueError):
        delta.contradiction_delta = 0.0

    if delta.has_failure:
        delta.stagnant = False
        delta.reason = "partial failure this round — not stagnant"
        return delta
    if not cfg.enabled:
        delta.stagnant = False
        delta.reason = "stagnation guard disabled"
        return delta

    meaningful = (
        delta.position_changes > 0
        or delta.confidence_shift > cfg.conf_epsilon
        or delta.new_evidence > 0
        or delta.new_sources > 0
        or delta.disagreements_opened > 0
        or delta.disagreements_resolved > 0
        or delta.contradiction_delta > cfg.contradiction_epsilon
    )
    delta.stagnant = not meaningful
    delta.reason = (
        "no meaningful change (positions, confidence, evidence, disagreements)"
        if delta.stagnant
        else "round added value"
    )
    return delta


def needs_debate(report: object) -> bool:
    """True when a plain debate round is warranted (open disagreement or thin evidence).

    Uses the consensus report we already have: open disagreements, or
    evidence quality below the configured floor. No extra LLM calls.
    """
    open_dis = list(getattr(report, "open_disagreements", []) or [])
    if open_dis:
        return True
    factors = getattr(report, "factors", {}) or {}
    try:
        quality = float(factors.get("evidence_quality", 1.0))
    except (TypeError, ValueError):
        quality = 1.0
    try:
        floor = float(settings.consensus_evidence_floor)
    except (TypeError, ValueError, AttributeError):
        floor = 0.50
    return quality < floor


def stagnation_note() -> str:
    """Uncertainty note for forced finalization after stagnation."""
    return (
        "Debate stagnated (no meaningful change); finalizing from current "
        "positions with residual uncertainty."
    )
