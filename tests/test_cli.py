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


CLAIM: dict[str, object] = {
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


def write_claim(tmp_path: Path, claim: dict[str, object]) -> Path:
    path = tmp_path / "claim.json"
    path.write_text(json.dumps(claim), encoding="utf-8")
    return path


def read_events(runs_dir: Path) -> list[dict[str, object]]:
    text = (only_run_directory(runs_dir) / "events.ndjson").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_determine_emits_a_determination_event(tmp_path: Path) -> None:
    runs = tmp_path / "runs"

    assert cli.determine_command(write_claim(tmp_path, CLAIM), runs) == 0

    determinations = [e for e in read_events(runs) if e["kind"] == "determination"]
    assert len(determinations) == 1
    detail = determinations[0]["detail"]
    assert isinstance(detail, dict)
    assert detail["action"] == "appeal"
    assert determinations[0]["claim_id"] == "CLM-0001"


def test_determine_records_a_guardrail_in_the_event(tmp_path: Path) -> None:
    claim = json.loads(json.dumps(CLAIM))
    claim["service_lines"][0]["adjustments"][0]["remark_codes"] = ["MA130"]
    runs = tmp_path / "runs"

    cli.determine_command(write_claim(tmp_path, claim), runs)

    determination = next(e for e in read_events(runs) if e["kind"] == "determination")
    detail = determination["detail"]
    assert isinstance(detail, dict)
    assert detail["action"] == "close"
    assert detail["guardrail"] == "unappealable-remark:MA130"
    assert detail["priority"] is None


def test_determine_rejects_an_unreadable_claim_without_writing_a_run(tmp_path: Path) -> None:
    bad = tmp_path / "claim.json"
    bad.write_text("{ not json", encoding="utf-8")
    runs = tmp_path / "runs"

    assert cli.determine_command(bad, runs) == 2
    assert not runs.exists()


def test_no_staging_file_is_left_behind(tmp_path: Path) -> None:
    """run.json is written via a temp file and renamed; the temp must not survive."""
    runs = tmp_path / "runs"

    cli.run_command(runs, plain=True, step_delay=0.0)

    leftovers = list(only_run_directory(runs).glob(".*tmp*"))
    assert leftovers == []


def test_local_extraction_reports_a_failure_instead_of_a_traceback(tmp_path: Path) -> None:
    """`--local` is the branch likeliest to fail, and it must fail like the other.

    A scanned EOB needs tesseract on this machine, which `--local` often will not
    have. Before this, that surfaced as a raw `TesseractNotFoundError` out of the
    CLI, leaving a run directory stuck at `running`; the sandbox branch has always
    reported `ExtractionFailed`, which the command already knows how to end on.
    """
    import asyncio
    from datetime import UTC, datetime

    from rcm_agent.run_directory import RunDirectory
    from rcm_agent.sandbox_extraction import ExtractionFailed

    run = RunDirectory.create(tmp_path / "runs", started_at=datetime.now(UTC))
    missing = tmp_path / "not-a-pdf.pdf"
    missing.write_text("this is not a PDF at all", encoding="utf-8")

    async def read_it() -> None:
        async with cli.extractions(EventStream(), run, local=True) as read_document:
            await read_document(missing)

    with pytest.raises(ExtractionFailed) as failure:
        asyncio.run(read_it())

    assert missing.name in str(failure.value), "the report should name the document"
