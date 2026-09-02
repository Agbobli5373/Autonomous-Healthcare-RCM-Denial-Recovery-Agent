# A JavaScript toolchain for the console, and a committed bundle

The standing rule for this project was **Python only** — `uv`, `ruff`, `pytest`,
`pyright`, and no `package.json` anywhere. The operator console breaks it. The rule
is redrawn to **Python only at runtime**: a JavaScript toolchain exists under
`console/` for developing the console, its built output is committed to
`src/rcm_agent/console/static/`, and nobody running this demo installs Node.

## Why a front end at all

The console streams a run's events to the browser and rebuilds state there, so a page
that only re-rendered on the server would have to be re-decided as well as re-built.
The alternatives were weighed — server-rendered templates with HTMX, a Python-native UI
framework, hand-written DOM code — and each traded either the interaction quality the
console needs or a second unfamiliar idiom for the toolchain this avoids.

## Why the bundle is committed

Another standing constraint: **a reviewer must be able to run the demo in under fifteen
minutes.** A build step lands inside that budget, and `npm install` on a cold cache can
take most of it. Committing build output to a repository read as a work sample is
unusual enough to look like an accident, so it is written down here, in the README, in
`console/vite.config.ts` and in `rcm_agent/console/server.py` — every place someone
might meet it first.

`node_modules/` is not committed. The output ships; the toolchain that produced it does
not.

## The cost this creates, and what pays it

A committed artifact can drift from its source, and every test would still pass: the
TypeScript tests exercise the source, the Python tests exercise the output, and nothing
inherently ties them together. So the build stamps `static/source-digest.txt` with a
hash of its inputs, and `tests/test_console.py` recomputes it. A bundle built from
anything other than the committed source fails the suite.

## What does not change

The rules that decide anything stay in Python. The server attaches derived state to the
events it forwards, so the client renders what it is told rather than re-deriving it —
a project whose central claim is that its rules live in exactly one place does not
acquire a second copy of them in TypeScript.

The guest never receives any of this. `console` joins `agent` and `browser` in
`ORCHESTRATOR_ONLY`: the sandbox serves the mocks and runs the analysis kernel, and
nobody is looking at it.

## Consequences

- Working on the console needs Node; running the demo does not.
- A change to `console/src` is not finished until `npm run build` has been run, and the
  suite says so rather than leaving it to be noticed in a browser.
- The front end has its own quality bar — `tsc --noEmit` under strict, and `vitest` —
  alongside `ruff`, `pyright` and `pytest`.
