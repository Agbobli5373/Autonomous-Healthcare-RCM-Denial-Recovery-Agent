"""The denial codes the demo models, and what each one calls for.

Ten tuples in the table, plus `CO-45` and `PR-1/2/3` handled by guardrails
before any lookup. Chosen so that roughly half call for something other than an
appeal, several need claim *context* rather than a code lookup, and two are traps
for a model that has learned "denial -> appeal". Answering `appeal` everywhere
scores badly here by construction.

`default_action` is what the code alone implies. For several families the real
answer depends on evidence the code does not carry — whether an authorization
exists, whether the filing was timely, what an NCCI edit says — and a later
ticket replaces the default with an actual determination over that evidence. The
default is never `appeal` for a family whose appealability is unknown: filing on
a code we do not understand is a worse failure than closing it.
"""

from __future__ import annotations

from dataclasses import dataclass

from rcm_agent.domain import Action

UNAPPEALABLE_REMARKS = frozenset({"MA130", "N211"})
"""Remark codes that carry no appeal rights.

`MA130` is Medicare's "returned as unprocessable": it arrives on a remittance and
looks exactly like a denial, but there is nothing to appeal. An agent that files
against one has done something worse than fail — it has wasted a person's time on
a legally void submission.
"""

NON_APPEALABLE_CODES = frozenset({"OA-23", "CO-253"})
"""Adjustment codes with no appeal rights: another payer's adjudication, and the
sequestration reduction. Neither is a refusal the provider can contest.

Group and Reason together, never a bare Reason Code: `CO-253` and a hypothetical
`PR-253` would not mean the same thing.
"""


@dataclass(frozen=True, slots=True)
class DenialProfile:
    family: str
    default_action: Action
    rationale: str
    evidence_required: tuple[str, ...] = ()
    recovery_likelihood: float = 0.0
    """Used only for Priority. It ranks a worklist and never decides an Action."""


CATALOGUE: dict[str, DenialProfile] = {
    "CO-197": DenialProfile(
        family="Prior authorization",
        default_action="appeal",
        rationale="Prior authorization reported missing; appealable where a valid "
        "authorization covered the date of service.",
        evidence_required=("Authorization record", "Date of service"),
        recovery_likelihood=0.45,
    ),
    "CO-50": DenialProfile(
        family="Medical necessity",
        default_action="appeal",
        rationale="Not deemed medically necessary; appealable with clinical documentation "
        "argued against the coverage determination.",
        evidence_required=("Clinical notes", "Coverage determination"),
        recovery_likelihood=0.35,
    ),
    "PR-50": DenialProfile(
        family="Medical necessity, liability shifted",
        default_action="patient_bill",
        rationale="Liability shifted to the patient, so nothing was refused to the provider.",
        recovery_likelihood=0.0,
    ),
    "CO-29": DenialProfile(
        family="Timely filing",
        default_action="appeal",
        rationale="Filed after the deadline; appealable only with proof of timely submission.",
        evidence_required=("Proof of timely submission",),
        recovery_likelihood=0.25,
    ),
    "OA-22": DenialProfile(
        family="Coordination of benefits",
        default_action="rebill",
        rationale="Another payer is primary. Recovered by rebilling, not by appealing.",
        evidence_required=("Primary payer remittance",),
        recovery_likelihood=0.7,
    ),
    "CO-16": DenialProfile(
        family="Missing or invalid information",
        default_action="corrected_claim",
        rationale="Claim lacks information needed to adjudicate; resolved by correcting "
        "and resubmitting.",
        evidence_required=("Corrected claim",),
        recovery_likelihood=0.6,
    ),
    "CO-236": DenialProfile(
        family="Bundling (NCCI procedure-to-procedure)",
        default_action="corrected_claim",
        rationale="Procedure pair conflicts with an NCCI edit. Whether a modifier is "
        "permitted lives in the edit file, not in the code.",
        evidence_required=("NCCI modifier indicator",),
        recovery_likelihood=0.3,
    ),
    "CO-97": DenialProfile(
        family="Bundling (payer policy)",
        default_action="appeal",
        rationale="Payment bundled into another service under payer policy; appealable "
        "with documentation that the services were distinct.",
        evidence_required=("Operative note",),
        recovery_likelihood=0.3,
    ),
    "OA-18": DenialProfile(
        family="Duplicate",
        default_action="close",
        rationale="Duplicate of a claim already adjudicated. Triaged out rather than appealed.",
        recovery_likelihood=0.05,
    ),
    "CO-96": DenialProfile(
        family="Non-covered service",
        default_action="close",
        rationale="Service not covered by the plan. Appealable only where the exclusion "
        "is plan policy rather than statute, which the code does not distinguish.",
        recovery_likelihood=0.1,
    ),
}
"""Keyed by the Group Code and Reason Code together, because a Reason Code alone
is ambiguous — `CO-50` and `PR-50` share one and have opposite outcomes.

`CO-45` and `PR-1/2/3` are deliberately absent: they are not denials at all, and
are handled by guardrails before any catalogue lookup happens.
"""

UNKNOWN_CODE = DenialProfile(
    family="Unrecognised",
    default_action="close",
    rationale="Adjustment code is not in the modelled subset, so no action can be "
    "justified from it. Closed rather than guessed.",
    recovery_likelihood=0.0,
)


def profile_for(code: str) -> DenialProfile:
    return CATALOGUE.get(code, UNKNOWN_CODE)
