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


CHART_MONTHS: tuple[str, ...] = (
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
)
"""The month names the chart prints, written out rather than left to `strftime`.

`%b` is locale-dependent on both sides. On a machine running a non-English
locale the mock would render `01-févr.-2026` and the tool that reads it back
would be looking for `FEB` — a failure that appears only on someone else's
laptop, which is the worst kind. This module is uploaded to the sandbox, so both
the rendering and the parsing can share one definition.
"""


def render_chart_date(value: date) -> str:
    """A date as the practice-management system prints it: `14-MAR-2026`."""
    return f"{value.day:02d}-{CHART_MONTHS[value.month - 1]}-{value.year}"


def parse_chart_date(text: str) -> date:
    """Read a date back off the chart. The inverse of `render_chart_date`.

    Strict: a date the agent is going to compare against a claim's date of
    service is not somewhere to guess. A shape this does not recognise raises
    rather than returning something plausible.
    """
    parts = text.strip().upper().split("-")
    if len(parts) != 3 or parts[1] not in CHART_MONTHS:
        raise RecordFileError(f"{text!r} is not a chart date like 14-MAR-2026")
    try:
        return date(int(parts[2]), CHART_MONTHS.index(parts[1]) + 1, int(parts[0]))
    except ValueError as exc:
        raise RecordFileError(f"{text!r} is not a chart date like 14-MAR-2026") from exc
