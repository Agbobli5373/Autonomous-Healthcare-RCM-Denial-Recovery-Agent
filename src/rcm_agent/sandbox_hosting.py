"""Bringing the mocks up inside a sandbox, and taking them down again.

No tunnel, no PaaS, no deploy step: the sandbox serves the ports and
`preview_url` makes each one publicly reachable, so a Solari cloud browser can
load them the way it would load any site. The whole arrangement lives and dies
with the run.

**Order is the contract.** Upload, install, start, *health-check inside the
guest*, and only then ask for a preview URL. `hosting.start_script` explains why
the health check belongs in the guest; this module's job is to keep the order and
to make sure the teardown runs whatever happens.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path

from rcm_agent.config import credential, fingerprint
from rcm_agent.events import EventStream
from rcm_agent.sandbox import HostedMock, Sandbox, sandbox_session

REPO_ROOT = Path(__file__).resolve().parents[2]
"""The working copy. `src/rcm_agent/sandbox_hosting.py` -> up three."""


@dataclass(frozen=True, slots=True)
class Hosting:
    """Both mocks, live, with the sandbox still open for the analysis kernel."""

    sandbox: Sandbox
    mocks: tuple[HostedMock, ...]


KEEPALIVE_SECONDS = 120.0
"""How often to touch the guest while nothing else is happening.

`SANDBOX_TTL_MS` is a rolling idle window, so a command whose job is to hold the
mocks up would let them expire underneath itself by doing nothing. Comfortably
inside the ten minutes rather than close to it, because the cost of being early
is one cheap call.
"""


async def keep_alive(sandbox: Sandbox, *, every: float = KEEPALIVE_SECONDS) -> None:
    """Touch the guest forever, so an idle host does not lose its own sandbox."""
    while True:
        await asyncio.sleep(every)
        await sandbox.run("pass")


@contextlib.asynccontextmanager
async def hosted_mocks(
    stream: EventStream, *, repo_root: Path = REPO_ROOT
) -> AsyncGenerator[Hosting]:
    """Serve both mocks from one sandbox for the duration of the block.

    The sandbox is yielded alongside them rather than hidden, because the caller
    needs the same guest for the analysis kernel and creating a second one is not
    an option on this tier.
    """
    api_key = credential("SOLARI_API_KEY")
    stream.emit(
        phase="setup",
        kind="phase_start",
        detail={"key": fingerprint(api_key)},
    )

    async with sandbox_session(api_key) as sandbox:
        # The `try` opens before the servers are started, not after. A failure
        # part-way through starting them would otherwise skip the stop entirely
        # — the sandbox dying would cover it, but teardown should not depend on
        # that, and "including on failure paths" is the requirement.
        try:
            stream.emit(phase="setup", kind="tool_call", tool="upload_working_copy")
            files = await sandbox.upload_working_copy(repo_root)
            stream.emit(
                phase="setup",
                kind="tool_result",
                tool="upload_working_copy",
                outcome="ok",
                detail={"files": files},
            )

            stream.emit(phase="setup", kind="tool_call", tool="install_web_packages")
            await sandbox.install_web_packages()

            stream.emit(phase="setup", kind="tool_call", tool="start_mock_servers")
            mocks = await sandbox.start_mock_servers()
            for mock in mocks:
                stream.emit(
                    phase="setup",
                    kind="tool_result",
                    tool="start_mock_servers",
                    outcome="ok",
                    detail=mock.as_event_detail(),
                )

            yield Hosting(sandbox=sandbox, mocks=mocks)
        finally:
            # Killing the sandbox would take the servers with it. Stopping them
            # explicitly means teardown does not depend on that, and it runs on
            # the failure path too - this `finally` is inside the session's own.
            with contextlib.suppress(Exception):
                stopped = await sandbox.stop_mock_servers()
                stream.emit(
                    phase="setup",
                    kind="tool_result",
                    tool="stop_mock_servers",
                    outcome="ok",
                    detail={"stopped": list(stopped)},
                )
            stream.emit(phase="setup", kind="phase_end", outcome="ok")
