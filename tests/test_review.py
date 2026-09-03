"""A human's verdict on a Determination.

`Review`, not "approval": `CONTEXT.md` already gives *approval* to Authorization
- a payer's advance approval for a service - and proving one covered the date of
service is the entire prior-authorization story. Two unrelated things must not
share one word in a glossary this narrow.

The Determination is never touched. It is a judgement made at a moment, and a
second actor's decision about it is a second record; mutating the first would
make `action: appeal` ambiguous between what the agent judged and what survived
review.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from rcm_agent.domain import Determination, Priority
from rcm_agent.review import (
    Review,
    StaleReview,
    current_review,
    digest_of,
    review_history,
    reviewed,
    store_review,
)

WHEN = datetime(2026, 3, 20, 9, 30, tzinfo=UTC)


def a_determination(action: str = "appeal", guardrail: str | None = None) -> Determination:
    return Determination(
        claim_id="CLM-2026-0001",
        action=action,  # pyright: ignore[reportArgumentType]
        rationale="the authorization covered the date of service",
        evidence_required=("Authorization record",),
        guardrail=guardrail,
        priority=None
        if guardrail
        else Priority(amount_at_stake=Decimal("1250.00"), likelihood=0.45),
    )


def a_review(**kwargs: object) -> Review:
    defaults: dict[str, object] = {
        "claim_id": "CLM-2026-0001",
        "determination": a_determination(),
        "verdict": "approved",
        "reason": "",
        "reviewer": "isaac",
        "run_id": "2026-01-01T00-00-00Z",
        "at": WHEN,
    }
    return reviewed(**{**defaults, **kwargs})  # pyright: ignore[reportArgumentType]


# --- what a Review is -------------------------------------------------------


def test_a_review_names_who_decided_what_and_when() -> None:
    review = a_review()

    assert review.claim_id == "CLM-2026-0001"
    assert review.verdict == "approved"
    assert review.reviewer == "isaac"
    assert review.reviewed_at == WHEN.isoformat()
    assert review.run_id == "2026-01-01T00-00-00Z"


def test_a_rejection_must_carry_a_reason() -> None:
    """A rejected appeal that vanishes teaches nobody anything.

    The reasons are the only evidence that would ever improve the agent, so a
    rejection without one is refused rather than stored empty.
    """
    with pytest.raises(ValueError, match="reason"):
        a_review(verdict="rejected", reason="   ")


def test_a_rejection_may_name_the_action_the_reviewer_would_have_chosen() -> None:
    """Recorded on the Review, not as a second Determination.

    The agent did not judge it, and a Determination claiming otherwise would put
    a human's opinion where a record of the agent's reasoning belongs.
    """
    review = a_review(
        verdict="rejected", reason="no authorization was ever obtained", counter_action="rebill"
    )

    assert review.counter_action == "rebill"


def test_an_approval_needs_no_reason() -> None:
    assert a_review(verdict="approved").reason == ""


def test_a_claim_a_rule_closed_cannot_be_reviewed() -> None:
    """A rule was never a judgement, so there is nothing to sign off.

    Asking a human to approve one invents a decision that does not exist and
    quietly reframes a rule as an opinion - the failure ADR-0002 exists to
    prevent. The console offers no control; this refuses even if one appeared.
    """
    with pytest.raises(ValueError, match="rule"):
        a_review(
            determination=a_determination(action="close", guardrail="unappealable-remark:MA130")
        )


# --- the digest, which is the safety property -------------------------------


def test_a_review_carries_a_digest_of_what_it_approved() -> None:
    determination = a_determination()

    assert a_review(determination=determination).determination_digest == digest_of(determination)


def test_the_digest_is_taken_over_the_file_the_run_actually_wrote(tmp_path: Path) -> None:
    """Checked against the artifact on disk, not against a shared helper.

    The digest's whole justification is that anyone holding `claims/<id>.json`
    can recompute it. Asserting that against the same function that writes the
    file would pass however the two drifted; this reads the bytes back, so a
    change to the writer's serialisation fails here rather than silently making
    every digest describe a file it no longer matches.
    """
    from rcm_agent.run_directory import RunDirectory
    from rcm_agent.transport import sha256_of_bytes

    determination = a_determination()
    run = RunDirectory.create(tmp_path, started_at=WHEN)
    written = run.write_claim(determination)

    assert digest_of(determination) == sha256_of_bytes(written.read_bytes())


def test_a_changed_determination_changes_the_digest() -> None:
    assert digest_of(a_determination()) != digest_of(a_determination(action="rebill"))


def test_a_verdict_does_not_authorise_a_determination_it_never_saw() -> None:
    """The bug this exists to prevent, stated as a test.

    Keyed on the claim alone, yesterday's `approved` would sit over a
    Determination a re-run replaced - and filing on it is a void appeal on a
    patient's claim, reached by ordinary bookkeeping rather than by anything a
    guardrail inspects.
    """
    review = a_review(determination=a_determination())

    with pytest.raises(StaleReview, match="no longer"):
        review.authorises(a_determination(action="rebill"))


def test_a_verdict_authorises_the_determination_it_did_see() -> None:
    determination = a_determination()

    a_review(determination=determination).authorises(determination)


# --- the store --------------------------------------------------------------


def test_a_review_is_written_outside_the_run_directories(tmp_path: Path) -> None:
    """A completed run is never appended to.

    Finality is a designed property: `run.json` carries a terminal status and the
    reliability measurement reads those summaries. A verdict arriving hours later
    must not reach back into a run that has closed.
    """
    written = store_review(tmp_path, a_review())

    assert written == tmp_path / "clm-2026-0001.json"
    assert written.is_file()


def test_the_store_keeps_every_verdict_and_the_last_one_is_current(tmp_path: Path) -> None:
    """Append-only, because an audit trail that can be silently rewritten is not one."""
    store_review(tmp_path, a_review(verdict="approved"))
    store_review(
        tmp_path, a_review(verdict="rejected", reason="the authorization does not cover this DOS")
    )

    history = review_history(tmp_path, "CLM-2026-0001")

    assert [entry.verdict for entry in history] == ["approved", "rejected"]
    assert current_review(tmp_path, "CLM-2026-0001") is not None
    assert current_review(tmp_path, "CLM-2026-0001").verdict == "rejected"  # pyright: ignore[reportOptionalMemberAccess]


def test_a_claim_nobody_has_reviewed_has_no_verdict(tmp_path: Path) -> None:
    assert review_history(tmp_path, "CLM-2026-0009") == ()
    assert current_review(tmp_path, "CLM-2026-0009") is None


def test_a_stored_review_survives_a_round_trip(tmp_path: Path) -> None:
    original = a_review(
        verdict="rejected", reason="no authorization exists", counter_action="corrected_claim"
    )
    store_review(tmp_path, original)

    assert review_history(tmp_path, "CLM-2026-0001") == (original,)


def test_the_store_is_readable_by_someone_who_knows_the_domain(tmp_path: Path) -> None:
    """A person opening the file should not need this module to understand it."""
    store_review(tmp_path, a_review(verdict="rejected", reason="no auth"))

    written = json.loads((tmp_path / "clm-2026-0001.json").read_text(encoding="utf-8"))

    assert written[0]["verdict"] == "rejected"
    assert written[0]["reason"] == "no auth"
    assert written[0]["reviewer"] == "isaac"
    assert len(written[0]["determination_digest"]) == 64


def test_a_verdict_can_be_given_on_the_record_a_run_wrote(tmp_path: Path) -> None:
    """The server has the dict, not the object.

    Reconstructing a `Determination` just to hash it would put a parser between
    the artifact and its own digest - and a parser is a thing that can disagree.
    """
    determination = a_determination()
    recorded = determination.to_dict()

    from_record = reviewed(
        claim_id="CLM-2026-0001",
        determination=recorded,
        verdict="approved",
        reviewer="isaac",
        run_id="2026-01-01T00-00-00Z",
        at=WHEN,
    )

    assert from_record.determination_digest == digest_of(determination)
    from_record.authorises(recorded)


def test_a_rule_closed_record_is_refused_the_same_way() -> None:
    ruled = a_determination(action="close", guardrail="unappealable-remark:MA130").to_dict()

    with pytest.raises(ValueError, match="rule"):
        reviewed(
            claim_id="CLM-2026-0001",
            determination=ruled,
            verdict="approved",
            reviewer="isaac",
            run_id="r",
            at=WHEN,
        )


def test_a_determination_recorded_before_it_carried_a_claim_id_can_be_reviewed() -> None:
    """A run directory outlives the code that wrote it.

    Determinations written before the event settled on `Determination.to_dict()`
    carry no `claim_id` in their detail. Reading one out of the record raised,
    and the console answered a verdict with a 500 - found by clicking Approve on
    a real run rather than by any test.
    """
    older = {
        "action": "appeal",
        "rationale": "the authorization covered the date of service",
        "evidence_required": ["Authorization record"],
        "guardrail": None,
        "priority": None,
    }

    review = reviewed(
        claim_id="CLM-2026-0001",
        determination=older,
        verdict="approved",
        reviewer="console",
        run_id="2026-01-01T00-00-00Z",
        at=WHEN,
    )

    assert review.claim_id == "CLM-2026-0001"
    assert review.determination_digest == digest_of(older)
