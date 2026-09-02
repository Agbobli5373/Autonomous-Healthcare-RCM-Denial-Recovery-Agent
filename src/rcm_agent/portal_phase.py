"""The portal phase: get the EOB for a claim, however the portal behaves.

Scripted rather than planned, on purpose. An LLM will choose this sequence later;
running it fixed first means that when one is in the loop, a failure is a
planning failure and not a locator that never worked.

The one branch here is the recovery. The portal expires the session on a
claim-detail view deliberately, so `open_claim` comes back `session_expired`
rather than raising, and the answer is to sign in again and carry on. That is
handled behaviour and the record says so — `recovery`, not `error` — because a
run that recovered is not a run that failed, and a viewer should not have to
infer the difference from a message.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rcm_agent.browser.tools import ToolOutcome, download_eob, log_in, open_claim, search_claims
from rcm_agent.events import EventStream

if TYPE_CHECKING:  # pragma: no cover
    from patchright.async_api import Page


@dataclass(frozen=True, slots=True)
class PortalWork:
    """What the portal phase achieved for one claim."""

    claim_id: str
    document: Path | None
    recovered: bool
    """Whether the session expired part-way and had to be re-established."""

    steps: tuple[ToolOutcome, ...]

    @property
    def ok(self) -> bool:
        return self.document is not None


async def work_the_portal(
    page: Page,
    *,
    portal_url: str,
    claim_id: str,
    user: str,
    password: str,
    stream: EventStream,
    documents: Path,
    screenshots: Path | None = None,
) -> PortalWork:
    """Sign in, find the claim, open it, and bring back its EOB."""
    steps: list[ToolOutcome] = []
    recovered = False

    stream.emit(phase="portal", kind="phase_start", claim_id=claim_id)

    async def sign_in() -> ToolOutcome:
        outcome = await log_in(
            page,
            base_url=portal_url,
            user=user,
            password=password,
            stream=stream,
            screenshots=screenshots,
        )
        steps.append(outcome)
        return outcome

    async def reach_the_claim() -> ToolOutcome:
        outcome = await search_claims(
            page, stream=stream, looking_for=claim_id, screenshots=screenshots
        )
        steps.append(outcome)
        return outcome

    if not (await sign_in()).ok:
        return _give_up(stream, claim_id, steps, recovered)
    if not (await reach_the_claim()).ok:
        return _give_up(stream, claim_id, steps, recovered)

    opened = await open_claim(page, claim_id, stream=stream, screenshots=screenshots)
    steps.append(opened)

    if opened.outcome == "session_expired":
        # Expected, not exceptional. The portal does this once on purpose and the
        # agent's answer is to authenticate again and walk back to where it was.
        recovered = True
        stream.emit(
            phase="portal",
            kind="recovery",
            claim_id=claim_id,
            detail={"reason": "session expired", "action": "signing in again"},
        )
        if not (await sign_in()).ok:
            return _give_up(stream, claim_id, steps, recovered)
        if not (await reach_the_claim()).ok:
            return _give_up(stream, claim_id, steps, recovered)
        opened = await open_claim(page, claim_id, stream=stream, screenshots=screenshots)
        steps.append(opened)

    if not opened.ok:
        return _give_up(stream, claim_id, steps, recovered)

    got = await download_eob(page, claim_id, into=documents, stream=stream, screenshots=screenshots)
    steps.append(got)
    if not got.ok:
        return _give_up(stream, claim_id, steps, recovered)

    stream.emit(phase="portal", kind="phase_end", claim_id=claim_id, outcome="ok")
    return PortalWork(
        claim_id=claim_id,
        document=Path(str(got.detail["path"])),
        recovered=recovered,
        steps=tuple(steps),
    )


def _give_up(
    stream: EventStream, claim_id: str, steps: list[ToolOutcome], recovered: bool
) -> PortalWork:
    """End the phase honestly, naming the step that stopped it.

    No exception: the caller gets a `PortalWork` that says it has no document,
    for the same reason the tools return results — whether the portal is broken
    or merely unhelpful is not something an orchestrator should learn from a
    traceback.
    """
    last = steps[-1] if steps else None
    stream.emit(
        phase="portal",
        kind="phase_end",
        claim_id=claim_id,
        outcome="failed",
        detail={
            "stopped_at": last.tool if last else "start",
            "because": last.outcome if last else "?",
        },
    )
    return PortalWork(claim_id=claim_id, document=None, recovered=recovered, steps=tuple(steps))
