from __future__ import annotations

from pathlib import Path

import pytest

from rcm_agent.analysis.extract import extract, has_text_layer, parse_row, rows_from_words

FIXTURES = Path(__file__).resolve().parent.parent / "data" / "fixtures" / "eobs"


def row(*tokens: str) -> list[str]:
    return list(tokens)


# --- the field parser ------------------------------------------------------


def test_a_row_without_a_group_code_is_not_an_adjustment() -> None:
    assert parse_row(row("001", "E1390", "450.00", "357.50")) is None


def test_a_row_yields_the_full_cas_triple() -> None:
    parsed = parse_row(row("002", "E0601", "1250.00", "CO", "197", "N706", "1250.00"))

    assert parsed is not None
    assert (parsed.group, parsed.reason_code, parsed.remark_codes) == ("CO", "197", ("N706",))


def test_amounts_over_a_thousand_are_recognised() -> None:
    """The money pattern once capped the integer part at three digits.

    Every adjustment over 999.99 without a thousands separator was silently
    dropped: the row clustered correctly and the parser discarded it, so nothing
    failed loudly. That is most denials worth appealing.
    """
    parsed = parse_row(row("CO", "197", "N706", "12500.00"))

    assert parsed is not None
    assert parsed.amount == "12500.00"


def test_a_thousands_separator_is_removed() -> None:
    parsed = parse_row(row("CO", "197", "1,250.00"))

    assert parsed is not None
    assert parsed.amount == "1250.00"


def test_the_adjustment_amount_is_the_last_money_on_the_row() -> None:
    """Billed, allowed and paid come before the CAS block and are not it."""
    parsed = parse_row(row("001", "E1390", "450.00", "357.50", "286.00", "CO", "45", "92.50"))

    assert parsed is not None
    assert parsed.amount == "92.50"


def test_ocr_punctuation_is_stripped() -> None:
    parsed = parse_row(row("002", "E0601.", "CO", "45", "-", "258.00,"))

    assert parsed is not None
    assert parsed.procedure_code == "E0601"
    assert parsed.amount == "258.00"


def test_a_line_number_run_into_the_procedure_code_is_still_found() -> None:
    """OCR merges neighbouring cells; whole-token matching then finds neither."""
    parsed = parse_row(row("001E1392", "210.00", "OA", "22", "MA04", "210.00"))

    assert parsed is not None
    assert parsed.line_number == 1
    assert parsed.procedure_code == "E1392"


def test_a_corrupted_procedure_code_is_reported_missing_not_guessed() -> None:
    """OCR lost the leading letter once. Reporting nothing beats inventing a code."""
    parsed = parse_row(row("001�1392", "OA", "22", "210.00"))

    assert parsed is not None
    assert parsed.procedure_code is None
    assert parsed.line_number == 1


def test_a_group_code_alone_is_not_enough() -> None:
    assert parse_row(row("CO")) is None
    assert parse_row(row("CO", "197")) is None  # no amount


# --- row clustering --------------------------------------------------------


def word(text: str, x0: float, top: float) -> dict[str, object]:
    return {"text": text, "x0": x0, "top": top}


def test_words_sharing_a_baseline_become_one_row() -> None:
    rows = rows_from_words([word("CO", 372, 100.0), word("197", 404, 100.0)])

    assert rows == [["CO", "197"]]


def test_a_staggered_baseline_still_counts_as_the_same_row() -> None:
    """The fixtures stagger by up to 5.5pt to look like a real remittance."""
    rows = rows_from_words([word("CO", 372, 100.0), word("197", 404, 105.0)])

    assert rows == [["CO", "197"]]


def test_a_genuinely_different_row_is_kept_apart() -> None:
    rows = rows_from_words([word("CO", 372, 100.0), word("197", 404, 130.0)])

    assert len(rows) == 2


def test_a_row_is_read_left_to_right_whatever_order_it_arrives_in() -> None:
    rows = rows_from_words([word("197", 404, 100.0), word("CO", 372, 100.0)])

    assert rows == [["CO", "197"]]


# --- against the committed fixtures ----------------------------------------


def test_the_text_layer_fixtures_have_a_text_layer() -> None:
    assert has_text_layer(FIXTURES / "clm-2026-0001-eob.pdf")
    assert has_text_layer(FIXTURES / "clm-2026-0002-eob.pdf")


def test_the_scan_has_none() -> None:
    assert not has_text_layer(FIXTURES / "clm-2026-0003-eob.pdf")


def test_coordinate_extraction_recovers_the_column_major_rows() -> None:
    """The fixtures are drawn column-major so reading order cannot recover a row.

    This is the other half of that bargain: hard for a string split, entirely
    tractable for a reader that uses the glyph coordinates.
    """
    result = extract(FIXTURES / "clm-2026-0001-eob.pdf")

    assert result.method == "text_layer"
    assert [
        (line.procedure_code, f"{line.group}-{line.reason_code}", line.amount)
        for line in result.lines
    ] == [
        ("E1390", "CO-45", "92.50"),
        ("E0601", "CO-197", "1250.00"),
    ]


def test_the_guardrail_remark_survives_extraction() -> None:
    """MA130 is what stops an appeal on an unappealable claim. Losing it is unsafe."""
    result = extract(FIXTURES / "clm-2026-0002-eob.pdf")

    remarks = {r for line in result.lines for r in line.remark_codes}
    assert "MA130" in remarks


@pytest.mark.parametrize("name", ["clm-2026-0001", "clm-2026-0002"])
def test_extraction_matches_the_committed_claim_json(name: str) -> None:
    """The document and the claim JSON describe the same claim, or one is stale."""
    import json

    claim = json.loads((FIXTURES.parent / "claims" / f"{name}.json").read_text(encoding="utf-8"))
    expected = {
        (
            line["adjustments"][0]["group"],
            line["adjustments"][0]["reason_code"],
            line["adjustments"][0]["amount"],
        )
        for line in claim["service_lines"]
    }

    extracted = {
        (line.group, line.reason_code, line.amount)
        for line in extract(FIXTURES / f"{name}-eob.pdf").lines
    }

    assert extracted == expected
