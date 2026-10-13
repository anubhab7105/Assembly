# Assembly

**Assembly turns a question into a time-boxed team of AI agents that solve independently, challenge one another, check evidence, and synthesize a final answer with sources and uncertainty.**

Assembly is an experimental multi-agent orchestration project being prepared for open-source collaboration. It is for people who want to study, improve, or use structured AI collaboration instead of relying on one model response. Users bring their own provider API keys (BYOK); Assembly does not provide a shared pool of model credits.

## Why contribute?

Assembly is at the stage where thoughtful contributions can materially improve the project. Work on a real Python orchestration backend, a modern Next.js interface, provider reliability, testing, documentation, and safe handling of user-supplied keys.

Contributions are especially useful when they make Assembly more **reliable, verifiable, accessible, privacy-conscious, or easier to run**. First contributions do not need to be large: a reproducible bug report, a focused test, a clearer setup step, or a small accessibility fix can help every future user.

- Read [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow.
- Review the [documentation index](docs/README.md) and [architecture overview](docs/architecture.md).
- Browse [all open issues](https://github.com/anubhab7105/Assembly/issues). Good first contributions: [setup/documentation smoke check #8](https://github.com/anubhab7105/Assembly/issues/8), [keyboard accessibility tests #9](https://github.com/anubhab7105/Assembly/issues/9), and [provider development guide #10](https://github.com/anubhab7105/Assembly/issues/10).

## How Assembly works

1. **Plan:** inspect the question, time budget, available keys, and provider capacity.
2. **Solve independently:** create a temporary team of agents so the first answers are not built on one shared response.
3. **Challenge and verify:** use debate, research, and verification rounds when time and provider quotas allow.
4. **Evaluate and synthesize:** assess agreement, evidence, contradictions, and stability, then prepare an answer with sources and a note about remaining uncertainty.

The UI streams progress from the backend while an execution is running. Model-family diversity and available provider capacity influence which plans can be run.

## Architecture at a glance

~~~mermaid
flowchart TD
    U[User question and time budget] --> W[Next.js frontend]
    W -->|Run request and progress stream| API[FastAPI backend]
    W <--> LOCAL[Browser-local history and settings]
    API --> ORCH[Orchestration engine]
    ORCH --> CAP[Capacity and planning]
    CAP --> ROUTER[Model router and provider configuration]
    ROUTER --> AGENTS[Independent agent calls]
    AGENTS --> LOOP[Debate, research, verification and consensus loop]
    LOOP --> SYNTH[Synthesis and uncertainty notes]
    SYNTH --> API
    ROUTER <--> PROVIDERS[External model and search APIs]
    API -. dev / desktop modes .-> DB[Local SQLite and OS keyring where supported]
~~~

**Main components**

- **Frontend:** Next.js, React, TypeScript, and Tailwind CSS in the **frontend/** directory.
- **Backend:** Python and FastAPI; orchestration, capacity checks, provider routing, and API endpoints live under **src/**.
- **Providers:** calls go to external model and search services. In hosted web mode, provider keys are supplied with requests; development mode can read local environment configuration.
- **Local data:** hosted web mode is designed to keep run state in memory rather than store server-side user history. Browser-side history and settings are local to the user's browser. Development/desktop code can use local SQLite; desktop key storage uses the operating system keyring where supported.

See [docs/architecture.md](docs/architecture.md) for more detail.

## Who Assembly is for

- **Developers** experimenting with agent orchestration, async Python, event streaming, and modern web interfaces.
- **Researchers and evaluators** exploring model-family diversity, evidence-aware synthesis, and consensus mechanisms.
- **Contributors** who want to improve reliability, provider integration, UX, accessibility, security, testing, or developer documentation.
- **Power users** who have their own supported provider API keys and want to try time-boxed multi-agent workflows.

## Current status and limitations

Assembly is **experimental and pre-1.0**. Treat it as a project under active development, not as a guarantee of correctness or an audited decision system.

- **Consensus is not proof.** Multiple agents can agree and still be wrong. Verify important claims and sources independently.
- **External dependencies matter.** Model/search APIs may be unavailable, change their models or limits, or throttle requests. Free quotas and provider features change; check each provider's current terms and limits.
- **Bring your own keys.** Running real model tasks requires valid credentials for supported providers. Usage is subject to each provider's policies, quota, and billing settings.
- **Benchmark results are not yet a general quality guarantee.** Treat small samples, estimates, and synthetic benchmark fixtures as development evidence, not as proof of real-world accuracy.
- **No user accounts or hosted conversation database.** Hosted web mode is designed to be stateless, but browser data can be lost when site data is cleared. External providers receive the request content required to answer it; do not send secrets or sensitive data unless you have assessed the relevant policies.
- **Desktop packaging is experimental.** Do not assume that every desktop installer or platform is ready for production use. Check the current release notes and issues before relying on a packaged build.
- **Compatibility may change.** Before version 1.0, interfaces, configuration, and behavior may change without a migration guarantee.

## Run Assembly locally

### Prerequisites

- Python 3.11 or newer (CI currently uses Python 3.11).
- Node.js 20 and npm (CI currently uses Node.js 20).
- Git.
- API keys for the providers you plan to use for real model calls. You can still work on many UI and test tasks without live provider credentials.

### 1. Clone and install backend dependencies

~~~bash
git clone https://github.com/anubhab7105/Assembly.git
cd Assembly

python -m venv .venv
~~~

Activate the virtual environment:

~~~bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
~~~

Install the project and development/test dependencies:

~~~bash
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
~~~

### 2. Configure the backend

Create a local environment file. It is ignored by Git; never commit it.

~~~bash
# macOS / Linux
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
~~~

Generate a unique quota salt:

~~~bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
~~~

Copy the generated value into **QUOTA_SALT** in **.env**. For local development, keep **APP_MODE=dev**. Replace the example provider-key placeholders with your own valid keys, or clear the values for providers you are not using. Do not use real production credentials in local examples, tests, screenshots, or logs.

### 3. Start the backend

From the repository root, with the virtual environment active:

~~~bash
python -m uvicorn src.main:app --reload
~~~

The API should be available at **http://localhost:8000**. In development mode, the interactive API docs are available at **http://localhost:8000/docs**.

### 4. Install and start the frontend

Open a second terminal:

~~~bash
cd frontend
npm ci --legacy-peer-deps
~~~

Create **frontend/.env.local** if you need to override the local API endpoint:

~~~dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_APP_MODE=dev
~~~

Start the frontend:

~~~bash
npm run dev
~~~

Open **http://localhost:3000**. Leave both the backend and frontend running while developing. If your local environment already provides these frontend values, do not create a duplicate file.

## Tests and quality checks

Run the checks relevant to your change. Most contributions should run the matching checks locally before opening a pull request; CI runs the standard suite for pull requests to **main**.

### Backend

From the repository root:

~~~bash
python -m pytest -q
make lint
# For changed Python files not covered by make lint:
python -m ruff check path/to/changed/files
python -m ruff format --check path/to/changed/files
~~~

The repository Makefile also provides **make test**, **make lint**, and **make run**. The **make lint** target currently checks a defined subset of backend paths, so run Ruff directly on any additional Python files you changed.

### Frontend

From **frontend/**:

~~~bash
npm run lint
npx tsc --noEmit
npm run audit:high
npx playwright install chromium
npx playwright test
~~~

Playwright starts the frontend through its test configuration. The CI workflow also runs the high-severity frontend audit, Gitleaks, backend migrations/tests, and a Python dependency audit (currently configured as advisory/non-blocking).

Do not put real provider keys in tests. Prefer mocked network responses and deterministic fixtures so the suite can run without a paid API account.

## Documentation

Start at [docs/README.md](docs/README.md) for the architecture, workflow, technology stack, deployment guide, product requirements, and known documentation drift.

## Contributing and security

- Contributions: [CONTRIBUTING.md](CONTRIBUTING.md)
- Community expectations: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Vulnerability reports: [SECURITY.md](SECURITY.md)
- License: [Apache-2.0](LICENSE)

Thanks for helping make Assembly more useful, transparent, and dependable.
