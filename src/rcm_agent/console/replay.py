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

Opening a finished run and opening a live one are the same operation - the only
difference is whether more events arrive - so this is also what a later ticket
follows from.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from rcm_agent.events import Event
from rcm_agent.matrix import PHASES, ClaimMatrix


def replay(runs_dir: Path) -> Iterator[dict[str, Any]]:
    """Every event every run recorded, oldest run first, each with its state.

    Run directories are named for the moment they started, so sorting by name is
    chronological. A missing directory is an empty queue rather than an error:
    the console is often opened before anything has been run.
    """
    if not runs_dir.is_dir():
        return

    for run in sorted(runs_dir.iterdir()):
        log = run / "events.ndjson"
        if not run.is_dir() or not log.is_file():
            continue
        yield from _replay_one(run.name, log)


def _replay_one(run_id: str, log: Path) -> Iterator[dict[str, Any]]:
    # The whole log is held before any of it is sent, because `ClaimMatrix` is a
    # grid and wants its rows before it can be filled - the claim ids have to be
    # known up front. A run's log is a few kilobytes, so the memory is nothing,
    # but the shape is worth naming: this cannot stream a log as it is written,
    # and a tail that follows a live run will need the matrix to accept a claim
    # it has not seen before rather than being handed them all in advance.
    recorded = [_parsed(line) for line in log.read_text(encoding="utf-8").splitlines() if line]
    usable = [raw for raw in recorded if raw is not None]

    matrix = ClaimMatrix(list(dict.fromkeys(r["claim_id"] for r in usable if r["claim_id"])))
    # What each claim's Determination said, once it has one. Carried forward so
    # that *every* event for a claim describes it completely, and a client can
    # take the latest one wholesale instead of merging fields across events -
    # which is how a Determination ends up attributed to a run that never made
    # one.
    decided: dict[str, dict[str, Any]] = {}

    for raw in usable:
        event = Event(**raw)
        matrix.handle(event)
        if event.kind == "determination" and event.claim_id:
            decided[event.claim_id] = {
                "guardrail": event.detail.get("guardrail"),
                "priority": event.detail.get("priority"),
            }
        yield {"run_id": run_id, **raw, "derived": _derived(matrix, event, decided)}


def _parsed(line: str) -> dict[str, Any] | None:
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
    return raw


def _derived(
    matrix: ClaimMatrix, event: Event, decided: dict[str, dict[str, Any]]
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
            "guardrail": None,
            "guardrailed": False,
            "priority": None,
        }

    determination = decided.get(event.claim_id, {})
    guardrail = determination.get("guardrail")
    priority = determination.get("priority")

    return {
        "cells": {phase: matrix.cell(event.claim_id, phase) for phase in PHASES},
        "action": matrix.action_for(event.claim_id),
        "guardrail": guardrail,
        # The same test `Determination.was_guardrailed` makes, made here so the
        # browser is told the answer instead of working it out.
        "guardrailed": guardrail is not None,
        "priority": priority,
    }
