"""Driving an EOB document through the Sandbox, orchestrator-side.

Named for the side it runs on. `analysis/extract.py` is the code that runs
*inside* the sandbox; this is the code that puts it there and reads back
what it found.

The path, and why each hop is where it is:

```
document on disk
  -> copied into runs/<ts>/documents/     the retained artifact
  -> SHA-256 taken here                   the orchestrator is the only witness
  -> uploaded to the sandbox
  -> hashed again in the guest, extracted, then deleted
  -> structured lines and the guest's digest come back
  -> digests compared; a mismatch stops the run
```

The copy happens before the upload on purpose. If the sandbox dies mid-flight
the document is already an artifact, so a killed run still leaves the evidence it
had — which is the same reason `events.ndjson` is flushed per event.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import cast

from rcm_agent.analysis.extract import ExtractedAdjustment, Extraction
from rcm_agent.config import credential
from rcm_agent.events import EventStream
from rcm_agent.run_directory import RunDirectory
from rcm_agent.sandbox import (
    ProvisioningError,
    extraction_script,
    guest_document_path,
    sandbox_session,
)
from rcm_agent.transport import DigestMismatch, Shipment, sha256_of, verify

SOURCE_ROOT = Path(__file__).resolve().parent


class ExtractionFailed(RuntimeError):
    """The document could not be read, for a reason worth reporting verbatim."""


def _as_object_map(value: object) -> dict[str, object] | None:
    """Narrow an untrusted JSON value to a mapping with known key and value types.

    `isinstance(x, dict)` alone narrows to `dict[Unknown, Unknown]`, which puts
    every later `.get()` back outside the type system. This is the seam where
    data from the sandbox becomes typed, so it is worth doing once and properly
    rather than suppressing the complaint at each use.
    """
    if not isinstance(value, dict):
        return None
    return cast(dict[str, object], value)


def _as_object_list(value: object) -> list[object]:
    """As above, for sequences: `isinstance(x, list)` alone gives `list[Unknown]`."""
    if not isinstance(value, list):
        return []
    return cast(list[object], value)


def _as_optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _as_optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _adjustment_from(item: object) -> ExtractedAdjustment | None:
    fields = _as_object_map(item)
    if fields is None:
        return None
    remarks = _as_object_list(fields.get("remark_codes"))
    return ExtractedAdjustment(
        line_number=_as_optional_int(fields.get("line_number")),
        procedure_code=_as_optional_str(fields.get("procedure_code")),
        group=str(fields.get("group", "")),
        reason_code=str(fields.get("reason_code", "")),
        remark_codes=tuple(str(r) for r in remarks),
        amount=str(fields.get("amount", "")),
    )


def _extraction_from(payload: dict[str, object]) -> Extraction:
    raw = _as_object_map(payload.get("extraction"))
    if raw is None:
        raise ExtractionFailed("the sandbox returned no extraction")

    lines = [
        line
        for item in _as_object_list(raw.get("lines"))
        if (line := _adjustment_from(item)) is not None
    ]

    return Extraction(
        source=str(raw.get("source", "")),
        method=str(raw.get("method", "")),
        lines=tuple(lines),
    )


async def extract_document(
    document: Path, run: RunDirectory, stream: EventStream
) -> tuple[Shipment, Extraction]:
    api_key = credential("SOLARI_API_KEY")

    stream.emit(phase="analysis", kind="phase_start")

    retained = run.documents_path / document.name
    shutil.copy2(document, retained)
    digest = sha256_of(retained)
    shipment = Shipment(
        local_path=retained, remote_path=guest_document_path(document.name), digest=digest
    )
    stream.emit(
        phase="analysis",
        kind="tool_result",
        tool="retain_document",
        outcome="ok",
        detail=shipment.as_event_detail(),
    )

    try:
        async with sandbox_session(api_key) as sandbox:
            stream.emit(phase="analysis", kind="tool_call", tool="provision_sandbox")
            provisioning = await sandbox.provision()
            stream.emit(
                phase="analysis",
                kind="tool_result",
                tool="provision_sandbox",
                outcome="ok",
                detail=provisioning.as_event_detail(),
            )

            await sandbox.upload_analysis_code(SOURCE_ROOT)
            await sandbox.upload(retained, shipment.remote_path)

            stream.emit(phase="analysis", kind="tool_call", tool="extract_document")
            raw = await sandbox.run(extraction_script(shipment.remote_path))
    except ProvisioningError as exc:
        stream.emit(phase="analysis", kind="error", outcome="failed", detail={"error": str(exc)})
        raise ExtractionFailed(str(exc)) from exc

    try:
        decoded = _as_object_map(json.loads(raw.splitlines()[-1]))
    except (ValueError, IndexError) as exc:
        stream.emit(phase="analysis", kind="error", outcome="failed", detail={"raw": raw[:400]})
        raise ExtractionFailed(f"the sandbox returned no result: {raw[:300]}") from exc

    if decoded is None:
        stream.emit(phase="analysis", kind="error", outcome="failed", detail={"raw": raw[:400]})
        raise ExtractionFailed(f"the sandbox returned a non-object: {raw[:300]}")
    payload = decoded

    try:
        verify(shipment.digest, str(payload.get("sha256")), document=document.name)
    except DigestMismatch as exc:
        stream.emit(
            phase="analysis",
            kind="error",
            outcome="failed",
            detail={
                "orchestrator_sha256": shipment.digest,
                "sandbox_sha256": payload.get("sha256"),
            },
        )
        raise ExtractionFailed(str(exc)) from exc

    if payload.get("still_present") is not False:
        # Reported, and enforced. Minimal retention is a claim this project makes
        # in its README, so an unconfirmed delete is a failed run rather than a
        # line in a log nobody reads.
        stream.emit(
            phase="analysis",
            kind="error",
            outcome="failed",
            detail={"document": document.name, "deleted_in_sandbox": False},
        )
        raise ExtractionFailed(
            f"{document.name} was still present in the sandbox after extraction; "
            "the run stops rather than leave it there."
        )

    extraction = _extraction_from(payload)
    stream.emit(
        phase="analysis",
        kind="tool_result",
        tool="extract_document",
        outcome="ok",
        detail={
            "method": extraction.method,
            "lines": len(extraction.lines),
            "sha256": shipment.digest,
            "sandbox_sha256": payload.get("sha256"),
            # Proof the guest kept the document only while computing on it.
            "deleted_in_sandbox": payload.get("still_present") is False,
        },
    )
    stream.emit(phase="analysis", kind="phase_end", outcome="ok")
    return shipment, extraction
