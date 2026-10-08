# Assembly Benchmark — `bench/`

Draft question set for testing the core hypothesis: a temporary team that
reasons independently, cross-examines, and verifies beats the best single
free-tier model on the same question.

## Files

- `questions.jsonl` — 40 draft questions, one JSON object per line.
- `README.md` — this file.
- Planned (not yet implemented): `run_single.py`, `run_assembly.py`,
  (`run_vote.py` optional), `grade.py` → results CSV / slide.

## Schema (one JSON object per line)

| Field | Type | Notes |
|---|---|---|
| `id` | string | Unique, e.g. `ms-01`, `logic-01`, `code-01`, `res-01` |
| `category` | string | `math_science` \| `logic_reasoning` \| `coding` \| `research` |
| `question` | string | Self-contained prompt, includes test cases where relevant |
| `answer_type` | string | `exact` \| `numeric` \| `rubric` |
| `reference_answer` | string | Draft answer. **Every value is prefixed `NEEDS HUMAN VERIFICATION`** — do not treat as ground truth until reviewed |
| `rubric` | array of strings \| null | Present (non-null) for `rubric` type; `null` otherwise |
| `difficulty` | string | `easy` \| `medium` \| `hard` |

## Counts

- 10× `math_science` (`ms-01`–`ms-10`): `numeric`/`exact`. Traps: average-speed harmonic mean, negation-vs-exponent precedence, conditional probability (1/3 not 1/2), digit-counting double-count, pH with water autoionization, ice-melt displacement, modular last digit, train+tunnel distance, vacuum free-fall, 1-is-not-prime.
- 10× `logic_reasoning` (`logic-01`–`logic-10`): all `exact`. Traps: bat-and-ball, lily-pad halving, passing-2nd-place, pigeonhole socks, fencepost off-by-one, mislabeled-boxes single-sample, rate invariance, knights/knaves, 3-switches-1-bulb, syllogism validity.
- 10× `coding` (`code-01`–`code-10`): all `exact` with testable expectations embedded in `question` (function signature + input/output cases: 32-bit overflow, FizzBuzz, palindrome normalization, Fibonacci base cases, merge, bracket stack, distinct second-largest, nested flatten, Gregorian leap rule, order-preserving dedupe).
- 10× `research` (`res-01`–`res-10`): all `rubric` with a short 4-criterion rubric each. Cover Tauri/Electron, citation hallucination, SQLite/Postgres, limit-verification methodology, prompt-injection defense, consensus-vs-vote, source comparison, BYOK handling, benchmark design, adversarial debate.

## Grading guidance (for future `grade.py`)

- `exact`: normalize (trim, case-fold, collapse whitespace/punctuation per
  question; accept listed equivalents, e.g. `2nd` ≡ `2`).
- `numeric`: parse float; accept tolerance where the question states a range
  (e.g. `ms-05` accepts 6.9–7.0).
- `rubric`: 1 point per rubric bullet; report per-criterion pass/fail plus total.
- `coding`: run the embedded cases as pytest-style asserts against the
  model's function (exact values in `reference_answer` drafts after review).

## Verification status

⚠️ **DRAFT — all 40 `reference_answer` values are marked
`NEEDS HUMAN VERIFICATION`.** A human reviewer must check every answer
(and every coding expectation and rubric) before this set is used for
scoring or slides. Suggested review pass:

1. Solve each question independently of the draft.
2. Run each `coding` case in Python.
3. Fix the draft, remove nothing else — keep the marker until that line is signed off, then delete just the marker for that line.

## Adding questions

- Keep lines self-contained (no external context needed).
- Prefer questions small single models commonly get wrong (see trap notes above).
- Keep `id` prefix per category and keep the 10/10/10/10 balance unless
  deliberately rebalancing (update this README + counts if so).
- Validate: `python -c "import json; [json.loads(l) for l in open('bench/questions.jsonl')]; print('ok')"`
