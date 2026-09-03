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

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from rcm_agent.console.replay import determinations, replay
from rcm_agent.domain import Action
from rcm_agent.matrix import PHASES
from rcm_agent.review import (
    StaleReview,
    all_current_reviews,
    digest_of,
    reviewed,
    store_review,
)

STATIC_ROOT = Path(__file__).resolve().parent / "static"
"""Where `console/` builds to. Committed, and served as-is."""

DEFAULT_RUNS = Path("runs")

DEFAULT_REVIEWS = Path("reviews")
"""Outside `runs/`, because a completed run is never appended to."""


class ConsoleNotBuilt(RuntimeError):
    """The bundle is missing, so there is nothing to serve.

    Only reachable in a working tree where the build output has been removed -
    a reviewer's clone always has it. Named rather than left as a stack trace
    from deep inside the static-files mount, because the fix is one command.
    """


class VerdictRequest(BaseModel):
    """What the browser sends when someone approves or rejects.

    The digest is the page saying *which* Determination it was looking at. A
    stale tab would otherwise record a verdict against a reading a re-run had
    already replaced.

    `reviewer` is whatever the person typed. Nothing verifies it - there is no
    sign-in yet - so it is a signature rather than an identity, and recording an
    unverified name is still better than the alternative the first version
    shipped, where every verdict was signed `console` and the record could not
    answer who approved anything.

    At module scope on purpose: `from __future__ import annotations` makes the
    handler's annotations strings, and FastAPI resolves them against the module -
    a class defined inside the factory is invisible there, and the body silently
    becomes a query parameter.
    """

    verdict: Literal["approved", "rejected"]
    reviewer: str
    reason: str = ""
    counter_action: Action | None = None
    determination_digest: str


def create_app(runs_dir: Path | None = None, reviews_dir: Path | None = None) -> FastAPI:
    """The console as an app, so it can be tested without a port."""
    if not (STATIC_ROOT / "index.html").is_file():
        raise ConsoleNotBuilt(
            f"no built console at {STATIC_ROOT}. It is normally committed; "
            "rebuild it with `npm install && npm run build` in console/."
        )

    root = DEFAULT_RUNS if runs_dir is None else runs_dir
    reviews_root = DEFAULT_REVIEWS if reviews_dir is None else reviews_dir
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

    @app.get("/reviews")
    def reviews() -> dict[str, Any]:
        """The verdict that stands for each claim.

        Fetched rather than streamed: a Review is not something the agent did,
        and the socket carries a run's events. Putting it there would make the
        transport describe two different things.

        Each carries whether it still `stands`. A verdict is given for one
        reading, and a re-run that changes the reading leaves it over what its
        reviewer actually read - so serving it as current would hand every
        consumer a sign-off nobody gave. The comparison is made here, once,
        against the same `authorises` the domain uses; leaving it to the browser
        would put the safety rule in a second language and let the next consumer
        of this endpoint inherit the stale verdict in silence.
        """
        standing = determinations(root)
        answer: dict[str, Any] = {}
        for claim_id, review in all_current_reviews(reviews_root).items():
            current = standing.get(claim_id)
            stands = False
            if current is not None:
                try:
                    review.authorises(current["determination"])
                except StaleReview:
                    stands = False
                else:
                    stands = True
            answer[claim_id] = {**review.to_dict(), "stands": stands}
        return answer

    @app.post("/reviews/{claim_id}")
    def record_verdict(claim_id: str, body: VerdictRequest) -> dict[str, Any]:
        """Record a verdict against the Determination the reviewer was shown.

        The digest is checked here rather than trusted, because the browser is
        the one thing that can be looking at yesterday's page.
        """
        standing = determinations(root).get(claim_id)
        if standing is None:
            raise HTTPException(status_code=404, detail=f"no Determination for {claim_id}")

        # First, before any other complaint. A stale page can be wrong about
        # everything else too - the Determination it was shown may since have
        # been replaced by one a rule closed - and telling that reviewer their
        # rejection needs a reason sends them to fix the wrong thing.
        if digest_of(standing["determination"]) != body.determination_digest:
            raise HTTPException(
                status_code=409,
                detail=(
                    "this page was looking at a different Determination. Reload before "
                    "deciding: a verdict recorded now would be against a reading that "
                    "has since been replaced."
                ),
            )

        try:
            review = reviewed(
                claim_id=claim_id,
                determination=standing["determination"],
                verdict=body.verdict,
                reason=body.reason,
                counter_action=body.counter_action,
                reviewer=body.reviewer,
                run_id=standing["run_id"],
                at=datetime.now(UTC),
            )
        except ValueError as exc:
            # A rejection with no reason, or a claim a rule closed. Both are the
            # request asking for something that should not exist.
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        store_review(reviews_root, review)
        # Freshly given for the Determination just checked, so it stands by
        # construction - said explicitly so one shape comes back from both routes.
        return {**review.to_dict(), "stands": True}

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
