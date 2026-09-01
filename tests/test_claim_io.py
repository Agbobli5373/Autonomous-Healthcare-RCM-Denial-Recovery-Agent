from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from rcm_agent.claim_io import ClaimFileError, claim_from_dict, load_claim

VALID: dict[str, Any] = {
    "claim_id": "CLM-0001",
    "payer": "Demo Health Plan",
    "patient_id": "PAT-1",
    "date_of_service": "2026-03-14",
    "service_lines": [
        {
            "line_number": 1,
            "procedure_code": "E1390",
            "charge": "450.00",
            "adjustments": [
                {"group": "CO", "reason_code": "197", "amount": "450.00", "remark_codes": ["N706"]}
            ],
        }
    ],
}


def without(key: str) -> dict[str, Any]:
    data = json.loads(json.dumps(VALID))
    del data[key]
    return data


def test_a_valid_claim_round_trips() -> None:
    claim = claim_from_dict(VALID)

    assert claim.claim_id == "CLM-0001"
    assert claim.date_of_service.isoformat() == "2026-03-14"
    assert claim.service_lines[0].adjustments[0].code == "CO-197"
    assert claim.service_lines[0].adjustments[0].remark_codes == ("N706",)


def test_amounts_are_decimal_not_float() -> None:
    """Money must not go through binary floating point."""
    claim = claim_from_dict(VALID)

    amount = claim.service_lines[0].adjustments[0].amount
    assert isinstance(amount, Decimal)
    assert amount == Decimal("450.00")


@pytest.mark.parametrize("field", ["claim_id", "payer", "patient_id", "date_of_service"])
def test_a_missing_required_field_is_named(field: str) -> None:
    with pytest.raises(ClaimFileError, match=field):
        claim_from_dict(without(field))


def test_a_missing_group_code_is_rejected() -> None:
    """Without the group code CO-50 and PR-50 are indistinguishable, so this cannot default."""
    data = json.loads(json.dumps(VALID))
    del data["service_lines"][0]["adjustments"][0]["group"]

    with pytest.raises(ClaimFileError, match="group"):
        claim_from_dict(data)


def test_an_invented_group_code_is_rejected() -> None:
    data = json.loads(json.dumps(VALID))
    data["service_lines"][0]["adjustments"][0]["group"] = "XX"

    with pytest.raises(ClaimFileError, match="not a group code"):
        claim_from_dict(data)


def test_the_error_says_which_adjustment_was_wrong() -> None:
    data = json.loads(json.dumps(VALID))
    data["service_lines"][0]["adjustments"][0]["amount"] = "not-money"

    with pytest.raises(ClaimFileError, match=r"service_lines\[0\]\.adjustments\[0\]\.amount"):
        claim_from_dict(data)


def test_a_bad_date_is_rejected() -> None:
    data = json.loads(json.dumps(VALID))
    data["date_of_service"] = "14/03/2026"

    with pytest.raises(ClaimFileError, match="ISO date"):
        claim_from_dict(data)


def test_a_claim_with_no_service_lines_is_rejected() -> None:
    data = json.loads(json.dumps(VALID))
    data["service_lines"] = []

    with pytest.raises(ClaimFileError, match="non-empty"):
        claim_from_dict(data)


def test_adjustments_are_optional_on_a_line() -> None:
    data = json.loads(json.dumps(VALID))
    del data["service_lines"][0]["adjustments"]

    claim = claim_from_dict(data)

    assert claim.service_lines[0].adjustments == ()


def test_a_missing_file_names_the_path(tmp_path: Path) -> None:
    with pytest.raises(ClaimFileError, match="no such file"):
        load_claim(tmp_path / "nope.json")


def test_malformed_json_reports_the_line(tmp_path: Path) -> None:
    path = tmp_path / "claim.json"
    path.write_text("{ not json", encoding="utf-8")

    with pytest.raises(ClaimFileError, match="not valid JSON"):
        load_claim(path)


def test_load_claim_reads_a_real_file(tmp_path: Path) -> None:
    path = tmp_path / "claim.json"
    path.write_text(json.dumps(VALID), encoding="utf-8")

    assert load_claim(path).claim_id == "CLM-0001"
