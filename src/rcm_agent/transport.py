"""Moving a document from the orchestrator to the Sandbox, provably.

There is no platform-level hop between the Browser and the Sandbox: they sit on
separate gateways behind separate SDK packages, so bytes transit this process.
That makes the orchestrator the only place that can vouch for what was analysed,
which is why the digest is taken here.

The document is hashed as it lands and hashed again inside the sandbox. Matching
digests mean the audit trail can *prove* the file kept in `documents/` is the
file that produced the Determination, rather than asserting it by filename. A
mismatch fails the run: in a domain where the artifact is the point, a silently
wrong answer is worse than a loud stop.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

_CHUNK = 1024 * 1024


class DigestMismatch(RuntimeError):
    """The sandbox did not receive the bytes the orchestrator retained."""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_of_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class Shipment:
    """A document that reached the sandbox, with both ends' digests agreeing."""

    local_path: Path
    remote_path: str
    digest: str

    def as_event_detail(self) -> dict[str, object]:
        return {
            "document": self.local_path.name,
            "remote_path": self.remote_path,
            "sha256": self.digest,
            "bytes": self.local_path.stat().st_size,
        }


def verify(expected: str, actual: str, *, document: str) -> None:
    if expected != actual:
        raise DigestMismatch(
            f"{document}: the sandbox received different bytes than were retained. "
            f"orchestrator sha256={expected} sandbox sha256={actual}. "
            "The determination this would produce could not be tied to the stored "
            "document, so the run stops here."
        )
