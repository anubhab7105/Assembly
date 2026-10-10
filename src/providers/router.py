"""
Assembly — family-aware model router (config-driven).

All model ids, families, roles, limits, and endpoints come from
models.yaml — nothing is hard-coded here. Candidate order follows the
catalog: provider order, then model order inside each provider (list the
fastest/cheapest model first; tight budgets automatically get fast models).

Diversity is counted by MODEL FAMILY, never by provider: two providers
serving the same family are one vote, one failure domain, one bias.

Runs are gated on distinct usable families: >=3 OK, 2 WARN, 1 DEGRADED
(confirm + lower-confidence label), 0 BLOCKED.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, SecretStr

from src.core.keystore import get_keystore, reveal
from src.core.logging_config import logger
from src.orchestration.capacity import AVG_TOKENS_PER_CALL
from src.providers.base import AIProvider
from src.providers.config import (
    LimitsNotFilledError,
    ModelsConfig,
    load_models_config,
    validate_provider_limits,
)
from src.providers.quota import fingerprint_key, get_limiter
from src.providers.registry import get_provider

MIN_REQUIRED_PROVIDERS = 3  # Deprecated: kept for imports; the live gate is
# FAMILY_GATE_THRESHOLDS below (PRD FR-10, D3 counts families, not providers).
MIN_AFFORDABLE_CALLS = 2  # a routed provider should afford solve + critique

# Family-diversity gate (PRD FR-10, D3): one constant, no scattered literals.
# >= OK → run; == WARN_AT → run with visible warning; == 1 → DEGRADED
# (confirm + lower-confidence label); == 0 → BLOCKED.
FAMILY_GATE_THRESHOLDS: dict[str, int] = {"ok": 3, "warn": 2}

# Key prefixes that mean "not configured" (mirrors Settings.has_provider).
_PLACEHOLDER_PREFIXES = (
    "sk-your",
    "your-",
    "gsk_your",
    "hf_your",
    "csk_your",
    "xpl_your",
)


@dataclass
class RoutingDecision:
    """One routed agent: where it runs, why, and for which role."""

    provider: AIProvider
    model: str
    provider_name: str
    family: str = ""
    role: str = ""
    reason: str = ""


# Back-compat alias (same shape plus role/reason defaults).
ModelAssignment = RoutingDecision


@dataclass
class TeamRouting:
    """Whole-team routing outcome with diversity health."""

    decisions: list[RoutingDecision] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    degraded: bool = False
    families: list[str] = field(default_factory=list)


@dataclass
class DiversityGate:
    """Family-count gate verdict (PRD FR-10, D3).

    Levels: OK (>=3 families) → run; WARN (2) → run with visible warning;
    DEGRADED (1) → run only after user confirms, final answer labeled
    lower-confidence; BLOCKED (0) → refuse with a clear message.
    """

    level: str = "BLOCKED"
    families_ready: list[str] = field(default_factory=list)
    families_count: int = 0
    providers_count: int = 0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "families_ready": list(self.families_ready),
            "families_count": self.families_count,
            "providers_count": self.providers_count,
            "reasons": list(self.reasons),
        }


class DiversityGateResponse(BaseModel):
    """Wire shape of DiversityGate (status, preflight, SSE start event)."""

    model_config = ConfigDict(extra="forbid")

    level: str = "BLOCKED"
    families_ready: list[str] = []
    families_count: int = 0
    providers_count: int = 0
    reasons: list[str] = []


class ModelRouter:
    """
    Family-aware model selection engine.

    route_team() is the primary path: it spreads solvers across distinct
    families, keeps the critic off the solvers' families, honors quota
    state and the time budget, and reports warnings/degraded mode.
    route() handles single agents (planner, synthesizer); route_team()
    should be preferred whenever a team is formed.
    """

    def __init__(
        self,
        config: ModelsConfig | None = None,
        keys: Mapping[str, str | SecretStr] | None = None,
        limiter: Any = None,
    ) -> None:
        """Build the router. keys (provider → key) overrides the APP_MODE store.

        Keys arrive as SecretStr and are revealed only for provider
         construction — names alone are ever logged.
        """
        self.config = config or load_models_config()
        self._limiter = limiter if limiter is not None else get_limiter()
        self._providers: dict[str, AIProvider] = {}
        self._fingerprints: dict[str, str] = {}
        self._init_providers(keys)

    @staticmethod
    def _mode_keys() -> dict[str, str]:
        """Keys for the current APP_MODE (dev: env, web: none, desktop: keyring).

        Web mode intentionally contributes no server keys — keys arrive
        per request. Failures reading the desktop keyring degrade to no
        keys rather than crashing startup.
        """
        try:
            store = get_keystore()
        except (ValueError, RuntimeError):
            return {}
        try:
            return {pid: reveal(value) for pid, value in store.get_keys().items()}
        except Exception:  # noqa: BLE001 — keyring trouble must not kill startup
            return {}

    def _init_providers(
        self, keys: Mapping[str, str | SecretStr] | None = None
    ) -> None:
        """Initialize every enabled provider that has a real API key."""
        key_map = (
            {pid: reveal(value) for pid, value in keys.items()}
            if keys is not None
            else self._mode_keys()
        )
        total = len(self.config.providers)
        for provider_id, spec in self.config.providers.items():
            if not spec.enabled:
                logger.info(
                    f"Router  │ ○ {provider_id} provider disabled in models.yaml"
                )
                continue
            key = key_map.get(provider_id, "")
            if not key or any(key.startswith(p) for p in _PLACEHOLDER_PREFIXES):
                logger.warning(f"Router  │ ✗ {provider_id} provider — no API key")
                continue
            try:
                validate_provider_limits(provider_id, spec)
            except LimitsNotFilledError as exc:
                logger.error(f"Router  │ ✗ {provider_id} provider — {exc}")
                continue
            try:
                provider = get_provider(provider_id, key, config=self.config)
                if provider.is_available():
                    self._providers[provider_id] = provider
                    self._fingerprints[provider_id] = fingerprint_key(key)
                    logger.info(f"Router  │ ✓ {provider_id} provider available")
                else:
                    logger.warning(f"Router  │ ✗ {provider_id} provider — no API key")
            except Exception as e:  # noqa: BLE001 — one bad provider must not kill startup
                logger.warning(f"Router  │ ✗ {provider_id} provider — init error: {e}")

        live = len(self._providers)
        gate = self.diversity_gate()
        logger.info(
            f"Router  │ {live}/{total} providers live; "
            f"family gate: {gate.level} "
            f"({gate.families_count} families: {', '.join(gate.families_ready) or 'none'})"
        )
        if gate.level == "BLOCKED":
            logger.error(
                f"Router  │ ⚠ No usable model family. {' '.join(gate.reasons)}"
            )
        elif gate.level in ("WARN", "DEGRADED"):
            logger.warning(f"Router  │ {' '.join(gate.reasons)}")

    def get_available_providers(self) -> list[str]:
        """Return names of providers with valid credentials."""
        return list(self._providers.keys())

    def get_live_count(self) -> int:
        """Return the number of currently live providers."""
        return len(self._providers)

    def _suggest_families(self, ready: list[str]) -> str:
        """Actionable fix hint naming catalog families the user lacks."""
        missing: list[str] = []
        for spec in self.config.providers.values():
            for model in spec.models:
                if model.family not in ready and model.family not in missing:
                    missing.append(model.family)
        hint = " / ".join(missing[:2]) if missing else "another provider"
        return f"Add a {hint} key to reach 3 families."

    def diversity_gate(self, allowed_models: set[str] | None = None) -> DiversityGate:
        """Count DISTINCT usable families right now (PRD D3).

        Usable means: provider enabled, key present (in this router),
        limits filled (else the provider never joined this router), model
        not in cooldown/exhausted, and inside the user's model selection
        when one is given. The same family on two providers counts once.
        """
        allowed = set(allowed_models) if allowed_models else set()
        families: list[str] = []
        usable_providers: set[str] = set()
        for provider_id in self._providers:
            try:
                spec = self.config.providers[provider_id]
            except KeyError:
                continue
            for model in spec.models:
                if allowed and model.id not in allowed:
                    continue
                if not self._usable_model(provider_id, model.id):
                    continue
                usable_providers.add(provider_id)
                if model.family not in families:
                    families.append(model.family)
        ok_at = FAMILY_GATE_THRESHOLDS["ok"]
        warn_at = FAMILY_GATE_THRESHOLDS["warn"]
        count = len(families)
        if count >= ok_at:
            level = "OK"
            reasons = [f"{count} families ready: {', '.join(families)}."]
        elif count == warn_at:
            level = "WARN"
            reasons = [
                f"Only {count} distinct model families ready ({', '.join(families)}): "
                "independent reasoning is weakened. " + self._suggest_families(families)
            ]
        elif count == 1:
            level = "DEGRADED"
            reasons = [
                f"Only 1 model family ready ({', '.join(families)}): "
                "agents cannot reason independently. Run only after confirming; "
                "the final answer will be labeled lower-confidence. "
                + self._suggest_families(families)
            ]
        else:
            level = "BLOCKED"
            reasons = [
                (
                    "No model families ready. Add keys for at least two providers "
                    "covering 3 model families, then try again."
                )
            ]
        return DiversityGate(
            level=level,
            families_ready=families,
            families_count=count,
            providers_count=len(usable_providers),
            reasons=reasons,
        )

    def _enforce_minimum(self) -> None:
        """Block only when zero usable families remain (family gate)."""
        gate = self.diversity_gate()
        if gate.level == "BLOCKED":
            raise RuntimeError(
                "Assembly needs at least 1 usable model family to run. "
                + " ".join(gate.reasons)
            )

    def _family_of(self, provider_id: str, model_id: str) -> str:
        """Look up the catalog family for a live provider/model pair."""
        for model in self.config.providers[provider_id].models:
            if model.id == model_id:
                return model.family
        return ""

    def _usable_model(self, provider_id: str, model_id: str) -> bool:
        """Live and not quota-exhausted for one model (cooldown or spent bucket).

        Fail-open: limiter trouble never removes a model from routing;
        acquire() still enforces at call time.
        """
        fingerprint = self._fingerprints.get(provider_id)
        if fingerprint is None:
            return True
        try:
            return not self._limiter.is_exhausted(provider_id, fingerprint, model_id)
        except Exception:  # noqa: BLE001 — quota must never break routing
            return True

    def _usable(self, provider_id: str) -> bool:
        """Live and not quota-exhausted on every model (legacy helper)."""
        try:
            models = self.config.providers[provider_id].models
        except KeyError:
            return True
        if not models:
            return True
        return any(self._usable_model(provider_id, model.id) for model in models)

    def _affordable(self, time_budget_minutes: int) -> dict[str, bool]:
        """Providers able to afford a solve+critique pair for this budget.

        Unknown limits count as affordable (fail-open: the repo catalog
        ships null limits until filled from dashboards).
        """
        try:
            estimate = self.capacity_estimate(time_budget_minutes)
        except Exception:  # noqa: BLE001 — unknown capacity, not zero
            return {pid: True for pid in self._providers}
        per_provider = estimate.get("per_provider", {})
        return {
            pid: (calls is None or calls >= MIN_AFFORDABLE_CALLS)
            for pid, calls in per_provider.items()
        }

    def _role_models(self, role: str) -> list[tuple[str, str, str]]:
        """All (provider, model, family) offering a role, in catalog order."""
        candidates = []
        for provider_id, spec in self.config.providers.items():
            if provider_id not in self._providers:
                continue
            for model in spec.models:
                if role in model.roles:
                    candidates.append((provider_id, model.id, model.family))
        return candidates

    def _candidates(
        self, role: str, time_budget_minutes: int = 5
    ) -> list[tuple[str, str, str]]:
        """Usable candidates: live, role-matching, unexhausted, affordable.

        Falls back to ignoring affordability (fail-open) when nothing can
        afford the budget — a thin quota beats no team at all.
        """
        affordable = self._affordable(time_budget_minutes)
        usable = [
            (pid, mid, fam)
            for pid, mid, fam in self._role_models(role)
            if self._usable_model(pid, mid) and affordable.get(pid, True)
        ]
        if usable:
            return usable
        fallback = [
            (pid, mid, fam)
            for pid, mid, fam in self._role_models(role)
            if self._usable_model(pid, mid)
        ]
        if fallback:
            logger.warning(
                f"Router  │ no provider can afford {role} on this budget; proceeding fail-open"
            )
        return fallback

    def capacity_estimate(self, time_budget_minutes: int = 3) -> dict[str, object]:
        """Affordable calls per provider for the planner (WORKFLOW capacity rule).

        Per quota bucket: calls_now = min(rpm × minutes, rpd remaining,
        tpm × minutes / AVG_TOKENS_PER_CALL, tpd / AVG_TOKENS_PER_CALL);
        a provider totals its buckets × 0.7 margin (account-scope models
        share one bucket and are counted once). Unknown limits yield None
        (unlimited-for-planning, not zero).
        """
        per_provider: dict[str, int | None] = {}
        for provider_id in self._providers:
            fingerprint = self._fingerprints.get(provider_id)
            if fingerprint is None:
                per_provider[provider_id] = None
                continue
            try:
                buckets: dict[str, dict[str, Any]] = {}
                for model in self.config.providers[provider_id].models:
                    remaining = self._limiter.remaining(
                        provider_id, fingerprint, model.id
                    )
                    key = (
                        "" if remaining.get("scope", "model") == "account" else model.id
                    )
                    buckets.setdefault(key, remaining)
                subtotals = []
                for remaining in buckets.values():
                    options = []
                    if remaining["rpm_limit"] is not None:
                        options.append(remaining["rpm_limit"] * time_budget_minutes)
                    if remaining["rpd_limit"] is not None:
                        options.append(remaining["rpd_remaining"])
                    if remaining["tpm_limit"] is not None:
                        options.append(
                            remaining["tpm_limit"]
                            * time_budget_minutes
                            // AVG_TOKENS_PER_CALL
                        )
                    if remaining["tpd_limit"] is not None:
                        options.append(
                            remaining["tpd_remaining"] // AVG_TOKENS_PER_CALL
                        )
                    if options:
                        subtotals.append(int(min(options) * 0.7))
                per_provider[provider_id] = sum(subtotals) if subtotals else None
            except Exception:  # noqa: BLE001 — unknown capacity, not zero
                per_provider[provider_id] = None
                continue
        known = [v for v in per_provider.values() if v is not None]
        return {"per_provider": per_provider, "total": sum(known) if known else None}

    def quota_snapshot(self) -> list[dict[str, Any]]:
        """Per quota bucket: provider + model + quota COUNTS.

        Read-only input for the capacity planner (WORKFLOW section 4).
        Account-scope models share one bucket and appear once (as the
        first model). Counts only — fingerprints and raw keys never leave
        the router. Unknown limits stay None (unlimited-for-planning).
        """
        snapshot: list[dict[str, Any]] = []
        for provider_id in self._providers:
            try:
                spec = self.config.providers.get(provider_id)
                models = spec.models if spec is not None else []
                fingerprint = self._fingerprints.get(provider_id)
                seen_buckets: set[str] = set()
                for model in models:
                    scope = model.scope
                    bucket = "" if scope == "account" else model.id
                    if bucket in seen_buckets:
                        continue
                    seen_buckets.add(bucket)
                    rpm_limit: int | None = None
                    rpd_remaining: int | None = None
                    tpm_limit: int | None = None
                    tpd_remaining: int | None = None
                    cooldown_seconds: float = 0.0
                    if fingerprint is not None:
                        remaining = self._limiter.remaining(
                            provider_id, fingerprint, model.id
                        )
                        rpm_limit = remaining.get("rpm_limit")
                        rpd_remaining = remaining.get("rpd_remaining")
                        tpm_limit = remaining.get("tpm_limit")
                        tpd_remaining = remaining.get("tpd_remaining")
                        cooldown_seconds = float(
                            remaining.get("cooldown_seconds") or 0.0
                        )
                    else:
                        limits = model.limits
                        rpm_limit = limits.rpm if isinstance(limits.rpm, int) else None
                    snapshot.append(
                        {
                            "provider": provider_id,
                            "model": model.id,
                            "scope": scope,
                            "rpm_limit": rpm_limit,
                            "rpd_remaining": rpd_remaining,
                            "tpm_limit": tpm_limit,
                            "tpd_remaining": tpd_remaining,
                            "cooldown_seconds": cooldown_seconds,
                        }
                    )
                if not models:
                    snapshot.append(
                        {
                            "provider": provider_id,
                            "model": "",
                            "scope": "model",
                            "rpm_limit": None,
                            "rpd_remaining": None,
                            "tpm_limit": None,
                            "tpd_remaining": None,
                            "cooldown_seconds": 0.0,
                        }
                    )
            except Exception:  # noqa: BLE001, S110 — quota must never break planning
                pass
        return snapshot

    def available_families(self) -> list[str]:
        """Distinct families across live providers, in catalog order."""
        families: list[str] = []
        for provider_id, spec in self.config.providers.items():
            if provider_id not in self._providers:
                continue
            for model in spec.models:
                if model.family not in families:
                    families.append(model.family)
        return families

    def route_team(
        self,
        team: list[dict],
        problem_type: str = "general",
        complexity: str = "medium",
        time_budget_minutes: int = 5,
    ) -> TeamRouting:
        """Route a whole team with family-diversity guarantees.

        - Solvers go first, each on a fresh family while one is available.
        - The critic avoids every solver family (it reviews those positions).
        - Other roles spread across unused families, then reuse.
        - 2 available families → proceed with a warning; 1 → degraded flag.
        """
        self._enforce_minimum()
        specs = [
            {
                "agent_type": member.get("agent_type", "solver"),
                "role_description": member.get("role_description", ""),
            }
            for member in team
        ]
        available = self.available_families()
        warnings: list[str] = []
        degraded = False
        if len(available) == 2:
            warnings.append(
                f"Only 2 distinct model families available ({', '.join(available)}): "
                "independent reasoning is weakened; answers carry correlated-error risk."
            )
        elif len(available) <= 1:
            degraded = True
            warnings.append(
                f"Degraded mode: a single model family available ({', '.join(available) or 'none'}). "
                "No independence between agents; treat consensus with suspicion."
            )

        # Solvers first (distinct families), then the rest in spec order so
        # the critic is placed once solver families are known.
        order = sorted(
            range(len(specs)),
            key=lambda i: 0 if specs[i]["agent_type"] == "solver" else 1,
        )
        by_index: dict[int, RoutingDecision] = {}
        used_families: list[str] = []
        solver_families: list[str] = []

        for index in order:
            agent_type = specs[index]["agent_type"]
            forbid = set(solver_families) if agent_type == "critic" else set()
            candidates = self._candidates(agent_type, time_budget_minutes)
            decision = self._pick(agent_type, candidates, used_families, forbid)
            if decision is None:
                decision = self._last_resort(agent_type)
                warnings.append(
                    f"No usable {agent_type} model available; "
                    f"fell back to {decision.provider_name}/{decision.model}."
                )
            by_index[index] = decision
            used_families.append(decision.family)
            if agent_type == "solver":
                solver_families.append(decision.family)
            logger.info(
                f"Router  │ {agent_type} → {decision.provider_name}/{decision.model} "
                f"({decision.family or 'unknown family'}): {decision.reason}"
            )

        decisions = [by_index[i] for i in range(len(specs))]
        families = [fam for fam in dict.fromkeys(d.family for d in decisions) if fam]
        solver_families = [d.family for d in decisions if d.role == "solver"]
        if len(solver_families) != len(set(solver_families)):
            warnings.append(
                "Solver family reused: more solvers than distinct families; "
                "those agents are not independent."
            )
        for warning in warnings:
            logger.warning(f"Router  │ {warning}")
        return TeamRouting(
            decisions=decisions, warnings=warnings, degraded=degraded, families=families
        )

    def _pick(
        self,
        agent_type: str,
        candidates: list[tuple[str, str, str]],
        used_families: list[str],
        forbid_families: set[str],
    ) -> RoutingDecision | None:
        """Best candidate: fresh family, then allowed family, then anything."""
        if not candidates:
            return None
        fresh = [
            c
            for c in candidates
            if c[2] not in used_families and c[2] not in forbid_families
        ]
        allowed = [c for c in candidates if c[2] not in forbid_families]
        if fresh:
            provider_id, model_id, family = fresh[0]
            reason = f"first {agent_type} model on unused family {family}"
        elif allowed:
            provider_id, model_id, family = allowed[0]
            if family in forbid_families:
                reason = (
                    f"only {agent_type} models left are on reviewed family {family}"
                )
            else:
                reason = f"all families in use; reusing {family} for {agent_type}"
        else:
            provider_id, model_id, family = candidates[0]
            reason = (
                f"no {agent_type} model outside reviewed families "
                f"({', '.join(sorted(forbid_families)) or 'none'}); using {family}"
            )
        return RoutingDecision(
            provider=self._providers[provider_id],
            model=model_id,
            provider_name=provider_id,
            family=family,
            role=agent_type,
            reason=reason,
        )

    def _last_resort(self, agent_type: str) -> RoutingDecision:
        """First model of the first live provider (catalog order)."""
        provider_id = next(iter(self._providers))
        model_id = self.config.providers[provider_id].models[0].id
        return RoutingDecision(
            provider=self._providers[provider_id],
            model=model_id,
            provider_name=provider_id,
            family=self._family_of(provider_id, model_id),
            role=agent_type,
            reason="last resort: first live model",
        )

    def fallback_for(
        self, decision: RoutingDecision, error: Exception
    ) -> RoutingDecision | None:
        """Next model after a call failure: different family first, then the
        same family via a different provider. Never the same model again."""
        pool = [
            (pid, mid, fam)
            for pid, mid, fam in self._role_models(decision.role or "solver")
            if (pid, mid) != (decision.provider_name, decision.model)
            and self._usable_model(pid, mid)
        ]
        different_family = [c for c in pool if c[2] != decision.family]
        same_family = [
            c
            for c in pool
            if c[2] == decision.family and c[0] != decision.provider_name
        ]
        error_name = type(error).__name__
        if different_family:
            provider_id, model_id, family = different_family[0]
            reason = f"fallback after {error_name}: different family {family}"
        elif same_family:
            provider_id, model_id, family = same_family[0]
            reason = (
                f"fallback after {error_name}: same family {family}, other provider"
            )
        else:
            logger.warning(
                f"Router  │ no fallback for {decision.provider_name}/{decision.model} "
                f"after {error_name}"
            )
            return None
        logger.info(
            f"Router  │ fallback {decision.provider_name}/{decision.model} → "
            f"{provider_id}/{model_id} ({family}): {reason}"
        )
        return RoutingDecision(
            provider=self._providers[provider_id],
            model=model_id,
            provider_name=provider_id,
            family=family,
            role=decision.role,
            reason=reason,
        )

    def route(
        self,
        agent_type: str,
        problem_type: str = "general",
        complexity: str = "medium",
        time_budget_minutes: int = 5,
        prefer_provider: str | None = None,
    ) -> RoutingDecision:
        """
        Route a single agent to the best available model for its role.

        First usable catalog model whose roles include the agent type. A
        requested live provider is honored when it offers the role and is
        usable, else routing falls through to team-order candidates.
        Prefer route_team() whenever a team is formed — only it can enforce
        family diversity.
        """
        self._enforce_minimum()

        if (
            prefer_provider
            and prefer_provider in self._providers
            and self._usable(prefer_provider)
        ):
            spec = self.config.providers[prefer_provider]
            model = next(
                (m for m in spec.models if agent_type in m.roles),
                spec.models[0] if spec.models else None,
            )
            if model is not None:
                affordable = self._affordable(time_budget_minutes)
                if affordable.get(prefer_provider, True) and self._usable_model(
                    prefer_provider, model.id
                ):
                    return RoutingDecision(
                        provider=self._providers[prefer_provider],
                        model=model.id,
                        provider_name=prefer_provider,
                        family=model.family,
                        role=agent_type,
                        reason=f"requested provider offers {agent_type}",
                    )

        candidates = self._candidates(agent_type, time_budget_minutes)
        if candidates:
            provider_id, model_id, family = candidates[0]
            return RoutingDecision(
                provider=self._providers[provider_id],
                model=model_id,
                provider_name=provider_id,
                family=family,
                role=agent_type,
                reason=f"first usable {agent_type} model in catalog order",
            )
        decision = self._last_resort(agent_type)
        logger.warning(f"Router  │ {decision.reason} for {agent_type}")
        return decision

    def route_for_planning(self) -> RoutingDecision:
        """Route specifically for the Planner (cheap classification call)."""
        self._enforce_minimum()
        candidates = self._candidates("planner")
        if candidates:
            provider_id, model_id, family = candidates[0]
            return RoutingDecision(
                provider=self._providers[provider_id],
                model=model_id,
                provider_name=provider_id,
                family=family,
                role="planner",
                reason="first usable planner model in catalog order",
            )
        decision = self._last_resort("planner")
        logger.warning(f"Router  │ {decision.reason} for planner")
        return decision
