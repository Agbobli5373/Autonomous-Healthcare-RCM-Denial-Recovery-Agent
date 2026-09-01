"""Reading the practice-management system's records from JSON.

A `PracticeRecord` is what the practice holds about one episode of care: who the
patient is, what was done and when, and — when there is one — the Authorization
the payer granted in advance. The Claim is the payer's view of the same episode;
this is the provider's, which is why the patient's name lives here and not on the
Claim.

The Authorization itself is the domain type, not a copy of it. Proving that a
valid Authorization covered the date of service is how a prior-authorization
Denial is overturned, and that comparison has to run against real dates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from rcm_agent.domain import Authorization
from rcm_agent.strict_json import (
    RecordFileError,
    as_date,
    as_list,
    as_mapping,
    read_json,
    require,
)


@dataclass(frozen=True, slots=True)
class PracticeRecord:
    """One episode of care, as the practice-management system holds it."""

    claim_id: str
    patient_id: str
    patient_name: str
    date_of_service: date
    ordering_provider: str
    authorization: Authorization | None = None


def _authorization_from(data: Any, where: str) -> Authorization:
    fields = as_mapping(data, where)
    valid_from = as_date(require(fields, "valid_from", where), f"{where}.valid_from")
    valid_to = as_date(require(fields, "valid_to", where), f"{where}.valid_to")
    if valid_to < valid_from:
        # An Authorization whose range runs backwards can never cover a date of
        # service, so it would read on screen as evidence while proving nothing.
        raise RecordFileError(
            f"{where}.valid_to: {valid_to.isoformat()} is before valid_from "
            f"{valid_from.isoformat()}"
        )
    codes = as_list(
        require(fields, "covered_procedure_codes", where), f"{where}.covered_procedure_codes"
    )
    return Authorization(
        authorization_number=str(require(fields, "authorization_number", where)),
        valid_from=valid_from,
        valid_to=valid_to,
        covered_procedure_codes=tuple(str(code) for code in codes),
    )


def record_from_dict(data: Any) -> PracticeRecord:
    fields = as_mapping(data, "record")
    authorization = fields.get("authorization")
    return PracticeRecord(
        claim_id=str(require(fields, "claim_id", "record")),
        patient_id=str(require(fields, "patient_id", "record")),
        patient_name=str(require(fields, "patient_name", "record")),
        date_of_service=as_date(
            require(fields, "date_of_service", "record"), "record.date_of_service"
        ),
        ordering_provider=str(require(fields, "ordering_provider", "record")),
        authorization=(
            None
            if authorization is None
            else _authorization_from(authorization, "record.authorization")
        ),
    )


def load_practice_record(path: Path) -> PracticeRecord:
    return record_from_dict(read_json(path))
