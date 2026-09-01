"""Where a fixture's files live, in one place.

The convention was written out three times - in the generator, in the mock that
serves the documents, and in a Content-Disposition header - which is three
chances for them to disagree about the same file.
"""

from __future__ import annotations


def claim_slug(claim_id: str) -> str:
    return claim_id.lower()


def eob_filename(claim_id: str) -> str:
    return f"{claim_slug(claim_id)}-eob.pdf"


def claim_filename(claim_id: str) -> str:
    return f"{claim_slug(claim_id)}.json"
