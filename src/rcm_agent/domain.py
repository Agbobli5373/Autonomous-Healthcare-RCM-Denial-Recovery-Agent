"""The domain types, in the vocabulary of `CONTEXT.md`.

Two decisions from the ADRs are load-bearing here and are expressed in the types
rather than left to convention:

* **Adjustments attach to Service Lines, not Claims** (ADR-0001). One claim
  routinely mixes outcomes — a contractual write-off on one line beside a denial
  on another — and the guardrails are only expressible at that grain.
* **A Determination names an Action, not a recoverability score** (ADR-0002).
  Priority exists separately and never decides an Action.

The adjudication outcome carried here is two-valued. A front-end `Rejection`
never produces a remittance, so nothing in the data path can carry one; the word
stays defined in the glossary because it is the most misused term in the domain,
but a state nothing can populate does not belong in the type system.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

GroupCode = Literal["CO", "PR", "OA", "PI"]
"""Who bears the adjusted amount, and therefore whether anything is appealable.

`CO` provider, `PR` patient, `OA` other, `PI` payer-initiated.
"""

Action = Literal["appeal", "corrected_claim", "rebill", "patient_bill", "close"]
"""What a Determination calls for. Exactly the five from `CONTEXT.md`.

Most denial volume is correction work rather than appeal work, so `appeal` is one
option among five and never a default.
"""

PATIENT_RESPONSIBILITY_CARCS = frozenset({"1", "2", "3"})
"""Deductible, coinsurance, copay. Nothing was refused, so nothing is appealable."""

CONTRACTUAL_WRITE_OFF_CARC = "45"
"""Standing alone this means the claim was paid correctly."""


@dataclass(frozen=True, slots=True)
class Adjustment:
    """One reason a Service Line was paid at less than its charge.

    Always a triple: Group Code, Reason Code (CARC) and zero or more Remark
    Codes (RARC). The CARC alone is deliberately underspecified — `CO-50` and
    `PR-50` share a Reason Code and have opposite outcomes — so the group is
    never optional and the tuple is never flattened to a single code.
    """

    group: GroupCode
    reason_code: str
    amount: Decimal
    remark_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Normalise the codes at construction, so no caller can slip past a guardrail.

        The guardrails match on exact strings. A remark of `ma130` or ` MA130`
        would otherwise sail through `UNAPPEALABLE_REMARKS` and produce a legally
        void appeal — and every caller would have to remember to normalise first.
        Doing it here means there is no unnormalised Adjustment to reason about.
        """
        object.__setattr__(self, "reason_code", self.reason_code.strip().upper())
        object.__setattr__(
            self, "remark_codes", tuple(r.strip().upper() for r in self.remark_codes)
        )

    @property
    def code(self) -> str:
        """The tuple as it is written in prose, e.g. `CO-197`."""
        return f"{self.group}-{self.reason_code}"

    @property
    def is_patient_responsibility(self) -> bool:
        return self.group == "PR" and self.reason_code in PATIENT_RESPONSIBILITY_CARCS

    @property
    def is_contractual_write_off(self) -> bool:
        return self.group == "CO" and self.reason_code == CONTRACTUAL_WRITE_OFF_CARC

    @property
    def refuses_payment(self) -> bool:
        """Whether this adjustment is a refusal at all.

        A write-off and a patient-responsibility amount both reduce what the
        payer pays without refusing anything, which is why neither is a Denial.
        """
        return not (self.is_patient_responsibility or self.is_contractual_write_off)


@dataclass(frozen=True, slots=True)
class ServiceLine:
    """One billed service within a Claim, carrying its own charge and adjustments."""

    line_number: int
    procedure_code: str
    charge: Decimal
    adjustments: tuple[Adjustment, ...] = ()

    @property
    def denials(self) -> tuple[Adjustment, ...]:
        return tuple(a for a in self.adjustments if a.refuses_payment)


@dataclass(frozen=True, slots=True)
class Claim:
    """A provider's request for payment for services on a date of service."""

    claim_id: str
    payer: str
    patient_id: str
    date_of_service: date
    service_lines: tuple[ServiceLine, ...]

    @property
    def denials(self) -> tuple[Adjustment, ...]:
        return tuple(a for line in self.service_lines for a in line.denials)

    @property
    def adjustments(self) -> tuple[Adjustment, ...]:
        return tuple(a for line in self.service_lines for a in line.adjustments)

    @property
    def amount_denied(self) -> Decimal:
        return sum((a.amount for a in self.denials), Decimal("0"))

    @property
    def patient_responsibility(self) -> Decimal:
        return sum(
            (a.amount for a in self.adjustments if a.is_patient_responsibility), Decimal("0")
        )


@dataclass(frozen=True, slots=True)
class Authorization:
    """A payer's advance approval for a service.

    Lives in the practice-management system, not on the Claim. Proving that a
    valid Authorization covered the date of service is how a prior-authorization
    denial is overturned — which is why the validity range is a real date range
    and not a string.
    """

    authorization_number: str
    valid_from: date
    valid_to: date
    covered_procedure_codes: tuple[str, ...] = ()

    def covers(self, procedure_code: str, on: date) -> bool:
        within_dates = self.valid_from <= on <= self.valid_to
        in_scope = not self.covered_procedure_codes or procedure_code in (
            self.covered_procedure_codes
        )
        return within_dates and in_scope


@dataclass(frozen=True, slots=True)
class Priority:
    """How worth working a Determination is, relative to others.

    Ranks a worklist. It never decides an Action — ADR-0002 keeps ranking and
    deciding apart deliberately, so that no amount of confidence can override a
    Guardrail.
    """

    amount_at_stake: Decimal
    likelihood: float

    @property
    def expected_recovery(self) -> Decimal:
        return (self.amount_at_stake * Decimal(str(self.likelihood))).quantize(Decimal("0.01"))


@dataclass(frozen=True, slots=True)
class Determination:
    """The agent's conclusion about one Claim: an Action, why, and what it needs."""

    claim_id: str
    action: Action
    rationale: str
    evidence_required: tuple[str, ...] = ()
    guardrail: str | None = None
    priority: Priority | None = None

    @property
    def was_guardrailed(self) -> bool:
        """Whether a rule fixed this Action without any judgement being exercised."""
        return self.guardrail is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "claim_id": self.claim_id,
            "action": self.action,
            "rationale": self.rationale,
            "evidence_required": list(self.evidence_required),
            "guardrail": self.guardrail,
            "priority": (
                None
                if self.priority is None
                else {
                    "amount_at_stake": str(self.priority.amount_at_stake),
                    "likelihood": self.priority.likelihood,
                    "expected_recovery": str(self.priority.expected_recovery),
                }
            ),
        }
