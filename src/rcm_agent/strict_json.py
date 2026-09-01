"""Reading JSON records that refuse to guess.

Every reader here fails rather than defaulting, and every error names the field
that is wrong. That rule comes from `claim_io`, where it earned itself: an
Adjustment missing its Group Code would make `CO-50` and `PR-50`
indistinguishable, and a file that is silently wrong is far more dangerous in
this domain than one that will not load.

These helpers live apart from `claim_io` because there is now a second kind of
record to read — the practice-management system's — and a second copy of "what a
valid date is" would eventually disagree with the first.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast


class RecordFileError(ValueError):
    """A record file that cannot be trusted to mean what it says."""


def require(data: dict[str, Any], key: str, where: str) -> Any:
    if key not in data:
        raise RecordFileError(f"{where}: missing required field {key!r}")
    return data[key]


def as_mapping(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RecordFileError(f"{where}: expected an object, got {type(value).__name__}")
    return cast(dict[str, Any], value)


def as_list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise RecordFileError(f"{where}: expected a list, got {type(value).__name__}")
    return cast(list[Any], value)


def as_decimal(value: Any, where: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RecordFileError(f"{where}: {value!r} is not an amount") from exc


def as_date(value: Any, where: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise RecordFileError(f"{where}: {value!r} is not an ISO date") from exc


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RecordFileError(f"{path}: no such file") from exc
    except json.JSONDecodeError as exc:
        raise RecordFileError(f"{path}: not valid JSON - {exc.msg} at line {exc.lineno}") from exc
