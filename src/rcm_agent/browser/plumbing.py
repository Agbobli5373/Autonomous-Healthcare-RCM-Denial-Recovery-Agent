"""The plumbing every browser tool shares.

Two systems now have tools — the payer portal and the practice-management system
— and they agree on how a tool behaves even though they agree on nothing else.
A tool reports rather than raises, retries only what is mechanical, records a
decision with a screenshot beside it, and finds things by text and structure.

That contract lives here so both sets can hold it, and so neither has to reach
into the other's privates to do so.
"""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit, urlunsplit

from rcm_agent.browser.perception import capture_decision
from rcm_agent.browser.retry import MechanicalFailure
from rcm_agent.events import EventStream, Phase

if TYPE_CHECKING:  # pragma: no cover
    from patchright.async_api import Page


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


def starting(
    stream: EventStream, tool: str, claim_id: str | None = None, phase: Phase = "portal"
) -> None:
    """Say a tool began, before it can succeed or fail.

    All four announce themselves, so a reader of the record can tell a tool that
    was never reached from one that ran and came back unhappy. No screenshot:
    nothing has been decided yet, and the picture worth keeping is the one at the
    end.
    """
    stream.emit(phase=phase, kind="tool_call", tool=tool, claim_id=claim_id)


async def gave_up(
    page: Page,
    stream: EventStream,
    tool: str,
    exhausted: Exception,
    screenshots: Path | None,
    claim_id: str | None = None,
    phase: Phase = "portal",
) -> ToolOutcome:
    """Every tool answers an exhausted retry the same way, so it is written once."""
    return await finish(
        page,
        stream,
        tool,
        "unavailable",
        {"error": str(exhausted)[:300]},
        screenshots=screenshots,
        claim_id=claim_id,
        phase=phase,
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


async def retryable[T](action: Awaitable[T], what: str) -> T:
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


async def finish(
    page: Page,
    stream: EventStream,
    tool: str,
    outcome: Outcome,
    detail: dict[str, Any],
    *,
    screenshots: Path | None = None,
    claim_id: str | None = None,
    phase: Phase = "portal",
) -> ToolOutcome:
    """Record the decision, keep the picture, and hand back the result.

    Every tool ends here so that a screenshot is taken at exactly the points a
    human would want one — the moments something was decided — rather than on a
    timer or on every action.
    """
    await capture_decision(
        page,
        stream,
        phase=phase,
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
