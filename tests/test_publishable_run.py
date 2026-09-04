"""Turning a real run into one that is safe to publish.

The same artifact is committed to the repository and served by the hosted
console, so there is one thing to inspect and one thing to trust.

**The redaction is a walk, not a list of fields.** A rule that named the keys it
knew about would stop covering the run the moment the run recorded something
new - and it already has: the model exchange arrived after this was designed.
Anything credential-shaped is removed wherever it is found, including inside
content nobody has thought of yet.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rcm_agent.publishable_run import UnsafeToPublish, publish, redact

FINGERPRINT = "...hwAA (108 chars)"
TOKENED = "https://demo-8080.preview.getsolari.com/wl?pt_token=not-a-real-token"


def test_a_key_fingerprint_is_removed() -> None:
    """Four characters of a live credential is four more than a public artifact needs.

    It is already tail-only, so this is not a leak. It is also not information a
    reader of a published run has any use for.
    """
    assert FINGERPRINT not in json.dumps(redact({"key": FINGERPRINT}))


def test_a_token_bearing_url_loses_its_token_and_keeps_its_address() -> None:
    """The token grants access to the port for as long as it is valid.

    The address is worth keeping - it shows the mock was exposed and which port
    it was on, which is the whole reason the event exists.
    """
    redacted = redact({"url": TOKENED})

    assert redacted == {"url": "https://demo-8080.preview.getsolari.com/wl"}


def test_it_reaches_content_the_export_has_never_heard_of() -> None:
    """A named-fields rule stops covering the run the moment the run grows.

    That is not hypothetical: the model exchange was added to what a run records
    after this export was specified, and it is the largest free text a run
    carries.
    """
    recorded: dict[str, Any] = {
        "detail": {
            "invented_later": [
                {"deeper": {"and_again": f"the key was {FINGERPRINT} at the time"}},
            ],
            "facts": f"see {TOKENED} for the portal",
        }
    }

    dumped = json.dumps(redact(recorded))

    assert FINGERPRINT not in dumped
    assert "pt_token" not in dumped


def test_ordinary_recorded_text_is_left_alone() -> None:
    """A redaction that eats the artifact has not made it publishable.

    The rationale, the evidence and the codes are the reason anyone opens a
    published run.
    """
    rationale = (
        "Cascade denied the E0601 line CO-197 with remark N706. An appeal with "
        "the authorization number is the route on this risk-adjusted, task-based "
        "queue, and 45% of these are recovered."
    )

    assert redact({"rationale": rationale}) == {"rationale": rationale}


def test_a_url_without_a_query_is_untouched() -> None:
    assert redact({"url": "https://example.test/wl"}) == {"url": "https://example.test/wl"}


def test_numbers_and_nulls_survive_the_walk() -> None:
    """Priority is numbers, and a guardrailed claim's is `null`."""
    priority = {"amount_at_stake": "1250.00", "likelihood": 0.45, "expected_recovery": None}

    assert redact({"priority": priority}) == {"priority": priority}


# --- the whole run ----------------------------------------------------------


RATIONALE = "because the authorization covered the date of service"


def a_run(root: Path, *, with_token: bool = True, rationale: str = RATIONALE) -> Path:
    """A run directory shaped like a real one, carrying what a real one carries."""
    run = root / "2026-01-01T00-00-00Z"
    for name in ("claims", "screenshots", "documents"):
        (run / name).mkdir(parents=True)

    events = [
        {
            "seq": 0,
            "ts": "2026-01-01T00:00:00+00:00",
            "phase": "portal",
            "kind": "tool_call",
            "tool": "open_planner",
            "claim_id": None,
            "outcome": None,
            "screenshot": None,
            "detail": {"key": FINGERPRINT},
        },
        {
            "seq": 1,
            "ts": "2026-01-01T00:00:01+00:00",
            "phase": "setup",
            "kind": "tool_result",
            "tool": "host_mocks",
            "claim_id": None,
            "outcome": "ok",
            "screenshot": None,
            "detail": {"portal": TOKENED if with_token else "https://example.test/wl"},
        },
        {
            "seq": 2,
            "ts": "2026-01-01T00:00:02+00:00",
            "phase": "analysis",
            "kind": "determination",
            "claim_id": "CLM-1",
            "outcome": "ok",
            "screenshot": None,
            "detail": {
                "claim_id": "CLM-1",
                "action": "appeal",
                "rationale": rationale,
                "evidence_required": ["Authorization record"],
                "guardrail": None,
                "priority": {
                    "amount_at_stake": "1250.00",
                    "likelihood": 0.45,
                    "expected_recovery": "562.50",
                },
            },
        },
    ]
    (run / "events.ndjson").write_text(
        "\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8"
    )
    (run / "run.json").write_text(
        json.dumps({"run_id": run.name, "status": "completed", "summary": {"appeal": 1}}),
        encoding="utf-8",
    )
    # The claim file is the Determination the run recorded, written the way
    # `RunDirectory.write_claim` writes it. Two hand-written copies of one
    # judgement drift, and the digest that names it is taken over these bytes.
    decided = next(event for event in events if event["kind"] == "determination")["detail"]
    (run / "claims" / "clm-1.json").write_text(
        json.dumps(decided, indent=2) + chr(10), encoding="utf-8", newline=""
    )
    (run / "screenshots" / "0004-log_in.png").write_bytes(b"\x89PNG\r\n\x1a\n not really")
    (run / "documents" / "clm-1-eob.pdf").write_bytes(b"%PDF-1.4 not really")
    return run


def test_an_exported_run_carries_no_credential(tmp_path: Path) -> None:
    """The check the sandbox archive already gets, given to the other artifact.

    Its value is that it runs over everything, so nobody has to remember which
    parts were argued safe.
    """
    exported = publish(a_run(tmp_path / "runs"), tmp_path / "out")

    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(exported.rglob("*"))
        if path.is_file() and path.suffix in {".ndjson", ".json"}
    )

    assert FINGERPRINT not in text
    assert "pt_token" not in text


def test_an_exported_run_opens_like_any_other(tmp_path: Path) -> None:
    """It is a run directory, not a report about one.

    The console reads it with the same code that reads a live one, so a shape
    the export invented would be a shape nothing can open.
    """
    from rcm_agent.console.replay import replay

    exported = publish(a_run(tmp_path / "runs"), tmp_path / "out")

    streamed = list(replay(exported.parent))

    assert [event["kind"] for event in streamed] == ["tool_call", "tool_result", "determination"]
    assert streamed[-1]["derived"]["determination"]["action"] == "appeal"


def test_the_documents_and_screenshots_come_too(tmp_path: Path) -> None:
    """The browser work is an inspector layer, so it has to survive the export."""
    exported = publish(a_run(tmp_path / "runs"), tmp_path / "out")

    assert (exported / "screenshots" / "0004-log_in.png").is_file()
    assert (exported / "documents" / "clm-1-eob.pdf").is_file()
    assert (exported / "claims" / "clm-1.json").is_file()


def test_what_the_run_actually_said_survives(tmp_path: Path) -> None:
    exported = publish(a_run(tmp_path / "runs"), tmp_path / "out")
    events = [
        json.loads(line)
        for line in (exported / "events.ndjson").read_text(encoding="utf-8").splitlines()
    ]

    determination = events[-1]["detail"]
    assert determination["action"] == "appeal"
    assert determination["priority"]["expected_recovery"] == "562.50"
    assert events[1]["detail"]["portal"].startswith("https://demo-8080.preview.getsolari.com")


def test_it_refuses_to_publish_over_something(tmp_path: Path) -> None:
    """An export that silently replaced a directory would be a bad surprise."""
    run = a_run(tmp_path / "runs")
    (tmp_path / "out" / run.name).mkdir(parents=True)

    with pytest.raises(UnsafeToPublish):
        publish(run, tmp_path / "out")


def test_it_refuses_a_run_that_never_finished(tmp_path: Path) -> None:
    """A half-written run published as an example is a demo of a crash.

    The status is in `run.json` precisely so this is answerable.
    """
    run = a_run(tmp_path / "runs")
    (run / "run.json").write_text(json.dumps({"run_id": run.name, "status": "running"}), "utf-8")

    with pytest.raises(UnsafeToPublish):
        publish(run, tmp_path / "out")


OLD_FINGERPRINT = "sk-ant-a...hwAA (108 chars)"
"""How runs recorded a key before the fingerprint became tail-only.

Older runs are exactly what an export exists to handle: a run directory outlives
the code that wrote it.
"""


def test_an_older_fingerprint_leaves_no_vendor_prefix_behind() -> None:
    """The shape is the problem, not the characters.

    A pattern anchored on the dots redacted the tail and left `sk-ant-a` in the
    published artifact - the same credential *shape* that failed a secret scanner
    on this repository once. Found by exporting a real run, not by this fixture.
    """
    redacted = json.dumps(redact({"key": OLD_FINGERPRINT}))

    assert "sk-ant" not in redacted
    assert "hwAA" not in redacted


def test_the_export_refuses_rather_than_publishing_a_vendor_prefix(tmp_path: Path) -> None:
    """Read back rather than trusted, because the rewrite is what could be wrong."""
    run = a_run(tmp_path / "runs")
    log = run / "events.ndjson"
    # A shape no redaction rule knows about, to prove the read-back is a real
    # gate and not a restatement of the rewrite.
    log.write_text(
        log.read_text(encoding="utf-8").replace(FINGERPRINT, "sk-ant-api03-untouchable"),
        encoding="utf-8",
    )

    with pytest.raises(UnsafeToPublish, match="still carries"):
        publish(run, tmp_path / "out")

    assert not (tmp_path / "out" / run.name).exists(), "a refused export is not left behind"


def test_the_guard_catches_a_prefix_with_almost_nothing_after_it(tmp_path: Path) -> None:
    """`sk-ant-a` is what a half-redacted old fingerprint leaves behind.

    An earlier guard wanted several characters after the prefix and let exactly
    that through - one short of its own threshold. The shape is what a secret
    scanner rejects, so the shape is what this refuses.
    """
    run = a_run(tmp_path / "runs")
    log = run / "events.ndjson"
    log.write_text(
        log.read_text(encoding="utf-8").replace(FINGERPRINT, "sk-ant-a"), encoding="utf-8"
    )

    with pytest.raises(UnsafeToPublish, match="still carries"):
        publish(run, tmp_path / "out")


# --- what the guard must not do ---------------------------------------------


def test_an_ordinary_phrase_does_not_make_a_run_unpublishable(tmp_path: Path) -> None:
    """`risk-adjusted` contains `sk-adjusted`.

    The guard's pattern was unanchored, so an everyday phrase in a
    denial-management domain - written by a model, into free text - matched it.
    The consequence was not a warning: the export refused *and deleted itself*,
    for a word.
    """
    # Asked for at the source rather than edited in afterwards: the rationale
    # is recorded in two places, and rewriting one of them makes a run that
    # disagrees with itself - which is a different refusal than the one under
    # test here.
    run = a_run(
        tmp_path / "runs", rationale="a risk-adjusted, task-based review of the disk-backed record"
    )

    exported = publish(run, tmp_path / "out")

    assert exported.is_dir(), "an ordinary rationale must not be treated as a key"
    assert "risk-adjusted" in (exported / "events.ndjson").read_text(encoding="utf-8")


def test_text_the_guard_reads_is_text_the_rewrite_touched(tmp_path: Path) -> None:
    """The two sets were different, and the gap was an export that could never pass.

    A `.txt` was scanned but never rewritten, so one carrying a fingerprint was
    copied verbatim and then refused - for ever, with no way to publish the run.
    """
    run = a_run(tmp_path / "runs")
    (run / "notes.txt").write_text(f"the key was {FINGERPRINT}\n", encoding="utf-8")

    exported = publish(run, tmp_path / "out")

    assert FINGERPRINT not in (exported / "notes.txt").read_text(encoding="utf-8")


def test_a_failed_rewrite_leaves_no_half_export(tmp_path: Path) -> None:
    """A half-redacted directory looks like an export and is not one."""
    run = a_run(tmp_path / "runs")
    (run / "claims" / "broken.json").write_text("{ not json at all", encoding="utf-8")

    with pytest.raises(UnsafeToPublish, match="could not be rewritten"):
        publish(run, tmp_path / "out")

    assert not (tmp_path / "out" / run.name).exists()


def test_the_read_back_can_fail_when_the_rewrite_did_not(tmp_path: Path) -> None:
    """Otherwise it restates the rewrite rather than checking it.

    A fingerprint whose head format drifted would slip past the pattern the
    rewrite uses. The guard matches the part of the shape least likely to move.
    """
    run = a_run(tmp_path / "runs")
    log = run / "events.ndjson"
    log.write_text(
        log.read_text(encoding="utf-8").replace(FINGERPRINT, "key#abcd# (108 chars)"),
        encoding="utf-8",
    )

    with pytest.raises(UnsafeToPublish, match="still carries"):
        publish(run, tmp_path / "out")


def test_a_query_string_is_cut_even_when_it_carries_nothing() -> None:
    """Blunt on purpose, and the bluntness costs something.

    A query in a run artifact is not worth keeping even when it holds no token,
    because deciding which ones are safe means reading them. The price is that a
    URL written in prose loses a trailing question mark and any harmless query
    with it - recorded here so it is a choice rather than a surprise.
    """
    assert redact({"note": "see https://example.test/wl?claim_id=CLM-1 for the row"}) == {
        "note": "see https://example.test/wl for the row"
    }


# --- what the walk must cover, whatever it is called -------------------------


def test_a_file_type_this_module_never_heard_of_is_still_redacted(tmp_path: Path) -> None:
    """The hole an allow-list left, and the reason it is now a deny-list.

    Unknown *keys* were covered from the start; unknown *file types* were not. A
    `.jsonl`, a `.log` and a `.yaml` were copied verbatim and never scanned - and
    `.jsonl` is the likely shape for the model exchange, the very content this
    export exists to cover.
    """
    run = a_run(tmp_path / "runs")
    (run / "transcript.jsonl").write_text(f'{{"key": "{FINGERPRINT}"}}\n', encoding="utf-8")
    (run / "notes.yaml").write_text("portal: " + TOKENED + "\n", encoding="utf-8")

    exported = publish(run, tmp_path / "out")

    assert FINGERPRINT not in (exported / "transcript.jsonl").read_text(encoding="utf-8")
    assert "pt_token" not in (exported / "notes.yaml").read_text(encoding="utf-8")


def test_a_token_outside_a_query_string_does_not_survive(tmp_path: Path) -> None:
    """Latent, not live - and that is exactly how the token got in last time.

    Solari puts it in a query string today, so `_QUERY` catches it. A fragment or
    a path segment slipped past every pattern.
    """
    run = a_run(tmp_path / "runs")
    log = run / "events.ndjson"
    log.write_text(
        log.read_text(encoding="utf-8").replace(
            TOKENED, "https://demo-8080.preview.getsolari.com/wl#pt_token=live-secret-xyz"
        ),
        encoding="utf-8",
    )

    exported = publish(run, tmp_path / "out")

    assert "pt_token" not in (exported / "events.ndjson").read_text(encoding="utf-8")


def test_a_markdown_link_keeps_its_brackets(tmp_path: Path) -> None:
    """`.md` is rewritten now, so the query pattern had to stop being greedy."""
    run = a_run(tmp_path / "runs")
    (run / "notes.md").write_text("see [the portal](https://host.test/wl?t=1) for it\n", "utf-8")

    exported = publish(run, tmp_path / "out")

    assert (exported / "notes.md").read_text(encoding="utf-8") == (
        "see [the portal](https://host.test/wl) for it\n"
    )


def test_an_image_is_published_exactly_as_captured(tmp_path: Path) -> None:
    """Not rewritten, but still read. Left alone is not the same as trusted."""
    run = a_run(tmp_path / "runs")
    original = (run / "screenshots" / "0004-log_in.png").read_bytes()

    exported = publish(run, tmp_path / "out")

    assert (exported / "screenshots" / "0004-log_in.png").read_bytes() == original


def test_a_published_claim_hashes_to_the_digest_a_review_would_name(tmp_path: Path) -> None:
    """The export is the artifact a reader checks, so it has to be checkable.

    A Review names the Determination it was given for by a digest over the exact
    bytes of `claims/<id>.json`, and the whole justification for that number is
    that anyone holding the file can recompute it. The export rewrites every
    text file it copies, and wrote them with the host's newline - so an export
    made on Windows carried CRLF, the digest was taken over the LF form, and the
    published artifact did not hash to the number published beside it.

    Same failure as ADR-0004 records for the writer, arriving by the one route
    that reaches a public artifact rather than a local one.
    """
    from rcm_agent.review import digest_of
    from rcm_agent.transport import sha256_of_bytes

    published = publish(a_run(tmp_path / "runs"), tmp_path / "out")

    for claim in sorted((published / "claims").glob("*.json")):
        recorded: Any = json.loads(claim.read_text(encoding="utf-8"))
        assert sha256_of_bytes(claim.read_bytes()) == digest_of(recorded), (
            f"{claim.name} does not hash to the digest of what it contains"
        )


def test_every_published_text_file_is_byte_identical_on_any_platform(tmp_path: Path) -> None:
    """An artifact read as a work sample is diffed, hashed and compared.

    One that differs by the operating system it was exported from is a different
    artifact each time it is produced.
    """
    published = publish(a_run(tmp_path / "runs"), tmp_path / "out")

    carriage_returns = [
        path.name
        for path in sorted(published.rglob("*"))
        if path.is_file() and path.suffix in {".json", ".ndjson"} and b"\r" in path.read_bytes()
    ]

    assert carriage_returns == []


def test_it_refuses_a_run_whose_artifact_disagrees_with_what_it_recorded(tmp_path: Path) -> None:
    """The published digest has to be the digest of the published file.

    A Review names its Determination by a digest, and the console computes that
    from the `determination` event while a reader recomputes it from
    `claims/<id>.json`. Those are two recordings of one judgement and they were
    unified deliberately - but a run directory outlives the code that wrote it,
    and an older one recorded a detail missing `claim_id` while its claims file
    carried it. Exported, that ships a public artifact whose published digest
    does not match its published file: ADR-0004's central claim, false in the
    one place a reviewer would check it.

    Refused here rather than explained in a caveat, because an export is the
    artifact that gets trusted.
    """
    run = a_run(tmp_path / "runs")
    stale = json.loads((run / "claims" / "clm-1.json").read_text(encoding="utf-8"))
    stale["rationale"] = "a rationale the recorded event never mentioned"
    (run / "claims" / "clm-1.json").write_text(json.dumps(stale), encoding="utf-8")

    with pytest.raises(UnsafeToPublish, match="does not match"):
        publish(run, tmp_path / "out")


def test_a_run_whose_artifact_agrees_is_published(tmp_path: Path) -> None:
    """The fixture's claim file is what the run recorded, so it goes."""
    published = publish(a_run(tmp_path / "runs"), tmp_path / "out")

    assert (published / "claims" / "clm-1.json").is_file()
