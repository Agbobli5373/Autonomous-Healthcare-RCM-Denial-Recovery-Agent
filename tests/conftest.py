"""Shared fixtures for the tests that need a real portal and a real browser.

Both the tool tests and the agent-loop tests want the same thing: the mock payer
portal actually served, with its actual XHR latency and its actual deliberate
session expiry. Serving it once per module and sharing it here keeps the two
suites from each keeping their own copy of a uvicorn thread — and from drifting
about whether the latency should be turned down. It should not: the latency is
what makes waiting on a condition rather than sleeping mean anything.
"""

from __future__ import annotations

import importlib.util
import socket
import threading
from collections.abc import Iterator
from contextlib import closing

import pytest
import uvicorn

from rcm_agent.mocks.portal import create_app
from rcm_agent.mocks.practice_management import create_app as create_practice_app

PORTAL_USER = "provider"
PORTAL_PASSWORD = "demo"
"""The mock accepts anything. Spelled out so the type checker can see each tool
is called with what it declares, rather than splatted from a dict."""

HERO_CLAIM = "CLM-2026-0001"
"""The CO-197 prior-authorization claim. Oldest of three, so it is on page two."""


def free_port() -> int:
    with closing(socket.socket()) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def chromium_is_available() -> bool:
    """Skip rather than fail where the browser was never installed.

    The suite has to stay runnable on a machine that has not downloaded a
    hundred megabytes of Chromium, the same way the OCR test skips without
    tesseract.
    """
    return importlib.util.find_spec("patchright") is not None


needs_browser = pytest.mark.skipif(
    not chromium_is_available(), reason="patchright/chromium is not installed here"
)


def _serve(latency: float) -> Iterator[str]:
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(latency=latency), host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        threading.Event().wait(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="module")
def portal_url() -> Iterator[str]:
    """A real server, with the mock's real 1.2s worklist latency.

    Shared across a module, which is fine for tests that do not depend on the
    session expiry. Anything that does needs `fresh_portal` instead.
    """
    yield from _serve(1.2)


@pytest.fixture
def fresh_portal() -> Iterator[str]:
    """A portal of its own, for one test.

    **The mock expires a session exactly once per process, deliberately.** A
    shared server therefore hands that expiry to whichever test runs first and to
    none of the others - which quietly turned every later recovery assertion into
    a test of nothing. It cost six failing tests to notice, and the failure mode
    was the tests passing individually.

    Latency is zero: these tests are about which tool the agent chooses, and
    waiting on the XHR condition rather than sleeping is covered where it belongs,
    in the tool tests.
    """
    yield from _serve(0.0)


def _serve_practice() -> Iterator[str]:
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_practice_app(), host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        threading.Event().wait(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def practice_url() -> Iterator[str]:
    """The practice-management system, one per test.

    Per test rather than per module because chart notes are held in memory: a
    shared server would let one test's note be visible to the next, and a
    write-back test that passes because of an earlier test's write is testing
    nothing.
    """
    yield from _serve_practice()
