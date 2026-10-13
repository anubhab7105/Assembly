# Assembly documentation

This index distinguishes documents intended to describe the current implementation from planning, historical, and audit material. Some older documents record earlier designs; do not treat them as proof that a feature is implemented.

## Start here

- [Project overview and local setup](../README.md) — what Assembly does, limitations, environment setup, tests, and the architecture at a glance.
- [Architecture](architecture.md) — current high-level runtime paths and component responsibilities.
- [Workflow](WORKFLOW.md) — execution stages, consensus behavior, event flow, and BYOK paths.
- [Technology stack](TECH_STACK.md) — framework and provider choices, including time-sensitive notes that should be re-verified.
- [Deployment guide](deploy.md) — current hosted frontend/backend deployment model and environment variables.
- [Contributing](../CONTRIBUTING.md) — fork, branch, test, formatting, and pull request workflow.
- [Security policy](../SECURITY.md) — private vulnerability reporting, exposed-key response, and support policy.
- [Code of Conduct](../CODE_OF_CONDUCT.md) — community expectations and enforcement.

## Product and engineering references

- [Current product requirements](PRD.md) — the primary product requirements document.
- [Technical decisions](decisions.md) — recorded architecture and implementation decisions.
- [Audit notes](audit.md) — point-in-time findings; not a guarantee of current status.
- [Documentation drift log](doc-drift.md) — known contradictions and outdated statements in older documents. Check it before relying on an older reference.
- [Demo script](demo-script.md) — demo flow and talking points.
- [Deployment](deploy.md) — hosted setup and operational environment.

## Historical or point-in-time material

- [PRD v1.0 snapshot](Assembly%20%E2%80%94%20Product%20Requirements%20Document%20v1.0.md) is a frozen historical copy; use [PRD.md](PRD.md) for current requirements.
- Audit notes, demo records, progress logs, benchmark reports, and decision records may describe the system at the time they were written. Read their dates and assumptions before treating them as current.
- Benchmark outputs and estimated provider capacities are development evidence, not a claim that Assembly is accurate for every domain or question.

If you find a documentation contradiction, please open an issue or a focused pull request with the file, section, and current code/configuration that supports the correction.
