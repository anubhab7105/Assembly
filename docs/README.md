# Assembly documentation

This directory contains the maintained product, architecture, security, privacy, workflow, and release documentation for Assembly. For the fastest setup path, start with the [root README](../README.md). For the contribution workflow and test expectations, read [CONTRIBUTING.md](../CONTRIBUTING.md).

## Current project references

- [Architecture](architecture.md) — component map, request lifecycle, APIs, configuration, and storage boundaries.
- [Product requirements](PRD.md) — current product scope, requirements, and design decisions.
- [Workflow](WORKFLOW.md) — planning, independent solving, consensus, challenge rounds, and synthesis.
- [Tech stack](TECH_STACK.md) — implementation choices, with historical recommendations called out.
- [Decision log](decisions.md) — architecture and product decisions with consequences.
- [Threat model](threat-model.md) — assets, trust boundaries, threats, mitigations, and remaining risks.
- [Security and prompt-injection defense](security.md) — untrusted web content, sanitization, and known limits.
- [Privacy](privacy.md) — what the browser, web backend, desktop app, and external providers may process or retain.
- [Attachments](attachments.md) — supported text formats, validation limits, retention boundaries, and prompt-injection handling.
- [Deployment](deploy.md) — web deployment configuration and operational notes.
- [Windows release](windows-release.md) — Tauri packaging instructions and the clean-machine verification checklist.

## Documentation conventions

The current implementation and configuration are the source of truth for behavior. Product requirements and workflow documents also record intended behavior and design decisions; they are not a substitute for tests. When a statement depends on the current code, verify it against `src/`, `frontend/src/`, `desktop/`, `models.yaml`, the dependency manifests, and the active GitHub Actions workflows.

Provider model IDs, availability, quotas, and terms change frequently. Confirm them against the provider's current documentation or dashboard and record the source/date when the repository configuration is updated. Benchmark conclusions must distinguish real graded results from synthetic fixtures or unverified pilot runs.
