"""The Determination a model makes, where the guardrails leave one to make.

Guardrails run first and short-circuit (ADR-0002). This module is only reached
for a denial where the law and the contract genuinely leave a judgement — and
even then, what the model may choose is narrowed before it is asked.

**`CO-236` can never be an appeal, and that is structural.** An NCCI
procedure-to-procedure denial is recoverable only when the pair's modifier
indicator is 1; where it is 0, no modifier permits the pair and an appeal is
dead on arrival. That indicator lives in the CMS edit files, which are gated
behind an AMA CPT licence, so this project cannot model it — and a fact that
cannot be checked must not become a judgement call.

Until now the code was harmless because the catalogue defaulted it to
`corrected_claim`. Replacing that default with a real determination is exactly
what makes it dangerous, so `appeal` is removed from the options the model is
offered, and removed again from what it is allowed to return. Two mechanisms for
one rule, because the failure is a void appeal filed on a patient's claim.

The model is asked through a forced tool call rather than free text. A tool with
a narrowed enum cannot answer `appeal` for a code where appeal is withheld; a
paragraph can say anything and be parsed into it.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from rcm_agent.agent.model import HARD_JUDGEMENT, Escalation
from rcm_agent.catalogue import profile_for
from rcm_agent.domain import Action, Adjustment, Claim, Determination, Priority
from rcm_agent.events import EventStream

if TYPE_CHECKING:  # pragma: no cover
    from rcm_agent.agent.loop import ModelClient

EVERY_ACTION: tuple[Action, ...] = (
    "appeal",
    "corrected_claim",
    "rebill",
    "patient_bill",
    "close",
)

APPEAL_WITHHELD: dict[str, str] = {
    "CO-236": (
        "appealability turns on the NCCI procedure-to-procedure modifier indicator "
        "for this code pair and quarter. Indicator 0 means no modifier permits the "
        "pair and an appeal cannot succeed. The indicator is in the CMS edit files, "
        "which this project does not carry because they are gated behind an AMA CPT "
        "licence — so appeal is not offered rather than guessed at"
    ),
}
"""Codes where `appeal` is withheld because the deciding fact cannot be checked.

Not a claim that these are unappealable — some are. A claim that *this* system
cannot tell, and that filing blind on a patient's claim is the worse error. Each
entry carries the reason, and the reason goes into the Determination's rationale
so nobody has to come back here to find out why.
"""

DECISION_TOOL_NAME = "record_determination"


class JudgementRefused(RuntimeError):
    """The model returned something the narrowing had already ruled out.

    Should be unreachable — the enum it was given did not contain the value — so
    reaching it means the request was built wrongly or the API ignored the
    schema. Either way the answer is not usable and the caller falls back.
    """


def withheld_reasons(claim: Claim) -> tuple[str, ...]:
    """Every reason `appeal` is withheld from this claim, in code order.

    Read across the whole claim, not just the denial being answered. A
    Determination names one Action for the claim, so an `appeal` chosen for the
    governing denial would be filed over a claim that also carries a code appeal
    cannot answer - and the governing denial is only the largest by amount, so a
    bigger `CO-197` sitting beside a `CO-236` would have skipped the narrowing
    altogether. `_unappealable_remark` is claim-wide for exactly this reason.
    """
    present = {denial.code for denial in claim.denials} & APPEAL_WITHHELD.keys()
    return tuple(f"{code}: {APPEAL_WITHHELD[code]}" for code in sorted(present))


def allowed_actions(claim: Claim) -> tuple[Action, ...]:
    """What the model may choose for this claim."""
    if withheld_reasons(claim):
        return tuple(action for action in EVERY_ACTION if action != "appeal")
    return EVERY_ACTION


def decision_tool(claim: Claim) -> dict[str, Any]:
    """The one tool the model must call, with the choices already narrowed."""
    return {
        "name": DECISION_TOOL_NAME,
        "description": (
            "Record the Determination for this denial: which action the provider "
            "should take, why, and what evidence that action needs."
        ),
        # Validated by the API, so the enum is a constraint rather than a request.
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": list(allowed_actions(claim)),
                    "description": "The action this denial calls for.",
                },
                "rationale": {
                    "type": "string",
                    "description": (
                        "One or two sentences a biller could act on: what the payer "
                        "said, and why this action answers it."
                    ),
                },
                "evidence_required": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "The specific documents and facts a biller must gather "
                        "before this action can be taken - the authorisation "
                        "number, the operative note, the corrected modifier. Name "
                        "them individually rather than writing `documentation`. "
                        "Empty only for `close`, which asks for nothing."
                    ),
                },
            },
            "required": ["action", "rationale", "evidence_required"],
            "additionalProperties": False,
        },
    }


SYSTEM_PROMPT = """\
You decide what a provider should do about one denied medical claim, from the \
adjustment codes a payer returned on its remittance.

The five actions are `appeal`, `corrected_claim`, `rebill`, `patient_bill` and \
`close`. Most denial volume is correction work rather than appeal work, so \
`appeal` is one option among five and never a default. Appealing something that \
should have been corrected, rebilled or billed to the patient wastes a person's \
day and delays the money.

Some denials are not appealable at all, and some are recoverable only by a route \
other than appeal. Where the action you would otherwise choose is absent from \
the options you are offered, that is deliberate: the fact that would settle it \
cannot be checked here, and a confident guess is worse than a cautious answer.

Every action except `close` needs something gathered before anyone can take \
it, and naming those things is half the value of the determination. List them \
individually and concretely, as the items a biller would go and find.

Answer only by calling the tool."""


def _facts(claim: Claim, denial: Adjustment) -> str:
    """What the model is told. Read off the remittance, not looked up elsewhere."""
    lines = [
        f"Claim {claim.claim_id}, {claim.payer}.",
        f"Total refused: {claim.amount_denied}.",
        "",
        "Adjustments, per service line, as extracted from the EOB document:",
    ]
    for line in claim.service_lines:
        for adjustment in line.adjustments:
            remarks = " ".join(adjustment.remark_codes) or "none"
            lines.append(
                f"  line {line.line_number} · {line.procedure_code} · "
                f"{adjustment.code} · remark {remarks} · {adjustment.amount}"
            )

    profile = profile_for(denial.code)
    lines += [
        "",
        f"The denial to answer is {denial.code} ({profile.family}).",
        f"Known about this family: {profile.rationale}",
    ]
    for reason in withheld_reasons(claim):
        lines += ["", f"`appeal` is not among your options here because {reason}."]
    return "\n".join(lines)


async def judge(
    claim: Claim,
    denial: Adjustment,
    *,
    client: ModelClient,
    stream: EventStream,
    escalation: Escalation = HARD_JUDGEMENT,
) -> Determination:
    """Ask the model what this denial calls for, within the choices it is allowed.

    Opus by default. This is the step the escalation seam was built for: being
    wrong here files a void appeal or abandons recoverable money, which is
    expensive rather than merely slow.
    """
    tool = decision_tool(claim)
    allowed = allowed_actions(claim)
    facts = _facts(claim, denial)
    stream.emit(
        phase="analysis",
        kind="tool_call",
        tool="judge_denial",
        claim_id=claim.claim_id,
        detail={
            "denial": denial.code,
            "model": escalation.model,
            "options": list(allowed),
            # What varies per claim, and the whole basis of the inspector's
            # claim that the Determination was read off the document rather
            # than pattern-matched from a claim id. The system prompt is not
            # here on purpose: it is a module constant, byte-identical in every
            # run, already readable in source, and it would ship publicly in
            # every exported run for nothing.
            "facts": facts,
        },
    )

    response = await client.create(
        model=escalation.model,
        max_tokens=escalation.max_tokens,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={"effort": escalation.effort},
        tools=[tool],
        # Forced: the answer is a Determination or it is nothing. Free text would
        # have to be parsed, and parsing is where a withheld action creeps back.
        tool_choice={"type": "tool", "name": DECISION_TOOL_NAME},
        messages=[{"role": "user", "content": facts}],
    )

    decided = _decision(response)
    action = str(decided.get("action", ""))
    usable = action in allowed
    # Recorded either way, so a call always has a result - but stamped with what
    # happened, not with having happened. An answer the narrowing had already
    # ruled out is a refusal, and writing it down as `ok` would leave a reader an
    # accepted model result whose action contradicts the Determination beside it.
    stream.emit(
        phase="analysis",
        kind="tool_result",
        tool="judge_denial",
        claim_id=claim.claim_id,
        outcome="ok" if usable else "failed",
        detail={"denial": denial.code, "returned": dict(decided)},
    )
    if not usable:
        raise JudgementRefused(
            f"{denial.code}: the model answered {action!r}, which was not among its options"
        )

    profile = profile_for(denial.code)
    raw_evidence: object = decided.get("evidence_required") or []
    evidence: list[object] = (
        cast("list[object]", raw_evidence) if isinstance(raw_evidence, list) else []
    )
    rationale = str(decided.get("rationale", "")).strip()
    if not evidence and action != "close":
        # Observed on a live call: the same prompt returned ten evidence items
        # once and none the next time. Everything except `close` needs something
        # gathered, and an Appeal Package built from an empty list is not an
        # appeal - so the catalogue's documented list for the family stands in
        # rather than the Determination going out hollow. Recorded in the
        # rationale because a reader should know which part the model chose.
        evidence = list(profile_for(denial.code).evidence_required)
        rationale = (
            f"{rationale} Evidence list supplied from the catalogue for "
            f"{denial.code}: the judgement named none."
        )
        stream.emit(
            phase="analysis",
            kind="error",
            claim_id=claim.claim_id,
            outcome="handled",
            detail={
                "error": f"the judgement named no evidence for action {action!r}",
                "fell_back_to": "catalogue evidence_required",
            },
        )
    for reason in withheld_reasons(claim):
        # The narrowing is part of the answer, not a detail of how it was
        # produced. Someone reading this later should not have to guess why
        # appeal was never on the table.
        rationale = f"{rationale} Appeal was not available: {reason}."

    return Determination(
        claim_id=claim.claim_id,
        action=action,  # pyright: ignore[reportArgumentType] - checked above
        rationale=rationale,
        evidence_required=tuple(str(item) for item in evidence),
        # A `close` abandons the claim, so there is nothing left to rank and no
        # recovery to expect. The catalogue's likelihood is the figure for the
        # family's *default* action, so carrying it here would print an expected
        # recovery beside a claim nobody is going to work. A guardrailed close
        # records no Priority; a judged one should read the same.
        priority=(
            None
            if action == "close"
            else Priority(
                amount_at_stake=claim.amount_denied,
                likelihood=profile.recovery_likelihood,
            )
        ),
    )


def _decision(response: Any) -> dict[str, Any]:
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == DECISION_TOOL_NAME:
            raw: object = block.input
            if isinstance(raw, dict):
                return dict(raw)  # pyright: ignore[reportUnknownArgumentType]
            if isinstance(raw, str):
                # Never string-matched: these models vary their JSON escaping.
                parsed: object = json.loads(raw)
                if isinstance(parsed, dict):
                    return dict(parsed)  # pyright: ignore[reportUnknownArgumentType]
    raise JudgementRefused("the model returned no determination")
