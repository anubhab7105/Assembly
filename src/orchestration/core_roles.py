"""Assembly — core role guarantee (FR-2).

Every plan keeps at least 1 solver, 1 critic and (downstream) 1
synthesizer. The synthesizer is always created by the orchestrator after
debate, so this module guarantees the solver/critic pair in the planned
team and reports the synthesizer as guaranteed.

Trim order when the tier cap is tight: researcher first, then extra
solvers, then extra critics. The last solver and the last critic are
never dropped, even if that exceeds the cap (the cap yields, not the
guarantee).
"""

from __future__ import annotations


def ensure_core_roles(roles: list[str], tier_cap: int) -> tuple[list[str], list[str]]:
    """Enforce solver+critic presence within a tier cap.

    Args:
        roles: Planned team roles (solver/researcher/critic subset).
        tier_cap: Maximum team members for the tier.

    Returns:
        (final_roles, adjustments): final team roles in a stable order
        (solvers, researchers, critics as first seen) plus short human
        reasons for every add/drop.
    """
    try:
        cap = int(tier_cap)
    except (TypeError, ValueError):
        cap = max(2, len(roles))
    cap = max(cap, 2)
    working = [str(r) for r in (roles or [])]
    adjustments: list[str] = []

    # 1. Guarantee presence (called after planner, before cap trim, so adds
    # are visible even when the cap later forces drops elsewhere).
    if "solver" not in working:
        working.append("solver")
        adjustments.append("added solver (every plan needs one solver)")
    if "critic" not in working:
        working.append("critic")
        adjustments.append("added critic (every plan needs one critic)")

    # 2. Trim to the cap in the mandated drop order.
    def _drop_one(role: str) -> bool:
        # Drop the last occurrence, never the last solver/critic.
        indices = [i for i, r in enumerate(working) if r == role]
        if not indices:
            return False
        if role in ("solver", "critic") and sum(1 for r in working if r == role) <= 1:
            return False
        del working[indices[-1]]
        return True

    while len(working) > cap:
        if _drop_one("researcher"):
            adjustments.append("dropped researcher (tight tier cap)")
            continue
        # Extra solvers beyond the first.
        solvers = sum(1 for r in working if r == "solver")
        if solvers > 1 and _drop_one("solver"):
            adjustments.append("dropped extra solver (tight tier cap)")
            continue
        critics = sum(1 for r in working if r == "critic")
        if critics > 1 and _drop_one("critic"):
            adjustments.append("dropped extra critic (tight tier cap)")
            continue
        # Only the protected solver+critic (plus unrecognized roles) remain;
        # the guarantee wins over the cap.
        break
    return working, adjustments


def final_roles_with_synthesizer(team_roles: list[str]) -> list[str]:
    """Final role list for preflight/UI: team plus the guaranteed synthesizer."""
    roles = list(team_roles or [])
    if "synthesizer" not in roles:
        roles.append("synthesizer")
    return roles


def single_family_warning(families: list[str]) -> str | None:
    """Warning when only one model family is usable (critic cannot differ)."""
    unique = sorted({str(f) for f in (families or []) if str(f).strip()})
    if len(unique) == 1 and unique:
        return (
            f"Only one model family usable ({unique[0]}): critic shares "
            "the solvers' family; treat consensus with suspicion and "
            "confidence is lowered."
        )
    return None
