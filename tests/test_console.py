"""What the console guarantees before it shows a single claim.

Every check here is a promise made to somebody who is not the author: a reviewer
who must not install Node, a viewer whose machine is offline, a reader whose
system is in dark mode, someone who has asked their browser to stop animating
things. None of them can be verified by looking at the source of the app - they
are properties of the *built* output, which is what actually ships.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rcm_agent.console.server import STATIC_ROOT, create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(scope="module")
def built_css() -> str:
    """Every stylesheet the built page ships, concatenated."""
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(STATIC_ROOT.rglob("*.css"))
    )


def test_the_console_serves_a_page_with_no_build_step(client: TestClient) -> None:
    """A reviewer types one command and never installs Node.

    The bundle is committed for exactly this reason. If this fails, the build
    output is missing and the console is a repository that needs a toolchain
    rather than a demo that runs.
    """
    response = client.get("/")

    assert response.status_code == 200
    assert "Denial Recovery Console" in response.text

    referenced = re.findall(r"""(?:src|href)=["\']([^"\']+)["\']""", response.text)
    assert referenced, "the page references no assets, so it cannot be the built one"
    for asset in referenced:
        served = client.get("/" + asset.lstrip("./"))
        assert served.status_code == 200, f"the page references {asset}, which 404s"


def test_the_page_loads_nothing_from_the_network(built_css: str) -> None:
    """Offline, and on a first run, the page is whole.

    A remote stylesheet or font would work on the author's machine and fail in
    the room where it is being judged.

    What matters is what the page *loads*, not whether a URL appears anywhere in
    it. The bundle legitimately contains five: four XML namespace identifiers,
    which are names and never fetched, and React's link to its own error docs
    inside a message. Asserting no URL appears at all would fail on those and
    would still pass a page that fetched a font through a variable.
    """
    html = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(STATIC_ROOT.rglob("*.html"))
    )

    assert not re.search(r"""(href|src)\s*=\s*["\']?(https?:)?//""", html), (
        "the page asks the network for a resource at load"
    )
    assert not re.search(r"""@import\s+(url\()?["\']?(https?:)?//""", built_css), (
        "a stylesheet is pulled from a remote host"
    )
    assert not re.search(r"""url\(\s*["\']?(https?:)?//""", built_css), (
        "a stylesheet loads a remote asset"
    )

    # The script matters too. It is 194 KB and it *can* fetch - Vite ships a
    # modulepreload polyfill that calls `fetch` on same-origin hrefs - so
    # checking only the markup and the stylesheet would leave the failure this
    # docstring names uncaught. Every remote address in the bundle is named
    # here; a new one has to be looked at rather than waved through.
    benign = {
        "http://www.w3.org/1998/Math/MathML",
        "http://www.w3.org/1999/xlink",
        "http://www.w3.org/2000/svg",
        "http://www.w3.org/XML/1998/namespace",
        "https://react.dev/errors/",
    }
    script = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(STATIC_ROOT.rglob("*.js"))
    )
    found = set(re.findall(r"""https?://[^\s"\'`)]{0,60}""", script))

    assert found <= benign, f"the bundle carries an unexpected remote address: {found - benign}"


def test_the_type_is_the_operating_system_stack(built_css: str) -> None:
    """No webfont, and none needed.

    The reference this console borrows from ships Geist and then renders
    `ui-sans-serif` anyway - its "premium" typography is the OS stack set large,
    light and tight. Matching that costs no network request and no licence.
    """
    assert "system-ui" in built_css
    assert "@font-face" not in built_css


def test_both_themes_resolve_including_the_unstamped_default(built_css: str) -> None:
    """Three states, not two.

    An explicit choice stamps the root element; the default setting stamps
    nothing at all, and only `prefers-color-scheme` separates light from dark
    there. A palette defined solely behind an attribute never applies in the
    state most viewers are actually in.
    """
    # Quotes are stripped from attribute selectors when the CSS is minified, so
    # the assertions are written against the shape that actually ships.
    selectors = built_css.replace('"', "").replace("'", "")

    assert "prefers-color-scheme" in selectors, "the unstamped default needs this"
    assert "[data-theme=dark]" in selectors, "an explicit dark choice must win"
    assert ":not([data-theme=light])" in selectors, "an explicit light choice must win too"


def test_motion_stops_when_the_viewer_has_asked_it_to(built_css: str) -> None:
    """Set here, because there is nothing to inherit.

    The reference ships no reduced-motion rule at all. It matters more here than
    there: on this console motion will come to mean a claim changed, and someone
    who cannot use motion still has to be able to read the run.
    """
    assert "prefers-reduced-motion" in built_css


def test_the_guest_is_never_sent_the_console() -> None:
    """The sandbox serves mocks and runs the analysis kernel. It has no screen.

    Checked against the archive that actually ships rather than against the
    exclusion list, because the list is the intention and the archive is what
    happens.
    """
    import io as _io
    import tarfile

    from rcm_agent.hosting import working_copy_archive

    repo_root = Path(__file__).resolve().parent.parent
    with tarfile.open(fileobj=_io.BytesIO(working_copy_archive(repo_root)), mode="r:gz") as archive:
        names = archive.getnames()

    assert names, "the archive is empty, so this proves nothing"
    assert not [name for name in names if "console" in name]


def test_the_built_bundle_is_committed() -> None:
    """The guarantee behind every other test in this file."""
    assert (STATIC_ROOT / "index.html").is_file()
    assert any(STATIC_ROOT.rglob("*.js")), "no script was built"


def test_no_dependency_of_the_console_is_committed() -> None:
    """The bundle ships; the toolchain that produced it does not.

    Asked of git rather than of `.gitignore` - a pattern in that file is an
    intention, and this is git's own answer about what it would do.
    """
    import subprocess

    repo_root = Path(__file__).resolve().parent.parent
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "console/node_modules"],
        cwd=repo_root,
        capture_output=True,
    )

    assert ignored.returncode == 0, "console/node_modules is not ignored and could be committed"

    tracked = subprocess.run(
        ["git", "ls-files", "console"], cwd=repo_root, capture_output=True, text=True, check=True
    ).stdout.splitlines()

    assert not [path for path in tracked if "node_modules" in path]


def test_the_committed_bundle_was_built_from_the_committed_source() -> None:
    """Nothing else in this repository can catch a stale bundle.

    The TypeScript tests exercise the source and the tests above exercise the
    output, and until this existed nothing tied the two together: someone could
    change a component, forget to rebuild, and watch every check pass while the
    page a reviewer opens is the old one. The build stamps a digest of its
    inputs; this recomputes it.

    If it fails, the fix is `npm run build` in `console/`.
    """
    repo_root = Path(__file__).resolve().parent.parent
    console = repo_root / "console"
    stamp = STATIC_ROOT / "source-digest.txt"

    assert stamp.is_file(), "the bundle carries no source stamp; rebuild it"

    inputs = sorted(
        [path for path in (console / "src").rglob("*") if path.is_file()]
        + [
            console / name
            for name in ("index.html", "package.json", "tsconfig.json", "vite.config.ts")
        ],
        key=lambda path: path.relative_to(console).as_posix(),
    )
    digest = hashlib.sha256()
    for path in inputs:
        digest.update(path.relative_to(console).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())

    assert digest.hexdigest() == stamp.read_text(encoding="utf-8").strip(), (
        "the committed bundle was not built from the committed source - "
        "run `npm run build` in console/"
    )
