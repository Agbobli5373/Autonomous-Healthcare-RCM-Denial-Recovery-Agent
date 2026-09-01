from __future__ import annotations

import ast
import shutil
from pathlib import Path

import pytest

from rcm_agent.analysis import extract as analysis_extract
from rcm_agent.sandbox import SANDBOX_TTL_MS, extraction_script, guest_document_path

ANALYSIS_DIR = Path(analysis_extract.__file__).resolve().parent
FIXTURES = Path(__file__).resolve().parent.parent / "data" / "fixtures" / "eobs"


def uploaded_module_names() -> set[str]:
    """What `upload_analysis_code` would ship: every module in the package."""
    return {p.stem for p in ANALYSIS_DIR.glob("*.py") if p.name != "__init__.py"}


def sibling_imports_of(module: Path) -> set[str]:
    """Modules this file imports from its own package, however written."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    siblings: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        relative = node.level and node.module is None
        absolute = node.module is not None and node.module.startswith("rcm_agent.analysis")
        if relative or absolute:
            siblings.update(alias.name for alias in node.names)
    return siblings


def test_every_module_the_analysis_code_imports_is_shipped() -> None:
    """The guest gets the whole package, so a new sibling module cannot be missed.

    An earlier version hand-listed `extract.py`. When the OCR boundary moved into
    its own module the guest lost it, and only the scanned path broke - so the
    text-layer check still passed and the gap shipped.
    """
    shipped = uploaded_module_names()

    for module in ANALYSIS_DIR.glob("*.py"):
        missing = sibling_imports_of(module) - shipped
        assert not missing, f"{module.name} imports {missing}, which the guest never receives"


def test_the_analysis_code_does_not_reach_back_into_the_orchestrator() -> None:
    """`rcm_agent` does not exist in the guest; importing it is a runtime failure there."""
    for module in ANALYSIS_DIR.glob("*.py"):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("rcm_agent."), (
                    f"{module.name} imports {node.module}, which is absent from the sandbox"
                )


def test_a_sandbox_is_given_a_ttl() -> None:
    """The only defence that survives SIGKILL, which no `finally` can catch."""
    assert 0 < SANDBOX_TTL_MS <= 30 * 60_000


def test_the_guest_deletes_the_document_even_if_extraction_raises() -> None:
    script = extraction_script(guest_document_path("eob.pdf"))

    assert "finally:" in script
    assert script.index("try:") < script.index("os.remove")


def test_the_guest_reports_whether_the_document_survived() -> None:
    assert "still_present" in extraction_script(guest_document_path("eob.pdf"))


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract is not installed")
def test_ocr_reads_the_scanned_fixture() -> None:
    """Runs only where tesseract exists; in the demo that is inside the sandbox.

    The scan carries the OA-22 rebill and its MA04 remark. A Remark Code is what
    a guardrail fires on, so losing one to OCR is a safety failure rather than a
    cosmetic one.
    """
    result = analysis_extract.extract(FIXTURES / "clm-2026-0003-eob.pdf")

    assert result.method == "ocr"
    codes = {f"{line.group}-{line.reason_code}" for line in result.lines}
    remarks = {r for line in result.lines for r in line.remark_codes}
    assert "OA-22" in codes
    assert "MA04" in remarks
