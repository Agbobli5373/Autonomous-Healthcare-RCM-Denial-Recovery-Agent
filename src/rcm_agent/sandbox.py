# The Solari SDKs ship no type stubs, so every handle is `Any` and strict mode
# has nothing to check. Rather than scatter ignores across the codebase, this one
# module absorbs the untyped boundary: everything outside it stays strict, and
# anything crossing out of here is converted to a typed value first.
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false

"""The Sandbox: lifecycle, provisioning, and getting work into it.

Three things here are the product of measurement rather than documentation, and
each cost time to discover:

**`connect()` is mandatory after `create()`.** Without it every code call fails
with `ConnectionError: Not connected`. It appears in neither the docs nor the
cookbook's sandbox example.

**Provisioning happens at run time**, measured at roughly 21 seconds all in. A
baked template would save that, but a template built in one account does not
exist in a reviewer's, so it would trade sixteen seconds for a build step and a
lifecycle to maintain.

**Teardown is registered the moment the sandbox exists**, never at the end of a
happy path. A failure between `create()` and the end of setup otherwise strands
the session, and on the Free tier the orphan consumes the only slot and blocks
every later run. That happened during the spike, and the next run failed at
`create` with no obvious cause.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "https://api.getsolari.com"
"""The only region Solari offers is us-west, and it is the default."""

PIP_PACKAGES: tuple[str, ...] = ("pdfplumber", "pypdfium2", "pytesseract")
"""Measured at ~7.3s. The sandbox ships none of these; only Pillow is present."""

APT_PACKAGES: tuple[str, ...] = ("tesseract-ocr",)
"""Measured at ~8.6s. `pytesseract` is a wrapper - without the binary it is inert."""

GUEST_WORKDIR = "/tmp/rcm"

SANDBOX_TTL_MS = 10 * 60_000
"""A ceiling on how long an abandoned sandbox can survive.

The `finally` below handles clean exits and usually handles SIGINT. It cannot
handle SIGTERM, which does not unwind, or SIGKILL, which cannot be caught - and
an orphan consumes the only slot on the Free tier, so the *next* run fails at
`create` with no obvious cause. This is the only defence that outlives the
process. Note the platform treats it as a rolling idle window rather than a hard
deadline, so a working sandbox is not cut off mid-run."""

_INSTALL_SCRIPT = """
import subprocess, sys, shutil, json
result = {{}}
pip = subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q", {pip_packages}],
    capture_output=True, text=True,
)
result["pip_returncode"] = pip.returncode
result["pip_stderr"] = pip.stderr[-400:]
apt = subprocess.run(
    "apt-get update -qq && apt-get install -y -qq {apt_packages}",
    shell=True, capture_output=True, text=True,
)
result["apt_returncode"] = apt.returncode
result["apt_stderr"] = apt.stderr[-400:]
result["tesseract"] = shutil.which("tesseract")
print(json.dumps(result))
"""


class UploadFailed(RuntimeError):
    """A file did not reach the guest. Deliberately carries no URL."""


class ProvisioningError(RuntimeError):
    """The sandbox came up but could not be made ready to do the work."""


@dataclass(frozen=True, slots=True)
class Provisioning:
    """What provisioning actually achieved, for the audit trail."""

    tesseract_path: str | None
    pip_packages: tuple[str, ...]
    apt_packages: tuple[str, ...]

    def as_event_detail(self) -> dict[str, object]:
        return {
            "pip": list(self.pip_packages),
            "apt": list(self.apt_packages),
            "tesseract": self.tesseract_path,
        }


class Sandbox:
    """A live sandbox, already connected and provisioned."""

    def __init__(self, handle: Any) -> None:
        self._handle = handle
        self._context: str | None = None

    async def _context_id(self) -> str:
        if self._context is None:
            self._context = str(await self._handle.create_code_context("python"))
        return self._context

    async def run(self, code: str) -> str:
        """Run Python in the guest and return whatever it printed."""
        captured: list[str] = []
        await self._handle.run_code(
            code, context_id=await self._context_id(), on_stdout=captured.append
        )
        return "".join(captured).strip()

    async def _put(self, guest_path: str, payload: bytes, *, timeout: float) -> None:
        signed = await self._handle.upload_url(guest_path)
        url = signed["url"] if isinstance(signed, dict) else str(signed)
        async with httpx.AsyncClient(timeout=timeout) as http:
            response = await http.put(url, content=payload)
        if response.is_error:
            # Deliberately not raise_for_status(): httpx puts the request URL in
            # the message, and this URL is pre-signed - the token rides in its
            # query string. That would end up in a traceback on someone's screen.
            raise UploadFailed(f"upload of {guest_path} failed with HTTP {response.status_code}")

    async def upload(self, local: Path, guest_path: str) -> None:
        await self._put(guest_path, local.read_bytes(), timeout=120)

    async def upload_text(self, text: str, guest_path: str) -> None:
        await self._put(guest_path, text.encode("utf-8"), timeout=60)

    async def provision(self) -> Provisioning:
        script = _INSTALL_SCRIPT.format(
            pip_packages=", ".join(repr(p) for p in PIP_PACKAGES),
            apt_packages=" ".join(APT_PACKAGES),
        )
        raw = await self.run(script)
        try:
            import json

            report: dict[str, Any] = json.loads(raw.splitlines()[-1])
        except (ValueError, IndexError) as exc:
            raise ProvisioningError(f"provisioning produced no report: {raw[:400]}") from exc

        if report.get("pip_returncode") != 0:
            raise ProvisioningError(f"pip install failed: {report.get('pip_stderr')}")
        if report.get("apt_returncode") != 0:
            raise ProvisioningError(f"apt install failed: {report.get('apt_stderr')}")

        # Verified present rather than assumed: pytesseract imports happily
        # without the binary and only fails later, mid-run, on a real document.
        tesseract = report.get("tesseract")
        if not tesseract:
            raise ProvisioningError("tesseract is not on PATH after apt install")

        return Provisioning(
            tesseract_path=str(tesseract),
            pip_packages=PIP_PACKAGES,
            apt_packages=APT_PACKAGES,
        )

    async def upload_analysis_code(self, source_root: Path) -> None:
        """Ship the working copy's analysis package, not a baked-in snapshot.

        Every module in `analysis/`, not a hand-listed subset. An earlier version
        uploaded only `extract.py`; when the OCR boundary moved into its own
        module the guest lost it, and the scanned path died with
        `ModuleNotFoundError` while the text-layer path kept working - so the
        obvious check missed it.
        """
        await self.upload_text("", f"{GUEST_WORKDIR}/rcm_analysis/__init__.py")
        for module in sorted((source_root / "analysis").glob("*.py")):
            if module.name == "__init__.py":
                continue
            await self.upload_text(
                module.read_text(encoding="utf-8"),
                f"{GUEST_WORKDIR}/rcm_analysis/{module.name}",
            )


@contextlib.asynccontextmanager
async def sandbox_session(api_key: str) -> AsyncGenerator[Sandbox]:
    """Create, connect and provision a sandbox; always tear it down.

    Teardown is registered before anything else can fail. The `finally` here is
    the whole point of the function.
    """
    from solari_sandbox import SandboxClient

    client = SandboxClient(api_key=api_key, base_url=BASE_URL)
    handle = await client.create(timeout_ms=SANDBOX_TTL_MS)
    try:
        await handle.connect()
        yield Sandbox(handle)
    finally:
        with contextlib.suppress(Exception):
            await handle.kill()
        with contextlib.suppress(Exception):
            await client.aclose()


def guest_document_path(name: str) -> str:
    return f"{GUEST_WORKDIR}/documents/{name}"


def extraction_script(guest_path: str) -> str:
    """Code the guest runs: hash, extract, delete, report.

    The delete is not tidiness. The PRD asks the design to mirror a HIPAA-aware
    architecture with minimal retention, and this is the cheapest place in the
    system to demonstrate that rather than claim it: the analysis environment
    holds a patient-adjacent document only while it is computing on it.
    """
    return f"""
import hashlib, json, os, sys
sys.path.insert(0, {GUEST_WORKDIR!r})
from rcm_analysis.extract import extract

path = {guest_path!r}
digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
try:
    result = extract(__import__("pathlib").Path(path))
finally:
    # In a finally, not after the call: an extraction that raises would
    # otherwise leave a patient-adjacent document sitting in the guest until
    # the sandbox happened to die.
    if os.path.exists(path):
        os.remove(path)
print(json.dumps({{"sha256": digest, "extraction": result.as_dict(),
                   "still_present": os.path.exists(path)}}))
"""
