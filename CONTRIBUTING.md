# Contributing to Assembly

Thanks for helping improve Assembly. Contributions of code, tests, documentation, accessibility, bug reports, and careful technical feedback are welcome. The goal is not to add complexity for its own sake; the best changes make Assembly easier to understand, safer to use, or more reliable under real provider and network failures.

Please read the [Code of Conduct](CODE_OF_CONDUCT.md) before participating. By contributing, you agree to follow it.

## Before you start

1. Search [open issues](https://github.com/anubhab7105/Assembly/issues) and pull requests to avoid duplicating work.
2. For a large feature or architecture change, open an issue first and describe the user problem, proposed solution, and trade-offs. Small fixes and documentation corrections can usually proceed directly.
3. If a change is security-sensitive, do not open a public issue or pull request. Follow [SECURITY.md](SECURITY.md).

## Fork and create a branch

1. Fork the repository on GitHub.
2. Clone your fork and add the original repository as upstream.

~~~bash
git clone https://github.com/<your-user>/Assembly.git
cd Assembly
git remote add upstream https://github.com/anubhab7105/Assembly.git
git fetch upstream
git switch -c docs/short-description upstream/main
~~~

Choose a descriptive branch prefix:

- **feat/** for a user-facing feature.
- **fix/** for a bug fix.
- **docs/** for documentation.
- **test/** for tests or test infrastructure.
- **refactor/** for internal changes that should not alter intended behavior.

Use a separate branch for each logical change. Do not work directly on **main**.

## Set up your environment

### Backend

Use Python 3.11 or newer. From the repository root:

~~~bash
python -m venv .venv
# Activate: source .venv/bin/activate (macOS/Linux)
# Activate: .venv\Scripts\Activate.ps1 (Windows PowerShell)
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
~~~

Copy **.env.example** to **.env**, generate a unique **QUOTA_SALT**, and configure only the provider keys you need. The root **.env** is ignored by Git. Never put credentials into a committed example, fixture, issue, screenshot, or log.

Run the backend:

~~~bash
python -m uvicorn src.main:app --reload
~~~

### Frontend

From the repository root:

~~~bash
cd frontend
npm ci --legacy-peer-deps
~~~

For local development, create **frontend/.env.local** with **NEXT_PUBLIC_API_URL=http://localhost:8000** and **NEXT_PUBLIC_APP_MODE=dev** when those values are not already set. Start the frontend with **npm run dev**. The app is normally served at **http://localhost:3000**; keep the backend running in a separate terminal.

See the root [README.md](README.md) for the complete setup instructions and configuration notes.

## Test your changes

Run all checks relevant to the touched code and record their results in your pull request.

| Area | Recommended checks |
|---|---|
| Backend Python | **python -m pytest -q** |
| Python style | **python -m ruff check** and **python -m ruff format --check** on changed paths |
| Frontend lint | **cd frontend && npm run lint** |
| Frontend types | **cd frontend && npx tsc --noEmit** |
| Frontend security audit | **cd frontend && npm run audit:high** |
| Browser behavior | **cd frontend && npx playwright test** |
| Local migration behavior | **alembic upgrade head** when changing database models/migrations |

CI also runs Gitleaks and backend tests/migrations on pull requests. The Python dependency audit is currently advisory/non-blocking in CI. If your change affects another subsystem, add and run its appropriate test too.

### What evidence should a contribution include?

- **Bug fixes:** a regression test where practical, steps to reproduce, expected behavior, and actual behavior.
- **New behavior:** tests for the success path, important failure paths, validation, and edge cases. Use mocked provider/network calls where possible.
- **UI changes:** before/after screenshots or a short recording when the visual behavior materially changes, plus responsive behavior notes for relevant viewport sizes. Do not include keys, private data, or identifiable user content.
- **API, schema, or configuration changes:** sample requests/responses, migration notes if needed, and updated docs or **.env.example** entries that use placeholders only.
- **Performance or benchmark claims:** explain the setup, workload, sample size, baseline, and limitations. Do not present synthetic or tiny samples as proof of real-world accuracy.
- **Security changes:** describe the threat or failure mode being addressed, the protection added, and tests showing the unsafe path is blocked. Never publish a working exploit for an unresolved vulnerability.

Tests should be repeatable without a live provider key unless the issue specifically requires a provider integration test. If a test cannot be run locally, say why and identify the checks that still need to pass.

## Code and documentation style

- Prefer focused pull requests that do one thing well.
- Match the surrounding code style; avoid drive-by formatting changes.
- Python: use Ruff for lint and formatting on touched files.
- Frontend: use ESLint and the existing Prettier/Tailwind formatting conventions. For changed files, you can run **npx prettier --write <paths>**.
- Keep errors useful but avoid logging prompts, provider keys, authorization headers, or user-supplied sensitive content.
- Keep model IDs, provider limits, and other changeable provider details in configuration where the existing architecture expects them.
- Update documentation whenever commands, behavior, configuration, API contracts, or limitations change.
- Preserve compatibility where reasonable; pre-1.0 changes should still explain migration or behavior changes clearly.

## Submit a pull request

1. Commit focused changes with a clear message, such as **fix: handle provider timeout** or **docs: clarify local setup**.
2. Push your branch to your fork.
3. Open a pull request against **anubhab7105/Assembly**'s **main** branch.
4. Fill in the pull request template. Link the issue when applicable and describe the user-facing impact.
5. Include tests and evidence, list anything not tested, and confirm that no credentials or private data are included.
6. Respond constructively to review feedback. Maintainers may ask for smaller scope, clearer tests, or design discussion before merge.

A pull request is ready for merge when it has a clear purpose, appropriate tests/evidence, relevant docs updated, and required CI checks passing. Maintainers make the final merge decision; opening a pull request does not guarantee acceptance.

## Good places to start

Look for focused work in these areas:

- **Reliability:** deterministic tests for cancellation, timeouts, provider failure, retries, and partial answers.
- **Evaluation:** better reproducible benchmarks that distinguish synthetic fixtures from real-provider results.
- **Frontend UX and accessibility:** keyboard navigation, loading/error states, responsive layouts, and screen-reader semantics.
- **Security and privacy:** safer error/log paths, dependency hygiene, and tests that verify keys never appear in logs.
- **Developer experience:** environment validation, setup smoke tests, and docs that stay in sync with the code.

If no issue matches your idea, open a focused issue describing the problem and intended approach before taking on a large change.
