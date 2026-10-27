"""Assembly — per-request execution context (preflight + run share this).

One builder for provider keys, search-key presence, usage snapshots, and
model selection, so the preflight verdict and run routing cannot diverge.
Keys stay in memory only and are never logged (names alone are ever logged).
"""

from dataclasses import dataclass, field

from src.core.keystore import wrap_keys
from src.core.logging_config import logger
from src.providers.config import load_models_config
from src.providers.quota import fingerprint_key, get_limiter


def _resolve_selection(selected: list[str]) -> tuple[set[str], dict[str, str]]:
    """Validate selected model ids against the catalog.

    Returns (allowed model ids, model id -> provider). Empty selection
    means Auto (all catalog models allowed).
    """
    wanted = [s.strip() for s in (selected or []) if s and s.strip()][:50]
    if not wanted:
        return set(), {}
    catalog = load_models_config()
    known: dict[str, str] = {}
    for pid, spec in catalog.providers.items():
        if not spec.enabled:
            continue
        for m in spec.models:
            known[m.id] = pid
    allowed = {m for m in wanted if m in known}
    # Unknown ids are dropped (fail-soft); all-unknown falls back to Auto.
    if not allowed:
        return set(), {}
    return allowed, {m: known[m] for m in allowed}


def _diversity_is_blocked(router: object, allowed: set[str]) -> bool:
    """True when zero model families are usable for this run's keys.

    Routers with a family diversity gate use it; routers without one
    (test doubles) fall back to catalog families under the selection.
    """
    gate = None
    diversity_gate = getattr(router, "diversity_gate", None)
    if callable(diversity_gate):
        try:
            gate = diversity_gate(set(allowed) if allowed else None)
        except Exception:  # noqa: BLE001 — gate trouble reads as blocked
            return True
    if gate is not None:
        return gate.level == "BLOCKED"
    catalog = load_models_config()
    fams: set[str] = set()
    for spec in catalog.providers.values():
        if not spec.enabled:
            continue
        for m in spec.models:
            if not allowed or m.id in allowed:
                fams.add(m.family)
    return len(fams) == 0


def diversity_payload(router: object, allowed: set[str]) -> dict[str, object]:
    """Family-diversity metadata for run.started events (names only)."""
    payload: dict[str, object] = {
        "level": "BLOCKED",
        "families_ready": [],
        "families_count": 0,
        "providers_count": 0,
        "reasons": [],
    }
    try:
        gate = (
            router.diversity_gate(set(allowed) if allowed else None)  # type: ignore[union-attr]
            if hasattr(router, "diversity_gate")
            else None
        )
        if gate is not None:
            return gate.to_dict()  # type: ignore[no-any-return]
        catalog = load_models_config()
        fams: set[str] = set()
        if allowed:
            for spec in catalog.providers.values():
                for m in spec.models:
                    if m.id in allowed:
                        fams.add(m.family)
        else:
            for spec in catalog.providers.values():
                if spec.enabled:
                    fams.update(m.family for m in spec.models)
        if 0 < len(fams) < 3:
            logger.info("Run     │ fewer than 3 families selected")
    except Exception as exc:  # noqa: BLE001 — warning only
        logger.debug(f"Run     │ family gate skipped: {exc}")
    return payload


def _filtered_router(
    provider_keys: dict[str, str], allowed: set[str], pins: dict[str, str]
):
    """Build a ModelRouter restricted to selected models + validated role pins.

    Pins are strict: they must exist in the active selection (when one is
    provided), have a configured/live provider adapter, and be valid for the
    requested role. Invalid pins raise PinViolationError rather than silently
    falling back to a different model.
    """
    from src.providers.router import ModelRouter, PinViolationError

    keys = wrap_keys(provider_keys or {})
    revealed = {
        p: k.get_secret_value() for p, k in keys.items() if k.get_secret_value()
    }
    base_router: ModelRouter | None = None
    if allowed:
        catalog = load_models_config()
        filtered_providers = {}
        for pid, spec in catalog.providers.items():
            kept = [m for m in spec.models if m.id in allowed]
            if kept:
                filtered_providers[pid] = spec.model_copy(update={"models": kept})
        if filtered_providers:
            from src.providers.config import ModelsConfig

            base_router = ModelRouter(
                config=ModelsConfig(providers=filtered_providers), keys=revealed
            )
    if base_router is None:
        base_router = ModelRouter(keys=revealed)

    if not pins:
        return base_router

    # Resolve each pin against the full catalog first, then verify the model
    # survived the active selection. Never quietly widen that selection.
    catalog = load_models_config()
    pin_specs: dict[str, tuple[str, object]] = {}
    for role, model_id in list(pins.items())[:10]:
        role = str(role).strip()
        model_id = str(model_id).strip()
        if not role or not model_id:
            continue
        match = next(
            (
                (pid, model)
                for pid, spec in catalog.providers.items()
                if spec.enabled
                for model in spec.models
                if model.id == model_id
            ),
            None,
        )
        if match is None:
            raise PinViolationError(
                f"Pinned model for {role!r} is unknown or disabled. "
                "Choose an enabled model from the model picker."
            )
        provider_id, model = match
        if allowed and model_id not in allowed:
            raise PinViolationError(
                f"Pinned model for {role!r} is excluded by the current model selection. "
                "Add it to the selection or choose a model within the selection."
            )
        if provider_id not in base_router._providers:
            raise PinViolationError(
                f"Pinned provider for {role!r} is not configured or available. "
                "Add a valid API key for that provider, then retry."
            )
        if role not in model.roles:
            raise PinViolationError(
                f"Pinned model {model_id!r} does not support the {role!r} role. "
                "Choose a model that supports this role."
            )
        pin_specs[role] = (provider_id, model)

    if not pin_specs:
        return base_router

    class _PinRouter:
        """Delegate to ModelRouter while applying validated model pins."""

        def __init__(
            self, wrapped: ModelRouter, resolved: dict[str, tuple[str, object]]
        ) -> None:
            self._w = wrapped
            self._pins = resolved
            self.config = wrapped.config

        def __getattr__(self, name: str):  # delegate everything else
            return getattr(self._w, name)

        def _apply_pin(self, decision, role: str):
            pin = self._pins.get(role)
            if pin is None:
                return decision
            provider_id, model = pin
            provider = self._w._providers.get(provider_id)
            if provider is None:
                raise PinViolationError(
                    f"Pinned provider for {role!r} is no longer available. "
                    "Check its API key and retry."
                )
            # Update the complete assignment, including the adapter. Build a
            # fresh decision to avoid exposing a half-mutated assignment.
            from src.providers.router import RoutingDecision

            return RoutingDecision(
                provider=provider,
                model=model.id,
                provider_name=provider_id,
                family=model.family,
                role=role,
                reason=f"pinned model {provider_id}/{model.id} for {role}",
            )

        def route(self, agent_type: str, *a, **k):  # type: ignore[no-untyped-def]
            decision = self._w.route(agent_type, *a, **k)
            return self._apply_pin(decision, agent_type)

        def route_team(self, team: list, *a, **k):  # type: ignore[no-untyped-def]
            from src.providers.router import TeamRouting

            routing = self._w.route_team(team, *a, **k)
            decisions = []
            for decision, spec in zip(routing.decisions, team):
                role = spec.get("agent_type", "") if isinstance(spec, dict) else ""
                decisions.append(self._apply_pin(decision, role))

            # Routing's solver spread / critic isolation were computed before
            # role pins. Revalidate against the final assignments.
            solver_families = {
                d.family for d in decisions if d.role == "solver"
            }
            critic = next((d for d in decisions if d.role == "critic"), None)
            pinned_critic = self._pins.get("critic")
            solver_was_pinned = "solver" in self._pins
            if (
                critic is not None
                and (pinned_critic is not None or solver_was_pinned)
                and critic.family in solver_families
            ):
                raise PinViolationError(
                    "Role pins place the critic in a solver's family, so critic "
                    "independence cannot be guaranteed. Pin the critic or solver "
                    "to a different model family."
                )

            solver_decisions = [d for d in decisions if d.role == "solver"]
            solver_families_ordered = [d.family for d in solver_decisions]
            available_solver_families = {
                family for _, _, family in self._w._candidates("solver")
            }
            required_distinct = min(
                len(solver_decisions), len(available_solver_families)
            )
            if (
                solver_was_pinned
                and len(set(solver_families_ordered)) < required_distinct
            ):
                raise PinViolationError(
                    "The solver pin prevents the team from using distinct available model families. "
                    "Choose a solver pin from another family or remove the solver pin."
                )

            warnings = list(routing.warnings)
            if len(solver_families_ordered) != len(set(solver_families_ordered)):
                message = (
                    "Solver family reused after role pins; those agents are not independent."
                )
                if message not in warnings:
                    warnings.append(message)
            families = [fam for fam in dict.fromkeys(d.family for d in decisions) if fam]
            return TeamRouting(
                decisions=decisions,
                warnings=warnings,
                degraded=routing.degraded,
                families=families,
            )

    return _PinRouter(base_router, pin_specs)


@dataclass
class RequestContext:
    """One request's routing input: router + selection + quota snapshot.

    `has_search_key` records only whether a Tavily search key was supplied
    (never the value). The quota snapshot holds counts only.
    """

    router: object
    allowed: set[str] = field(default_factory=set)
    pins: dict[str, str] = field(default_factory=dict)
    quota_snapshot: list[dict] = field(default_factory=list)
    has_search_key: bool = False
    quota_snapshot_token: object | None = None


def build_request_context(
    provider_keys: dict[str, str] | None,
    search_keys: dict[str, str] | None,
    selected: list[str] | None,
    pins: dict[str, str] | None,
    usage_snapshot: list[dict] | None,
) -> RequestContext:
    """Build the shared context for preflight and run (keys in, names out).

    Loads the client usage snapshot into the limiter (so capacity math sees
    max(server memory, client snapshot)) and snapshots per-bucket counts.
    """
    from src.core.keystore import reveal, wrap_keys

    allowed, _ = _resolve_selection(list(selected or []))
    resolved_pins = dict(pins or {})
    router = _filtered_router(dict(provider_keys or {}), allowed, resolved_pins)
    limiter = get_limiter()
    key_ids = {
        provider: fingerprint_key(key)
        for provider, key in (provider_keys or {}).items()
        if key
    }
    snapshot_token = limiter.set_usage_snapshot(
        usage_snapshot or [], owner_key_ids=key_ids
    )
    snapshot = []
    if hasattr(router, "quota_snapshot"):
        try:
            snapshot = router.quota_snapshot()
        except Exception:  # noqa: BLE001 — capacity advisory, fail open
            snapshot = []
    search_wrapped = wrap_keys(search_keys or {})
    has_search = bool(search_wrapped.get("tavily") and reveal(search_wrapped["tavily"]))
    return RequestContext(
        router=router,
        allowed=allowed,
        pins=resolved_pins,
        quota_snapshot=list(snapshot or []),
        has_search_key=has_search,
        quota_snapshot_token=snapshot_token,
    )
