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

from rcm_agent.claim_io import claim_from_dict
from rcm_agent.determination import governing_denial
from rcm_agent.events import Event
from rcm_agent.matrix import PHASES, ClaimMatrix
from rcm_agent.strict_json import RecordFileError


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
    refused: dict[str, dict[str, Any]] = {}

    for raw in usable:
        event = Event(**raw)
        matrix.handle(event)
        if event.kind == "claim" and event.claim_id:
            refused[event.claim_id] = _refusal(dict(event.detail))
        if event.kind == "determination" and event.claim_id:
            decided[event.claim_id] = dict(event.detail)
        yield {"run_id": run_id, **raw, "derived": _derived(matrix, event, decided, refused)}


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
        # The same test `Determination.was_guardrailed` makes, made here so the
        # browser is told the answer instead of working it out.
        "guardrailed": determination is not None and determination.get("guardrail") is not None,
        # The payer's refusal, so the console can show it beside the
        # Determination rather than presenting a conclusion alone.
        "claim": refused.get(event.claim_id),
    }
