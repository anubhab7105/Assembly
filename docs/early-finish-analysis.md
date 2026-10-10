# Early-finish analysis — 64% consensus with 280 s unused (tier 5, no research)

Branch: `main` (clean at start; this file uncommitted). No code changed, no live provider calls, `.env` never opened.
Repro used `MockProvider` + real `ConsensusEngine` + real `Orchestrator` (offline; neutral question so `needs_research` stays `False` and no search runs).

## 1. Reproduction (MockProvider, real engine + orchestrator)

Setup: tier 5 (300 s), plan `needs_research=False`, 0 searches, 3 solve outputs —
solver 0.80 / researcher 0.65 / critic 0.70, paraphrased-agreeing positions (literally
different strings), 3 bare `evidence` items each (`source_id=""`), no `sources`,
no `supports`/`disagrees_with`, families gemini/llama/qwen, synthesis 0.78.

### 1a. Consensus engine directly (`src/orchestration/consensus.py`)

Round 1 (`evaluate(outputs, 1, time_for_round=True, quota_ok=True)`):

- score **0.6433 (64%)**, decision **DEBATE**
- reason: `"Score 64% below finalize threshold (85%) — debate another round."`
  (`consensus.py:364-368`, below-threshold branch)
- factors: `agreement=0.3333, calibrated_confidence=0.7167, evidence_quality=1.0, contradiction_ratio=0.0, stability=0.0`
  - agreement 1/3: no cross-family edges, so fallback is largest literal-position bloc/3
    (`_calculate_agreement`, `consensus.py:414-430`). Three paraphrases = 3 blocs.
  - confidence mean (0.80+0.65+0.70)/3 = 0.7167 (`_calculate_confidence`).
  - evidence 1.0: `min(1, 3/3)` per output — **bare claims count** (`_calculate_evidence_quality`, `consensus.py:438-463`).
  - stability 0.0: first evaluation, `new_info_rate=1.0`.
- `open_disagreements=[]`, `needs_debate(report)=False` (`stagnation.py:202-220`: no open edges and 1.0 >= floor 0.50),
  `has_external_evidence=False` (`consensus.py:528-533`: no `sources`, no `source_id`),
  `positions_match=False` (`consensus.py:535-538`: literal string equality).

Score math: `0.30*0.3333 + 0.20*0.7167 + 0.25*1.0 + 0.15*1.0 + 0.10*0.0 = 0.6433`.

Round 2 (same outputs): score 0.7433 (74%), still DEBATE below threshold, `needs_debate=False`.
Literal-match variant (same string x3, no evidence) instead gives 59% round 1 / 69% round 2 with
decision ADVERSARIAL — not this run.

### 1b. Full orchestrator (`src/orchestration/orchestrator.py`, `MockProvider` scripts as above)

- `planner` 1 call, `solve` 3 calls (0.80/0.65/0.70), `synthesis` 1 call (0.78). **Zero `debate` / `adversarial` calls.**
- `consensus.updated` round 1: score 0.6433, DEBATE, same reason as above.
- Loop log: `"no open disagreement or missing evidence — skipping further debate"`
  (`orchestrator.py:711-718`). `budget.can_debate()=True`, `should_force_synthesis()=False`,
  `remaining≈300 s` (real run ≈280 s; both satisfy `has_time_for_debate`: remaining > 60 s,
  `budget_controller.py:163-165`, and `can_start_round(30 s)` with reserve `max(25 s, 12%)`).
- Result: `status=completed, consensus_score=0.6433, agent_count=3, debate_rounds=1`,
  `verification={agents:3, families:3, rounds:1, disagreements_resolved:0, sources_verified:0, external_sources_used:False}`.

### Per-stage table

| Stage | Ran / skipped | Why (code ref) |
|---|---|---|
| Research | SKIPPED, 0 searches | `plan.needs_research=False` so `if plan.needs_research and budget.can_search()` false (`orchestrator.py:543`). Note: current planner OR-rule (`planner.py:469-510`) would flip a "better than" question to True; repro uses a neutral question to hold False. |
| Solve | RAN (3 calls) | `run_all_independent` (`agent_manager.py:197-266`). |
| Consensus r1 | RAN | `consensus_engine.evaluate(outputs, 1, ...)` (`orchestrator.py:659-667`). Score 64%, DEBATE. |
| Adversarial | SKIPPED (0 calls) | `_decide` branch 2 needs `positions_match` literal True (`consensus.py:332-343`); paraphrase => False. Branch 1 needs score>=0.85; 64% fails. Orchestrator strike never attempted. |
| Debate | SKIPPED (0 calls) | Decision DEBATE but `not needs_debate(report)` => break (`orchestrator.py:711-718`; `stagnation.py:202-220`). Bare claims push quality 1.0 over floor 0.50. |
| Verification | SKIPPED (effective) | No `verification` map is ever passed (`orchestrator.py:659-667,862-870` omit it; default `None` in `consensus.py:120`). Cross-bonus never applies; composer only summarizes counts. |
| Synthesis | RAN (1 call, 0.78) | Falls through to `SYNTHESIZING` (`orchestrator.py:923-965`). Final label from consensus 64% => Moderate. |

## 2. Against WORKFLOW §6, FR-5, FR-7, FR-9

WORKFLOW §6 (`docs/WORKFLOW.md:136-166`): Finalize needs score>=0.85 + new_info<0.15 + no critical
contradiction. Adversarial on score>=0.85 in round 1 **or** all-agree-no-external-evidence.
Debate on open disagreement or missing evidence with time left. Force-finalize only when
time/quota nearly out. Answer bands: >=0.85 normal, 0.60-0.85 + uncertainty, <0.60 + alternative.

- **Does the code finalize at 64% with no external evidence and 280 s unused? Yes.**
  Not via `FINALIZE` (never reached at 64%) but via `DEBATE` + the FR-5 early-break to synthesis.
  The run synthesizes a Moderate answer with zero verification calls and ~93% of the tier-5
  time budget unspent.
- **Which rule/branch allows it?** `orchestrator.py:711-718`: `if decision==DEBATE and not needs_debate(report): break`.
  `needs_debate` (`stagnation.py:202-220`) is False because `open_disagreements` is empty and
  `evidence_quality (1.0) >= evidence_floor (0.50)`. Quality counts bare claims
  (`consensus.py:453`), so "missing evidence" (0 searches, 0 sources, 0 `source_id`) reads as satisfied.
  The adversarial safety net misses because `_positions_match` is literal equality
  (`consensus.py:535-538`) while the three positions agree only semantically.
- **Intended or gap? Gap.** FR-5 ("debate only while open disagreement or missing evidence") intends to
  avoid redundant rounds, not to bless a 64% unverified answer with a full budget remaining.
  WORKFLOW §6's "missing evidence" and "all agents agree with no external evidence" both describe this
  run, yet neither fires. The adversarial branch order is correct; its predicates are too narrow
  (literal match; score-gated first branch), and the evidence predicate conflates quantity of bare
  claims with external verification.

FR-5 (PRD: debate only with open disagreement/missing evidence; each round must change something):
skipping is FR-5's letter but not its spirit here — "missing" should include "no external verification".

FR-7 (PRD: adversarial when agreement high too early): missed. Score-gate (>=0.85) and literal-match
gate both fail on paraphrased unanimous agreement at 64% with zero sources.

FR-9 (PRD: weak consensus states uncertainty): half-met. Composer does emit Moderate + uncertainty note
(`composer.py:246-338`; `events.py:381-387` bands), so the answer does not claim High. But it still
finalizes early instead of spending budget to reduce uncertainty first.

## 3. Why "1 debate round" with no debate calls in the token log

`debate_rounds` is `round_number`, which starts at **1 for the independent-solve round**
(`orchestrator.py:656`, returned as `debate_rounds=round_number` at `:1005` and event `:1055`,
summarized as `rounds` in `composer.py:346`). The debate `while` loop never iterates, so the counter
never increments, yet the result still reports 1. The token log only appends `stage="debate"` for
fresh debate-round calls (`orchestrator.py:844-857`) and `stage="adversarial"` for strikes
(`:742-754`); with both skipped, only `planner/solve/synthesis` appear. So "1 debate round" =
the solve round, not a critique wave. Same off-by-one feeds `verification.rounds`.

## 4. Minimal proposals (each with its rule; quota estimates)

Call budgets (WORKFLOW §4 / `budget_controller.py:97-124`, `capacity.py:87-91`):
3 min 8-12 calls (max 1 round, 5 searches), 5 min 15-22 (3 rounds, 10 searches),
10 min 25-40 (5 rounds, 20 searches), 15 min 40-60 (8 rounds, 30 searches).
Cost formula `agents + rounds*agents + searches + 2` (`capacity.py:266-268`).

(a) **Missing evidence counts as an open item** (implements WORKFLOW §6 "debate on missing
  evidence" + FR-5). Change `needs_debate` and the `_decide` thin-evidence branch to also require
  `has_external_evidence` (or a non-None verification map with >=1 cross-verified claim):
  `if open_dis or quality < floor or not has_external: DEBATE / needs_debate=True`.
  Do not count bare `source_id=""` claims toward the floor (cap bare contribution, e.g. at 0.3).
  Extra: forces >=1 debate wave when unverified: +agents calls (3 min +2-3, 5 min +3-4,
  10 min +4-5, 15 min +5-6) plus optional +1-2 searches. Fits all tiers (<=30% of call budget).

(b) **Adversarial on semantic unanimity without external evidence** (implements WORKFLOW §6
  second adversarial row + FR-7). Drop the literal `positions_match` requirement: trigger when
  `agent_count>=2 and not open_dis and not has_external` (optionally: agreement factor >=0.5 or
  contradiction==0 as the "agree" signal). Keep `select_adversarial_critic` + single-strike +
  fallback-to-debate (`orchestrator.py:719-761`, `consensus.py:221-243`). Extra: +1 critic call
  when it fires (all tiers); if no different-family critic, falls back to (a)'s one debate wave.
  Negligible quota impact (+1 vs 8-60 budget).

(c) **Minimum verification effort per tier before Moderate-or-lower may finalize** (implements
  WORKFLOW §4 tier table + §6 finalize + FR-8/FR-9). Gate the `needs_debate==False` break and any
  `FINALIZE` with score<0.85 on tier minima, e.g.: 3 min >=1 debate/adversarial or >=1 search;
  5 min >=1 debate/adversarial AND (>=1 search if `needs_research` else >=1 debate);
  10/15 min >=2 rounds + >=2/4 searches. Also thread `CitationManager.verification_map()` into
  `evaluate(..., verification=...)` so cross-verified claims actually score. Extra over today:
  3 min +2-4 calls, 5 min +4-6 calls, 10 min +8-12, 15 min +10-15 — each well inside the tier's
  20-60% headroom because budgets already assume 1-5 critique waves that today go unused.

(d) **Final confidence label never exceeds what the score allows** (implements WORKFLOW §6 answer
  bands + FR-9). Keep `confidence_label_for_score(min(consensus_score, ...))` as the sole label
  source (`composer.py:48-55`, `orchestrator.py:1030`); display synthesizer 0.78 as advisor text only,
  never as the header; always attach uncertainty note when <0.85 and alternative when <0.60, even on
  early-break paths. Extra: 0 calls (pure function).

Repro commands (offline): `repro_consensus.py` (engine factor sweep),
`repro64.py` (64% exact), `repro_orch2.py` (full orchestrator, MockProvider, neutral question).
Key files: `src/orchestration/consensus.py:291-368,438-463,528-538`,
`src/orchestration/orchestrator.py:656-718,844-857,1005,1030,1194-1259`,
`src/orchestration/stagnation.py:202-220`, `src/orchestration/budget_controller.py:97-165`,
`src/orchestration/capacity.py:87-98,266-268`, `src/api/events.py:381-387`,
`src/orchestration/composer.py:25-55,246-355`, `docs/WORKFLOW.md:136-166`, `docs/PRD.md` FR-5/7/8/9.
