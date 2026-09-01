# pypdfium2 and pytesseract ship no usable type information, so strict mode has
# nothing to check here. This module exists to keep that boundary in one place:
# it takes a path and returns plain strings, and everything downstream - the
# parser that turns those strings into Adjustments - stays fully typed.
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false

"""Rendering a scanned document and reading it with OCR.

Only reached when a document has no text layer. It is the slow, lossy path and
the one that can quietly return a code that was never on the page, so the caller
keeps the method it used in the audit trail.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_DPI = 300
"""Enough for the scanned fixture. Higher was measurably worse: at 600 DPI
tesseract read the amount 210.00 as 2100000 and merged neighbouring cells."""


def text_lines(pdf_path: Path, *, dpi: int = DEFAULT_DPI) -> list[str]:
    """Every non-empty line of text OCR can find, page by page."""
    import pypdfium2
    import pytesseract

    lines: list[str] = []
    document = pypdfium2.PdfDocument(str(pdf_path))
    try:
        for page in document:
            # pypdfium2's stub types `scale` as int; it accepts a float.
            image = page.render(scale=dpi / 72).to_pil()  # pyright: ignore[reportArgumentType]
            text = str(pytesseract.image_to_string(image))
            lines.extend(line for line in text.splitlines() if line.strip())
    finally:
        document.close()
    return lines
