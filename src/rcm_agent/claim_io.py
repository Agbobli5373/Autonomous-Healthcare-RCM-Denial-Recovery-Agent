"""Reading Claims from JSON.

Validation is strict and the errors name the field that is wrong. These files are
fixtures today and extracted output tomorrow, and a claim that is silently wrong
is far more dangerous here than one that fails to load: an Adjustment missing its
Group Code would make `CO-50` and `PR-50` indistinguishable.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast, get_args

from rcm_agent.domain import Adjustment, Claim, GroupCode, ServiceLine

GROUP_CODES = get_args(GroupCode)
"""Derived from the type, so the two cannot drift apart."""


class ClaimFileError(ValueError):
    """A claim file that cannot be trusted to mean what it says."""


def _require(data: dict[str, Any], key: str, where: str) -> Any:
    if key not in data:
        raise ClaimFileError(f"{where}: missing required field {key!r}")
    return data[key]


def _as_mapping(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ClaimFileError(f"{where}: expected an object, got {type(value).__name__}")
    return cast(dict[str, Any], value)


def _as_decimal(value: Any, where: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ClaimFileError(f"{where}: {value!r} is not an amount") from exc


def _as_date(value: Any, where: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ClaimFileError(f"{where}: {value!r} is not an ISO date") from exc


def _as_group_code(value: Any, where: str) -> GroupCode:
    if value not in GROUP_CODES:
        raise ClaimFileError(
            f"{where}: {value!r} is not a group code. Expected one of {', '.join(GROUP_CODES)}"
        )
    return value


def _adjustment_from(data: Any, where: str) -> Adjustment:
    fields = _as_mapping(data, where)
    remarks = fields.get("remark_codes", [])
    if not isinstance(remarks, list):
        raise ClaimFileError(f"{where}.remark_codes: expected a list")
    return Adjustment(
        group=_as_group_code(_require(fields, "group", where), f"{where}.group"),
        reason_code=str(_require(fields, "reason_code", where)),
        amount=_as_decimal(_require(fields, "amount", where), f"{where}.amount"),
        remark_codes=tuple(str(r) for r in cast(list[Any], remarks)),
    )


def _service_line_from(data: Any, where: str) -> ServiceLine:
    fields = _as_mapping(data, where)
    adjustments = fields.get("adjustments", [])
    if not isinstance(adjustments, list):
        raise ClaimFileError(f"{where}.adjustments: expected a list")
    return ServiceLine(
        line_number=int(_require(fields, "line_number", where)),
        procedure_code=str(_require(fields, "procedure_code", where)),
        charge=_as_decimal(_require(fields, "charge", where), f"{where}.charge"),
        adjustments=tuple(
            _adjustment_from(a, f"{where}.adjustments[{i}]")
            for i, a in enumerate(cast(list[Any], adjustments))
        ),
    )


def claim_from_dict(data: Any) -> Claim:
    fields = _as_mapping(data, "claim")
    lines = _require(fields, "service_lines", "claim")
    if not isinstance(lines, list) or not lines:
        raise ClaimFileError("claim.service_lines: expected a non-empty list")
    return Claim(
        claim_id=str(_require(fields, "claim_id", "claim")),
        payer=str(_require(fields, "payer", "claim")),
        patient_id=str(_require(fields, "patient_id", "claim")),
        date_of_service=_as_date(
            _require(fields, "date_of_service", "claim"), "claim.date_of_service"
        ),
        service_lines=tuple(
            _service_line_from(line, f"claim.service_lines[{i}]")
            for i, line in enumerate(cast(list[Any], lines))
        ),
    )


def load_claim(path: Path) -> Claim:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ClaimFileError(f"{path}: no such file") from exc
    except json.JSONDecodeError as exc:
        raise ClaimFileError(f"{path}: not valid JSON - {exc.msg} at line {exc.lineno}") from exc
    return claim_from_dict(raw)
