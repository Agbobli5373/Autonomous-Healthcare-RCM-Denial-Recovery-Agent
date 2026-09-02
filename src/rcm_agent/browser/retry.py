"""Retrying the mechanical, and only the mechanical.

The split this module exists to enforce: **a failure is either mechanical or
semantic, and they are handled in opposite ways.**

A *mechanical* failure is one where doing the same thing again plausibly works —
the element has not rendered yet, a click landed before the handler was bound, a
socket blipped. Those are retried here, inside the tool, and the caller never
learns it happened. A *semantic* failure is the page telling you something true:
the claim is not in this queue, the session expired, the login was refused.
Retrying those just asks the same question again and gets the same answer, so
they never reach this module — the tools return them as results.

Retries are **recorded but not returned**. A tool that quietly retried three
times must not look identical in the record to one that worked first time, which
is why every attempt is an event; but making the count part of the return value
would push the decision onto every caller, and the point of the split is that
callers do not have to make it.

**The wall-clock cap is separate from the attempt count** on purpose. Three
attempts bounds how many times something is tried, not how long it takes, and an
operation that hangs would sit well past both. The demo has a running clock and
the worst case has to be a number that can be planned around.

It is enforced by *running each attempt under the remaining budget*, not by
checking the time between them. An earlier version only looked at the clock
before sleeping, which bounded nothing: an attempt that took a minute was never
interrupted, the per-action timeouts summed past the cap, and the test that
claimed to prove otherwise asserted the attempt count rather than the elapsed
time — so it passed while finishing five seconds late.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from rcm_agent.events import EventStream, Phase

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]
WaitFor = Callable[[Awaitable[Any], float], Awaitable[Any]]
"""How an attempt is bounded. `asyncio.wait_for` in production, a fake in tests."""


class MechanicalFailure(RuntimeError):
    """Something that would plausibly succeed on a second attempt.

    Raised by the tools when a locator, click or wait does not land. Never raised
    for anything the page is actually saying — that is a result, not a fault.
    """


class RetriesExhausted(RuntimeError):
    """Every attempt failed, or the wall-clock cap was reached first.

    Tools convert this into a structured result; it is not meant to escape to the
    orchestrator, which should never have to tell a flaky click from a real one.
    """


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """The bounds, written down rather than scattered through the tools."""

    attempts: int = 3
    backoff_seconds: tuple[float, ...] = (0.25, 0.5)
    """Roughly a quarter second, then a half. Short enough to be invisible on
    camera, long enough for a page that is a frame behind to catch up."""

    wall_clock_cap: float = 30.0
    """The longest a single tool call may take, retries and backoff included.

    Enforced, not hoped for: each attempt runs under whatever is left of it.

    Thirty rather than fifteen because fifteen was less than the policy's own
    worst case — three attempts at a five-second action timeout plus 0.75s of
    backoff is 15.75s — so the cap could be blown by a tool that was behaving
    exactly as designed.
    """

    action_timeout_ms: int = 5_000
    """How long one locator action may wait before it counts as mechanical.

    Here rather than as a module constant because it is the same kind of thing as
    the other three - a bound on how long the agent will keep trying - and
    because a test that wants a fast failure should not have to monkeypatch a
    constant to get one."""


async def with_retries[T](
    operation: Callable[[], Awaitable[T]],
    *,
    tool: str,
    stream: EventStream,
    phase: Phase = "portal",
    claim_id: str | None = None,
    policy: RetryPolicy | None = None,
    clock: Clock = time.monotonic,
    sleep: Sleep = asyncio.sleep,
    wait_for: WaitFor = asyncio.wait_for,
) -> T:
    """Run `operation`, retrying mechanical failures within the policy's bounds.

    `clock`, `sleep` and `wait_for` are injected so the policy can be tested
    without waiting for it. A test that really sleeps 750ms is a test people stop
    running, and one that really hangs for thirty seconds is worse.
    """
    rules = policy or RetryPolicy()
    deadline = clock() + rules.wall_clock_cap
    last: Exception | None = None

    for attempt in range(1, rules.attempts + 1):
        remaining = deadline - clock()
        if remaining <= 0:
            raise RetriesExhausted(
                f"{tool} hit its wall-clock cap of {rules.wall_clock_cap}s "
                f"after {attempt - 1} attempt(s): {last}"
            ) from last

        try:
            # The attempt itself is bounded. Without this the cap is a comment:
            # one call that never returns outlives every check around it.
            return cast(T, await wait_for(operation(), remaining))
        except TimeoutError as overran:
            last = MechanicalFailure(f"{tool} exceeded its remaining budget of {remaining:.1f}s")
            last.__cause__ = overran
        except MechanicalFailure as failure:
            last = failure

        if attempt == rules.attempts:
            break

        pause = rules.backoff_seconds[min(attempt - 1, len(rules.backoff_seconds) - 1)]
        if clock() + pause >= deadline:
            raise RetriesExhausted(
                f"{tool} hit its wall-clock cap of {rules.wall_clock_cap}s "
                f"after {attempt} attempt(s): {last}"
            ) from last

        # Recorded, not returned. `seq` joins this to the tool_call it belongs to
        # and to any screenshot taken around it.
        stream.emit(
            phase=phase,
            kind="retry",
            tool=tool,
            claim_id=claim_id,
            detail={"attempt": attempt, "of": rules.attempts, "error": str(last)},
        )
        await sleep(pause)

    raise RetriesExhausted(f"{tool} failed {rules.attempts} times; last error: {last}") from last
