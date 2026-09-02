"""Reading a run back for the console.

The console never re-derives anything. The server replays what a run recorded
and attaches the cell state each event produced, so the rules that decide what a
cell shows stay in Python - in one place, under the type and test bar the rest of
the project has - and the browser renders what it is told.

That is the whole reason this seam exists, and every test here is about it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rcm_agent.console.replay import replay

DOS = "2026-03-14T00:00:00+00:00"


def write_run(root: Path, run_id: str, events: list[dict[str, Any]]) -> Path:
    """A run directory holding exactly these events, in this order."""
    run = root / run_id
    (run / "claims").mkdir(parents=True)
    lines = [
        json.dumps(
            {
                "seq": seq,
                "ts": DOS,
                "phase": event.get("phase", "analysis"),
                "kind": event["kind"],
                "tool": event.get("tool"),
                "claim_id": event.get("claim_id"),
                "outcome": event.get("outcome"),
                "screenshot": None,
                "detail": event.get("detail", {}),
            }
        )
        for seq, event in enumerate(events)
    ]
    (run / "events.ndjson").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return run


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


def test_every_recorded_event_comes_back_in_the_order_it_happened(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        [
            {"kind": "phase_start", "phase": "portal", "claim_id": "CLM-1"},
            {"kind": "phase_end", "phase": "portal", "claim_id": "CLM-1", "outcome": "ok"},
            determination("CLM-1", "appeal"),
        ],
    )

    streamed = list(replay(tmp_path))

    assert [event["seq"] for event in streamed] == [0, 1, 2]
    assert [event["kind"] for event in streamed] == ["phase_start", "phase_end", "determination"]


def test_each_event_carries_the_cell_state_it_produced(tmp_path: Path) -> None:
    """The client renders this rather than working it out.

    A browser deriving cell states would be a second implementation of rules
    that already exist in Python - including the one saying an Action needing no
    evidence closes the evidence phases - in a language nothing else here is
    written in.
    """
    write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        [
            {"kind": "phase_start", "phase": "portal", "claim_id": "CLM-1"},
            {"kind": "phase_end", "phase": "portal", "claim_id": "CLM-1", "outcome": "ok"},
        ],
    )

    streamed = list(replay(tmp_path))

    assert streamed[0]["derived"]["cells"]["portal"] == "running"
    assert streamed[1]["derived"]["cells"]["portal"] == "done"


def test_a_guardrailed_claim_reads_as_not_applicable_rather_than_pending(tmp_path: Path) -> None:
    """The discrimination story, arriving already decided.

    `pending` would say the agent still has work to do on a claim it closed by
    rule. The difference is the most important thing this demo communicates, and
    it is settled here rather than in the browser.
    """
    write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        [determination("CLM-2", "close", guardrail="unappealable-remark:MA130")],
    )

    cells = list(replay(tmp_path))[-1]["derived"]["cells"]

    assert cells["emr"] == "na"
    assert cells["appeal"] == "na"


def test_an_appeal_leaves_its_evidence_phases_open(tmp_path: Path) -> None:
    write_run(tmp_path, "2026-01-01T00-00-00Z", [determination("CLM-1", "appeal")])

    cells = list(replay(tmp_path))[-1]["derived"]["cells"]

    assert cells["emr"] == "pending"
    assert cells["appeal"] == "pending"


def test_the_queue_spans_runs_oldest_first(tmp_path: Path) -> None:
    """A run is plumbing. The queue is claims, and claims outlive the run that worked them."""
    write_run(tmp_path, "2026-01-01T00-00-00Z", [determination("CLM-1", "appeal")])
    write_run(tmp_path, "2026-01-02T00-00-00Z", [determination("CLM-9", "rebill")])

    streamed = list(replay(tmp_path))

    assert [event["run_id"] for event in streamed] == [
        "2026-01-01T00-00-00Z",
        "2026-01-02T00-00-00Z",
    ]
    assert [event["claim_id"] for event in streamed] == ["CLM-1", "CLM-9"]


def test_each_run_numbers_its_own_events(tmp_path: Path) -> None:
    """`seq` restarts per run, so a client keying on it alone would collide."""
    write_run(tmp_path, "2026-01-01T00-00-00Z", [determination("CLM-1", "appeal")])
    write_run(tmp_path, "2026-01-02T00-00-00Z", [determination("CLM-9", "rebill")])

    streamed = list(replay(tmp_path))

    assert [event["seq"] for event in streamed] == [0, 0]
    assert len({event["run_id"] for event in streamed}) == 2


def test_a_directory_that_is_not_a_run_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "not-a-run").mkdir()
    write_run(tmp_path, "2026-01-01T00-00-00Z", [determination("CLM-1", "appeal")])

    assert len(list(replay(tmp_path))) == 1


def test_a_missing_runs_directory_is_an_empty_queue_not_a_crash(tmp_path: Path) -> None:
    assert list(replay(tmp_path / "nothing-here")) == []


def test_the_three_claims_reach_three_different_actions(tmp_path: Path) -> None:
    """The demo's whole point, read off the stream the console consumes.

    An agent that answered `appeal` everywhere would get one of these right.
    """
    write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        [
            determination("CLM-2026-0001", "appeal"),
            determination("CLM-2026-0002", "close", guardrail="unappealable-remark:MA130"),
            determination("CLM-2026-0003", "rebill"),
        ],
    )

    actions = {
        event["claim_id"]: event["derived"]["action"]
        for event in replay(tmp_path)
        if event["kind"] == "determination"
    }

    assert actions == {
        "CLM-2026-0001": "appeal",
        "CLM-2026-0002": "close",
        "CLM-2026-0003": "rebill",
    }


# --- over the socket --------------------------------------------------------


def test_the_socket_replays_the_whole_queue_then_says_so(tmp_path: Path) -> None:
    """A client has to tell "nothing more yet" from "the server went away".

    Without the marker an empty queue and a dropped connection look identical,
    and the console would have no honest way to say which it is.
    """
    from fastapi.testclient import TestClient

    from rcm_agent.console.server import create_app

    write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        [
            determination("CLM-2026-0001", "appeal"),
            determination("CLM-2026-0002", "close", guardrail="unappealable-remark:MA130"),
        ],
    )

    with TestClient(create_app(tmp_path)).websocket_connect("/events") as socket:
        first = socket.receive_json()
        second = socket.receive_json()
        marker = socket.receive_json()

    assert first["type"] == "event"
    assert first["claim_id"] == "CLM-2026-0001"
    assert first["derived"]["action"] == "appeal"
    assert second["derived"]["cells"]["appeal"] == "na", "the rule-closed claim arrives decided"
    assert marker == {"type": "replayed"}


def test_the_socket_is_reachable_alongside_the_page(tmp_path: Path) -> None:
    """The static mount sits at the root and would swallow this if ordered wrong."""
    from fastapi.testclient import TestClient

    from rcm_agent.console.server import create_app

    client = TestClient(create_app(tmp_path))

    assert client.get("/").status_code == 200
    with client.websocket_connect("/events") as socket:
        assert socket.receive_json() == {"type": "replayed"}
