# Release Checklist

This document tracks pre-flight checks before an Assembly release. It was automatically generated and verified.

## Pre-flight Status

- [x] **All tests green**: `pytest tests/` ran and passed (334 passed, 1 skipped). **PASS**
- [x] **Canary key test green**: `test_key_leak.py` runs as part of the test suite and prevents accidental API key commits. **PASS**
- [ ] **Benchmark report current**: The current `bench/results/REPORT.md` displays a prominent warning that it uses synthetic demo data instead of live metrics. **FAIL**
  - *Fix plan*: Run the live benchmark pipeline locally (`bench/run_assembly.py`, `bench/run_single.py`, `bench/run_vote.py`) followed by `bench/grade.py` and `bench/analyze.py` to overwrite `REPORT.md` with real benchmark data.
- [x] **No TODO or FIXME in critical paths**: Grepped `src/` and `frontend/`—no lingering TODO/FIXME comments found. **PASS**
- [ ] **Models.yaml limits verified**: Checked `models.yaml`. It still contains `null` placeholders (e.g., `context_tokens`, `limits: {rpm: null, rpd: null, tpm: null}`) instead of real metrics. **FAIL**
  - *Fix plan*: The operator needs to log in to the dashboards for Gemini, Groq, Cerebras, OpenRouter, and Mistral, check the limits for their specific tier, and populate the `null` values with current real numbers as of today (October 9, 2026).
- [x] **.env files ignored**: Verified `.gitignore` correctly lists `/.env` and `.env.dev`. **PASS**
- [ ] **Dependency audit clean**: Cannot confidently assert that all dependencies are free of CVEs without a dedicated audit tool. **FAIL**
  - *Fix plan*: Run `pip-audit` or `safety check` locally on `requirements.txt` to identify and resolve any vulnerable dependencies before tagging the release.
- [ ] **Installer tested on a clean VM**: Not automatically testable. **FAIL**
  - *Fix plan*: Compile the Tauri app locally (`npm run tauri build`), copy the installer to Windows Sandbox or a clean Windows/macOS VM, and verify the app opens and securely uses the OS keyring without crashing.
- [x] **Replay demo works offline**: Checked `scripts/replay_run.py`. The CLI tool is fully functional and successfully plays back saved executions from `recordings/`. **PASS**
- [ ] **Deploy rollback tested**: Not automatically testable. **FAIL**
  - *Fix plan*: Push a broken commit to the `main` branch connected to Render. Verify the deployment fails or deploys successfully but can be rolled back via the Render dashboard instantly using the "Rollback to this deploy" button. Verify traffic routes correctly.
