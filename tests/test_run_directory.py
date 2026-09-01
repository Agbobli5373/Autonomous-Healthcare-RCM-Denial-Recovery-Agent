from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from rcm_agent.events import EventStream
from rcm_agent.run_directory import RunDirectory

STARTED = datetime(2026, 9, 1, 14, 22, 3, tzinfo=UTC)
FINISHED = datetime(2026, 9, 1, 14, 24, 9, tzinfo=UTC)


def make(tmp_path: Path) -> RunDirectory:
    return RunDirectory.create(tmp_path / "runs", started_at=STARTED)


def read_run_json(run: RunDirectory) -> dict[str, object]:
    return json.loads(run.run_json_path.read_text(encoding="utf-8"))


def read_events(run: RunDirectory) -> list[dict[str, object]]:
    text = run.events_path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_directory_name_is_filesystem_safe(tmp_path: Path) -> None:
    run = make(tmp_path)

    # Colons are illegal in Windows paths, so the ISO time is dash-separated.
    assert run.path.name == "2026-09-01T14-22-03Z"
    assert ":" not in run.path.name


def test_creates_the_expected_layout(tmp_path: Path) -> None:
    run = make(tmp_path)

    assert run.path.is_dir()
    assert (run.path / "claims").is_dir()
    assert (run.path / "screenshots").is_dir()
    assert (run.path / "documents").is_dir()
    assert run.run_json_path.is_file()
    assert run.events_path.is_file()


def test_status_is_running_from_the_moment_it_exists(tmp_path: Path) -> None:
    run = make(tmp_path)

    state = read_run_json(run)

    assert state["status"] == "running"
    assert state["finished_at"] is None
    assert state["failed_at"] is None


def test_events_are_appended_as_ndjson(tmp_path: Path) -> None:
    run = make(tmp_path)
    stream = EventStream(clock=lambda: STARTED)
    stream.add_sink(run)

    stream.emit(phase="portal", kind="phase_start")
    stream.emit(phase="portal", kind="tool_call", tool="log_in")

    events = read_events(run)
    assert [e["seq"] for e in events] == [1, 2]
    assert events[1]["tool"] == "log_in"


def test_events_are_readable_before_the_run_ends(tmp_path: Path) -> None:
    """A killed run must leave every event it emitted, so writes cannot sit in a buffer."""
    run = make(tmp_path)
    stream = EventStream(clock=lambda: STARTED)
    stream.add_sink(run)

    stream.emit(phase="portal", kind="phase_start")

    # No close(), no flush() call from the test — simulating a hard kill.
    assert len(read_events(run)) == 1
    assert read_run_json(run)["status"] == "running"


def test_completing_records_status_and_finish_time(tmp_path: Path) -> None:
    run = make(tmp_path)

    run.complete(finished_at=FINISHED, summary={"appealed": 1, "declined": 1, "rebilled": 1})

    state = read_run_json(run)
    assert state["status"] == "completed"
    assert state["finished_at"] == "2026-09-01T14:24:09+00:00"
    assert state["summary"] == {"appealed": 1, "declined": 1, "rebilled": 1}
    assert state["failed_at"] is None


def test_failing_records_where_it_stopped(tmp_path: Path) -> None:
    run = make(tmp_path)
    stream = EventStream(clock=lambda: STARTED)
    stream.add_sink(run)
    stream.emit(phase="analysis", kind="phase_start")

    run.fail(phase="analysis", seq=1, finished_at=FINISHED)

    state = read_run_json(run)
    assert state["status"] == "failed"
    assert state["failed_at"] == {"phase": "analysis", "seq": 1}
    assert state["finished_at"] == "2026-09-01T14:24:09+00:00"


def test_run_json_is_rewritten_at_each_phase_transition(tmp_path: Path) -> None:
    run = make(tmp_path)
    stream = EventStream(clock=lambda: STARTED)
    stream.add_sink(run)

    stream.emit(phase="portal", kind="phase_start")
    assert read_run_json(run)["current_phase"] == "portal"

    stream.emit(phase="analysis", kind="phase_start")
    assert read_run_json(run)["current_phase"] == "analysis"


def test_concurrent_runs_get_distinct_directories(tmp_path: Path) -> None:
    first = RunDirectory.create(tmp_path / "runs", started_at=STARTED)
    second = RunDirectory.create(tmp_path / "runs", started_at=STARTED)

    assert first.path != second.path
