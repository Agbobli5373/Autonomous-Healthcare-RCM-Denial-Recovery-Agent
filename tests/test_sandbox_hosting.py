"""Teardown, without waiting on a real sandbox.

The live check is worth doing and was done, but it costs a minute and it needs
the Free tier's only slot to be free. This pins the ordering that check verifies,
so a later edit that moves the `try` cannot quietly reintroduce the leak.

The failure being pinned is specific: if the `try` opens *after* the servers are
started, a failure part-way through starting them skips the stop entirely. The
sandbox dying would cover it in practice, which is exactly why the mistake would
survive review — the requirement is that teardown does not depend on that.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from typing import Any

import pytest

from rcm_agent import sandbox_hosting
from rcm_agent.events import Event, EventStream
from rcm_agent.sandbox import HostedMock, ServerStartupError
from rcm_agent.sandbox_hosting import hosted_mocks

MOCKS = (
    HostedMock("payer-portal", 8080, "https://example-8080.preview.getsolari.com?pt_token=abc"),
    HostedMock(
        "practice-management", 8081, "https://example-8081.preview.getsolari.com?pt_token=d"
    ),
)


class FakeSandbox:
    """Records what the orchestrator asked it to do, and can fail on demand."""

    def __init__(self, *, fail_on_start: bool = False) -> None:
        self.calls: list[str] = []
        self._fail_on_start = fail_on_start

    async def upload_working_copy(self, repo_root: object) -> int:
        self.calls.append("upload")
        return 42

    async def install_web_packages(self) -> None:
        self.calls.append("install")

    async def start_mock_servers(self) -> tuple[HostedMock, ...]:
        self.calls.append("start")
        if self._fail_on_start:
            raise ServerStartupError("uvicorn died")
        return MOCKS

    async def stop_mock_servers(self) -> tuple[int, ...]:
        self.calls.append("stop")
        return (101, 102)


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[Event]:
    monkeypatch.setenv("SOLARI_API_KEY", "slr_live_not_a_real_key_for_tests")
    return []


def run_hosting(
    sandbox: FakeSandbox, monkeypatch: pytest.MonkeyPatch, events: list[Event], body: Any
) -> None:
    @contextlib.asynccontextmanager
    async def fake_session(api_key: str) -> AsyncGenerator[FakeSandbox]:
        yield sandbox

    monkeypatch.setattr(sandbox_hosting, "sandbox_session", fake_session)
    stream = EventStream()
    stream.add_sink(_Collector(events))

    async def main() -> None:
        async with hosted_mocks(stream) as hosting:
            await body(hosting)

    asyncio.run(main())


class _Collector:
    def __init__(self, into: list[Event]) -> None:
        self._into = into

    def handle(self, event: Event) -> None:
        self._into.append(event)


def test_the_servers_are_stopped_on_the_happy_path(
    monkeypatch: pytest.MonkeyPatch, recorded: list[Event]
) -> None:
    sandbox = FakeSandbox()

    async def body(hosting: sandbox_hosting.Hosting) -> None:
        assert hosting.mocks == MOCKS

    run_hosting(sandbox, monkeypatch, recorded, body)

    assert sandbox.calls == ["upload", "install", "start", "stop"]


def test_the_servers_are_stopped_when_the_body_raises(
    monkeypatch: pytest.MonkeyPatch, recorded: list[Event]
) -> None:
    sandbox = FakeSandbox()

    async def body(hosting: sandbox_hosting.Hosting) -> None:
        raise RuntimeError("the run failed while the mocks were up")

    with pytest.raises(RuntimeError):
        run_hosting(sandbox, monkeypatch, recorded, body)

    assert sandbox.calls[-1] == "stop"


def test_the_servers_are_stopped_when_starting_them_fails(
    monkeypatch: pytest.MonkeyPatch, recorded: list[Event]
) -> None:
    """The one the `try` placement decides. See this module's docstring."""
    sandbox = FakeSandbox(fail_on_start=True)

    async def body(hosting: sandbox_hosting.Hosting) -> None:  # pragma: no cover - never reached
        raise AssertionError("the block should not have been entered")

    with pytest.raises(ServerStartupError):
        run_hosting(sandbox, monkeypatch, recorded, body)

    assert "stop" in sandbox.calls, "a failure while starting skipped the teardown"


def test_no_access_token_reaches_the_recorded_events(
    monkeypatch: pytest.MonkeyPatch, recorded: list[Event]
) -> None:
    """The run directory is committed evidence. A live token must not be in it."""
    import json

    async def body(hosting: sandbox_hosting.Hosting) -> None:
        return None

    run_hosting(FakeSandbox(), monkeypatch, recorded, body)

    assert recorded, "the hosting emitted nothing at all"
    assert "pt_token" not in json.dumps([event.to_dict() for event in recorded])


def test_the_api_key_is_recorded_only_as_a_fingerprint(
    monkeypatch: pytest.MonkeyPatch, recorded: list[Event]
) -> None:
    import json

    async def body(hosting: sandbox_hosting.Hosting) -> None:
        return None

    run_hosting(FakeSandbox(), monkeypatch, recorded, body)

    dumped = json.dumps([event.to_dict() for event in recorded])
    assert "slr_live_not_a_real_key_for_tests" not in dumped
    assert "slr_live" in dumped, "the fingerprint should still tell two keys apart"
