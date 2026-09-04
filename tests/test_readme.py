"""The README, checked against the thing it describes.

It is the first artifact a reader opens and the only one nothing was verifying.
It went stale exactly as you would expect: a banner promising the real README in
"a later ticket" survived into the ticket that was supposed to remove it, and a
Quick start still described a command that plays a scripted sequence.

These are cheap checks for the two ways a README lies without anyone noticing —
naming a command that does not exist, and linking a file that does not. Neither
can tell whether a sentence is *true*, and nothing here pretends to. What they
prevent is the class of rot that accumulates silently while every other test
stays green.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
README = (REPO / "README.md").read_text(encoding="utf-8")


def test_every_command_it_tells_you_to_run_exists() -> None:
    """`uv run rcm-agent <something>` has to name a real subcommand.

    Asked of the CLI rather than of a list beside it: each command the README
    names is invoked with `--help`, which argparse answers by exiting zero for a
    command it knows and two for one it does not. A README is where a reader
    learns the interface, and a command renamed out from under it spends the
    fifteen minutes this project's setup budget is measured in.
    """
    import pytest

    from rcm_agent.cli import main

    named = sorted(set(re.findall(r"rcm-agent ([a-z][a-z-]*)", README)))
    assert named, "the README stopped naming any command, which is itself suspicious"

    unknown: list[str] = []
    for command in named:
        with pytest.raises(SystemExit) as exit_code:
            main([command, "--help"])
        if exit_code.value.code != 0:
            unknown.append(command)

    assert unknown == [], f"the README names commands the CLI does not have: {unknown}"


def test_every_repository_path_it_links_exists() -> None:
    """Relative links are to files in this repository, so they can be checked."""
    linked = {target for target in re.findall(r"\]\((\./[^)#]+)\)", README)}
    assert linked, "the README stopped linking anything, which is itself suspicious"

    missing = sorted(target for target in linked if not (REPO / target.removeprefix("./")).exists())

    assert missing == []


def test_it_does_not_still_promise_itself() -> None:
    """The placeholder deferred the real README to "a later ticket" - this one.

    Pinned because a banner that outlives its ticket is the single most visible
    way this document can be out of date, and it survived several tickets that
    edited the file around it.
    """
    assert "Work in progress" not in README
    assert "placeholder" not in README.lower()


def test_it_states_the_departures_from_the_original_spec() -> None:
    """Stated, they read as judgement. Discovered, they read as oversight.

    The reader builds this platform for a living and will notice every one of
    them, so each is named in the README rather than left to be found.
    """
    for departure in ("FR-1", "FR-2", "FR-3", "Goal 2"):
        assert departure in README, f"{departure} is a departure the README has to state"


def test_it_names_both_credentials_as_prerequisites() -> None:
    """Documented up front, not discovered at the first failed run."""
    for credential in ("SOLARI_API_KEY", "ANTHROPIC_API_KEY"):
        assert credential in README


def test_it_points_at_the_run_a_reader_can_open_without_credentials() -> None:
    """The whole point of committing one: evaluate this without running it."""
    assert "docs/example-run" in README


def test_every_file_it_tells_you_to_copy_exists() -> None:
    """`cp .env.example .env` is useless advice if that file was never written.

    Found by running the instruction rather than reading it: `.gitignore` had
    carried `!.env.example` for months, anticipating a file nobody had added, and
    the link check above could not see it because it is not a link.
    """
    sources = re.findall(r"^cp ([^\s]+) ", README, flags=re.MULTILINE)
    assert sources, "no copy instructions to check"

    missing = sorted(name for name in sources if not (REPO / name).exists())

    assert missing == []


def test_the_architecture_diagram_is_there_and_names_what_it_must() -> None:
    """Browser, sandbox, both mocks, and where the artifacts go.

    A diagram is the one part of this README that cannot be checked for being
    *true*; this checks only that it is present and mentions the pieces the
    ticket asked it to show, so deleting it fails loudly.
    """
    fenced = re.findall(r"```mermaid\n(.*?)```", README, flags=re.DOTALL)
    assert fenced, "the architecture diagram is gone"

    diagram = "\n".join(fenced)
    for piece in ("Browser", "Sandbox", "portal", "practice-management", "runs/", "console"):
        assert piece in diagram, f"the diagram no longer shows {piece}"
