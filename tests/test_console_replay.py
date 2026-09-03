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
from rcm_agent.matrix import PHASES

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
        hello = socket.receive_json()
        first = socket.receive_json()
        second = socket.receive_json()
        marker = socket.receive_json()

    assert hello == {"type": "hello", "phases": list(PHASES)}, (
        "the phase names come from the server, so they live in one place"
    )
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
        assert socket.receive_json()["type"] == "hello"
        assert socket.receive_json() == {"type": "replayed"}


def test_whether_a_rule_closed_the_claim_is_decided_here(tmp_path: Path) -> None:
    """The browser is told, not left to work it out.

    Which section a claim belongs in is the judgement this project turns on, and
    the domain already answers it. A client testing the rule label for emptiness
    would be a second, untyped copy of `Determination.was_guardrailed`.
    """
    write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        [
            determination("CLM-1", "appeal"),
            determination("CLM-2", "close", guardrail="unappealable-remark:MA130"),
        ],
    )

    by_claim = {
        event["claim_id"]: event["derived"]
        for event in replay(tmp_path)
        if event["kind"] == "determination"
    }

    assert by_claim["CLM-1"]["guardrailed"] is False
    assert by_claim["CLM-1"]["determination"]["guardrail"] is None
    assert by_claim["CLM-2"]["guardrailed"] is True
    assert by_claim["CLM-2"]["determination"]["guardrail"] == "unappealable-remark:MA130"


def test_the_priority_travels_with_the_determination(tmp_path: Path) -> None:
    write_run(tmp_path, "2026-01-01T00-00-00Z", [determination("CLM-1", "appeal")])

    derived = list(replay(tmp_path))[-1]["derived"]

    assert derived["determination"]["priority"]["expected_recovery"] == "562.50"


def test_a_guardrailed_claim_carries_no_priority(tmp_path: Path) -> None:
    """`None`, not zero. Nothing was weighed, so there is no score missing."""
    write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        [determination("CLM-2", "close", guardrail="unappealable-remark:MA130")],
    )

    assert list(replay(tmp_path))[-1]["derived"]["determination"]["priority"] is None


def test_a_line_this_build_cannot_read_costs_one_row_not_the_stream(tmp_path: Path) -> None:
    """A run directory outlives the code that wrote it.

    An older run can carry a field this build has never heard of. Losing that row
    is a real cost; taking down the socket mid-replay, so the console reports
    itself disconnected, is a worse answer to an event it does not understand.
    """
    run = write_run(tmp_path, "2026-01-01T00-00-00Z", [determination("CLM-1", "appeal")])
    log = run / "events.ndjson"
    log.write_text(
        log.read_text(encoding="utf-8")
        + json.dumps(
            {
                "seq": 9,
                "ts": DOS,
                "phase": "analysis",
                "kind": "determination",
                "claim_id": "CLM-9",
                "detail": {},
                "invented_later": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    streamed = list(replay(tmp_path))

    assert [event["claim_id"] for event in streamed] == ["CLM-1"]


def test_every_event_after_a_determination_still_describes_it(tmp_path: Path) -> None:
    """The contract that lets the client take the latest event wholesale.

    If a later event carried less than an earlier one, a client would have to
    merge them field by field - and merging is what mixed two runs together,
    rendering one run's Determination against another run's phases.
    """
    write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        [
            determination("CLM-1", "appeal"),
            {"kind": "phase_end", "phase": "analysis", "claim_id": "CLM-1", "outcome": "ok"},
        ],
    )

    last = list(replay(tmp_path))[-1]["derived"]

    assert last["action"] == "appeal"
    assert last["determination"]["priority"]["expected_recovery"] == "562.50"
    assert last["guardrailed"] is False


def test_a_rule_closed_claim_carries_its_rule_on_every_later_event(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        [
            determination("CLM-2", "close", guardrail="unappealable-remark:MA130"),
            {"kind": "phase_end", "phase": "analysis", "claim_id": "CLM-2", "outcome": "ok"},
        ],
    )

    last = list(replay(tmp_path))[-1]["derived"]

    assert last["guardrailed"] is True
    assert last["determination"]["guardrail"] == "unappealable-remark:MA130"
    assert last["determination"]["priority"] is None


def claim_record(claim_id: str) -> dict[str, Any]:
    """What the payer refused, as a run now records it."""
    return {
        "kind": "claim",
        "claim_id": claim_id,
        "detail": {
            "claim_id": claim_id,
            "payer": "Cascade Health Plan",
            "patient_id": "PAT-40219",
            "date_of_service": "2026-03-14",
            "service_lines": [
                {
                    "line_number": 2,
                    "procedure_code": "E0601",
                    "charge": "1250.00",
                    "adjustments": [
                        {
                            "group": "CO",
                            "reason_code": "197",
                            "amount": "1250.00",
                            "remark_codes": ["N706"],
                        }
                    ],
                }
            ],
        },
    }


def test_the_refusal_travels_beside_the_determination(tmp_path: Path) -> None:
    """Approving is a comparison, so both halves have to reach the browser.

    A run kept the Determination and not the Claim it answered, so nothing
    downstream could show what the payer actually said - only the conclusion
    drawn from it.
    """
    write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        [claim_record("CLM-1"), determination("CLM-1", "appeal")],
    )

    derived = list(replay(tmp_path))[-1]["derived"]

    assert derived["claim"]["payer"] == "Cascade Health Plan"
    assert derived["claim"]["service_lines"][0]["adjustments"][0]["remark_codes"] == ["N706"]


def test_a_rule_closed_claim_still_shows_what_the_payer_said(tmp_path: Path) -> None:
    """The guardrailed claim has no model call, so it cannot come from the facts.

    Its refusal has to be recorded in its own right, or the one claim whose story
    matters most would have an empty half.
    """
    write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        [
            claim_record("CLM-2"),
            determination("CLM-2", "close", guardrail="unappealable-remark:MA130"),
        ],
    )

    derived = list(replay(tmp_path))[-1]["derived"]

    assert derived["claim"] is not None
    assert derived["guardrailed"] is True


def test_the_refusal_rides_on_every_later_event_too(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        [
            claim_record("CLM-1"),
            determination("CLM-1", "appeal"),
            {"kind": "phase_end", "phase": "analysis", "claim_id": "CLM-1", "outcome": "ok"},
        ],
    )

    assert list(replay(tmp_path))[-1]["derived"]["claim"] is not None


def test_the_governing_denial_is_named_by_the_server(tmp_path: Path) -> None:
    """A contractual write-off is not the denial being answered.

    `governing_denial` takes the largest *denial*, and an adjustment that does
    not refuse payment is not one. A browser taking "the biggest number on the
    claim" would show `CO-45` - a write-off - as the code being answered, and on
    the rule-closed claim that hides the `MA130` the guardrail fired on.
    """
    record = claim_record("CLM-2")
    record["detail"]["service_lines"] = [
        {
            "line_number": 1,
            "procedure_code": "A4253",
            "charge": "78.00",
            "adjustments": [
                {
                    "group": "CO",
                    "reason_code": "16",
                    "amount": "78.00",
                    "remark_codes": ["MA130"],
                }
            ],
        },
        {
            "line_number": 2,
            "procedure_code": "E1390",
            "charge": "450.00",
            # Larger than the denial, and not a denial: a contractual write-off.
            "adjustments": [
                {"group": "CO", "reason_code": "45", "amount": "92.50", "remark_codes": []}
            ],
        },
    ]
    write_run(tmp_path, "2026-01-01T00-00-00Z", [record, determination("CLM-2", "close")])

    governing = list(replay(tmp_path))[-1]["derived"]["claim"]["governing"]

    assert governing["reason_code"] == "16", "the write-off is bigger and is not a denial"
    assert governing["remark_codes"] == ["MA130"]


def test_a_charge_the_remittance_never_stated_is_sent_as_nothing(tmp_path: Path) -> None:
    """Told apart from a charge that is genuinely zero, and not left to a browser.

    A Claim read off an EOB carries no charge - the document says what was
    adjusted, not what was billed - so sending the placeholder zero on would put
    a number on screen the payer never sent.
    """
    record = claim_record("CLM-1")
    record["detail"]["service_lines"][0]["charge"] = "0"
    write_run(tmp_path, "2026-01-01T00-00-00Z", [record, determination("CLM-1", "appeal")])

    lines = list(replay(tmp_path))[-1]["derived"]["claim"]["service_lines"]

    assert lines[0]["charge"] is None


def test_a_charge_that_is_known_still_travels(tmp_path: Path) -> None:
    record = claim_record("CLM-1")
    record["detail"]["service_lines"][0]["charge"] = "1250.00"
    write_run(tmp_path, "2026-01-01T00-00-00Z", [record, determination("CLM-1", "appeal")])

    lines = list(replay(tmp_path))[-1]["derived"]["claim"]["service_lines"]

    assert lines[0]["charge"] == "1250.00"


def test_a_claim_of_only_write_offs_has_no_governing_denial(tmp_path: Path) -> None:
    """An ordinary claim, not an error.

    `governing_denial` takes the largest of `claim.denials`, and a claim whose
    every adjustment is a contractual write-off has none - `max` of nothing
    raises. Guarded rather than caught, so a real parse failure still surfaces.
    """
    record = claim_record("CLM-3")
    record["detail"]["service_lines"] = [
        {
            "line_number": 1,
            "procedure_code": "E1390",
            "charge": "450.00",
            "adjustments": [
                {"group": "CO", "reason_code": "45", "amount": "92.50", "remark_codes": []}
            ],
        }
    ]
    write_run(tmp_path, "2026-01-01T00-00-00Z", [record, determination("CLM-3", "close")])

    claim = list(replay(tmp_path))[-1]["derived"]["claim"]

    assert claim["governing"] is None
    assert claim["service_lines"], "the lines still travel; only the denial is absent"
