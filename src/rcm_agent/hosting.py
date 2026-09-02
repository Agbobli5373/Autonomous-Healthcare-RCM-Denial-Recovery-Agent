"""Serving the mocks from inside the sandbox: what to ship, and how to start it.

Everything here is pure — it builds an archive and writes a script — so the whole
arrangement can be rehearsed on this machine before a sandbox is ever created.
`tests/test_hosting.py` extracts the archive into a temporary directory and runs
the very script the guest runs, which is what stops "it worked locally" from
meaning "it worked in a different tree with a different `sys.path`".

**One sandbox, three jobs.** The Free tier allows one concurrent sandbox, and
the agent visits the practice-management system while the analysis kernel is
still needed, so the same guest serves both mocks and runs the kernel. That is
forced by the plan rather than chosen.
"""

from __future__ import annotations

import io
import tarfile
from dataclasses import dataclass
from pathlib import Path

GUEST_ROOT = "/tmp/rcm"
"""Where the working copy lands. Mirrors the repository layout, deliberately.

`fixtures_data.FIXTURES_ROOT` walks up from its own file to find
`data/fixtures/`, so shipping `src/` without the matching `data/` beside it
leaves the mocks importable and empty — the worst of both outcomes.
"""

ORCHESTRATOR_ONLY: tuple[str, ...] = ("agent", "browser", "console")
"""Packages the guest has no business holding.

The rule is short: **the guest serves the mocks and runs the analysis kernel. It
never drives a browser, it never calls a model, and it has no screen.** These
packages do those things, so they stay on this machine - the sandbox is
reachable from the public internet through its preview URL for as long as the
demo runs, and code that talks to a model does not belong on it. `console` is
here for a quieter reason: it is a page for a person, and nobody is looking at
the guest.

This is the one exception to building the archive by walking rather than by
listing, and it is an *exclusion* rather than an inclusion for that reason: it
cannot silently drop a module the mocks need, only a package they must not
import. If that ever stopped being true, the rehearsal in
`tests/test_hosting.py` boots both servers out of this archive and would fail.
"""

WEB_PIP_PACKAGES: tuple[str, ...] = ("fastapi", "uvicorn", "python-multipart")
"""What serving needs. `python-multipart` is not optional: both sign-in forms
post as multipart, and without it FastAPI raises only when the form is submitted."""

HEALTH_TIMEOUT_SECONDS = 45.0
"""Generous. A server that has not bound in this long has not lost a race."""


@dataclass(frozen=True, slots=True)
class MockServer:
    """One mock, where it will answer, and how to know the answer is its own."""

    name: str
    factory: str
    """An import path uvicorn can call, as `module:callable`."""

    port: int
    marker: str
    """Text this mock's front page carries and no other server would.

    Without it the health check asks only "is something serving this port", and
    something else answering counts as success. That is not hypothetical: a
    review of this code ran the suite on a machine with an unrelated server on
    8080, the check passed, and the failure arrived later as a raw 404 — the
    exact "reads as a platform fault" outcome the check exists to prevent.
    """


MOCK_SERVERS: tuple[MockServer, ...] = (
    MockServer(
        "payer-portal",
        "rcm_agent.mocks.portal:create_app",
        8080,
        "CASCADE HEALTH PLAN",
    ),
    MockServer(
        "practice-management",
        "rcm_agent.mocks.practice_management:create_app",
        8081,
        "NORTHWIND PRACTICE MANAGER",
    ),
)


def working_copy_archive(repo_root: Path) -> bytes:
    """The working copy, as one gzipped tar.

    A tarball rather than a file-by-file upload for two reasons. It is one
    pre-signed PUT instead of forty, and — more importantly — it is built by
    walking the tree rather than by listing modules. #28 shipped a hand-listed
    subset, and when a module moved the guest silently lost it.

    Only what serving needs travels: the package's Python and the committed
    fixtures. Not the tests, not the generator's outputs beyond those fixtures,
    not `__pycache__` - whose stale `.pyc` files would shadow the sources this
    exists to ship - and not `ORCHESTRATOR_ONLY`, which is the single exception
    to the walk and is explained where it is defined.
    """
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        package = repo_root / "src" / "rcm_agent"
        for path in sorted(package.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            if path.relative_to(package).parts[0] in ORCHESTRATOR_ONLY:
                continue
            archive.add(path, arcname=str(path.relative_to(repo_root).as_posix()))
        for path in sorted((repo_root / "data" / "fixtures").rglob("*")):
            if path.is_file():
                archive.add(path, arcname=str(path.relative_to(repo_root).as_posix()))
    return buffer.getvalue()


def install_script(packages: tuple[str, ...] = WEB_PIP_PACKAGES) -> str:
    """Install what serving needs, and report rather than fail silently.

    It lives here beside the other guest scripts rather than being concatenated
    at the call site: one place to look for anything the guest is asked to run.
    Unlike its neighbours it is not rehearsed end to end by the tests, because
    doing that would mean running a real `pip install` — so it is at least
    checked for being valid Python that reports the shape the caller reads.
    """
    names = ", ".join(repr(p) for p in packages)
    return f"""
import json, subprocess, sys
result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q", {names}],
    capture_output=True, text=True,
)
print(json.dumps({{"returncode": result.returncode, "stderr": result.stderr[-400:]}}))
"""


def unpack_script(archive_path: str, root: str = GUEST_ROOT) -> str:
    """Unpack the working copy in the guest.

    `filter="data"` is the safe extraction mode and the 3.14 default, but it only
    exists from 3.12 — and the guest is not this machine. Passing it
    unconditionally raised a `TypeError` there, which reached the orchestrator as
    "unpacking produced no report" with nothing after the colon, because guest
    stderr was not being captured at the time. Both halves of that are fixed.
    """
    return f"""
import json, pathlib, sys, tarfile
root = pathlib.Path({root!r})
root.mkdir(parents=True, exist_ok=True)
safely = {{"filter": "data"}} if sys.version_info >= (3, 12) else {{}}
with tarfile.open({archive_path!r}, "r:gz") as archive:
    archive.extractall(root, **safely)
print(json.dumps({{"files": sum(1 for path in root.rglob("*") if path.is_file()),
                   "python": "%d.%d" % sys.version_info[:2]}}))
"""


def start_script(
    servers: tuple[MockServer, ...] = MOCK_SERVERS,
    root: str = GUEST_ROOT,
    timeout: float = HEALTH_TIMEOUT_SECONDS,
) -> str:
    """Code the guest runs: start each server, then wait for it to answer.

    **The health check runs here, inside the guest, before the orchestrator asks
    for a preview URL.** A browser pointed at a server that has not finished
    binding fails in a way that reads as a platform problem rather than as a
    race, and the demo run has to be unbroken.

    Healthy means *this mock* answered, matched by a marker on its front page —
    not merely that the port replied. Both mocks answer `/` with a redirect, and
    a redirect or an error page is fine as long as the marker is in it.

    Processes are detached from any terminal and their output is captured to a
    file, so a server that dies at startup leaves its traceback somewhere the
    orchestrator can read and report rather than a browser error minutes later.
    """
    specs = [
        {"name": s.name, "factory": s.factory, "port": s.port, "marker": s.marker} for s in servers
    ]
    return f"""
import json, os, pathlib, subprocess, sys, time, urllib.error, urllib.request

ROOT = {root!r}
LOGS = pathlib.Path(ROOT) / "logs"
LOGS.mkdir(parents=True, exist_ok=True)
SPECS = {specs!r}

env = dict(os.environ)
env["PYTHONPATH"] = ROOT + "/src"
env["PYTHONUNBUFFERED"] = "1"

started = []
for spec in SPECS:
    log = LOGS / (spec["name"] + ".log")
    with open(log, "wb") as handle:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", spec["factory"], "--factory",
             "--host", "0.0.0.0", "--port", str(spec["port"]), "--log-level", "warning"],
            cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, env=env,
        )
    # Closed here, not left open: the child holds its own descriptor, and this
    # script keeps running long after the handle stops being useful to it.
    started.append((spec, process, log))


def answered(port, marker):
    # Not "did something answer" but "did OUR server answer". Anything else on
    # the port is a different program, and treating it as success hands out a
    # preview URL for someone else\'s service.
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/" % port, timeout=3) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
    except Exception:
        return False
    return marker in body


report = {{"servers": [], "ok": True}}
for spec, process, log in started:
    # A deadline each, not one shared across all of them. Shared, a first server
    # that takes the whole budget leaves the second no time at all and fails it
    # for being second rather than for being broken.
    deadline = time.monotonic() + {timeout!r}
    healthy = False
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break            # it died; stop waiting for a corpse to answer
        if answered(spec["port"], spec["marker"]):
            healthy = True
            break
        time.sleep(0.25)
    entry = {{"name": spec["name"], "port": spec["port"], "pid": process.pid,
              "healthy": healthy, "exited": process.poll()}}
    if not healthy and process.poll() is None:
        # Alive but never identified itself: almost always another program
        # already holding the port, so say that rather than only "timed out".
        entry["note"] = "the port was not serving this mock within the timeout"
    if not healthy:
        report["ok"] = False
        entry["log"] = log.read_text(errors="replace")[-1500:] if log.exists() else ""
    report["servers"].append(entry)

pathlib.Path(ROOT, "server-pids.json").write_text(
    json.dumps([e["pid"] for e in report["servers"]])
)
print(json.dumps(report))
"""


def stop_script(root: str = GUEST_ROOT) -> str:
    """Stop whatever `start_script` started, and say what it stopped.

    Killing the sandbox would take the servers with it. This exists so that the
    teardown does not *depend* on that: a failure between starting the servers
    and the end of the run should not leave the demo's ports held by processes
    the orchestrator has forgotten about.
    """
    return f"""
import json, os, pathlib, signal
pids_file = pathlib.Path({root!r}, "server-pids.json")
stopped = []
if pids_file.exists():
    for pid in json.loads(pids_file.read_text()):
        try:
            os.kill(pid, signal.SIGTERM)
            stopped.append(pid)
        except (ProcessLookupError, PermissionError):
            pass
    pids_file.unlink()
print(json.dumps({{"stopped": stopped}}))
"""
