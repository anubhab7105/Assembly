# Assembly architecture

Assembly is a time-boxed, multi-agent orchestration system. The current web client is built with Next.js, React, TypeScript, and Tailwind CSS. The backend is Python/FastAPI, with orchestration logic and provider integrations under **src/**.

## Runtime overview

~~~mermaid
flowchart TD
    User[User question and time budget] --> Frontend[Next.js frontend]
    Frontend -->|Run request / progress stream| API[FastAPI API]
    Frontend <--> BrowserStore[Browser-local history and settings]
    API --> Orchestrator[Orchestrator]
    Orchestrator --> Capacity[Capacity and preflight checks]
    Capacity --> Planner[Planner and team formation]
    Planner --> Router[Model router and provider configuration]
    Router --> Agents[Independent agent calls]
    Agents --> Debate[Debate, research, and verification]
    Debate --> Consensus[Consensus and stopping decision]
    Consensus -->|More work if time/quota permit| Agents
    Consensus --> Synthesis[Synthesis with sources and uncertainty]
    Synthesis --> API
    Router <--> Providers[External model/search APIs]
    API -. dev or supported desktop path .-> LocalData[Local SQLite; OS keyring in desktop mode]
~~~

## Component responsibilities

| Component | Responsibility |
|---|---|
| **frontend/** | User interface, settings, browser-local data, request composition, and live progress display. |
| **src/main.py** and **src/api/** | FastAPI application, CORS and request limits, health and run endpoints, key checks, and event transport. |
| **src/orchestration/** | Execution lifecycle, planning, independent agent work, debate/research/verification, consensus, and synthesis. |
| **src/providers/** | Provider routing, model configuration, rate/quota handling, external model calls, and research/search integrations. |
| **models.yaml** | Provider/model metadata and configured limits; provider model names and quotas can change and must be verified. |
| **tests/** | Backend behavior and regression tests. **frontend/tests/** contains browser tests. |
| **docs/** | Product requirements, execution workflow, deployment guidance, decisions, and historical audit material. |

## Web and local data paths

### Hosted web mode

- The web backend is intended to be stateless: execution state is kept in memory for the active run rather than written to a server-side conversation database.
- The browser owns its local history and settings. Clearing browser/site data can remove them.
- Provider keys are sent with the relevant run request rather than being configured as shared operator keys. External providers receive the request data necessary to process the requested task.
- Because web runs depend on in-memory process state, deployments should not be assumed to provide durable run history or cross-instance recovery.

### Development and desktop modes

- Local development/desktop configuration can initialize local SQLite for local state and history.
- The desktop key-storage path uses the operating system keyring where supported by the current build.
- Desktop packaging and platform support are experimental; consult current release information and issues before relying on a packaged installer.

## Execution lifecycle

A typical run follows this sequence:

1. **Capacity and preflight:** inspect configured providers, keys, rate/quota budgets, concurrency, and the selected time tier.
2. **Planning and team formation:** classify the question, determine likely work, and choose roles/agent families that fit capacity.
3. **Independent solving:** collect separate first-pass positions before agents exchange arguments.
4. **Evaluation:** assess agreement, confidence, evidence, contradictions, stability, and remaining time.
5. **Debate, research, or verification:** perform another targeted round when useful and affordable; provider errors, quotas, and deadlines can shorten the run.
6. **Synthesis:** produce a final answer, source references where available, and uncertainty information.
7. **Streaming:** publish progress events to the UI while the run is active.

See [WORKFLOW.md](WORKFLOW.md) for detailed execution states, stopping rules, and event types.

## Reliability and security boundaries

- Consensus scores indicate the system's internal evaluation of an answer; they are not calibrated guarantees of factual correctness.
- Provider APIs are external dependencies and can rate-limit, fail, or change model/feature availability.
- Do not log credentials, authorization headers, or sensitive user prompts. Keep live API keys in local secret configuration or the intended per-request flow, never in source code.
- Web mode depends on correct deployment configuration, including an explicit **CORS_ALLOW_LIST** in production and a deployment-specific **QUOTA_SALT**.
- The repository does not currently provide user accounts or a hosted conversation database.

## Local development entry points

From the repository root, install backend development dependencies with **python -m pip install -r requirements-dev.txt**, configure **.env** from **.env.example**, set **QUOTA_SALT**, then run **python -m uvicorn src.main:app --reload**.

In another terminal, run **cd frontend**, **npm ci --legacy-peer-deps**, and **npm run dev**. Set **NEXT_PUBLIC_API_URL=http://localhost:8000** in **frontend/.env.local** if needed.

For exact steps and test commands, see the root [README.md](../README.md). For known issues in older documentation, see [doc-drift.md](doc-drift.md).
