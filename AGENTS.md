# AGENTS.md

## Agent skills

### Issue tracker

Issues live as GitHub issues in `Agbobli5373/Autonomous-Healthcare-RCM-Denial-Recovery-Agent`, driven by the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, using their default label strings. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Branching

One branch per ticket, named `ticket/<number>-<slug>` — for example
`ticket/26-domain-types-and-guardrails`. Branch from `main`, and open a pull
request referencing the ticket when the work is ready for review.

`ticket/` rather than `feat/`: not every ticket is a feature. Some are
measurement, documentation or fixtures, and a uniform prefix keeps the branch
list sorted by the thing that actually identifies the work.

Do not commit directly to `main`. The commits before this convention was
adopted did, which is why the early history looks different.

## Commit messages

Do not add `Co-Authored-By` trailers to commit messages. No agent attribution, no
`Generated with` footers — commits are authored by the committing developer alone.

Explain why the change is what it is, not what the diff already shows. Where a
decision departs from an issue, an ADR or the glossary, say so in the message.
