from __future__ import annotations

from datetime import UTC, datetime

from rcm_agent.events import Event, EventStream


class Recorder:
    """Minimal EventSink that keeps what it was handed."""

    def __init__(self) -> None:
        self.seen: list[Event] = []

    def handle(self, event: Event) -> None:
        self.seen.append(event)


def fixed_clock() -> datetime:
    return datetime(2026, 9, 1, 14, 22, 3, tzinfo=UTC)


def test_seq_starts_at_one_and_increments() -> None:
    stream = EventStream(clock=fixed_clock)

    first = stream.emit(phase="portal", kind="phase_start")
    second = stream.emit(phase="portal", kind="phase_end", outcome="ok")

    assert first.seq == 1
    assert second.seq == 2


def test_timestamp_comes_from_the_clock() -> None:
    stream = EventStream(clock=fixed_clock)

    event = stream.emit(phase="analysis", kind="phase_start")

    assert event.ts == "2026-09-01T14:22:03+00:00"


def test_sinks_receive_events_in_order() -> None:
    stream = EventStream(clock=fixed_clock)
    recorder = Recorder()
    stream.add_sink(recorder)

    stream.emit(phase="portal", kind="phase_start")
    stream.emit(phase="portal", kind="tool_call", tool="log_in")

    assert [e.seq for e in recorder.seen] == [1, 2]
    assert recorder.seen[1].tool == "log_in"


def test_every_sink_sees_every_event() -> None:
    stream = EventStream(clock=fixed_clock)
    one, two = Recorder(), Recorder()
    stream.add_sink(one)
    stream.add_sink(two)

    stream.emit(phase="report", kind="phase_start")

    assert len(one.seen) == 1
    assert len(two.seen) == 1


def test_to_dict_carries_the_full_shape() -> None:
    stream = EventStream(clock=fixed_clock)

    event = stream.emit(
        phase="portal",
        kind="tool_result",
        tool="open_claim",
        claim_id="CLM-0001",
        outcome="ok",
        screenshot="screenshots/0042-portal-open_claim.png",
        detail={"attempts": 2},
    )

    assert event.to_dict() == {
        "seq": 1,
        "ts": "2026-09-01T14:22:03+00:00",
        "phase": "portal",
        "kind": "tool_result",
        "tool": "open_claim",
        "claim_id": "CLM-0001",
        "outcome": "ok",
        "screenshot": "screenshots/0042-portal-open_claim.png",
        "detail": {"attempts": 2},
    }


def test_optional_fields_default_to_none_and_empty_detail() -> None:
    stream = EventStream(clock=fixed_clock)

    event = stream.emit(phase="emr", kind="phase_start")

    assert event.tool is None
    assert event.claim_id is None
    assert event.outcome is None
    assert event.screenshot is None
    assert event.detail == {}


def test_a_failing_sink_does_not_stop_other_sinks() -> None:
    """The audit log must still receive an event if the panel blows up."""

    class Exploding:
        def handle(self, event: Event) -> None:
            raise RuntimeError("boom")

    stream = EventStream(clock=fixed_clock)
    recorder = Recorder()
    stream.add_sink(Exploding())
    stream.add_sink(recorder)

    stream.emit(phase="portal", kind="phase_start")

    assert len(recorder.seen) == 1
