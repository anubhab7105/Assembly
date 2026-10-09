"""
Assembly — Critic Agent

Dedicated adversarial agent that finds flaws, challenges assumptions,
and prevents echo chambers (PRD Section 10).
"""

from typing import Any

from src.agents.base_agent import AgentOutput, BaseAgent
from src.research.sanitize import UNTRUSTED_SYSTEM_NOTE


class CriticAgent(BaseAgent):
    """
    Critic: actively searches for flaws and challenges the consensus.
    
    Critical for preventing AI echo chambers where models blindly
    agree with each other (cascading trust problem).
    """

    agent_type = "critic"

    def build_system_prompt(self) -> str:
        role = self.role_description or "Critical Analyst and Devil's Advocate"
        prompt = f"""You are an expert {role} on a multi-agent reasoning team called Assembly.

Your CRITICAL role is to find flaws, challenge assumptions, and prevent groupthink.

YOUR MINDSET:
- "What could everyone here be wrong about?"
- "What evidence would disprove the current consensus?"
- "Are we suffering from cascading trust — one agent wrong, everyone else following?"
- "What are the strongest counterarguments?"

RULES:
1. ACTIVELY look for errors, weak reasoning, and unsupported claims.
2. Challenge popular opinions — don't just agree with the majority.
3. Identify logical fallacies, missing context, and hidden assumptions.
4. Propose alternative perspectives that haven't been considered.
5. If everyone agrees, try harder to find what they might all be wrong about.
6. But if the evidence genuinely supports the consensus, say so honestly.
7. State your confidence level honestly as a number 0.0 to 1.0.
8. Report only a SHORT reasoning_summary (2-4 sentences) — never dump a long chain-of-thought.
9. In the independent round you have seen no other agents: leave "supports" and "disagrees_with" empty.

You MUST respond with a JSON object in this exact format (no extra keys):
```json
{{
    "position": "Your critical assessment and conclusion",
    "reasoning_summary": "Why you challenge or support the current positions (2-4 sentences)",
    "confidence": 0.75,
    "evidence": [{{"claim": "Counter-evidence or supporting evidence", "source_id": ""}}],
    "supports": ["agent_ids whose reasoning holds up"],
    "disagrees_with": ["agent_ids with flawed reasoning"],
    "remaining_uncertainty": ["Critical unknowns that affect the answer"]
}}
```"""
        return prompt + "\n\n" + UNTRUSTED_SYSTEM_NOTE

    def build_user_prompt(self, question: str, context: dict[str, Any] | None = None) -> str:
        if context and context.get("mode") == "adversarial":
            return self._build_adversarial_prompt(
                question,
                context.get("other_outputs", []),
                context.get("round_number", 1),
                context.get("valid_agent_ids", []),
            )
        if context and context.get("mode") == "critique":
            other_outputs = context.get("other_outputs", [])
            round_num = context.get("round_number", 1)
            valid_ids = context.get("valid_agent_ids", [])

            others_text = ""
            for o in other_outputs:
                claims = "; ".join(
                    e.get("claim", "") if isinstance(e, dict) else str(e)
                    for e in o.get("evidence", [])
                )
                others_text += f"\n--- Agent {o['agent_id']} ({o['agent_type']}) ---\n"
                others_text += f"Position: {o['position']}\n"
                others_text += f"Confidence: {o['confidence']}\n"
                others_text += f"Reasoning summary: {o.get('reasoning_summary', 'N/A')}\n"
                others_text += f"Evidence: {claims}\n"

            valid_ids_str = ", ".join(f'"{aid}"' for aid in valid_ids)

            return f"""CRITIQUE ROUND {round_num}

Original question: {question}

Other agents' conclusions:
{others_text}

VALID AGENT IDs you may reference: [{valid_ids_str}]
You MUST use ONLY these exact IDs in your "supports" and "disagrees_with" arrays.

As the Critic, you MUST:
1. Identify the WEAKEST arguments and evidence among all agents.
2. Find at least ONE flaw or questionable assumption (if any exist).
3. Check for cascading trust — are agents agreeing because of evidence, or just copying each other?
4. Propose the STRONGEST counterargument to the current consensus.
5. If the consensus is genuinely strong, acknowledge it but note remaining risks.

Respond with the JSON format specified in your instructions."""

        # First round: independent critical analysis
        return f"""Analyze this question with a critical, skeptical lens.

Question: {question}

Consider:
- What are the common misconceptions about this topic?
- What would a devil's advocate argue?
- What evidence would be needed to give a truly confident answer?
- What are the strongest counterarguments to the obvious answer?

Respond with the JSON format specified in your instructions."""

    @staticmethod
    def _build_adversarial_prompt(
        question: str,
        other_outputs: list,
        round_num: int,
        valid_ids: list,
    ) -> str:
        """The WORKFLOW 6.4 strike: assume the consensus is wrong."""
        others_text = ""
        for o in other_outputs:
            claims = "; ".join(
                e.get("claim", "") if isinstance(e, dict) else str(e)
                for e in o.get("evidence", [])
            )
            others_text += f"\n--- Agent {o['agent_id']} ({o['agent_type']}) ---\n"
            others_text += f"Position: {o['position']}\n"
            others_text += f"Confidence: {o['confidence']}\n"
            others_text += f"Evidence: {claims}\n"

        valid_ids_str = ", ".join(f'"{aid}"' for aid in valid_ids)

        return f"""ADVERSARIAL CHALLENGE — round {round_num}

Assume the current consensus is wrong. Give the strongest counterargument and what would prove it.

Original question: {question}

Current consensus positions:
{others_text}

VALID AGENT IDs you may reference: [{valid_ids_str}]
You MUST use ONLY these exact IDs in your "supports" and "disagrees_with" arrays.

You are attacking the consensus, not defending it:
1. Steelman the opposite of the current consensus position.
2. Name the single weakest assumption holding the consensus together.
3. State exactly what evidence would prove the consensus wrong.
4. Give your counter-position and honest confidence in it.

Respond with JSON only, no extra keys, in the format specified in your instructions."""

    async def adversarial_challenge(
        self,
        question: str,
        other_outputs: list[AgentOutput],
        round_number: int,
    ) -> AgentOutput:
        """Assume the consensus is wrong; counterargue (WORKFLOW 5b).

        Same validation contract as critique (Fix B ID-stripping included).
        """
        valid_agent_ids = [o.agent_id for o in other_outputs]
        context = {
            "round_number": round_number,
            "other_outputs": [o.to_dict() for o in other_outputs],
            "valid_agent_ids": valid_agent_ids,
            "mode": "adversarial",
        }
        output = await self.run(question, context=context)

        all_valid = set(valid_agent_ids + [self.agent_id])
        output.supports = [aid for aid in output.supports if aid in all_valid]
        output.disagrees_with = [
            aid for aid in output.disagrees_with if aid in all_valid
        ]

        return output
