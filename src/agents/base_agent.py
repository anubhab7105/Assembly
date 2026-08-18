"""
Assembly — Base Agent

Foundation class for all agents. Handles provider interaction,
structured output parsing, and the common agent lifecycle.
"""

import json
import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from src.providers.base import AIProvider, ChatMessage, ProviderResponse
from src.core.logging_config import logger


@dataclass
class AgentOutput:
    """
    Structured output from any agent.
    
    Every agent must return this format so the consensus engine
    can evaluate agreement, evidence quality, and confidence.
    """
    agent_id: str
    agent_type: str
    position: str  # The agent's conclusion / answer
    confidence: float  # 0.0 to 1.0
    evidence: List[str] = field(default_factory=list)
    reasoning: str = ""
    supports: List[str] = field(default_factory=list)  # agent_ids this agent agrees with
    disagrees_with: List[str] = field(default_factory=list)  # agent_ids this agent disagrees with
    remaining_uncertainty: List[str] = field(default_factory=list)
    sources: List[Dict[str, str]] = field(default_factory=list)  # [{url, title, snippet}]
    raw_content: str = ""  # Full LLM response for debugging
    tokens_used: int = 0  # Total tokens consumed by this agent call

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "position": self.position,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "reasoning": self.reasoning,
            "supports": self.supports,
            "disagrees_with": self.disagrees_with,
            "remaining_uncertainty": self.remaining_uncertainty,
            "sources": self.sources,
        }


class BaseAgent:
    """
    Abstract base for all Assembly agents.
    
    Subclasses override build_system_prompt() and build_user_prompt()
    to customize behavior. The solve/critique/synthesize lifecycle
    is handled by the orchestrator.
    """

    agent_type: str = "base"

    def __init__(
        self,
        agent_id: str,
        provider: AIProvider,
        model: str,
        role_description: str = "",
    ):
        self.agent_id = agent_id
        self.provider = provider
        self.model = model
        self.role_description = role_description

    def build_system_prompt(self) -> str:
        """Build the system prompt for this agent type. Override in subclasses."""
        return "You are a helpful AI assistant."

    def build_user_prompt(self, question: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Build the user prompt. Override in subclasses."""
        return question

    async def run(
        self,
        question: str,
        context: Optional[Dict[str, Any]] = None,
        temperature: float = 0.2,
    ) -> AgentOutput:
        """
        Execute this agent: call the provider and parse the structured response.
        """
        system_prompt = self.build_system_prompt()
        user_prompt = self.build_user_prompt(question, context)

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]

        logger.info(f"Agent   │ {self.agent_id} ({self.agent_type}) → running on {self.model}")

        response = await self.provider.generate(
            messages=messages,
            model=self.model,
            temperature=temperature,
        )

        output = self._parse_response(response)
        output.tokens_used = response.total_tokens
        logger.info(
            f"Agent   │ {self.agent_id} → confidence: {output.confidence:.0%}, "
            f"tokens: {response.total_tokens}"
        )
        return output

    def _parse_response(self, response: ProviderResponse) -> AgentOutput:
        """
        Parse the LLM response into an AgentOutput.
        Uses a robust JSON extractor that handles:
        - Raw JSON responses (no code fences)
        - Any markdown code fence language (```json, ```javascript, ```, etc.)
        - JSON embedded in surrounding text
        - Nested JSON objects
        """
        content = response.content.strip()
        json_str = self._extract_json(content)

        if json_str:
            try:
                data = json.loads(json_str)

                return AgentOutput(
                    agent_id=self.agent_id,
                    agent_type=self.agent_type,
                    position=data.get("position", data.get("answer", data.get("conclusion", ""))),
                    confidence=float(data.get("confidence", 0.7)),
                    evidence=data.get("evidence", []),
                    reasoning=data.get("reasoning", ""),
                    supports=data.get("supports", []),
                    disagrees_with=data.get("disagrees_with", []),
                    remaining_uncertainty=data.get("remaining_uncertainty", []),
                    sources=data.get("sources", []),
                    raw_content=content,
                )
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Agent   │ {self.agent_id} — JSON decode failed after extraction: {e}")

        # Fallback: treat entire response as the position
        logger.warning(f"Agent   │ {self.agent_id} — No valid JSON found, using text fallback")
        return AgentOutput(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            position=content,
            confidence=0.6,
            reasoning=content,
            raw_content=content,
        )

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """
        Robustly extract a JSON object string from LLM output.

        Strategy:
        1. Strip markdown code fences of any language (```json, ```python, etc.)
        2. Find the first '{' character
        3. Walk forward, tracking brace depth, to find the matching '}'
        4. Return the substring as the candidate JSON

        Returns None if no valid JSON object structure is found.
        """
        # Step 1: Strip markdown code fences (handles ```json, ```javascript, ``` etc.)
        stripped = re.sub(r'```\w*\s*', '', text)
        stripped = stripped.replace('```', '').strip()

        # Step 2: Find the first '{' — start of JSON object
        start = stripped.find('{')
        if start == -1:
            return None

        # Step 3: Walk forward tracking brace depth to find the matching '}'
        depth = 0
        in_string = False
        escape_next = False

        for i in range(start, len(stripped)):
            char = stripped[i]

            if escape_next:
                escape_next = False
                continue

            if char == '\\' and in_string:
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    return stripped[start:i + 1]

        return None

    # ── Convenience for debate rounds ────────────────────────────────

    async def critique(
        self,
        question: str,
        other_outputs: List[AgentOutput],
        round_number: int,
    ) -> AgentOutput:
        """
        Review other agents' outputs and produce critique.
        Used during debate rounds.
        """
        valid_agent_ids = [o.agent_id for o in other_outputs]
        context = {
            "round_number": round_number,
            "other_outputs": [o.to_dict() for o in other_outputs],
            "valid_agent_ids": valid_agent_ids,
            "mode": "critique",
        }
        output = await self.run(question, context=context)

        # Validate referential integrity: strip hallucinated agent IDs
        all_valid = set(valid_agent_ids + [self.agent_id])
        output.supports = [aid for aid in output.supports if aid in all_valid]
        output.disagrees_with = [aid for aid in output.disagrees_with if aid in all_valid]

        return output
