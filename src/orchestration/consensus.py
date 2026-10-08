"""
Assembly — Consensus Engine (docs/WORKFLOW.md section 6).

Scores agreement, calibrated confidence, evidence quality,
contradictions and stability, then returns one of four stopping
decisions with a reason string:

    FINALIZE        score >= 0.85, new info low, no critical contradiction
    ADVERSARIAL     score >= 0.85 in round 1, or unanimous with no evidence
    DEBATE          open disagreement or thin evidence, time permitting
    FORCE_FINALIZE  out of time/quota (or forced) — synthesize now

Anti-echo rules applied here: agents from the same model family count
as ONE vote when computing agreement (WORKFLOW 6.5), and failed calls
are excluded from stabilization (Fix D, WORKFLOW 6.6).
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional

from src.agents.base_agent import AgentOutput
from src.core.config import settings
from src.core.logging_config import logger

# Stopping decisions returned by evaluate().
FINALIZE = "FINALIZE"
DEBATE = "DEBATE"
ADVERSARIAL = "ADVERSARIAL"
FORCE_FINALIZE = "FORCE_FINALIZE"


@dataclass
class ConsensusConfig:
    """Scoring weights and stopping thresholds (WORKFLOW section 6).

    Defaults mirror src/core/config.py so benchmarks can tune them via
    environment without touching code. Weights should sum to 1.0.
    """

    w_agreement: float = 0.30
    w_confidence: float = 0.20
    w_evidence: float = 0.25
    w_contradiction: float = 0.15
    w_stability: float = 0.10
    finalize_threshold: float = 0.85
    new_info_threshold: float = 0.15
    contradiction_limit: float = 0.20
    evidence_floor: float = 0.50

    @classmethod
    def from_settings(cls) -> "ConsensusConfig":
        """Build from the app Settings (env-overridable)."""
        return cls(
            w_agreement=settings.consensus_w_agreement,
            w_confidence=settings.consensus_w_confidence,
            w_evidence=settings.consensus_w_evidence,
            w_contradiction=settings.consensus_w_contradiction,
            w_stability=settings.consensus_w_stability,
            finalize_threshold=settings.consensus_finalize_threshold,
            new_info_threshold=settings.consensus_new_info_threshold,
            contradiction_limit=settings.consensus_contradiction_limit,
            evidence_floor=settings.consensus_evidence_floor,
        )


@dataclass
class ConsensusReport:
    """One consensus evaluation: score, breakdown, disagreements, decision."""

    score: float  # 0.0 to 1.0, weighted per WORKFLOW section 6
    decision: str  # FINALIZE | DEBATE | ADVERSARIAL | FORCE_FINALIZE
    reason: str  # human-readable why for this decision
    factors: dict  # agreement, calibrated_confidence, evidence_quality, ...
    open_disagreements: list  # [{agent_id, agent_type, family, disagrees_with, position}]
    new_info_rate: float  # fraction of agents that changed position this round
    agreement_count: int  # raw support edges (descriptive, not family-weighted)
    disagreement_count: int  # raw disagree edges (descriptive, not family-weighted)
    average_confidence: float  # mean calibrated confidence
    round_number: int = 1

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 3),
            "decision": self.decision,
            "reason": self.reason,
            "factors": {k: round(v, 3) for k, v in self.factors.items()},
            "open_disagreements": self.open_disagreements,
            "new_info_rate": round(self.new_info_rate, 3),
            "agreement_count": self.agreement_count,
            "disagreement_count": self.disagreement_count,
            "average_confidence": round(self.average_confidence, 3),
            "round_number": self.round_number,
        }


class ConsensusEngine:
    """
    Scores team consensus and decides whether to finalize, debate,
    run an adversarial round, or force finalization.

    Position history (`_previous_positions`) drives the stability factor;
    call reset() between executions.
    """

    def __init__(self, config: Optional[ConsensusConfig] = None):
        self.config = config or ConsensusConfig.from_settings()
        self._previous_positions: dict[str, str] = {}  # agent_id → previous position

    # ── Main entry point ──────────────────────────────────────────

    def evaluate(
        self,
        outputs: list[AgentOutput],
        round_number: int,
        force_finalize: bool = False,
        time_for_round: bool = True,
        quota_ok: bool = True,
        allow_adversarial: bool = True,
        verification: dict[str, bool] | None = None,
    ) -> ConsensusReport:
        """Score the outputs and return a stopping decision.

        Args:
            outputs: current round's agent outputs.
            round_number: 1-based round (1 = independent solve).
            force_finalize: time budget expired — synthesize now.
            time_for_round: room for another round plus synthesis.
            quota_ok: quota not nearly exhausted.
            allow_adversarial: False once an adversarial round already ran.
            verification: claim → cross-verified map from CitationManager
                (claims backed by 2+ independent domains score higher).
        """
        factors: dict[str, float] = {}
        if not outputs:
            return ConsensusReport(
                score=0.0,
                decision=DEBATE,
                reason="No agent outputs to evaluate — debate another round.",
                factors=factors,
                open_disagreements=[],
                new_info_rate=1.0,
                agreement_count=0,
                disagreement_count=0,
                average_confidence=0.0,
                round_number=round_number,
            )

        agreement = self._calculate_agreement(outputs)
        calibrated_conf = self._calculate_confidence(outputs)
        evidence_quality = self._calculate_evidence_quality(outputs, verification)
        contradiction_ratio = self._calculate_contradiction_ratio(outputs)
        new_info_rate = self._calculate_new_information_rate(outputs, round_number)
        stability = 1.0 - new_info_rate
        factors = {
            "agreement": agreement,
            "calibrated_confidence": calibrated_conf,
            "evidence_quality": evidence_quality,
            "contradiction_ratio": contradiction_ratio,
            "stability": stability,
        }
        score = min(
            1.0,
            max(
                0.0,
                agreement * self.config.w_agreement
                + calibrated_conf * self.config.w_confidence
                + evidence_quality * self.config.w_evidence
                + (1.0 - contradiction_ratio) * self.config.w_contradiction
                + stability * self.config.w_stability,
            ),
        )

        open_disagreements = self._open_disagreements(outputs)
        has_external_evidence = self._has_external_evidence(outputs)
        avg_confidence = calibrated_conf

        decision, reason = self._decide(
            score=score,
            new_info_rate=new_info_rate,
            contradiction_ratio=contradiction_ratio,
            open_disagreements=open_disagreements,
            evidence_quality=evidence_quality,
            has_external_evidence=has_external_evidence,
            positions_match=self._positions_match(outputs),
            agent_count=len(outputs),
            round_number=round_number,
            force_finalize=force_finalize,
            time_for_round=time_for_round,
            quota_ok=quota_ok,
            allow_adversarial=allow_adversarial,
        )

        # Update position history for next round's stability calculation.
        for o in outputs:
            self._previous_positions[o.agent_id] = o.position

        report = ConsensusReport(
            score=score,
            decision=decision,
            reason=reason,
            factors=factors,
            open_disagreements=open_disagreements,
            new_info_rate=new_info_rate,
            agreement_count=sum(len(o.supports) for o in outputs),
            disagreement_count=sum(len(o.disagrees_with) for o in outputs),
            average_confidence=avg_confidence,
            round_number=round_number,
        )

        logger.info(
            f"Consensus │ Round {round_number}: score={score:.0%}, "
            f"decision={decision}, agreements={report.agreement_count}, "
            f"disagreements={report.disagreement_count}"
        )
        return report

    # ── Adversarial round (WORKFLOW 5b) ───────────────────────────

    @staticmethod
    def select_adversarial_critic(
        agents: list, outputs: list[AgentOutput]
    ) -> Any | None:
        """Pick a critic from a different family than the consensus block.

        Returns None when there is no critic, or no critic outside the
        consensus families (e.g. single-family team) — callers then run a
        normal debate round instead.
        """
        critics = [a for a in agents if getattr(a, "agent_type", "") == "critic"]
        if not critics or not outputs:
            return None
        block_position = Counter(o.position for o in outputs).most_common(1)[0][0]
        consensus_families = {
            (o.family or "").strip()
            for o in outputs
            if o.position == block_position
        }
        for critic in critics:
            family = (getattr(critic, "family", "") or "").strip()
            if family and family not in consensus_families:
                return critic
        return None

    async def adversarial_round(
        self,
        critic: Any,
        question: str,
        outputs: list[AgentOutput],
        round_number: int,
        force_finalize: bool = False,
        time_for_round: bool = True,
        quota_ok: bool = True,
    ) -> tuple[list[AgentOutput], ConsensusReport] | None:
        """Run one adversarial strike and re-score (WORKFLOW 5b).

        The critic assumes the consensus is wrong and produces the
        strongest counterargument; its output replaces its previous one
        and the team is re-scored with adversarial triggers disabled
        (one strike per decision is enough — the re-score decides next).
        Returns None when no eligible critic was passed.
        """
        if critic is None:
            return None
        others = [o for o in outputs if o.agent_id != critic.agent_id]
        challenge_fn = getattr(critic, "adversarial_challenge", None)
        if challenge_fn is None:
            challenge_fn = critic.critique
        logger.info(
            f"Consensus │ Adversarial round: {critic.agent_id} "
            f"({getattr(critic, 'family', '')}) assumes the consensus is wrong"
        )
        challenge = await challenge_fn(question, others, round_number)
        updated = [
            challenge if o.agent_id == critic.agent_id else o for o in outputs
        ]
        if all(o.agent_id != critic.agent_id for o in outputs):
            updated.append(challenge)
        report = self.evaluate(
            updated,
            round_number,
            force_finalize=force_finalize,
            time_for_round=time_for_round,
            quota_ok=quota_ok,
            allow_adversarial=False,
        )
        return updated, report

    # ── Stopping decision (WORKFLOW section 6 table, in order) ────

    def _decide(
        self,
        score: float,
        new_info_rate: float,
        contradiction_ratio: float,
        open_disagreements: list,
        evidence_quality: float,
        has_external_evidence: bool,
        positions_match: bool,
        agent_count: int,
        round_number: int,
        force_finalize: bool,
        time_for_round: bool,
        quota_ok: bool,
        allow_adversarial: bool,
    ) -> tuple[str, str]:
        """Return (decision, reason) following the section 6 table top-down."""
        cfg = self.config
        if force_finalize:
            return FORCE_FINALIZE, "Time budget expired — forcing final synthesis."
        if not time_for_round:
            return (
                FORCE_FINALIZE,
                "Not enough time left for another round plus synthesis — "
                "finalizing from current positions.",
            )
        if not quota_ok:
            return (
                FORCE_FINALIZE,
                "Quota nearly exhausted — finalizing from current positions.",
            )
        if (
            allow_adversarial
            and score >= cfg.finalize_threshold
            and round_number <= 1
        ):
            return (
                ADVERSARIAL,
                f"Score {score:.0%} in round 1 — suspiciously agreeable too "
                "early; running an adversarial round.",
            )
        if (
            allow_adversarial
            and agent_count >= 2
            and not open_disagreements
            and positions_match
            and not has_external_evidence
        ):
            return (
                ADVERSARIAL,
                "All agents agree with no external evidence — running an "
                "adversarial round to check for an echo chamber.",
            )
        if (
            score >= cfg.finalize_threshold
            and new_info_rate < cfg.new_info_threshold
            and contradiction_ratio < cfg.contradiction_limit
        ):
            return (
                FINALIZE,
                f"Consensus {score:.0%} ≥ {cfg.finalize_threshold:.0%}, new info "
                f"low ({new_info_rate:.0%}), no critical contradiction.",
            )
        if open_disagreements or evidence_quality < cfg.evidence_floor:
            details = []
            if open_disagreements:
                details.append(f"{len(open_disagreements)} open disagreement(s)")
            if evidence_quality < cfg.evidence_floor:
                details.append(f"evidence thin (quality={evidence_quality:.0%})")
            return (
                DEBATE,
                f"{' and '.join(details)} — debate another round.",
            )
        return (
            DEBATE,
            f"Score {score:.0%} below finalize threshold "
            f"({cfg.finalize_threshold:.0%}) — debate another round.",
        )

    # ── Score factors ─────────────────────────────────────────────

    @staticmethod
    def _family_of(output: AgentOutput) -> str:
        """Family vote key: unknown family ⇒ each agent votes alone."""
        family = (output.family or "").strip()
        return family if family else f"__solo:{output.agent_id}"

    def _family_groups(self, outputs: list[AgentOutput]) -> dict[str, list]:
        groups: dict[str, list] = {}
        for o in outputs:
            groups.setdefault(self._family_of(o), []).append(o)
        return groups

    def _family_stances(
        self, outputs: list[AgentOutput]
    ) -> dict[tuple[str, str], str | None]:
        """Cross-family stance per ordered pair: support/disagree/None.

        Majority of member edges toward the other family's members wins;
        ties and silence are neutral. Same-family pairs are skipped: one
        family casts ONE vote, so internal agreement adds no signal.
        """
        groups = self._family_groups(outputs)
        stances: dict[tuple[str, str], str | None] = {}
        for fam_a, members_a in groups.items():
            for fam_b, members_b in groups.items():
                if fam_a == fam_b:
                    continue
                targets = {o.agent_id for o in members_b}
                supporting = sum(
                    1 for o in members_a for s in o.supports if s in targets
                )
                disagreeing = sum(
                    1 for o in members_a for d in o.disagrees_with if d in targets
                )
                if supporting > disagreeing:
                    stances[(fam_a, fam_b)] = "support"
                elif disagreeing > supporting:
                    stances[(fam_a, fam_b)] = "disagree"
                else:
                    stances[(fam_a, fam_b)] = None
        return stances

    def _calculate_agreement(self, outputs: list[AgentOutput]) -> float:
        """Pairwise agreement with one vote per model family (WORKFLOW 6.5)."""
        if len(outputs) <= 1:
            return 1.0
        decided = [
            stance
            for stance in self._family_stances(outputs).values()
            if stance is not None
        ]
        if decided:
            return sum(1 for s in decided if s == "support") / len(decided)
        # No explicit cross-family relations: share of the largest position
        # bloc, counted in family votes.
        groups = self._family_groups(outputs)
        representative = [members[0].position for members in groups.values()]
        top = Counter(representative).most_common(1)[0][1]
        return top / len(representative)

    def _calculate_confidence(self, outputs: list[AgentOutput]) -> float:
        """Mean calibrated confidence across all agents."""
        if not outputs:
            return 0.0
        return sum(o.calibrated_confidence for o in outputs) / len(outputs)

    def _calculate_evidence_quality(
        self,
        outputs: list[AgentOutput],
        verification: dict[str, bool] | None = None,
    ) -> float:
        """Claims with sources score best; bare claims still count.

        A claim the CitationManager cross-verified (2+ independent
        domains) adds +0.15, capped at +0.3 per output. Without a
        verification map the score is exactly the legacy value.
        """
        if not outputs:
            return 0.0
        scores = []
        for o in outputs:
            evidence_score = min(1.0, len(o.evidence) / 3)
            sourced = sum(1 for e in o.evidence if e.source_id) + len(o.sources)
            source_bonus = min(0.2, sourced * 0.05)
            cross_bonus = 0.0
            if verification:
                verified = sum(
                    1 for e in o.evidence if verification.get(e.claim) is True
                )
                cross_bonus = min(0.3, verified * 0.15)
            scores.append(min(1.0, evidence_score + source_bonus + cross_bonus))
        return sum(scores) / len(scores)

    def _calculate_new_information_rate(
        self,
        outputs: list[AgentOutput],
        round_number: int = 0,
    ) -> float:
        """Fraction of agents whose position changed since last round.

        Excludes agents whose call failed this round (Fix D): stale
        carry-forward output would fake stability and trigger premature
        consensus.
        """
        if not self._previous_positions:
            return 1.0  # First evaluation — all info is new

        changed = 0
        total = 0
        for o in outputs:
            if o.failed_round == round_number:
                logger.warning(
                    f"Consensus │ Excluding {o.agent_id} from new-info calculation "
                    f"(API failure in round {round_number})"
                )
                continue
            total += 1
            prev = self._previous_positions.get(o.agent_id, "")
            if not prev or prev != o.position:
                changed += 1

        return changed / total if total > 0 else 1.0

    def _calculate_contradiction_ratio(
        self, outputs: list[AgentOutput]
    ) -> float:
        """Share of ordered family pairs standing in disagreement."""
        if len(outputs) <= 1:
            return 0.0
        families = list(self._family_groups(outputs))
        total_pairs = len(families) * (len(families) - 1)
        if total_pairs == 0:
            return 0.0
        disagreeing = sum(
            1 for stance in self._family_stances(outputs).values()
            if stance == "disagree"
        )
        return disagreeing / total_pairs

    # ── Report helpers ────────────────────────────────────────────

    @staticmethod
    def _open_disagreements(outputs: list[AgentOutput]) -> list:
        """Every live disagree edge, with families attached for transparency."""
        return [
            {
                "agent_id": o.agent_id,
                "agent_type": o.agent_type,
                "family": o.family,
                "disagrees_with": list(o.disagrees_with),
                "position": o.position[:200],
            }
            for o in outputs
            if o.disagrees_with
        ]

    @staticmethod
    def _has_external_evidence(outputs: list[AgentOutput]) -> bool:
        """Any attached sources or source-linked claims (vs bare opinion)."""
        return any(
            o.sources or any(e.source_id for e in o.evidence) for o in outputs
        )

    @staticmethod
    def _positions_match(outputs: list[AgentOutput]) -> bool:
        """All agents literally hold the same position."""
        return len({o.position for o in outputs}) <= 1

    def reset(self):
        """Reset state for a new execution."""
        self._previous_positions.clear()
