"""Turning a real run into one that is safe to publish.

The same artifact is committed to the repository and served by the hosted
console, so there is one thing to inspect and one thing to trust rather than two
that might differ.

**The redaction is a walk, not a list of fields.** Naming the keys it knew about
would have stopped covering the run the moment the run recorded something new -
and it already has: the model exchange was added after this export was
specified, and it is the largest free text a run carries. So anything
credential-shaped is removed wherever it is found, including inside content
nobody has thought of yet.

Nothing here is expected to find anything. The fingerprint is already tail-only
and preview tokens are already stripped where they are recorded. That is the
point: a check whose value is that it runs over everything, so nobody has to
remember which parts were argued safe. This repository has twice shipped a
credential-shaped string that reasoning said was fine.

**One thing it cannot reach.** Screenshots are images, and an image of a browser
showing a tokened address bar would carry the token past every check here. The
agent screenshots pages rather than browser chrome, so this has not happened -
but it is a gap in the guarantee rather than a case that is covered.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from rcm_agent.fixtures.naming import claim_filename
from rcm_agent.run_directory import claim_json
from rcm_agent.transport import sha256_of_bytes

REDACTED = "[redacted]"

_BINARY_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip", ".gz"})
"""What is not text, and is copied through untouched.

A deny-list, not an allow-list, and the difference is the whole point. An
allow-list of text suffixes was here first, and it covered unknown *keys* while
leaving unknown *file types* wide open: a `.jsonl`, a `.log`, a `.yaml` carrying
a key was neither rewritten nor checked. `.jsonl` is the likely shape for the
model exchange - the very content this export was extended to cover.

Everything else is treated as text if it decodes as text. Getting this list wrong
costs a mangled file, which is loud; getting an allow-list wrong costs a
published credential, which is silent.
"""

_FINGERPRINT = re.compile(r"[A-Za-z0-9_-]*\.\.\.\S{2,8} \(\d+ chars\)")
"""The shape `config.fingerprint` produces: a tail, and a length.

Matched rather than looked up by key, because the fingerprint travels in a
`detail` whose shape is the emitting tool's business, not this module's.

It encodes what `config.fingerprint` produces. If that changes, this has to
change with it - `_ANY_FINGERPRINT` below is the backstop for exactly that.

The leading `[A-Za-z0-9_-]*` matters and was not there at first. Runs written
before the fingerprint became tail-only carry the vendor prefix in front of the
tail, and a pattern anchored on the dots redacted the tail and left the vendor
prefix sitting in the published artifact - the exact credential *shape* that
failed a secret scanner on this repository once already. Found by exporting a
real run rather than the fixture, which only carried the current format.
"""

_QUERY = re.compile(r"(https?://[^\s\"'<>)\]]*?)\?[^\s\"'<>)\]]*")
"""A URL and its query string.

The query is where an access token rides - `preview_url` returns one that grants
anyone holding it access to the port for as long as it is valid. The address
survives: it shows the mock was exposed and on which port, which is why the
event exists at all.

The same cut `HostedMock.url_without_token` makes, applied to text rather than to
a URL that is known to be one. It is deliberately blunt: a query string in a run
artifact is not worth keeping even when it carries nothing.

`)` and `]` end a match because Markdown is rewritten too, and a link written
`[portal](https://host/wl?t=1)` would otherwise lose its closing bracket along
with its query.
"""

_TOKEN = re.compile(r"pt_token[=/][^\s\"'<>)\]]*")
"""A preview access token, wherever it sits.

`_QUERY` catches the ordinary case because Solari puts the token in a query
string. This catches it in a fragment or a path segment, which nothing produces
today - but "nothing produces it today" is how the token reached `events.ndjson`
in the first place.
"""

_VENDOR_SECRET = re.compile(r"(?<![A-Za-z0-9])(sk-[A-Za-z]{2,}|slr_[A-Za-z]{2,})")
"""A whole key, in the shape its vendor issues.

Loose about what follows the prefix and strict about what precedes it. The
*shape* is what a secret scanner rejects, so a prefix with almost nothing after
it still counts - an earlier version wanted several characters and let a
half-redacted fingerprint through, one short of its own threshold.

The lookbehind is not decoration. Without it this matches inside ordinary words:
`risk-adjusted`, `risk-based`, `task-based`. Model-written rationales are free
text in a domain where "risk-adjusted" is an everyday phrase, and a match here
refuses the export and deletes it - so an unanchored pattern would have made a
perfectly good run unpublishable, for a word.

The prefixes are not spelled out in this docstring. This module ships to the
sandbox, and `test_no_credential_travels_to_the_guest` rightly refuses source
carrying a credential-shaped string - prose included. It caught this.

Nothing should ever write a key into a run; that is why `fingerprint` exists. A
match here means something upstream is wrong, so the export refuses rather than
quietly publishing it.
"""


class UnsafeToPublish(RuntimeError):
    """The run cannot be published as it is, and saying why is the whole job."""


def redact(value: Any) -> Any:
    """Anything credential-shaped, removed wherever it appears.

    Recursive over whatever a run recorded: mappings, sequences and strings.
    Numbers, booleans and `None` pass through untouched - a Priority is numbers,
    and a guardrailed claim's is `null`.
    """
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    if isinstance(value, list):
        return [redact(item) for item in value]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _redact_text(text: str) -> str:
    without_queries = _QUERY.sub(r"\1", text)
    without_tokens = _TOKEN.sub(REDACTED, without_queries)
    return _FINGERPRINT.sub(REDACTED, without_tokens)


def publish(run: Path, out_dir: Path) -> Path:
    """Write a redacted copy of `run` under `out_dir`, and return it.

    The copy is a run directory, not a report about one: the console opens it
    with the same code that opens a live one, so a shape invented here would be
    a shape nothing can read.
    """
    state = _state(run)
    if state.get("status") != "completed":
        raise UnsafeToPublish(
            f"{run.name} has status {state.get('status')!r}. A half-written run published "
            "as an example is a demonstration of a crash."
        )

    destination = out_dir / run.name
    if destination.exists():
        raise UnsafeToPublish(f"{destination} already exists; publishing would overwrite it")

    # Everything, then rewrite what is text. Copying first means a file this
    # module has never heard of arrives rather than being silently dropped -
    # losing a document is a quieter failure than publishing one.
    shutil.copytree(run, destination)

    # 4. Everything the guard will read is also rewritten. The two sets were
    #    different once, and a `.txt` carrying a fingerprint was copied verbatim
    #    and then refused - an export that could never succeed.
    try:
        for path in sorted(destination.rglob("*")):
            if not path.is_file() or path.suffix.lower() in _BINARY_SUFFIXES:
                continue
            if path.suffix == ".ndjson":
                _rewrite_lines(path)
            elif path.suffix == ".json":
                _rewrite_json(path)
            else:
                # Anything else that is text, whatever it is called.
                _rewrite_text(path)
    except (OSError, ValueError) as exc:
        # A half-redacted directory is the worst thing to leave behind: it looks
        # like an export and is not one.
        shutil.rmtree(destination, ignore_errors=True)
        raise UnsafeToPublish(f"{run.name} could not be rewritten: {exc}") from exc

    # A refusal takes the directory with it. A half-written export is the worst
    # thing to leave behind - it looks like an export and is not one - and that
    # was already true of the rewrite failing; it is just as true of a guard
    # refusing after the copy.
    try:
        refuse_if_credential_shaped(destination)
        _refuse_if_the_artifact_disagrees(destination)
    except UnsafeToPublish:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return destination


def _state(run: Path) -> dict[str, Any]:
    try:
        loaded: Any = json.loads((run / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UnsafeToPublish(f"{run} has no readable run.json: {exc}") from exc
    if not isinstance(loaded, dict):
        raise UnsafeToPublish(f"{run}: run.json is not an object")
    return loaded  # pyright: ignore[reportUnknownVariableType]


def _write(path: Path, text: str) -> None:
    """Write the same bytes wherever the export is produced.

    `newline=""` for the reason ADR-0004 gives the writer: the default
    translates newlines to the host's, so an export made on Windows carried CRLF
    and did not hash to the digest published beside it.
    """
    path.write_text(text, encoding="utf-8", newline="")


def _rewrite_lines(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    _write(path, "".join(json.dumps(redact(json.loads(line))) + "\n" for line in lines if line))


def _rewrite_text(path: Path) -> None:
    """Redact a file of unknown kind, if it turns out to be text.

    A file that does not decode is left alone rather than mangled - and the guard
    still reads it afterwards, so leaving it alone is not the same as trusting
    it.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    _write(path, _redact_text(text))


def _rewrite_json(path: Path) -> None:
    loaded: Any = json.loads(path.read_text(encoding="utf-8"))
    # `claim_json`, not a third copy of it. ADR-0004: the serialisation is
    # written once and both the writer and the digest call it, because two
    # copies are joined by nothing but coincidence - and this one produces the
    # published file a reader hashes.
    _write(path, claim_json(redact(loaded)))


_ANY_FINGERPRINT = re.compile(r"\(\d+ chars\)")
"""Broader than the pattern the rewrite uses, on purpose.

The read-back is worth having only if it can fail when the rewrite succeeded, and
reusing `_FINGERPRINT` here would mean a drift in what `config.fingerprint`
produces defeated both identically. This matches the part of the shape least
likely to change - a length in brackets - and would still catch a fingerprint
whose head had been reformatted out from under the rewrite.
"""


def refuse_if_credential_shaped(published: Path) -> None:
    """Read the export back and refuse to hand over one that still carries a key.

    The same check the sandbox archive gets, given to the artifact that actually
    goes to strangers. Read back rather than trusted, because the rewrite is the
    thing that could be wrong - and once was: it left a vendor prefix behind on
    a run written before the fingerprint format changed.
    """
    checks = (
        (_VENDOR_SECRET, "a key"),
        (_ANY_FINGERPRINT, "a key fingerprint"),
        (_TOKEN, "an access token"),
    )
    # Every file, including ones this module does not recognise and ones it chose
    # not to rewrite. A check that only reads what the rewrite touched cannot
    # catch what the rewrite missed.
    for path in sorted(published.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_bytes().decode("utf-8", errors="replace")
        for pattern, what in checks:
            if pattern.search(text):
                shutil.rmtree(published, ignore_errors=True)
                raise UnsafeToPublish(
                    f"{path.name} still carries {what} after redaction. The export was "
                    "removed rather than handed over."
                )


def _refuse_if_the_artifact_disagrees(published: Path) -> None:
    """Every `claims/<id>.json` must hash to the digest of what the run recorded.

    A Determination is written down twice - as the `determination` event and as
    the claim file - and a Review names it by a digest the console takes from
    the first while a reader recomputes it from the second. They were unified
    deliberately, but a run directory outlives the code that wrote it: an older
    one recorded a detail carrying no `claim_id` while its claim file carried
    one, so the two hash differently.

    Published, that is ADR-0004's central claim - anyone holding the artifact
    can recompute the number - being false in the one place a reviewer would
    check it. Refused rather than shipped with a caveat, because the point of an
    export is that it can be trusted without one.
    """
    from rcm_agent.review import digest_of

    log = published / "events.ndjson"
    if not log.is_file():
        return

    for line in log.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        try:
            recorded: dict[str, Any] = json.loads(line)
        except ValueError:
            continue
        if recorded.get("kind") != "determination":
            continue
        claim_id = recorded.get("claim_id")
        if not isinstance(claim_id, str):
            continue

        artifact = published / "claims" / claim_filename(claim_id)
        if not artifact.is_file():
            raise UnsafeToPublish(
                f"{published.name} recorded a Determination for {claim_id} but has no "
                f"{artifact.name}. The digest a Review names would have nothing to check."
            )
        on_file = sha256_of_bytes(artifact.read_bytes())
        recorded_digest = digest_of(recorded.get("detail") or {})
        if on_file != recorded_digest:
            raise UnsafeToPublish(
                f"{artifact.name} does not match the Determination the run recorded for "
                f"{claim_id}: the file hashes to {on_file[:12]} and the recorded event to "
                f"{recorded_digest[:12]}. Publishing would put a digest beside an artifact "
                "it does not describe."
            )
