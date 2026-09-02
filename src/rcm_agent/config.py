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
    """Enough to tell two keys apart in a log, not enough to use one - and not
    shaped like one either.

    The tail identifies a key: vendor consoles print the last few characters
    beside it, so that is what a human matches against. The head is dropped on
    purpose. In every credential this project handles the head is a fixed vendor
    prefix - identical across every key that vendor issues - which tells two of
    their keys apart not at all, and is exactly what a secret scanner matches
    on. The prefixes are not written out here: this module ships to the sandbox,
    and `test_no_credential_travels_to_the_guest` rightly refuses source
    carrying a credential-shaped string, a docstring included.

    Run artifacts carry these fingerprints and are committed as example runs, so
    a fingerprint that keeps the prefix is a scanner failure waiting in a
    directory. This repo has paid that once already: a constant that merely
    looked like a session token had to be rewritten out of a branch history.
    """
    if len(secret) < 12:
        return "?" * len(secret)
    return f"...{secret[-4:]} ({len(secret)} chars)"
