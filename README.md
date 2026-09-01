# Autonomous Healthcare RCM Denial Recovery Agent

An agent that recovers denied medical claims by operating payer and
practice-management software directly — no APIs required. Built on Solari's
Cloud Browser and Sandbox primitives.

> **Work in progress.** This README is a placeholder; the full one — architecture
> diagram, setup path, and the project's deliberate departures from its original
> spec — is written in a later ticket.

## Quick start

```bash
uv sync
uv run rcm-agent run
```

Today that plays a scripted event sequence to exercise the run directory and the
progress panel. Real work replaces it slice by slice.

## Where things are

| | |
| --- | --- |
| Domain glossary | [`CONTEXT.md`](./CONTEXT.md) |
| Architecture decisions | [`docs/adr/`](./docs/adr/) |
| Research behind the decisions | [`docs/research/`](./docs/research/) |
| The plan, as issues | [decision map](https://github.com/Agbobli5373/Autonomous-Healthcare-RCM-Denial-Recovery-Agent/issues/1) |

## Development

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
```

The Solari smoke-test spike under `spikes/` needs its own extra:

```bash
uv sync --extra spike
```
