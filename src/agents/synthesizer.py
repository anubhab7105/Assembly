"""
Assembly — Synthesizer Agent

Produces the final answer from the team's consensus.
The user never sees the debate — only this agent's output.
"""

from typing import Optional, Dict, Any, List

from src.agents.base_agent import BaseAgent, AgentOutput


class SynthesizerAgent(BaseAgent):
    """
    Synthesizer: produces the final user-facing answer from team consensus.
    
    Takes all agents' positions, the debate history, and consensus data
    to create a clear, comprehensive, well-sourced final answer.
    """

    agent_type = "synthesizer"

    def build_system_prompt(self) -> str:
        return """You are the Final Synthesizer on a multi-agent reasoning team called Assembly.

Your job is to produce the FINAL ANSWER that the user will see. The user never sees the agent debate — only YOUR output.

RULES:
1. Synthesize the team's best reasoning into one clear, comprehensive answer.
2. Prioritize positions with strong evidence and high confidence.
3. If agents disagreed, present the strongest position while acknowledging alternatives.
4. If consensus is weak, honestly state the uncertainty.
5. Include ONLY sources that were actually used and verified.
6. Write clearly and professionally — this is what the user reads.
7. Present the answer as a direct expert response.
8. Do NOT include any footer or metadata about agents — that will be added automatically.

You MUST respond with a JSON object in this exact format:
```json
{
    "position": "The comprehensive final answer (can be multiple paragraphs, use \\n for line breaks)",
    "confidence": 0.90,
    "reasoning": "Brief internal note on synthesis approach (not shown to user)",
    "evidence": ["Key evidence points incorporated"],
    "sources": [{"title": "Source name", "url": "URL", "snippet": "Why this source is relevant"}],
    "remaining_uncertainty": ["Any honest caveats the user should know"]
}
```"""

    def build_user_prompt(self, question: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not context:
            return question

        # Build comprehensive context from all agent outputs and debate history
        agent_outputs = context.get("agent_outputs", [])
        consensus_score = context.get("consensus_score", 0.0)
        debate_rounds = context.get("debate_rounds", 0)
        all_sources = context.get("all_sources", [])

        agents_text = ""
        for o in agent_outputs:
            agents_text += f"\n--- {o.get('agent_type', 'Unknown').title()} (confidence: {o.get('confidence', 0):.0%}) ---\n"
            agents_text += f"Position: {o.get('position', 'N/A')}\n"
            evidence = o.get("evidence", [])
            if evidence:
                agents_text += f"Evidence: {'; '.join(evidence)}\n"
            uncertainty = o.get("remaining_uncertainty", [])
            if uncertainty:
                agents_text += f"Uncertainty: {'; '.join(uncertainty)}\n"

        sources_text = ""
        if all_sources:
            sources_text = "\n\nAVAILABLE SOURCES:\n"
            for s in all_sources:
                sources_text += f"- {s.get('title', 'Unknown')}: {s.get('url', 'N/A')} — {s.get('snippet', '')}\n"

        return f"""SYNTHESIZE THE FINAL ANSWER

Original question: {question}

Team consensus score: {consensus_score:.0%}
Debate rounds completed: {debate_rounds}

Agent findings:
{agents_text}
{sources_text}

Create the best possible final answer for the user. Remember:
- The user sees ONLY your answer, not the debate.
- Write as a direct expert response, not as a summary of agent discussion.
- Include relevant sources in your response.
- If consensus was weak, be honest about uncertainty.

Respond with the JSON format specified in your instructions."""

    async def synthesize(
        self,
        question: str,
        agent_outputs: List[AgentOutput],
        consensus_score: float,
        debate_rounds: int,
        providers_used: List[str] = None,
    ) -> AgentOutput:
        """
        Convenience method for final synthesis.
        Collects all sources and agent data into context.
        Appends agent attribution footer to the final answer.
        """
        all_sources = []
        for output in agent_outputs:
            all_sources.extend(output.sources)

        # Deduplicate sources by URL
        seen_urls = set()
        unique_sources = []
        for s in all_sources:
            url = s.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_sources.append(s)
            elif not url:
                unique_sources.append(s)

        context = {
            "agent_outputs": [o.to_dict() for o in agent_outputs],
            "consensus_score": consensus_score,
            "debate_rounds": debate_rounds,
            "all_sources": unique_sources,
        }

        result = await self.run(question, context=context, temperature=0.3)

        # Append attribution footer
        agent_count = len(agent_outputs)
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

        footer = f"\n\n---\n\U0001F916 This answer was assembled by {agent_count} AI agents powered by {providers_str}."
        result.position = result.position + footer

        return result
