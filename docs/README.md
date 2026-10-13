# Assembly documentation

This folder contains architecture and engineering notes for contributors. For a current local setup, begin with the root [README](../README.md). For contribution steps and test commands, read [CONTRIBUTING.md](../CONTRIBUTING.md).

## Core references

- [Architecture](architecture.md) — current component map, execution phases, API boundaries, configuration, and storage caveats.
- [Execution workflow](WORKFLOW.md) — how a run progresses through planning, solving, consensus, challenge rounds, and synthesis.
- [Tech stack notes](TECH_STACK.md) — implementation choices plus some historical design recommendations.
- [Product requirements](PRD.md) — product requirements and design intent.
- [Decision log](decisions.md) — design decisions and their recorded consequences.
- [Progress log](progress.md) — historical engineering notes and work in progress.

## Documentation status

Not every table or recommendation in older design documents is a statement about the currently implemented product. When they conflict, verify against the code and configuration: `frontend/package.json`, `requirements.txt`, `src/`, `frontend/src/`, `models.yaml`, and the active GitHub Actions workflow. Provider model IDs and quotas change frequently and must be checked before use.
