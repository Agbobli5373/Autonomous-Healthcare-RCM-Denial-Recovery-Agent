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
    recorded = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]

    # The matrix is a grid, so it needs its rows before it can be filled. Read
    # once for the claim ids, in the order they first appear, then again for
    # real - a run's log is a few kilobytes and this keeps the alternative
    # (mutating the grid as unknown claims arrive) out of the matrix.
    matrix = ClaimMatrix(list(dict.fromkeys(r["claim_id"] for r in recorded if r["claim_id"])))

    for raw in recorded:
        event = Event(**raw)
        matrix.handle(event)
        yield {"run_id": run_id, **raw, "derived": _derived(matrix, event)}


def _derived(matrix: ClaimMatrix, event: Event) -> dict[str, Any]:
    """What this event did to the claim it belongs to.

    `None` for a run-level event - provisioning a sandbox belongs to the run, not
    to any one claim, and inventing a claim for it would put a row in the queue
    that answers to nobody.
    """
    if event.claim_id is None:
        return {"cells": None, "action": None}
    return {
        "cells": {phase: matrix.cell(event.claim_id, phase) for phase in PHASES},
        "action": matrix.action_for(event.claim_id),
    }
