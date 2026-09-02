from __future__ import annotations

from pathlib import Path

import pytest

from rcm_agent.config import MissingCredential, credential, fingerprint
from rcm_agent.transport import DigestMismatch, sha256_of, sha256_of_bytes, verify

KNOWN_EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_hashing_a_file_matches_hashing_its_bytes(tmp_path: Path) -> None:
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-1.4 pretend")

    assert sha256_of(path) == sha256_of_bytes(b"%PDF-1.4 pretend")


def test_an_empty_file_hashes_to_the_known_value(tmp_path: Path) -> None:
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")

    assert sha256_of(path) == KNOWN_EMPTY


def test_matching_digests_pass_silently() -> None:
    verify("abc", "abc", document="eob.pdf")


def test_a_mismatch_stops_the_run_and_says_both_digests() -> None:
    """A silently wrong answer is worse than a loud stop when the artifact is the point."""
    with pytest.raises(DigestMismatch) as caught:
        verify("aaa", "bbb", document="eob.pdf")

    message = str(caught.value)
    assert "aaa" in message and "bbb" in message and "eob.pdf" in message


def test_a_credential_is_read_from_a_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEMO_KEY", raising=False)
    (tmp_path / ".env").write_text('DEMO_KEY="slr_live_abc"\n', encoding="utf-8")

    assert credential("DEMO_KEY", start=tmp_path) == "slr_live_abc"


def test_the_environment_wins_over_the_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("DEMO_KEY=from_file\n", encoding="utf-8")
    monkeypatch.setenv("DEMO_KEY", "from_env")

    assert credential("DEMO_KEY", start=tmp_path) == "from_env"


def test_a_missing_credential_says_where_to_put_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEMO_KEY", raising=False)

    with pytest.raises(MissingCredential, match=r"\.env"):
        credential("DEMO_KEY", start=tmp_path)


def test_a_fingerprint_does_not_leak_the_secret() -> None:
    secret = "slr_live_0123456789abcdef"

    printed = fingerprint(secret)

    assert "0123456789ab" not in printed
    assert printed == "...cdef (25 chars)"


# Assembled rather than written out. A whole key shape in the source is the
# thing a secret scanner matches, and this repo has already had to rewrite a
# constant out of a branch's history for looking like one - in a test file just
# the same. Splitting them keeps the literal off disk while the tests still
# exercise a realistic head.
VENDOR_PREFIXES = ("sk-" + "ant-api03-", "slr" + "_live_")


def test_a_fingerprint_is_not_itself_shaped_like_a_credential() -> None:
    """A run artifact carrying a vendor prefix fails a secret scanner on sight.

    Not hypothetical: a constant that merely looked like a session token had to
    be rewritten out of this repo's history once. The prefix is the token that
    gets matched, and it distinguishes nothing - every key a vendor issues opens
    with the same characters.
    """
    for prefix in VENDOR_PREFIXES:
        secret = prefix + "0123456789abcdef"

        printed = fingerprint(secret)

        assert prefix not in printed
        assert not printed.startswith(secret[:8])


def test_two_keys_from_one_vendor_still_read_differently() -> None:
    """What the prefix was wrongly credited with doing, done by the tail."""
    head = VENDOR_PREFIXES[0]

    assert fingerprint(head + "aaaabbbbccccdddd") != fingerprint(head + "aaaabbbbcccceeee")
