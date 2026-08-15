"""
Assembly — Consensus Engine

Evaluates structured agent outputs and calculates consensus score
based on agreement, evidence quality, confidence, contradictions,
and new-information rate (PRD Section 9).
"""

from typing import List, Dict, Optional
from dataclasses import dataclass

from src.agents.base_agent import AgentOutput
from src.core.logging_config import logger


@dataclass
class ConsensusResult:
    """Result of a consensus evaluation."""
    score: float  # 0.0 to 1.0
    decision: str  # "continue" | "finalize" | "timeout"
    agreement_count: int
    disagreement_count: int
    average_confidence: float
    new_information_rate: float  # How much new info was added this round
    reasoning: str

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 3),
            "decision": self.decision,
            "agreement_count": self.agreement_count,
            "disagreement_count": self.disagreement_count,
            "average_confidence": round(self.average_confidence, 3),
            "new_information_rate": round(self.new_information_rate, 3),
            "reasoning": self.reasoning,
        }


class ConsensusEngine:
    """
    Evaluates whether the agent team has reached sufficient consensus.
    
    This is an actual Consensus Controller, not just a final LLM call (PRD Section 9).
    
    Stopping algorithm (PRD Section 24):
    - Consensus > 90% AND new information < threshold AND no major contradiction → FINALIZE
    - Otherwise → CONTINUE
    - Near deadline → force FINALIZE
    """

    # Thresholds
    CONSENSUS_THRESHOLD = 0.85  # Score above which we consider finalizing
    HIGH_CONSENSUS_THRESHOLD = 0.92  # Strong consensus — can finalize early
    NEW_INFO_THRESHOLD = 0.15  # Below this, little new info is being produced
    MIN_CONFIDENCE_THRESHOLD = 0.5  # Minimum average confidence to finalize

    def __init__(self):
        self._previous_positions: Dict[str, str] = {}  # agent_id → previous position

    def evaluate(
        self,
        outputs: List[AgentOutput],
        round_number: int,
        force_finalize: bool = False,
    ) -> ConsensusResult:
        """
        Evaluate consensus across agent outputs.
        
        Args:
            outputs: Current round's agent outputs.
            round_number: Current debate round.
            force_finalize: If True, force finalization (time budget expired).
        """
        if not outputs:
            return ConsensusResult(
                score=0.0,
                decision="continue",
                agreement_count=0,
                disagreement_count=0,
                average_confidence=0.0,
                new_information_rate=1.0,
                reasoning="No agent outputs to evaluate.",
            )

        # ── Calculate component scores ───────────────────────────────
        agreement_score = self._calculate_agreement(outputs)
        confidence_score = self._calculate_confidence(outputs)
        evidence_score = self._calculate_evidence_quality(outputs)
        new_info_rate = self._calculate_new_information_rate(outputs)
        contradiction_score = self._calculate_contradictions(outputs)

        # ── Weighted composite score ─────────────────────────────────
        # Agreement matters most, followed by evidence quality
        composite = (
            agreement_score * 0.35
            + confidence_score * 0.20
            + evidence_score * 0.20
            + (1 - contradiction_score) * 0.15  # Lower contradictions = higher score
            + (1 - new_info_rate) * 0.10  # Lower new info rate = more stable = higher
        )

        # Count agreements/disagreements
        agreement_count = sum(len(o.supports) for o in outputs)
        disagreement_count = sum(len(o.disagrees_with) for o in outputs)

        avg_confidence = sum(o.confidence for o in outputs) / len(outputs)

        # ── Decision logic (PRD Section 24) ──────────────────────────
        decision, reasoning = self._make_decision(
            composite, avg_confidence, new_info_rate,
            contradiction_score, round_number, force_finalize,
        )

        # Update position history for next round's new-info calculation
        for o in outputs:
            self._previous_positions[o.agent_id] = o.position

        result = ConsensusResult(
            score=composite,
            decision=decision,
            agreement_count=agreement_count,
            disagreement_count=disagreement_count,
            average_confidence=avg_confidence,
            new_information_rate=new_info_rate,
            reasoning=reasoning,
        )

        logger.info(
            f"Consensus │ Round {round_number}: score={composite:.0%}, "
            f"decision={decision}, agreements={agreement_count}, "
            f"disagreements={disagreement_count}"
        )

        return result

    def _calculate_agreement(self, outputs: List[AgentOutput]) -> float:
        """
        Calculate how much agents agree with each other.
        Based on supports/disagrees_with lists and position similarity.
        """
        if len(outputs) <= 1:
            return 1.0

        total_relations = 0
        agreements = 0

        for output in outputs:
            total_relations += len(output.supports) + len(output.disagrees_with)
            agreements += len(output.supports)

        if total_relations == 0:
            # No explicit agreement/disagreement — estimate from confidence
            avg_confidence = sum(o.confidence for o in outputs) / len(outputs)
            return avg_confidence * 0.7  # Conservative estimate

        return agreements / total_relations

    def _calculate_confidence(self, outputs: List[AgentOutput]) -> float:
        """Average confidence across all agents."""
        if not outputs:
            return 0.0
        return sum(o.confidence for o in outputs) / len(outputs)

    def _calculate_evidence_quality(self, outputs: List[AgentOutput]) -> float:
        """
        Score evidence quality based on:
        - Number of evidence points
        - Whether sources are cited
        """
        if not outputs:
            return 0.0

        scores = []
        for o in outputs:
            evidence_count = len(o.evidence)
            source_count = len(o.sources)
            # More evidence = better, with diminishing returns
            evidence_score = min(1.0, evidence_count / 3)
            source_bonus = min(0.2, source_count * 0.05)
            scores.append(min(1.0, evidence_score + source_bonus))

        return sum(scores) / len(scores)

    def _calculate_new_information_rate(self, outputs: List[AgentOutput]) -> float:
        """
        Estimate how much new information was produced this round
        compared to previous rounds.
        
        Low rate = positions have stabilized = closer to consensus.
        """
        if not self._previous_positions:
            return 1.0  # First round — all info is new

        changed = 0
        total = 0

        for o in outputs:
            total += 1
            prev = self._previous_positions.get(o.agent_id, "")
            if not prev or prev != o.position:
                changed += 1

        return changed / total if total > 0 else 1.0

    def _calculate_contradictions(self, outputs: List[AgentOutput]) -> float:
        """
        Score how many contradictions exist between agents.
        Higher = more contradictions = less consensus.
        """
        if len(outputs) <= 1:
            return 0.0

        total_disagreements = sum(len(o.disagrees_with) for o in outputs)
        max_possible = len(outputs) * (len(outputs) - 1)

        return total_disagreements / max_possible if max_possible > 0 else 0.0

    def _make_decision(
        self,
        score: float,
        avg_confidence: float,
        new_info_rate: float,
        contradiction_score: float,
        round_number: int,
        force_finalize: bool,
    ) -> tuple[str, str]:
        """
        Make the stop/continue decision.
        
        Returns (decision, reasoning) tuple.
        """
        if force_finalize:
            return "finalize", "Time budget expired — forcing final synthesis."

        # Strong consensus — finalize
        if (
            score >= self.HIGH_CONSENSUS_THRESHOLD
            and new_info_rate < self.NEW_INFO_THRESHOLD
            and avg_confidence >= self.MIN_CONFIDENCE_THRESHOLD
        ):
            return "finalize", (
                f"Strong consensus reached (score={score:.0%}). "
                f"Positions have stabilized (new info rate={new_info_rate:.0%})."
            )

        # Good consensus with diminishing returns
        if (
            score >= self.CONSENSUS_THRESHOLD
            and new_info_rate < self.NEW_INFO_THRESHOLD * 1.5
            and contradiction_score < 0.2
            and round_number >= 2
        ):
            return "finalize", (
                f"Good consensus (score={score:.0%}) with minimal new information. "
                f"Contradictions low ({contradiction_score:.0%})."
            )

        # Still improving — continue
        return "continue", (
            f"Consensus not yet sufficient (score={score:.0%}). "
            f"New info rate={new_info_rate:.0%}, contradictions={contradiction_score:.0%}."
        )

    def reset(self):
        """Reset state for a new execution."""
        self._previous_positions.clear()
