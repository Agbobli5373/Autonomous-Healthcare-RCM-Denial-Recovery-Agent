"""The agent loop, driven by a scripted model against a real portal.

**Real tools, real browser, real portal — scripted model.** The model is the one
thing faked here, and it is faked deliberately rather than for speed. The cases
that matter are a model that recovers, a model that does not, a model that will
not stop, and a model that asks for a tool which does not exist. None of those
can be ordered from a live call, and a test that bills for tokens on every run is
a test people stop running.

What the fake does *not* do is stand in for the portal. The expiry these tests
recover from is the mock's own, sprung on the real first claim-detail view.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
from tests.conftest import HERO_CLAIM, PORTAL_PASSWORD, PORTAL_USER, needs_browser

from rcm_agent.agent.loop import (
    MAX_STEPS,
    PortalAccess,
    TokenUsage,
    UnknownTool,
    Workspace,
    work_the_claim,
)
from rcm_agent.agent.surface import SYSTEM_PROMPT, TOOL_NAMES, tool_schemas
from rcm_agent.browser.session import as_storage_state
from rcm_agent.events import Event, EventStream
from rcm_agent.mocks.practice_management import storage_state as practice_storage_state

# --- a model made of tape --------------------------------------------------


DENIED_PROCEDURE = "E0601"
"""The CPAP device the CO-197 denial is about."""


@dataclass
class Usage:
    input_tokens: int = 120
    output_tokens: int = 40
    cache_read_input_tokens: int = 0


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: str = "tool_use"


@dataclass
class Reply:
    content: list[Any]
    stop_reason: str
    usage: Usage = field(default_factory=Usage)


class ScriptedModel:
    """A model with a policy instead of a mind.

    It sees the same tool results the real one would and decides from them, which
    is what makes the recovery test meaningful: the loop is not told a recovery
    is coming, it observes the decision this policy makes.
    """

    def __init__(self, policy: Any) -> None:
        self.policy = policy
        self.calls: list[dict[str, Any]] = []
        self._next_id = 0

    async def create(self, **kwargs: Any) -> Reply:
        self.calls.append(kwargs)
        results = _results_so_far(kwargs["messages"])
        decision = self.policy(results)
        if decision is None:
            return Reply(content=[TextBlock("I have the EOB.")], stop_reason="end_turn")
        name, arguments = decision
        self._next_id += 1
        return Reply(
            content=[ToolUseBlock(id=f"call_{self._next_id}", name=name, input=arguments)],
            stop_reason="tool_use",
        )


def _results_so_far(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every tool result the model has been shown, in order, in full.

    The whole payload rather than only the outcome string, because a policy that
    is meant to stand in for a model has to be able to *reason* over what it was
    told — comparing a validity range against a date of service is the point of
    this leg, and it cannot be done from the word "ok".
    """
    seen: list[dict[str, Any]] = []
    for message in messages:
        content: object = message.get("content")
        if message.get("role") != "user" or not isinstance(content, list):
            continue
        for entry in cast("list[object]", content):
            if not isinstance(entry, dict):
                continue
            block = cast("dict[str, Any]", entry)
            if block.get("type") == "tool_result":
                seen.append(cast("dict[str, Any]", json.loads(str(block["content"]))))
    return seen


def _outcomes(results: list[dict[str, Any]]) -> list[str]:
    return [str(r["outcome"]) for r in results]


def a_competent_agent(results: list[dict[str, Any]]) -> tuple[str, dict[str, Any]] | None:
    """Works the claim across both systems, and reasons about what it reads.

    Written as a policy over what it has been told rather than as a fixed list,
    so the recovery and the conclusion are decisions it *reaches*. That is the
    same shape the real model's are, and the reason these tests prove anything
    about the loop rather than about a script.
    """
    outcomes = _outcomes(results)
    if outcomes and outcomes[-1] == "session_expired":
        return "log_in", {}

    # Progress since the last time the portal signed us out. Counting every `ok`
    # ever seen would have it resume mid-sequence after a recovery and reach for
    # the EOB with no claim open - which is what the first version did, and what
    # a real model would have no reason to do either.
    step = 0
    for outcome in outcomes:
        step = 0 if outcome == "session_expired" else step + (outcome == "ok")

    if step == 0:
        return "log_in", {}
    if step == 1:
        return "search_claims", {"looking_for": HERO_CLAIM}
    if step == 2:
        return "open_claim", {"claim_id": HERO_CLAIM}
    if step == 3:
        return "download_eob", {"claim_id": HERO_CLAIM}
    if step == 4:
        return "read_auth_record", {"claim_id": HERO_CLAIM}
    if step == 5:
        return "write_note", {"claim_id": HERO_CLAIM, "text": _conclusion(results)}
    return None


def _conclusion(results: list[dict[str, Any]]) -> str:
    """The reasoning step, made from the typed fields the tool returned.

    This is what the ticket means by the agent reaching a conclusion: nothing
    told this policy whether the Authorization covers the claim. It compares the
    range against the date of service and the code against the scope, and says
    what it found.
    """
    record = next(r for r in results if "authorization_number" in r)
    service = date.fromisoformat(str(record["date_of_service"]))
    valid_from = date.fromisoformat(str(record["valid_from"]))
    valid_to = date.fromisoformat(str(record["valid_to"]))
    in_range = valid_from <= service <= valid_to
    in_scope = DENIED_PROCEDURE in record["covered_procedure_codes"]

    if in_range and in_scope:
        return (
            f"Payer denied CO-197 asserting no prior authorization. Chart holds "
            f"{record['authorization_number']}, valid {valid_from} to {valid_to}, "
            f"covering {DENIED_PROCEDURE}. Date of service {service} falls inside "
            f"that range, so the denial is refutable."
        )
    return (
        f"Authorization {record['authorization_number']} does not answer this denial: "
        f"date of service {service} in range={in_range}, {DENIED_PROCEDURE} in scope={in_scope}."
    )


def an_agent_that_gives_up(results: list[dict[str, Any]]) -> tuple[str, dict[str, Any]] | None:
    """Signs in, gets bounced, and stops instead of recovering."""
    outcomes = _outcomes(results)
    if outcomes and outcomes[-1] == "session_expired":
        return None
    done = [o for o in outcomes if o == "ok"]
    if len(done) == 0:
        return "log_in", {}
    if len(done) == 1:
        return "search_claims", {"looking_for": HERO_CLAIM}
    return "open_claim", {"claim_id": HERO_CLAIM}


def an_agent_that_never_stops(results: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    return "log_in", {}


def an_agent_that_invents_a_tool(results: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    return "escalate_to_a_human", {}


# --- driving it ------------------------------------------------------------


class Recorder:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def handle(self, event: Event) -> None:
        self.events.append(event)


@dataclass
class Driven:
    run: Any
    recorder: Recorder
    model: ScriptedModel

    def of_kind(self, kind: str) -> list[Event]:
        return [e for e in self.recorder.events if e.kind == kind]


def drive(
    portal_url: str,
    practice_url: str,
    tmp_path: Path,
    policy: Any,
    recorder: Recorder | None = None,
) -> Driven:
    """Run one agent against real browsers and both really-served systems.

    Two contexts in one browser rather than two browsers: what matters is that
    the two systems have separate sessions and separate cookies, which is what a
    context is. Two Solari browsers is the production arrangement and costs a
    minute a run to prove.

    A `recorder` can be passed in so a test that expects the run to *raise* can
    still read what was emitted before it did.
    """
    from patchright.async_api import async_playwright

    recorder = recorder or Recorder()
    stream = EventStream()
    stream.add_sink(recorder)
    model = ScriptedModel(policy)

    async def go() -> Any:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            portal_context = await browser.new_context(accept_downloads=True)
            portal_page = await portal_context.new_page()

            practice_context = await browser.new_context(
                storage_state=as_storage_state(practice_storage_state(practice_url))
            )
            practice_page = await practice_context.new_page()
            try:
                return await work_the_claim(
                    Workspace(
                        portal_page=portal_page,
                        portal=PortalAccess(
                            url=portal_url, user=PORTAL_USER, password=PORTAL_PASSWORD
                        ),
                        practice_page=practice_page,
                        practice_url=practice_url,
                    ),
                    claim_id=HERO_CLAIM,
                    stream=stream,
                    documents=tmp_path / "documents",
                    screenshots=tmp_path / "screenshots",
                    client=model,
                )
            finally:
                await browser.close()

    return Driven(run=asyncio.run(go()), recorder=recorder, model=model)


# --- the model does the driving --------------------------------------------


@needs_browser
def test_the_agent_reaches_the_claim_and_downloads_its_eob(
    fresh_portal: str, practice_url: str, tmp_path: Path
) -> None:
    """Unattended, from an opening instruction and four tools."""
    from rcm_agent.mocks import fixtures_data

    driven = drive(fresh_portal, practice_url, tmp_path, a_competent_agent)

    assert driven.run.ok, driven.run
    claim = fixtures_data.find(HERO_CLAIM)
    assert claim is not None
    assert driven.run.document is not None
    assert driven.run.document.read_bytes() == claim.eob_path.read_bytes()


@needs_browser
def test_the_tools_that_ran_are_the_ones_the_model_asked_for(
    fresh_portal: str, practice_url: str, tmp_path: Path
) -> None:
    """No sequence in the loop. Change the policy and the run changes with it."""
    driven = drive(fresh_portal, practice_url, tmp_path, a_competent_agent)

    assert [step.tool for step in driven.run.steps] == [
        "log_in",
        "search_claims",
        "open_claim",
        "log_in",
        "search_claims",
        "open_claim",
        "download_eob",
        "read_auth_record",
        "write_note",
    ]


# --- the recovery ----------------------------------------------------------


@needs_browser
def test_the_expiry_is_detected_by_the_tool_and_recovered_by_the_agent(
    fresh_portal: str, practice_url: str, tmp_path: Path
) -> None:
    """The split the ticket asks for, both halves in one run.

    Detection is the tool's and deterministic — `open_claim` returns
    `session_expired` because it landed on the login page. The decision is the
    model's: this policy answers that outcome by signing in again.
    """
    driven = drive(fresh_portal, practice_url, tmp_path, a_competent_agent)

    expired = [s for s in driven.run.steps if s.outcome == "session_expired"]
    assert [s.tool for s in expired] == ["open_claim"], "the tool did not detect the expiry"

    recoveries = driven.of_kind("recovery")
    assert len(recoveries) == 1
    assert recoveries[0].detail["reason"] == "session expired"
    assert driven.run.recovered


@needs_browser
def test_no_recovery_is_recorded_when_the_agent_does_not_recover(
    fresh_portal: str, practice_url: str, tmp_path: Path
) -> None:
    """Proof the loop observes the decision rather than making it.

    Same portal, same expiry, a model that answers it by stopping. If the loop
    were driving, a `recovery` would be recorded here anyway — and the record
    would be claiming something the agent never did.
    """
    driven = drive(fresh_portal, practice_url, tmp_path, an_agent_that_gives_up)

    assert any(s.outcome == "session_expired" for s in driven.run.steps)
    assert driven.of_kind("recovery") == []
    assert not driven.run.recovered
    assert not driven.run.ok


@needs_browser
def test_a_recovery_is_never_recorded_as_an_error(
    fresh_portal: str, practice_url: str, tmp_path: Path
) -> None:
    """It is handled behaviour, and the schema has to say so."""
    driven = drive(fresh_portal, practice_url, tmp_path, a_competent_agent)

    assert driven.of_kind("error") == []
    assert driven.of_kind("recovery")


@needs_browser
def test_retry_and_recovery_are_different_kinds(
    fresh_portal: str, practice_url: str, tmp_path: Path
) -> None:
    """One is a click that missed; the other is the agent changing its plan.

    A clean run has recoveries and no retries, which is only a meaningful
    statement because they are separate kinds rather than one event with a flag.
    """
    driven = drive(fresh_portal, practice_url, tmp_path, a_competent_agent)

    assert driven.of_kind("recovery")
    assert driven.of_kind("retry") == [], "a clean run should not have retried anything"


# --- what the run cost -----------------------------------------------------


@needs_browser
def test_token_usage_is_accumulated_and_logged_for_the_run(
    fresh_portal: str, practice_url: str, tmp_path: Path
) -> None:
    driven = drive(fresh_portal, practice_url, tmp_path, a_competent_agent)

    assert driven.run.usage.input_tokens > 0
    assert driven.run.usage.output_tokens > 0
    assert driven.run.usage.steps == len(driven.model.calls)

    ended = driven.of_kind("phase_end")[-1]
    assert ended.detail["input_tokens"] == driven.run.usage.input_tokens
    assert ended.detail["output_tokens"] == driven.run.usage.output_tokens
    assert ended.detail["model_calls"] == driven.run.usage.steps


def test_usage_survives_a_response_that_reports_none() -> None:
    """A missing usage block must not take the run down over accounting."""
    assert TokenUsage().plus(None).steps == 1
    assert TokenUsage().plus(None).input_tokens == 0


# --- bounds and bad tools --------------------------------------------------


@needs_browser
def test_a_model_that_never_stops_is_stopped(
    fresh_portal: str, practice_url: str, tmp_path: Path
) -> None:
    """A confused model must cost a bounded number of calls, not a bill."""
    driven = drive(fresh_portal, practice_url, tmp_path, an_agent_that_never_stops)

    assert len(driven.model.calls) == MAX_STEPS
    assert not driven.run.ok


@needs_browser
def test_a_tool_the_schemas_never_offered_is_a_bug_not_a_result(
    fresh_portal: str, practice_url: str, tmp_path: Path
) -> None:
    """Feeding it back as an error would leave the model guessing at a bad menu."""
    with pytest.raises(UnknownTool, match="escalate_to_a_human"):
        drive(fresh_portal, practice_url, tmp_path, an_agent_that_invents_a_tool)


# --- what the model is and is not told -------------------------------------


def test_the_credentials_are_not_in_anything_the_model_sees() -> None:
    """`log_in` takes no arguments, and that is a security property.

    Putting them in the schema would place them in the model's context, and from
    there into every transcript, log and cache entry for the rest of the run.
    """
    schemas = json.dumps(tool_schemas(HERO_CLAIM))

    assert PORTAL_PASSWORD not in schemas
    assert PORTAL_PASSWORD not in SYSTEM_PROMPT
    log_in = next(s for s in tool_schemas(HERO_CLAIM) if s["name"] == "log_in")
    assert log_in["input_schema"]["properties"] == {}


def test_every_tool_the_loop_can_run_is_offered_to_the_model() -> None:
    """A tool the model cannot see is a tool it cannot choose.

    Compared against `TOOL_NAMES`, which is what the loop dispatches on, rather
    than against a set written out here. A third hardcoded copy could not have
    caught either of the other two drifting — which is the whole failure this is
    named for.
    """
    offered = {schema["name"] for schema in tool_schemas(HERO_CLAIM)}

    assert offered == set(TOOL_NAMES)
    assert len(TOOL_NAMES) == len(set(TOOL_NAMES)), "a name is listed twice"


def test_the_prompt_explains_the_outcomes_without_prescribing_the_answer() -> None:
    """It has to describe the world, not the sequence.

    Naming what `session_expired` means is context. Saying "when you see it, call
    log_in" would move the decision out of the model and make the centrepiece of
    this ticket a script with extra steps.
    """
    assert "session_expired" in SYSTEM_PROMPT
    lowered = SYSTEM_PROMPT.lower()

    assert "call `log_in`" not in lowered
    assert "then call" not in lowered
    assert "first, " not in lowered


@needs_browser
def test_the_recovery_is_recorded_only_after_the_sign_in_worked(
    fresh_portal: str, practice_url: str, tmp_path: Path
) -> None:
    """Ordering, because the record has to be true and not merely hopeful.

    The first version emitted on the model's *decision*, before running the
    tool. A refused re-authentication would then have read as "session expired —
    handled" with `recovered` set, on a run that failed. `seq` is the join key,
    so asserting on it is asserting the order the record actually shows.
    """
    driven = drive(fresh_portal, practice_url, tmp_path, a_competent_agent)

    recovery = driven.of_kind("recovery")[0]
    sign_ins = [
        e
        for e in driven.recorder.events
        if e.kind == "tool_result" and e.tool == "log_in" and e.seq < recovery.seq
    ]

    assert sign_ins, "the recovery was recorded before any sign-in had returned"
    assert sign_ins[-1].outcome == "ok"


@needs_browser
def test_what_the_run_cost_is_recorded_even_when_the_loop_comes_apart(
    fresh_portal: str, practice_url: str, tmp_path: Path
) -> None:
    """Spend is reported when the loop raises, which is when it is most wanted.

    `phase_end` used to sit after the loop, so an unknown tool or a refusing API
    took the accounting with it.
    """
    recorder = Recorder()

    with pytest.raises(UnknownTool):
        drive(fresh_portal, practice_url, tmp_path, an_agent_that_invents_a_tool, recorder)

    ended = [e for e in recorder.events if e.kind == "phase_end"]
    assert ended, "the run raised and took the accounting with it"
    assert ended[-1].detail["model_calls"] == 1
    assert ended[-1].detail["input_tokens"] > 0


# --- the other system, and the conclusion drawn from it --------------------


@needs_browser
def test_the_agent_reads_the_authorization_and_writes_what_it_concluded(
    fresh_portal: str, practice_url: str, tmp_path: Path
) -> None:
    """The whole point of this leg, end to end through the loop.

    The policy is not told whether the Authorization covers the claim. It is
    handed the typed fields the tool read off the chart, compares the validity
    range against the date of service and the code against the scope, and writes
    what it found. If the loop stopped passing those fields through — as it did,
    by filtering them out of the tool result — this fails.
    """
    driven = drive(fresh_portal, practice_url, tmp_path, a_competent_agent)

    assert driven.run.ok, driven.run
    assert driven.run.noted, "the agent never wrote its finding to the chart"

    note = next(s for s in driven.run.steps if s.tool == "write_note")
    assert note.ok

    read = next(s for s in driven.run.steps if s.tool == "read_auth_record")
    assert read.detail["authorization_number"] == "CHP-2026-0044719"
    assert read.detail["valid_from"] == "2026-02-01"
    assert read.detail["date_of_service"] == "2026-03-14"


@needs_browser
def test_the_conclusion_the_agent_reaches_is_the_right_one(
    fresh_portal: str, practice_url: str, tmp_path: Path
) -> None:
    """Correct, not merely present. 14 March is inside 1 Feb to 31 May.

    Asserting only that *a* note was written would pass for an agent that
    concluded the opposite, which is the answer the payer would like.
    """
    driven = drive(fresh_portal, practice_url, tmp_path, a_competent_agent)

    written = _conclusion(
        [{"outcome": "ok", **s.detail} for s in driven.run.steps if s.tool == "read_auth_record"]
    )

    assert "refutable" in written, written
    assert "does not answer" not in written


@needs_browser
def test_the_two_systems_are_told_apart_in_the_record(
    fresh_portal: str, practice_url: str, tmp_path: Path
) -> None:
    """Events carry the phase of the system they happened in.

    They all said `portal` once, which would have left the run's EMR column
    empty while the scripted demo filled it — a record disagreeing with itself
    about which system did what.
    """
    driven = drive(fresh_portal, practice_url, tmp_path, a_competent_agent)

    phases = {e.tool: e.phase for e in driven.recorder.events if e.kind == "tool_result" and e.tool}

    assert phases["download_eob"] == "portal"
    assert phases["read_auth_record"] == "emr"
    assert phases["write_note"] == "emr"


@needs_browser
def test_a_run_that_never_wrote_the_note_is_not_reported_as_done(
    fresh_portal: str, practice_url: str, tmp_path: Path
) -> None:
    """The job is the EOB *and* the finding. Half of it is not success.

    `ok` meant "a document arrived", so an agent that fetched the EOB and stopped
    exited zero with the question it was sent to answer still open.
    """
    driven = drive(fresh_portal, practice_url, tmp_path, an_agent_that_gives_up)

    assert not driven.run.ok
    assert not driven.run.noted
