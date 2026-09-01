from __future__ import annotations

import re
from pathlib import Path

import pytest
from pypdf import PdfReader

from rcm_agent.claim_io import load_claim
from rcm_agent.determination import determine
from rcm_agent.fixtures.generate import claim_json_path, document_path, generate_fixtures
from rcm_agent.fixtures.render import wrap_descriptor
from rcm_agent.fixtures.spec import CLAIMS, ClaimSpec

COMMITTED = Path(__file__).resolve().parent.parent / "data" / "fixtures"

HCPCS_LEVEL_II = re.compile(r"^[A-V]\d{4}$")
"""HCPCS Level II codes are a letter A-V followed by four digits."""


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("fixtures")
    generate_fixtures(root)
    return root


def text_layer_of(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


# --- what the generator produces -------------------------------------------


def test_every_claim_gets_a_json_and_a_document(generated: Path) -> None:
    for claim in CLAIMS:
        assert claim_json_path(generated, claim).is_file()
        assert document_path(generated, claim).is_file()


def test_regeneration_is_byte_identical(tmp_path: Path) -> None:
    """Committed outputs are only reviewable in a diff if regenerating is stable."""
    first, second = tmp_path / "a", tmp_path / "b"
    generate_fixtures(first)
    generate_fixtures(second)

    for claim in CLAIMS:
        assert document_path(first, claim).read_bytes() == document_path(second, claim).read_bytes()
        assert (
            claim_json_path(first, claim).read_text() == claim_json_path(second, claim).read_text()
        )


# --- the documents are as hard as they are meant to be ----------------------


def text_layer_claims() -> list[ClaimSpec]:
    return [c for c in CLAIMS if c.rendering == "text_layer"]


def scanned_claims() -> list[ClaimSpec]:
    return [c for c in CLAIMS if c.rendering == "scan"]


@pytest.mark.parametrize("claim", text_layer_claims(), ids=lambda c: c.claim_id)
def test_a_text_layer_document_has_a_text_layer(claim: ClaimSpec, generated: Path) -> None:
    assert text_layer_of(document_path(generated, claim)).strip()


@pytest.mark.parametrize("claim", scanned_claims(), ids=lambda c: c.claim_id)
def test_the_scan_has_no_text_layer_at_all(claim: ClaimSpec, generated: Path) -> None:
    """Image-only, so it can be read by OCR and nothing else."""
    assert not text_layer_of(document_path(generated, claim)).strip()


@pytest.mark.parametrize("claim", text_layer_claims(), ids=lambda c: c.claim_id)
def test_stream_order_groups_by_column_not_by_row(claim: ClaimSpec, generated: Path) -> None:
    """Reading order must cluster cells by column, so no row survives it.

    The earlier version of this test asserted only that a Reason Code and its
    amount never shared an output line. That is a much weaker property, and
    trivially parseable output satisfied it: the document drew row-wise, so
    `extract_text()` returned every cell in row order and a five-line reader
    recovered the lot. The test passed while the criterion failed.

    So assert the real thing. Each line's Reason Code must sit nearer the *other*
    line's Reason Code than its own adjustment amount — which is only true if the
    stream is column-major, and which makes a row unrecoverable without glyph
    coordinates.
    """
    if len(claim.lines) < 2:
        pytest.skip("a single-row table is recoverable whatever order it is drawn in")

    tokens = [t.strip() for t in text_layer_of(document_path(generated, claim)).splitlines()]

    def index_of(value: str, after: int = 0) -> int:
        return next(i for i, token in enumerate(tokens) if token == value and i >= after)

    reason_positions = [index_of(line.reason_code, after=10) for line in claim.lines]
    amount_positions = [index_of(line.adjustment_amount, after=10) for line in claim.lines]

    between_reason_codes = abs(reason_positions[0] - reason_positions[1])
    for reason, amount in zip(reason_positions, amount_positions, strict=True):
        assert between_reason_codes < abs(reason - amount), (
            "a Reason Code sits nearer its own amount than the next row's Reason Code, "
            "so the stream is row-major and a string split would parse it"
        )


@pytest.mark.parametrize("claim", text_layer_claims(), ids=lambda c: c.claim_id)
def test_the_codes_are_present_somewhere_in_the_text_layer(
    claim: ClaimSpec, generated: Path
) -> None:
    """Hard to parse is the goal; missing is not. The data must actually be there."""
    text = text_layer_of(document_path(generated, claim))

    for line in claim.lines:
        assert line.procedure_code in text
        assert line.adjustment_amount in text
        for remark in line.remark_codes:
            assert remark in text


# --- coding ----------------------------------------------------------------


def test_every_procedure_code_is_hcpcs_level_ii() -> None:
    """CMS publishes HCPCS Level II freely; AMA licenses CPT descriptors."""
    for claim in CLAIMS:
        for line in claim.lines:
            assert HCPCS_LEVEL_II.match(line.procedure_code), line.procedure_code


def test_every_code_carries_a_descriptor() -> None:
    for claim in CLAIMS:
        for line in claim.lines:
            assert len(line.descriptor.strip()) > 10


# --- the fixtures drive the demo's three outcomes --------------------------


@pytest.mark.parametrize("claim", CLAIMS, ids=lambda c: c.claim_id)
def test_a_generated_claim_loads_and_reaches_its_expected_action(
    claim: ClaimSpec, generated: Path
) -> None:
    """End to end against the real domain code, not a restatement of the spec."""
    loaded = load_claim(claim_json_path(generated, claim))

    assert determine(loaded).action == claim.expected_action


def test_the_three_outcomes_are_all_different() -> None:
    """An agent that answers the same thing three times demonstrates nothing."""
    actions = {claim.expected_action for claim in CLAIMS}

    assert actions == {"appeal", "close", "rebill"}


def test_one_claim_carries_lines_with_different_outcomes(generated: Path) -> None:
    """A write-off beside a denial, so the CO-45 guardrail meets real fixture data."""
    mixed = [c for c in CLAIMS if len(c.lines) > 1]
    assert mixed, "no claim has more than one service line"

    claim = mixed[0]
    codes = {f"{line.group}-{line.reason_code}" for line in claim.lines}
    assert "CO-45" in codes
    assert codes - {"CO-45"}, "the claim is nothing but write-offs"

    # And the write-off must not swallow the denial beside it.
    assert determine(load_claim(claim_json_path(generated, claim))).action == "appeal"


# --- what is committed matches what the generator makes --------------------


@pytest.mark.parametrize("claim", CLAIMS, ids=lambda c: c.claim_id)
def test_the_committed_fixtures_are_current(claim: ClaimSpec, generated: Path) -> None:
    """Committed outputs must be what today's generator produces.

    If this fails, the generator changed and `rcm-agent generate-fixtures` was
    not re-run — which would leave the demo running on documents no longer
    described by the spec.
    """
    assert document_path(COMMITTED, claim).read_bytes() == (
        document_path(generated, claim).read_bytes()
    )
    assert claim_json_path(COMMITTED, claim).read_text(encoding="utf-8") == (
        claim_json_path(generated, claim).read_text(encoding="utf-8")
    )


# --- descriptors are wrapped, never truncated ------------------------------


def test_wrapping_never_loses_a_word() -> None:
    """The scan cut descriptors at a fixed width, silently losing the tail."""
    for claim in CLAIMS:
        for line in claim.lines:
            rejoined = " ".join(wrap_descriptor(line.descriptor))

            assert rejoined == " ".join(line.descriptor.split())


def test_wrapping_respects_the_width() -> None:
    long_descriptor = " ".join(["word"] * 60)

    assert all(len(chunk) <= 20 for chunk in wrap_descriptor(long_descriptor, width=20))


def test_a_word_longer_than_the_width_is_kept_whole() -> None:
    """Better an overlong line than a mangled CMS term."""
    assert wrap_descriptor("supercalifragilistic", width=5) == ["supercalifragilistic"]


def test_the_longest_committed_descriptor_survives_wrapping() -> None:
    longest = max((line.descriptor for claim in CLAIMS for line in claim.lines), key=len)

    assert " ".join(wrap_descriptor(longest, width=88)) == longest
