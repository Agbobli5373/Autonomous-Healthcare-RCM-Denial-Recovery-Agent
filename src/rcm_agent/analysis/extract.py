"""Reading an EOB document into structured Adjustments.

This module runs **inside the Sandbox**. It is uploaded from the working copy at
run start rather than baked into an image, and it is a plain function over a file
path, so it is unit-testable locally against the committed fixtures without a
live sandbox anywhere in the loop.

Two paths, chosen by whether the document has a text layer:

**Coordinate clustering** for the text-layer documents. The fixtures are drawn
column-major on purpose, so reading order returns every line number, then every
procedure code, then every charge — a row does not survive it. Rows are
recovered by clustering words on their vertical position and reading each
cluster left to right. Nothing here knows the fixture's column positions; that
would be tuning the reader to its own test data. It knows only that a row is a
set of words sharing a baseline, which is true of any remittance.

**OCR** for the scan, which has no text layer at all.

Both hand off to the same field parser, and the parser is driven by what the
codes *look like* rather than by where they sit: a Group Code is one of four
literals, a Reason Code is short and numeric, a Remark Code is letters followed
by digits. Layout changes; the code vocabulary does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GROUP_CODES = ("CO", "PR", "OA", "PI")
"""Repeated from `domain.GroupCode` rather than imported.

This module is uploaded into the Sandbox on its own; `rcm_agent.domain` is
not there to import. The duplication is the price of the module being
shippable, and the four group codes are fixed by X12 rather than by us.
"""

_LINE_NUMBER = re.compile(r"^\d{1,3}$")
_PROCEDURE_CODE = re.compile(r"^[A-V]\d{4}$")
_MONEY = re.compile(r"^\d+(?:,\d{3})*\.\d{2}$")
"""Any number of integer digits.

An earlier version capped it at three, which silently dropped every
adjustment over 999.99 that carried no thousands separator - which is to
say most denials worth appealing. The row clustered correctly and the
parser then discarded it, so nothing failed loudly.
"""
_REMARK_CODE = re.compile(r"^(?:M|MA|N)\d{1,3}$")
_PROCEDURE_IN_TEXT = re.compile(r"([A-V]\d{4})")
_LINE_NUMBER_IN_TEXT = re.compile(r"^\s*(\d{1,3})(?=\D|$)")
"""Anything non-numeric may follow.

It used to require a letter or whitespace, which OCR does not guarantee:
a misread "E" came back as an unencodable glyph and the line number went
with it.
"""

_ROW_TOLERANCE = 6.0
"""Points of vertical slack when deciding two words share a row.

The fixtures stagger baselines by up to 5.5pt to look like a real remittance, so
a tolerance below that would split one row in two. Real scans and real
generators wobble similarly.
"""


@dataclass(frozen=True, slots=True)
class ExtractedAdjustment:
    line_number: int | None
    procedure_code: str | None
    group: str
    reason_code: str
    remark_codes: tuple[str, ...]
    amount: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "line_number": self.line_number,
            "procedure_code": self.procedure_code,
            "group": self.group,
            "reason_code": self.reason_code,
            "remark_codes": list(self.remark_codes),
            "amount": self.amount,
        }


@dataclass(frozen=True, slots=True)
class Extraction:
    source: str
    method: str
    """`text_layer` or `ocr` — recorded so the audit trail says how it was read."""

    lines: tuple[ExtractedAdjustment, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "method": self.method,
            "lines": [line.as_dict() for line in self.lines],
        }


_OCR_PUNCTUATION = ".,;:|_"


def _clean(token: str) -> str:
    """Strip punctuation OCR hangs off the end of a code.

    Safe because it removes characters, never substitutes them. Guessing that a
    letter O in "MAO04" was meant to be a zero would be inventing data, and this
    reader does not do that - it prefers to report nothing over reporting a code
    that was never on the page.
    """
    return token.strip(_OCR_PUNCTUATION)


def parse_row(tokens: list[str]) -> ExtractedAdjustment | None:
    """Turn one row's tokens into an Adjustment, or None if it is not one.

    Driven by the shape of the codes rather than by column position, so a
    different remittance layout does not need a different parser.
    """
    tokens = [_clean(t) for t in tokens]
    group_at = next((i for i, t in enumerate(tokens) if t in GROUP_CODES), None)
    if group_at is None:
        return None

    after = tokens[group_at + 1 :]
    reason = next((t for t in after if _LINE_NUMBER.match(t)), None)
    if reason is None:
        return None

    remarks = tuple(t for t in after if _REMARK_CODE.match(t))
    amounts = [t.replace(",", "") for t in after if _MONEY.match(t)]
    if not amounts:
        return None

    # Searched within the joined text rather than matched per token: OCR runs
    # neighbouring cells together ("001E1392"), and a whole-token match then
    # finds neither the line number nor the procedure code. The code grammar is
    # distinctive enough to locate unaided by whitespace.
    before = " ".join(tokens[:group_at])
    procedure = _PROCEDURE_IN_TEXT.search(before)
    line_number = _LINE_NUMBER_IN_TEXT.match(before)

    return ExtractedAdjustment(
        line_number=int(line_number.group(1)) if line_number else None,
        procedure_code=procedure.group(1) if procedure else None,
        group=tokens[group_at],
        reason_code=reason,
        remark_codes=remarks,
        # The adjustment amount is the last money on the row; the billed,
        # allowed and paid columns come before the CAS block.
        amount=amounts[-1],
    )


def rows_from_words(words: list[dict[str, Any]]) -> list[list[str]]:
    """Cluster words into rows by vertical position, then read each left to right."""
    rows: list[list[dict[str, Any]]] = []
    for word in sorted(words, key=lambda w: (float(w["top"]), float(w["x0"]))):
        placed = False
        for row in rows:
            if abs(float(row[0]["top"]) - float(word["top"])) <= _ROW_TOLERANCE:
                row.append(word)
                placed = True
                break
        if not placed:
            rows.append([word])

    return [[str(w["text"]) for w in sorted(row, key=lambda w: float(w["x0"]))] for row in rows]


def extract_from_text_layer(pdf_path: Path) -> Extraction:
    import pdfplumber

    rows: list[list[str]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            rows.extend(rows_from_words(page.extract_words()))

    lines = [parsed for row in rows if (parsed := parse_row(row)) is not None]
    return Extraction(source=pdf_path.name, method="text_layer", lines=tuple(lines))


def extract_from_scan(pdf_path: Path) -> Extraction:
    """OCR. The scan carries no text layer, so there is nothing else to try."""
    from . import ocr

    rows = [line.split() for line in ocr.text_lines(pdf_path)]
    lines = [parsed for row in rows if (parsed := parse_row(row)) is not None]
    return Extraction(source=pdf_path.name, method="ocr", lines=tuple(lines))


def has_text_layer(pdf_path: Path) -> bool:
    import pdfplumber

    with pdfplumber.open(str(pdf_path)) as pdf:
        return any((page.extract_text() or "").strip() for page in pdf.pages)


def extract(pdf_path: Path) -> Extraction:
    """Read an EOB document, choosing the method the document allows."""
    if has_text_layer(pdf_path):
        return extract_from_text_layer(pdf_path)
    return extract_from_scan(pdf_path)
