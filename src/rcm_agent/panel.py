"""The live progress surface — the second renderer of the event stream.

Claim matrix over event tail. The matrix carries the run's shape; the tail
carries step detail and gives a recovery somewhere legible to land.

Two rules matter more than the layout:

* A `recovery` reads as **handled**, never as an error. A run that visibly
  stumbles and recovers is more convincing than one that never stumbles — but
  only if the panel says so rather than flashing red.
* `na` is a distinct cell state from "not yet", because that is how a
  guardrailed determination shows up.

On completion the panel freezes with every cell in its final state. That frozen
frame is the demo's closing shot, generated rather than staged, so a reviewer
running the project sees exactly what the video ends on.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.table import Table
from rich.text import Text

from rcm_agent.events import Event
from rcm_agent.matrix import PHASES, CellState, ClaimMatrix

_TAIL_LENGTH = 8

_CELL_STYLES: dict[CellState, str] = {
    "pending": "dim",
    "running": "bold cyan",
    "done": "green",
    "na": "dim italic",
    "failed": "bold red",
}

_OUTCOME_STYLES: dict[str, str] = {
    "ok": "green",
    "recovered": "yellow",
    "failed": "bold red",
}


@dataclass(frozen=True, slots=True)
class Glyphs:
    """Cell and marker characters, chosen to suit the output encoding."""

    pending: str
    running: str
    done: str
    na: str
    failed: str
    recovery: str

    def cell(self, state: CellState) -> str:
        return getattr(self, state)  # pyright: ignore[reportAny]


UNICODE_GLYPHS = Glyphs(pending="·", running="●", done="✓", na="n/a", failed="✗", recovery="↻")
ASCII_GLYPHS = Glyphs(pending=".", running="*", done="+", na="n/a", failed="x", recovery="~")


def glyphs_for(console: Console) -> Glyphs:
    """Pick a glyph set the console can actually encode.

    A redirected stdout on Windows is cp1252, which cannot encode any of the box
    characters — and an exception from the renderer would otherwise be the only
    sign. Degrade to ASCII rather than crash or emit replacement characters.
    """
    encoding = getattr(console.file, "encoding", None) or "utf-8"
    try:
        "".join((UNICODE_GLYPHS.running, UNICODE_GLYPHS.done, UNICODE_GLYPHS.recovery)).encode(
            encoding
        )
    except (LookupError, UnicodeEncodeError):
        return ASCII_GLYPHS
    return UNICODE_GLYPHS


class ProgressPanel(Protocol):
    def handle(self, event: Event) -> None: ...
    def freeze(self, *, summary: dict[str, int], run_path: Path) -> None: ...
    def __enter__(self) -> ProgressPanel: ...
    def __exit__(self, *args: object) -> None: ...


def describe(event: Event, glyphs: Glyphs) -> Text:
    """One line of the tail. Recovery is styled as handled, never as an error."""
    line = Text()
    line.append(f"[{event.phase:<8}] ", style="dim")

    if event.kind == "recovery":
        reason = str(event.detail.get("reason", "recovered"))
        line.append(f"{glyphs.recovery} ", style="yellow")
        line.append(f"{reason} — handled", style="yellow")
        return line

    label = event.tool or event.kind.replace("_", " ")
    line.append(f"{label:<22}")

    if event.claim_id:
        line.append(f"{event.claim_id:<12}", style="dim")

    if event.outcome:
        line.append(event.outcome, style=_OUTCOME_STYLES.get(event.outcome, ""))

    attempts = event.detail.get("attempts")
    if isinstance(attempts, int) and attempts > 1:
        line.append(f"  ({attempts} attempts)", style="dim")

    return line


def matrix_table(matrix: ClaimMatrix, glyphs: Glyphs) -> Table:
    table = Table(box=None, pad_edge=False, expand=False)
    table.add_column("", style="bold", no_wrap=True)
    for phase in PHASES:
        table.add_column(phase, justify="center", no_wrap=True)

    for claim_id in matrix.claim_ids:
        cells: list[RenderableType] = [Text(claim_id)]
        for phase in PHASES:
            state = matrix.cell(claim_id, phase)
            cells.append(Text(glyphs.cell(state), style=_CELL_STYLES[state]))
        table.add_row(*cells)
    return table


class RichPanel:
    """Live-rendered panel for an interactive terminal."""

    def __init__(self, matrix: ClaimMatrix, console: Console | None = None) -> None:
        self._matrix = matrix
        self._console = console or Console()
        self._glyphs = glyphs_for(self._console)
        self._tail: deque[Text] = deque(maxlen=_TAIL_LENGTH)
        self._live = Live(self._render(), console=self._console, refresh_per_second=8)

    def _render(self) -> RenderableType:
        return Group(matrix_table(self._matrix, self._glyphs), Text(""), *self._tail)

    def handle(self, event: Event) -> None:
        # The matrix keeps its own subscription to the stream; the panel reacts
        # to the same event only for the tail, then repaints.
        self._tail.append(describe(event, self._glyphs))
        self._live.update(self._render())

    def freeze(self, *, summary: dict[str, int], run_path: Path) -> None:
        self._live.update(self._render())
        self._live.stop()
        if summary:
            parts = " · ".join(f"{count} {label}" for label, count in summary.items())
            self._console.print(Text(parts, style="bold"))
        self._console.print(Text(str(run_path), style="dim"))

    def __enter__(self) -> RichPanel:
        self._live.start()
        return self

    def __exit__(self, *_: object) -> None:
        if self._live.is_started:
            self._live.stop()


class PlainPanel:
    """Line-per-event output for pipes, CI and anything that is not a terminal.

    Emitting cursor-control codes into a log file helps nobody, so when stdout is
    not a terminal the panel degrades rather than disappearing.
    """

    def __init__(self, matrix: ClaimMatrix, console: Console | None = None) -> None:
        self._matrix = matrix
        self._console = console or Console(no_color=True)
        self._glyphs = glyphs_for(self._console)

    def handle(self, event: Event) -> None:
        self._console.print(describe(event, self._glyphs), highlight=False)

    def freeze(self, *, summary: dict[str, int], run_path: Path) -> None:
        self._console.print(matrix_table(self._matrix, self._glyphs))
        if summary:
            self._console.print(" | ".join(f"{c} {label}" for label, c in summary.items()))
        self._console.print(str(run_path))

    def __enter__(self) -> PlainPanel:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def make_panel(matrix: ClaimMatrix, console: Console | None = None) -> ProgressPanel:
    console = console or Console()
    if console.is_terminal:
        return RichPanel(matrix, console)
    return PlainPanel(matrix, console)
