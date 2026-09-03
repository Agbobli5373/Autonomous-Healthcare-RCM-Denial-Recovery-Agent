"""A human's verdict on a Determination.

**`Review`, not "approval".** `CONTEXT.md` already defines Authorization as "a
payer's advance approval for a service" - in this domain an approval *is* a prior
authorization, and proving one covered the date of service is the entire CO-197
story. Two unrelated things must not share a word in a glossary this narrow. The
person is a Reviewer.

**The Determination is never touched.** It is a judgement made at a moment, and
the project already treats it that way: frozen, written once to
`claims/<id>.json`. Mutating it with a status would make the artifact ambiguous -
is `action: appeal` what the agent judged, or what survived review? Two actors
made two decisions and they get two records.

**A Review names the Determination by digest, and that is a safety property
rather than bookkeeping.** Keyed on the claim alone, yesterday's `approved`
would sit over a Determination that a re-run had replaced, and whatever acts on
it would file an appeal a human approved for a reading that no longer exists -
a void appeal on a patient's claim, reached by an ordinary oversight rather than
by anything a guardrail inspects.

Nothing yet acts on a Review. Filing an approved appeal was ruled out of scope
for the console effort, so approving records a verdict and stops there - and the
console has to say so rather than implying a loop that closes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from rcm_agent.domain import Action, Determination
from rcm_agent.run_directory import claim_json, write_atomically
from rcm_agent.transport import sha256_of_bytes

Verdict = Literal["approved", "rejected"]

VERDICTS: tuple[Verdict, ...] = ("approved", "rejected")


class StaleReview(RuntimeError):
    """The Determination this verdict was given for is not the one in hand.

    Raised rather than returned, because every caller reaching this is about to
    act on a claim and none of them should carry on.
    """


def digest_of(determination: Determination | Mapping[str, Any]) -> str:
    """The Determination, hashed as the run wrote it down.

    Over the serialisation `claims/<id>.json` holds - the writer's own function
    rather than a second copy of it - so anyone holding the artifact can recompute
    the number. Two copies would be joined by coincidence, and the digest would
    quietly stop describing the file the day one of them changed.

    Takes the record as readily as the object, because the two callers have
    different things in hand: the domain has a `Determination`, and a server
    reading a run back has the dict it wrote. Reconstructing the object only to
    hash it would put a parser between the artifact and its own digest - and a
    parser is a thing that can disagree.
    """
    recorded = (
        determination.to_dict() if isinstance(determination, Determination) else dict(determination)
    )
    return sha256_of_bytes(claim_json(recorded).encode("utf-8"))


@dataclass(frozen=True, slots=True)
class Review:
    """What a person decided about one Determination, and when."""

    claim_id: str
    reviewed_at: str
    reviewer: str
    verdict: Verdict
    reason: str
    determination_digest: str
    run_id: str
    counter_action: Action | None = None

    def authorises(self, determination: Determination | Mapping[str, Any]) -> None:
        """Refuse unless this verdict was given for exactly this Determination."""
        actual = digest_of(determination)
        if actual != self.determination_digest:
            raise StaleReview(
                f"{self.claim_id}: this verdict was given for a Determination that is no "
                f"longer the one on file. reviewed sha256={self.determination_digest} "
                f"current sha256={actual}. Acting on it would file against a reading nobody "
                "approved."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "reviewed_at": self.reviewed_at,
            "reviewer": self.reviewer,
            "verdict": self.verdict,
            "reason": self.reason,
            "counter_action": self.counter_action,
            "determination_digest": self.determination_digest,
            "run_id": self.run_id,
        }


def reviewed(
    *,
    claim_id: str,
    determination: Determination | Mapping[str, Any],
    verdict: Verdict,
    reviewer: str,
    run_id: str,
    at: datetime,
    reason: str = "",
    counter_action: Action | None = None,
) -> Review:
    """A verdict on this Determination, refusing the ones that make no sense.

    Built from the Determination rather than from a digest so the two cannot
    disagree, and so a claim a rule closed can be refused here as well as being
    given no control on screen.

    `claim_id` is passed rather than taken from the record: an older run's
    determination may not carry one, and a verdict is about a claim the caller
    already knows the name of.
    """
    recorded = (
        determination.to_dict() if isinstance(determination, Determination) else dict(determination)
    )
    # The claim is named by the caller, not read out of the record. A run
    # directory outlives the code that wrote it, and determinations recorded
    # before the event settled on `Determination.to_dict()` carry no `claim_id`
    # at all - reading one raised, and the console answered a verdict with a 500.
    guardrail = recorded.get("guardrail")
    if guardrail is not None:
        raise ValueError(
            f"{claim_id} was closed by the rule {guardrail!r}. A rule was never a "
            "judgement, so there is nothing to sign off - asking for a verdict would "
            "invent a decision that does not exist."
        )
    if verdict not in VERDICTS:
        raise ValueError(f"{verdict!r} is not a verdict; expected one of {VERDICTS}")
    if verdict == "approved" and counter_action is not None:
        raise ValueError(
            "an approval cannot name a counter-action. The Reviewer agreed with the "
            "Action the agent chose, so there is no other one they would have picked - "
            "recording one would put a disagreement inside an agreement."
        )
    if verdict == "rejected" and not reason.strip():
        raise ValueError(
            "a rejection must carry a reason. A rejected appeal that vanishes teaches "
            "nobody anything, and the reasons are the only evidence that would improve "
            "the agent."
        )

    return Review(
        claim_id=claim_id,
        reviewed_at=at.isoformat(),
        reviewer=reviewer,
        verdict=verdict,
        reason=reason.strip(),
        determination_digest=digest_of(recorded),
        run_id=run_id,
        counter_action=counter_action,
    )


def store_review(reviews_dir: Path, review: Review) -> Path:
    """Append a verdict to the claim's history and return the file.

    Outside the run directories on purpose. A completed run is never appended to:
    finality is a designed property - `run.json` carries a terminal status and
    the reliability measurement reads those summaries - and a verdict arriving
    hours later must not reach back into a run that has closed.

    Append-only, because an audit trail that can be silently rewritten is not
    one. A reconsidered rejection stays visible rather than being erased - and
    the file is replaced atomically, so the history survives a process killed
    mid-write rather than being truncated to nothing.
    """
    reviews_dir.mkdir(parents=True, exist_ok=True)
    path = _path_for(reviews_dir, review.claim_id)
    history = [entry.to_dict() for entry in review_history(reviews_dir, review.claim_id)]
    history.append(review.to_dict())
    # Written atomically because this file is the whole history, not one entry.
    # A plain write truncates first, so a process killed mid-write would lose
    # every verdict ever recorded for the claim - the exact failure the
    # append-only store exists to prevent, reached by the write itself.
    write_atomically(path, json.dumps(history, indent=2) + "\n")
    return path


def review_history(reviews_dir: Path, claim_id: str) -> tuple[Review, ...]:
    """Every verdict recorded for this claim, oldest first."""
    path = _path_for(reviews_dir, claim_id)
    if not path.is_file():
        return ()
    recorded: Any = json.loads(path.read_text(encoding="utf-8"))
    return tuple(_review_from(entry) for entry in recorded)


def current_review(reviews_dir: Path, claim_id: str) -> Review | None:
    """The verdict that stands, which is simply the last one recorded."""
    history = review_history(reviews_dir, claim_id)
    return history[-1] if history else None


def _path_for(reviews_dir: Path, claim_id: str) -> Path:
    return reviews_dir / f"{claim_id.lower()}.json"


def _review_from(recorded: dict[str, Any]) -> Review:
    return Review(
        claim_id=str(recorded["claim_id"]),
        reviewed_at=str(recorded["reviewed_at"]),
        reviewer=str(recorded["reviewer"]),
        verdict=recorded["verdict"],
        reason=str(recorded["reason"]),
        determination_digest=str(recorded["determination_digest"]),
        run_id=str(recorded["run_id"]),
        counter_action=recorded.get("counter_action"),
    )


def all_current_reviews(reviews_dir: Path) -> dict[str, Review]:
    """The verdict that stands for every claim anyone has reviewed."""
    if not reviews_dir.is_dir():
        return {}
    standing: dict[str, Review] = {}
    for path in sorted(reviews_dir.glob("*.json")):
        history = review_history(reviews_dir, path.stem)
        if history:
            standing[history[-1].claim_id] = history[-1]
    return standing
