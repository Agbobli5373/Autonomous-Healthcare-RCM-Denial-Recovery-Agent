# The route handlers below are registered by their decorators and never called
# by name, which pyright reads as dead code. Scoped to that one rule so every
# other strict check still applies to this module.
# pyright: reportUnusedFunction=false

"""The mock payer portal.

No payer portal permits automated access, and this project does not evade bot
detection, so a mock is the only lawful option — which means it has to be
credible rather than convenient. Four frictions are deliberate:

* **The worklist arrives by XHR**, so a fixed sleep reads an empty page.
* **Pagination**: the `CO-197` claim is the oldest, and the queue is newest
  first, so it sits on page two.
* **The EOB opens in a new tab**, which is tab switching plus a download.
* **The session expires on a specific navigation** — action-triggered rather
  than wall-clock, so the recovery lands at the same point on every run and can
  be rehearsed against a take that has to be unbroken.

The markup has no automation hooks. See `markup.py`.
"""

from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from rcm_agent.fixtures.naming import eob_filename
from rcm_agent.mocks import fixtures_data
from rcm_agent.mocks.portal import markup

SESSION_COOKIE = "CHPSESSID"
PAGE_SIZE = 2
WORKLIST_LATENCY_SECONDS = 1.2
"""Long enough that reading the page too early returns the spinner, not rows."""

EXPIRE_ON_CLAIM_VIEW = 1
"""Which claim-detail view of the run expires the session, once.

Action-triggered, not wall-clock. A timer lands somewhere different on every
take, which makes the recovery impossible to rehearse; counting navigations puts
it in the same place every time without faking anything — the agent genuinely
gets bounced to the login page.

**One, not two.** The demo's browser leg opens exactly one claim detail per
claim: sign in, worklist, paginate, open the prior-authorization claim, fetch
its EOB. Expiring on the second view meant the friction existed and never fired
on the only path that matters, and it disagreed with `demo_script`, which models
the recovery on the first claim.

**Of the run, not of the session.** Counted on `_State` rather than `_Session`,
because a fresh session starts its own count at zero — so with a per-session
counter the recovered session expires on its first claim detail too, and the
agent loops between the login page and the bounce without ever seeing a claim.
The friction is one interruption to recover from, not a wall.
"""


@dataclass
class _Session:
    expired: bool = False
    viewed: set[str] = field(default_factory=set[str])
    """Claims whose detail page this session actually opened.

    A real portal does not hand out a document to someone who never opened the
    claim, and without this the EOB endpoint is a deep link that skips the
    spinner, the pagination and the expiry in a single request."""


@dataclass
class _State:
    sessions: dict[str, _Session] = field(default_factory=dict[str, _Session])
    claim_views: int = 0
    """Claim details opened in this run, across every session it took."""

    def start(self) -> str:
        token = secrets.token_hex(16)
        self.sessions[token] = _Session()
        return token

    def get(self, token: str | None) -> _Session | None:
        if token is None:
            return None
        session = self.sessions.get(token)
        return None if session is None or session.expired else session


def create_app(*, latency: float = WORKLIST_LATENCY_SECONDS) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    state = _State()

    def signed_in(request: Request) -> _Session | None:
        return state.get(request.cookies.get(SESSION_COOKIE))

    def to_login() -> RedirectResponse:
        return RedirectResponse("/login", status_code=303)

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request) -> Response:
        return RedirectResponse("/wl" if signed_in(request) else "/login", status_code=303)

    @app.get("/login", response_class=HTMLResponse)
    async def login_form(request: Request) -> Response:
        expired = request.query_params.get("e") == "1"
        message = "Your session has ended. Please sign in again." if expired else ""
        return HTMLResponse(markup.login(message))

    @app.post("/login")
    async def sign_in(
        user: str = Form(default="", alias="ctl00$phBody$txtUserId"),
        password: str = Form(default="", alias="ctl00$phBody$txtPwd"),
    ) -> Response:
        if not user or not password:
            return HTMLResponse(markup.login("User ID and password are required."))
        response = RedirectResponse("/wl", status_code=303)
        # Any credentials are accepted. The demo authenticates from a saved
        # profile, and inventing a password to check would only mean a real
        # secret living somewhere for no benefit.
        response.set_cookie(SESSION_COOKIE, state.start(), httponly=True)
        return response

    @app.get("/wl", response_class=HTMLResponse)
    async def worklist(request: Request) -> Response:
        if signed_in(request) is None:
            return to_login()
        return HTMLResponse(markup.worklist_shell(_page_number(request)))

    @app.get("/wl/rows", response_class=HTMLResponse)
    async def worklist_rows(request: Request) -> Response:
        if signed_in(request) is None:
            return HTMLResponse(markup.login("Your session has ended."), status_code=401)
        await asyncio.sleep(latency)

        claims = list(fixtures_data.worklist())
        pages = page_count()
        page = min(_page_number(request), pages)
        start = (page - 1) * PAGE_SIZE
        return HTMLResponse(markup.worklist_rows(claims[start : start + PAGE_SIZE], page, pages))

    @app.get("/clm/{claim_id}", response_class=HTMLResponse)
    async def claim_detail(claim_id: str, request: Request) -> Response:
        session = signed_in(request)
        if session is None:
            return to_login()

        claim = fixtures_data.find(claim_id)
        if claim is None:
            # Looked up before the counter moves: a mistyped claim number should
            # not consume the budget, or the expiry stops being deterministic.
            return HTMLResponse(markup.login("Claim not found."), status_code=404)

        state.claim_views += 1
        if state.claim_views == EXPIRE_ON_CLAIM_VIEW:
            # `==`, so it fires exactly once. Signing in again has to actually
            # work or the recovery the demo rehearses is unreachable.
            session.expired = True
            return RedirectResponse("/login?e=1", status_code=303)

        session.viewed.add(claim.claim_id)
        return HTMLResponse(markup.claim_detail(claim))

    @app.get("/doc/{claim_id}")
    async def eob(claim_id: str, request: Request) -> Response:
        session = signed_in(request)
        if session is None:
            return to_login()
        claim = fixtures_data.find(claim_id)
        if claim is None or not claim.eob_path.is_file():
            return Response("Not found", status_code=404, media_type="text/plain")
        if claim.claim_id not in session.viewed:
            # No deep links. Reaching the document requires having opened the
            # claim, which is what keeps the spinner, the pagination and the
            # expiry on the path rather than beside it.
            return RedirectResponse(f"/clm/{claim.claim_id}", status_code=303)
        return Response(
            claim.eob_path.read_bytes(),
            media_type="application/pdf",
            headers={
                # attachment, not inline: the friction this is here for is
                # download capture, and an inline PDF fires no download event.
                "Content-Disposition": f'attachment; filename="{eob_filename(claim.claim_id)}"'
            },
        )

    return app


def page_count() -> int:
    """Pages in the worklist. Shared, so the tests cannot disagree with the app."""
    claims = len(fixtures_data.worklist())
    return max(1, -(-claims // PAGE_SIZE))


def _page_number(request: Request) -> int:
    raw = request.query_params.get("p", "1")
    return int(raw) if raw.isdigit() and int(raw) >= 1 else 1
