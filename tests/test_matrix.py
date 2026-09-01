from __future__ import annotations

from datetime import UTC, datetime

from rcm_agent.events import EventStream
from rcm_agent.matrix import PHASES, ClaimMatrix

CLAIMS = ["CLM-0001", "CLM-0002", "CLM-0003"]


def stream_into(matrix: ClaimMatrix) -> EventStream:
    stream = EventStream(clock=lambda: datetime(2026, 9, 1, tzinfo=UTC))
    stream.add_sink(matrix)
    return stream


def test_every_cell_starts_pending() -> None:
    matrix = ClaimMatrix(CLAIMS)

    assert all(matrix.cell(c, p) == "pending" for c in CLAIMS for p in PHASES)


def test_phase_start_marks_a_claim_running() -> None:
    matrix = ClaimMatrix(CLAIMS)
    stream = stream_into(matrix)

    stream.emit(phase="portal", kind="phase_start", claim_id="CLM-0001")

    assert matrix.cell("CLM-0001", "portal") == "running"
    assert matrix.cell("CLM-0002", "portal") == "pending"


def test_phase_end_marks_a_claim_done() -> None:
    matrix = ClaimMatrix(CLAIMS)
    stream = stream_into(matrix)

    stream.emit(phase="portal", kind="phase_start", claim_id="CLM-0001")
    stream.emit(phase="portal", kind="phase_end", claim_id="CLM-0001", outcome="ok")

    assert matrix.cell("CLM-0001", "portal") == "done"


def test_a_guardrailed_determination_marks_later_phases_not_applicable() -> None:
    """The declined claim showing n/a is the discrimination story rendering itself."""
    matrix = ClaimMatrix(CLAIMS)
    stream = stream_into(matrix)

    stream.emit(
        phase="analysis",
        kind="determination",
        claim_id="CLM-0002",
        detail={"action": "decline", "guardrail": "MA130"},
    )

    assert matrix.cell("CLM-0002", "emr") == "na"
    assert matrix.cell("CLM-0002", "appeal") == "na"


def test_not_applicable_is_distinct_from_pending() -> None:
    matrix = ClaimMatrix(CLAIMS)
    stream = stream_into(matrix)

    stream.emit(
        phase="analysis", kind="determination", claim_id="CLM-0002", detail={"action": "decline"}
    )

    assert matrix.cell("CLM-0002", "emr") == "na"
    assert matrix.cell("CLM-0003", "emr") == "pending"


def test_an_appeal_determination_leaves_later_phases_open() -> None:
    matrix = ClaimMatrix(CLAIMS)
    stream = stream_into(matrix)

    stream.emit(
        phase="analysis", kind="determination", claim_id="CLM-0001", detail={"action": "appeal"}
    )

    assert matrix.cell("CLM-0001", "emr") == "pending"
    assert matrix.cell("CLM-0001", "appeal") == "pending"


def test_a_rebill_determination_skips_the_emr_and_appeal() -> None:
    matrix = ClaimMatrix(CLAIMS)
    stream = stream_into(matrix)

    stream.emit(
        phase="analysis", kind="determination", claim_id="CLM-0003", detail={"action": "rebill"}
    )

    assert matrix.cell("CLM-0003", "emr") == "na"
    assert matrix.cell("CLM-0003", "appeal") == "na"


def test_recovery_does_not_mark_a_cell_failed() -> None:
    """A handled recovery is not a failure, and the panel must not imply otherwise."""
    matrix = ClaimMatrix(CLAIMS)
    stream = stream_into(matrix)

    stream.emit(phase="portal", kind="phase_start", claim_id="CLM-0001")
    stream.emit(
        phase="portal", kind="recovery", claim_id="CLM-0001", detail={"reason": "session expired"}
    )

    assert matrix.cell("CLM-0001", "portal") == "running"


def test_an_error_marks_the_cell_failed() -> None:
    matrix = ClaimMatrix(CLAIMS)
    stream = stream_into(matrix)

    stream.emit(phase="portal", kind="phase_start", claim_id="CLM-0001")
    stream.emit(phase="portal", kind="error", claim_id="CLM-0001", outcome="failed")

    assert matrix.cell("CLM-0001", "portal") == "failed"


def test_events_without_a_claim_do_not_disturb_the_matrix() -> None:
    matrix = ClaimMatrix(CLAIMS)
    stream = stream_into(matrix)

    stream.emit(phase="report", kind="phase_start")

    assert all(matrix.cell(c, "report") == "pending" for c in CLAIMS)


def test_unknown_claims_are_ignored_rather_than_crashing() -> None:
    matrix = ClaimMatrix(CLAIMS)
    stream = stream_into(matrix)

    stream.emit(phase="portal", kind="phase_start", claim_id="CLM-9999")

    assert matrix.cell("CLM-0001", "portal") == "pending"
