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

## The two mock systems

The agent operates two unrelated systems, and both are mocks. Run them side by
side — they are deliberately nothing alike to look at, because in the demo video
they must not read as one thing.

```bash
uv run rcm-agent serve-portal
```

```bash
uv run rcm-agent serve-practice
```

### The payer portal

No payer portal permits automated access, and this project does not evade bot
detection, so the demo drives a mock.

It serves at <http://127.0.0.1:8080>; any user ID and password are accepted. The
markup deliberately carries no `data-testid`, no stable `id` and no ARIA — hooks
added by the mock's own author would prove nothing about operating software that
was never built to be automated. Four frictions are equally deliberate: the
worklist arrives by XHR, the claim the demo follows sits on page two, the EOB
opens in a new tab as a download, and the session expires once on a claim-detail
view so the agent has to sign in again.

### The practice-management system

Serves at <http://127.0.0.1:8081>. This is where the `CO-197` denial is refuted:
the patient's chart holds the Authorization the payer says was never on file,
with its number, its validity range and its covered HCPCS scope, beside the date
of service they have to be compared against.

No open-source EMR models US payer authorizations, so it is purpose-built rather
than an authorization stubbed into a spare field of something bigger. The agent
also writes a chart note back, which is why it cannot be static. Notes are held
in memory: they survive a reload, and a restart returns the system to a known
screen so a second take of the demo starts where the first did.

Sign-on accepts any credentials, but the demo does not type them. It restores a
saved Solari browser profile instead:

```bash
uv run rcm-agent practice-storage-state --url http://127.0.0.1:8081
```

That writes a Playwright `storageState` file, which is one of the documented
ways to create a Solari profile — so the second profile is reproducible from
this repository rather than from whoever last signed on by hand. It contains no
secret: the session id it carries is a constant in the source, and the system it
opens holds only synthetic records.

### Serving them from a Solari sandbox

The demo does not run the mocks on localhost. It uploads the working copy into a
sandbox, serves both there, and exposes each port with `preview_url` — no tunnel,
no PaaS, no deploy step:

```bash
uv run rcm-agent host-mocks
```

That prints a public URL for each mock and holds them up until you interrupt it.
It needs `SOLARI_API_KEY` in a gitignored `.env`.

**One sandbox does all three jobs** — both mocks and the analysis kernel, which
runs on a real EOB before the URLs are handed over. The Free tier allows one
concurrent sandbox and the agent visits the practice-management system while the
kernel is still needed, so this is forced by the plan rather than chosen.

If a run is killed rather than interrupted, its sandbox can keep the only slot
for far longer than the ten-minute TTL suggests, and the next run then fails at
`create`. See the `SANDBOX_TTL_MS` docstring for how to end an orphan.

The servers are health-checked *from inside the sandbox* before any URL is
handed out. A browser pointed at a port that has not finished binding fails in a
way that reads as a platform fault rather than as a race, and the recorded run
has to be unbroken.

The preview URL carries an access token in its query string. It is printed to
the terminal, because that is what you open — but the run directory records the
URL without it.

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
