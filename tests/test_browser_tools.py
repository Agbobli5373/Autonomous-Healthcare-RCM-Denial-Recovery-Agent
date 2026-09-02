"""The four tools, against a real browser and a really-served portal.

Nothing here is mocked below the tool boundary. A real Chromium drives a real
uvicorn serving the real mock, with its real XHR latency and its real deliberate
session expiry. That is the only way most of these could be checked: every
interesting failure is a locator that does not match, a wait that returns too
early, or a download that arrives somewhere other than where it was expected —
and all three pass a test that stubs the page out.

The browser is local while the demo's is a Solari cloud browser. The tools take a
`Page` and do not know the difference, which is the seam that makes this possible
at all; the cloud path is exercised separately and costs a minute a run.
"""

from __future__ import annotations

import asyncio
import importlib.util
import socket
import threading
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
import uvicorn

from rcm_agent.browser.retry import RetryPolicy
from rcm_agent.browser.tools import (
    download_eob,
    log_in,
    open_claim,
    page_url,
    search_claims,
)
from rcm_agent.events import Event, EventStream
from rcm_agent.mocks.portal import create_app

HERO_CLAIM = "CLM-2026-0001"
"""The CO-197 prior-authorization claim. Oldest of three, so it is on page two."""

PORTAL_USER = "provider"
PORTAL_PASSWORD = "demo"
"""The mock accepts anything. Spelled out rather than splatted from a dict so the
type checker can see that each tool is being called with what it declares."""

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def free_port() -> int:
    with closing(socket.socket()) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="module")
def portal_url() -> Iterator[str]:
    """A real server, with the mock's real 1.2s worklist latency.

    The latency is not turned down. It is the thing that makes waiting on a
    condition rather than sleeping actually matter, and a test that removes it
    would pass against a `sleep(0.1)` implementation.
    """
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        threading.Event().wait(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


class Recorder:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def handle(self, event: Event) -> None:
        self.events.append(event)


def chromium_is_available() -> bool:
    """Skip rather than fail where the browser was never installed.

    The suite has to stay runnable on a machine that has not downloaded a
    hundred megabytes of Chromium, the same way the OCR test skips without
    tesseract.
    """
    return importlib.util.find_spec("patchright") is not None


needs_browser = pytest.mark.skipif(
    not chromium_is_available(), reason="patchright/chromium is not installed here"
)


class Driven:
    """One browser, one page, one recorded stream — the fixture's whole world."""

    def __init__(self, page: Any, stream: EventStream, recorder: Recorder, shots: Path) -> None:
        self.page = page
        self.stream = stream
        self.recorder = recorder
        self.shots = shots

    def retries(self) -> list[Event]:
        return [e for e in self.recorder.events if e.kind == "retry"]

    def results(self) -> list[Event]:
        return [e for e in self.recorder.events if e.kind == "tool_result"]


async def _drive(portal_url: str, shots: Path, body: Any) -> None:
    from patchright.async_api import async_playwright

    recorder = Recorder()
    stream = EventStream()
    stream.add_sink(recorder)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        try:
            await body(Driven(page, stream, recorder, shots))
        finally:
            await browser.close()


def drive(portal_url: str, tmp_path: Path, body: Any) -> None:
    asyncio.run(_drive(portal_url, tmp_path, body))


# --- log_in ----------------------------------------------------------------


@needs_browser
def test_signing_in_lands_on_the_worklist(portal_url: str, tmp_path: Path) -> None:
    async def body(run: Driven) -> None:
        outcome = await log_in(
            run.page,
            base_url=portal_url,
            user=PORTAL_USER,
            password=PORTAL_PASSWORD,
            stream=run.stream,
            screenshots=run.shots,
        )

        assert outcome.ok and outcome.outcome == "ok", outcome
        assert "/wl" in run.page.url

    drive(portal_url, tmp_path, body)


@needs_browser
def test_refused_credentials_come_back_as_a_result_not_an_exception(
    portal_url: str, tmp_path: Path
) -> None:
    """A refusal is the page telling the truth. Retrying it asks again and loses."""

    async def body(run: Driven) -> None:
        outcome = await log_in(
            run.page, base_url=portal_url, user="", password="", stream=run.stream
        )

        assert not outcome.ok
        assert outcome.outcome == "refused"

    drive(portal_url, tmp_path, body)


# --- search_claims ---------------------------------------------------------


@needs_browser
def test_the_worklist_is_waited_for_rather_than_slept_past(portal_url: str, tmp_path: Path) -> None:
    """The rows arrive by XHR. Anything that sleeps a fixed interval reads a spinner."""

    async def body(run: Driven) -> None:
        await log_in(
            run.page,
            base_url=portal_url,
            user=PORTAL_USER,
            password=PORTAL_PASSWORD,
            stream=run.stream,
        )

        outcome = await search_claims(run.page, stream=run.stream)

        assert outcome.ok, outcome
        assert outcome.detail["claims"], "the queue came back empty; the spinner was read"

    drive(portal_url, tmp_path, body)


@needs_browser
def test_pagination_is_walked_to_reach_the_prior_authorization_claim(
    portal_url: str, tmp_path: Path
) -> None:
    """The hero claim is the oldest of three and the queue is newest first.

    It is genuinely not on page one, so finding it is a navigation, not a read.
    """

    async def body(run: Driven) -> None:
        await log_in(
            run.page,
            base_url=portal_url,
            user=PORTAL_USER,
            password=PORTAL_PASSWORD,
            stream=run.stream,
        )

        found = await search_claims(run.page, stream=run.stream, looking_for=HERO_CLAIM)

        assert found.ok, found
        assert HERO_CLAIM in found.detail["claims"]
        # The proof that this was a navigation: the claim was not on the page the
        # agent landed on, so a page had to be turned to reach it. That the
        # fixture puts it there is the portal suite's business, not this one's.
        assert found.detail["pages_walked"] > 1, "it was found without turning a page"

    drive(portal_url, tmp_path, body)


@needs_browser
def test_a_claim_that_is_not_in_the_queue_is_a_result_not_a_failure(
    portal_url: str, tmp_path: Path
) -> None:
    async def body(run: Driven) -> None:
        await log_in(
            run.page,
            base_url=portal_url,
            user=PORTAL_USER,
            password=PORTAL_PASSWORD,
            stream=run.stream,
        )

        outcome = await search_claims(run.page, stream=run.stream, looking_for="CLM-0000-0000")

        assert not outcome.ok
        assert outcome.outcome == "not_found"

    drive(portal_url, tmp_path, body)


# --- open_claim, and the expiry the portal springs on purpose --------------


@needs_browser
def test_the_deliberate_expiry_comes_back_as_session_expired(
    portal_url: str, tmp_path: Path
) -> None:
    """The portal signs the agent out on its first claim detail. That is the demo.

    It has to arrive as a result the caller can act on — signing in again — and
    never as an exception, and never as something the retry policy tries to
    paper over by clicking again.
    """

    async def body(run: Driven) -> None:
        await log_in(
            run.page,
            base_url=portal_url,
            user=PORTAL_USER,
            password=PORTAL_PASSWORD,
            stream=run.stream,
        )
        await search_claims(run.page, stream=run.stream, looking_for=HERO_CLAIM)

        outcome = await open_claim(run.page, HERO_CLAIM, stream=run.stream, screenshots=run.shots)

        assert not outcome.ok
        assert outcome.outcome == "session_expired"
        assert run.retries() == [], "an expiry is semantic; it must not be retried"

    drive(portal_url, tmp_path, body)


@needs_browser
def test_signing_in_again_recovers_and_the_claim_opens(portal_url: str, tmp_path: Path) -> None:
    async def body(run: Driven) -> None:
        await walk_to_the_claim(run, portal_url)

        assert HERO_CLAIM in run.page.url

    drive(portal_url, tmp_path, body)


# --- download_eob ----------------------------------------------------------


@needs_browser
def test_the_eob_lands_on_orchestrator_disk(portal_url: str, tmp_path: Path) -> None:
    """The link opens a new tab and the document is an attachment.

    Chromium abandons the popup and routes the download back to the opening page,
    which is why the tool waits there. The bytes are compared against the
    committed fixture, so "a file arrived" is not mistaken for "the right file".
    """
    from rcm_agent.mocks import fixtures_data

    async def body(run: Driven) -> None:
        await walk_to_the_claim(run, portal_url)

        outcome = await download_eob(
            run.page, HERO_CLAIM, into=run.shots.parent / "documents", stream=run.stream
        )

        assert outcome.ok, outcome
        landed = Path(str(outcome.detail["path"]))
        claim = fixtures_data.find(HERO_CLAIM)
        assert claim is not None
        assert landed.read_bytes() == claim.eob_path.read_bytes()

    drive(portal_url, tmp_path, body)


# --- what the record shows -------------------------------------------------


@needs_browser
def test_a_clean_run_records_no_retries(portal_url: str, tmp_path: Path) -> None:
    """If the locators are right, nothing retries. This is how we know they are."""

    async def body(run: Driven) -> None:
        await walk_to_the_claim(run, portal_url)

        assert run.retries() == [], [e.detail for e in run.retries()]

    drive(portal_url, tmp_path, body)


@needs_browser
def test_a_locator_that_never_matches_retries_and_reports_unavailable(
    portal_url: str, tmp_path: Path
) -> None:
    """The mechanical path, end to end, against a real browser.

    A claim number that is not on the page produces a click that never lands —
    which is a mechanical failure, not a semantic one, because the tool cannot
    tell "not rendered yet" from "not here" without waiting. So it retries, says
    so in the record, and returns a result rather than raising.
    """
    impatient = RetryPolicy(wall_clock_cap=30.0, action_timeout_ms=400)

    async def body(run: Driven) -> None:
        await log_in(
            run.page,
            base_url=portal_url,
            user=PORTAL_USER,
            password=PORTAL_PASSWORD,
            stream=run.stream,
        )
        await search_claims(run.page, stream=run.stream)

        outcome = await open_claim(run.page, "CLM-NOT-HERE", stream=run.stream, policy=impatient)

        assert not outcome.ok
        assert outcome.outcome == "unavailable"
        assert [e.detail["attempt"] for e in run.retries()] == [1, 2]
        assert "attempt" not in outcome.detail, "the attempt count must not be returned"

    drive(portal_url, tmp_path, body)


@needs_browser
def test_screenshots_are_written_and_named_for_the_event_that_points_at_them(
    portal_url: str, tmp_path: Path
) -> None:
    """Audit artifacts, joined to the record by `seq` so they cannot drift apart."""

    async def body(run: Driven) -> None:
        await walk_to_the_claim(run, portal_url)

        referenced = [e for e in run.recorder.events if e.screenshot]
        assert referenced, "no event referenced a screenshot"
        for event in referenced:
            name = event.screenshot
            assert name is not None
            assert (run.shots / name).is_file(), name
            assert name.startswith(f"{event.seq:04d}-"), name

    drive(portal_url, tmp_path, body)


async def walk_to_the_claim(run: Driven, portal_url: str) -> None:
    """Sign in, find the claim, get bounced, sign in again, open it.

    The whole browser leg of the demo, and the reason it is a helper: several
    tests need the agent to be *past* the deliberate expiry before they start.
    """
    await log_in(
        run.page, base_url=portal_url, user=PORTAL_USER, password=PORTAL_PASSWORD, stream=run.stream
    )
    await search_claims(run.page, stream=run.stream, looking_for=HERO_CLAIM)

    first = await open_claim(run.page, HERO_CLAIM, stream=run.stream, screenshots=run.shots)
    if first.outcome == "session_expired":
        await log_in(
            run.page,
            base_url=portal_url,
            user=PORTAL_USER,
            password=PORTAL_PASSWORD,
            stream=run.stream,
            screenshots=run.shots,
        )
        await search_claims(run.page, stream=run.stream, looking_for=HERO_CLAIM)
        await open_claim(run.page, HERO_CLAIM, stream=run.stream, screenshots=run.shots)


# --- the preview URL the sandbox hands out ---------------------------------


def test_a_path_is_added_without_destroying_the_preview_token() -> None:
    """The sandbox-hosted portal is reached through a URL with a token in its query.

    Concatenating a path onto it produced `https://host?pt_token=.../login` — a
    request for the root with a corrupted token glued to it. That survived only
    because the portal's root happens to redirect to the login page, so nothing
    failed and nothing was covered.
    """
    tokened = "https://abc123-8080.preview.getsolari.com?pt_token=SECRET"

    assert page_url(tokened, "/login") == (
        "https://abc123-8080.preview.getsolari.com/login?pt_token=SECRET"
    )


def test_a_plain_base_url_still_gets_its_path() -> None:
    assert page_url("http://127.0.0.1:8080", "/login") == "http://127.0.0.1:8080/login"


def test_a_trailing_slash_does_not_double_up() -> None:
    assert page_url("http://127.0.0.1:8080/", "/login") == "http://127.0.0.1:8080/login"
