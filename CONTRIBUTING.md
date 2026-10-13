# Contributing to Assembly

Thanks for considering a contribution. Assembly is experimental, and contributions that improve reproducibility, reliability, privacy, accessibility, or documentation are especially useful. Please keep changes focused and make them easy to review.

## Before you start

1. Read the [README](README.md) and [architecture notes](docs/architecture.md).
2. Search existing issues and pull requests to avoid duplicating work.
3. For a new feature, major refactor, provider integration, or architectural change, open an issue first and describe the problem and intended approach.
4. Never include real API keys, personal data, production logs, or other secrets in a commit, test fixture, issue, screenshot, or pull request. For a suspected vulnerability, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Fork and branch

After the repository is public, use the standard fork workflow:

```bash
# Fork anubhab7105/Assembly on GitHub, then clone your fork
git clone https://github.com/<your-github-name>/Assembly.git
cd Assembly
git remote add upstream https://github.com/anubhab7105/Assembly.git
git fetch upstream
git switch -c docs/describe-your-change
```

Use a short descriptive branch name such as `fix/stream-cancellation`, `feat/provider-validation`, `test/replay-fallback`, or `docs/local-setup`. Branch from the current `main`. Keep unrelated changes in separate branches and commits.

## Install dependencies

Use Python 3.11+ and Node.js 20+.

```bash
# Repository root: create and activate .venv first
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

Set a unique random value for `QUOTA_SALT` in your local `.env`. Do not commit `.env` or real provider credentials.

Then install frontend dependencies:

```bash
cd frontend
npm ci --legacy-peer-deps
```

For local UI work, run the backend from the repository root in one terminal and the frontend from `frontend/` in another. See the [README quick start](README.md#quick-start) for the exact commands.

## Run checks

Run the checks relevant to your change before opening a pull request. The GitHub Actions workflow is the final shared baseline; it currently runs frontend dependency/security audit, ESLint, TypeScript checking, Playwright, Python dependency audit output, Alembic migrations, and pytest.

### Backend (from the repository root)

```bash
alembic upgrade head
pytest
```

For Python files you changed, format and lint those files:

```bash
ruff format path/to/changed_file.py
ruff check path/to/changed_file.py
```

Replace the example path with each Python file you changed. Prefer focused checks while working; the repository may still contain older code outside your change that needs separate cleanup.

### Frontend (from `frontend/`)

```bash
npm run audit:high
npm run lint
npx tsc --noEmit
npx playwright install chromium
npx playwright test
npm run build
```

Use Prettier for formatting changed frontend files, following the surrounding style:

```bash
npx prettier --write path/to/changed_file.tsx
```

The repository uses Playwright browser tests. When your change affects key setup, navigation, streaming, cancellation, privacy notices, or responsive UI, add or update a regression test. Capture screenshots for visible changes when they help reviewers reproduce the result.

### Testing principles

- Prefer deterministic, offline tests with mock/replay providers.
- Do not make ordinary tests depend on live provider keys or external API calls.
- Any test that must contact a real provider must be explicitly marked `@pytest.mark.live` and must not run by default.
- Add regression coverage for bugs, failure paths, cancellation, retries, and security-sensitive behavior where applicable.
- If a check cannot be run locally, say so in the pull request and provide the reason. Do not report a check as passing unless it actually passed.

## Code and documentation expectations

- Keep the scope small and explain the user-visible or developer-visible effect.
- Preserve existing public API and configuration behavior unless the change deliberately updates it.
- Keep model IDs, families, role support, and quota data in `models.yaml`; verify provider limits instead of guessing.
- Do not log or persist provider secrets. Do not add secrets to fixtures or captured output.
- Update relevant documentation and `.env.example` when configuration, setup, routes, storage, or behavior changes.
- Add database migrations when the schema changes. Explain upgrade/backward-compatibility considerations.
- Use accessible controls, clear empty/error/loading states, and responsive layouts.
- Avoid adding dependencies or changing orchestration, provider routing, quota enforcement, or key storage without explaining why in the issue/PR.

## Pull request checklist

Before submitting, make sure your pull request includes:

- A concise summary of what changed and why.
- A link to the issue or discussion, if one exists.
- Test commands run and their actual results, plus any checks skipped and why.
- Regression tests for bug fixes and meaningful new behavior.
- Screenshots or a short recording for user-visible UI changes, including viewport/device context where useful.
- Documentation updates for changed behavior, configuration, APIs, or setup.
- Confirmation that no real credentials, private data, or generated artifacts are included.

Open a pull request against `main`, fill in the pull-request template, and keep the PR focused. Maintainers may ask for changes, tests, or a smaller scope. A green check is necessary but does not replace human review.

## Maintainer workflow

The repository owner should protect `main` in GitHub Settings and require pull requests plus the CI status checks `build-and-test` and `backend-test` before merging. Disable force pushes and direct pushes where practical. Once the repository is public, enable private vulnerability reporting under **Settings → Security and quality → Advanced Security** and confirm notifications for security reports. These are repository settings and must be verified in GitHub itself; adding documentation alone does not turn them on.
