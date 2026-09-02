from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal

import pytest

from rcm_agent.determination import GUARDRAILS, determine, run_guardrails
from rcm_agent.domain import Action, Adjustment, Claim, ServiceLine

DOS = date(2026, 3, 14)


def adjustment(code: str, amount: str = "450.00", *remarks: str) -> Adjustment:
    group, reason = code.split("-", 1)
    return Adjustment(
        group=group,  # pyright: ignore[reportArgumentType]
        reason_code=reason,
        amount=Decimal(amount),
        remark_codes=remarks,
    )


def claim_with(*adjustments: Adjustment, claim_id: str = "CLM-0001") -> Claim:
    """A single-line claim carrying the given adjustments."""
    return Claim(
        claim_id=claim_id,
        payer="Demo Health Plan",
        patient_id="PAT-1",
        date_of_service=DOS,
        service_lines=(
            ServiceLine(
                line_number=1,
                procedure_code="E1390",
                charge=Decimal("450.00"),
                adjustments=adjustments,
            ),
        ),
    )


# --- the twelve-code demo subset -------------------------------------------
#
# Roughly half must call for something other than an appeal, and two are traps
# for a model that has learned "denial -> appeal". Answering `appeal` everywhere
# would look perfect here and be worthless.

TWELVE_CODES: list[tuple[str, tuple[str, ...], Action]] = [
    ("CO-197", ("N706",), "appeal"),  # prior authorization
    ("CO-50", ("N115",), "appeal"),  # medical necessity
    ("PR-50", (), "patient_bill"),  # same CARC, liability shifted
    ("CO-29", (), "appeal"),  # timely filing
    ("OA-22", ("MA04",), "rebill"),  # coordination of benefits
    ("CO-16", ("MA130",), "close"),  # unprocessable: no appeal rights
    ("CO-236", (), "corrected_claim"),  # NCCI bundling
    ("CO-97", ("M15",), "appeal"),  # payer-policy bundling
    ("OA-18", ("N522",), "close"),  # duplicate
    ("CO-96", ("N130",), "close"),  # non-covered service
    ("CO-45", (), "close"),  # write-off: not a denial
    ("PR-1", (), "patient_bill"),  # deductible: not a denial
]


@pytest.mark.parametrize(("code", "remarks", "expected"), TWELVE_CODES)
def test_the_demo_subset_determines_as_specified(
    code: str, remarks: tuple[str, ...], expected: Action
) -> None:
    determination = determine(claim_with(adjustment(code, "450.00", *remarks)))

    assert determination.action == expected


def test_the_subset_is_not_dominated_by_appeal() -> None:
    """Answering `appeal` everywhere must not score well here."""
    actions = [expected for _, _, expected in TWELVE_CODES]

    assert actions.count("appeal") <= len(actions) // 2


# --- the trap: same CARC, opposite outcome ---------------------------------


def test_co50_and_pr50_share_a_carc_and_diverge() -> None:
    """The group code decides liability. Reading only the Reason Code fails here."""
    provider_liable = determine(claim_with(adjustment("CO-50", "450.00", "N115")))
    patient_liable = determine(claim_with(adjustment("PR-50", "450.00")))

    assert provider_liable.action == "appeal"
    assert patient_liable.action == "patient_bill"


# --- guardrails are rules, not thresholds ----------------------------------


@pytest.mark.parametrize("remark", ["MA130", "N211"])
def test_unappealable_remarks_can_never_produce_an_appeal(remark: str) -> None:
    """Legal unappealability is a rule. No confidence may override it."""
    determination = determine(claim_with(adjustment("CO-197", "450.00", remark, "N706")))

    assert determination.action != "appeal"
    assert determination.was_guardrailed


def test_ma130_is_guardrailed_even_beside_an_appealable_denial() -> None:
    claim = claim_with(
        adjustment("CO-197", "300.00", "N706"),
        adjustment("CO-16", "150.00", "MA130"),
    )

    determination = determine(claim)

    assert determination.action != "appeal"
    assert determination.guardrail is not None


def test_a_guardrailed_determination_reaches_no_scoring() -> None:
    determination = determine(claim_with(adjustment("CO-16", "450.00", "MA130")))

    assert determination.was_guardrailed
    assert determination.priority is None


def test_patient_responsibility_is_billed_not_appealed() -> None:
    for reason in ("1", "2", "3"):
        determination = determine(claim_with(adjustment(f"PR-{reason}")))

        assert determination.action == "patient_bill"
        assert determination.was_guardrailed


# --- the CO-45 false positive ----------------------------------------------


def test_a_lone_write_off_is_not_a_denial() -> None:
    """If a contractual write-off is the only adjustment, the claim was paid correctly."""
    determination = determine(claim_with(adjustment("CO-45")))

    assert determination.action == "close"
    assert determination.was_guardrailed


def test_a_write_off_beside_a_denial_does_not_suppress_the_denial() -> None:
    """Only expressible because adjustments sit at line grain (ADR-0001)."""
    claim = Claim(
        claim_id="CLM-0001",
        payer="Demo Health Plan",
        patient_id="PAT-1",
        date_of_service=DOS,
        service_lines=(
            ServiceLine(1, "E1390", Decimal("450.00"), (adjustment("CO-45", "50.00"),)),
            ServiceLine(2, "J1745", Decimal("900.00"), (adjustment("CO-197", "900.00", "N706"),)),
        ),
    )

    determination = determine(claim)

    assert determination.action == "appeal"


def test_a_write_off_beside_patient_responsibility_is_still_not_a_denial() -> None:
    claim = claim_with(adjustment("CO-45", "50.00"), adjustment("PR-2", "25.00"))

    determination = determine(claim)

    assert determination.action == "patient_bill"


# --- priority is separate from the action ----------------------------------


def test_a_judged_determination_carries_a_priority() -> None:
    determination = determine(claim_with(adjustment("CO-197", "900.00", "N706")))

    assert determination.priority is not None
    assert determination.priority.amount_at_stake == Decimal("900.00")


def test_priority_ranks_but_does_not_decide() -> None:
    """Two claims, same code, different money: same Action, different ranking."""
    small = determine(claim_with(adjustment("CO-197", "100.00", "N706")))
    large = determine(claim_with(adjustment("CO-197", "5000.00", "N706")))

    assert small.action == large.action
    assert small.priority is not None
    assert large.priority is not None
    assert large.priority.expected_recovery > small.priority.expected_recovery


# --- shape of the answer ---------------------------------------------------


def test_a_determination_says_what_evidence_an_appeal_needs() -> None:
    determination = determine(claim_with(adjustment("CO-197", "450.00", "N706")))

    assert determination.evidence_required


def test_every_determination_carries_a_rationale() -> None:
    for code, remarks, _ in TWELVE_CODES:
        determination = determine(claim_with(adjustment(code, "450.00", *remarks)))

        assert determination.rationale.strip()


def test_the_claim_id_travels_with_the_determination() -> None:
    determination = determine(
        claim_with(adjustment("CO-197", "450.00", "N706"), claim_id="CLM-0042")
    )

    assert determination.claim_id == "CLM-0042"


def test_an_unknown_code_is_not_guessed_into_an_appeal() -> None:
    """Filing an appeal on a code we do not understand is the wrong failure."""
    determination = determine(claim_with(adjustment("CO-9999")))

    assert determination.action != "appeal"


def test_a_claim_with_no_adjustments_is_closed() -> None:
    claim = Claim(
        claim_id="CLM-0001",
        payer="Demo Health Plan",
        patient_id="PAT-1",
        date_of_service=DOS,
        service_lines=(ServiceLine(1, "E1390", Decimal("450.00"), ()),),
    )

    assert determine(claim).action == "close"


def test_emitted_text_survives_a_narrow_terminal_encoding() -> None:
    """Rationales reach JSON, the panel and later an appeal letter.

    A redirected stdout on Windows is cp1252. An em dash in a docstring is
    harmless because it never prints; one in a rationale renders as a
    replacement character in front of a reviewer.
    """
    for code, remarks, _ in TWELVE_CODES:
        determination = determine(claim_with(adjustment(code, "450.00", *remarks)))

        determination.rationale.encode("cp1252")
        for item in determination.evidence_required:
            item.encode("cp1252")


# --- regressions found by review -------------------------------------------


@pytest.mark.parametrize("written_as", ["ma130", " MA130", "Ma130 ", "\tma130"])
def test_an_unappealable_remark_holds_however_it_is_written(written_as: str) -> None:
    """The criterion is "under any input", and exact-string matching did not meet it.

    A claim file carrying a lowercase or padded MA130 produced an appeal on a
    legally unappealable claim. Codes are normalised at construction now, so
    there is no unnormalised Adjustment for a guardrail to miss.
    """
    determination = determine(claim_with(adjustment("CO-50", "450.00", written_as)))

    assert determination.action != "appeal"
    assert determination.was_guardrailed


def test_a_reason_code_is_normalised_too() -> None:
    assert adjustment("CO- 45 ").code == "CO-45"


@pytest.mark.parametrize("incidental", ["CO-253", "OA-23"])
def test_a_non_appealable_code_beside_a_real_denial_does_not_suppress_it(
    incidental: str,
) -> None:
    """`CO-253` is the sequestration reduction and rides along on nearly every
    Medicare remittance. A claim-wide check closed genuine denials that merely
    shared a claim with one — the same failure the `CO-45` rule prevents."""
    claim = claim_with(
        adjustment("CO-50", "900.00", "N115"),
        adjustment(incidental, "18.00"),
    )

    assert determine(claim).action == "appeal"


@pytest.mark.parametrize("code", ["CO-253", "OA-23"])
def test_a_non_appealable_code_still_closes_when_it_is_the_denial(code: str) -> None:
    determination = determine(claim_with(adjustment(code, "18.00")))

    assert determination.action == "close"
    assert determination.was_guardrailed


# --- the guardrail trace ----------------------------------------------------


def test_the_trace_names_every_rule_that_ran_in_order() -> None:
    """The order is the safety property, so the record has to show it.

    Until now the only evidence guardrails ran at all was the *absence* of a
    model call, which proves the model was not asked and not that the rules were
    consulted.
    """
    trace = run_guardrails(claim_with(adjustment("CO-197", "450.00", "N706")))

    assert trace.determination is None, "nothing should fire on an appealable denial"
    assert [outcome.name for outcome in trace.evaluated] == [rule.name for rule in GUARDRAILS]
    assert not any(outcome.fired for outcome in trace.evaluated)


def test_the_trace_stops_at_the_rule_that_fired() -> None:
    """Short-circuit is real, so a rule after the fired one never ran.

    Listing it as `passed` would be a record of something that did not happen.
    """
    trace = run_guardrails(claim_with(adjustment("CO-16", "450.00", "MA130")))

    assert trace.determination is not None
    assert trace.evaluated[-1].fired
    assert len(trace.evaluated) < len(GUARDRAILS), "later rules must not be reported"
    assert [outcome.name for outcome in trace.evaluated] == ["unappealable-remark"]


def test_the_trace_is_produced_without_an_event_stream() -> None:
    """ADR-0002's module keeps doing one thing.

    A function deciding whether a patient's claim may be appealed does not also
    do I/O, and its tests do not construct a stream to call it.
    """

    parameters = list(inspect.signature(run_guardrails).parameters)

    assert parameters == ["claim"], "the rules take a claim and nothing else"


def test_every_guardrail_is_named() -> None:
    """The inspector prints these, so they are domain names and not identifiers."""
    names = [rule.name for rule in GUARDRAILS]

    assert names == ["unappealable-remark", "nothing-was-refused", "non-appealable-code"]
