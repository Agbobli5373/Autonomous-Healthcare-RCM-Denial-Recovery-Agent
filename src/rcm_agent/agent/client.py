"""Where the Anthropic key is read, and the only place it is.

**Orchestrator-side, always.** The key is read in this process, handed to the SDK
in this process, and used to make calls from this process. It is not uploaded, is
not written into a guest script, and does not appear in any artifact — the run
records a fingerprint and nothing more, the same rule the Solari key follows.

That is not only hygiene. The sandbox serves the mocks and runs the analysis
kernel, and it is reachable from the public internet through a preview URL for as
long as the demo lasts. A model key in there would be a credential on a public
host, which is the kind of thing this project exists to be careful about.
"""

from __future__ import annotations

from typing import cast

from rcm_agent.agent.loop import ModelClient
from rcm_agent.config import credential, fingerprint
from rcm_agent.events import EventStream

ANTHROPIC_KEY = "ANTHROPIC_API_KEY"
"""Read from the environment or the gitignored `.env`, like the Solari key."""


def planning_client(stream: EventStream) -> ModelClient:
    """An async Anthropic client, with the key recorded only as a fingerprint.

    The key is passed explicitly rather than left to the SDK's own environment
    lookup, because this project keeps its credentials in a gitignored `.env`
    that nothing exports — and a client that silently found no key would fail
    later, mid-run, looking like a model problem.
    """
    from anthropic import AsyncAnthropic

    key = credential(ANTHROPIC_KEY)
    stream.emit(
        phase="portal",
        kind="tool_call",
        tool="open_planner",
        detail={"key": fingerprint(key)},
    )
    # Cast rather than a plain annotation: the SDK spells `create` with named
    # parameters and overloads, which is narrower than the `**kwargs` shape the
    # loop needs, so the two are compatible in use but not structurally. The
    # Protocol still earns its place - it is what the loop is checked against,
    # and what the tests substitute.
    return cast("ModelClient", AsyncAnthropic(api_key=key).messages)
