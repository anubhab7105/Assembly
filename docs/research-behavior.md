# Research-gate behavior (N-08)

What the planner, budget, providers, and composer do for borderline,
incomplete, and failed research — defined before any threshold tuning.
Thresholds change only with benchmark data, never by feel.

## Gate: is research needed?

`needs_research = LLM plan OR heuristic hints` (`RESEARCH_HINTS` in
`src/orchestration/capacity.py`: compare/versus/vs/latest/current/
research/source/evidence/best/better/review/ecosystem/market/2024-2026).
The heuristic only rescues (`False`→`True`), never overrides `True`.
A researcher joins within the tier cap; hint-bearing questions (e.g.
"compare battery chemistries") always research even when the LLM says no.

## Cases

| Case | Behavior |
|---|---|
| `needs_research=False` | No search calls, no search events. Answer stands on reasoning; composer states no external sources when nothing is cited. |
| Budget exhausted pre-search | UNREACHABLE today: one logical search per run on a fresh budget (`max_searches` 5–30 by tier). If multi-search ever lands, the run must emit a visible "search budget spent" notice and answer sourceless — never skip silently. |
| Some providers fail / 429 | Fall through the ordered chain (research: academic-first; else web-first). 429/402 → next provider. Run continues. |
| All providers fail or return empty | `[]` (never raises). Orchestrator emits researcher `agent.status`: "Web search returned nothing; no external sources were used." Budget records the attempt once. |
| Researcher call fails | Low-confidence error output; `verification.research_degraded`, "Research degraded" warning, reduced-research caveat in the answer; breaker trips after threshold-2 with a visible event. |
| Thin evidence at consensus | `evidence_quality < 0.50` (`consensus_evidence_floor`) counts as missing evidence → debate another round (time permitting). |
| Weak consensus at deadline | Finalize with uncertainty note (+ alternatives below 0.60). Never sound confident without consensus. |

## Thresholds (env-overridable, tune only via `bench/analyze.py`)

`consensus_evidence_floor` 0.50 · `RESEARCH_HINTS` keyword list ·
per-tier `max_searches` 5/10/20/30 · breaker threshold 2 · stagnation
epsilon 0.05. The N-08 instance ("compare" question, Research=False) is
already rescued by the OR-rule — verified: heuristic returns True.
