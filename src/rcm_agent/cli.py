"""Command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

from rcm_agent import demo_script
from rcm_agent.agent import AgentRun, PortalAccess, Workspace, work_the_claim
from rcm_agent.agent.client import planning_client
from rcm_agent.agent.determining import determine_with_judgement, record_guardrails
from rcm_agent.analysis.extract import Extraction
from rcm_agent.browser.session import cloud_browser
from rcm_agent.claim_from_document import ClaimIdentity, claim_from_extraction
from rcm_agent.claim_io import load_claim
from rcm_agent.config import MissingCredential, credential
from rcm_agent.determination import from_catalogue, run_guardrails
from rcm_agent.domain import Determination
from rcm_agent.events import EventStream
from rcm_agent.fixtures.generate import generate_fixtures
from rcm_agent.fixtures.naming import eob_filename
from rcm_agent.matrix import ClaimMatrix
from rcm_agent.mocks.practice_management import storage_state as practice_storage_state
from rcm_agent.panel import make_panel
from rcm_agent.run_directory import RunDirectory
from rcm_agent.sandbox import (
    ProvisioningError,
    SandboxUnreachable,
    ServerStartupError,
    UploadFailed,
)
from rcm_agent.sandbox_extraction import (
    SOURCE_ROOT,
    ExtractionFailed,
    extract_document,
    provisioned_sandbox,
)
from rcm_agent.sandbox_hosting import hosted_mocks, keep_alive
from rcm_agent.strict_json import RecordFileError

if TYPE_CHECKING:  # imported lazily at run time so `--help` stays fast
    from fastapi import FastAPI

PORTAL_USER = "provider"
PORTAL_PASSWORD = "demo"
"""The mock accepts anything; these exist so the run is reproducible, not secret."""

EXIT_BAD_INPUT = 2
EXIT_ENVIRONMENT = 3
"""The request was fine; the environment could not carry it out."""

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

    console_ui = sub.add_parser("console", help="Open the operator console")
    console_ui.add_argument("--host", default="127.0.0.1")
    console_ui.add_argument("--port", type=int, default=8090)

    portal = sub.add_parser("serve-portal", help="Run the mock payer portal locally")
    portal.add_argument("--host", default="127.0.0.1")
    portal.add_argument("--port", type=int, default=8080)

    practice = sub.add_parser(
        "serve-practice", help="Run the mock practice-management system locally"
    )
    practice.add_argument("--host", default="127.0.0.1")
    practice.add_argument("--port", type=int, default=8081)

    host = sub.add_parser(
        "host-mocks",
        help="Serve both mocks from a Solari sandbox and print their public URLs",
    )
    host.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Where run directories are written (default: ./runs)",
    )
    host.add_argument(
        "--document",
        type=Path,
        default=Path("data/fixtures/eobs/clm-2026-0001-eob.pdf"),
        help="The EOB the analysis kernel reads, to prove one sandbox does all three jobs",
    )

    browse = sub.add_parser(
        "browse",
        help="Let the agent work a claim in the sandbox-hosted portal",
    )
    browse.add_argument(
        "--claim",
        default="CLM-2026-0001",
        help="Which claim to fetch the EOB for (default: the CO-197 claim)",
    )
    browse.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Where run directories are written (default: ./runs)",
    )

    determine_all = sub.add_parser(
        "determine-all",
        help="Extract every committed EOB and reach a Determination on each claim",
    )
    determine_all.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Where run directories are written (default: ./runs)",
    )
    determine_all.add_argument(
        "--plain", action="store_true", help="Force line-per-event output instead of the live panel"
    )
    determine_all.add_argument(
        "--local",
        action="store_true",
        help="Extract on this machine instead of in a Solari sandbox",
    )

    profile = sub.add_parser(
        "practice-storage-state",
        help="Write a Solari browser profile that is already signed on to the practice system",
    )
    profile.add_argument(
        "--url",
        default="http://127.0.0.1:8081",
        help="Where the practice system will be reached (default: http://127.0.0.1:8081)",
    )
    profile.add_argument(
        "--out",
        type=Path,
        default=Path("practice-storage-state.json"),
        help="Where to write it (default: ./practice-storage-state.json)",
    )

    fixtures = sub.add_parser(
        "generate-fixtures", help="Regenerate the synthetic claims and EOB documents"
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
    except RecordFileError as exc:
        # A claim that cannot be trusted is worse than one that will not load, so
        # this fails rather than guessing at the missing parts.
        console.print(f"[bold red]cannot read claim[/] {exc}")
        return EXIT_BAD_INPUT

    run = RunDirectory.create(runs_dir, started_at=datetime.now(UTC))
    stream = EventStream()
    stream.add_sink(run)

    with run:
        stream.emit(phase="analysis", kind="phase_start", claim_id=claim.claim_id)
        # The trace is reused rather than `determine` called, so this route
        # records the guardrails without evaluating them twice.
        trace = run_guardrails(claim)
        record_guardrails(stream, claim.claim_id, trace)
        determination = trace.determination or from_catalogue(claim)
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


def _serve(app: FastAPI, host: str, port: int) -> int:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0


def console_command(host: str, port: int) -> int:
    """Serve the console's committed bundle.

    No build step, and no Node. The JavaScript toolchain in `console/` exists
    for developing this page; a reviewer types this command and nothing else.
    """
    from rcm_agent.console.server import ConsoleNotBuilt, create_app

    display = Console()
    try:
        app = create_app()
    except ConsoleNotBuilt as exc:
        display.print(f"[bold red]{exc}[/]")
        return EXIT_BAD_INPUT

    display.print(f"console on http://{host}:{port}", style="dim")
    return _serve(app, host, port)


def serve_portal_command(host: str, port: int) -> int:
    from rcm_agent.mocks.portal import create_app

    return _serve(create_app(), host, port)


def serve_practice_command(host: str, port: int) -> int:
    from rcm_agent.mocks.practice_management import create_app

    return _serve(create_app(), host, port)


def host_mocks_command(runs_dir: Path, document: Path) -> int:
    """Bring both mocks up in one sandbox and hold them there until interrupted.

    The analysis kernel runs in that same guest, on a real document, before the
    mocks are handed over. Provisioning it was not enough: the arrangement the
    Free tier forces on the demo is one sandbox serving both mocks *and* running
    the kernel, and only running it proves the three coexist. An earlier version
    provisioned the kernel here while the only code that ran one opened a second
    sandbox — which on this tier is the collision this command exists to avoid.
    """
    console = Console()
    run = RunDirectory.create(runs_dir, started_at=datetime.now(UTC))
    stream = EventStream()
    stream.add_sink(run)

    async def serve() -> None:
        async with hosted_mocks(stream) as hosting:
            for mock in hosting.mocks:
                console.print(f"{mock.name:22} [link={mock.url}]{mock.url}[/link]")

            console.print("provisioning the analysis kernel in the same sandbox...", style="dim")
            provisioning = await hosting.sandbox.provision()
            await hosting.sandbox.upload_analysis_code(SOURCE_ROOT)
            console.print(f"kernel ready (tesseract at {provisioning.tesseract_path})")

            _, extraction = await extract_document(document, run, stream, sandbox=hosting.sandbox)
            console.print(
                f"kernel read {document.name} by {extraction.method}: "
                f"{len(extraction.lines)} adjustments, while both mocks were served"
            )

            console.print("\nserving. press ctrl-c to tear down.", style="dim")
            # Not a plain sleep: the sandbox TTL is a rolling idle window, so a
            # host that does nothing lets the mocks expire underneath itself.
            await keep_alive(hosting.sandbox)

    with run:
        try:
            asyncio.run(serve())
        except KeyboardInterrupt:
            console.print(f"\ntorn down - run at {run.path}")
            return EXIT_INTERRUPTED
        except MissingCredential as exc:
            # No key configured is bad input. The two below are not: the request
            # was fine and the environment could not carry it out.
            console.print(f"[bold red]{exc}[/]")
            return EXIT_BAD_INPUT
        except (
            ServerStartupError,
            ProvisioningError,
            UploadFailed,
            SandboxUnreachable,
            ExtractionFailed,
        ) as exc:
            # Reported as a message rather than re-raised, because the whole
            # point of the in-guest health check is that a server which never
            # bound gets named here instead of surfacing as a browser error
            # later. `run.fail` sits inside the `with`, or it would be recording
            # against a run directory that has already been closed.
            console.print(f"[bold red]could not host the mocks[/] {exc}")
            run.fail(phase="setup", seq=run.last_seq, finished_at=datetime.now(UTC))
            return EXIT_ENVIRONMENT
    return 0


def browse_command(claim_id: str, runs_dir: Path) -> int:
    """The whole browser leg: host the mocks, drive them, bring back the EOB.

    Both halves are real. The portal is served from a Solari sandbox and reached
    over its public preview URL, and the browser is a Solari cloud browser — so
    this exercises the arrangement the demo runs on rather than a local stand-in.
    """
    console = Console()
    run = RunDirectory.create(runs_dir, started_at=datetime.now(UTC))
    stream = EventStream()
    stream.add_sink(run)

    async def go() -> AgentRun:
        solari = credential("SOLARI_API_KEY")
        planner = planning_client(stream)
        async with hosted_mocks(stream) as hosting:
            portal = next(m for m in hosting.mocks if m.name == "payer-portal")
            practice = next(m for m in hosting.mocks if m.name == "practice-management")
            console.print(f"portal   {portal.url_without_token}", style="dim")
            console.print(f"practice {practice.url_without_token}", style="dim")

            # Two browser sessions at once, and the sandbox serving both mocks
            # underneath them. Browsers and sandboxes are separate concurrency
            # counters, so two of one and one of the other fits the Free tier.
            # Nested rather than sequential because the agent moves between the
            # two systems and back; opening the practice session only when it is
            # first needed would put a visible pause in the middle of the demo.
            async with (
                cloud_browser(solari, stream, label="payer-portal") as portal_page,
                cloud_browser(
                    solari,
                    stream,
                    storage_state=practice_storage_state(practice.url),
                    label="practice-management",
                ) as practice_page,
            ):
                return await work_the_claim(
                    Workspace(
                        portal_page=portal_page,
                        portal=PortalAccess(
                            url=portal.url, user=PORTAL_USER, password=PORTAL_PASSWORD
                        ),
                        practice_page=practice_page,
                        practice_url=practice.url,
                    ),
                    claim_id=claim_id,
                    stream=stream,
                    documents=run.documents_path,
                    screenshots=run.screenshots_path,
                    client=planner,
                )

    with run:
        try:
            work = asyncio.run(go())
        except KeyboardInterrupt:
            console.print(f"\ninterrupted - partial run at {run.path}")
            return EXIT_INTERRUPTED
        except MissingCredential as exc:
            console.print(f"[bold red]{exc}[/]")
            return EXIT_BAD_INPUT
        except (ServerStartupError, ProvisioningError, UploadFailed, SandboxUnreachable) as exc:
            console.print(f"[bold red]could not host the mocks[/] {exc}")
            run.fail(phase="setup", seq=run.last_seq, finished_at=datetime.now(UTC))
            return EXIT_ENVIRONMENT

        for step in work.steps:
            console.print(f"  {step.tool:15} {step.outcome}")
        if work.recovered:
            console.print("the agent recovered from the session expiry", style="dim")
        if work.noted:
            console.print("the agent wrote its finding onto the patient's chart", style="dim")
        calls = work.usage.steps
        console.print(
            f"{calls} model call{'' if calls == 1 else 's'},  "
            f"{work.usage.input_tokens:,} in / {work.usage.output_tokens:,} out",
            style="dim",
        )
        if work.said:
            console.print(f"agent: {work.said}", style="dim italic")
        if not work.ok:
            console.print("[bold red]the agent did not obtain the EOB[/]")
            run.fail(phase="portal", seq=run.last_seq, finished_at=datetime.now(UTC))
            return EXIT_ENVIRONMENT
        console.print(f"EOB saved to {work.document}")
        console.print(f"run at {run.path}")
    return 0


def determine_all_command(runs_dir: Path, *, plain: bool, local: bool) -> int:
    """Every committed claim, from its EOB document to a Determination.

    This is where the matrix visibly diverges: one claim heads for an appeal, one
    is closed by a rule without a model ever being asked, and one is recoverable
    by rebilling rather than by appealing. An agent that answered `appeal`
    everywhere would get one of the three right.

    Extraction runs in a Solari sandbox by default, because that is the
    arrangement the demo uses. `--local` runs it here instead, for when the
    interesting part is the adjudication rather than the transport.
    """
    console = Console()
    claims = sorted(Path("data/fixtures/claims").glob("*.json"))
    matrix = ClaimMatrix([load_claim(path).claim_id for path in claims])
    panel = make_panel(matrix, console, force_plain=plain)

    run = RunDirectory.create(runs_dir, started_at=datetime.now(UTC))
    stream = EventStream()
    stream.add_sink(run)
    stream.add_sink(matrix)
    stream.add_sink(panel)

    async def work() -> None:
        judge_client = planning_client(stream, phase="analysis")
        async with extractions(stream, run, local=local) as read_document:
            for path in claims:
                known = load_claim(path)
                document = Path("data/fixtures/eobs") / eob_filename(known.claim_id)
                stream.emit(phase="analysis", kind="phase_start", claim_id=known.claim_id)

                claim = claim_from_extraction(
                    await read_document(document), ClaimIdentity.of(known)
                )
                determination = await determine_with_judgement(
                    claim, client=judge_client, stream=stream
                )
                run.write_claim(determination)
                stream.emit(
                    phase="analysis", kind="phase_end", claim_id=known.claim_id, outcome="ok"
                )

    try:
        with run, panel:
            try:
                asyncio.run(work())
            except MissingCredential as exc:
                console.print(f"[bold red]{exc}[/]")
                return EXIT_BAD_INPUT
            except (
                ServerStartupError,
                ProvisioningError,
                UploadFailed,
                SandboxUnreachable,
                ExtractionFailed,
            ) as exc:
                # Inside the `with`, for the reason `host_mocks_command` gives:
                # outside it, this records against a run directory that has
                # already been closed.
                console.print(f"[bold red]could not reach a Determination[/] {exc}")
                run.fail(phase="analysis", seq=run.last_seq, finished_at=datetime.now(UTC))
                return EXIT_ENVIRONMENT

            summary = matrix.summary()
            run.complete(finished_at=datetime.now(UTC), summary=summary)
            panel.freeze(summary=summary, run_path=run.path)
    except KeyboardInterrupt:
        console.print(f"\ninterrupted - partial run at {run.path}")
        return EXIT_INTERRUPTED

    console.print(f"per-claim determinations in {run.claims_path}")
    return 0


@contextlib.asynccontextmanager
async def extractions(
    stream: EventStream, run: RunDirectory, *, local: bool
) -> AsyncGenerator[Callable[[Path], Awaitable[Extraction]]]:
    """Hand back a way to read one EOB, either in a sandbox or on this machine.

    One sandbox for all three documents rather than one each: provisioning costs
    about twenty seconds, and the Free tier allows a single sandbox anyway.
    """
    if local:
        from rcm_agent.analysis.extract import extract as extract_here

        async def here(document: Path) -> Extraction:
            stream.emit(phase="analysis", kind="tool_call", tool="extract_document")
            try:
                return extract_here(document)
            except Exception as exc:
                # The sandbox path reports every read failure as ExtractionFailed
                # and the run ends tidily. Local extraction should not be the one
                # that ends a run in a traceback with a half-written directory
                # behind it - and it is the likelier one to fail, because a
                # scanned EOB needs tesseract installed on this machine.
                raise ExtractionFailed(f"could not read {document.name}: {exc}") from exc

        yield here
        return

    async with provisioned_sandbox(stream) as sandbox:

        async def in_the_sandbox(document: Path) -> Extraction:
            _, extraction = await extract_document(document, run, stream, sandbox=sandbox)
            return extraction

        yield in_the_sandbox


def practice_storage_state_command(url: str, out: Path) -> int:
    """Write the profile that lets the demo skip a login it has nothing to show.

    Solari profiles are Playwright `storageState` files, and uploading one is a
    documented way to create a profile — so the second profile is reproducible
    from the repository rather than from whoever last logged in by hand.
    """
    from rcm_agent.mocks.practice_management import storage_state

    out.write_text(json.dumps(storage_state(url), indent=2) + "\n", encoding="utf-8")
    Console().print(str(out), style="dim")
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
    if args.command == "serve-portal":
        return serve_portal_command(args.host, args.port)
    if args.command == "serve-practice":
        return serve_practice_command(args.host, args.port)
    if args.command == "host-mocks":
        return host_mocks_command(args.runs_dir, args.document)
    if args.command == "console":
        return console_command(args.host, args.port)
    if args.command == "determine-all":
        return determine_all_command(args.runs_dir, plain=args.plain, local=args.local)
    if args.command == "browse":
        return browse_command(args.claim, args.runs_dir)
    if args.command == "practice-storage-state":
        return practice_storage_state_command(args.url, args.out)
    if args.command == "generate-fixtures":
        return generate_fixtures_command(args.out)
    return run_command(args.runs_dir, plain=args.plain, step_delay=args.step_delay)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
