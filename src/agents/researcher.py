"""
Assembly — Researcher Agent

Gathers evidence, performs web research, and provides
evidence-backed analysis.
"""

from typing import Optional, Dict, Any

from src.agents.base_agent import BaseAgent


class ResearcherAgent(BaseAgent):
    """
    Researcher: gathers evidence and provides research-backed analysis.
    
    Can incorporate web search results when available.
    """

    agent_type = "researcher"

    def build_system_prompt(self) -> str:
        role = self.role_description or "Research Analyst"
        return f"""You are an expert {role} on a multi-agent reasoning team called Assembly.

Your job is to research the question thoroughly, gather evidence, and provide well-sourced analysis.

RULES:
1. Focus on EVIDENCE and FACTS, not opinions.
2. Cite sources when possible (even from your training data).
3. Distinguish between well-established facts and uncertain claims.
4. Consider multiple perspectives and viewpoints.
5. Rate source credibility when citing information.
6. State your confidence level honestly (0.0 to 1.0).

You MUST respond with a JSON object in this exact format:
```json
{{
    "position": "Your evidence-based conclusion",
    "confidence": 0.80,
    "reasoning": "How the evidence supports your conclusion",
    "evidence": ["Key evidence point 1 with source", "Key evidence point 2 with source"],
    "remaining_uncertainty": ["Areas where evidence is insufficient"],
    "sources": [{{"title": "Source name", "url": "URL if available", "snippet": "Relevant excerpt"}}]
}}
```"""

    def build_user_prompt(self, question: str, context: Optional[Dict[str, Any]] = None) -> str:
        # Check for web search results in context
        web_results = ""
        if context and context.get("search_results"):
            web_results = "\n\nWEB SEARCH RESULTS:\n"
            for i, result in enumerate(context["search_results"], 1):
                web_results += f"\n[{i}] {result.get('title', 'Unknown')}\n"
                web_results += f"    URL: {result.get('url', '')}\n"
                web_results += f"    {result.get('snippet', '')}\n"

        if context and context.get("mode") == "critique":
            other_outputs = context.get("other_outputs", [])
            round_num = context.get("round_number", 1)

            others_text = ""
            for o in other_outputs:
                others_text += f"\n--- Agent {o['agent_id']} ({o['agent_type']}) ---\n"
                others_text += f"Position: {o['position']}\n"
                others_text += f"Confidence: {o['confidence']}\n"
                others_text += f"Evidence: {', '.join(o.get('evidence', []))}\n"

            return f"""DEBATE ROUND {round_num}

Original question: {question}
{web_results}

Other agents' conclusions:
{others_text}

As the Researcher, evaluate:
1. Is the evidence cited by other agents accurate and sufficient?
2. Are there missing sources or contradicting evidence?
3. What additional research would strengthen or weaken their claims?
4. Update your position with the strongest available evidence.

Respond with the JSON format specified in your instructions. Include 'supports' and 'disagrees_with' arrays with agent IDs."""

        return f"""Research this question thoroughly and provide an evidence-based analysis.
{web_results}
Question: {question}

Respond with the JSON format specified in your instructions."""
