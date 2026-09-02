"""The agent loop: the model chooses the tools, the orchestrator runs them.

This is what makes the browser leg an agent rather than a scraper. There is no
navigation sequence here — no "sign in, then search, then open". The loop hands
the model four tools and the outcomes they return, and the model decides what to
call and when it is finished.

**The recovery is the centrepiece, and it is split deliberately.** Detection is
tool-level and deterministic: `open_claim` notices it landed on the login page
and returns `session_expired`, which is a fact about the portal that no model
needs to infer. The *decision* is the model's: seeing that outcome, it chooses to
call `log_in` again and resume. This loop records that decision as a `recovery`
event when it happens — it does not cause it, and if the model chose to do
something else the record would say that instead.

That split is the whole point. Detection in a prompt would be unreliable; the
decision in code would make this a script.

**A written loop rather than the SDK's tool runner.** Every tool call here has to
emit events, be counted, and be watched for the recovery decision, and the loop
is short enough that owning it is cheaper than threading hooks through a helper.

**All model calls happen here, orchestrator-side.** The Anthropic key is read in
this process and never leaves it. The sandbox runs the mocks and the analysis
kernel and has no idea a model exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from rcm_agent.agent.model import NAVIGATION, Escalation
from rcm_agent.agent.surface import (
    SYSTEM_PROMPT,
    TOOL_NAMES,
    opening_message,
    tool_schemas,
)
from rcm_agent.browser.plumbing import ToolOutcome
from rcm_agent.browser.practice import read_auth_record, write_note
from rcm_agent.browser.tools import download_eob, log_in, open_claim, search_claims
from rcm_agent.events import EventStream

if TYPE_CHECKING:  # pragma: no cover
    from patchright.async_api import Page

MAX_STEPS = 14
"""A stop, so a confused model cannot spend a run going in circles.

Generous against the demo's shape — sign in, search, open, get bounced, sign in,
search, open, download is eight — and small enough that hitting it is a signal
rather than a bill.
"""


@dataclass(frozen=True, slots=True)
class PortalAccess:
    """Where the portal is and how to sign into it.

    One argument rather than three that always travel together — and the model
    never sees any of it. `log_in` is the only tool that needs any of these, and
    it takes no arguments precisely so that none of them reach the transcript.
    """

    url: str
    user: str
    password: str


@dataclass(frozen=True, slots=True)
class Workspace:
    """The two systems the agent works, each with its own browser session.

    Two sessions rather than two tabs, because they are two unrelated systems
    with unrelated logins — the portal is signed into during the run and gets
    signed out of on purpose, while the practice system arrives already
    authenticated from a saved profile. Sharing a session would let one
    system's session trouble become the other's.
    """

    portal_page: Page
    portal: PortalAccess
    practice_page: Page
    practice_url: str


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """What the run cost, in tokens. Logged per run."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    steps: int = 0

    def plus(self, usage: Any) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=self.output_tokens + int(getattr(usage, "output_tokens", 0) or 0),
            cache_read_tokens=(
                self.cache_read_tokens + int(getattr(usage, "cache_read_input_tokens", 0) or 0)
            ),
            steps=self.steps + 1,
        )

    def as_detail(self) -> dict[str, object]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "model_calls": self.steps,
        }


@dataclass(frozen=True, slots=True)
class AgentRun:
    """What the agent achieved, and what it cost."""

    claim_id: str
    document: Path | None
    recovered: bool
    noted: bool
    """Whether the agent wrote its finding back to the patient's chart."""

    usage: TokenUsage
    steps: tuple[ToolOutcome, ...]
    said: str
    """The model's own last words. Kept for the record, never parsed for control."""

    @property
    def ok(self) -> bool:
        """The whole job: the EOB in hand and the finding written down.

        It meant only "a document arrived", so an agent that fetched the EOB and
        stopped — leaving the question the claim was sent to answer wide open —
        finished green and exited zero.
        """
        return self.document is not None and self.noted


class ModelClient(Protocol):
    """The slice of the Anthropic client this loop uses.

    Narrow on purpose: it is what lets the tests drive the loop with a scripted
    model instead of paying for one, which matters because the interesting cases
    here are a model that recovers, a model that gives up, and a model that will
    not stop — none of which a live call can be asked for on demand.
    """

    async def create(self, **kwargs: Any) -> Any: ...


async def work_the_claim(
    workspace: Workspace,
    *,
    claim_id: str,
    stream: EventStream,
    documents: Path,
    screenshots: Path | None = None,
    client: ModelClient,
    escalation: Escalation = NAVIGATION,
) -> AgentRun:
    """Let the model work the claim across both systems until it is done."""
    page = workspace.portal_page
    portal = workspace.portal
    stream.emit(
        phase="portal",
        kind="phase_start",
        claim_id=claim_id,
        # The model and the reason for it, in the record. An escalation that is
        # not written down is one nobody can review later.
        detail={
            "model": escalation.model,
            "effort": escalation.effort,
            "chosen_because": escalation.because,
        },
    )

    async def _log_in(_: dict[str, Any]) -> ToolOutcome:
        return await log_in(
            page,
            base_url=portal.url,
            user=portal.user,
            password=portal.password,
            stream=stream,
            screenshots=screenshots,
        )

    async def _search_claims(arguments: dict[str, Any]) -> ToolOutcome:
        looking_for = arguments.get("looking_for")
        return await search_claims(
            page,
            stream=stream,
            looking_for=str(looking_for) if looking_for else None,
            screenshots=screenshots,
        )

    async def _open_claim(arguments: dict[str, Any]) -> ToolOutcome:
        return await open_claim(
            page, str(arguments["claim_id"]), stream=stream, screenshots=screenshots
        )

    async def _download_eob(arguments: dict[str, Any]) -> ToolOutcome:
        return await download_eob(
            page,
            str(arguments["claim_id"]),
            into=documents,
            stream=stream,
            screenshots=screenshots,
        )

    async def _read_auth_record(arguments: dict[str, Any]) -> ToolOutcome:
        return await read_auth_record(
            workspace.practice_page,
            str(arguments["claim_id"]),
            base_url=workspace.practice_url,
            stream=stream,
            screenshots=screenshots,
        )

    async def _write_note(arguments: dict[str, Any]) -> ToolOutcome:
        return await write_note(
            workspace.practice_page,
            str(arguments["claim_id"]),
            text=str(arguments["text"]),
            base_url=workspace.practice_url,
            stream=stream,
            screenshots=screenshots,
        )

    # Keyed by the same names the schemas are built from, so a tool the model can
    # see and a tool the loop can run cannot drift apart without a test noticing.
    handlers = dict(
        zip(
            TOOL_NAMES,
            (
                _log_in,
                _search_claims,
                _open_claim,
                _download_eob,
                _read_auth_record,
                _write_note,
            ),
            strict=True,
        )
    )

    async def run_tool(name: str, arguments: dict[str, Any]) -> ToolOutcome:
        handler = handlers.get(name)
        if handler is None:
            raise UnknownTool(name)
        return await handler(arguments)

    messages: list[dict[str, Any]] = [{"role": "user", "content": opening_message(claim_id)}]
    tools = tool_schemas(claim_id)

    usage = TokenUsage()
    steps: list[ToolOutcome] = []
    document: Path | None = None
    recovered = False
    noted = False
    expiry_is_outstanding = False
    said = ""

    async def plan_and_act() -> None:
        nonlocal usage, document, recovered, noted, expiry_is_outstanding, said

        for _ in range(MAX_STEPS):
            response = await client.create(
                model=escalation.model,
                max_tokens=escalation.max_tokens,
                # Cached: the prompt and the tool schemas are byte-identical on
                # every turn of every run, and they are rendered before the
                # messages, so they are exactly the stable prefix caching wants.
                # A short prefix simply will not cache rather than erroring, so
                # this costs nothing if it turns out to be under the minimum.
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                # Adaptive rather than a token budget: `budget_tokens` is rejected
                # outright on this model, and adaptive is the only on-mode it has.
                thinking={"type": "adaptive"},
                output_config={"effort": escalation.effort},
                tools=tools,
                messages=messages,
            )
            usage = usage.plus(getattr(response, "usage", None))
            said = _spoken(response) or said
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                # The model decided it was finished. Its own judgement, not a
                # condition checked here.
                return

            results: list[dict[str, Any]] = []
            for call in _tool_calls(response):
                answering_an_expiry = expiry_is_outstanding and call.name == "log_in"

                outcome = await run_tool(call.name, call.arguments)
                steps.append(outcome)

                if answering_an_expiry and outcome.ok:
                    # Emitted *after* the sign-in worked, not when it was attempted.
                    # Emitting on the decision alone meant a refused re-authentication
                    # still read as "session expired — handled", and a failed run
                    # still reported `recovered`. The record has to be true, which is
                    # the entire reason the recovery is worth showing.
                    recovered = True
                    expiry_is_outstanding = False
                    stream.emit(
                        phase="portal",
                        kind="recovery",
                        claim_id=claim_id,
                        detail={"reason": "session expired", "action": "the agent signed in again"},
                    )
                if outcome.outcome == "session_expired":
                    expiry_is_outstanding = True
                if outcome.tool == "download_eob" and outcome.ok:
                    document = Path(str(outcome.detail["path"]))
                if outcome.tool == "write_note" and outcome.ok:
                    noted = True

                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": json.dumps(
                            {"outcome": outcome.outcome, **_readable(outcome.detail)}
                        ),
                        "is_error": False,
                    }
                )

            # Every result in one user message. Splitting them teaches the model to
            # stop making parallel calls, which is not a lesson worth teaching.
            messages.append({"role": "user", "content": results})

    try:
        await plan_and_act()
    finally:
        # In a `finally`, so what the run cost is recorded even when the loop
        # comes apart - an unknown tool, or the API refusing. That is precisely
        # when someone wants to know what was spent.
        stream.emit(
            phase="portal",
            kind="phase_end",
            claim_id=claim_id,
            outcome="ok" if document else "failed",
            detail={
                **usage.as_detail(),
                "recovered": recovered,
                "wrote_a_note": noted,
                "tool_calls": len(steps),
            },
        )

    return AgentRun(
        claim_id=claim_id,
        document=document,
        recovered=recovered,
        noted=noted,
        usage=usage,
        steps=tuple(steps),
        said=said,
    )


class UnknownTool(RuntimeError):
    """The model asked for a tool that does not exist.

    A bug in the schemas rather than in the model's judgement, so it is raised
    rather than fed back as a result — swallowing it would leave the model
    guessing at a menu that was wrong to begin with.
    """


@dataclass(frozen=True, slots=True)
class _Call:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict[str, Any])


def _tool_calls(response: Any) -> list[_Call]:
    calls: list[_Call] = []
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            # Already parsed by the SDK. Never string-match a serialized input:
            # these models vary their JSON escaping between turns.
            raw: object = block.input
            arguments: dict[str, Any] = cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
            calls.append(_Call(id=str(block.id), name=str(block.name), arguments=arguments))
    return calls


def _spoken(response: Any) -> str:
    return " ".join(
        block.text.strip()
        for block in response.content
        if getattr(block, "type", None) == "text" and block.text.strip()
    )


AUDIT_ONLY: frozenset[str] = frozenset({"path", "bytes", "characters"})
"""Fields the record wants and the model has no use for.

A *deny* list, not an allow list. It was an allow list, and it silently dropped
every field `read_auth_record` returns — so the model was handed `{"outcome":
"ok"}` and asked to compare a validity range it had never been shown. The tool
was typed, the prompt described the comparison, and the data never arrived.

Deny is the safer default here: a new tool that returns something useful is
readable by the model without anyone remembering to add it, and the cost of
getting this wrong in that direction is a few tokens rather than a silent
lobotomy.
"""


def _readable(detail: dict[str, Any]) -> dict[str, Any]:
    """Trim a tool's detail to what helps the model decide.

    Local paths and byte counts are audit material, not planning material, and
    every token of them is paid for on each subsequent turn.
    """
    return {key: value for key, value in detail.items() if key not in AUDIT_ONLY}
