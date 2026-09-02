"""Serving the console's built page.

The bundle under `static/` is committed. That is a deliberate and slightly
unusual choice for a repository read as a work sample, and the reason is a
constraint from the build plan: a reviewer must be able to run the demo in under
fifteen minutes, and a JavaScript build step lands inside that budget. So the
JavaScript toolchain exists for developing this console and for nobody else -
`uv run` is the only command anyone needs, and Node never appears in the
prerequisites.

The page it serves asks the network for nothing. There is no webfont: the
typography is the operating system's own stack, which is what the reference this
console borrows from actually renders despite shipping a font of its own.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

STATIC_ROOT = Path(__file__).resolve().parent / "static"
"""Where `console/` builds to. Committed, and served as-is."""


class ConsoleNotBuilt(RuntimeError):
    """The bundle is missing, so there is nothing to serve.

    Only reachable in a working tree where the build output has been removed -
    a reviewer's clone always has it. Named rather than left as a stack trace
    from deep inside the static-files mount, because the fix is one command.
    """


def create_app() -> FastAPI:
    """The console as an app, so it can be tested without a port."""
    if not (STATIC_ROOT / "index.html").is_file():
        raise ConsoleNotBuilt(
            f"no built console at {STATIC_ROOT}. It is normally committed; "
            "rebuild it with `npm install && npm run build` in console/."
        )

    app = FastAPI(title="Denial Recovery Console", docs_url=None, redoc_url=None)
    # Mounted last, at the root, so later routes for run data are matched first.
    # `html=True` serves index.html for `/`.
    app.mount("/", StaticFiles(directory=STATIC_ROOT, html=True), name="console")
    return app
