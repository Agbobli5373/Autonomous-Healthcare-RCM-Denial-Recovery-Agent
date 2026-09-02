"""Which model runs the loop, and how hard it thinks.

One place, so escalating a step to Opus 5 is a configuration change rather than a
rewrite. `Escalation` names *why* a step would be escalated, not just what to;
"use the bigger model here" is a decision someone should be able to read a reason
for six months from now.

**Sonnet 5 for the browser leg.** The work is choosing among four tools on a page
whose state the tools already describe in words — that is not where the harder
model earns its keep, and the loop runs several times per claim. The judgement
that actually wants Opus is the Determination, which is a different phase and
does not run here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Effort = Literal["low", "medium", "high", "xhigh", "max"]


@dataclass(frozen=True, slots=True)
class Escalation:
    """A model, an effort level, and the reason this step is worth them."""

    model: str
    effort: Effort
    because: str

    max_tokens: int = 16_000
    """Not lowballed. A truncated turn costs a whole extra round trip, and the
    assistant turns here are short anyway — this is a ceiling, not a spend."""


NAVIGATION = Escalation(
    model="claude-sonnet-5",
    effort="low",
    because=(
        "picking one of four tools from outcomes the tools already state in words. "
        "Low effort means fewer, more consolidated tool calls, which is what a "
        "navigation loop wants"
    ),
)
"""The default. Chosen in the ticket, and it is the cheap half of the work."""

HARD_JUDGEMENT = Escalation(
    model="claude-opus-5",
    effort="high",
    because="reserved for a step where being wrong is expensive rather than slow",
)
"""Unused today, and deliberately present.

The ticket asks that escalating a single step be configuration rather than a
rewrite. This is the configuration: pass it to the loop instead of `NAVIGATION`.
Keeping it named and reasoned means the next person escalates on purpose.
"""
