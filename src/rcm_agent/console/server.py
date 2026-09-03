"""Serving the console: its built page, and the run it reads.

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

Run data arrives over a socket rather than in the page, because opening a
finished run and watching a live one should be the same operation - and a later
ticket makes it one by leaving this connection open instead of closing it.
"""

# pyright: reportUnusedFunction=false
# Route handlers are registered by decoration, not called by name - the same
# pragma the mock servers carry, for the same reason.

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from rcm_agent.console.replay import replay
from rcm_agent.matrix import PHASES

STATIC_ROOT = Path(__file__).resolve().parent / "static"
"""Where `console/` builds to. Committed, and served as-is."""

DEFAULT_RUNS = Path("runs")


class ConsoleNotBuilt(RuntimeError):
    """The bundle is missing, so there is nothing to serve.

    Only reachable in a working tree where the build output has been removed -
    a reviewer's clone always has it. Named rather than left as a stack trace
    from deep inside the static-files mount, because the fix is one command.
    """


def create_app(runs_dir: Path | None = None) -> FastAPI:
    """The console as an app, so it can be tested without a port."""
    if not (STATIC_ROOT / "index.html").is_file():
        raise ConsoleNotBuilt(
            f"no built console at {STATIC_ROOT}. It is normally committed; "
            "rebuild it with `npm install && npm run build` in console/."
        )

    root = DEFAULT_RUNS if runs_dir is None else runs_dir
    app = FastAPI(title="Denial Recovery Console", docs_url=None, redoc_url=None)

    @app.websocket("/events")
    async def events(socket: WebSocket) -> None:
        """Replay every run, then hold the connection open.

        Held rather than closed so the client can tell "there is nothing more
        yet" from "the server went away" - and so that following a live run is a
        change to what happens after this loop, not a change to the protocol.
        """
        await socket.accept()
        # The phase names come from the server so they live in one place. They
        # are a constant of the domain rather than per-run data, so they are sent
        # once here instead of riding on every event.
        await socket.send_json({"type": "hello", "phases": list(PHASES)})
        for enriched in replay(root):
            await socket.send_json({"type": "event", **enriched})
        await socket.send_json({"type": "replayed"})
        try:
            # Nothing is expected from the browser. This waits for it to leave.
            await socket.receive_text()
        except WebSocketDisconnect:
            return

    runs_root = root.resolve()

    @app.get("/runs/{run_id}/screenshots/{name}")
    def screenshot(run_id: str, name: str) -> FileResponse:
        """One captured screenshot, by the run it belongs to and its file name.

        Both parts of the path come from the request and neither is trusted. An
        earlier version resolved the permitted directory *through* `run_id`, so
        the boundary moved with the input it was supposed to constrain and
        `run_id` of `..` walked straight out - a check that could not fail.

        The boundary is now `runs_root`, resolved once, before any request. Each
        segment is also rejected outright if it contains a separator or a parent
        reference, so a traversal is refused rather than merely contained.
        """
        for segment in (run_id, name):
            if segment in {"", ".", ".."} or {"/", "\\"} & set(segment):
                raise HTTPException(status_code=404, detail="no such screenshot")

        candidate = (runs_root / run_id / "screenshots" / name).resolve()
        if not candidate.is_file() or runs_root not in candidate.parents:
            raise HTTPException(status_code=404, detail="no such screenshot")
        return FileResponse(candidate)

    # Mounted last and at the root, so the routes above are matched first.
    # `html=True` serves index.html for `/`.
    app.mount("/", StaticFiles(directory=STATIC_ROOT, html=True), name="console")
    return app
