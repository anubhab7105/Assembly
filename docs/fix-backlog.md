# Fix backlog: items 5 to 14

## Group 2 (high)
5. Search visibility: when no search key is set and keyless sources return nothing, say so in the progress view and in the answer ("Web search returned nothing; no external sources were used").
6. CORS: the development default allows http://localhost:3000 and http://127.0.0.1:3000. Production requires CORS_ALLOW_LIST, or startup fails with a clear message. If /api/catalog fails, the frontend shows a visible banner ("Can't reach the Assembly server at <url>") with a Retry button, never an empty Settings page.
7. Rate limits: a run counts against the 5/min budget only after it passes validation and starts. Validation failures (422/413) use a separate, looser limit. Tests.
8. Client IP: add TRUSTED_PROXY_COUNT (default 0). Use the forwarded chain only when it is greater than 0; ignore spoofed forwarded headers otherwise. Tests including spoofing.

## Group 3 (medium)
9. Key Test (UPDATED; supersedes the earlier probe-prompt wording): validity is judged by authentication status, never by generated content. Use auth-only endpoints (provider list-models where it requires auth; OpenRouter's key-info endpoint, because its model list is public); confirm each choice in the provider docs and with a mocked 401 test. Fall back to a minimal generation only where no auth-only endpoint exists, with enough output tokens for thinking models, classified by HTTP status only. 200 = valid; 401/403 (and Gemini 400 API_KEY_INVALID) = invalid; 429 = "Key accepted; provider is rate-limiting right now" (amber, not an error), with Retry-After guidance when present; timeout or network error = "Couldn't reach <provider>; try again", never invalid; an empty or truncated generation = valid. 15 s client timeout with a spinner. Mock tests for every case, including the Gemini finish_reason cases. If the Gemini-specific fix already covers Gemini, extend the same classification to every provider.
10. Trim leading and trailing whitespace on save and before test. Mask keys as a fixed number of bullets with no characters from the key. Canary tests. (Skip any part already done.)
11. Family chip and model picker count only families from enabled providers that have a usable key; warn when the selection narrows to 2 families. The nvidia card must show its documented key variable name, or be hidden until it is documented.
12. Refresh or tab close during a run: show a beforeunload warning, and on return show "The run was cancelled when the page closed."

## Group 4 (so this cannot recur)
13. Real end-to-end test: production frontend build + the real backend process (web mode, no server keys) + Playwright, using a test-only replay/mock provider. The switch is honored ONLY when APP_ENV=test and a test flag is set; startup MUST fail if the flag is set when APP_ENV=production; no request can enable it. Journey: privacy acknowledgment, enter keys, pick models, ask a question, preflight feasible, run streams, answer shown, history saved, reload, unlock, history present. Failure cases: invalid key, no keys, server busy. Make this test part of the default merge gates.
14. Run `npm audit --omit=dev` and install and run pip-audit; report high and critical findings, do not auto-fix.

## Gates
Full offline suite, ruff and frontend lint/type-check on touched files, canary tests green, the new e2e green. Report test counts before and after, list any test changed or removed with a justification, update docs/decisions.md and docs/progress.md, print git diff --stat and commit hashes per group, then stop.
