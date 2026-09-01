"""The run's artifacts on disk.

Everything is written as it happens. `events.ndjson` is appended and flushed per
event; `run.json` is rewritten at every phase transition carrying an explicit
status. So a run killed at step six of nine leaves a directory that is valid and
honest rather than absent or misleading — which is the whole of FR-4's
partial-progress requirement, and the part most easily skipped.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TextIO

from rcm_agent.events import Event, Phase

Status = Literal["running", "completed", "failed"]

_SUBDIRECTORIES = ("claims", "screenshots", "documents")


def _no_summary() -> dict[str, int]:
    return {}


def _write_atomically(destination: Path, payload: str) -> None:
    staging = destination.with_name(f".{destination.name}.tmp")
    staging.write_text(payload, encoding="utf-8")
    os.replace(staging, destination)


def _directory_stamp(moment: datetime) -> str:
    """ISO 8601 with a dash-separated time — colons are illegal in Windows paths.

    Normalised to UTC first: the trailing Z is a claim about the timezone, and
    stamping it on a local-time value would make the directory name disagree
    with the `started_at` recorded beside it.
    """
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")


@dataclass(frozen=True, slots=True)
class FailurePoint:
    phase: Phase
    seq: int

    def to_dict(self) -> dict[str, Any]:
        return {"phase": self.phase, "seq": self.seq}


@dataclass
class RunState:
    run_id: str
    started_at: str
    status: Status = "running"
    current_phase: Phase | None = None
    finished_at: str | None = None
    failed_at: FailurePoint | None = None
    summary: dict[str, int] = field(default_factory=_no_summary)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "status": self.status,
            "current_phase": self.current_phase,
            "finished_at": self.finished_at,
            "failed_at": self.failed_at.to_dict() if self.failed_at else None,
            "summary": dict(self.summary),
        }


class RunDirectory:
    """An event sink that is also the run's artifact store."""

    def __init__(self, path: Path, state: RunState) -> None:
        self.path = path
        self.state = state
        self._last_seq = 0
        self._events: TextIO = self.events_path.open("a", encoding="utf-8", newline="\n")

    @classmethod
    def create(cls, root: Path, *, started_at: datetime) -> RunDirectory:
        root.mkdir(parents=True, exist_ok=True)
        path = cls._reserve(root, started_at)
        for name in _SUBDIRECTORIES:
            (path / name).mkdir()

        run = cls(path, RunState(run_id=path.name, started_at=started_at.isoformat()))
        run.write_state()
        return run

    @staticmethod
    def _reserve(root: Path, started_at: datetime) -> Path:
        """Claim a directory, suffixing if one already exists for this second."""
        stamp = _directory_stamp(started_at)
        candidate = root / stamp
        suffix = 2
        while True:
            try:
                candidate.mkdir()
                return candidate
            except FileExistsError:
                candidate = root / f"{stamp}-{suffix}"
                suffix += 1

    @property
    def events_path(self) -> Path:
        return self.path / "events.ndjson"

    @property
    def run_json_path(self) -> Path:
        return self.path / "run.json"

    @property
    def claims_path(self) -> Path:
        return self.path / "claims"

    @property
    def screenshots_path(self) -> Path:
        return self.path / "screenshots"

    @property
    def documents_path(self) -> Path:
        return self.path / "documents"

    @property
    def last_seq(self) -> int:
        """Sequence number of the last event written — what `fail()` points at."""
        return self._last_seq

    def handle(self, event: Event) -> None:
        self._last_seq = event.seq
        self._events.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        # Flushed per event on purpose: a hard kill must not lose what a buffer
        # was still holding. These are small writes and there are few of them.
        self._events.flush()

        if event.kind == "phase_start" and event.phase != self.state.current_phase:
            self.state.current_phase = event.phase
            self.write_state()

    def write_state(self) -> None:
        # Written atomically. `write_text` truncates before writing, so a kill
        # landing in that window leaves a corrupt run.json — in the one
        # requirement that is specifically about surviving kills.
        _write_atomically(
            self.run_json_path,
            json.dumps(self.state.to_dict(), indent=2, ensure_ascii=False) + "\n",
        )

    def complete(self, *, finished_at: datetime, summary: dict[str, int] | None = None) -> None:
        self.state.status = "completed"
        self.state.finished_at = finished_at.isoformat()
        if summary is not None:
            self.state.summary = dict(summary)
        self.write_state()

    def fail(self, *, phase: Phase, seq: int, finished_at: datetime) -> None:
        self.state.status = "failed"
        self.state.failed_at = FailurePoint(phase=phase, seq=seq)
        self.state.finished_at = finished_at.isoformat()
        self.write_state()

    def close(self) -> None:
        if not self._events.closed:
            self._events.close()

    def __enter__(self) -> RunDirectory:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
