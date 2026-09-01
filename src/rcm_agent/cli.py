"""Command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from rcm_agent import demo_script
from rcm_agent.analysis.extract import Extraction
from rcm_agent.claim_io import ClaimFileError, load_claim
from rcm_agent.determination import determine
from rcm_agent.domain import Determination
from rcm_agent.events import EventStream
from rcm_agent.fixtures import generate_fixtures
from rcm_agent.matrix import ClaimMatrix
from rcm_agent.panel import make_panel
from rcm_agent.run_directory import RunDirectory
from rcm_agent.sandbox_extraction import ExtractionFailed, extract_document

EXIT_BAD_INPUT = 2
EXIT_INTERRUPTED = 130


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rcm-agent", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Work a batch of denied claims")
    run.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Where run directories are written (default: ./runs)",
    )
    run.add_argument(
        "--plain", action="store_true", help="Force line-per-event output instead of the live panel"
    )
    run.add_argument(
        "--step-delay",
        type=float,
        default=0.35,
        help="Pause between steps so the panel is readable (default: 0.35s)",
    )

    determine_claim = sub.add_parser(
        "determine", help="Reach a Determination on one claim and print it"
    )
    determine_claim.add_argument("claim", type=Path, help="Path to a claim JSON file")
    determine_claim.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Where run directories are written (default: ./runs)",
    )

    extract_doc = sub.add_parser("extract", help="Read an EOB document in a Solari sandbox")
    extract_doc.add_argument("document", type=Path, help="Path to an EOB PDF")
    extract_doc.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Where run directories are written (default: ./runs)",
    )

    fixtures = sub.add_parser(
        "generate-fixtures", help="Regenerate the synthetic claims and remittance documents"
    )
    fixtures.add_argument(
        "--out",
        type=Path,
        default=Path("data/fixtures"),
        help="Where fixtures are written (default: ./data/fixtures)",
    )
    return parser


def _determination_table(determination: Determination) -> Table:
    table = Table(box=None, pad_edge=False, show_header=False)
    table.add_column("", style="dim", no_wrap=True)
    table.add_column("")

    table.add_row("claim", determination.claim_id)
    table.add_row("action", determination.action)
    if determination.guardrail:
        # Naming the rule matters more than naming the action: it says the answer
        # was fixed by law or contract, not weighed.
        table.add_row("guardrail", determination.guardrail)
    table.add_row("rationale", determination.rationale)
    if determination.evidence_required:
        table.add_row("evidence", ", ".join(determination.evidence_required))
    if determination.priority is not None:
        table.add_row(
            "priority",
            f"{determination.priority.amount_at_stake} at stake, "
            f"expected {determination.priority.expected_recovery}",
        )
    return table


def run_command(runs_dir: Path, *, plain: bool, step_delay: float) -> int:
    console = Console()
    matrix = ClaimMatrix(demo_script.CLAIM_IDS)
    panel = make_panel(matrix, console, force_plain=plain)

    run = RunDirectory.create(runs_dir, started_at=datetime.now(UTC))
    stream = EventStream()

    # Order matters: the matrix updates before the panel repaints, and the run
    # directory records regardless of what the renderers do.
    stream.add_sink(run)
    stream.add_sink(matrix)
    stream.add_sink(panel)

    try:
        with run, panel:
            demo_script.play(stream, step_delay=step_delay)
            # Derived from the events, so the closing frame and run.json cannot
            # claim an outcome the stream did not record.
            summary = matrix.summary()
            run.complete(finished_at=datetime.now(UTC), summary=summary)
            panel.freeze(summary=summary, run_path=run.path)
    except KeyboardInterrupt:
        # The artifacts already tell the truth — events are flushed per event and
        # run.json still says "running" with the phase it reached. Nothing to
        # repair, so say where to look and get out of the way.
        console.print(f"\ninterrupted — partial run at {run.path}")
        return EXIT_INTERRUPTED
    except Exception:
        # Without this the run stays "running" for ever and the `failed` status
        # is unreachable outside tests. Record where it stopped, then re-raise
        # so the traceback is not swallowed.
        run.fail(
            phase=run.state.current_phase or "portal",
            seq=run.last_seq,
            finished_at=datetime.now(UTC),
        )
        console.print(f"\nfailed - partial run at {run.path}")
        raise

    return 0


def determine_command(claim_path: Path, runs_dir: Path) -> int:
    console = Console()

    try:
        claim = load_claim(claim_path)
    except ClaimFileError as exc:
        # A claim that cannot be trusted is worse than one that will not load, so
        # this fails rather than guessing at the missing parts.
        console.print(f"[bold red]cannot read claim[/] {exc}")
        return EXIT_BAD_INPUT

    run = RunDirectory.create(runs_dir, started_at=datetime.now(UTC))
    stream = EventStream()
    stream.add_sink(run)

    with run:
        stream.emit(phase="analysis", kind="phase_start", claim_id=claim.claim_id)
        determination = determine(claim)
        stream.emit(
            phase="analysis",
            kind="determination",
            claim_id=claim.claim_id,
            detail=determination.to_dict(),
        )
        stream.emit(phase="analysis", kind="phase_end", claim_id=claim.claim_id, outcome="ok")
        run.complete(finished_at=datetime.now(UTC), summary={determination.action: 1})

    console.print(_determination_table(determination))
    console.print(str(run.path), style="dim")
    return 0


def _extraction_table(extraction: Extraction) -> Table:
    table = Table(box=None, pad_edge=False)
    table.add_column("line", style="dim", no_wrap=True)
    table.add_column("hcpcs", no_wrap=True)
    table.add_column("adjustment", no_wrap=True)
    table.add_column("remarks", no_wrap=True)
    table.add_column("amount", justify="right", no_wrap=True)
    for line in extraction.lines:
        table.add_row(
            str(line.line_number or "-"),
            line.procedure_code or "-",
            f"{line.group}-{line.reason_code}",
            ", ".join(line.remark_codes) or "-",
            line.amount,
        )
    return table


def extract_command(document: Path, runs_dir: Path) -> int:
    console = Console()
    if not document.is_file():
        console.print(f"[bold red]no such document[/] {document}")
        return EXIT_BAD_INPUT

    run = RunDirectory.create(runs_dir, started_at=datetime.now(UTC))
    stream = EventStream()
    stream.add_sink(run)

    try:
        with run:
            shipment, extraction = asyncio.run(extract_document(document, run, stream))
            run.complete(
                finished_at=datetime.now(UTC),
                summary={extraction.method: len(extraction.lines)},
            )
    except ExtractionFailed as exc:
        run.fail(
            phase=run.state.current_phase or "analysis",
            seq=run.last_seq,
            finished_at=datetime.now(UTC),
        )
        console.print(f"[bold red]extraction failed[/] {exc}")
        console.print(str(run.path), style="dim")
        return EXIT_BAD_INPUT

    console.print(_extraction_table(extraction))
    console.print(f"read by {extraction.method}, sha256 {shipment.digest[:16]}...", style="dim")
    console.print(str(run.path), style="dim")
    return 0


def generate_fixtures_command(out: Path) -> int:
    console = Console()
    for path in generate_fixtures(out):
        console.print(str(path), style="dim")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "determine":
        return determine_command(args.claim, args.runs_dir)
    if args.command == "extract":
        return extract_command(args.document, args.runs_dir)
    if args.command == "generate-fixtures":
        return generate_fixtures_command(args.out)
    return run_command(args.runs_dir, plain=args.plain, step_delay=args.step_delay)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
