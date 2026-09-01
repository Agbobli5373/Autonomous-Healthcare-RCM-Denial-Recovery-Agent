"""The committed fixtures, as the mocks see them.

Both mocks serve the same three claims the extraction reads, so the portal, the
EOB documents and the claim JSON cannot drift apart. There is one source and it
is `data/fixtures/`.

The claims are loaded through `claim_io`, not parsed again here. An earlier
version re-implemented that parsing and lost its validation with it — and a
second copy of "what a valid claim looks like" is exactly the kind of drift this
module exists to prevent. `PortalClaim` is a thin presentation wrapper over the
domain's `Claim`: it adds what a payer's UI needs to show and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from rcm_agent.claim_io import load_claim
from rcm_agent.domain import Claim, ServiceLine
from rcm_agent.fixtures.naming import eob_filename
from rcm_agent.practice_io import PracticeRecord, load_practice_record

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "data" / "fixtures"


@dataclass(frozen=True, slots=True)
class PortalClaim:
    """A Claim, plus the handful of things a payer's screen shows about it."""

    claim: Claim

    @property
    def claim_id(self) -> str:
        return self.claim.claim_id

    @property
    def patient_id(self) -> str:
        return self.claim.patient_id

    @property
    def date_of_service(self) -> date:
        return self.claim.date_of_service

    @property
    def service_lines(self) -> tuple[ServiceLine, ...]:
        return self.claim.service_lines

    @property
    def slug(self) -> str:
        return self.claim_id.lower()

    @property
    def eob_path(self) -> Path:
        return FIXTURES_ROOT / "eobs" / eob_filename(self.claim_id)

    @property
    def denied_total(self) -> Decimal:
        """What the payer refused.

        `Claim.amount_denied` already knows which adjustments are refusals — a
        write-off and a patient-responsibility amount reduce what the payer pays
        without refusing anything. Re-deriving that here would put a second copy
        of a domain rule in a mock's presentation layer.
        """
        return self.claim.amount_denied

    @property
    def status(self) -> str:
        """What a payer portal would print in its status column."""
        return "DENIED" if self.claim.denials else "PAID"


@lru_cache(maxsize=1)
def worklist() -> tuple[PortalClaim, ...]:
    """Every committed claim, newest service date first.

    The ordering is not cosmetic. A payer worklist is newest first, and that puts
    the `CO-197` prior-authorization claim — the oldest of the three — on the
    second page, where the agent has to paginate to reach it. It falls out of the
    data rather than being pinned there, so a fixture change cannot leave the
    requirement quietly unmet.
    """
    claims = [load_claim(path) for path in sorted((FIXTURES_ROOT / "claims").glob("*.json"))]
    return tuple(
        PortalClaim(claim)
        for claim in sorted(claims, key=lambda c: c.date_of_service, reverse=True)
    )


def find(claim_id: str) -> PortalClaim | None:
    return next((c for c in worklist() if c.claim_id == claim_id), None)


@lru_cache(maxsize=1)
def practice_records() -> tuple[PracticeRecord, ...]:
    """Every committed practice record, in claim order.

    The provider's view of the same three episodes the payer portal serves. Both
    mocks read the same `data/fixtures/`, which is what stops the payer's story
    and the practice's story from drifting apart between takes.
    """
    paths = sorted((FIXTURES_ROOT / "practice").glob("*.json"))
    return tuple(load_practice_record(path) for path in paths)


def find_record(claim_id: str) -> PracticeRecord | None:
    return next((r for r in practice_records() if r.claim_id == claim_id), None)


def search_records(query: str) -> list[PracticeRecord]:
    """Match on patient id, claim number or patient name.

    Three keys because the agent arrives holding a claim number and a person
    reading over its shoulder has a name - a lookup that only accepted the one
    key the demo happens to use would not be a lookup.
    """
    wanted = query.strip().casefold()
    if not wanted:
        return []
    return [
        record
        for record in practice_records()
        if wanted in record.patient_id.casefold()
        or wanted in record.claim_id.casefold()
        or wanted in record.patient_name.casefold()
    ]
