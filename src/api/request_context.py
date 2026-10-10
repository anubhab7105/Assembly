"""Assembly — per-request execution context (preflight + run share this).

One builder for provider keys, search-key presence, usage snapshots, and
model selection, so the preflight verdict and run routing cannot diverge.
Keys stay in memory only and are never logged (names alone are ever logged).
"""

from dataclasses import dataclass, field

from src.core.keystore import wrap_keys
from src.core.logging_config import logger
from src.providers.config import load_models_config
from src.providers.quota import get_limiter


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
    """Build a ModelRouter restricted to selected models + pin wrapper."""
    from src.providers.router import ModelRouter

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

    valid_pins = {}
    if pins:
        catalog_ids: set[str] = set()
        for spec in base_router.config.providers.values():
            catalog_ids.update(m.id for m in spec.models)
        if not allowed:
            full = load_models_config()
            for spec in full.providers.values():
                catalog_ids.update(m.id for m in spec.models)
        for role, model_id in list(pins.items())[:10]:
            if model_id in catalog_ids:
                valid_pins[str(role)] = model_id
            else:
                logger.warning("Run     │ ignoring unknown pin model")
    if not valid_pins:
        return base_router

    inner = base_router

    class _PinRouter:
        """Delegate to ModelRouter, forcing pinned models per role."""

        def __init__(self, wrapped: ModelRouter, pin_map: dict[str, str]) -> None:
            self._w = wrapped
            self._pins = pin_map
            self.config = wrapped.config

        def __getattr__(self, name: str):  # delegate everything else
            return getattr(self._w, name)

        def _apply_pin(self, decision, role: str):
            pinned = self._pins.get(role)
            if not pinned:
                return decision
            try:
                for pid, pspec in self.config.providers.items():
                    for m in pspec.models:
                        if m.id == pinned:
                            decision.model = pinned
                            decision.provider_name = pid
                            decision.family = m.family
                            return decision
            except Exception as exc:  # noqa: BLE001 — pin is best-effort
                logger.debug(f"Run     │ pin apply skipped: {exc}")
            return decision

        def route(self, agent_type: str, *a, **k):  # type: ignore[no-untyped-def]
            d = self._w.route(agent_type, *a, **k)
            return self._apply_pin(d, agent_type)

        def route_team(self, team: list, *a, **k):  # type: ignore[no-untyped-def]
            routing = self._w.route_team(team, *a, **k)
            for d, spec in zip(routing.decisions, team):
                role = spec.get("agent_type", "") if isinstance(spec, dict) else ""
                self._apply_pin(d, role)
            return routing

    return _PinRouter(inner, valid_pins)


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
    limiter.set_usage_snapshot(usage_snapshot or [])
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
    )
