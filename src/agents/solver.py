"""
Assembly — Solver Agent

Independent problem-solving agent that produces a solution
with reasoning and evidence before seeing other agents' work.
"""

from typing import Optional, Dict, Any

from src.agents.base_agent import BaseAgent


class SolverAgent(BaseAgent):
    """
    Solver: independently analyzes and solves the problem.
    
    In the first round, works without seeing other agents' outputs
    to prevent groupthink (PRD Section 6.1).
    """

    agent_type = "solver"

    def build_system_prompt(self) -> str:
        role = self.role_description or "Problem Solver and Analyst"
        return f"""You are an expert {role} on a multi-agent reasoning team called Assembly.

Your job is to independently analyze and solve the given problem with rigorous reasoning.

RULES:
1. Think step-by-step and show your reasoning clearly.
2. Provide evidence and justification for every claim.
3. State your confidence level honestly (0.0 to 1.0).
4. Identify any uncertainties or assumptions.
5. If you're unsure, say so — don't fabricate confidence.

You MUST respond with a JSON object in this exact format:
```json
{{
    "position": "Your clear conclusion/answer to the question",
    "confidence": 0.85,
    "reasoning": "Step-by-step explanation of how you arrived at your answer",
    "evidence": ["Evidence point 1", "Evidence point 2"],
    "remaining_uncertainty": ["What you're still unsure about"],
    "sources": []
}}
```"""

    def build_user_prompt(self, question: str, context: Optional[Dict[str, Any]] = None) -> str:
        if context and context.get("mode") == "critique":
            # Debate mode: review others' work
            other_outputs = context.get("other_outputs", [])
            round_num = context.get("round_number", 1)
            valid_ids = context.get("valid_agent_ids", [])

            others_text = ""
            for o in other_outputs:
                others_text += f"\n--- Agent {o['agent_id']} ({o['agent_type']}) ---\n"
                others_text += f"Position: {o['position']}\n"
                others_text += f"Confidence: {o['confidence']}\n"
                others_text += f"Evidence: {', '.join(o.get('evidence', []))}\n"

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

Update your own position based on this review. Respond with JSON:
```json
{{
    "position": "Your updated conclusion",
    "confidence": 0.0-1.0,
    "reasoning": "Why you updated (or maintained) your position",
    "evidence": ["Your evidence"],
    "supports": ["agent_ids you agree with"],
    "disagrees_with": ["agent_ids you disagree with"],
    "remaining_uncertainty": ["What's still unclear"]
}}
```"""

        # First round: independent solving
        return f"""Solve this problem independently. Think carefully and provide a thorough answer.

Question: {question}

Respond with the JSON format specified in your instructions."""
