"""Reaching a Determination on a Claim: guardrails first, then a judgement.

**The order is the safety property.** Guardrails run before any model call, so a
denial the law puts beyond appeal is answered without a model being consulted at
all. Expressing that as a confidence threshold would let a sufficiently
confident model file a void appeal, which is why ADR-0002 makes them rules; this
module is where that decision either holds or quietly stops being true.

Lives under `agent/` because it needs a `ModelClient`, and that package is the
one the sandbox archive excludes. The guardrails themselves stay in
`determination`, model-free and reachable from anywhere.

Not named for the payer's verb: `CONTEXT.md` reserves adjudication for what the
payer does to a Claim. What happens here is a Determination.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from rcm_agent.agent.judgement import JudgementRefused, judge
from rcm_agent.agent.model import HARD_JUDGEMENT, Escalation
from rcm_agent.determination import determine, governing_denial, guardrailed
from rcm_agent.domain import Claim, Determination
from rcm_agent.events import EventStream

if TYPE_CHECKING:  # pragma: no cover
    from rcm_agent.agent.loop import ModelClient


async def determine_with_judgement(
    claim: Claim,
    *,
    client: ModelClient,
    stream: EventStream,
    escalation: Escalation = HARD_JUDGEMENT,
) -> Determination:
    """Guardrails first; a model only where they leave a judgement to make."""
    guardrail = guardrailed(claim)
    if guardrail is not None:
        _record(stream, guardrail)
        return guardrail

    try:
        determination = await judge(
            claim, governing_denial(claim), client=client, stream=stream, escalation=escalation
        )
    except JudgementRefused as refused:
        # The catalogue's documented default, which is never `appeal` for a
        # family whose appealability is unknown. Falling back to it is safe in a
        # way that retrying a model that just answered out of bounds is not.
        fallback = determine(claim)
        determination = replace(
            fallback,
            rationale=(
                f"{fallback.rationale} Fell back to the documented default for this "
                f"family because the judgement was not usable ({refused})."
            ),
        )
        stream.emit(
            phase="analysis",
            kind="error",
            claim_id=claim.claim_id,
            outcome="handled",
            detail={"error": str(refused), "fell_back_to": fallback.action},
        )

    _record(stream, determination)
    return determination


def _record(stream: EventStream, determination: Determination) -> None:
    """Emit the Determination in the one shape every consumer already reads.

    `to_dict` rather than a hand-built detail: `determine_command` emits this
    same event kind that way, and two shapes for one `kind` is a trap for
    anything replaying the stream.
    """
    stream.emit(
        phase="analysis",
        kind="determination",
        claim_id=determination.claim_id,
        outcome="ok",
        detail=determination.to_dict(),
    )
