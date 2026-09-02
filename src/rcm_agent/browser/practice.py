"""The two practice-management tools: read the Authorization, write the note.

This is the leg the hero claim exists to justify. The payer says no
Authorization was on file; the agent leaves the portal, opens a different system
in a different browser session, and finds the record that proves otherwise.

**`read_auth_record` returns typed fields, not prose.** The comparison the agent
has to make — does this validity range cover the claim's date of service — is a
comparison between dates, and it cannot be made against a paragraph. So the
dates come back parsed and the covered scope comes back as a list, and the
parsing is strict: a shape it does not recognise fails rather than returning
something plausible, because a plausible wrong date here produces a confident
wrong appeal.

**It does not make the comparison.** The tool reports what the chart says; the
agent decides what that means, exactly as the portal's tools report outcomes and
the agent decides how to answer them. Returning a `covers` boolean would move
the one piece of reasoning this ticket is about out of the agent and into a
`<=`.

Same rules as the portal tools throughout: locators are text and structure,
mechanical failures retry inside the tool, semantic ones come back as results.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from rcm_agent.browser.perception import accessibility_tree, definition_pairs
from rcm_agent.browser.plumbing import (
    ToolOutcome,
    finish,
    gave_up,
    page_url,
    retryable,
    starting,
)
from rcm_agent.browser.retry import (
    MechanicalFailure,
    RetriesExhausted,
    RetryPolicy,
    with_retries,
)
from rcm_agent.events import EventStream, Phase
from rcm_agent.practice_io import parse_chart_date
from rcm_agent.strict_json import RecordFileError

if TYPE_CHECKING:  # pragma: no cover
    from patchright.async_api import Page

CHART_READY_TIMEOUT_MS = 15_000
"""How long to wait for a chart to render. No XHR here, so shorter than the portal."""

AUTHORIZATION_NUMBER = "Authorization No."
VALID_FROM = "Valid From"
VALID_THROUGH = "Valid Through"
COVERED_HCPCS = "Covered HCPCS"
DATE_OF_SERVICE = "Date of Service"
"""The labels the chart prints, named once.

They are what the locators match on — this system has no automation hooks either
— so a label changing in the markup should break one constant, not four tools.
"""

NO_AUTHORIZATION = "No authorization on file"
"""What the chart says when there is nothing to find. A real answer, not a fault.

Matched against the page rather than assumed from a missing field — see
`read_auth_record`.
"""

PHASE: Phase = "emr"
"""Where these events belong in the record.

Not `portal`. The run directory and the progress matrix both have a column for
this system, and events filed under the wrong phase would leave that column
empty on a live run while the scripted demo filled it — a record that disagrees
with itself about which system did what.
"""


async def _open_chart(page: Page, claim_id: str, *, base_url: str, rules: RetryPolicy) -> None:
    """Reach a chart the way a person does: search for it, then open the result.

    Not by building the URL. The search is what proves the claim can be *found*
    in this system, and a direct link would skip the only part of this that could
    realistically fail.

    The result row is found by where its link goes rather than by its text,
    because the row is titled with the *patient's* name — the claim number sits
    beside it, and a link's destination is part of what the accessibility tree
    reports about it (`/url`), not an authored hook.
    """
    await retryable(page.goto(page_url(base_url, "/search.do")), "opening the chart search")
    await retryable(
        page.get_by_role("textbox").fill(claim_id, timeout=rules.action_timeout_ms),
        "typing the claim number",
    )
    await retryable(
        page.get_by_role("button", name="Search").click(timeout=rules.action_timeout_ms),
        "running the chart search",
    )
    chart_link = page.locator(f'a[href*="{claim_id}"]').first
    await retryable(
        chart_link.wait_for(timeout=CHART_READY_TIMEOUT_MS), "waiting for the search results"
    )
    await retryable(chart_link.click(timeout=rules.action_timeout_ms), "opening the chart")
    await retryable(page.wait_for_load_state(), "waiting for the chart")


async def read_auth_record(
    page: Page,
    claim_id: str,
    *,
    base_url: str,
    stream: EventStream,
    screenshots: Path | None = None,
    policy: RetryPolicy | None = None,
) -> ToolOutcome:
    """Open a claim's chart and read its prior Authorization as typed fields."""
    rules = policy or RetryPolicy()
    starting(stream, "read_auth_record", claim_id, PHASE)

    async def attempt() -> dict[str, str]:
        await _open_chart(page, claim_id, base_url=base_url, rules=rules)
        return definition_pairs(await accessibility_tree(page))

    try:
        chart = await with_retries(
            attempt, tool="read_auth_record", stream=stream, claim_id=claim_id, policy=rules
        )
    except RetriesExhausted as exhausted:
        return await gave_up(
            page, stream, "read_auth_record", exhausted, screenshots, claim_id, PHASE
        )

    if not chart:
        return await finish(
            page,
            stream,
            "read_auth_record",
            "not_found",
            {"url": page.url},
            screenshots=screenshots,
            claim_id=claim_id,
            phase=PHASE,
        )

    if AUTHORIZATION_NUMBER not in chart:
        # A missing field is not the same as the chart saying there is nothing.
        # Reporting "no authorization on file" because a label was absent would
        # turn a half-rendered page into a confident answer about a patient —
        # the exact plausible-wrong-answer this module claims to refuse. So the
        # page is asked, and a chart that says neither is a fault.
        says_none = NO_AUTHORIZATION.casefold() in (await page.content()).casefold()
        return await finish(
            page,
            stream,
            "read_auth_record",
            "not_found" if says_none else "unavailable",
            (
                {"reason": NO_AUTHORIZATION, "patient": chart.get("Name", "")}
                if says_none
                else {"error": "the chart showed neither an Authorization nor a note saying none"}
            ),
            screenshots=screenshots,
            claim_id=claim_id,
            phase=PHASE,
        )

    try:
        detail: dict[str, Any] = {
            "authorization_number": chart[AUTHORIZATION_NUMBER],
            "valid_from": parse_chart_date(chart[VALID_FROM]).isoformat(),
            "valid_to": parse_chart_date(chart[VALID_THROUGH]).isoformat(),
            "covered_procedure_codes": [
                code.strip() for code in chart.get(COVERED_HCPCS, "").split(",") if code.strip()
            ],
            "date_of_service": parse_chart_date(chart[DATE_OF_SERVICE]).isoformat(),
        }
    except (KeyError, RecordFileError) as unreadable:
        # A chart that renders but does not parse is a fault, not an answer: the
        # agent would otherwise compare dates that were never really read.
        return await finish(
            page,
            stream,
            "read_auth_record",
            "unavailable",
            {"error": f"the chart did not parse: {unreadable}"},
            screenshots=screenshots,
            claim_id=claim_id,
            phase=PHASE,
        )

    return await finish(
        page,
        stream,
        "read_auth_record",
        "ok",
        detail,
        screenshots=screenshots,
        claim_id=claim_id,
        phase=PHASE,
    )


async def write_note(
    page: Page,
    claim_id: str,
    *,
    text: str,
    base_url: str,
    stream: EventStream,
    screenshots: Path | None = None,
    policy: RetryPolicy | None = None,
) -> ToolOutcome:
    """Write a note back to the chart, and confirm it is there on reload.

    Confirmed rather than assumed. A write-back nobody checked is the kind of
    thing that looks fine in a demo and is not true, and this one is the reason
    the practice-management system could not be a static page.
    """
    rules = policy or RetryPolicy()
    starting(stream, "write_note", claim_id, PHASE)

    if not text.strip():
        return await finish(
            page,
            stream,
            "write_note",
            "refused",
            {"reason": "an empty note is not worth writing"},
            screenshots=screenshots,
            claim_id=claim_id,
            phase=PHASE,
        )

    async def attempt() -> bool:
        if claim_id not in page.url:
            await _open_chart(page, claim_id, base_url=base_url, rules=rules)

        # Checked before writing, so a retry cannot leave two copies. The portal's
        # tools are all reads and could be retried freely; this one changes the
        # world, and a click that raised *after* it landed would otherwise append
        # the note a second time.
        if text in await page.content():
            return True

        # No `.last`: the chart has exactly one textbox, and Playwright's strict
        # locators fail loudly if that ever stops being true. Picking by position
        # would quietly write into whichever box happened to be there.
        await retryable(
            page.get_by_role("textbox").fill(text, timeout=rules.action_timeout_ms),
            "typing the note",
        )
        await retryable(
            page.get_by_role("button", name="Save Note").click(timeout=rules.action_timeout_ms),
            "saving the note",
        )
        await retryable(page.wait_for_load_state(), "waiting for the chart to come back")
        # Read it back off the reloaded page rather than trusting the click. A
        # save that did not land is mechanical - the next attempt may well work -
        # so it is raised rather than returned, and the retry policy handles it.
        if text not in await page.content():
            raise MechanicalFailure("the note was not on the chart after saving")
        return True

    try:
        await with_retries(
            attempt, tool="write_note", stream=stream, claim_id=claim_id, policy=rules
        )
    except RetriesExhausted as exhausted:
        return await gave_up(page, stream, "write_note", exhausted, screenshots, claim_id, PHASE)

    return await finish(
        page,
        stream,
        "write_note",
        "ok",
        {"characters": len(text), "url": page.url},
        screenshots=screenshots,
        claim_id=claim_id,
        phase=PHASE,
    )
