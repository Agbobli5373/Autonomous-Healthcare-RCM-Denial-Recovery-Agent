"""Writing the spec out as claim JSON and EOB documents.

A Remittance is the data; an EOB is the document a person reads. These are
documents that carry Remittance data, so they are EOBs.
"""

from __future__ import annotations

import json
from pathlib import Path

from rcm_agent.fixtures.naming import claim_filename, eob_filename
from rcm_agent.fixtures.render import render_scan, render_text_layer
from rcm_agent.fixtures.spec import CLAIMS, ClaimSpec


def claim_json_path(root: Path, claim: ClaimSpec) -> Path:
    return root / "claims" / claim_filename(claim.claim_id)


def document_path(root: Path, claim: ClaimSpec) -> Path:
    return root / "eobs" / eob_filename(claim.claim_id)


def _write_claim(root: Path, claim: ClaimSpec) -> Path:
    path = claim_json_path(root, claim)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(claim.as_claim(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def _write_document(root: Path, claim: ClaimSpec) -> Path:
    path = document_path(root, claim)
    path.parent.mkdir(parents=True, exist_ok=True)
    if claim.rendering == "scan":
        render_scan(claim, path)
    else:
        render_text_layer(claim, path)
    return path


def generate_fixtures(root: Path) -> list[Path]:
    """Write every claim's JSON and document under `root`. Returns what it wrote."""
    written: list[Path] = []
    for claim in CLAIMS:
        written.append(_write_claim(root, claim))
        written.append(_write_document(root, claim))
    return written
