"""Turning the spec into the EOB documents the Sandbox has to read.

Two renderings, and the difference between them is the point.

**Text layer.** reportlab, drawing the table **column by column**. A PDF has no
table — it has a stream of positioned draw operations, and a text extractor
replays that stream. Emitting column-major means reading order groups cells that
share a column, so a Reason Code arrives next to the *other row's* Reason Code
rather than next to its own amount. Recovering a row then requires the glyph
coordinates: real table extraction, not a string split.

An earlier version drew row-wise and merely staggered the baselines. It looked
messy and parsed perfectly — a five-line reader recovered every field, because
visual disorder is not structural disorder. Coordinate-aware extraction
(pdfplumber's table finder, or pypdf's layout mode) still reads these correctly,
and should: that is the capability the Sandbox leg exists to show.

**Scan.** Drawn as an image with Pillow, then degraded — rotated a fraction of a
degree, blurred, speckled, contrast-flattened — and saved as an image-only PDF.
There is no text layer at all, so it can only be read by OCR.

Both are deterministic: reportlab runs with `invariant=1` so it embeds no
timestamp, and every random choice in the degradation comes from a seeded
generator. Regenerating produces the same bytes, which is what lets the outputs
be committed and reviewed in a diff.
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from rcm_agent.fixtures.spec import ClaimSpec, LineSpec

DEGRADATION_SEED = 20260314
"""Fixed so the scan is byte-identical on every regeneration."""

_PAGE_WIDTH, _PAGE_HEIGHT = LETTER
_LEFT_MARGIN = 46.0
_DESCRIPTOR_WIDTH = 74
"""Characters per wrapped descriptor line, shared by both renderings."""

# Column origins, in points from the left margin. Deliberately tight, and the
# CAS block is split across four narrow columns rather than one wide cell.
_COLUMNS: dict[str, float] = {
    "line": 46,
    "proc": 74,
    "dates": 118,
    "charge": 214,
    "allowed": 268,
    "paid": 322,
    "group": 372,
    "reason_code": 404,
    "remark_codes": 440,
    "cas_amount": 492,
}

_BASELINE_STAGGER: dict[str, float] = {
    # Cosmetic: real remittances wrap and misalign, and this makes the page look
    # the part. It does *not* create the parsing difficulty — column-major
    # emission does. Do not mistake this for the mechanism.
    "group": 3.5,
    "reason_code": -2.0,
    "remark_codes": 3.5,
    "cas_amount": -2.0,
}


_HEADINGS: dict[str, str] = {
    "line": "LN",
    "proc": "HCPCS",
    "dates": "SERVICE DATES",
    "charge": "BILLED",
    "allowed": "ALLOWED",
    "paid": "PAID",
    # The abbreviations a payer actually prints. The dict keys above stay in the
    # glossary's words; only what lands on the page is payer verisimilitude.
    "group": "GRP",
    "reason_code": "CARC",
    "remark_codes": "RMK",
    "cas_amount": "ADJ AMT",
}


def wrap_descriptor(descriptor: str, width: int = _DESCRIPTOR_WIDTH) -> list[str]:
    """Wrap a CMS descriptor across lines, never truncating it.

    Both renderings share this. The scan used to cut at a fixed 88 characters,
    which silently lost the tail of the longest CMS wording — the kind of quiet
    corruption of source data this project cannot afford in a fixture.
    """
    wrapped: list[str] = []
    current = ""
    for word in descriptor.split():
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > width:
            wrapped.append(current)
            current = word
        else:
            current = candidate
    if current:
        wrapped.append(current)
    return wrapped


def _draw_header(pdf: Canvas, claim: ClaimSpec, top: float) -> float:
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(_LEFT_MARGIN, top, claim.payer.upper())
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(_LEFT_MARGIN, top - 12, "EXPLANATION OF BENEFITS - PROVIDER REMITTANCE ADVICE")
    pdf.drawString(400, top, f"CHECK/EFT  {claim.check_number}")
    pdf.drawString(400, top - 12, "PAGE 001 OF 001")

    pdf.setFont("Helvetica", 8)
    pdf.drawString(_LEFT_MARGIN, top - 36, f"PATIENT  {claim.patient_name}")
    pdf.drawString(_LEFT_MARGIN, top - 48, f"MEMBER ID  {claim.patient_id}")
    pdf.drawString(300, top - 36, f"CLAIM  {claim.claim_id}")
    pdf.drawString(300, top - 48, f"SERVICE DATE  {claim.date_of_service}")

    pdf.setLineWidth(0.4)
    pdf.line(_LEFT_MARGIN, top - 58, _PAGE_WIDTH - _LEFT_MARGIN, top - 58)
    return top - 72


def _draw_column_headings(pdf: Canvas, y: float) -> float:
    pdf.setFont("Helvetica-Bold", 6.5)
    for key, label in _HEADINGS.items():
        pdf.drawString(_COLUMNS[key], y, label)
    pdf.setLineWidth(0.3)
    pdf.line(_LEFT_MARGIN, y - 4, _PAGE_WIDTH - _LEFT_MARGIN, y - 4)
    return y - 16


_RIGHT_ALIGNED = frozenset({"charge", "allowed", "paid", "cas_amount"})
_CELL_RIGHT_EDGE = {"charge": 40, "allowed": 40, "paid": 40, "cas_amount": 46}


def _cell(line: LineSpec, claim: ClaimSpec, key: str) -> str:
    match key:
        case "line":
            return f"{line.line_number:03d}"
        case "proc":
            return line.procedure_code
        case "dates":
            return f"{claim.date_of_service} {claim.date_of_service}"
        case "charge":
            return line.charge
        case "allowed":
            return line.allowed
        case "paid":
            return line.paid
        case "group":
            return line.group
        case "reason_code":
            return line.reason_code
        case "remark_codes":
            return " ".join(line.remark_codes) or "-"
        case _:
            return line.adjustment_amount


def _draw_rows(pdf: Canvas, claim: ClaimSpec, top: float) -> float:
    """Draw the service lines **column by column**, not row by row.

    This is the difficulty, and it has to be structural rather than visual. A
    PDF has no table: it has a stream of positioned draw operations, and a text
    extractor replays that stream. Drawing row-wise — however far apart the
    columns look on the page — emits each row's cells consecutively, so
    `extract_text()` hands back tidy rows and a string split does the parsing.

    Emitting column-major means the stream carries every line number, then every
    procedure code, then every charge. Reading order now groups cells that share
    a *column*, and recovering which amount belongs to which Reason Code takes
    the glyph coordinates — which is real table extraction, and the thing the
    Sandbox leg exists to demonstrate.

    Real remittances are like this by accident. Here it is on purpose.
    """
    heights = [len(wrap_descriptor(line.descriptor)) for line in claim.lines]
    tops: list[float] = []
    y = top
    for height in heights:
        tops.append(y)
        y -= 18 + (height * 8)

    for key in _HEADINGS:
        pdf.setFont("Helvetica", 7.5 if key in ("line", "proc", "dates") else 7)
        stagger = _BASELINE_STAGGER.get(key, 0.0)
        for line, row_top in zip(claim.lines, tops, strict=True):
            text = _cell(line, claim, key)
            if key in _RIGHT_ALIGNED:
                pdf.drawRightString(_COLUMNS[key] + _CELL_RIGHT_EDGE[key], row_top + stagger, text)
            else:
                pdf.drawString(_COLUMNS[key], row_top + stagger, text)

    # Descriptors last, so they sit between the table and whatever follows and
    # break the stream once more.
    pdf.setFont("Helvetica-Oblique", 6.5)
    for line, row_top in zip(claim.lines, tops, strict=True):
        for offset, chunk in enumerate(wrap_descriptor(line.descriptor)):
            pdf.drawString(_COLUMNS["proc"], row_top - 9 - (offset * 8), chunk)

    return y


def render_text_layer(claim: ClaimSpec, destination: Path) -> None:
    pdf = Canvas(
        str(destination),
        pagesize=LETTER,
        # No creation timestamp and a fixed document id, so the bytes are stable.
        invariant=1,
    )
    pdf.setTitle(f"EOB {claim.claim_id}")
    pdf.setAuthor(claim.payer)

    y = _draw_header(pdf, claim, _PAGE_HEIGHT - 60)
    y = _draw_column_headings(pdf, y)
    y = _draw_rows(pdf, claim, y)

    pdf.setFont("Helvetica", 6.5)
    pdf.drawString(
        _LEFT_MARGIN, 60, "CARC/RARC definitions available at wpc-edi.com. Retain for your records."
    )
    pdf.showPage()
    pdf.save()


def _scan_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        # Pillow ships a scalable default from 10.1 onward, so this needs no
        # system font and behaves the same on every machine.
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover - very old Pillow
        return ImageFont.load_default()


def _draw_scan_page(claim: ClaimSpec) -> Image.Image:
    # 1700x2200 is roughly 200 DPI for a letter page - the resolution a cheap
    # office scanner produces, and what sets how hard the OCR step is.
    page = Image.new("L", (1700, 2200), color=250)
    draw = ImageDraw.Draw(page)
    heading = _scan_font(34)
    body = _scan_font(26)

    draw.text((110, 120), claim.payer.upper(), font=heading, fill=25)
    draw.text((110, 175), "EXPLANATION OF BENEFITS", font=body, fill=40)
    draw.text((1050, 120), f"CHECK/EFT {claim.check_number}", font=body, fill=40)

    draw.text((110, 265), f"PATIENT   {claim.patient_name}", font=body, fill=35)
    # "MEMBER ID" is the payer's own wording on the page; the glossary term for
    # the person is Patient, and that is what the domain types use.
    draw.text((110, 305), f"MEMBER ID {claim.patient_id}", font=body, fill=35)
    draw.text((900, 265), f"CLAIM {claim.claim_id}", font=body, fill=35)
    draw.text((900, 305), f"SERVICE DATE {claim.date_of_service}", font=body, fill=35)
    draw.line((110, 360, 1590, 360), fill=90, width=2)

    draw.text(
        (110, 400),
        "LN  HCPCS   BILLED   ALLOWED  PAID    GRP CARC RMK   ADJ AMT",
        font=body,
        fill=30,
    )

    y = 455
    for line in claim.lines:
        row = (
            f"{line.line_number:03d} {line.procedure_code:<8}{line.charge:>9}"
            f"{line.allowed:>10}{line.paid:>8}   {line.group:<4}{line.reason_code:<5}"
            f"{' '.join(line.remark_codes) or '-':<6}{line.adjustment_amount:>9}"
        )
        draw.text((110, y), row, font=body, fill=30)
        # Wrapped, not truncated: cutting a CMS descriptor at a fixed width lost
        # the tail of the longest wording, and nothing would have caught it.
        for offset, chunk in enumerate(wrap_descriptor(line.descriptor, width=88)):
            draw.text((150, y + 38 + (offset * 30)), chunk, font=_scan_font(22), fill=60)
        y += 100 + (30 * max(0, len(wrap_descriptor(line.descriptor, width=88)) - 1))

    return page


def render_scan(claim: ClaimSpec, destination: Path) -> None:
    """A page that only OCR can read: no text layer, and deliberately imperfect."""
    rng = random.Random(DEGRADATION_SEED)
    page = _draw_scan_page(claim)

    # A sheet fed slightly crooked, then a cheap sensor: soft focus, speckle,
    # and the flattened contrast of a photocopy.
    page = page.rotate(rng.uniform(-0.8, 0.8), resample=Image.Resampling.BICUBIC, fillcolor=250)
    page = page.filter(ImageFilter.GaussianBlur(radius=0.7))

    pixels = page.load()
    assert pixels is not None
    width, height = page.size
    for _ in range(int(width * height * 0.004)):
        x, y = rng.randrange(width), rng.randrange(height)
        pixels[x, y] = rng.randrange(90, 190)

    # An explicit lookup table rather than a lambda: the flattened contrast of a
    # photocopy, and a shape the type checker can actually see through.
    page = page.point(  # pyright: ignore[reportUnknownMemberType]  # Pillow's lut overload
        [int(28 + value * 0.86) for value in range(256)]
    )

    # Wrapped by reportlab rather than saved through Pillow: Pillow's PDF writer
    # stamps a creation date, which would make the fixture differ on every
    # regeneration and defeat the point of committing it.
    pdf = Canvas(str(destination), pagesize=LETTER, invariant=1)
    pdf.setTitle(f"EOB {claim.claim_id} (scanned)")
    pdf.drawImage(  # pyright: ignore[reportUnknownMemberType]  # reportlab ships no stubs
        ImageReader(page.convert("L")),
        0,
        0,
        width=_PAGE_WIDTH,
        height=_PAGE_HEIGHT,
        preserveAspectRatio=False,
    )
    pdf.showPage()
    pdf.save()
