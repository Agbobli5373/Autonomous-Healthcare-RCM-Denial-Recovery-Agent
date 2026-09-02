"""The run's single event stream.

One typed event per tool call and phase transition, fanned out to every sink.
The progress panel renders it live; the audit writer appends it to
`events.ndjson`. One emitter and one schema means the screen and the record
cannot disagree — which is the point, in a project whose central claim is
auditability.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

log = logging.getLogger(__name__)

Phase = Literal["setup", "portal", "analysis", "emr", "appeal", "report"]
"""Phases are named by role, not by Solari primitive.

`setup` is the odd one and is deliberately run-level: standing the mocks up in a
sandbox happens once, for the whole run, rather than once per claim. It is not in
`matrix.PHASES` for that reason - the matrix is a grid of claims against the work
done on each, and a column every claim shares tells the viewer nothing. Its
events still reach the run directory, which is where the preview URLs belong.
"""

Kind = Literal[
    "phase_start",
    "phase_end",
    "tool_call",
    "tool_result",
    "determination",
    "recovery",
    "retry",
    "error",
]
"""Neither `recovery` nor `retry` is a subtype of `error`.

A `retry` is a mechanical attempt that did not land - an element a frame late, a
click that missed - and the next one usually works. Recording it as an error
would make a healthy run look broken; not recording it at all would make a tool
that quietly tried three times indistinguishable from one that worked at once.

`recovery` is the other kind of handled thing.

The mock portal expires its session on purpose, and the agent re-authenticates.
That is handled behaviour, and the schema says so rather than leaving every
consumer to infer it from an error with a special message.
"""

Outcome = Literal["ok", "recovered", "failed"]

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _no_detail() -> dict[str, Any]:
    return {}


@dataclass(frozen=True, slots=True)
class Event:
    seq: int
    ts: str
    phase: Phase
    kind: Kind
    tool: str | None = None
    claim_id: str | None = None
    outcome: Outcome | None = None
    screenshot: str | None = None
    detail: Mapping[str, Any] = field(default_factory=_no_detail)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "phase": self.phase,
            "kind": self.kind,
            "tool": self.tool,
            "claim_id": self.claim_id,
            "outcome": self.outcome,
            "screenshot": self.screenshot,
            "detail": dict(self.detail),
        }


class EventSink(Protocol):
    def handle(self, event: Event) -> None: ...


class EventStream:
    """Assigns sequence numbers and timestamps, then fans out to sinks.

    `seq` is the join key between events, screenshots and retry attempts, so it
    is assigned here and nowhere else.
    """

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock: Clock = clock or _utc_now
        self._sinks: list[EventSink] = []
        self._seq = 0

    def add_sink(self, sink: EventSink) -> None:
        self._sinks.append(sink)

    @property
    def next_seq(self) -> int:
        """The number the next emit will assign.

        Screenshots are named for the event that references them, so whoever
        writes the file has to know the seq before the event exists. Asking here
        keeps that number issued in one place; a second counter kept elsewhere
        would drift the moment anything emitted out of order.
        """
        return self._seq + 1

    def emit(
        self,
        *,
        phase: Phase,
        kind: Kind,
        tool: str | None = None,
        claim_id: str | None = None,
        outcome: Outcome | None = None,
        screenshot: str | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> Event:
        self._seq += 1
        event = Event(
            seq=self._seq,
            ts=self._clock().isoformat(),
            phase=phase,
            kind=kind,
            tool=tool,
            claim_id=claim_id,
            outcome=outcome,
            screenshot=screenshot,
            detail=dict(detail) if detail else {},
        )
        for sink in self._sinks:
            try:
                sink.handle(event)
            except Exception:
                # A broken renderer must never cost us the audit record, and a
                # broken audit writer must never blank the screen. Sinks are
                # independent by construction.
                log.exception("event sink %r failed on seq %d", type(sink).__name__, event.seq)
        return event
