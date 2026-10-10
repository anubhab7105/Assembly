"""Assembly — stateless web run (POST /api/run, SSE).

Web mode stores nothing: no database file, no disk writes. Runs live in
an in-memory registry with a TTL and a global concurrency cap. Keys,
questions and answers are held in memory for the run only and never
stored; logs carry metadata (run prefix, tier, timings, counts) only.
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.core.config import settings
from src.core.keystore import wrap_keys
from src.core.logging_config import logger
from src.core.rate_limit import check_rate_limit
from src.database.schemas import RunRequest
from src.orchestration.capacity import KeyBudget, heuristic_suggestion, plan_capacity
from src.providers.config import load_models_config
from src.providers.quota import get_limiter

router = APIRouter(prefix="/api/run", tags=["run"])

#: Machine-readable code for "no usable model family" rejections.
BLOCKED_CODE = "blocked_no_usable_keys"

#: Minimum distinct model families for a healthy team (mirrors catalog).
MINIMUM_FAMILIES = 3


@dataclass
class _RunEntry:
    run_id: str
    created_at: float
    task: asyncio.Task | None = None
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    done: bool = False
    usage: list[dict] = field(default_factory=list)


_runs: dict[str, _RunEntry] = {}
_runs_lock = asyncio.Lock()


def _now() -> float:
    return time.monotonic()


async def _sweep_expired() -> None:
    ttl = settings.run_ttl_seconds
    now = _now()
    expired = [rid for rid, e in _runs.items() if now - e.created_at > ttl]
    for rid in expired:
        entry = _runs.pop(rid, None)
        if entry is not None and entry.task is not None and not entry.task.done():
            entry.task.cancel()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


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


def _filtered_router(provider_keys: dict[str, str], allowed: set[str], pins: dict[str, str]):
    """Build a ModelRouter restricted to selected models + pin wrapper."""
    from src.providers.router import ModelRouter

    keys = wrap_keys(provider_keys or {})
    revealed = {p: k.get_secret_value() for p, k in keys.items() if k.get_secret_value()}
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


async def _execute_run(
    run_id: str,
    question: str,
    tier: int,
    provider_keys: dict[str, str],
    allowed: set[str],
    pins: dict[str, str],
    usage_snapshot: list[dict],
    entry: _RunEntry,
    search_keys: dict[str, str] | None = None,
) -> None:
    """Run the orchestrator, forwarding recorder events into the SSE queue."""
    from src.orchestration.orchestrator import Orchestrator

    limiter = get_limiter()
    limiter.set_usage_snapshot(usage_snapshot or [])
    router_override = _filtered_router(provider_keys, allowed, pins)
    orch = Orchestrator()
    # Use the per-run router (keys + selection) instead of the shared one.
    orch.router = router_override  # type: ignore[assignment]

    async def on_progress(event: dict) -> None:
        await entry.queue.put(dict(event))

    result_status = "failed"
    usage: list[dict] = []
    try:
        result = await orch.execute(
            execution_id=run_id,
            question=question,
            time_budget_minutes=tier,
            on_progress=on_progress,
            provider_keys=provider_keys or None,
            search_keys=search_keys,
            router_override=router_override,
        )
        result_status = result.status
        # Updated usage counters (counts only, never keys).
        usage = [
            {
                "provider": str(u.get("provider", "")),
                "model": str(u.get("model", "")),
                "count": int(u.get("count", 0) or 0),
                "tokens": int(u.get("tokens", 0) or 0),
            }
            for u in (usage_snapshot or [])
        ]
        usage.append(
            {
                "provider": "run",
                "model": "",
                "count": 1,
                "tokens": int(result.total_tokens or 0),
            }
        )
        entry.usage = usage
        await entry.queue.put(
            {
                "event_type": "run.finished",
                "run_id": run_id,
                "status": result_status,
                "usage": usage,
            }
        )
    except asyncio.CancelledError:
        await entry.queue.put(
            {"event_type": "run.finished", "run_id": run_id, "status": "cancelled"}
        )
    except Exception:  # noqa: BLE001 — run must finish as an event, not a crash
        logger.error("Run     │ background run failed")
        await entry.queue.put(
            {"event_type": "run.finished", "run_id": run_id, "status": "failed"}
        )
    finally:
        entry.done = True
        await entry.queue.put(None)  # type: ignore[arg-type] — SSE terminator
        limiter.set_usage_snapshot([])


@router.post("", response_class=StreamingResponse)
async def start_run(req: RunRequest, request: Request):
    """Stream a full run as SSE. Cancels on disconnect. Stateless."""
    ip = _client_ip(request)
    await check_rate_limit(
        f"ip:{ip}", "run", settings.rate_limit_run_per_min_per_ip, 60
    )
    await _sweep_expired()
    question = (req.question or "").strip()
    if not question:
        return JSONResponse(status_code=422, content={"detail": "Invalid request."})
    if len(question) > settings.max_question_chars:
        return JSONResponse(status_code=422, content={"detail": "Invalid request."})
    if req.time_budget_minutes not in (3, 5, 10, 15):
        return JSONResponse(status_code=422, content={"detail": "Invalid request."})
    if len(req.provider_keys or {}) > 20:
        return JSONResponse(status_code=422, content={"detail": "Invalid request."})

    # Capacity check with max(client snapshot, server memory). Advisory:
    # only an actually-infeasible verdict blocks; errors fail open.
    allowed, _ = _resolve_selection(list(req.model_selection.selected or []))
    pins = dict(req.model_selection.pins or {})

    # No usable model family: refuse before streaming or spending quota.
    gate_probe = _filtered_router(dict(req.provider_keys or {}), allowed, {})
    if _diversity_is_blocked(gate_probe, allowed):
        return JSONResponse(
            status_code=400,
            content={
                "code": BLOCKED_CODE,
                "detail": (
                    "No usable model families. Add keys for at least "
                    f"{MINIMUM_FAMILIES} model families (2 work with a "
                    "warning)."
                ),
                "minimum_families": MINIMUM_FAMILIES,
            },
        )
    try:
        limiter = get_limiter()
        limiter.set_usage_snapshot(
            [u.model_dump() for u in (req.usage_snapshot or [])]
        )
        probe = _filtered_router(dict(req.provider_keys or {}), allowed, {})
        snap = probe.quota_snapshot() if hasattr(probe, "quota_snapshot") else []
        keys = [
            KeyBudget(
                provider=e.get("provider", "unknown"),
                rpm_limit=e.get("rpm_limit"),
                rpd_remaining=e.get("rpd_remaining"),
                tpm_limit=e.get("tpm_limit"),
                tpd_remaining=e.get("tpd_remaining"),
            )
            for e in (snap or [])
        ]
        if keys:
            plan = plan_capacity(
                keys,
                req.time_budget_minutes,
                heuristic_suggestion(question),
                usage_snapshot=[u.model_dump() for u in (req.usage_snapshot or [])],
            )
            if not plan.feasible:
                limiter.set_usage_snapshot([])
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Tier not feasible with current quota."},
                )
    except Exception as exc:  # noqa: BLE001 — capacity advisory, fail open
        logger.debug(f"Run     │ capacity check skipped: {exc}")

    async with _runs_lock:
        active = sum(1 for e in _runs.values() if not e.done)
        if active >= settings.max_concurrent_runs:
            return JSONResponse(
                status_code=429, content={"detail": "Server busy, try again later."}
            )
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        entry = _RunEntry(run_id=run_id, created_at=_now())
        _runs[run_id] = entry

    # Family-diversity gate for this run's keys + selection (metadata only).
    run_diversity: dict[str, object] = {
        "level": "BLOCKED",
        "families_ready": [],
        "families_count": 0,
        "providers_count": 0,
        "reasons": [],
    }
    try:
        gate = (
            gate_probe.diversity_gate(set(allowed) if allowed else None)
            if hasattr(gate_probe, "diversity_gate")
            else None
        )
        if gate is not None:
            run_diversity = gate.to_dict()  # type: ignore[assignment]
        else:
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

    await entry.queue.put(
        {
            "event_type": "run.started",
            "run_id": run_id,
            "diversity": run_diversity,
        }
    )

    logger.info(
        f"Run     │ start tier={req.time_budget_minutes} "
        f"models={len(allowed) or 'auto'}"
    )
    entry.task = asyncio.create_task(
        _execute_run(
            run_id,
            question,
            req.time_budget_minutes,
            dict(req.provider_keys or {}),
            allowed,
            pins,
            [u.model_dump() for u in (req.usage_snapshot or [])],
            entry,
            search_keys=(
                dict(req.search_keys) if req.search_keys is not None else None
            ),
        )
    )

    heartbeat = max(5, settings.sse_heartbeat_seconds)

    async def event_stream():  # type: ignore[no-untyped-def]
        try:
            while True:
                try:
                    item = await asyncio.wait_for(entry.queue.get(), timeout=heartbeat)
                except asyncio.TimeoutError:
                    yield ":heartbeat\n\n"
                    continue
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
                if isinstance(item, dict) and item.get("event_type") == "run.finished":
                    # Drain terminator then close.
                    try:
                        term = await asyncio.wait_for(entry.queue.get(), timeout=2.0)
                        _ = term
                    except asyncio.TimeoutError:
                        pass
                    break
        except asyncio.CancelledError:
            # Client disconnected: cancel the run (stateless cancel).
            if entry.task is not None and not entry.task.done():
                entry.task.cancel()
            raise
        finally:
            async with _runs_lock:
                _runs.pop(run_id, None)
            logger.info("Run     │ finished")

    return StreamingResponse(event_stream(), media_type="text/event-stream")
