"""How the agent sees a page, and what it keeps of what it saw.

**Perception is the accessibility tree, not the screenshot.** For a page the a11y
tree is strictly more information than pixels: it carries role, name, structure
and the relationships between them, it costs about an order of magnitude less to
produce and to reason over, and it does not change when a stylesheet does.

That is not a compromise forced by the mock. The payer portal authors no ARIA at
all — no roles, no labels, no landmarks — and the tree is still rich, because
real HTML has implicit semantics: `<table>` is a table, `<a>` is a link, `<td>`
is a cell, `<input>` is a textbox. Reading those is reading what a screen reader
reads, which is a fair description of "operating software the way a person does"
and a much better one than matching pixels.

Screenshots are still taken, but they are **audit artifacts, not inputs**. They
exist so a human can see what the agent saw at the moment it decided something,
and they are named for the `seq` of the event that references them so the two can
never drift apart.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rcm_agent.events import Event, EventStream, Kind, Outcome

if TYPE_CHECKING:  # pragma: no cover - patchright is heavy and only needed live
    from pathlib import Path

    from patchright.async_api import Page


async def accessibility_tree(page: Page, selector: str = "body") -> str:
    """What the agent reads. Role/name/structure, as a screen reader would get it."""
    return await page.locator(selector).aria_snapshot()


def screenshot_name(seq: int, tool: str) -> str:
    """Named for the event that points at it, so the join cannot rot."""
    return f"{seq:04d}-{tool}.png"


async def capture_decision(
    page: Page,
    stream: EventStream,
    *,
    kind: Kind,
    tool: str,
    claim_id: str | None = None,
    outcome: Outcome | None = None,
    detail: dict[str, Any] | None = None,
    into: Path | None = None,
) -> Event:
    """Emit an event and keep the picture that goes with it.

    The screenshot is named from the `seq` this emit is about to assign, which is
    why the stream is asked for it rather than a counter being kept here: `seq`
    is the join key and it is issued in exactly one place.

    A screenshot that cannot be taken must never cost the event. The record of
    what the agent decided matters more than the picture of it, and a browser
    that has already gone away is a normal way for this to fail.
    """
    # Taken and written *before* the event is emitted, so the record only ever
    # names a file that is already there. Emitting first left an event pointing
    # at a screenshot whose write then failed - which is exactly the dangling
    # reference this function claims to prevent.
    name: str | None = None
    if into is not None:
        candidate = screenshot_name(stream.next_seq, tool)
        try:
            image = await page.screenshot()
            into.mkdir(parents=True, exist_ok=True)
            (into / candidate).write_bytes(image)
            name = candidate
        except Exception:
            # A browser that has already gone away is a normal way for this to
            # fail, and the record of what was decided matters more than the
            # picture of it.
            name = None

    return stream.emit(
        phase="portal",
        kind=kind,
        tool=tool,
        claim_id=claim_id,
        outcome=outcome,
        screenshot=name,
        detail=detail,
    )
