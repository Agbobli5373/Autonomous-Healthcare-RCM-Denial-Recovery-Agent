"""Rehearsing the guest on this machine.

The interesting test here is `test_the_archive_and_the_start_script_boot_both_
servers`: it extracts the archive into a temporary directory and runs the very
script the sandbox runs, against that tree. Nothing about it is a stand-in — the
same bytes, the same `sys.path`, the same uvicorn invocation, the same health
check.

That matters because every plausible failure of this arrangement is a path
failure: fixtures resolved relative to the wrong parent, a module that imports
something the guest lacks, a factory string that does not name anything. All of
them pass a unit test that asserts the script mentions the right port, and all
of them fail on a camera.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest

from rcm_agent.hosting import (
    MOCK_SERVERS,
    ORCHESTRATOR_ONLY,
    WEB_PIP_PACKAGES,
    MockServer,
    install_script,
    start_script,
    stop_script,
    unpack_script,
    working_copy_archive,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def archive() -> bytes:
    return working_copy_archive(REPO_ROOT)


def names_in(archive: bytes) -> set[str]:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        return set(tar.getnames())


# --- what travels ----------------------------------------------------------


def test_the_archive_carries_both_mock_applications(archive: bytes) -> None:
    names = names_in(archive)

    assert "src/rcm_agent/mocks/portal/app.py" in names
    assert "src/rcm_agent/mocks/practice_management/app.py" in names


def test_the_archive_carries_the_fixtures_the_mocks_serve(archive: bytes) -> None:
    """Shipping the code without the data leaves the mocks importable and empty."""
    names = names_in(archive)

    assert "data/fixtures/claims/clm-2026-0001.json" in names
    assert "data/fixtures/practice/clm-2026-0001.json" in names
    assert "data/fixtures/eobs/clm-2026-0001-eob.pdf" in names


def test_the_archive_is_built_by_walking_rather_than_by_listing(archive: bytes) -> None:
    """Every module in the package travels, so a moved file cannot be left behind.

    #28 hand-listed what to upload; when a module moved, the guest lost it and
    only one of two paths broke.
    """
    package = REPO_ROOT / "src" / "rcm_agent"
    on_disk = {
        str(path.relative_to(REPO_ROOT).as_posix())
        for path in package.rglob("*.py")
        if "__pycache__" not in path.parts
        # The one deliberate exclusion, tested for on its own just below. Written
        # as a subtraction so a new module anywhere else still has to travel.
        and path.relative_to(package).parts[0] not in ORCHESTRATOR_ONLY
    }

    assert on_disk <= names_in(archive)
    assert len(on_disk) > 20, "the exclusion swallowed most of the package"


def test_no_compiled_bytecode_travels(archive: bytes) -> None:
    """A stale .pyc would shadow the source this exists to ship."""
    assert not [name for name in names_in(archive) if ".pyc" in name or "__pycache__" in name]


def test_the_archive_holds_no_run_artifacts_or_credentials(archive: bytes) -> None:
    """Only the package and the committed fixtures. Nothing else is invited."""
    for name in names_in(archive):
        assert name.startswith(("src/rcm_agent/", "data/fixtures/")), name


# --- the rehearsal ---------------------------------------------------------


def test_the_archive_and_the_start_script_boot_both_servers(archive: bytes, tmp_path: Path) -> None:
    """The real archive, the real script, a real uvicorn, two real ports.

    Ports come from `MOCK_SERVERS`, so this occupies the same ones the demo does;
    if something local is already holding them the health check fails loudly
    rather than passing against someone else's server, because the pages are
    asserted too.
    """
    (tmp_path / "archive.tar.gz").write_bytes(archive)
    guest_root = str(tmp_path / "guest")

    unpacked = _run_guest_script(unpack_script(str(tmp_path / "archive.tar.gz"), guest_root))
    assert unpacked["files"] > 30, unpacked

    report = _run_guest_script(start_script(MOCK_SERVERS, guest_root, timeout=60.0))
    try:
        assert report["ok"], json.dumps(report, indent=2)
        assert [s["name"] for s in report["servers"]] == [s.name for s in MOCK_SERVERS]
        for served in report["servers"]:
            assert served["healthy"]
            assert served["exited"] is None
        _assert_the_pages_are_the_mocks()
    finally:
        stopped = _run_guest_script(stop_script(guest_root))
        assert len(stopped["stopped"]) == len(MOCK_SERVERS)


def test_the_health_check_reports_a_server_that_never_starts(tmp_path: Path) -> None:
    """A startup failure has to arrive as a report, not as a browser error later.

    The failure is real rather than simulated: the factory does not exist, so
    uvicorn dies exactly as it would if a module had been left out of the
    archive — the #28 failure, which is the one most likely to recur.
    """
    broken = (MockServer("broken", "rcm_agent.mocks.nonexistent:create_app", 8099, "never"),)

    report = _run_guest_script(start_script(broken, str(tmp_path), timeout=25.0))

    assert not report["ok"]
    assert report["servers"][0]["healthy"] is False
    assert report["servers"][0]["exited"] is not None, "a dead server should not be waited on"
    assert "nonexistent" in report["servers"][0]["log"], "the report must carry the reason"


def test_a_stranger_on_the_port_does_not_pass_the_health_check() -> None:
    """The bug this check was written with, and the reason it now matches a marker.

    A review ran the suite on a machine with an unrelated server on 8080. The
    health check reported healthy — something had answered — and the run then
    died later on a raw 404, which is precisely the "reads as a platform fault"
    failure the in-guest check exists to prevent.

    So a real foreign server is started here, on a port no mock uses, and the
    check must refuse it. Nothing is mocked: the failure was in what "answered"
    meant, and a stand-in would encode the same mistake.
    """
    import http.server
    import threading

    class Stranger(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<html>some other service entirely</html>")

        def log_message(self, format: str, *args: object) -> None:
            return  # the stdlib server logs to stderr otherwise

    server = http.server.HTTPServer(("127.0.0.1", 0), Stranger)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        occupied = (
            MockServer(
                "payer-portal", "rcm_agent.mocks.portal:create_app", port, "CASCADE HEALTH PLAN"
            ),
        )

        report = _run_guest_script(start_script(occupied, timeout=6.0))

        assert not report["ok"], "a stranger on the port was accepted as the mock"
        assert report["servers"][0]["healthy"] is False
    finally:
        server.shutdown()
        thread.join(timeout=5)
        _run_guest_script(stop_script())


def test_every_mock_declares_a_marker_no_other_server_would_carry() -> None:
    for server in MOCK_SERVERS:
        assert server.marker
        assert server.marker.upper() == server.marker, "markers are matched against page chrome"


def test_the_web_packages_are_the_ones_uvicorn_and_the_forms_need() -> None:
    """python-multipart's absence only shows when a form is posted, not at import."""
    assert set(WEB_PIP_PACKAGES) >= {"fastapi", "uvicorn", "python-multipart"}


@pytest.mark.parametrize(
    "script",
    [
        install_script(),
        unpack_script("/tmp/x.tar.gz"),
        start_script(),
        stop_script(),
    ],
)
def test_every_guest_script_is_runnable_python(script: str) -> None:
    """A syntax error in generated code is a mid-run failure, not a build failure.

    The other tests here run three of these for real. `install_script` is the one
    that cannot be rehearsed - doing so would mean a real `pip install` - so this
    is what stands between a broken f-string in it and a sandbox that gets as far
    as installing nothing.
    """
    compile(script, "<guest>", "exec")


def test_the_install_script_names_every_package_it_must_install() -> None:
    for package in WEB_PIP_PACKAGES:
        assert repr(package) in install_script()


def _run_guest_script(code: str) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=180
    )
    assert result.returncode == 0, result.stderr
    parsed: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    return parsed


def _assert_the_pages_are_the_mocks() -> None:
    """Proves the servers are ours, and that they found their fixtures."""
    import urllib.request

    portal = urllib.request.urlopen("http://127.0.0.1:8080/login", timeout=10).read().decode()
    assert "CASCADE HEALTH PLAN" in portal

    practice = urllib.request.urlopen("http://127.0.0.1:8081/signin.do", timeout=10).read().decode()
    assert "NORTHWIND PRACTICE MANAGER" in practice


# --- what the guest is never given -----------------------------------------


def test_no_credential_travels_to_the_guest(archive: bytes) -> None:
    """Neither key reaches the sandbox, and the archive is where that is decided.

    The Solari key would let the guest create more sandboxes; the Anthropic key
    would put a model credential on a host that is reachable from the public
    internet through a preview URL for as long as the demo runs. Both stay in the
    orchestrator, and `.env` is not among the two prefixes that travel.
    """
    import io as _io
    import tarfile as _tarfile

    with _tarfile.open(fileobj=_io.BytesIO(archive), mode="r:gz") as tar:
        names = tar.getnames()
        blob = b"".join(
            (tar.extractfile(name) or _io.BytesIO()).read()
            for name in names
            if name.endswith(".py")
        )

    assert not [name for name in names if ".env" in name]
    # The env var *names* are ordinary source; it is the values that must never
    # travel, and the only place they live is a gitignored file that does not.
    for secret in ("sk-ant-", "slr_live"):
        assert secret.encode() not in blob


def test_the_guest_is_never_sent_the_code_that_talks_to_a_model(archive: bytes) -> None:
    """The agent loop runs orchestrator-side, so it has no business in the guest.

    Shipping it would not leak the key by itself, but it is the kind of drift
    that ends with someone wondering why the sandbox needs an Anthropic client.
    """
    for package in ORCHESTRATOR_ONLY:
        assert not [n for n in names_in(archive) if f"/{package}/" in n], package
