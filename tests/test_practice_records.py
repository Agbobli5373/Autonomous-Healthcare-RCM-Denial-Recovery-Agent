"""The practice-management system's side of the committed fixtures.

The load-bearing test here is `test_the_authorization_covers_the_denied_line`.
The hero claim's whole story is that `CO-197` asserts no Authorization was on
file and the agent proves otherwise, so if the fixture's date range ever stops
covering the date of service, the demo argues for something untrue — and it
would do it silently, because every other test would still pass.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from rcm_agent.claim_io import load_claim
from rcm_agent.domain import Authorization
from rcm_agent.mocks import fixtures_data
from rcm_agent.practice_io import PracticeRecord, load_practice_record, record_from_dict
from rcm_agent.strict_json import RecordFileError

HERO_CLAIM = "CLM-2026-0001"


def hero_record() -> PracticeRecord:
    record = fixtures_data.find_record(HERO_CLAIM)
    assert record is not None, "the practice fixture for the hero claim is missing"
    return record


# --- the fixtures on disk --------------------------------------------------


def test_every_committed_claim_has_a_practice_record() -> None:
    """A patient the agent cannot look up is a patient the demo cannot explain."""
    for claim in fixtures_data.worklist():
        assert fixtures_data.find_record(claim.claim_id) is not None


def test_only_the_prior_authorization_claim_has_an_authorization() -> None:
    """An empty record has to exist somewhere, or finding one proves nothing."""
    with_authorization = [r.claim_id for r in fixtures_data.practice_records() if r.authorization]

    assert with_authorization == [HERO_CLAIM]


def test_the_record_carries_a_patient_name_the_claim_does_not() -> None:
    """The claim knows a patient id; the practice-management system knows the person."""
    record = hero_record()

    assert record.patient_name
    assert record.patient_id == "PAT-40219"


# --- the invariant the demo's argument rests on ----------------------------


def test_the_authorization_covers_the_denied_line() -> None:
    """The `CO-197` denial says no Authorization was on file. This is the proof.

    Both halves are read from the committed fixtures and the denied line is
    found rather than named, so editing either file to disagree fails here
    instead of producing a demo that argues for something untrue.
    """
    claim = load_claim(fixtures_data.FIXTURES_ROOT / "claims" / "clm-2026-0001.json")
    authorization = hero_record().authorization
    assert authorization is not None

    denied_lines = [line for line in claim.service_lines if line.denials]
    assert denied_lines, "the hero claim has no denied line to authorize"

    for line in denied_lines:
        assert authorization.covers(line.procedure_code, claim.date_of_service), (
            f"line {line.line_number} ({line.procedure_code}) is not covered "
            f"on {claim.date_of_service}"
        )


def test_the_written_off_line_is_not_in_the_authorized_scope() -> None:
    """Scope has to exclude something, or `covers` is only ever testing the dates."""
    authorization = hero_record().authorization
    assert authorization is not None

    assert authorization.covered_procedure_codes
    assert "E1390" not in authorization.covered_procedure_codes


def test_the_date_of_service_is_not_on_either_boundary() -> None:
    """A range that only just covers the date reads as a coincidence on screen."""
    record = hero_record()
    authorization = record.authorization
    assert authorization is not None

    assert authorization.valid_from < record.date_of_service < authorization.valid_to


# --- reading the files -----------------------------------------------------


def test_a_record_without_an_authorization_reads_as_none() -> None:
    record = record_from_dict(
        {
            "claim_id": "CLM-1",
            "patient_id": "PAT-1",
            "patient_name": "DOE, JANE",
            "date_of_service": "2026-03-14",
            "ordering_provider": "OKAFOR, N MD",
        }
    )

    assert record.authorization is None


def test_an_authorization_reads_into_the_domain_type() -> None:
    record = record_from_dict(
        {
            "claim_id": "CLM-1",
            "patient_id": "PAT-1",
            "patient_name": "DOE, JANE",
            "date_of_service": "2026-03-14",
            "ordering_provider": "OKAFOR, N MD",
            "authorization": {
                "authorization_number": "CHP-1",
                "valid_from": "2026-01-01",
                "valid_to": "2026-12-31",
                "covered_procedure_codes": ["E0601"],
            },
        }
    )

    assert isinstance(record.authorization, Authorization)
    assert record.authorization.valid_from == date(2026, 1, 1)
    assert record.authorization.covered_procedure_codes == ("E0601",)


@pytest.mark.parametrize(
    "field", ["claim_id", "patient_id", "patient_name", "date_of_service", "ordering_provider"]
)
def test_a_missing_field_names_itself(field: str) -> None:
    data = {
        "claim_id": "CLM-1",
        "patient_id": "PAT-1",
        "patient_name": "DOE, JANE",
        "date_of_service": "2026-03-14",
        "ordering_provider": "OKAFOR, N MD",
    }
    del data[field]

    with pytest.raises(RecordFileError, match=field):
        record_from_dict(data)


def test_a_validity_range_that_ends_before_it_starts_is_refused() -> None:
    """An Authorization that cannot cover anything is a fixture bug, not a record."""
    with pytest.raises(RecordFileError, match="valid_to"):
        record_from_dict(
            {
                "claim_id": "CLM-1",
                "patient_id": "PAT-1",
                "patient_name": "DOE, JANE",
                "date_of_service": "2026-03-14",
                "ordering_provider": "OKAFOR, N MD",
                "authorization": {
                    "authorization_number": "CHP-1",
                    "valid_from": "2026-12-31",
                    "valid_to": "2026-01-01",
                    "covered_procedure_codes": ["E0601"],
                },
            }
        )


def test_a_missing_file_says_so(tmp_path: Path) -> None:
    with pytest.raises(RecordFileError, match="no such file"):
        load_practice_record(tmp_path / "absent.json")
