"""The console as something a stranger opens on the internet.

Everything here is about the difference between running this locally and putting
it where a reviewer can reach it. Three properties matter and none of them is
about features.

**Nothing credential-shaped ships.** The sandbox archive already gets this check
(`test_no_credential_travels_to_the_guest`); the exported run is the other
artifact that leaves this machine, and it gets the same one. Relying on nobody
ever committing a run that broke the invariant is how this repository has
already had to rewrite a branch's history once.

**Nothing on the page can start a run.** The agent's work is done before the
host ever sees it. The routes are enumerated rather than described, because a
route added later is exactly the thing a prose promise fails to notice.

**The published digest describes the published file.** A Review names its
Determination by a digest, and the hosted console is the one place a reviewer
would recompute it. If the committed artifact does not hash to the number shown
beside it, ADR-0004's central claim is false in public.
"""

from __future__ import annotations

import json
from pathlib import Path

from rcm_agent.console.replay import RunStream
from rcm_agent.fixtures.naming import claim_filename
from rcm_agent.transport import sha256_of_bytes

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "docs" / "example-run"


def the_run() -> Path:
    """The one run the hosted console serves.

    Required, not skipped-if-absent. It is committed, it is what the host
    serves, and a suite that went green when someone deleted it would be
    reporting on a demo that no longer has anything to show.
    """
    assert EXAMPLE.is_dir(), f"{EXAMPLE} is committed and the hosted console serves it"
    runs = [path for path in sorted(EXAMPLE.iterdir()) if path.is_dir()]
    assert len(runs) == 1, f"expected exactly one example run, found {[r.name for r in runs]}"
    return runs[0]


# --- what ships -------------------------------------------------------------


def test_the_committed_example_carries_nothing_credential_shaped() -> None:
    """The check the guest archive gets, given to the artifact that goes public.

    Read off the committed bytes rather than by re-running the export, because
    what is committed is what is served and what a reader clones.
    """
    from rcm_agent.publishable_run import refuse_if_credential_shaped

    refuse_if_credential_shaped(the_run())


def test_the_committed_example_is_a_completed_run() -> None:
    """A half-written run published as an example demonstrates a crash."""
    state = json.loads((the_run() / "run.json").read_text(encoding="utf-8"))

    assert state["status"] == "completed"


def test_every_committed_claim_hashes_to_the_digest_shown_beside_it() -> None:
    """The number a reviewer can check, checked.

    The console shows a Determination's digest and says a re-run producing a
    different one invalidates the verdict. That is only meaningful if the file
    in this repository hashes to the number on screen.
    """
    from rcm_agent.review import digest_of

    run = the_run()
    recorded = [
        json.loads(line)
        for line in (run / "events.ndjson").read_text(encoding="utf-8").splitlines()
        if line
    ]
    determinations = {
        event["claim_id"]: event["detail"] for event in recorded if event["kind"] == "determination"
    }
    assert determinations, "the example run decided nothing"

    for claim_id, detail in determinations.items():
        artifact = run / "claims" / claim_filename(claim_id)
        assert sha256_of_bytes(artifact.read_bytes()) == digest_of(detail), (
            f"{artifact.name} does not hash to the digest the console shows for {claim_id}"
        )


def test_the_committed_example_is_byte_identical_on_any_platform() -> None:
    """Cloned on Windows, it must be the same bytes it was exported as.

    `.gitattributes` marks the export `-text` for this reason: a checkout that
    rewrote its line endings would make every committed digest wrong on exactly
    the machines that convert them, and only on those.
    """
    converted = [
        path.name
        for path in sorted(the_run().rglob("*"))
        if path.is_file() and path.suffix in {".json", ".ndjson"} and b"\r" in path.read_bytes()
    ]

    assert converted == []


def test_the_example_opens_with_the_same_reader_as_any_run() -> None:
    """Not a report about a run - a run, read by the code that reads live ones."""
    claims = {
        event["claim_id"]: event["derived"]["action"]
        for event in RunStream(EXAMPLE).catch_up()
        if event["claim_id"] and event["derived"]["action"]
    }

    assert len(claims) >= 2, "the example should show more than one claim being worked"
    assert len(set(claims.values())) >= 2, (
        "an agent that answered the same Action everywhere would prove nothing; "
        "the example has to show it reaching different ones"
    )


def test_the_example_includes_a_claim_a_rule_closed() -> None:
    """The hardest thing this project has to communicate, and the reason to host it.

    An agent that appealed everything would get the unappealable one wrong. A
    demo without that claim in it shows the easy half.
    """
    ruled = [event for event in RunStream(EXAMPLE).catch_up() if event["derived"]["guardrailed"]]

    assert ruled, "no claim in the example was closed by a rule"


# --- what cannot happen -----------------------------------------------------


def test_the_hosted_console_has_no_route_that_reaches_the_agent(tmp_path: Path) -> None:
    """Enumerated, not promised.

    Nothing can be started from the host: no credentials are deployed and the
    agent's work is already done. A route added later that broke that is exactly
    what a sentence in a README fails to notice.

    This is also how `/openapi.json` was found still open on a console whose
    documentation routes had been deliberately turned off - a schema of every
    endpoint, published, because closing two of the three read as closing them.
    """
    from rcm_agent.console.server import create_app

    app = create_app(EXAMPLE, tmp_path / "reviews")

    assert {str(getattr(route, "path", "?")) for route in app.routes} == {
        "/events",
        "/healthz",
        "/reviews",
        "/reviews/{claim_id}",
        "/runs/{run_id}/screenshots/{name}",
        # The bundle, mounted at the root. Serving files is the whole of it.
        "",
    }


def test_the_build_context_cannot_contain_the_credentials_file() -> None:
    """The second line of defence, matching at any depth.

    What actually keeps credentials out of the image is the Dockerfile naming
    five paths instead of copying the tree. This is what catches the day someone
    writes `COPY . .` - and a bare `.env` is anchored at the context root, so it
    would miss a nested one, which is precisely the case a fallback is for.
    """
    ignored = (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert "**/.env" in ignored
    assert "**/.env.*" in ignored
    assert "runs/" in ignored, "real runs carry a key fingerprint and portal screenshots"


def test_the_image_is_built_from_named_paths_rather_than_the_tree() -> None:
    """The guarantee itself, rather than the fallback that backs it up."""
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    copied = [
        line.split(maxsplit=1)[1] for line in dockerfile.splitlines() if line.startswith("COPY ")
    ]

    assert copied, "the image has to copy something"
    for what in copied:
        assert not what.startswith(". "), f"{what!r} copies the whole context, `.env` included"


def test_the_hosted_console_needs_no_credentials_to_start(tmp_path: Path) -> None:
    """It reads a directory. There is nothing to authenticate to."""
    import os

    from rcm_agent.console.server import create_app

    removed = {
        name: os.environ.pop(name)
        for name in ("ANTHROPIC_API_KEY", "SOLARI_API_KEY")
        if name in os.environ
    }
    try:
        create_app(EXAMPLE, tmp_path / "reviews")
    finally:
        os.environ.update(removed)


# --- waking up --------------------------------------------------------------


def test_the_console_answers_a_health_check(tmp_path: Path) -> None:
    """Polled by the waking page from another origin while the instance boots."""
    from fastapi.testclient import TestClient

    from rcm_agent.console.server import create_app

    client = TestClient(create_app(EXAMPLE, tmp_path / "reviews"))
    answer = client.get("/healthz")

    assert answer.status_code == 200
    assert answer.json() == {"status": "awake"}
    assert answer.headers["access-control-allow-origin"] == "*", (
        "the waking page is served from a host that does not sleep, so it reads this "
        "cross-origin; without the header it cannot tell awake from unreachable"
    )


def test_the_waking_page_stands_alone() -> None:
    """It is on screen because the console is not, so it can depend on nothing.

    A front door that fetched a stylesheet would be showing nothing during
    exactly the window it exists to cover.
    """
    page = (REPO / "docs" / "hosting" / "waking.html").read_text(encoding="utf-8")

    assert "<link" not in page, "no external stylesheet"
    assert "src=" not in page, "no external script"
    assert "/healthz" in page, "it has to know what to poll"
    assert "prefers-reduced-motion" in page, "the sweep is motion, and it is suppressible"


def test_the_waking_page_will_not_forward_anywhere_it_is_told() -> None:
    """It is a public page on a trusted domain that redirects. That is a target.

    The `?console=` override exists so the page can be pointed at a console on
    this machine while it is being worked on. Unrestricted, it is an open
    redirect: a link on a domain a reader trusts, forwarding wherever it says.
    Only a local address is accepted.
    """
    page = (REPO / "docs" / "hosting" / "waking.html").read_text(encoding="utf-8")

    assert "localOnly" in page, "the override has to be filtered somewhere"
    for allowed in ('"localhost"', '"127.0.0.1"'):
        assert allowed in page
    assert "location.replace(origin" in page, "and the forward uses the filtered origin"


def test_the_waking_page_gives_up_gracefully_rather_than_spinning_forever() -> None:
    """A wrong origin must not read like the blank page it replaces.

    `CONSOLE_ORIGIN` is a placeholder until a deploy names the real URL, and
    Render suffixes a name that is taken. Retrying in silence past the point
    where "waking" explains it is the same failure wearing a nicer coat, so the
    page hands over the address and lets the reader decide.
    """
    page = (REPO / "docs" / "hosting" / "waking.html").read_text(encoding="utf-8")

    assert "Open the console directly" in page
    assert "createElement" in page, "the link is added, and `.status a` is styled for it"
