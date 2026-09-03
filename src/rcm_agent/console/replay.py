"""Reading runs back, with the state each event produced.

The console tails what a run wrote rather than being told anything by the agent.
Nothing has to be configured, no sink has to be registered, and a run started
from a terminal is exactly as visible as any other - including the unattended
ones the reliability measurement makes.

**The server derives; the client renders.** Every event goes out carrying the
cell state it produced, because working that out means applying rules that
already exist in Python: which Actions need evidence, and the fact that a
guardrailed close leaves the work queue rather than sitting at the bottom of it.
A browser recomputing those would be a second copy of them, in a second
language, in a project whose central claim is that its rules live in one place.

**Opening a finished run and opening a live one are the same operation.** The
only difference is whether more events arrive. `RunStream.catch_up` yields what
it has not yielded before, so the first ask happens to be the whole history and
every later one happens to be whatever has landed since; `replay` is that first
ask and nothing else. There is no replay mode to leave, and this file holds one
reader rather than two agreeing by hand.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from rcm_agent.claim_io import claim_from_dict
from rcm_agent.determination import governing_denial
from rcm_agent.events import Event
from rcm_agent.matrix import PHASES, ClaimMatrix
from rcm_agent.review import digest_of
from rcm_agent.strict_json import RecordFileError


def replay(runs_dir: Path) -> Iterator[dict[str, Any]]:
    """Every event every run recorded, oldest run first, each with its state.

    One pass of the same stream a live console follows - there is no second
    reader. Run directories are named for the moment they started, so sorting by
    name is chronological. A missing directory is an empty queue rather than an
    error: the console is often opened before anything has been run.
    """
    yield from RunStream(runs_dir).catch_up()


class RunReplay:
    """One run's accumulated state, fed its events in the order they happened.

    Held as an object rather than as locals in a loop because a live tail comes
    back to the same run again and again as it grows. Replaying a finished run
    and following one in flight are then the same thing: build one of these, feed
    it what has arrived, and feed it more when more arrives.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._matrix = ClaimMatrix([])
        # What each claim's Determination said, once it has one. Carried forward
        # so that *every* event for a claim describes it completely, and a client
        # can take the latest one wholesale instead of merging fields across
        # events - which is how a Determination ends up attributed to a run that
        # never made one.
        self._decided: dict[str, dict[str, Any]] = {}
        self._refused: dict[str, dict[str, Any]] = {}

    def feed(self, raw: dict[str, Any]) -> dict[str, Any]:
        """One recorded event, and the state it produced."""
        event = Event(**raw)
        if event.claim_id is not None:
            # Admitted on sight, because a run being followed announces its
            # claims one event at a time. The matrix used to be handed every
            # claim id up front, which meant the whole log had to be read before
            # any of it could be sent - impossible for a log still being written.
            self._matrix.admit(event.claim_id)
        self._matrix.handle(event)
        if event.kind == "claim" and event.claim_id:
            self._refused[event.claim_id] = _refusal(dict(event.detail))
        if event.kind == "determination" and event.claim_id:
            self._decided[event.claim_id] = dict(event.detail)
        return {
            "run_id": self.run_id,
            **raw,
            "derived": _derived(self._matrix, event, self._decided, self._refused),
        }


def _refusal(recorded: dict[str, Any]) -> dict[str, Any]:
    """What the payer refused, with the denial the Determination answers named.

    `governing_denial` picks the largest *denial* by amount, and a denial is an
    adjustment that refuses payment - a contractual write-off is not one. Left to
    a browser this becomes "the biggest number on the claim", which on the
    rule-closed claim is the `CO-45` write-off: the fact bar would show a
    contractual adjustment as the code being answered and hide the `MA130` the
    guardrail actually fired on.
    """
    try:
        claim = claim_from_dict(recorded)
    except RecordFileError:
        return {**recorded, "governing": None}

    lines = [
        {**line, "charge": _charge(line.get("charge"))}
        for line in recorded.get("service_lines", [])
    ]

    # Guarded rather than caught. A Claim carrying only write-offs has no denial
    # to govern - `governing_denial` takes the largest of `claim.denials`, and
    # `max` of nothing raises - and that is an ordinary claim, not an error.
    if not claim.denials:
        return {**recorded, "service_lines": lines, "governing": None}

    denial = governing_denial(claim)
    return {
        **recorded,
        "service_lines": lines,
        "governing": {
            "group": denial.group,
            "reason_code": denial.reason_code,
            "remark_codes": list(denial.remark_codes),
        },
    }


def _charge(recorded: Any) -> str | None:
    """A charge the remittance never stated, told apart from one that is zero.

    A Claim read off an EOB carries no charge: the document says what was
    adjusted, not what was billed, so `claim_from_extraction` leaves it at zero
    rather than inventing one. Sending that zero on would put a number on screen
    the payer never sent, and leave a browser to decide what it meant - which is
    this rule, in a second language.
    """
    return None if recorded in (None, "0", "0.00") else str(recorded)


def parse_record(line: str) -> dict[str, Any] | None:
    """One recorded line, or nothing if this build cannot read it.

    A run directory is an audit trail that outlives the code that wrote it, and
    an older one can carry a field this build has never heard of. Skipping the
    line loses one row of history; letting it raise takes down the socket
    mid-stream and the console reports itself disconnected, which is a worse
    answer to "there is an event here I do not understand".
    """
    try:
        raw: dict[str, Any] = json.loads(line)
        Event(**raw)
    except (ValueError, TypeError):
        return None
    # `seq` is the join key - to screenshots, to retries, and to where a
    # reconnecting client got to - and `Event` does not enforce its type at
    # runtime. One that is not a number cannot be ordered against a cursor, and
    # letting it through meant it was re-sent on every resume, forever.
    if not isinstance(raw.get("seq"), int) or isinstance(raw.get("seq"), bool):
        return None
    return raw


def _derived(
    matrix: ClaimMatrix,
    event: Event,
    decided: dict[str, dict[str, Any]],
    refused: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """What this event did to the claim it belongs to.

    `guardrailed` is here rather than left to the browser on purpose. Whether a
    claim was closed by a rule is the judgement this whole project turns on, and
    it has an answer in the domain already - `Determination.was_guardrailed`. A
    client testing the rule label for emptiness would be a second, untyped copy
    of that, deciding which section a claim belongs in.

    Every event for a claim carries the claim's whole state as of that event, not
    only what changed. A client merging fields across events cannot tell which
    run a value came from, and mixes them: a Determination from one run rendered
    against the phases and the run label of another.

    `None` for a run-level event - provisioning a sandbox belongs to the run, not
    to any one claim, and inventing a claim for it would put a row in the queue
    that answers to nobody.
    """
    if event.claim_id is None:
        return {
            "cells": None,
            "action": None,
            "determination": None,
            "determination_digest": None,
            "guardrailed": False,
            "claim": None,
        }

    determination = decided.get(event.claim_id)

    return {
        "cells": {phase: matrix.cell(event.claim_id, phase) for phase in PHASES},
        "action": matrix.action_for(event.claim_id),
        # The whole Determination, in the shape `Determination.to_dict` already
        # writes to `claims/<id>.json`. One object rather than its fields spread
        # flat: the console shows a rationale, an evidence list and a Priority
        # together, and they are one answer.
        "determination": determination,
        # Sent rather than computed in the browser. The digest is over the exact
        # bytes the run wrote, and a client reproducing that serialisation would
        # be re-deriving the one number whose whole job is to be checkable
        # against the artifact.
        "determination_digest": None if determination is None else digest_of(determination),
        # The same test `Determination.was_guardrailed` makes, made here so the
        # browser is told the answer instead of working it out.
        "guardrailed": determination is not None and determination.get("guardrail") is not None,
        # The payer's refusal, so the console can show it beside the
        # Determination rather than presenting a conclusion alone.
        "claim": refused.get(event.claim_id),
    }


def determinations(runs_dir: Path) -> dict[str, dict[str, Any]]:
    """The Determination that stands for each claim, and the run that made it.

    Replayed rather than read from `claims/<id>.json`, so this and the console
    agree by construction: both take the last run to have decided a claim, which
    is the one an analyst is looking at.
    """
    latest: dict[str, dict[str, Any]] = {}
    for event in replay(runs_dir):
        determination = event["derived"]["determination"]
        if event["kind"] == "determination" and determination is not None:
            latest[str(event["claim_id"])] = {
                "determination": determination,
                "run_id": str(event["run_id"]),
            }
    return latest


LOG_NAME = "events.ndjson"

Cursor = Mapping[str, int]
"""How far a client has got in each run it has heard of.

A map rather than the single `(run, seq)` pair this started as. `seq` restarts
per run, so one pair meant "the newest thing you were sent" and resuming asked
whether an event sorted above it - which is only the same question while there
is one run in flight. With two, a client's last event comes from the newer one,
and everything the older run goes on to record sorts below the cursor and is
dropped. Not delayed: dropped, and the cursor never advances past it, so they
are gone for the life of the connection.

Runs a client has never heard of are absent from the map and sent in full.
"""


class RunStream:
    """Every run in a directory, read once and then followed.

    Holds one `RunReplay` and one file offset per run, so asking again costs a
    `stat` per run rather than a re-read. A run that has stopped growing costs
    nothing at all.
    """

    def __init__(self, runs_dir: Path, after: Cursor | None = None) -> None:
        self._runs_dir = runs_dir
        self._seen = dict(after or {})
        self._logs: dict[str, _RunLog] = {}

    def catch_up(self) -> Iterator[dict[str, Any]]:
        """Everything recorded since the last time this was asked.

        A missing runs directory is an empty queue rather than an error: the
        console is often opened before anything has been run, and it is the same
        directory a run will later create.
        """
        if not self._runs_dir.is_dir():
            return

        # Re-listed every time rather than once, because a run started while the
        # console is open is a directory that did not exist when it opened.
        for run in sorted(self._runs_dir.iterdir()):
            log = run / LOG_NAME
            if not run.is_dir() or not log.is_file():
                # `RunDirectory.create` makes the directory before it writes
                # anything, so an empty one is a run about to start.
                continue

            follower = self._logs.get(run.name)
            if follower is not None and follower.was_replaced():
                # A shrunk file is not the file we were reading - a runs
                # directory cleared and rebuilt under the same name. The place
                # the client had reached goes with it: kept, it would name a
                # `seq` in a run that no longer exists and silence the new run's
                # opening events.
                self._seen.pop(run.name, None)
                follower = None
            if follower is None:
                follower = _RunLog(log, RunReplay(run.name))
                self._logs[run.name] = follower

            for raw in follower.records():
                enriched = follower.enriched(raw)
                if self._not_yet_sent(run.name, raw):
                    yield enriched

    def _not_yet_sent(self, run_id: str, raw: dict[str, Any]) -> bool:
        """Whether the client still needs this, having named where it got to.

        Asked per run, because that is the grain `seq` counts on. Everything is
        fed to the replay either way: state is cumulative, so a resumed client
        given a matrix that started at its cursor would watch its own queue go
        backwards. This decides only what goes out.
        """
        already = self._seen.get(run_id)
        return already is None or int(raw["seq"]) > already


class _RunLog:
    """One run's log, and how far into it we have read."""

    def __init__(self, path: Path, replay: RunReplay) -> None:
        self.path = path
        self._replay = replay
        self._offset = 0

    def was_replaced(self) -> bool:
        """Whether the file shrank, meaning it is not the one we were reading."""
        return self.path.stat().st_size < self._offset

    def enriched(self, raw: dict[str, Any]) -> dict[str, Any]:
        """This run's state, brought up to and including this event."""
        return self._replay.feed(raw)

    def records(self) -> Iterator[dict[str, Any]]:
        """Every complete event appended since the last read.

        Byte offsets rather than line counts, because the file is being written
        as it is read and the last thing in it is often half a line. Reading up
        to the final newline and advancing by exactly those bytes leaves the
        fragment where it is, to be read again once the rest of it lands.
        """
        size = self.path.stat().st_size
        if size == self._offset:
            return

        with self.path.open("rb") as handle:
            handle.seek(self._offset)
            chunk = handle.read()

        complete = chunk.rfind(b"\n")
        if complete == -1:
            return
        self._offset += complete + 1

        for line in chunk[: complete + 1].decode("utf-8").splitlines():
            raw = parse_record(line)
            if raw is not None:
                yield raw
