"""Building run directories for tests that read them back.

Shared because the live tail and the replay it grew out of are the same code
path with a different clock, so they want the same fixtures. A second copy would
drift, and the two suites would stop agreeing about what a run looks like on
disk - which is the one thing they both depend on.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DOS = "2026-03-14T00:00:00+00:00"


def event_line(seq: int, event: dict[str, Any]) -> str:
    """One recorded event, in the shape `events.ndjson` holds."""
    return json.dumps(
        {
            "seq": seq,
            "ts": DOS,
            "phase": event.get("phase", "analysis"),
            "kind": event["kind"],
            "tool": event.get("tool"),
            "claim_id": event.get("claim_id"),
            "outcome": event.get("outcome"),
            "screenshot": event.get("screenshot"),
            "detail": event.get("detail", {}),
        }
    )


def write_run(root: Path, run_id: str, events: list[dict[str, Any]]) -> Path:
    """A run directory holding exactly these events, in this order."""
    run = root / run_id
    (run / "claims").mkdir(parents=True)
    lines = [event_line(seq, event) for seq, event in enumerate(events)]
    (run / "events.ndjson").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return run


def append_events(run: Path, events: list[dict[str, Any]]) -> None:
    """More events on the end of a run already on disk, as a live run does.

    Appended and flushed the way `RunDirectory` writes, because the thing under
    test is a reader that has to cope with a file growing under it.
    """
    log = run / "events.ndjson"
    existing = sum(1 for line in log.read_text(encoding="utf-8").splitlines() if line)
    with log.open("a", encoding="utf-8", newline="") as handle:
        for offset, event in enumerate(events):
            handle.write(event_line(existing + offset, event) + "\n")
            handle.flush()


def determination(claim_id: str, action: str, guardrail: str | None = None) -> dict[str, Any]:
    priority = (
        None
        if guardrail
        else {"amount_at_stake": "1250.00", "likelihood": 0.45, "expected_recovery": "562.50"}
    )
    return {
        "kind": "determination",
        "claim_id": claim_id,
        "outcome": "ok",
        "detail": {
            "claim_id": claim_id,
            "action": action,
            "rationale": "because the remittance said so",
            "evidence_required": [],
            "guardrail": guardrail,
            "priority": priority,
        },
    }
