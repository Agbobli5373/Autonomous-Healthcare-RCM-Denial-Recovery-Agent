"""The Claim a Determination is made about, built from what an EOB said.

Kept apart from the deciding: this module only turns an `Extraction` into the
domain object, and takes no view on what should be done about it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from rcm_agent.analysis.extract import Extraction
from rcm_agent.domain import Adjustment, Claim, ServiceLine


@dataclass(frozen=True, slots=True)
class ClaimIdentity:
    """Who and when. Known from the systems, not read off the document.

    Kept separate from the extracted adjustments so it is obvious which facts
    drove the Determination: the identity says *which* claim is being answered
    and takes no part in deciding what to do about it.
    """

    claim_id: str
    payer: str
    patient_id: str
    date_of_service: date

    @classmethod
    def of(cls, claim: Claim) -> ClaimIdentity:
        """The identity of a Claim already known from the fixtures or the PMS."""
        return cls(
            claim_id=claim.claim_id,
            payer=claim.payer,
            patient_id=claim.patient_id,
            date_of_service=claim.date_of_service,
        )


def claim_from_extraction(extraction: Extraction, identity: ClaimIdentity) -> Claim:
    """Build the Claim the guardrails read, from what the EOB actually said.

    Every adjustment here came out of the document. Nothing is filled in from the
    committed fixtures - if the extraction misread a code, the Determination is
    made on the misread code, which is the honest behaviour and the reason the
    extraction is tested as hard as it is.

    Adjustments attach to service lines (ADR-0001). A line number the document
    did not carry becomes its own line rather than being merged into another:
    guessing which line an adjustment belongs to would be inventing structure the
    page did not have.
    """
    by_line: dict[int, list[Adjustment]] = {}
    procedures: dict[int, str] = {}
    for index, extracted in enumerate(extraction.lines, start=1):
        number = extracted.line_number if extracted.line_number is not None else index
        by_line.setdefault(number, []).append(
            Adjustment(
                group=extracted.group,  # pyright: ignore[reportArgumentType] - parser-constrained
                reason_code=extracted.reason_code,
                amount=Decimal(extracted.amount),
                remark_codes=tuple(extracted.remark_codes),
            )
        )
        if extracted.procedure_code:
            procedures.setdefault(number, extracted.procedure_code)

    return Claim(
        claim_id=identity.claim_id,
        payer=identity.payer,
        patient_id=identity.patient_id,
        date_of_service=identity.date_of_service,
        service_lines=tuple(
            ServiceLine(
                line_number=number,
                procedure_code=procedures.get(number, ""),
                # The EOB states what was adjusted, not what was charged. Left at
                # zero rather than invented: nothing in the Determination reads
                # it, and a plausible fabricated charge would end up in an appeal.
                # `judgement._facts` omits it rather than show the model a zero.
                charge=Decimal("0"),
                adjustments=tuple(adjustments),
            )
            for number, adjustments in sorted(by_line.items())
        ),
    )
