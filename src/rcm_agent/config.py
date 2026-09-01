"""Credentials, read from the environment or a gitignored .env.

The Solari key is all-or-nothing: it has no scopes, and anyone holding it can
attach any saved profile and act as that account. So it is read here, kept out
of logs, and never written into an artifact - only a fingerprint ever appears.
"""

from __future__ import annotations

import os
from pathlib import Path


class MissingCredential(RuntimeError):
    """A credential the run cannot proceed without."""


def _from_dotenv(name: str, start: Path) -> str | None:
    for directory in (start, *start.parents):
        candidate = directory / ".env"
        if not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("\"'")
    return None


def credential(name: str, *, start: Path | None = None) -> str:
    value = os.environ.get(name) or _from_dotenv(name, start or Path.cwd())
    if not value:
        raise MissingCredential(
            f"{name} is not set. Put it in a .env at the repo root or export it. "
            "The .env is gitignored."
        )
    return value


def fingerprint(secret: str) -> str:
    """Enough to tell two keys apart in a log, not enough to use one."""
    if len(secret) < 12:
        return "?" * len(secret)
    return f"{secret[:8]}...{secret[-4:]} ({len(secret)} chars)"
