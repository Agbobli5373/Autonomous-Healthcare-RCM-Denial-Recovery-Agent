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

## The mock payer portal

No payer portal permits automated access, and this project does not evade bot
detection, so the demo drives a mock. Run it locally:

```bash
uv run rcm-agent serve-portal
```

It serves at <http://127.0.0.1:8080>; any user ID and password are accepted. The
markup deliberately carries no `data-testid`, no stable `id` and no ARIA — hooks
added by the mock's own author would prove nothing about operating software that
was never built to be automated. Four frictions are equally deliberate: the
worklist arrives by XHR, the claim the demo follows sits on page two, the EOB
opens in a new tab as a download, and the session expires once on a claim-detail
view so the agent has to sign in again.

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
