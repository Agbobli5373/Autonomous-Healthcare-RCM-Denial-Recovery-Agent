from __future__ import annotations

import json
from pathlib import Path

import pytest

from rcm_agent import cli, demo_script
from rcm_agent.events import EventStream


def only_run_directory(runs_dir: Path) -> Path:
    children = [p for p in runs_dir.iterdir() if p.is_dir()]
    assert len(children) == 1
    return children[0]


def read_run_json(runs_dir: Path) -> dict[str, object]:
    return json.loads((only_run_directory(runs_dir) / "run.json").read_text(encoding="utf-8"))


def test_a_completed_run_records_a_summary_derived_from_the_events(tmp_path: Path) -> None:
    runs = tmp_path / "runs"

    assert cli.run_command(runs, plain=True, step_delay=0.0) == 0

    state = read_run_json(runs)
    assert state["status"] == "completed"
    # Actions come from CONTEXT.md, not invented synonyms: appeal / close / rebill.
    assert state["summary"] == {"appeal": 1, "close": 1, "rebill": 1}


def test_an_unexpected_failure_records_status_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`failed` was unreachable outside tests until the CLI caught more than KeyboardInterrupt."""
    runs = tmp_path / "runs"

    def explode(stream: EventStream, *, step_delay: float = 0.0) -> None:
        stream.emit(phase="portal", kind="phase_start", claim_id="CLM-0001")
        raise RuntimeError("the sandbox died")

    monkeypatch.setattr(demo_script, "play", explode)

    with pytest.raises(RuntimeError, match="the sandbox died"):
        cli.run_command(runs, plain=True, step_delay=0.0)

    state = read_run_json(runs)
    assert state["status"] == "failed"
    assert state["failed_at"] == {"phase": "portal", "seq": 1}
    assert state["finished_at"] is not None


def test_a_failed_run_keeps_the_events_it_emitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = tmp_path / "runs"

    def explode(stream: EventStream, *, step_delay: float = 0.0) -> None:
        stream.emit(phase="portal", kind="phase_start", claim_id="CLM-0001")
        stream.emit(phase="portal", kind="tool_call", tool="log_in", claim_id="CLM-0001")
        raise RuntimeError("boom")

    monkeypatch.setattr(demo_script, "play", explode)

    with pytest.raises(RuntimeError):
        cli.run_command(runs, plain=True, step_delay=0.0)

    events = (only_run_directory(runs) / "events.ndjson").read_text(encoding="utf-8")
    assert len([line for line in events.splitlines() if line.strip()]) == 2


def test_no_staging_file_is_left_behind(tmp_path: Path) -> None:
    """run.json is written via a temp file and renamed; the temp must not survive."""
    runs = tmp_path / "runs"

    cli.run_command(runs, plain=True, step_delay=0.0)

    leftovers = list(only_run_directory(runs).glob(".*tmp*"))
    assert leftovers == []
