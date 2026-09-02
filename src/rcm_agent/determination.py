"""Turning a Claim into a Determination.

Guardrails run first and short-circuit. They are **rules, not thresholds**
(ADR-0002): where the law or the contract leaves no judgement to exercise, no
amount of model confidence may override them. A guardrailed Determination never
reaches scoring at all, which is why its Priority is `None` rather than zero —
nothing was weighed.

Only if no guardrail fires does the catalogue supply an Action. Today that is a
documented default per denial family; a later ticket replaces it with a real
judgement over the claim's evidence. The seam is deliberate: the guardrails are
the part that must never be delegated to a model.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from rcm_agent.catalogue import NON_APPEALABLE_CODES, UNAPPEALABLE_REMARKS, profile_for
from rcm_agent.domain import Adjustment, Claim, Determination, Priority

GuardrailRule = Callable[[Claim], Determination | None]


@dataclass(frozen=True, slots=True)
class Guardrail:
    """A rule and the name it is known by.

    The name is carried rather than derived from the function: a rule's name and
    the label its Determination ends up with are different things.
    `nothing-was-refused` can answer with either `patient-responsibility` or
    `no-denial` depending on what it found, and an inspector showing which rules
    ran needs the rule, not one of its outcomes.
    """

    name: str
    rule: GuardrailRule


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    """One rule, and what it did.

    `name` rather than `rule`, because `Guardrail.rule` is the callable and two
    attributes spelled the same meaning different things in one module.

    `guardrail` carries the label the Determination ended up with, present only
    when this rule fired. Without it the record contradicts itself: the trace
    would say `nothing-was-refused` while the determination beside it says
    `patient-responsibility`, and nothing would connect the two.
    """

    name: str
    fired: bool
    guardrail: str | None = None


@dataclass(frozen=True, slots=True)
class GuardrailTrace:
    """What the guardrails did, and what they decided.

    Only rules that actually ran appear. The loop short-circuits, so a rule
    sitting after the one that fired never executed - listing it as `passed`
    would record something that did not happen.
    """

    evaluated: tuple[RuleOutcome, ...]
    determination: Determination | None

    @property
    def fired(self) -> RuleOutcome | None:
        """The rule that answered the claim, if one did.

        Only the last entry can have fired - the loop short-circuits - so this
        reads it rather than searching for it.
        """
        last = self.evaluated[-1] if self.evaluated else None
        return last if last is not None and last.fired else None


def governing_denial(claim: Claim) -> Adjustment:
    """The denial the Determination answers.

    The largest by amount: where a claim carries several, the money is the
    honest tie-break, and it keeps the choice independent of line ordering.
    """
    return max(claim.denials, key=lambda a: a.amount)


def _unappealable_remark(claim: Claim) -> Determination | None:
    """A remark that removes appeal rights outright.

    Checked across the whole claim, not just the governing adjustment: an
    `MA130` sitting beside an otherwise appealable denial still means the claim
    was never adjudicated, and an appeal would be void.
    """
    for adjustment in claim.adjustments:
        for remark in adjustment.remark_codes:
            if remark in UNAPPEALABLE_REMARKS:
                return Determination(
                    claim_id=claim.claim_id,
                    action="close",
                    rationale=(
                        f"Remark {remark} carries no appeal rights: the claim was "
                        "returned as unprocessable rather than adjudicated. A "
                        "corrected claim, not an appeal."
                    ),
                    guardrail=f"unappealable-remark:{remark}",
                )
    return None


def _non_appealable_governing_code(claim: Claim) -> Determination | None:
    """A non-appealable code, but only where it is the denial we are answering.

    Scoped to the governing denial rather than the whole claim, for the same
    reason `CO-45` is: `CO-253` is the sequestration reduction and rides along on
    essentially every Medicare remittance, so a claim-wide check would silently
    close genuinely appealable denials that merely share a claim with one. That
    is the exact failure the `CO-45` rule below exists to prevent, and it was
    reintroduced here on the neighbouring codes.
    """
    if not claim.denials:
        return None

    adjustment = governing_denial(claim)
    if adjustment.code not in NON_APPEALABLE_CODES:
        return None

    return Determination(
        claim_id=claim.claim_id,
        action="close",
        rationale=f"{adjustment.code} is not a refusal the provider can contest.",
        guardrail=f"non-appealable-code:{adjustment.code}",
    )


def _nothing_was_refused(claim: Claim) -> Determination | None:
    """No denial anywhere on the claim, so there is nothing to recover.

    This is the `CO-45` false positive and the `PR-1/2/3` trap in one rule. Both
    reduce what the payer pays without refusing anything, and an agent that
    appeals either has failed the domain.

    It is only expressible at line grain (ADR-0001): a write-off on one line
    beside a denial on another must *not* reach this rule.
    """
    if claim.denials:
        return None

    if claim.patient_responsibility > 0:
        return Determination(
            claim_id=claim.claim_id,
            action="patient_bill",
            rationale=(
                "Only patient-responsibility amounts remain: deductible, coinsurance or "
                "copay. Nothing was refused, so there is nothing to appeal."
            ),
            guardrail="patient-responsibility",
        )

    return Determination(
        claim_id=claim.claim_id,
        action="close",
        rationale=(
            "No adjustment on this claim refuses payment. A contractual write-off "
            "standing alone means the claim was paid correctly."
        ),
        guardrail="no-denial",
    )


GUARDRAILS: tuple[Guardrail, ...] = (
    Guardrail("unappealable-remark", _unappealable_remark),
    Guardrail("nothing-was-refused", _nothing_was_refused),
    Guardrail("non-appealable-code", _non_appealable_governing_code),
)
"""Order matters.

The first two are claim-wide: an `MA130` means the claim was never adjudicated,
and a claim with no refusal on it has nothing to recover. Only then is there a
governing denial for the third to look at.
"""


def run_guardrails(claim: Claim) -> GuardrailTrace:
    """Run the guardrails in order and report what they did.

    Split out because both routes to a Determination begin here and neither may
    skip it - ADR-0002 is only true while the guardrails run first, so there is
    one loop rather than a copy per caller.

    Returns the trace rather than emitting it. This module decides whether a
    patient's claim may be appealed; it does not also do I/O, and its tests do
    not construct an event stream to call it. The caller owns what is recorded.
    """
    evaluated: list[RuleOutcome] = []
    for guardrail in GUARDRAILS:
        determination = guardrail.rule(claim)
        if determination is not None:
            evaluated.append(
                RuleOutcome(name=guardrail.name, fired=True, guardrail=determination.guardrail)
            )
            return GuardrailTrace(tuple(evaluated), determination)
        evaluated.append(RuleOutcome(name=guardrail.name, fired=False))
    return GuardrailTrace(tuple(evaluated), None)


def determine(claim: Claim) -> Determination:
    """Guardrails, then the catalogue's documented default for the family.

    The model-free Determination: what this project can say about a denial
    without asking anything.
    """
    trace = run_guardrails(claim)
    if trace.determination is not None:
        return trace.determination
    return from_catalogue(claim)


def from_catalogue(claim: Claim) -> Determination:
    """The documented default for the governing denial's family.

    Split from `determine` so a caller that has *already* run the guardrails can
    reach the default without running them again. `determine_with_judgement`
    falls back here when a judgement is unusable, and it knows by then that no
    rule fired; re-deciding that would evaluate the rules a second time and put a
    second, unrecorded evaluation behind a Determination.
    """
    denial = governing_denial(claim)
    profile = profile_for(denial.code)

    return Determination(
        claim_id=claim.claim_id,
        action=profile.default_action,
        rationale=f"{denial.code}: {profile.rationale}",
        evidence_required=profile.evidence_required,
        priority=Priority(
            amount_at_stake=claim.amount_denied,
            likelihood=profile.recovery_likelihood,
        ),
    )
