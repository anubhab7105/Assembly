"""Assembly — per-request execution context (preflight + run share this).

One builder for provider keys, search-key presence, usage snapshots, and
model selection, so the preflight verdict and run routing cannot diverge.
Keys stay in memory only and are never logged (names alone are ever logged).
"""

import asyncio
from dataclasses import dataclass, field

from src.core.keystore import wrap_keys
from src.core.logging_config import logger
from src.providers.config import load_models_config
from src.providers.quota import fingerprint_key, get_limiter


def _resolve_selection(selected: list[str]) -> tuple[set[str], dict[str, str]]:
    """Validate selected model ids; Auto is represented by an empty selection."""
    from src.providers.config import provider_limits_issue
    from src.providers.router import PinViolationError

    raw = selected or []
    if len(raw) > 50:
        raise PinViolationError("Select no more than 50 models.")
    wanted = list(dict.fromkeys(value.strip() for value in raw if value and value.strip()))
    if not wanted:
        return set(), {}

    catalog = load_models_config()
    known: dict[str, str] = {}
    disabled: set[str] = set()
    unready: dict[str, str] = {}
    for provider_id, spec in catalog.providers.items():
        for model in spec.models:
            if not spec.enabled:
                disabled.add(model.id)
                continue
            issue = provider_limits_issue(provider_id, spec)
            if issue:
                unready[model.id] = issue
            else:
                known[model.id] = provider_id

    for model_id in wanted:
        if model_id in disabled:
            raise PinViolationError(
                f"Selected model {model_id!r} belongs to a disabled provider."
            )
        if model_id in unready:
            raise PinViolationError(
                f"Selected model {model_id!r} is not routable: {unready[model_id]}"
            )
        if model_id not in known:
            raise PinViolationError(
                f"Selected model {model_id!r} is not in the enabled model catalog."
            )
    return set(wanted), {model_id: known[model_id] for model_id in wanted}




async def verify_run_provider_keys(
    provider_keys: dict[str, str] | None,
    selected: list[str] | None,
) -> tuple[dict[str, str], list[str], list[str]]:
    """Verify the exact keys and models supplied for this preflight/run.

    Provider enablement is permission to configure a provider. A key becomes
    eligible for this request only after its own auth-only model-list test
    succeeds and the provider's quota metadata is fresh and complete. The
    returned model ids are limited to models confirmed for those keys.
    """
    from src.api.keys import verify_provider_key
    from src.core.keystore import clean_key
    from src.providers.config import load_models_config, provider_limits_issue
    from src.providers.router import PinViolationError

    catalog = load_models_config()
    wanted = list(dict.fromkeys(
        value.strip() for value in (selected or []) if value and value.strip()
    ))
    if len(wanted) > 50:
        raise PinViolationError("Select no more than 50 models.")
    selected_providers: dict[str, str] = {}
    known_models: dict[str, str] = {}
    disabled_models: set[str] = set()
    for provider_id, spec in catalog.providers.items():
        for model in spec.models:
            if spec.enabled:
                known_models[model.id] = provider_id
            else:
                disabled_models.add(model.id)
    for model_id in wanted:
        if model_id in disabled_models:
            raise PinViolationError(
                f"Selected model {model_id!r} belongs to a provider that is not permitted."
            )
        provider_id = known_models.get(model_id)
        if provider_id is None:
            raise PinViolationError(
                f"Selected model {model_id!r} is not in the permitted model catalog."
            )
        selected_providers[model_id] = provider_id

    supplied = {
        str(provider).strip(): clean_key(key)
        for provider, key in (provider_keys or {}).items()
        if str(provider).strip() and clean_key(key)
    }
    required_providers = set(selected_providers.values()) if wanted else set(supplied)
    if not required_providers:
        return {}, [], ["No API keys were supplied for this run."]
    for provider_id in required_providers:
        if not supplied.get(provider_id):
            raise PinViolationError(
                f"Models from {provider_id!r} require an API key for this run."
            )

    semaphore = asyncio.Semaphore(8)

    async def check_one(provider_id: str, key: str):
        spec = catalog.providers.get(provider_id)
        if spec is None:
            return provider_id, None, "Provider is not in the enabled model catalog."
        if not spec.enabled:
            return provider_id, None, "Provider is not permitted in the current catalog."
        async with semaphore:
            result = await verify_provider_key(provider_id, key, catalog=catalog)
        if not result.valid:
            return provider_id, None, result.message or "The API key test failed."
        verification = result.verification
        if verification is None:
            return provider_id, None, "The provider did not return verification metadata."
        if not verification.quota_metadata_ready:
            return (
                provider_id,
                None,
                verification.quota_metadata_issue
                or "Quota metadata is missing or stale; update it from the provider dashboard.",
            )
        available = {
            model.id
            for model in verification.models
            if model.available is True
        }
        if not available:
            return (
                provider_id,
                None,
                "The key test did not confirm any configured model is available for this key.",
            )
        # Keep the shared readiness guard as a second check, using the same
        # source/date/limits policy that the router and capacity limiter use.
        issue = provider_limits_issue(provider_id, spec)
        if issue:
            return provider_id, None, issue
        return provider_id, available, None

    checks = await asyncio.gather(
        *(
            check_one(provider_id, supplied[provider_id])
            for provider_id in required_providers
            if provider_id in supplied
        )
    )
    valid_keys: dict[str, str] = {}
    models_by_provider: dict[str, set[str]] = {}
    issues: list[str] = []
    for provider_id, available, issue in checks:
        if issue:
            issues.append(f"{provider_id}: {issue}")
            continue
        valid_keys[provider_id] = supplied[provider_id]
        models_by_provider[provider_id] = available or set()

    if wanted:
        for model_id in wanted:
            provider_id = selected_providers[model_id]
            if provider_id not in valid_keys:
                detail = next(
                    (item for item in issues if item.startswith(f"{provider_id}:")),
                    f"{provider_id}: the key is not verified for this run.",
                )
                raise PinViolationError(
                    f"Selected model {model_id!r} is not ready: {detail}"
                )
            if model_id not in models_by_provider.get(provider_id, set()):
                raise PinViolationError(
                    f"Selected model {model_id!r} was not confirmed available for the supplied {provider_id!r} key."
                )
        return valid_keys, wanted, issues

    eligible_models = sorted(
        model_id
        for available in models_by_provider.values()
        for model_id in available
    )
    return valid_keys, eligible_models, issues

def _diversity_is_blocked(router: object, allowed: set[str]) -> bool:
    """True when fewer than two usable solver/critic families are available.

    Routers with a family diversity gate use it; test doubles fall back to
    catalog models that support at least one core reasoning role.
    """
    gate = None
    diversity_gate = getattr(router, "diversity_gate", None)
    if callable(diversity_gate):
        try:
            gate = diversity_gate(set(allowed) if allowed else None)
        except Exception:  # noqa: BLE001 — gate trouble reads as blocked
            return True
    if gate is not None:
        return gate.level == "BLOCKED" or getattr(gate, "families_count", 0) < 2
    catalog = load_models_config()
    fams: set[str] = set()
    roles: set[str] = set()
    for spec in catalog.providers.values():
        if not spec.enabled:
            continue
        for model in spec.models:
            if (not allowed or model.id in allowed) and (
                "solver" in model.roles or "critic" in model.roles
            ):
                fams.add(model.family)
                roles.update({"solver", "critic"}.intersection(model.roles))
    return len(fams) < 2 or not {"solver", "critic"}.issubset(roles)


def diversity_payload(router: object, allowed: set[str]) -> dict[str, object]:
    """Family-diversity metadata for run.started events (names only)."""
    payload: dict[str, object] = {
        "level": "BLOCKED",
        "families_ready": [],
        "families_count": 0,
        "providers_count": 0,
        "roles_ready": [],
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
        logger.debug("Run     │ family gate skipped (type=%s)", type(exc).__name__)
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
    if len(pins) > 10:
        raise PinViolationError("Pin no more than 10 model roles.")
    valid_roles = {"solver", "researcher", "critic", "synthesizer", "planner"}
    for role, model_id in pins.items():
        role = str(role).strip()
        model_id = str(model_id).strip()
        if not role or not model_id or role not in valid_roles:
            raise PinViolationError("A model pin contains an empty or unsupported role/model.")
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
                "Add a valid API key and verify quota metadata, then retry."
            )
        if not base_router._usable_model(provider_id, model.id):
            raise PinViolationError(
                f"Pinned model {model_id!r} is exhausted or cooling down for {role!r}. "
                "Choose another model or retry after its quota resets."
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
            if not self._w._usable_model(provider_id, model.id):
                raise PinViolationError(
                    f"Pinned model for {role!r} is unavailable due to quota or cooldown. "
                    "Choose another available model or retry after the quota resets."
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

        def fallback_for(self, decision, error):  # type: ignore[no-untyped-def]
            # A role pin is strict across retries too. Never let the router's
            # normal fallback chain silently substitute another model.
            if getattr(decision, "role", "") in self._pins:
                return None
            return self._w.fallback_for(decision, error)

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
            if len(families) < len(routing.families):
                raise PinViolationError(
                    "Role pins reduce the team's final model-family diversity. "
                    "Choose pins from different families or remove conflicting pins."
                )
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
    provider_issues: list[str] = field(default_factory=list)

    async def aclose(self) -> None:
        """Release resources owned by this short-lived request router."""
        close_router = getattr(self.router, "aclose", None)
        if callable(close_router):
            await close_router()


def build_request_context(
    provider_keys: dict[str, str] | None,
    search_keys: dict[str, str] | None,
    selected: list[str] | None,
    pins: dict[str, str] | None,
    usage_snapshot: list[dict] | None,
    provider_issues: list[str] | None = None,
) -> RequestContext:
    """Build the shared context for preflight and run (keys in, names out).

    Loads the client usage snapshot into the limiter (so capacity math sees
    max(server memory, client snapshot)) and snapshots per-bucket counts.
    """
    from src.core.keystore import reveal, wrap_keys

    allowed, selected_providers = _resolve_selection(list(selected or []))
    resolved_pins = dict(pins or {})
    supplied_keys = dict(provider_keys or {})
    from src.providers.router import PinViolationError

    for provider_id in set(selected_providers.values()):
        if not str(supplied_keys.get(provider_id, "")).strip():
            raise PinViolationError(
                f"Selected models from {provider_id!r} require a saved API key for that provider."
            )
    router = _filtered_router(supplied_keys, allowed, resolved_pins)
    live_router = getattr(router, "_w", router)
    unavailable = sorted(
        provider_id
        for provider_id in set(selected_providers.values())
        if provider_id not in getattr(live_router, "_providers", {})
    )
    if unavailable:
        raise PinViolationError(
            "Selected models are unavailable for providers: "
            + ", ".join(unavailable)
            + ". Test the saved API key and verify its quota metadata."
        )
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
        provider_issues=list(provider_issues or []),
    )
