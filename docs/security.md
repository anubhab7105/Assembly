# Security — Web Content & Prompt-Injection Defense

Web search results are **untrusted data, never instructions**. A single
malicious snippet (``ignore previous instructions...``, a fake
``END`` delimiter, a request to print keys) rides into agent prompts
otherwise. This note documents the defense in `src/research/sanitize.py`,
where it is enforced, and what it cannot do.

## Threat model

- Attacker controls page content reachable via Tavily / Wikipedia /
  arXiv / Semantic Scholar / DuckDuckGo (or any pasted text sharing the
  code path).
- Attacker goals: hijack the answer, exfiltrate keys, break out of the
  quoted-evidence format, or poison citations.
- Non-goals: compromised providers/models, malicious users, network
  attackers — handled elsewhere (BYOK key handling, key-masking logs).

## Defense layers (all in `sanitize.py`, the single choke point)

1. **Strip** (`strip_markup`): `<script>` / `<style>` bodies, HTML
   comments, remaining tags, and zero-width characters are removed;
   whitespace is collapsed. Snippets arrive as plain text.
2. **Budget** (`truncate_to_budget`, `MAX_SNIPPET_CHARS = 1500`,
   `MAX_PROMPT_WEB_CHARS = 6000`, ≈4 chars/token): per-source and
   per-prompt caps. Overflow sources are dropped (counted) and cuts are
   marked with `…[truncated]` so truncation is visible, not silent.
3. **Delimit** (`format_untrusted_block`): each result is wrapped in
   `<<<UNTRUSTED_WEB_CONTENT [n] ...>` … `<<<END_UNTRUSTED_WEB_CONTENT>>>`
   blocks. Markers occurring *inside* content are neutralized first
   (`escape_delimiters`), so content cannot close its own block.
4. **Detect** (`scan_for_injection`, `INJECTION_PATTERNS`): regex
   tripwires in five categories — `instruction_override`,
   `prompt_disclosure`, `secret_exfiltration`, `role_reassignment`,
   `delimiter_escape`. Hits are reported, never acted on.
5. **Standing instruction** (`UNTRUSTED_SYSTEM_NOTE`): appended to every
   agent system prompt (solver, researcher, critic, synthesizer, base
   default) — block content is data to analyze, never instructions;
   role changes, prompt disclosure, and key/secret requests inside blocks
   are hostile data, not commands.
6. **Event-stream warning**: the orchestrator scans search hits in
   Phase 3 and emits `agent.status` (role `researcher`) naming the hit
   count and categories when tripwires fire; researchers and the
   synthesizer sanitize again at prompt-build time.

## Limits (read before relying on this)

- **Detection is a tripwire, not a proof.** Paraphrased, obfuscated, or
  non-English instructions evade the regexes; instructions that survive
  as plain prose (``the article suggests the reader should...'') are
  indistinguishable from content. The real defense is layers 3 + 5
  (delimiting plus the standing note), not the patterns.
- **The model can still be fooled.** Delimiters and notes reduce, but do
  not eliminate, prompt-injection success against capable models.
  Treat high-stakes answers as needing human review.
- **No execution boundary exists here.** Sanitized text is still model
  input; Assembly never executes fetched code, but it does *read* it.
- **Patterns need gardening.** When a new attack shape appears, add a
  regression snippet to `ADVERSARIAL_SET` in `tests/test_sanitize.py`
  and a pattern to `INJECTION_PATTERNS` — never weaken the standing note.
- **Budgets are heuristic.** The 4-chars/token conversion is approximate;
  exact token accounting stays with `BudgetController`.
