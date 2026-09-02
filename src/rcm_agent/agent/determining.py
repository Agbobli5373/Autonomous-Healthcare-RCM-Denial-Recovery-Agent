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
from rcm_agent.determination import (
    GuardrailTrace,
    from_catalogue,
    governing_denial,
    run_guardrails,
)
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
    trace = run_guardrails(claim)
    # Before the determination, because that is the order it happened in. A run
    # that showed only the rule that fired could not evidence the claim this
    # project actually makes - that the rules were consulted, in order, before
    # any model call. The absence of a `judge_denial` event proves the model was
    # not asked; it does not prove the rules were checked.
    record_guardrails(stream, claim.claim_id, trace)
    if trace.determination is not None:
        _record(stream, trace.determination)
        return trace.determination

    try:
        determination = await judge(
            claim, governing_denial(claim), client=client, stream=stream, escalation=escalation
        )
    except JudgementRefused as refused:
        # The catalogue's documented default, which is never `appeal` for a
        # family whose appealability is unknown. Falling back to it is safe in a
        # way that retrying a model that just answered out of bounds is not.
        # `from_catalogue`, not `determine`: the guardrails already ran above
        # and none fired. Re-deciding would evaluate them a second time and put
        # an unrecorded evaluation behind the Determination that ships.
        fallback = from_catalogue(claim)
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


def record_guardrails(stream: EventStream, claim_id: str, trace: GuardrailTrace) -> None:
    """Record what the guardrails did, before whatever they decided.

    The wire shape lives here rather than on `GuardrailTrace`: `determination`
    decides whether a patient's claim may be appealed and owns no opinion about
    how a run is written down. Shared with `determine_command`, so both routes
    to a Determination describe the guardrails the same way.

    No separate `fired` key - it is the last entry of `evaluated` or nothing, and
    a second copy is a second thing to keep true.
    """
    stream.emit(
        phase="analysis",
        kind="guardrails",
        claim_id=claim_id,
        detail={
            "evaluated": [
                {"rule": outcome.name, "fired": outcome.fired}
                | ({"guardrail": outcome.guardrail} if outcome.guardrail else {})
                for outcome in trace.evaluated
            ]
        },
    )


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
