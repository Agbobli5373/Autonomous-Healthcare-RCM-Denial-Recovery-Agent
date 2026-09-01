"""The declarative spec the demo's fixtures are generated from.

Three claims, chosen in [#6](../../issues/6) so the run shows an agent that
discriminates rather than one that appeals everything:

| Claim | Governing denial | Expected Action |
| --- | --- | --- |
| `CLM-2026-0001` | `CO-197 + N706` | `appeal`   — prior authorization |
| `CLM-2026-0002` | `CO-16 + MA130` | `close`    — unprocessable, no appeal rights |
| `CLM-2026-0003` | `OA-22 + MA04`  | `rebill`   — another payer is primary |

**Coding is HCPCS Level II.** CMS publishes it freely with descriptors, unlike
CPT, whose descriptors the AMA licenses — and prior authorization is most common
in exactly this territory (durable medical equipment and supplies), so the
scenarios are more realistic here than a CPT-coded physician service would be.
Every descriptor below was checked against a CMS or CMS-derived source rather
than written from memory.

The first claim deliberately carries **two lines with different outcomes**: an
oxygen concentrator paid correctly under a contractual write-off, beside a CPAP
device denied for prior authorization. That exercises the `CO-45` guardrail
against real fixture data rather than only in a unit test — a write-off beside a
denial must not suppress the denial.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from rcm_agent.domain import Action, GroupCode

Rendering = Literal["text_layer", "scan"]


@dataclass(frozen=True, slots=True)
class LineSpec:
    line_number: int
    procedure_code: str
    descriptor: str
    """The CMS long descriptor, kept beside the code so the fixture is readable."""

    charge: str
    allowed: str
    paid: str
    group: GroupCode
    reason_code: str
    adjustment_amount: str
    remark_codes: tuple[str, ...] = ()

    def as_claim_line(self) -> dict[str, Any]:
        return {
            "line_number": self.line_number,
            "procedure_code": self.procedure_code,
            "charge": self.charge,
            "adjustments": [
                {
                    "group": self.group,
                    "reason_code": self.reason_code,
                    "amount": self.adjustment_amount,
                    "remark_codes": list(self.remark_codes),
                }
            ],
        }


@dataclass(frozen=True, slots=True)
class ClaimSpec:
    claim_id: str
    payer: str
    patient_id: str
    patient_name: str
    date_of_service: str
    check_number: str
    rendering: Rendering
    expected_action: Action
    """Asserted by the tests, so a fixture edit that changes the demo's story fails loudly.

    Typed as the domain's `Action` rather than `str` on purpose. This repo has
    twice had a word invented for one of the five — `decline` for `close`, and
    `classification` for a Determination — and both spread before review caught
    them. Typed, the next one is a pyright error at the keystroke instead.
    """

    lines: tuple[LineSpec, ...] = field(default_factory=tuple)

    @property
    def slug(self) -> str:
        return self.claim_id.lower()

    def as_claim(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "payer": self.payer,
            "patient_id": self.patient_id,
            "date_of_service": self.date_of_service,
            "service_lines": [line.as_claim_line() for line in self.lines],
        }


CLAIMS: tuple[ClaimSpec, ...] = (
    ClaimSpec(
        claim_id="CLM-2026-0001",
        payer="Cascade Health Plan",
        patient_id="PAT-40219",
        patient_name="RIVERA, DELORES A",
        date_of_service="2026-03-14",
        check_number="EFT-8842019",
        rendering="text_layer",
        expected_action="appeal",
        lines=(
            LineSpec(
                line_number=1,
                procedure_code="E1390",
                descriptor=(
                    "Oxygen concentrator, single delivery port, capable of delivering "
                    "85 percent or greater oxygen concentration at the prescribed flow rate"
                ),
                charge="450.00",
                allowed="357.50",
                paid="286.00",
                group="CO",
                reason_code="45",
                adjustment_amount="92.50",
            ),
            LineSpec(
                line_number=2,
                procedure_code="E0601",
                descriptor="Continuous positive airway pressure (CPAP) device",
                charge="1250.00",
                allowed="0.00",
                paid="0.00",
                group="CO",
                reason_code="197",
                adjustment_amount="1250.00",
                remark_codes=("N706",),
            ),
        ),
    ),
    ClaimSpec(
        claim_id="CLM-2026-0002",
        payer="Cascade Health Plan",
        patient_id="PAT-51884",
        patient_name="OKONKWO, SAMUEL T",
        date_of_service="2026-03-19",
        check_number="EFT-8842019",
        rendering="text_layer",
        expected_action="close",
        lines=(
            LineSpec(
                line_number=1,
                procedure_code="A4253",
                descriptor=(
                    "Blood glucose test or reagent strips for home blood glucose monitor, "
                    "per 50 strips"
                ),
                charge="78.00",
                allowed="0.00",
                paid="0.00",
                group="CO",
                reason_code="16",
                adjustment_amount="78.00",
                remark_codes=("MA130",),
            ),
            LineSpec(
                line_number=2,
                procedure_code="E1390",
                descriptor=(
                    "Oxygen concentrator, single delivery port, capable of delivering "
                    "85 percent or greater oxygen concentration at the prescribed flow rate"
                ),
                charge="450.00",
                allowed="357.50",
                paid="286.00",
                group="CO",
                reason_code="45",
                adjustment_amount="92.50",
            ),
        ),
    ),
    ClaimSpec(
        claim_id="CLM-2026-0003",
        payer="Cascade Health Plan",
        patient_id="PAT-33947",
        patient_name="HALVORSEN, MARGIT",
        date_of_service="2026-03-22",
        check_number="EFT-8842019",
        # The scan sits here on purpose: OA-22 is the least narratively critical
        # of the three, so an OCR wobble cannot take the hero story down with it.
        rendering="scan",
        expected_action="rebill",
        lines=(
            LineSpec(
                line_number=1,
                procedure_code="E1392",
                descriptor="Portable oxygen concentrator, rental",
                charge="210.00",
                allowed="0.00",
                paid="0.00",
                group="OA",
                reason_code="22",
                adjustment_amount="210.00",
                remark_codes=("MA04",),
            ),
            LineSpec(
                line_number=2,
                procedure_code="E0601",
                descriptor="Continuous positive airway pressure (CPAP) device",
                charge="1250.00",
                allowed="992.00",
                paid="793.60",
                group="CO",
                reason_code="45",
                adjustment_amount="258.00",
            ),
        ),
    ),
)
