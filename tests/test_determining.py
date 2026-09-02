"""Reaching a Determination: extraction, guardrails, judgement, Priority.

Three properties here are safety properties rather than features, and each has a
test whose failure would mean the demo files something it should not:

* **A guardrailed claim reaches no model at all.** The client used for those
  tests raises if it is called, so "the guardrail ran first" is not a claim about
  ordering in a docstring.
* **`CO-236` cannot become an appeal**, whatever the model says, because the
  fact that would settle it is not available to this system.
* **Priority never decides an Action.** A guardrailed Determination has no
  Priority at all.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from rcm_agent.agent.determining import determine_with_judgement
from rcm_agent.agent.judgement import (
    APPEAL_WITHHELD,
    EVERY_ACTION,
    JudgementRefused,
    allowed_actions,
    decision_tool,
    judge,
)
from rcm_agent.analysis.extract import ExtractedAdjustment, Extraction
from rcm_agent.claim_from_document import ClaimIdentity, claim_from_extraction
from rcm_agent.domain import Adjustment, Claim, ServiceLine
from rcm_agent.events import Event, EventStream

IDENTITY = ClaimIdentity(
    claim_id="CLM-2026-0001",
    payer="Cascade Health Plan",
    patient_id="PAT-40219",
    date_of_service=date(2026, 3, 14),
)


# --- a model that answers to order, or refuses to be called ----------------


@dataclass
class ToolUseBlock:
    name: str
    input: dict[str, Any]
    id: str = "call_1"
    type: str = "tool_use"


@dataclass
class Usage:
    input_tokens: int = 200
    output_tokens: int = 60
    cache_read_input_tokens: int = 0


@dataclass
class Reply:
    content: list[Any]
    stop_reason: str = "tool_use"
    usage: Usage = field(default_factory=Usage)


class ScriptedJudge:
    """Answers with whatever it was told to, and remembers what it was asked."""

    def __init__(self, action: str, rationale: str = "because", evidence: Any = None) -> None:
        self.action = action
        self.rationale = rationale
        self.evidence = evidence if evidence is not None else ["Something"]
        self.requests: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Reply:
        self.requests.append(kwargs)
        return Reply(
            content=[
                ToolUseBlock(
                    name="record_determination",
                    input={
                        "action": self.action,
                        "rationale": self.rationale,
                        "evidence_required": self.evidence,
                    },
                )
            ]
        )


class NoModelAllowed:
    """A client that fails the test if anything reaches it.

    This is how "guardrails run before any model call" is checked. An assertion
    about call ordering could be satisfied by a model call that happened anyway
    and was ignored; this cannot.
    """

    async def create(self, **kwargs: Any) -> Reply:
        raise AssertionError("a model was consulted for a claim a guardrail had already answered")


class Recorder:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def handle(self, event: Event) -> None:
        self.events.append(event)


def run(claim: Claim, client: Any) -> tuple[Any, Recorder]:
    recorder = Recorder()
    stream = EventStream()
    stream.add_sink(recorder)
    return asyncio.run(determine_with_judgement(claim, client=client, stream=stream)), recorder


def a_claim(*adjustments: tuple[str, str, tuple[str, ...], str]) -> Claim:
    """One line per adjustment, which is enough for every rule under test."""
    return Claim(
        claim_id=IDENTITY.claim_id,
        payer=IDENTITY.payer,
        patient_id=IDENTITY.patient_id,
        date_of_service=IDENTITY.date_of_service,
        service_lines=tuple(
            ServiceLine(
                line_number=index,
                procedure_code="E0601",
                charge=Decimal("100.00"),
                adjustments=(
                    Adjustment(
                        group=group,  # pyright: ignore[reportArgumentType]
                        reason_code=reason,
                        amount=Decimal(amount),
                        remark_codes=remarks,
                    ),
                ),
            )
            for index, (group, reason, remarks, amount) in enumerate(adjustments, start=1)
        ),
    )


# --- extraction becomes a Claim --------------------------------------------


def test_the_claim_is_built_from_what_the_document_said() -> None:
    extraction = Extraction(
        source="clm-2026-0001-eob.pdf",
        method="text_layer",
        lines=(
            ExtractedAdjustment(1, "E1390", "CO", "45", (), "92.50"),
            ExtractedAdjustment(2, "E0601", "CO", "197", ("N706",), "1250.00"),
        ),
    )

    claim = claim_from_extraction(extraction, IDENTITY)

    assert [line.line_number for line in claim.service_lines] == [1, 2]
    assert claim.amount_denied == Decimal("1250.00"), "the write-off is not a refusal"
    assert [a.code for a in claim.denials] == ["CO-197"]


def test_an_adjustment_with_no_line_number_gets_one_of_its_own() -> None:
    """Guessing which line it belonged to would invent structure the page lacked."""
    extraction = Extraction(
        source="x.pdf",
        method="ocr",
        lines=(
            ExtractedAdjustment(None, None, "CO", "197", ("N706",), "10.00"),
            ExtractedAdjustment(None, None, "OA", "23", (), "5.00"),
        ),
    )

    claim = claim_from_extraction(extraction, IDENTITY)

    assert len(claim.service_lines) == 2


def test_nothing_is_filled_in_from_the_committed_fixtures() -> None:
    """A misread code has to produce a Determination on the misread code.

    Reconciling against the fixture claim would make the extraction decorative
    and hide exactly the failure the extraction tests exist to catch.
    """
    extraction = Extraction(
        source="clm-2026-0001-eob.pdf",
        method="text_layer",
        lines=(ExtractedAdjustment(1, "E0601", "OA", "22", ("MA04",), "210.00"),),
    )

    claim = claim_from_extraction(extraction, IDENTITY)

    assert [a.code for a in claim.adjustments] == ["OA-22"]


# --- guardrails run first, and no model is consulted -----------------------


def test_the_unappealable_remark_is_answered_without_a_model() -> None:
    """`MA130` must be impossible to appeal regardless of what a model thinks."""
    claim = a_claim(("CO", "16", ("MA130",), "78.00"))

    determination, _ = run(claim, NoModelAllowed())

    assert determination.action == "close"
    assert determination.guardrail == "unappealable-remark:MA130"


def test_a_guardrailed_determination_has_no_priority() -> None:
    """Nothing was weighed, so there is no score. `None`, not zero."""
    determination, _ = run(a_claim(("CO", "16", ("MA130",), "78.00")), NoModelAllowed())

    assert determination.priority is None


def test_a_claim_with_only_a_write_off_is_answered_without_a_model() -> None:
    determination, _ = run(a_claim(("CO", "45", (), "92.50")), NoModelAllowed())

    assert determination.action == "close"
    assert determination.guardrail == "no-denial"


def test_the_determination_event_carries_the_guardrail_that_fired() -> None:
    _, recorder = run(a_claim(("CO", "16", ("MA130",), "78.00")), NoModelAllowed())

    decided = [e for e in recorder.events if e.kind == "determination"]
    assert len(decided) == 1
    assert decided[0].detail["guardrail"] == "unappealable-remark:MA130"
    assert "MA130" in str(decided[0].detail["rationale"])


# --- where a judgement remains, a model makes it ---------------------------


def test_the_model_decides_where_no_guardrail_fires() -> None:
    judge_client = ScriptedJudge("appeal", "A valid authorization covered the service.")

    determination, _ = run(a_claim(("CO", "197", ("N706",), "1250.00")), judge_client)

    assert determination.action == "appeal"
    assert determination.guardrail is None
    assert "authorization" in determination.rationale.lower()
    assert judge_client.requests, "no model was consulted"


def test_priority_is_computed_and_kept_apart_from_the_action() -> None:
    determination, _ = run(a_claim(("CO", "197", ("N706",), "1250.00")), ScriptedJudge("appeal"))

    assert determination.priority is not None
    assert determination.priority.amount_at_stake == Decimal("1250.00")
    assert determination.priority.expected_recovery < Decimal("1250.00")


def test_the_judgement_runs_on_the_bigger_model() -> None:
    """The escalation seam's first real use: being wrong here is expensive."""
    judge_client = ScriptedJudge("rebill")

    run(a_claim(("OA", "22", ("MA04",), "210.00")), judge_client)

    assert judge_client.requests[0]["model"] == "claude-opus-5"


def test_the_model_is_forced_to_answer_through_the_tool() -> None:
    """Free text would have to be parsed, and parsing is where a rule slips."""
    judge_client = ScriptedJudge("rebill")

    run(a_claim(("OA", "22", ("MA04",), "210.00")), judge_client)

    assert judge_client.requests[0]["tool_choice"]["name"] == "record_determination"


# --- CO-236 cannot become an appeal ----------------------------------------


def test_appeal_is_not_among_the_options_offered_for_co_236() -> None:
    """Structural: the enum it is given does not contain the word."""
    withheld = a_claim(("CO", "236", (), "300.00"))

    assert "appeal" not in allowed_actions(withheld)
    assert "appeal" in allowed_actions(a_claim(("CO", "197", ("N706",), "300.00")))

    schema = decision_tool(withheld)["input_schema"]
    assert "appeal" not in schema["properties"]["action"]["enum"]


def test_a_bigger_denial_beside_co_236_does_not_reopen_appeal() -> None:
    """The narrowing is claim-wide, because the Determination is.

    `governing_denial` picks the largest by amount, so a `CO-197` of 1200 beside
    a `CO-236` of 300 would once have been judged with the full five options -
    and the resulting claim-level `appeal` would have covered the CO-236 line
    too. Withholding keyed on the governing denial alone was the whole bug.
    """
    mixed = a_claim(
        ("CO", "197", ("N706",), "1200.00"),
        ("CO", "236", (), "300.00"),
    )

    assert "appeal" not in allowed_actions(mixed)
    assert "appeal" not in decision_tool(mixed)["input_schema"]["properties"]["action"]["enum"]


def test_every_other_action_is_still_offered_for_co_236() -> None:
    """Withholding appeal is not the same as closing the claim."""
    withheld = a_claim(("CO", "236", (), "300.00"))

    assert set(allowed_actions(withheld)) == set(EVERY_ACTION) - {"appeal"}


def test_a_model_that_answers_appeal_for_co_236_anyway_is_refused() -> None:
    """Belt and braces, because the failure is a void appeal on a patient's claim.

    The enum should make this unreachable. If it is ever reached, the schema was
    built wrongly or the API ignored it, and the answer is not usable either way.
    """
    claim = a_claim(("CO", "236", (), "300.00"))

    with pytest.raises(JudgementRefused, match="appeal"):
        asyncio.run(
            judge(
                claim,
                claim.denials[0],
                client=ScriptedJudge("appeal"),
                stream=EventStream(),
            )
        )


def test_a_refused_judgement_falls_back_to_the_documented_default() -> None:
    """And the default for this family is never `appeal`."""
    determination, recorder = run(a_claim(("CO", "236", (), "300.00")), ScriptedJudge("appeal"))

    assert determination.action == "corrected_claim"
    assert "fell back" in determination.rationale.lower()
    assert [e.kind for e in recorder.events if e.kind == "error"] == ["error"]


def test_the_reason_appeal_was_withheld_reaches_the_determination() -> None:
    """Nobody should have to open the source to find out why."""
    determination, _ = run(a_claim(("CO", "236", (), "300.00")), ScriptedJudge("corrected_claim"))

    assert "NCCI" in determination.rationale
    assert "appeal was not available" in determination.rationale.lower()


def test_every_withheld_code_explains_itself() -> None:
    for code, because in APPEAL_WITHHELD.items():
        group, reason = code.split("-", 1)
        assert because.strip(), code
        assert "appeal" not in allowed_actions(a_claim((group, reason, (), "300.00")))


# --- all three claims, from the committed PDFs -----------------------------

EXPECTED: dict[str, str] = {
    "CLM-2026-0001": "appeal",
    "CLM-2026-0002": "close",
    "CLM-2026-0003": "rebill",
}
"""The discrimination story, as three rows.

An agent that answered `appeal` everywhere would score one out of three here, and
the middle row is the one that matters most: `MA130` arrives on a remittance
looking exactly like a denial and is legally unappealable.
"""


class ReadsTheFacts:
    """A model that answers from the denial it is shown, not from a script.

    Written as a policy over the prompt so the end-to-end test proves the right
    facts reached the model — a fixed answer per call would pass even if the
    the caller handed it the wrong claim.
    """

    def __init__(self) -> None:
        self.seen: list[str] = []

    async def create(self, **kwargs: Any) -> Reply:
        facts = str(kwargs["messages"][0]["content"])
        self.seen.append(facts)
        allowed = kwargs["tools"][0]["input_schema"]["properties"]["action"]["enum"]

        if "CO-197" in facts:
            action, why = "appeal", "A prior authorization covered the date of service."
        elif "OA-22" in facts:
            action, why = "rebill", "Another payer is primary; bill them first."
        else:
            action, why = "corrected_claim", "Resubmit with the missing information."
        assert action in allowed, f"{action} was not offered"
        return Reply(
            content=[
                ToolUseBlock(
                    name="record_determination",
                    input={"action": action, "rationale": why, "evidence_required": []},
                )
            ]
        )


@pytest.mark.parametrize("claim_id", sorted(EXPECTED))
def test_each_claim_reaches_its_expected_action_from_its_own_document(claim_id: str) -> None:
    """The committed PDF, really extracted, really determined.

    Not from the claim JSON: the whole point is that the Determination is made on
    what the EOB said. The scanned claim needs OCR, so it skips where tesseract
    is absent — the same skip the extraction tests use.
    """
    import shutil
    from pathlib import Path

    from rcm_agent.analysis.extract import extract, has_text_layer
    from rcm_agent.claim_io import load_claim
    from rcm_agent.fixtures.naming import claim_filename, eob_filename

    document = Path("data/fixtures/eobs") / eob_filename(claim_id)
    if not has_text_layer(document) and shutil.which("tesseract") is None:
        pytest.skip("this claim's EOB is a scan and tesseract is not installed")

    known = load_claim(Path("data/fixtures/claims") / claim_filename(claim_id))
    identity = ClaimIdentity(
        claim_id=known.claim_id,
        payer=known.payer,
        patient_id=known.patient_id,
        date_of_service=known.date_of_service,
    )

    claim = claim_from_extraction(extract(document), identity)
    determination, _ = run(claim, ReadsTheFacts())

    assert determination.action == EXPECTED[claim_id], determination


def test_the_unappealable_claim_is_the_one_no_model_ever_sees() -> None:
    """`MA130` is answered by a rule, and the model is never asked.

    Run with a client that raises on contact, so this cannot pass by a model
    being consulted and its answer discarded.
    """
    from pathlib import Path

    from rcm_agent.analysis.extract import extract
    from rcm_agent.claim_io import load_claim

    known = load_claim(Path("data/fixtures/claims/clm-2026-0002.json"))
    claim = claim_from_extraction(
        extract(Path("data/fixtures/eobs/clm-2026-0002-eob.pdf")),
        ClaimIdentity(known.claim_id, known.payer, known.patient_id, known.date_of_service),
    )

    determination, _ = run(claim, NoModelAllowed())

    assert determination.action == "close"
    assert determination.guardrail == "unappealable-remark:MA130"
    assert determination.priority is None


# --- what the run leaves behind --------------------------------------------


def test_the_closed_claim_reads_as_not_applicable_rather_than_pending() -> None:
    """The discrimination story rendering itself, and the demo's whole point.

    A claim that will never be appealed has no EMR visit and no appeal package
    in its future. Leaving those cells `pending` would say the agent has work
    left; `n/a` says it decided there was none.
    """
    from rcm_agent.matrix import ClaimMatrix

    matrix = ClaimMatrix(["CLM-2026-0001", "CLM-2026-0002"])
    stream = EventStream()
    stream.add_sink(matrix)

    asyncio.run(
        determine_with_judgement(
            a_claim(("CO", "16", ("MA130",), "78.00")), client=NoModelAllowed(), stream=stream
        )
    )

    assert matrix.cell("CLM-2026-0001", "emr") == "na"
    assert matrix.cell("CLM-2026-0001", "appeal") == "na"


def test_a_claim_headed_for_appeal_keeps_its_evidence_cells_open() -> None:
    """The other half of the contrast, or `n/a` would just mean "decided"."""
    from rcm_agent.matrix import ClaimMatrix

    matrix = ClaimMatrix([IDENTITY.claim_id])
    stream = EventStream()
    stream.add_sink(matrix)

    asyncio.run(
        determine_with_judgement(
            a_claim(("CO", "197", ("N706",), "1250.00")),
            client=ScriptedJudge("appeal"),
            stream=stream,
        )
    )

    assert matrix.cell(IDENTITY.claim_id, "emr") == "pending"
    assert matrix.cell(IDENTITY.claim_id, "appeal") == "pending"


def test_each_claim_is_written_out_in_the_domain_vocabulary(tmp_path: Any) -> None:
    """`claims/<id>.json`, readable by someone who knows the domain and not this code."""
    import json
    from datetime import UTC, datetime

    from rcm_agent.run_directory import RunDirectory

    directory = RunDirectory.create(tmp_path, started_at=datetime.now(UTC))
    determination, _ = run(a_claim(("CO", "197", ("N706",), "1250.00")), ScriptedJudge("appeal"))

    written = directory.write_claim(determination)
    payload = json.loads(written.read_text(encoding="utf-8"))

    assert written.name == "clm-2026-0001.json"
    assert payload["action"] == "appeal"
    assert payload["rationale"]
    assert payload["guardrail"] is None
    assert payload["priority"]["amount_at_stake"] == "1250.00"


def test_a_guardrailed_claim_is_written_with_its_rule_and_no_priority(tmp_path: Any) -> None:
    import json
    from datetime import UTC, datetime

    from rcm_agent.run_directory import RunDirectory

    directory = RunDirectory.create(tmp_path, started_at=datetime.now(UTC))
    determination, _ = run(a_claim(("CO", "16", ("MA130",), "78.00")), NoModelAllowed())

    payload = json.loads(directory.write_claim(determination).read_text(encoding="utf-8"))

    assert payload["action"] == "close"
    assert payload["guardrail"] == "unappealable-remark:MA130"
    assert payload["priority"] is None, "nothing was weighed, so there is no score"


def test_an_action_that_needs_evidence_never_goes_out_with_an_empty_list() -> None:
    """Observed live: the same prompt named ten items once and none the next time.

    An Appeal Package built from an empty list is not an appeal, so the
    catalogue's documented list for the family stands in. #36 consumes this
    field, and a hollow Determination would surface there rather than here.
    """
    determination, recorder = run(
        a_claim(("CO", "197", ("N706",), "1250.00")),
        ScriptedJudge("appeal", evidence=[]),
    )

    assert determination.evidence_required == ("Authorization record", "Date of service")
    assert "supplied from the catalogue" in determination.rationale
    handled = [e for e in recorder.events if e.kind == "error"]
    assert handled and handled[0].outcome == "handled", "the substitution must be visible"


def test_a_close_may_name_no_evidence_because_nothing_is_gathered() -> None:
    """CO-236, not a guardrailed code: otherwise the judge is never consulted."""
    judge_client = ScriptedJudge("close", evidence=[])

    determination, _ = run(a_claim(("CO", "236", (), "300.00")), judge_client)

    assert judge_client.requests, "the guardrails must not have answered this one"
    assert determination.evidence_required == ()
    assert "supplied from the catalogue" not in determination.rationale


# --- what the run records about how it decided ------------------------------


def kinds(recorder: Recorder) -> list[str]:
    return [event.kind for event in recorder.events]


def only(recorder: Recorder, kind: str) -> Event:
    matches = [event for event in recorder.events if event.kind == kind]
    assert len(matches) == 1, f"expected one {kind}, got {len(matches)}"
    return matches[0]


def test_the_guardrail_trace_is_recorded_before_the_determination() -> None:
    """The trace is what happened first, and the record says so."""
    _, recorder = run(a_claim(("CO", "16", ("MA130",), "78.00")), NoModelAllowed())

    order = kinds(recorder)

    assert order.index("guardrails") < order.index("determination")


def test_a_guardrailed_claim_records_the_rules_that_passed_first() -> None:
    """`CO-45` is answered by the second rule, so the first one is on the record.

    A claim answered by the first rule could not tell these apart: the evidence
    that the rules ran *in order* is the passed rule sitting ahead of the one
    that fired.
    """
    _, recorder = run(a_claim(("CO", "45", (), "80.00")), NoModelAllowed())

    detail = only(recorder, "guardrails").detail

    assert detail["evaluated"] == [
        {"rule": "unappealable-remark", "fired": False},
        # The label the Determination ended up with rides on the rule that
        # produced it, so the two events do not name the same firing differently.
        {"rule": "nothing-was-refused", "fired": True, "guardrail": "no-denial"},
    ]


def test_a_guardrailed_run_shows_no_model_was_asked() -> None:
    """The absence proves the model was not consulted; the trace proves why."""
    _, recorder = run(a_claim(("CO", "16", ("MA130",), "78.00")), NoModelAllowed())

    tools = [event.tool for event in recorder.events if event.kind in ("tool_call", "tool_result")]

    assert "judge_denial" not in tools


def test_a_judged_claim_records_every_rule_passing() -> None:
    _, recorder = run(a_claim(("CO", "197", ("N706",), "1250.00")), ScriptedJudge("appeal"))

    detail = only(recorder, "guardrails").detail

    assert not any(entry["fired"] for entry in detail["evaluated"])  # pyright: ignore[reportIndexIssue, reportUnknownVariableType, reportUnknownArgumentType]
    assert [entry["rule"] for entry in detail["evaluated"]] == [  # pyright: ignore[reportIndexIssue, reportUnknownVariableType]
        "unappealable-remark",
        "nothing-was-refused",
        "non-appealable-code",
    ]


def test_the_facts_put_to_the_model_are_recorded_on_the_call() -> None:
    """The inspector's claim is that the Determination was read off the document.

    Recording the facts is what makes that checkable rather than asserted.
    """
    _, recorder = run(a_claim(("CO", "197", ("N706",), "1250.00")), ScriptedJudge("appeal"))

    facts = only(recorder, "tool_call").detail["facts"]

    assert isinstance(facts, str)
    assert "CO-197" in facts and "N706" in facts


def test_what_the_model_returned_is_recorded_as_a_result() -> None:
    _, recorder = run(
        a_claim(("CO", "197", ("N706",), "1250.00")),
        ScriptedJudge("appeal", rationale="because the auth covered it"),
    )

    result = only(recorder, "tool_result")

    assert result.tool == "judge_denial"
    returned = result.detail["returned"]
    assert isinstance(returned, dict)
    assert returned["action"] == "appeal"
    assert returned["rationale"] == "because the auth covered it"


def test_a_refused_judgement_is_not_recorded_as_ok() -> None:
    """The record must not show an accepted result the run then discarded.

    A model answering outside its narrowed options is refused and fallen back
    from; stamping that exchange `ok` would leave a reader an accepted model
    result whose action contradicts the Determination sitting beside it.
    """
    _, recorder = run(a_claim(("CO", "236", (), "300.00")), ScriptedJudge("appeal"))

    result = only(recorder, "tool_result")

    assert result.outcome == "failed", "appeal was never among the options for CO-236"
    assert result.detail["returned"]["action"] == "appeal"  # pyright: ignore[reportIndexIssue, reportUnknownVariableType, reportUnknownMemberType]
    assert any(e.kind == "error" and e.outcome == "handled" for e in recorder.events)


def test_the_system_prompt_is_never_recorded() -> None:
    """A module constant, identical every run, already readable in source.

    Persisting it would repeat the largest static string in the system into every
    artifact and ship it publicly on every export, for nothing.
    """
    import json

    from rcm_agent.agent.judgement import SYSTEM_PROMPT

    _, recorder = run(a_claim(("CO", "197", ("N706",), "1250.00")), ScriptedJudge("appeal"))

    dumped = json.dumps([event.to_dict() for event in recorder.events])

    assert SYSTEM_PROMPT[:60] not in dumped
