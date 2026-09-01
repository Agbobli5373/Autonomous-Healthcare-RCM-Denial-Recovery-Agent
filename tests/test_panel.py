from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console

from rcm_agent.events import Event, EventStream
from rcm_agent.matrix import ClaimMatrix
from rcm_agent.panel import (
    ASCII_GLYPHS,
    UNICODE_GLYPHS,
    PlainPanel,
    describe,
    glyphs_for,
    make_panel,
    matrix_table,
)

CLAIMS = ["CLM-0001", "CLM-0002", "CLM-0003"]


def console_with_encoding(encoding: str) -> Console:
    stream = io.TextIOWrapper(io.BytesIO(), encoding=encoding, errors="strict")
    return Console(file=stream, width=100, no_color=True)


def an_event(**overrides: object) -> Event:
    stream = EventStream(clock=lambda: datetime(2026, 9, 1, tzinfo=UTC))
    defaults: dict[str, object] = {"phase": "portal", "kind": "phase_start"}
    defaults.update(overrides)
    return stream.emit(**defaults)  # pyright: ignore[reportArgumentType]


def test_a_utf8_console_gets_the_unicode_glyphs() -> None:
    assert glyphs_for(console_with_encoding("utf-8")) is UNICODE_GLYPHS


def test_a_cp1252_console_falls_back_to_ascii() -> None:
    """A redirected stdout on Windows cannot encode the box characters.

    Found by running the CLI with output piped: the renderer raised
    UnicodeEncodeError on the recovery arrow. Degrade, do not crash.
    """
    assert glyphs_for(console_with_encoding("cp1252")) is ASCII_GLYPHS


def test_the_ascii_glyphs_are_actually_encodable_in_cp1252() -> None:
    for value in (
        ASCII_GLYPHS.pending,
        ASCII_GLYPHS.running,
        ASCII_GLYPHS.done,
        ASCII_GLYPHS.na,
        ASCII_GLYPHS.failed,
        ASCII_GLYPHS.recovery,
    ):
        value.encode("cp1252")


def test_rendering_a_recovery_to_a_cp1252_console_does_not_raise() -> None:
    console = console_with_encoding("cp1252")
    panel = PlainPanel(ClaimMatrix(CLAIMS), console)

    panel.handle(
        an_event(kind="recovery", claim_id="CLM-0001", detail={"reason": "session expired"})
    )
    panel.freeze(summary={"appealed": 1}, run_path=Path("runs/x"))


def test_a_recovery_reads_as_handled_not_as_an_error() -> None:
    line = describe(
        an_event(kind="recovery", detail={"reason": "session expired"}), UNICODE_GLYPHS
    ).plain

    assert "handled" in line
    assert "error" not in line.lower()
    assert "fail" not in line.lower()


def test_the_tail_shows_retry_attempts_when_there_were_several() -> None:
    line = describe(
        an_event(kind="tool_result", tool="open_claim", outcome="ok", detail={"attempts": 3}),
        UNICODE_GLYPHS,
    ).plain

    assert "3 attempts" in line


def test_a_single_attempt_is_not_called_out() -> None:
    line = describe(
        an_event(kind="tool_result", tool="open_claim", outcome="ok", detail={"attempts": 1}),
        UNICODE_GLYPHS,
    ).plain

    assert "attempt" not in line


def test_not_applicable_renders_differently_from_pending() -> None:
    matrix = ClaimMatrix(CLAIMS)
    stream = EventStream(clock=lambda: datetime(2026, 9, 1, tzinfo=UTC))
    stream.add_sink(matrix)
    stream.emit(
        phase="analysis", kind="determination", claim_id="CLM-0002", detail={"action": "decline"}
    )

    buffer = io.StringIO()
    console = Console(file=buffer, width=100, no_color=True)
    console.print(matrix_table(matrix, UNICODE_GLYPHS))
    rendered = buffer.getvalue()

    assert UNICODE_GLYPHS.na in rendered
    assert UNICODE_GLYPHS.pending in rendered


def test_a_non_terminal_console_gets_the_plain_panel() -> None:
    panel = make_panel(ClaimMatrix(CLAIMS), console_with_encoding("utf-8"))

    assert isinstance(panel, PlainPanel)
