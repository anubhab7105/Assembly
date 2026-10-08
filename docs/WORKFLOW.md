# Assembly — Workflow

*v1.0 · October 8, 2026 · Companion to the PRD v1.0 and TECH_STACK.md*

This document has two parts: **Part A** is how one execution runs inside Assembly. **Part B** is how you build and ship it for the hackathon.

---

# Part A — Execution workflow

## 1. Pipeline overview

```text
USER: question + time budget (3 / 5 / 10 / 15 min)
   │
   ▼
[0] CAPACITY CHECK ── reads keys, families, quotas ──► "what can we afford?"
   │
   ▼
[1] PLANNER ── type, complexity, needs_research ──► team plan
   │
   ▼
[2] TEAM FORMATION ── roles + model families (distinct) ──► temporary team
   │
   ▼
[3] INDEPENDENT SOLVE (parallel, agents cannot see each other)
   │
   ▼
[4] PUBLISH to shared workspace (structured JSON)
   │
   ▼
[5] CONSENSUS CHECK ── score, open disagreements, new-info rate
   │            │
   │            └── too agreeable too early? ──► [5b] ADVERSARIAL ROUND
   ▼
 consensus? ── yes ──────────────────────────────────┐
   │ no, time left                                    │
   ▼                                                  │
[6] DEBATE / RESEARCH / VERIFY round ──► back to [5]  │
   │ no, time nearly up                               │
   └──────────────────────────────────────────────────┤
                                                      ▼
[7] SYNTHESIS ── final answer + uncertainty note + sources
   │
   ▼
USER: answer + sources (+ optional Insight Mode)
```

## 2. Execution states

```text
CREATED → CAPACITY_CHECK → PLANNING → TEAM_READY → SOLVING
        → EVALUATING ⇄ DEBATING → SYNTHESIZING → COMPLETED
                    ↘ (any state) → CANCELLED | FAILED_PARTIAL
```

| State | Meaning | Exit condition |
|---|---|---|
| CAPACITY_CHECK | Count usable keys, families and remaining quota | Plan feasible, or user offered a smaller plan |
| PLANNING | One cheap call classifies the question | Valid plan JSON (one retry on bad JSON) |
| SOLVING | Parallel independent solves | All agents done or timed out |
| EVALUATING | Compute consensus score and open disagreements | Decision: finalize, debate, or adversarial |
| DEBATING | One targeted round | Round finished or round timeout |
| SYNTHESIZING | Final answer built | Answer validated |
| FAILED_PARTIAL | Too many failures to continue | Best-effort answer with a clear warning |

Every state change is published as a progress event (section 8).

## 3. Planner output

```json
{
  "problem_type": "technical_comparison",
  "complexity": "medium",
  "needs_research": true,
  "needs_code_execution": false,
  "suggested_roles": ["solver", "solver", "researcher", "critic"],
  "estimated_rounds": 2
}
```

Rules: low complexity gets 2 agents and one critique pass; high complexity gets research and verification rounds. The plan is a suggestion; the capacity planner (next section) has the final say.

## 4. Capacity-aware planning

Free keys cannot support unlimited calls. Before starting, compute what is affordable.

```text
for each key:
    calls_now   = min(rpm_limit × minutes_in_budget, rpd_remaining)
total_calls     = sum(calls_now over keys) × 0.7        # keep a 30% safety margin
cost(plan)      = agents × (1 solve) + rounds × agents × (1 critique)
                  + searches + 1 synthesis + 1 planner
choose the largest plan with cost(plan) ≤ total_calls
if none fits the chosen tier: tell the user, offer the best smaller tier
```

Time reserve: keep `synth_reserve = max(25 s, 12% of budget)` for final synthesis. Never start a round if `remaining < estimated_round_time + synth_reserve`.

Estimated call counts (replace with measured numbers after your first benchmark):

| Tier | Agents | Rounds | Approx. calls |
|---|---|---|---|
| 3 min | 2–3 | 1 | 8–12 |
| 5 min | 3–4 | 2 | 15–22 |
| 10 min | 4–5 | 2–4 | 25–40 |
| 15 min | 5–6 | 3–5 | 40–60 |

## 5. Agents and their contract

Every agent returns validated JSON:

```json
{
  "agent_id": "agent_03",
  "position": "short statement of the answer or claim",
  "reasoning_summary": "brief, not full chain-of-thought",
  "confidence": 0.78,
  "evidence": [{"claim": "...", "source_id": "s2"}],
  "supports": ["agent_01"],
  "disagrees_with": ["agent_02"],
  "remaining_uncertainty": ["..."]
}
```

| Role | Job | Model family guidance |
|---|---|---|
| Solver | Solve independently, show assumptions | Different family per solver |
| Researcher | Search, collect and rank sources, attach evidence | Long-context model |
| Critic | Find flaws; ask "what could everyone be wrong about?" | Family **different** from the answer it reviews |
| Synthesizer | Write the final answer from the team's verified positions | Strongest available |

Validation: schema check → one retry with the error message → fallback to another family. `supports` and `disagrees_with` may contain only valid agent IDs (already implemented in your Fix B).

## 6. Consensus and stopping

Starting formula (tune the weights on your benchmark):

```text
score = 0.30 × agreement          # pairwise agreement among independent agents
      + 0.20 × calibrated_conf    # mean confidence, discounted if agents are often wrong
      + 0.25 × evidence_quality   # claims with credible sources and independent verification
      + 0.15 × (1 − contradiction_ratio)
      + 0.10 × stability          # position unchanged over the last round
```

| Decision | Condition |
|---|---|
| **Finalize** | score ≥ 0.85 **and** new_info_rate < 0.15 **and** no critical contradiction |
| **Adversarial round** | score ≥ 0.85 reached in round 1 **or** all agents agree with no external evidence |
| **Debate another round** | open disagreement or missing evidence **and** time remains for a round plus synthesis |
| **Force finalize** | remaining time < round estimate + synth_reserve, or quota nearly exhausted |

Final answer wording:
- score ≥ 0.85: state the answer normally.
- 0.60–0.85: state the answer and list the main remaining uncertainty.
- below 0.60: present the leading answer **and** the main alternative, and say consensus was not reached.

### Anti-echo checks

1. First pass is independent (agents never see each other's answer).
2. Claims need evidence; unsupported claims reduce `evidence_quality`.
3. Critic must use a different family from the position it attacks.
4. Adversarial prompt: "Assume the current consensus is wrong. Give the strongest counterargument and what would prove it."
5. Agents from the same family count as **one** vote when computing agreement.
6. A failed call is excluded from stabilization (your Fix D) so it cannot fake agreement.

## 7. Failure handling

| Failure | Detection | Action |
|---|---|---|
| Rate limit (429) | HTTP status | Back off with jitter; mark key cooling down; route to another key or family |
| Daily quota exhausted | Quota tracker or provider message | Remove key for the run; replan with the remaining keys |
| Invalid key | 401/403 | Tell the user which provider failed; continue without it |
| Provider outage or timeout | Timeout | Cancel that agent; replace with another family; keep going |
| Bad JSON from agent | Validator | Retry once; then fallback model |
| Two agents strongly disagree | Pairwise disagreement high | Create a verification task: search or code test, then re-evaluate |
| All but one family lost | Capacity check | Warn, continue single-family with extra caution, label answer lower confidence |
| Client disconnects | WebSocket close | Keep running; client re-attaches by execution ID |
| Deadline reached | Timer | Stop new work; synthesize from current positions; state uncertainty |

## 8. Progress events (backend → UI)

| Event | Payload (summary) |
|---|---|
| `execution.started` | id, tier, deadline |
| `plan.ready` | problem type, complexity, agent count |
| `team.ready` | roles with families (display names) |
| `agent.status` | role, activity text, state |
| `round.started` / `round.finished` | round number, goal |
| `disagreement.opened` / `disagreement.resolved` | short description |
| `source.found` / `source.verified` | title, domain |
| `consensus.updated` | score, new_info_rate |
| `quota.warning` | provider, remaining |
| `timer.tick` | seconds remaining |
| `synthesis.started` | none |
| `execution.completed` | answer, sources, confidence label, summary stats |
| `execution.failed_partial` | reason, best-effort answer |

Insight Mode (if approved) subscribes to an extra stream with who-disagreed-with-whom and the evidence that changed a position. It is off by default.

## 9. Key (BYOK) flow

**Desktop**
```text
Settings: user pastes key → Test call → store in Windows Credential Manager
Execution: backend reads key just-in-time → calls provider directly → never logs it
```

**Website**
```text
Browser holds key in memory → sends with execution request (HTTPS)
Backend keeps it in memory for that run only → calls provider → deletes at completion
```

## 10. Worked example (5-minute tier, medium question)

Question: "Is React better than Vue for a large cybersecurity platform?"

| Time | Step |
|---|---|
| 0:00 | Capacity check: Gemini, Groq, Cerebras available → plan for 4 agents, 2 rounds |
| 0:05 | Planner: technical comparison, medium, needs research |
| 0:15 | Solvers A (Gemini), B (Llama), C (Qwen) solve independently; Researcher searches ecosystem evidence |
| 1:15 | Positions published; consensus 0.62; disagreement on state-management scaling |
| 1:20 | Debate round: Critic (GPT-OSS) challenges claims; Researcher finds two supporting sources |
| 2:40 | Consensus 0.81; disagreement resolved; one open uncertainty on hiring market |
| 2:45 | Adversarial prompt: "assume the consensus is wrong" → counterargument weak |
| 3:30 | Consensus 0.88, new info low → finalize |
| 3:35 | Synthesis with sources and a note on remaining uncertainty |
| 4:10 | Answer delivered (under the 5:00 limit) |

---

# Part B — Build workflow (hackathon)

## 11. Phases and checklists

**Phase 0 — Make the MVP real (first)**
- [ ] Create free keys: Gemini, Groq, Cerebras (or OpenRouter), optionally Mistral
- [ ] Run one full question end to end
- [ ] Fix whatever breaks (expect JSON and rate-limit issues)

**Phase 1 — Reliability and capacity**
- [ ] Router uses model families (3 distinct)
- [ ] Quota tracker and 429 cooldown
- [ ] Capacity-aware planner and tier fallback message
- [ ] Key-masking log filter and key-leak test
- [ ] Adversarial round trigger

**Phase 2 — Benchmark**
- [ ] 30–50 questions with expected answers or a rubric
- [ ] `run_single.py` (best single free model) and `run_assembly.py`
- [ ] Optional majority-vote baseline
- [ ] Blind grading script and a results table

**Phase 3 — Frontend**
- [ ] Next.js + TypeScript + Tailwind project
- [ ] Key Setup wizard with Test buttons
- [ ] Chat, time selector, progress view, answer view, history
- [ ] WebSocket client with re-attach

**Phase 4 — Windows app**
- [ ] Next.js static export
- [ ] Backend bundled with PyInstaller
- [ ] Tauri shell starts the backend on a random local port with a token
- [ ] Keys in Credential Manager
- [ ] Installer builds and installs on a clean machine

**Phase 5 — Demo polish**
- [ ] Insight Mode (if approved)
- [ ] Recorded replay fallback
- [ ] Benchmark results slide
- [ ] 10 full rehearsals; fix every failure you see

**Phase 6 — Website (only if time allows or required)**
- [ ] Supabase auth, per-request keys, long-running backend host
- [ ] Never rely on this for the live demo

## 12. Daily working loop

1. Pick one checklist item.
2. Write or update a test (use the mock provider).
3. Implement; run the app with real keys on one question.
4. Log what happened: calls used, time, consensus, failures.
5. Commit with a clear message; keep `main` always runnable.

## 13. Benchmark workflow

```text
questions.jsonl → run_single.py (best single free model) ─┐
                → run_assembly.py (tier: 5 min)           ├→ answers.csv → grade.py (blind) → results.md
                → run_vote.py (optional)                  ─┘
```

Grading rules: shuffle and hide system names; auto-check answers where possible; fixed rubric otherwise; record calls and time per run; report failures honestly.

## 14. Demo-day checklist

- [ ] Keys from at least 3 families added and tested that morning
- [ ] Provider dashboards checked for remaining daily quota
- [ ] App runs from the local installer or script, not a sleeping free server
- [ ] Recorded replay ready and tested
- [ ] 3 rehearsed questions (one with a known single-model failure)
- [ ] Benchmark slide ready
- [ ] Backup: laptop charger, offline copy of slides, phone hotspot
- [ ] One-sentence pitch memorized: *"Ask once; a temporary expert team solves, challenges and verifies until the answer is strong enough."*
