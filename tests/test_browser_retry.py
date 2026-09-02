"""The retry policy, at the seam where it can be tested without a browser.

Two properties matter more than the mechanics and are easy to get wrong:

* **A retry is recorded but not returned.** A tool that quietly retried three
  times must not look identical in the record to one that worked first time —
  and must not force every caller to care either.
* **The wall-clock cap is real.** Three attempts with backoff is a bound on
  count, not on time; a call that hangs would sit past both without it.

Time is injected rather than slept through. A test that actually waits 750ms is
a test people stop running.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import pytest

from rcm_agent.browser.retry import (
    MechanicalFailure,
    RetriesExhausted,
    RetryPolicy,
    with_retries,
)
from rcm_agent.events import Event, EventStream


class Recorder:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def handle(self, event: Event) -> None:
        self.events.append(event)


class FakeClock:
    """Monotonic time that only moves when something sleeps, or runs.

    `wait_for` is part of this rather than a separate fake because the cap is
    about elapsed time: bounding an attempt and advancing the clock are the same
    event, and splitting them let an earlier version of these tests "prove" a cap
    while finishing five seconds past it.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []
        self.budgets: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    async def wait_for(self, awaitable: Any, timeout: float) -> Any:
        """Run the attempt, cut off at its deadline the way asyncio would.

        The clock is wound *back* to the deadline on a timeout, because that is
        what really happens: `asyncio.wait_for` cancels the operation when the
        budget runs out, so the call cannot have taken longer than the budget.
        A fake that let the operation finish first and complained afterwards
        would report elapsed times no real caller could ever see.
        """
        self.budgets.append(timeout)
        deadline = self.now + timeout
        try:
            result = await awaitable
        except BaseException:
            if self.now > deadline:
                self.now = deadline
                raise TimeoutError(f"cancelled at its {timeout}s budget") from None
            raise
        if self.now > deadline:
            self.now = deadline
            raise TimeoutError(f"cancelled at its {timeout}s budget")
        return result


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
def stream(recorder: Recorder) -> EventStream:
    stream = EventStream()
    stream.add_sink(recorder)
    return stream


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


# --- the happy path leaves no trace ----------------------------------------


def test_an_operation_that_works_first_time_records_no_retry(
    stream: EventStream, recorder: Recorder
) -> None:
    async def works() -> str:
        return "done"

    clock = FakeClock()
    result = run(
        with_retries(
            works,
            tool="open_claim",
            stream=stream,
            clock=clock,
            sleep=clock.sleep,
            wait_for=clock.wait_for,
        )
    )

    assert result == "done"
    assert [e for e in recorder.events if e.kind == "retry"] == []
    assert clock.slept == []


# --- retries are recorded, and only recorded -------------------------------


def test_a_retried_call_still_returns_the_plain_result(
    stream: EventStream, recorder: Recorder
) -> None:
    """The attempt count is in the record, not in the caller's hands.

    Returning it would make every caller decide what to do about it, which is
    exactly the coupling the split between mechanical and semantic avoids.
    """
    attempts = {"n": 0}

    async def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise MechanicalFailure("element not there yet")
        return "opened"

    clock = FakeClock()
    result = run(
        with_retries(
            flaky,
            tool="open_claim",
            stream=stream,
            clock=clock,
            sleep=clock.sleep,
            wait_for=clock.wait_for,
        )
    )

    assert result == "opened"
    assert not isinstance(result, tuple), "the attempt count must not ride along"


def test_each_retry_is_an_event_carrying_its_attempt_number(
    stream: EventStream, recorder: Recorder
) -> None:
    attempts = {"n": 0}

    async def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise MechanicalFailure("click did not register")
        return "ok"

    clock = FakeClock()
    run(
        with_retries(
            flaky,
            tool="open_claim",
            stream=stream,
            clock=clock,
            sleep=clock.sleep,
            wait_for=clock.wait_for,
        )
    )

    retries = [e for e in recorder.events if e.kind == "retry"]
    assert [e.detail["attempt"] for e in retries] == [1, 2]
    assert all(e.tool == "open_claim" for e in retries)
    assert all("did not register" in str(e.detail["error"]) for e in retries)


def test_a_retry_is_not_recorded_as_an_error(stream: EventStream, recorder: Recorder) -> None:
    """It is not a failure. Something that succeeded on the second go worked."""
    attempts = {"n": 0}

    async def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise MechanicalFailure("blip")
        return "ok"

    clock = FakeClock()
    run(
        with_retries(
            flaky,
            tool="log_in",
            stream=stream,
            clock=clock,
            sleep=clock.sleep,
            wait_for=clock.wait_for,
        )
    )

    assert [e for e in recorder.events if e.kind == "error"] == []


# --- the bounds ------------------------------------------------------------


def test_the_backoff_is_the_stated_one(stream: EventStream) -> None:
    """250ms then 500ms. Written down because a demo has a running clock."""

    async def always_fails() -> str:
        raise MechanicalFailure("nope")

    clock = FakeClock()
    with pytest.raises(RetriesExhausted):
        run(
            with_retries(
                always_fails,
                tool="open_claim",
                stream=stream,
                clock=clock,
                sleep=clock.sleep,
                wait_for=clock.wait_for,
            )
        )

    assert clock.slept == [0.25, 0.5]


def test_it_stops_after_the_stated_number_of_attempts(stream: EventStream) -> None:
    calls = {"n": 0}

    async def always_fails() -> str:
        calls["n"] += 1
        raise MechanicalFailure("nope")

    clock = FakeClock()
    with pytest.raises(RetriesExhausted):
        run(
            with_retries(
                always_fails,
                tool="open_claim",
                stream=stream,
                clock=clock,
                sleep=clock.sleep,
                wait_for=clock.wait_for,
            )
        )

    assert calls["n"] == RetryPolicy().attempts == 3


def test_the_default_cap_exceeds_the_policy_own_worst_case() -> None:
    """A cap smaller than what the policy can spend is not a cap at all.

    It shipped that way: three attempts at a five-second action timeout plus
    0.75s of backoff is 15.75s, against a cap of 15. A tool behaving exactly as
    designed would have been cut off for it.
    """
    rules = RetryPolicy()
    worst_case = rules.attempts * (rules.action_timeout_ms / 1000) + sum(rules.backoff_seconds)

    assert rules.wall_clock_cap > worst_case, f"{rules.wall_clock_cap}s cannot cover {worst_case}s"


def test_the_whole_call_finishes_inside_the_wall_clock_cap(stream: EventStream) -> None:
    """The cap is a bound on *elapsed time*, and this asserts the elapsed time.

    The version of this test that shipped first asserted only that a second
    attempt never happened. It passed against an implementation whose call
    finished at t=20s under a 15s cap, because nothing ever looked at the clock
    after the attempt — which is precisely the bug it was written to catch.
    """
    clock = FakeClock()
    cap = 15.0

    async def slow() -> str:
        clock.now += 20.0
        raise MechanicalFailure("timed out")

    with pytest.raises(RetriesExhausted):
        run(
            with_retries(
                slow,
                tool="search_claims",
                stream=stream,
                policy=RetryPolicy(wall_clock_cap=cap),
                clock=clock,
                sleep=clock.sleep,
                wait_for=clock.wait_for,
            )
        )

    assert clock.now <= cap, f"the call ran {clock.now}s under a {cap}s cap"


def test_an_attempt_that_overruns_is_cut_off_rather_than_waited_out(
    stream: EventStream,
) -> None:
    """Each attempt runs under what is left of the budget, not under its own.

    Without this the cap bounds only the gaps between attempts, and a single
    call that never returns outlives every check around it.
    """
    clock = FakeClock()

    async def hangs() -> str:
        clock.now += 100.0
        return "far too late"

    with pytest.raises(RetriesExhausted):
        run(
            with_retries(
                hangs,
                tool="download_eob",
                stream=stream,
                policy=RetryPolicy(wall_clock_cap=10.0),
                clock=clock,
                sleep=clock.sleep,
                wait_for=clock.wait_for,
            )
        )

    assert clock.budgets[0] == 10.0, "the first attempt was not given the whole budget"
    assert all(b <= 10.0 for b in clock.budgets), clock.budgets


def test_each_attempt_is_given_only_what_is_left(stream: EventStream) -> None:
    """The budget shrinks as the call goes on, or three attempts could take 3x the cap."""
    clock = FakeClock()

    async def slow_ish() -> str:
        clock.now += 2.0
        raise MechanicalFailure("not yet")

    with pytest.raises(RetriesExhausted):
        run(
            with_retries(
                slow_ish,
                tool="open_claim",
                stream=stream,
                policy=RetryPolicy(wall_clock_cap=30.0),
                clock=clock,
                sleep=clock.sleep,
                wait_for=clock.wait_for,
            )
        )

    assert clock.budgets == sorted(clock.budgets, reverse=True), clock.budgets
    assert clock.budgets[-1] < clock.budgets[0]


def test_exhausting_the_retries_names_the_tool_and_the_last_error(stream: EventStream) -> None:
    async def always_fails() -> str:
        raise MechanicalFailure("the frame detached")

    clock = FakeClock()
    with pytest.raises(RetriesExhausted, match="search_claims") as caught:
        run(
            with_retries(
                always_fails,
                tool="search_claims",
                stream=stream,
                clock=clock,
                sleep=clock.sleep,
                wait_for=clock.wait_for,
            )
        )

    assert "frame detached" in str(caught.value)


# --- what counts as mechanical ---------------------------------------------


def test_an_unexpected_error_is_not_retried(stream: EventStream, recorder: Recorder) -> None:
    """Retrying a bug just runs it three times.

    Only failures with a plausible second outcome are mechanical. A TypeError is
    not one, and hiding it behind two more attempts would make it harder to find.
    """
    calls = {"n": 0}

    async def broken() -> str:
        calls["n"] += 1
        raise TypeError("this is a bug, not a blip")

    clock = FakeClock()
    with pytest.raises(TypeError):
        run(
            with_retries(
                broken,
                tool="open_claim",
                stream=stream,
                clock=clock,
                sleep=clock.sleep,
                wait_for=clock.wait_for,
            )
        )

    assert calls["n"] == 1
    assert [e for e in recorder.events if e.kind == "retry"] == []
