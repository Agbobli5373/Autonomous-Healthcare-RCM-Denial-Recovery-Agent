"""Following a run while it is still being written.

Replay and live are one code path with a different clock: a client receives
every event from the beginning and then keeps receiving them, and opening a
finished run is the same operation as opening one in flight. So this is not a
second reader - it is the same reader, asked again.

The two things that make it more than a loop are both here. A log is appended to
while it is being read, so a read can land mid-line and must not turn half an
event into a parse failure. And a dropped socket has to resume from what the
client already saw, which means the server rebuilds state from `seq` 0 while
sending only what comes after the cursor - state and delivery are different
questions, and conflating them either duplicates events or loses them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.runs import append_events, determination, event_line, write_run

from rcm_agent.console.replay import RunStream


def seqs(events: list[dict[str, Any]]) -> list[tuple[str, Any]]:
    return [(str(event["run_id"]), event["seq"]) for event in events]


# --- the same reader, asked again -------------------------------------------


def test_the_first_ask_yields_everything_already_recorded(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        [
            {"kind": "phase_start", "phase": "analysis", "claim_id": "CLM-1"},
            determination("CLM-1", "appeal"),
        ],
    )
    stream = RunStream(tmp_path)

    assert seqs(list(stream.catch_up())) == [
        ("2026-01-01T00-00-00Z", 0),
        ("2026-01-01T00-00-00Z", 1),
    ]


def test_asking_again_with_nothing_new_yields_nothing(tmp_path: Path) -> None:
    """The poll that finds no change is the common case, and must be silent.

    A reader that re-sent the log every time it was asked would flood a socket
    with events the client already has and make every claim's state churn.
    """
    write_run(tmp_path, "2026-01-01T00-00-00Z", [determination("CLM-1", "appeal")])
    stream = RunStream(tmp_path)
    list(stream.catch_up())

    assert list(stream.catch_up()) == []


def test_events_appended_after_the_first_ask_come_back_on_the_next(tmp_path: Path) -> None:
    run = write_run(
        tmp_path, "2026-01-01T00-00-00Z", [{"kind": "phase_start", "claim_id": "CLM-1"}]
    )
    stream = RunStream(tmp_path)
    list(stream.catch_up())

    append_events(run, [determination("CLM-1", "appeal")])

    fresh = list(stream.catch_up())
    assert seqs(fresh) == [("2026-01-01T00-00-00Z", 1)]
    assert fresh[0]["kind"] == "determination"


def test_a_run_that_did_not_exist_yet_is_picked_up(tmp_path: Path) -> None:
    """A run started while the console is open. Nothing tells it; it looks.

    The agent never learns a console exists - no sink is registered and no URL is
    passed - so a run started from a terminal has to become visible by being
    found on disk.
    """
    stream = RunStream(tmp_path)
    assert list(stream.catch_up()) == []

    write_run(tmp_path, "2026-02-02T00-00-00Z", [determination("CLM-9", "rebill")])

    assert seqs(list(stream.catch_up())) == [("2026-02-02T00-00-00Z", 0)]


def test_a_later_run_does_not_stop_an_earlier_one_being_followed(tmp_path: Path) -> None:
    """Live is a property of a run, not a mode of the console.

    Both are read every time. A console that latched onto "the newest run" would
    stop following one that was still working when a second started.
    """
    first = write_run(tmp_path, "2026-01-01T00-00-00Z", [{"kind": "phase_start", "claim_id": "A"}])
    stream = RunStream(tmp_path)
    list(stream.catch_up())

    write_run(tmp_path, "2026-02-02T00-00-00Z", [{"kind": "phase_start", "claim_id": "B"}])
    append_events(first, [determination("A", "appeal")])

    assert seqs(list(stream.catch_up())) == [
        ("2026-01-01T00-00-00Z", 1),
        ("2026-02-02T00-00-00Z", 0),
    ]


# --- a file being written while it is read ----------------------------------


def test_half_a_line_is_not_half_an_event(tmp_path: Path) -> None:
    """A read can land between an event and its newline.

    `events.ndjson` is appended and flushed per event, so a reader polling it
    will sooner or later see a partial line. Parsing it yields a broken event or
    drops a real one; the fragment has to wait for the rest of itself.
    """
    run = write_run(
        tmp_path, "2026-01-01T00-00-00Z", [{"kind": "phase_start", "claim_id": "CLM-1"}]
    )
    stream = RunStream(tmp_path)
    list(stream.catch_up())

    log = run / "events.ndjson"
    whole = (
        '{"seq": 1, "ts": "2026-03-14T00:00:00+00:00", "phase": "analysis", '
        '"kind": "phase_end", "tool": null, "claim_id": "CLM-1", "outcome": "ok", '
        '"screenshot": null, "detail": {}}'
    )
    with log.open("a", encoding="utf-8", newline="") as handle:
        handle.write(whole[:40])
        handle.flush()

    assert list(stream.catch_up()) == []

    with log.open("a", encoding="utf-8", newline="") as handle:
        handle.write(whole[40:] + "\n")
        handle.flush()

    assert seqs(list(stream.catch_up())) == [("2026-01-01T00-00-00Z", 1)]


def test_a_run_directory_with_no_log_yet_is_not_an_error(tmp_path: Path) -> None:
    """`RunDirectory.create` makes the directory before anything is written."""
    (tmp_path / "2026-01-01T00-00-00Z" / "claims").mkdir(parents=True)
    stream = RunStream(tmp_path)

    assert list(stream.catch_up()) == []


def test_a_runs_directory_that_does_not_exist_yet_is_an_empty_queue(tmp_path: Path) -> None:
    """The console is often opened before anything has been run."""
    stream = RunStream(tmp_path / "nothing-here")

    assert list(stream.catch_up()) == []


# --- state is built from the whole run, delivery starts at the cursor -------


def test_a_claim_first_seen_mid_run_still_gets_its_cells(tmp_path: Path) -> None:
    """The matrix cannot be handed the claim ids in advance any more.

    Following a run in flight, the first anyone hears of a claim is an event
    about it - so a claim that appears after the stream started has to be
    admitted rather than ignored, or its row arrives with no phases at all.
    """
    run = write_run(
        tmp_path, "2026-01-01T00-00-00Z", [{"kind": "phase_start", "claim_id": "CLM-1"}]
    )
    stream = RunStream(tmp_path)
    list(stream.catch_up())

    append_events(run, [{"kind": "phase_start", "phase": "analysis", "claim_id": "CLM-2"}])

    arrived = next(iter(stream.catch_up()))
    assert arrived["claim_id"] == "CLM-2"
    assert arrived["derived"]["cells"]["analysis"] == "running"


def test_resuming_sends_nothing_the_client_already_had(tmp_path: Path) -> None:
    """No duplicates, and no silent gap.

    A reconnecting client names the last event it saw. Everything before it is
    still read - the state a later event describes depends on it - but only what
    comes after is sent.
    """
    write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        [
            {"kind": "phase_start", "phase": "analysis", "claim_id": "CLM-1"},
            {"kind": "phase_end", "phase": "analysis", "claim_id": "CLM-1", "outcome": "ok"},
            determination("CLM-1", "appeal"),
        ],
    )

    resumed = list(RunStream(tmp_path, after={"2026-01-01T00-00-00Z": 0}).catch_up())

    assert seqs(resumed) == [("2026-01-01T00-00-00Z", 1), ("2026-01-01T00-00-00Z", 2)]


def test_what_a_resumed_client_receives_describes_the_whole_run(tmp_path: Path) -> None:
    """Not just the part it was sent.

    Cell state is cumulative, so an event replayed against a matrix that started
    at the cursor would describe a run that had only just begun - the resumed
    client would watch its own queue go backwards.
    """
    write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        [
            {"kind": "phase_start", "phase": "portal", "claim_id": "CLM-1"},
            {"kind": "phase_end", "phase": "portal", "claim_id": "CLM-1", "outcome": "ok"},
            {"kind": "phase_start", "phase": "analysis", "claim_id": "CLM-1"},
        ],
    )

    resumed = list(RunStream(tmp_path, after={"2026-01-01T00-00-00Z": 1}).catch_up())

    assert resumed[0]["derived"]["cells"]["portal"] == "done"


def test_a_cursor_naming_one_run_does_not_hold_back_another(tmp_path: Path) -> None:
    """A run the client has never heard of is sent in full."""
    write_run(tmp_path, "2026-01-01T00-00-00Z", [determination("CLM-1", "appeal")])
    write_run(tmp_path, "2026-02-02T00-00-00Z", [determination("CLM-2", "rebill")])

    resumed = list(RunStream(tmp_path, after={"2026-01-01T00-00-00Z": 0}).catch_up())

    assert seqs(resumed) == [("2026-02-02T00-00-00Z", 0)]


def test_a_run_still_being_written_is_not_silenced_by_a_newer_one(tmp_path: Path) -> None:
    """The gap a single cursor could not express, and the reason there is a map.

    Two runs in flight. The client has seen both, so the last event it received
    came from the newer one - that is the order the server sends them in. A
    cursor that was one `(run, seq)` pair then answered "is this event above the
    newest thing I sent?", and everything the *older* run went on to record
    sorted below it and was dropped. Not late: never. The cursor never advanced
    past it either, so the events were gone for the life of the connection.

    A verdict on a claim, silently missing from a console reporting itself up to
    date. Found by probing the resume path rather than by any test here, which is
    why this one exists.
    """
    first = write_run(tmp_path, "2026-01-01T00-00-00Z", [{"kind": "phase_start", "claim_id": "A"}])
    write_run(tmp_path, "2026-02-02T00-00-00Z", [{"kind": "phase_start", "claim_id": "B"}])
    seen = {"2026-01-01T00-00-00Z": 0, "2026-02-02T00-00-00Z": 0}

    append_events(first, [determination("A", "appeal")])

    resumed = list(RunStream(tmp_path, after=seen).catch_up())

    assert seqs(resumed) == [("2026-01-01T00-00-00Z", 1)]


def test_a_cursor_naming_runs_that_are_gone_replays_what_is_left(tmp_path: Path) -> None:
    """A client resuming against a runs directory that has been cleared.

    Sending nothing would leave it holding a queue for runs that no longer exist,
    with no way to find out. Everything it can still be told, it is told.
    """
    write_run(tmp_path, "2026-05-05T00-00-00Z", [determination("CLM-1", "appeal")])

    resumed = list(RunStream(tmp_path, after={"1999-01-01T00-00-00Z": 4}).catch_up())

    assert seqs(resumed) == [("2026-05-05T00-00-00Z", 0)]


# --- over the socket --------------------------------------------------------


def console(tmp_path: Path):
    from fastapi.testclient import TestClient

    from rcm_agent.console.server import create_app

    return TestClient(create_app(tmp_path))


def test_the_socket_keeps_delivering_after_it_has_caught_up(tmp_path: Path) -> None:
    """The acceptance criterion, end to end: nobody reloads anything.

    `replayed` is not the end of the stream. It means the client is level with
    what is on disk, and the socket goes on carrying whatever lands next.
    """
    run = write_run(
        tmp_path, "2026-01-01T00-00-00Z", [{"kind": "phase_start", "claim_id": "CLM-1"}]
    )

    with console(tmp_path).websocket_connect("/events") as socket:
        assert socket.receive_json()["type"] == "hello"
        assert socket.receive_json()["type"] == "event"
        assert socket.receive_json() == {"type": "replayed"}

        append_events(run, [determination("CLM-1", "appeal")])

        arrived = socket.receive_json()

    assert arrived["kind"] == "determination"
    assert arrived["derived"]["action"] == "appeal"


def test_a_run_that_starts_while_the_console_is_open_appears_in_it(tmp_path: Path) -> None:
    """Nothing tells the console. The agent does not know it exists."""
    tmp_path.mkdir(exist_ok=True)

    with console(tmp_path).websocket_connect("/events") as socket:
        assert socket.receive_json()["type"] == "hello"
        assert socket.receive_json() == {"type": "replayed"}

        write_run(tmp_path, "2026-03-03T00-00-00Z", [determination("CLM-7", "rebill")])

        arrived = socket.receive_json()

    assert arrived["claim_id"] == "CLM-7"
    assert arrived["run_id"] == "2026-03-03T00-00-00Z"


def test_reconnecting_resumes_from_the_last_event_the_client_saw(tmp_path: Path) -> None:
    """No duplicates, no gap - the half of the transport #56 knowingly bought."""
    write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        [
            {"kind": "phase_start", "phase": "analysis", "claim_id": "CLM-1"},
            {"kind": "phase_end", "phase": "analysis", "claim_id": "CLM-1", "outcome": "ok"},
            determination("CLM-1", "appeal"),
        ],
    )
    client = console(tmp_path)

    with client.websocket_connect("/events?after=2026-01-01T00-00-00Z:0") as socket:
        assert socket.receive_json()["type"] == "hello"
        first = socket.receive_json()
        second = socket.receive_json()
        assert socket.receive_json() == {"type": "replayed"}

    assert [first["seq"], second["seq"]] == [1, 2]
    assert first["derived"]["cells"]["analysis"] == "done", (
        "the resumed client is told the state of the whole run, not of its own fragment"
    )


def test_a_client_that_names_no_cursor_still_gets_everything(tmp_path: Path) -> None:
    write_run(tmp_path, "2026-01-01T00-00-00Z", [determination("CLM-1", "appeal")])

    with console(tmp_path).websocket_connect("/events") as socket:
        assert socket.receive_json()["type"] == "hello"
        assert socket.receive_json()["seq"] == 0


def test_the_query_a_reconnecting_console_actually_sends(tmp_path: Path) -> None:
    """The literal the browser puts on the wire, parsed by the thing that reads it.

    Pinned to the same string as `live.test.ts`'s "names its place in each run,
    in the shape the server parses". Nothing else in either suite crosses this
    boundary, and when the two halves disagreed - the client sending
    `after_run=&after_seq=`, the server reading `after=<run>:<seq>` - FastAPI
    ignored the unknown parameters, the server replayed from the beginning, both
    suites stayed green, and every reconnect silently duplicated the history.
    """
    write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        [
            # Thirteen, so the Determination lands at seq 13 - one past the
            # cursor, and therefore the only thing that should arrive.
            *[{"kind": "phase_start", "phase": "analysis", "claim_id": "CLM-1"}] * 13,
            determination("CLM-1", "appeal"),
        ],
    )

    with console(tmp_path).websocket_connect("/events?after=2026-01-01T00-00-00Z%3A12") as socket:
        assert socket.receive_json()["type"] == "hello"
        first = socket.receive_json()
        assert socket.receive_json() == {"type": "replayed"}

    assert first["seq"] == 13, "everything at or before the cursor was already delivered"
    assert first["kind"] == "determination"


def test_an_event_with_no_usable_sequence_number_is_skipped(tmp_path: Path) -> None:
    """`seq` is the join key, and a cursor cannot be compared against a string.

    Letting one through meant it sorted against nothing, so it was re-sent on
    every resume for as long as the run existed.
    """
    run = write_run(
        tmp_path, "2026-01-01T00-00-00Z", [{"kind": "phase_start", "claim_id": "CLM-1"}]
    )
    log = run / "events.ndjson"
    with log.open("a", encoding="utf-8", newline="") as handle:
        handle.write(
            '{"seq": "second", "ts": "2026-03-14T00:00:00+00:00", "phase": "analysis", '
            '"kind": "phase_end", "tool": null, "claim_id": "CLM-1", "outcome": "ok", '
            '"screenshot": null, "detail": {}}' + chr(10)
        )

    assert seqs(list(RunStream(tmp_path).catch_up())) == [("2026-01-01T00-00-00Z", 0)]


def test_a_runs_directory_rebuilt_under_the_same_name_starts_over(tmp_path: Path) -> None:
    """The place a client had reached goes with the file it was reached in.

    Kept, the cursor names a `seq` in a run that no longer exists, and the new
    run's opening events fall below it and are never sent.
    """
    run = write_run(
        tmp_path,
        "2026-01-01T00-00-00Z",
        [
            {"kind": "phase_start", "phase": "analysis", "claim_id": "CLM-1"},
            determination("CLM-1", "appeal"),
        ],
    )
    stream = RunStream(tmp_path)
    assert len(list(stream.catch_up())) == 2

    (run / "events.ndjson").write_text(
        event_line(0, {"kind": "phase_start", "phase": "analysis", "claim_id": "CLM-9"}) + chr(10),
        encoding="utf-8",
        newline="",
    )

    assert seqs(list(stream.catch_up())) == [("2026-01-01T00-00-00Z", 0)]
