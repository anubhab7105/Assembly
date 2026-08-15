"""
Assembly — Critic Agent

Dedicated adversarial agent that finds flaws, challenges assumptions,
and prevents echo chambers (PRD Section 10).
"""

from typing import Optional, Dict, Any

from src.agents.base_agent import BaseAgent


class CriticAgent(BaseAgent):
    """
    Critic: actively searches for flaws and challenges the consensus.
    
    Critical for preventing AI echo chambers where models blindly
    agree with each other (cascading trust problem).
    """

    agent_type = "critic"

    def build_system_prompt(self) -> str:
        role = self.role_description or "Critical Analyst and Devil's Advocate"
        return f"""You are an expert {role} on a multi-agent reasoning team called Assembly.

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
7. State your confidence level honestly (0.0 to 1.0).

You MUST respond with a JSON object in this exact format:
```json
{{
    "position": "Your critical assessment and conclusion",
    "confidence": 0.75,
    "reasoning": "Why you challenge or support the current positions",
    "evidence": ["Counter-evidence or supporting evidence"],
    "supports": ["agent_ids whose reasoning holds up"],
    "disagrees_with": ["agent_ids with flawed reasoning"],
    "remaining_uncertainty": ["Critical unknowns that affect the answer"],
    "sources": []
}}
```"""

    def build_user_prompt(self, question: str, context: Optional[Dict[str, Any]] = None) -> str:
        if context and context.get("mode") == "critique":
            other_outputs = context.get("other_outputs", [])
            round_num = context.get("round_number", 1)

            others_text = ""
            for o in other_outputs:
                others_text += f"\n--- Agent {o['agent_id']} ({o['agent_type']}) ---\n"
                others_text += f"Position: {o['position']}\n"
                others_text += f"Confidence: {o['confidence']}\n"
                others_text += f"Reasoning: {o.get('reasoning', 'N/A')}\n"
                others_text += f"Evidence: {', '.join(o.get('evidence', []))}\n"

            return f"""CRITIQUE ROUND {round_num}

Original question: {question}

Other agents' conclusions:
{others_text}

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
