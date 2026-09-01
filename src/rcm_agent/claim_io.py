"""Reading Claims from JSON.

Validation is strict and the errors name the field that is wrong. These files are
fixtures today and extracted output tomorrow, and a claim that is silently wrong
is far more dangerous here than one that fails to load: an Adjustment missing its
Group Code would make `CO-50` and `PR-50` indistinguishable.

The field readers themselves live in `strict_json`, shared with the practice
records, so the two cannot disagree about what a valid date or amount is — and
they raise the one `RecordFileError` rather than a per-record subclass, because
nothing has ever needed to catch "a bad claim" apart from "a bad record".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, get_args

from rcm_agent.domain import Adjustment, Claim, GroupCode, ServiceLine
from rcm_agent.strict_json import (
    RecordFileError,
    as_date,
    as_decimal,
    as_list,
    as_mapping,
    read_json,
    require,
)

GROUP_CODES = get_args(GroupCode)
"""Derived from the type, so the two cannot drift apart."""


def _as_group_code(value: Any, where: str) -> GroupCode:
    if value not in GROUP_CODES:
        raise RecordFileError(
            f"{where}: {value!r} is not a group code. Expected one of {', '.join(GROUP_CODES)}"
        )
    return value


def _adjustment_from(data: Any, where: str) -> Adjustment:
    fields = as_mapping(data, where)
    remarks = as_list(fields.get("remark_codes", []), f"{where}.remark_codes")
    return Adjustment(
        group=_as_group_code(require(fields, "group", where), f"{where}.group"),
        reason_code=str(require(fields, "reason_code", where)),
        amount=as_decimal(require(fields, "amount", where), f"{where}.amount"),
        remark_codes=tuple(str(r) for r in remarks),
    )


def _service_line_from(data: Any, where: str) -> ServiceLine:
    fields = as_mapping(data, where)
    adjustments = as_list(fields.get("adjustments", []), f"{where}.adjustments")
    return ServiceLine(
        line_number=int(require(fields, "line_number", where)),
        procedure_code=str(require(fields, "procedure_code", where)),
        charge=as_decimal(require(fields, "charge", where), f"{where}.charge"),
        adjustments=tuple(
            _adjustment_from(a, f"{where}.adjustments[{i}]") for i, a in enumerate(adjustments)
        ),
    )


def claim_from_dict(data: Any) -> Claim:
    fields = as_mapping(data, "claim")
    lines = as_list(require(fields, "service_lines", "claim"), "claim.service_lines")
    if not lines:
        raise RecordFileError("claim.service_lines: expected a non-empty list")
    return Claim(
        claim_id=str(require(fields, "claim_id", "claim")),
        payer=str(require(fields, "payer", "claim")),
        patient_id=str(require(fields, "patient_id", "claim")),
        date_of_service=as_date(
            require(fields, "date_of_service", "claim"), "claim.date_of_service"
        ),
        service_lines=tuple(
            _service_line_from(line, f"claim.service_lines[{i}]") for i, line in enumerate(lines)
        ),
    )


def load_claim(path: Path) -> Claim:
    return claim_from_dict(read_json(path))
