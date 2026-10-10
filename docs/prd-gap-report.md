# PRD Gap Report — v1.1 (October 10, 2026)

Classifications match PRD v1.1. Every row cites the decision ID or PRD section.
FR and decision IDs are stable and never renumbered.

| ID | Item | v1.1 status | Basis |
| --- | --- | --- | --- |
| FR-41 | Website login (signup/login/OAuth, per-user history) | Done-different, superseded by D8 | No `src/api/auth.py`, no user tables; web is stateless (`src/api/run.py`), history in IndexedDB (`frontend/src/lib/storage.ts`). PRD §8.4 |
| FR-14 | Coding mode + security/performance reviewers | Optional / Deferred post-demo | `needs_code_execution` in `src/orchestration/planner.py` has no consumer (reserved). PRD §8.1 note |
| Insight toggle | Off-by-default Insight Mode switch | Optional | Timeline exists and is always visible (`frontend/src/app/executions/page.tsx`); no `Insight` control in `frontend/src/`. PRD §11.4; revisit after benchmark and rehearsals |
| FR-36 | Key health panel | Could (was Should) | Per-key statuses `unknown/valid/invalid/rate_limited/testing` in `frontend/src/components/keys-manager.tsx`; no consolidated exhausted-for-today panel. PRD §8.3 note |
| Theme | Theme setting (§11.5) | Optional | One Tailwind dark theme (`frontend/src/app/globals.css`); no user-facing switch |
| FR-11 | Budget enforcement | Must, reworded | Split across `src/orchestration/budget_controller.py` (time/token/agent/search) and `src/providers/quota.py` (per-provider quotas). PRD §8.1 note |
| R2 app | Windows app scaffold | Track R2, pre-release | `desktop/src/` scaffold only; `productName` still `tauri-app` (`desktop/src-tauri/tauri.conf.json`); no installer under `desktop/`; no clean-VM test recorded. PRD §9.1 |

Note: `BUILD_PROMPTS.md` does not exist in the repo or its git history.
Intended markings (recorded in `docs/decisions.md`): Prompts 6.1 and 6.2
"Superseded by D8 (stateless web)", 6.3–6.5 drop users/accounts/Postgres
wording, 8.4 "Optional".
