"""A hardcoded event script, standing in for the real workflow.

This exists only so the skeleton has something to render and record. Every later
ticket replaces a slice of it with real work; when the last one lands this module
goes away.

It deliberately exercises the awkward cases rather than a clean path: a
guardrailed decline that never reaches the appeal, a rebill that skips the EMR,
and a session expiry the agent recovers from.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

from rcm_agent.events import EventStream

CLAIM_IDS = ("CLM-0001", "CLM-0002", "CLM-0003")

_DETERMINATIONS: dict[str, dict[str, str]] = {
    "CLM-0001": {"action": "appeal", "reason": "CO-197 prior authorization on file"},
    "CLM-0002": {"action": "decline", "guardrail": "MA130", "reason": "no appeal rights"},
    "CLM-0003": {"action": "rebill", "reason": "OA-22 coordination of benefits"},
}

SUMMARY = {"appealed": 1, "declined": 1, "rebilled": 1}


def _steps(stream: EventStream) -> Iterator[None]:
    for claim_id in CLAIM_IDS:
        stream.emit(phase="portal", kind="phase_start", claim_id=claim_id)
        stream.emit(phase="portal", kind="tool_call", tool="search_claims", claim_id=claim_id)
        yield

        if claim_id == "CLM-0001":
            # The mock portal expires the session on a specific navigation. The
            # agent notices and re-authenticates; this is handled, not a failure.
            stream.emit(
                phase="portal",
                kind="recovery",
                claim_id=claim_id,
                detail={"reason": "session expired"},
            )
            stream.emit(
                phase="portal",
                kind="tool_result",
                tool="log_in",
                claim_id=claim_id,
                outcome="recovered",
            )
            yield

        stream.emit(
            phase="portal",
            kind="tool_result",
            tool="download_eob",
            claim_id=claim_id,
            outcome="ok",
        )
        stream.emit(phase="portal", kind="phase_end", claim_id=claim_id, outcome="ok")
        yield

        stream.emit(phase="analysis", kind="phase_start", claim_id=claim_id)
        stream.emit(
            phase="analysis",
            kind="determination",
            claim_id=claim_id,
            detail=_DETERMINATIONS[claim_id],
        )
        stream.emit(phase="analysis", kind="phase_end", claim_id=claim_id, outcome="ok")
        yield

    appealed = "CLM-0001"
    stream.emit(phase="emr", kind="phase_start", claim_id=appealed)
    stream.emit(
        phase="emr", kind="tool_result", tool="read_auth_record", claim_id=appealed, outcome="ok"
    )
    stream.emit(phase="emr", kind="tool_result", tool="write_note", claim_id=appealed, outcome="ok")
    stream.emit(phase="emr", kind="phase_end", claim_id=appealed, outcome="ok")
    yield

    stream.emit(phase="appeal", kind="phase_start", claim_id=appealed)
    stream.emit(phase="appeal", kind="phase_end", claim_id=appealed, outcome="ok")
    yield

    for claim_id in CLAIM_IDS:
        stream.emit(phase="report", kind="phase_start", claim_id=claim_id)
        stream.emit(phase="report", kind="phase_end", claim_id=claim_id, outcome="ok")
    yield


def play(stream: EventStream, *, step_delay: float = 0.0) -> None:
    for _ in _steps(stream):
        if step_delay:
            time.sleep(step_delay)
