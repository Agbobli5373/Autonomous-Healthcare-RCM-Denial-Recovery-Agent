"""What the sandbox can actually import.

The guest is not this machine. It has fastapi and uvicorn because the mocks are
served there, and it does not have reportlab, Pillow or rich, because nothing in
the guest renders a PDF or draws a terminal panel. An import that reaches for one
of those works perfectly here and fails there, mid-run, in front of a camera.

This is the same failure #28 shipped: a module the guest needed was not sent, the
text-layer path kept working, and only the scanned path died. The lesson taken
from it was to stop reasoning about what the guest can import and check it.

Each test runs a fresh interpreter with the absent packages actually blocked,
rather than manipulating `sys.modules` in this one — a half-restored import
system leaks into every test that runs afterwards.
"""

from __future__ import annotations

import subprocess
import sys

ABSENT_FROM_GUEST = ("reportlab", "PIL", "rich", "pdfplumber")
"""Installed here, not in the guest.

`pdfplumber` and friends are installed into the guest only for the analysis
kernel, which runs as a separate program — the mock servers must not need them.
"""

_BLOCKER = """
import sys

class _Absent:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {absent!r}:
            raise ImportError(f"{{fullname}} is not installed in the sandbox")
        return None

sys.meta_path.insert(0, _Absent())
"""


def _import_in_a_guest_like_interpreter(statement: str) -> subprocess.CompletedProcess[str]:
    script = _BLOCKER.format(absent=ABSENT_FROM_GUEST) + statement
    return subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=120
    )


def test_the_payer_portal_imports_without_the_generator_dependencies() -> None:
    result = _import_in_a_guest_like_interpreter(
        "from rcm_agent.mocks.portal import create_app; create_app()"
    )

    assert result.returncode == 0, result.stderr


def test_the_practice_system_imports_without_the_generator_dependencies() -> None:
    result = _import_in_a_guest_like_interpreter(
        "from rcm_agent.mocks.practice_management import create_app; create_app()"
    )

    assert result.returncode == 0, result.stderr


def test_the_mocks_can_read_their_fixtures_without_the_generator() -> None:
    """Serving a claim must not need the code that drew its EOB."""
    result = _import_in_a_guest_like_interpreter(
        "from rcm_agent.mocks import fixtures_data;"
        "assert fixtures_data.worklist();"
        "assert fixtures_data.practice_records()"
    )

    assert result.returncode == 0, result.stderr


def test_the_blocker_actually_blocks() -> None:
    """Otherwise the three tests above pass by importing the real packages."""
    result = _import_in_a_guest_like_interpreter("import reportlab")

    assert result.returncode != 0
    assert "not installed in the sandbox" in result.stderr
