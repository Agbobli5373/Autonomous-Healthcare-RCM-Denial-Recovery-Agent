"""The claim matrix: three claims moving through five phases.

This is the state behind the panel's top half, kept separate from Rich so it can
be tested without rendering anything.

Its job is to make the run's *shape* visible. A claim going `na` on emr and
appeal is the agent refusing to appeal an unappealable denial — the hardest
thing this project has to communicate, shown rather than asserted. So `na` is a
distinct state from `pending`, not a cosmetic variant of it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Literal

from rcm_agent.events import Event, Phase

PHASES: tuple[Phase, ...] = ("portal", "analysis", "emr", "appeal", "report")

CellState = Literal["pending", "running", "done", "na", "failed"]

_EVIDENCE_GATHERING_PHASES: tuple[Phase, ...] = ("emr", "appeal")
"""Phases that exist to build an Appeal Package."""

_ACTIONS_NEEDING_EVIDENCE: frozenset[str] = frozenset({"appeal"})
"""Actions whose Determination requires the Authorization record.

Named as a set of Actions rather than as "not appeal", because ADR-0002 exists
precisely to stop this collapsing back into a binary. When `corrected claim`
grows an evidence requirement it joins the set; nothing else has to change.
"""


class ClaimMatrix:
    """An event sink holding one cell per claim per phase, plus what was decided."""

    def __init__(self, claim_ids: Sequence[str]) -> None:
        self.claim_ids = list(claim_ids)
        self._cells: dict[tuple[str, Phase], CellState] = {
            (claim_id, phase): "pending" for claim_id in self.claim_ids for phase in PHASES
        }
        self._actions: dict[str, str] = {}

    def cell(self, claim_id: str, phase: Phase) -> CellState:
        return self._cells[(claim_id, phase)]

    def action_for(self, claim_id: str) -> str | None:
        return self._actions.get(claim_id)

    def summary(self) -> dict[str, int]:
        """Counts by Action, derived from the stream rather than asserted.

        The panel's closing frame and `run.json` both read this, so neither can
        claim an outcome the events did not record.
        """
        return dict(Counter(self._actions.values()))

    def handle(self, event: Event) -> None:
        claim_id = event.claim_id
        if claim_id is None or claim_id not in self.claim_ids:
            # Run-level events, and anything about a claim we are not tracking,
            # belong in the tail rather than the matrix.
            return

        match event.kind:
            case "phase_start":
                self._set(claim_id, event.phase, "running")
            case "phase_end":
                self._set(claim_id, event.phase, "failed" if event.outcome == "failed" else "done")
            case "error":
                self._set(claim_id, event.phase, "failed")
            case "determination":
                self._apply_determination(claim_id, event)
            case _:
                # tool_call, tool_result and recovery all happen *within* a
                # phase. A recovery in particular must never mark a cell failed:
                # the agent handled it, and the matrix says so by leaving the
                # cell running.
                pass

    def _apply_determination(self, claim_id: str, event: Event) -> None:
        action = event.detail.get("action")
        if not isinstance(action, str):
            return
        self._actions[claim_id] = action
        if action in _ACTIONS_NEEDING_EVIDENCE:
            return
        for phase in _EVIDENCE_GATHERING_PHASES:
            if self._cells[(claim_id, phase)] == "pending":
                self._set(claim_id, phase, "na")

    def _set(self, claim_id: str, phase: Phase, state: CellState) -> None:
        self._cells[(claim_id, phase)] = state
