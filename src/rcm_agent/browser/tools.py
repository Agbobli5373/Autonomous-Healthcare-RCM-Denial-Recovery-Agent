"""The four browser tools the agent plans over.

They were built and proved scripted first, so that when the model arrived a
failure would be a planning failure rather than a locator that never worked.
`rcm_agent.agent.loop` is what chooses between them now; nothing in this file
knows what order they run in, and that is the point.

**Locators use text, structure and context — never a hook.** The portal offers
no `id`, no `data-testid` and no ARIA, which is the point of it, so a field is
found by the row whose label reads "User ID" and a claim by the link whose text
is its claim number. That is how a person finds them, and it is the only thing
available.

Two of these locators are worth knowing about, because the obvious form does not
work. The login inputs have **no accessible name** — the labels sit in adjacent
table cells rather than in `<label for>` — so `get_by_role("textbox", name=...)`
matches nothing and the field has to be reached through the row that names it.
And the worklist arrives by XHR, so the table is waited *for*, never slept past.

**Nothing here raises at the caller.** A tool returns a `ToolOutcome`, including
when the answer is "the session expired" or "that claim is not in this queue".
Those are the page telling the truth, not faults, and retrying them just asks the
same question again. Mechanical failures — an element a frame late, a click that
missed — are retried inside the tool by `retry.with_retries`, recorded as events,
and never mentioned in the return value.
"""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit, urlunsplit

from rcm_agent.browser.perception import accessibility_tree, capture_decision
from rcm_agent.browser.retry import (
    MechanicalFailure,
    RetriesExhausted,
    RetryPolicy,
    with_retries,
)
from rcm_agent.events import EventStream

if TYPE_CHECKING:  # pragma: no cover
    from patchright.async_api import Locator, Page

WORKLIST_READY_TIMEOUT_MS = 20_000
"""Long enough for the deliberate XHR latency, short enough to fail a hung page."""

DOWNLOAD_TIMEOUT_MS = 20_000
"""How long to wait for the EOB to start arriving.

Its own name rather than the worklist's: they happen to be the same number, and
naming one after the other would make changing either look safe when it is not.
"""

CLAIM_DETAIL_MARKER = "Claim Detail"
"""Text the claim screen carries and the worklist does not.

Matched against the accessibility tree, so it is the same thing a person reads.
"""

MAX_WORKLIST_PAGES = 20
"""A cap on paging, so a queue that never ends cannot hang the run.

Twenty is far past the three-claim fixture and far short of forever. Reaching it
is reported as the page count actually walked, not as a sentinel - a "gave up"
that looked like a low number was indistinguishable from a short queue.
"""

Outcome = Literal["ok", "session_expired", "not_found", "refused", "unavailable"]


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    """What a tool tells its caller. Never how hard it had to try.

    The attempt count is deliberately absent. It is in `events.ndjson`, where an
    auditor can see it, and out of here, where it would make every caller decide
    what to do about a retry that already succeeded.
    """

    tool: str
    outcome: Outcome
    detail: dict[str, Any] = field(default_factory=dict[str, Any])

    @property
    def ok(self) -> bool:
        """Derived, not stored.

        It was a field, and every one of the thirteen places that built a
        `ToolOutcome` passed both — which made it a flag that could only ever
        disagree with the outcome beside it, never add anything.
        """
        return self.outcome == "ok"


def _starting(stream: EventStream, tool: str, claim_id: str | None = None) -> None:
    """Say a tool began, before it can succeed or fail.

    All four announce themselves, so a reader of the record can tell a tool that
    was never reached from one that ran and came back unhappy. No screenshot:
    nothing has been decided yet, and the picture worth keeping is the one at the
    end.
    """
    stream.emit(phase="portal", kind="tool_call", tool=tool, claim_id=claim_id)


async def _gave_up(
    page: Page,
    stream: EventStream,
    tool: str,
    exhausted: Exception,
    screenshots: Path | None,
    claim_id: str | None = None,
) -> ToolOutcome:
    """Every tool answers an exhausted retry the same way, so it is written once."""
    return await _finish(
        page,
        stream,
        tool,
        "unavailable",
        {"error": str(exhausted)[:300]},
        screenshots=screenshots,
        claim_id=claim_id,
    )


def page_url(base_url: str, path: str) -> str:
    """Put `path` on `base_url`, keeping any query string it already carries.

    The sandbox-hosted portal is reached through a preview URL whose access
    token rides in the query: `https://host?pt_token=...`. Concatenating a path
    onto that produced `https://host?pt_token=.../login`, which asks for the
    root and corrupts the token in passing. It happened to work only because the
    portal's root redirects to the login page.
    """
    parts = urlsplit(base_url)
    return urlunsplit(parts._replace(path=path))


def _expired(page: Page) -> bool:
    """The portal answers an expired session with a redirect to its login page."""
    return "/login" in page.url


async def _retryable[T](action: Awaitable[T], what: str) -> T:
    """Turn a locator failure into the one exception the retry policy retries.

    Anything patchright raises here is a timing or interaction fault by
    construction — the element was not there yet, or the click did not land.
    Bugs in this module raise their own types and are not caught.

    Generic rather than `Any -> Any`, so the awaited type survives the wrapper
    and a caller that misuses a result still fails at the type checker.
    """
    from patchright.async_api import Error as PlaywrightError

    try:
        return await action
    except PlaywrightError as exc:
        raise MechanicalFailure(f"{what}: {str(exc).splitlines()[0]}") from exc


async def log_in(
    page: Page,
    *,
    base_url: str,
    user: str,
    password: str,
    stream: EventStream,
    screenshots: Path | None = None,
    policy: RetryPolicy | None = None,
) -> ToolOutcome:
    """Sign in, and land on the worklist.

    Also the recovery: the portal expires the session on purpose part-way
    through, and the agent's answer is to run this again.
    """
    rules = policy or RetryPolicy()
    _starting(stream, "log_in")

    async def attempt() -> None:
        await _retryable(page.goto(page_url(base_url, "/login")), "opening the login page")
        # Through the row that names it: the inputs carry no accessible name of
        # their own, because the label is a sibling cell rather than a <label>.
        await _retryable(
            page.get_by_role("row", name="User ID")
            .get_by_role("textbox")
            .fill(user, timeout=rules.action_timeout_ms),
            "filling the user id",
        )
        await _retryable(
            page.get_by_role("row", name="Password")
            .get_by_role("textbox")
            .fill(password, timeout=rules.action_timeout_ms),
            "filling the password",
        )
        await _retryable(
            page.get_by_role("button", name="Sign In").click(timeout=rules.action_timeout_ms),
            "clicking sign in",
        )
        await _retryable(page.wait_for_load_state(), "waiting for the sign-in to land")

    try:
        await with_retries(attempt, tool="log_in", stream=stream, policy=rules)
    except RetriesExhausted as exhausted:
        return await _gave_up(page, stream, "log_in", exhausted, screenshots)

    if _expired(page):
        # Still on the login page: the credentials were refused. Semantic, so it
        # comes back as a result rather than as an exception.
        return await _finish(
            page, stream, "log_in", "refused", {"url": page.url}, screenshots=screenshots
        )
    return await _finish(page, stream, "log_in", "ok", {"url": page.url}, screenshots=screenshots)


async def search_claims(
    page: Page,
    *,
    stream: EventStream,
    looking_for: str | None = None,
    screenshots: Path | None = None,
    policy: RetryPolicy | None = None,
) -> ToolOutcome:
    """Read the denial worklist, paging until the wanted claim is on screen.

    **The rows arrive by XHR**, so the table is waited for as a condition. A
    fixed sleep reads the spinner and reports an empty queue, which is the kind
    of failure that looks like the site being slow rather than the agent being
    wrong.

    Pagination is walked by clicking the numbered links, because the claim the
    demo turns on is the oldest of three and the queue is newest first.
    """

    rules = policy or RetryPolicy()
    _starting(stream, "search_claims", looking_for)

    async def rows_on_this_page() -> list[str]:
        await _retryable(
            page.get_by_role("table").first.wait_for(timeout=WORKLIST_READY_TIMEOUT_MS),
            "waiting for the worklist rows",
        )
        links = page.get_by_role("link")
        found: list[str] = []
        for index in range(await links.count()):
            text = (await links.nth(index).inner_text()).strip()
            if text.startswith("CLM-"):
                found.append(text)
        return found

    async def turn_to(number: int) -> None:
        nxt: Locator = page.get_by_role("link", name=str(number), exact=True)
        await _retryable(nxt.click(timeout=rules.action_timeout_ms), f"turning to page {number}")

    # Retries wrap one page read or one page turn, never the whole walk. Wrapping
    # the walk meant a retry restarted counting at page one while the browser was
    # still on page three, and the next "turn to 2" walked backwards.
    seen: list[str] = []
    pages_walked = 0
    try:
        for page_number in range(1, MAX_WORKLIST_PAGES + 1):
            pages_walked = page_number
            rows = await with_retries(
                rows_on_this_page,
                tool="search_claims",
                stream=stream,
                claim_id=looking_for,
                policy=rules,
            )
            seen.extend(claim for claim in rows if claim not in seen)
            if looking_for is not None and looking_for in seen:
                break
            if await page.get_by_role("link", name=str(page_number + 1), exact=True).count() == 0:
                break
            await with_retries(
                lambda n=page_number + 1: turn_to(n),
                tool="search_claims",
                stream=stream,
                claim_id=looking_for,
                policy=rules,
            )
    except RetriesExhausted as exhausted:
        return await _gave_up(page, stream, "search_claims", exhausted, screenshots, looking_for)

    claims = seen

    if _expired(page):
        return await _finish(
            page,
            stream,
            "search_claims",
            "session_expired",
            {"url": page.url},
            screenshots=screenshots,
            claim_id=looking_for,
        )

    detail: dict[str, Any] = {"claims": claims, "pages_walked": pages_walked}
    if looking_for is not None and looking_for not in claims:
        # The queue was read and the claim is genuinely not in it. Nothing here
        # is broken, so this is an answer rather than an error.
        return await _finish(
            page,
            stream,
            "search_claims",
            "not_found",
            detail,
            screenshots=screenshots,
            claim_id=looking_for,
        )
    return await _finish(
        page,
        stream,
        "search_claims",
        "ok",
        detail,
        screenshots=screenshots,
        claim_id=looking_for,
    )


async def open_claim(
    page: Page,
    claim_id: str,
    *,
    stream: EventStream,
    screenshots: Path | None = None,
    policy: RetryPolicy | None = None,
) -> ToolOutcome:
    """Open one claim's detail, and notice if the portal signed us out doing it.

    The portal expires the session on a claim-detail view on purpose. That is the
    single most likely thing to happen here and it is not a fault: it comes back
    as `session_expired`, and the caller signs in again.
    """

    rules = policy or RetryPolicy()
    _starting(stream, "open_claim", claim_id)

    async def attempt() -> None:
        link = page.get_by_role("link", name=claim_id, exact=True)
        await _retryable(link.click(timeout=rules.action_timeout_ms), f"clicking {claim_id}")
        await _retryable(page.wait_for_load_state(), "waiting for the claim detail")

    try:
        await with_retries(
            attempt, tool="open_claim", stream=stream, claim_id=claim_id, policy=rules
        )
    except RetriesExhausted as exhausted:
        return await _gave_up(page, stream, "open_claim", exhausted, screenshots, claim_id)

    if _expired(page):
        return await _finish(
            page,
            stream,
            "open_claim",
            "session_expired",
            {"url": page.url},
            screenshots=screenshots,
            claim_id=claim_id,
        )
    # Read through the accessibility tree, not the raw HTML: the claim number
    # appears in the worklist too, so "the id is somewhere on the page" cannot
    # tell a detail page from the list it was clicked out of. The detail screen
    # is the one that names the claim *and* announces itself.
    tree = await accessibility_tree(page)
    if claim_id not in tree or CLAIM_DETAIL_MARKER not in tree:
        return await _finish(
            page,
            stream,
            "open_claim",
            "not_found",
            {"url": page.url},
            screenshots=screenshots,
            claim_id=claim_id,
        )

    return await _finish(
        page,
        stream,
        "open_claim",
        "ok",
        {"url": page.url, "accessibility_tree_chars": len(tree)},
        screenshots=screenshots,
        claim_id=claim_id,
    )


async def download_eob(
    page: Page,
    claim_id: str,
    *,
    into: Path,
    stream: EventStream,
    screenshots: Path | None = None,
    policy: RetryPolicy | None = None,
) -> ToolOutcome:
    """Capture the EOB from the link that opens a new tab, onto orchestrator disk.

    The link is `target="_blank"` and the document is served as an attachment, so
    Chromium abandons the popup and routes the download back to the opening page.
    That is why the wait is on this page's download event rather than on a new
    one — measured, not assumed; waiting for a popup that never settles is a
    twenty-second hang that looks like the network.
    """

    from patchright.async_api import TimeoutError as PlaywrightTimeout

    rules = policy or RetryPolicy()
    _starting(stream, "download_eob", claim_id)

    async def attempt() -> Path:
        link = page.get_by_role("link", name="View Explanation of Benefits")
        try:
            async with page.expect_download(timeout=DOWNLOAD_TIMEOUT_MS) as caught:
                await _retryable(
                    link.click(timeout=rules.action_timeout_ms), "clicking the EOB link"
                )
            download = await caught.value
        except PlaywrightTimeout as never_arrived:
            # Inside the attempt, so it is retried like any other click that did
            # not land. Outside it, this timed out once and reported unavailable
            # while claiming in the record to have tried three times.
            raise MechanicalFailure(f"no download followed the click: {never_arrived}") from (
                never_arrived
            )
        into.mkdir(parents=True, exist_ok=True)
        destination = into / download.suggested_filename
        await download.save_as(destination)
        return destination

    try:
        landed = await with_retries(
            attempt, tool="download_eob", stream=stream, claim_id=claim_id, policy=rules
        )
    except RetriesExhausted as exhausted:
        if _expired(page):
            # The portal signed us out mid-download. That is the page telling the
            # truth, and the caller can act on it; reporting "unavailable" would
            # have sent it looking for a fault that is not there.
            return await _finish(
                page,
                stream,
                "download_eob",
                "session_expired",
                {"url": page.url},
                screenshots=screenshots,
                claim_id=claim_id,
            )
        return await _gave_up(page, stream, "download_eob", exhausted, screenshots, claim_id)

    return await _finish(
        page,
        stream,
        "download_eob",
        "ok",
        {"path": str(landed), "bytes": landed.stat().st_size},
        screenshots=screenshots,
        claim_id=claim_id,
    )


async def _finish(
    page: Page,
    stream: EventStream,
    tool: str,
    outcome: Outcome,
    detail: dict[str, Any],
    *,
    screenshots: Path | None = None,
    claim_id: str | None = None,
) -> ToolOutcome:
    """Record the decision, keep the picture, and hand back the result.

    Every tool ends here so that a screenshot is taken at exactly the points a
    human would want one — the moments something was decided — rather than on a
    timer or on every action.
    """
    await capture_decision(
        page,
        stream,
        kind="tool_result",
        tool=tool,
        claim_id=claim_id,
        # `unavailable` is the only one of these that is a fault: the tool tried
        # and could not finish. The rest are the portal answering truthfully, and
        # painting them as failures makes a working run look broken.
        outcome="ok" if outcome == "ok" else ("failed" if outcome == "unavailable" else "handled"),
        detail={**detail, "result": outcome},
        into=screenshots,
    )
    return ToolOutcome(tool=tool, outcome=outcome, detail=detail)
