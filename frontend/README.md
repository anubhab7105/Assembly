# Assembly frontend

This directory contains Assembly's web interface, built with Next.js, React, TypeScript, and Tailwind CSS. The UI configures model-provider keys, checks model readiness, submits investigations to the FastAPI backend, displays live progress, and renders final answers and sources.

For the overall project setup, see the [root README](../README.md). For architecture and data-storage boundaries, see [`docs/architecture.md`](../docs/architecture.md) and [`docs/privacy.md`](../docs/privacy.md).

## Requirements

- Node.js 20 or newer
- npm
- A running Assembly FastAPI backend for end-to-end use

## Install and run

From the repository root, create and activate the Python environment and configure `.env` as described in the root README. Then install the frontend dependencies:

```bash
cd frontend
npm ci --legacy-peer-deps
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The frontend uses the local backend at `http://localhost:8000` by default. To use a different API base URL, set `NEXT_PUBLIC_API_URL` in `.env.local` in this directory, without a trailing slash.

Run the backend and frontend in separate terminals. Starting the frontend alone does not provide model execution.

## Useful commands

Run these from `frontend/`:

```bash
npm run dev                 # Start Next.js development server
npm run lint                # ESLint
npx tsc --noEmit            # TypeScript type check
npm test                    # Frontend storage tests
npm run audit:high          # Check the configured high-severity dependency policy
npm run build               # Production frontend build
npx playwright test         # Browser regression tests
```

Playwright may require a browser to be installed first:

```bash
npx playwright install chromium
```

Do not report a test as passing unless it has actually completed. Some browser tests and production checks may require environment-specific setup; document any checks you could not run.

## Development notes

- Keep model IDs, provider families, and quota values in the repository's `models.yaml` catalog; do not hard-code provider details in UI components.
- Treat browser-persisted history and provider keys as sensitive local data. Do not log keys or include them in screenshots, test artifacts, issues, or pull requests.
- The web backend is designed to be stateless: run inputs and provider keys are transient backend memory, while UI-owned history and settings live in browser storage. See the privacy and architecture docs for exact boundaries.
- Prefer small, accessible UI changes and add regression tests for key setup, navigation, streaming, cancellation, privacy notices, responsive behavior, and storage failures.

See [`CONTRIBUTING.md`](../CONTRIBUTING.md) for the project-wide workflow and pull-request checklist.
