# The route handlers below are registered by their decorators and never called
# by name, which pyright reads as dead code. Scoped to that one rule so every
# other strict check still applies to this module.
# pyright: reportUnusedFunction=false

"""The mock practice-management system.

The payer's `CO-197` asserts that no Authorization was on file. This is where
the agent comes to prove otherwise, so the Authorization is a first-class record
with a real validity range and a real covered scope — not a string stubbed into
a spare field of something bigger. No open-source EMR models US payer
authorizations, which is why this is purpose-built rather than adapted.

Two things separate it from the payer portal beyond appearance:

* **Sign-on is seedable.** A saved Playwright `storageState` restores a session
  without a login round trip, which is how the second Solari profile earns its
  place: two systems, two saved logins, almost no screen time spent typing.
* **It is written to.** The agent leaves a chart note, so the mock cannot be
  static, and the note has to survive a reload to be worth anything.

A chart is addressed by claim number rather than by patient. A Practice Record
is one episode of care, and a patient with two episodes has two of them — keying
the screen by patient made the second silently unreachable and pointed both
search rows at the same chart.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from rcm_agent.mocks import fixtures_data
from rcm_agent.mocks.practice_management import markup

SESSION_COOKIE = "JSESSIONID"
"""The classic Java servlet cookie, against the portal's ASP.NET `CHPSESSID`.

Small detail, but it is the kind of thing that makes two mocks read as two
systems rather than one system with two stylesheets.
"""

SEEDED_SESSION = "demo-profile-not-a-secret"
"""A session id this system honours without ever having issued it.

A profile is captured once and replayed on every later run, including after this
process restarts — so if the only valid sessions were the ones minted at run
time, a saved profile would be dead by the second run and would fall back to the
sign-on page without saying so. Honouring one fixed id is what makes
`storage_state()` mean anything.

Signing on still mints a real session of its own; this id is recognised
*alongside* those, not instead of them.

**The value is words rather than the hex a real `JSESSIONID` would be.** It was
32 hex characters, which is more realistic and which secret scanning correctly
flagged as a committed session token — this repository is public and its subject
is healthcare, so a credential-shaped constant in it is a bad thing to be right
about. Suppressing the scanner would have kept the realism and taught the wrong
habit. It protects nothing either way: the mock accepts any credentials, holds
only synthetic records, and lives only as long as the demo's sandbox.
"""

SIGN_ON_USER = "rcm.demo"
"""What the seeded profile signed on as. Shown on screen; never checked."""


@dataclass
class _State:
    sessions: set[str] = field(default_factory=set[str])
    """Sessions this process actually issued, so signing out can end one."""

    notes: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    """Chart notes by claim number, held in memory on purpose.

    Writing them to disk would mean the second take of the demo starts from a
    different state than the first — the same reason the fixture documents are
    generated deterministically. A restart returns the mock to a known screen;
    a reload does not, which is what the write-back has to survive.
    """

    def signed_on(self, token: str | None) -> bool:
        return token is not None and (token == SEEDED_SESSION or token in self.sessions)

    def start(self) -> str:
        token = secrets.token_hex(16)
        self.sessions.add(token)
        return token

    def end(self, token: str | None) -> None:
        self.sessions.discard(token or "")


def create_app() -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    state = _State()

    def signed_on(request: Request) -> bool:
        return state.signed_on(request.cookies.get(SESSION_COOKIE))

    def to_sign_on() -> RedirectResponse:
        return RedirectResponse("/signin.do", status_code=303)

    def no_such_chart() -> Response:
        return HTMLResponse(markup.search("", [], searched=True), status_code=404)

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request) -> Response:
        return RedirectResponse("/search.do" if signed_on(request) else "/signin.do", 303)

    @app.get("/signin.do", response_class=HTMLResponse)
    async def sign_on_form() -> Response:
        return HTMLResponse(markup.sign_on())

    @app.post("/signin.do")
    async def sign_on_submit(
        user: str = Form(default="", alias="loginForm.userName"),
        password: str = Form(default="", alias="loginForm.password"),
    ) -> Response:
        if not user or not password:
            return HTMLResponse(markup.sign_on("User name and password are required."))
        # Any credentials are accepted, as in the payer portal: the demo signs on
        # from a saved profile, and a password to check would only mean a real
        # secret living somewhere for no benefit.
        response = RedirectResponse("/search.do", status_code=303)
        response.set_cookie(SESSION_COOKIE, state.start(), httponly=True)
        return response

    @app.get("/signout.do")
    async def sign_out(request: Request) -> Response:
        # Ends the session this process issued. A seeded profile is not ended by
        # signing out of it — the same as any saved login, which can simply be
        # loaded again.
        state.end(request.cookies.get(SESSION_COOKIE))
        response = to_sign_on()
        response.delete_cookie(SESSION_COOKIE)
        return response

    @app.get("/search.do", response_class=HTMLResponse)
    async def search(request: Request) -> Response:
        if not signed_on(request):
            return to_sign_on()
        query = request.query_params.get("q", "").strip()
        return HTMLResponse(
            markup.search(query, fixtures_data.search_records(query), searched=bool(query))
        )

    @app.get("/chart.do", response_class=HTMLResponse)
    async def chart(request: Request) -> Response:
        if not signed_on(request):
            return to_sign_on()
        record = fixtures_data.find_record(request.query_params.get("cid", ""))
        if record is None:
            return no_such_chart()
        saved = request.query_params.get("saved") == "1"
        return HTMLResponse(markup.chart(record, state.notes.get(record.claim_id, []), saved))

    @app.post("/note.do")
    async def save_note(
        request: Request,
        claim_id: str = Form(default="", alias="noteForm.claimNo"),
        text: str = Form(default="", alias="noteForm.noteText"),
    ) -> Response:
        if not signed_on(request):
            return to_sign_on()
        record = fixtures_data.find_record(claim_id)
        if record is None:
            return no_such_chart()
        if not text.strip():
            return HTMLResponse(markup.chart(record, state.notes.get(claim_id, [])))

        state.notes.setdefault(claim_id, []).append(_stamped(text.strip()))
        # Redirect after post, so the reload that proves the note persisted is a
        # plain GET rather than a resubmission the browser warns about.
        return RedirectResponse(f"/chart.do?cid={claim_id}&saved=1", status_code=303)

    return app


def _stamped(text: str) -> str:
    """UTC, as everywhere else in this project that stamps a time."""
    when = datetime.now(UTC).strftime("%d-%b-%Y %H:%M").upper()
    return f"[{when} UTC] {SIGN_ON_USER}: {text}"


def storage_state(base_url: str) -> dict[str, Any]:
    """A Playwright `storageState` that signs on without a round trip.

    Solari profiles are exactly this format, and one of the three documented ways
    to create a profile is uploading a `storage-state.json`. Writing it here
    rather than capturing it by hand keeps the second profile reproducible: the
    demo can be rebuilt from the repository without anyone remembering which
    browser they logged in from.

    The expiry is a fixed date rather than "now plus a year" so that regenerating
    the file twice produces the same bytes.
    """
    host = base_url.split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    return {
        "cookies": [
            {
                "name": SESSION_COOKIE,
                "value": SEEDED_SESSION,
                "domain": host,
                "path": "/",
                "expires": 2556057600,  # 2050-12-31T00:00:00Z
                "httpOnly": True,
                "secure": base_url.startswith("https://"),
                "sameSite": "Lax",
            }
        ],
        "origins": [],
    }
