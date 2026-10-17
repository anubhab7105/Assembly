"""
Assembly — Base Agent

Foundation class for all agents. Handles provider interaction,
strict structured-output validation, and the common agent lifecycle.

Validation pipeline (AGENTS.md section 4):
  1. Parse with the robust _extract_json extractor (preserved).
  2. Validate against the strict AgentOutput schema (unknown keys rejected).
  3. Validate agent IDs in supports/disagrees_with (Fix B: strip unknown IDs).
  4. On failure: retry ONCE with the validation error appended.
  5. Still failing: fall back to another family via the router.
  6. Still failing: raise AgentValidationError (the manager converts it
     into a low-confidence error output; debate carries forward stale output).

Independent solve (PRD Section 6.1): run() with no critique context never
sees other agents' answers — prompts are built from the question alone.
"""

import json
import math
import re
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.core.logging_config import logger
from src.providers.base import AIProvider, ChatMessage, ProviderResponse
from src.research.sanitize import UNTRUSTED_SYSTEM_NOTE

# reasoning_summary is a short digest, never a dumped chain-of-thought.
# Longer text is truncated (not a retryable error) to avoid burning retries.
MAX_REASONING_SUMMARY_CHARS = 2000


class AgentValidationError(Exception):
    """An agent reply failed strict validation on every attempt.

    Raised after: initial parse/validate, one retry with the error
    appended, and one fallback-family attempt (when a router is attached).
    Callers (manager, debate) convert this into error/carry-forward output.
    """


class EvidenceItem(BaseModel):
    """One verifiable claim plus where it came from."""

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1)
    source_id: str = ""


class SourceRef(BaseModel):
    """One citable source (researcher/synthesizer use)."""

    model_config = ConfigDict(extra="forbid")

    title: str = ""
    url: str = ""
    snippet: str = ""


class AgentOutput(BaseModel):
    """Strict structured output from any agent.

    The first block is the LLM contract (validated strictly: unknown keys
    are rejected). The second block is per-call provenance recorded by
    run() — never taken from the model. consensus reads confidence, which
    is always the calibrated (clamped) value; the raw model value is kept
    in confidence_raw for calibration analysis.
    """

    model_config = ConfigDict(extra="forbid")

    # Identity (filled by the agent, not the model)
    agent_id: str = ""
    agent_type: str = ""

    # Strict LLM contract
    position: str = Field(min_length=1)
    reasoning_summary: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    supports: list[str] = Field(default_factory=list)
    disagrees_with: list[str] = Field(default_factory=list)
    remaining_uncertainty: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)

    # Per-call provenance (recorded by run(), never from the model)
    provider: str = ""
    model: str = ""
    family: str = ""
    tokens_used: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    confidence_raw: float | None = None
    raw_content: str = ""
    failed_round: int | None = None  # debate carry-forward bookkeeping (Fix D)

    @property
    def calibrated_confidence(self) -> float:
        """Confidence value the consensus engine must use (always clamped)."""
        return self.confidence

    def to_dict(self) -> dict:
        """JSON-safe view for workspace events and critique context."""
        data = self.model_dump()
        data.pop("raw_content", None)  # large debug blob; kept off the event bus
        return data

    @staticmethod
    def calibrate_confidence(raw: Any) -> tuple[float, float]:
        """Clamp a model-stated confidence into [0.0, 1.0].

        Returns (calibrated, raw_float). Rejects booleans, non-numbers,
        NaN and infinities — those indicate a broken reply, not a value.
        """
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypeError(f"confidence must be a number, got {raw!r}")
        raw_float = float(raw)
        if math.isnan(raw_float) or math.isinf(raw_float):
            raise ValueError(f"confidence must be finite, got {raw!r}")
        calibrated = min(1.0, max(0.0, raw_float))
        return calibrated, raw_float


def add_attachment_context(
    question: str, context: dict[str, Any] | None = None
) -> str:
    """Append request-local, explicitly untrusted attachment data to a prompt.

    This helper adds no state to agents and never logs the file contents.
    """
    if not context:
        return question
    block = context.get("attachment_context")
    if not isinstance(block, str) or not block:
        return question
    # build_attachment_context already wraps the text in a labelled,
    # escaped UNTRUSTED_WEB_CONTENT block. Do not wrap or copy it again.
    return f"{question}{block}\n"


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
        router: Any = None,
        routing: Any = None,
        family: str = "",
        allowed_families: list[str] | tuple[str, ...] | set[str] | None = None,
    ):
        self.agent_id = agent_id
        self.provider = provider
        self.model = model
        self.role_description = role_description
        self.search_results: list[dict] = []
        # Routing context for family fallback (set by AgentManager).
        self._router = router
        self._routing = routing
        self.family = family
        # Bench family pins: validation-error retries never leave these
        # families (None = unconstrained). Kept local (not imported from
        # the router module) so this leaf module stays import-cycle free.
        if allowed_families is None:
            self._allowed_families: list[str] | None = None
        else:
            cleaned = sorted(
                {str(f).strip() for f in allowed_families if str(f).strip()}
            )
            self._allowed_families = cleaned or None

    def build_system_prompt(self) -> str:
        """Build the system prompt for this agent type. Override in subclasses."""
        return "You are a helpful AI assistant.\n\n" + UNTRUSTED_SYSTEM_NOTE

    def build_user_prompt(
        self, question: str, context: dict[str, Any] | None = None
    ) -> str:
        """Build the user prompt. Override in subclasses."""
        return question

    async def run(
        self,
        question: str,
        context: dict[str, Any] | None = None,
        temperature: float = 0.2,
    ) -> AgentOutput:
        """Execute this agent: call the provider and strictly validate.

        Independent solve: with no critique context the prompt contains
        only the question (plus web search results for the researcher) —
        never other agents' answers.

        Raises AgentValidationError after initial + retry + family-fallback
        attempts all fail validation. Transport errors propagate untouched
        so AgentManager can retry them on a fallback model.
        """
        system_prompt = self.build_system_prompt()
        user_prompt = self.build_user_prompt(question, context)

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]

        logger.info(
            f"Agent   │ {self.agent_id} ({self.agent_type}) → running on {self.model}"
        )

        provider_obj, model, family = self.provider, self.model, self.family
        provider_name = provider_obj.provider_name
        started = time.perf_counter()
        response = await provider_obj.generate(
            messages=messages,
            model=model,
            temperature=temperature,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0

        valid_ids = self._valid_ids_from_context(context)
        try:
            output = self._parse_and_validate(response.content, valid_ids=valid_ids)
        except AgentValidationError as first_error:
            logger.warning(
                f"Agent   │ {self.agent_id} — validation failed ({first_error}); "
                "retrying once with the error appended"
            )
            retry_messages = [
                *messages,
                ChatMessage(
                    role="user",
                    content=(
                        "Your previous reply was invalid: "
                        f"{first_error}. Reply with JSON only, "
                        "exactly matching the requested format."
                    ),
                ),
            ]
            started = time.perf_counter()
            response = await provider_obj.generate(
                messages=retry_messages,
                model=model,
                temperature=temperature,
            )
            latency_ms = (time.perf_counter() - started) * 1000.0
            try:
                output = self._parse_and_validate(response.content, valid_ids=valid_ids)
            except AgentValidationError as second_error:
                output, response, latency_ms = await self._fallback_attempt(
                    second_error, messages, temperature, valid_ids
                )
                provider_name = output.provider
                model = output.model
                family = output.family
                provider_obj = None
            else:
                provider_name = provider_obj.provider_name

        if provider_obj is not None:
            output.provider = provider_name
            output.model = response.model or model
            output.family = family
        output.tokens_used = response.total_tokens
        output.input_tokens = response.input_tokens
        output.output_tokens = response.output_tokens
        output.reasoning_tokens = getattr(response, "reasoning_tokens", 0) or 0
        output.latency_ms = latency_ms
        output.raw_content = response.content
        logger.info(
            f"Agent   │ {self.agent_id} → confidence: {output.confidence:.0%} "
            f"(raw {output.confidence_raw}), tokens: {output.tokens_used} "
            f"(in={output.input_tokens} out={output.output_tokens} "
            f"reason={output.reasoning_tokens})"
        )
        return output

    async def _fallback_attempt(
        self,
        error: AgentValidationError,
        messages: list[ChatMessage],
        temperature: float,
        valid_ids: list[str] | None,
    ) -> tuple[AgentOutput, ProviderResponse, float]:
        """One attempt on another family via the router (or raise).

        Returns (output, response, latency_ms) with provenance pre-filled
        from the fallback decision.
        """
        fallback = self._fallback_decision(error)
        if fallback is None:
            raise error
        logger.info(
            f"Agent   │ {self.agent_id} → falling back to "
            f"{fallback.provider_name}/{fallback.model} "
            f"({getattr(fallback, 'family', '')})"
        )
        started = time.perf_counter()
        response = await fallback.provider.generate(
            messages=messages,  # original messages: no error text leaks across families
            model=fallback.model,
            temperature=temperature,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        output = self._parse_and_validate(response.content, valid_ids=valid_ids)
        output.provider = fallback.provider_name
        output.model = response.model or fallback.model
        output.family = getattr(fallback, "family", "")
        return output, response, latency_ms

    def _fallback_decision(self, error: Exception) -> Any:
        """Ask the router for another family, or None if unavailable.

        Fail-open: routers without fallback_for (e.g. test doubles) simply
        yield no fallback and the validation error propagates. Under bench
        family pins, outside-pin candidates are walked past (bounded chain)
        so the retry never selects an out-of-pin model in the first place;
        None means "stay on this model or degrade", never "substitute".
        """
        router = self._router
        routing = self._routing
        fallback_for = getattr(router, "fallback_for", None)
        if router is None or routing is None or not callable(fallback_for):
            return None
        allowed = self._allowed_families
        current = routing
        seen: set[tuple[str, str]] = set()
        for _ in range(3):
            try:
                candidate = fallback_for(current, error)
            except Exception as e:  # noqa: BLE001 — fallback routing must not kill the run
                logger.warning(
                    f"Agent   │ {self.agent_id} — fallback routing failed: {e}"
                )
                return None
            if candidate is None:
                return None
            pair = (
                str(getattr(candidate, "provider_name", "")),
                str(getattr(candidate, "model", "")),
            )
            if pair in seen:
                return None
            seen.add(pair)
            if (
                allowed is not None
                and str(getattr(candidate, "family", "")) not in allowed
            ):
                logger.info(
                    f"Agent   │ {self.agent_id} — fallback family outside "
                    f"pins ({', '.join(allowed)}); trying the next fallback"
                )
                current = candidate
                continue
            return candidate
        return None

    @staticmethod
    def _valid_ids_from_context(
        context: dict[str, Any] | None,
    ) -> list[str] | None:
        """Agent IDs the reply may reference (critique mode only)."""
        if context and isinstance(context.get("valid_agent_ids"), list):
            return [str(aid) for aid in context["valid_agent_ids"]]
        return None

    def _parse_and_validate(
        self, content: str, valid_ids: list[str] | None = None
    ) -> AgentOutput:
        """Extract JSON and validate the strict AgentOutput schema.

        Raises AgentValidationError on: no JSON found, bad JSON, schema
        violations (missing/extra keys, wrong types, empty position), or
        non-numeric/non-finite confidence. Unknown agent IDs in
        supports/disagrees_with are stripped (Fix B), not rejected.
        """
        text = (content or "").strip()
        json_str = self._extract_json(text)
        if json_str is None:
            raise AgentValidationError("no JSON object found in agent reply")
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise AgentValidationError(f"agent reply is not JSON: {e}") from e
        if not isinstance(data, dict):
            raise AgentValidationError("agent reply JSON is not an object")

        data = dict(data)
        if "confidence" not in data:
            raise AgentValidationError("agent reply is missing 'confidence'")
        try:
            calibrated, raw = AgentOutput.calibrate_confidence(data["confidence"])
        except (TypeError, ValueError) as e:
            raise AgentValidationError(str(e)) from e
        data["confidence"] = calibrated
        data["confidence_raw"] = raw

        summary = data.get("reasoning_summary", "")
        if isinstance(summary, str) and len(summary) > MAX_REASONING_SUMMARY_CHARS:
            data["reasoning_summary"] = (
                summary[:MAX_REASONING_SUMMARY_CHARS] + "... [truncated]"
            )

        try:
            output = AgentOutput.model_validate(data)
        except ValidationError as e:
            raise AgentValidationError(f"agent reply failed schema: {e}") from e

        if valid_ids is not None:
            allowed = set(valid_ids + [self.agent_id])
            stripped_supports = [aid for aid in output.supports if aid in allowed]
            stripped_disagrees = [
                aid for aid in output.disagrees_with if aid in allowed
            ]
            if len(stripped_supports) != len(output.supports) or len(
                stripped_disagrees
            ) != len(output.disagrees_with):
                logger.warning(
                    f"Agent   │ {self.agent_id} — stripped hallucinated agent IDs "
                    "(Fix B: supports/disagrees_with must reference known agents)"
                )
            output.supports = stripped_supports
            output.disagrees_with = stripped_disagrees

        output.agent_id = self.agent_id
        output.agent_type = self.agent_type
        return output

    @staticmethod
    def _extract_json(text: str) -> str | None:
        """
        Robustly extract a JSON object string from LLM output.

        Strategy:
        1. Strip markdown code fences of any language (```json, ```python, etc.)
        2. Find the first '{' character
        3. Walk forward, tracking brace depth, to find the matching '}'
        4. Return the substring as the candidate JSON

        Returns None if no valid JSON object structure is found.
        """
        # Step 1: Strip markdown code fences (handles ```json, ```javascript, etc.)
        stripped = re.sub(r"```\w*\s*", "", text)
        stripped = stripped.replace("```", "").strip()

        # Step 2: Find the first '{' — start of JSON object
        start = stripped.find("{")
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

            if char == "\\" and in_string:
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return stripped[start : i + 1]

        return None

    # ── Convenience for debate rounds ────────────────────────────────

    async def critique(
        self,
        question: str,
        other_outputs: list[AgentOutput],
        round_number: int,
        *,
        context: dict[str, Any] | None = None,
    ) -> AgentOutput:
        """Review peer outputs while retaining optional run-local context."""
        valid_agent_ids = [o.agent_id for o in other_outputs]
        critique_context: dict[str, Any] = {
            "round_number": round_number,
            "other_outputs": [o.to_dict() for o in other_outputs],
            "valid_agent_ids": valid_agent_ids,
            "mode": "critique",
        }
        if context:
            attachment_context = context.get("attachment_context")
            if isinstance(attachment_context, str) and attachment_context:
                critique_context["attachment_context"] = attachment_context
        output = await self.run(question, context=critique_context)

        # Validate referential integrity: strip hallucinated agent IDs.
        all_valid = set(valid_agent_ids + [self.agent_id])
        output.supports = [aid for aid in output.supports if aid in all_valid]
        output.disagrees_with = [
            aid for aid in output.disagrees_with if aid in all_valid
        ]
        return output
