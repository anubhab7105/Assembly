"""
Assembly — Solver Agent

Independent problem-solving agent that produces a solution
with reasoning and evidence before seeing other agents' work.
"""

from typing import Optional, Dict, Any

from src.agents.base_agent import BaseAgent
from src.research.sanitize import UNTRUSTED_SYSTEM_NOTE


class SolverAgent(BaseAgent):
    """
    Solver: independently analyzes and solves the problem.
    
    In the first round, works without seeing other agents' outputs
    to prevent groupthink (PRD Section 6.1).
    """

    agent_type = "solver"

    def build_system_prompt(self) -> str:
        role = self.role_description or "Problem Solver and Analyst"
        prompt = f"""You are an expert {role} on a multi-agent reasoning team called Assembly.

Your job is to independently analyze and solve the given problem with rigorous reasoning.

RULES:
1. Think step-by-step, but report only a SHORT reasoning_summary (2-4 sentences) — never dump a long chain-of-thought.
2. Provide evidence for every claim as objects with "claim" and "source_id" (source_id may be "" when unknown).
3. State your confidence level honestly as a number 0.0 to 1.0.
4. Identify any uncertainties or assumptions.
5. If you're unsure, say so — don't fabricate confidence.
6. In the independent round you have seen no other agents: leave "supports" and "disagrees_with" empty.

You MUST respond with a JSON object in this exact format (no extra keys):
```json
{{
    "position": "Your clear conclusion/answer to the question",
    "reasoning_summary": "Brief summary of your key reasoning (2-4 sentences, no chain-of-thought)",
    "confidence": 0.85,
    "evidence": [{{"claim": "Evidence point 1", "source_id": ""}}],
    "supports": [],
    "disagrees_with": [],
    "remaining_uncertainty": ["What you're still unsure about"]
}}
```"""
        return prompt + "\n\n" + UNTRUSTED_SYSTEM_NOTE

    def build_user_prompt(self, question: str, context: Optional[Dict[str, Any]] = None) -> str:
        if context and context.get("mode") == "critique":
            # Debate mode: review others' work
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
                others_text += f"Evidence: {claims}\n"

            valid_ids_str = ", ".join(f'"{aid}"' for aid in valid_ids)

            return f"""DEBATE ROUND {round_num}

Original question: {question}

Other agents' conclusions:
{others_text}

VALID AGENT IDs you may reference: [{valid_ids_str}]
You MUST use ONLY these exact IDs in your "supports" and "disagrees_with" arrays.

Review the other agents' work. For each:
1. Do you agree or disagree? Why?
2. Did they miss anything important?
3. Is their evidence sufficient?
4. Are there better approaches?

Update your own position based on this review. Respond with JSON only, no extra keys:
```json
{{
    "position": "Your updated conclusion",
    "reasoning_summary": "Brief summary of why you updated (or maintained) your position",
    "confidence": 0.0-1.0,
    "evidence": [{{"claim": "Your evidence", "source_id": ""}}],
    "supports": ["agent_ids you agree with"],
    "disagrees_with": ["agent_ids you disagree with"],
    "remaining_uncertainty": ["What's still unclear"]
}}
```"""

        # First round: independent solving
        return f"""Solve this problem independently. Think carefully and provide a thorough answer.

Question: {question}

Respond with the JSON format specified in your instructions."""
