"""The two practice-management tools, against a real browser and a real chart.

The load-bearing test is `test_the_authorization_comes_back_as_typed_fields`.
The agent's one real reasoning step is comparing a validity range against a date
of service, and it cannot make that comparison against a paragraph — so if these
come back as prose, or come back parsed wrongly, the demo produces a confident
appeal built on a date nobody actually read.
"""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from tests.conftest import HERO_CLAIM, needs_browser

from rcm_agent.browser.perception import definition_pairs
from rcm_agent.browser.practice import read_auth_record, write_note
from rcm_agent.browser.session import as_storage_state
from rcm_agent.events import Event, EventStream
from rcm_agent.mocks.practice_management import storage_state as practice_storage_state
from rcm_agent.practice_io import parse_chart_date, render_chart_date
from rcm_agent.strict_json import RecordFileError

SECOND_CLAIM = "CLM-2026-0002"
"""The one with no Authorization on its chart, so "none on file" is testable."""


class Recorder:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def handle(self, event: Event) -> None:
        self.events.append(event)


def drive(practice_url: str, tmp_path: Path, body: Any) -> Recorder:
    """A browser signed in from the saved profile, exactly as the demo's is."""
    from patchright.async_api import async_playwright

    recorder = Recorder()
    stream = EventStream()
    stream.add_sink(recorder)

    async def go() -> None:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            context = await browser.new_context(
                storage_state=as_storage_state(practice_storage_state(practice_url))
            )
            page = await context.new_page()
            try:
                await body(page, stream, tmp_path / "screenshots")
            finally:
                await browser.close()

    asyncio.run(go())
    return recorder


# --- the chart date format, which both sides depend on ---------------------


def test_a_chart_date_survives_a_round_trip() -> None:
    """The renderer and the parser are inverses, or the agent reads a wrong date."""
    for value in (date(2026, 3, 14), date(2026, 1, 1), date(2026, 12, 31)):
        assert parse_chart_date(render_chart_date(value)) == value


def test_the_chart_date_does_not_depend_on_the_machine_locale() -> None:
    """`%b` would render `févr.` on a French machine and the parser would miss it.

    Spelled out on both sides instead, so the pair cannot disagree because of
    where someone happens to be running it.
    """
    assert render_chart_date(date(2026, 2, 1)) == "01-FEB-2026"


@pytest.mark.parametrize(
    "bad", ["", "2026-02-01", "01-FEBRUARY-2026", "32-FEB-2026", "01-XXX-2026"]
)
def test_a_date_that_is_not_a_chart_date_is_refused(bad: str) -> None:
    """Strict on purpose: a plausible wrong date here becomes a wrong appeal."""
    with pytest.raises(RecordFileError):
        parse_chart_date(bad)


def test_definition_pairs_reads_terms_and_values_from_the_tree() -> None:
    tree = (
        "- term: Valid From\n- definition: 01-FEB-2026\n- text: ignored\n- term: X\n- definition: Y"
    )

    assert definition_pairs(tree) == {"Valid From": "01-FEB-2026", "X": "Y"}


# --- read_auth_record ------------------------------------------------------


@needs_browser
def test_the_authorization_comes_back_as_typed_fields(practice_url: str, tmp_path: Path) -> None:
    """Dates as dates and codes as a list, because the agent has to compare them."""
    found: dict[str, Any] = {}

    async def body(page: Any, stream: EventStream, shots: Path) -> None:
        outcome = await read_auth_record(
            page, HERO_CLAIM, base_url=practice_url, stream=stream, screenshots=shots
        )
        found.update({"outcome": outcome.outcome, **outcome.detail})

    drive(practice_url, tmp_path, body)

    assert found["outcome"] == "ok", found
    assert found["authorization_number"] == "CHP-2026-0044719"
    assert date.fromisoformat(found["valid_from"]) == date(2026, 2, 1)
    assert date.fromisoformat(found["valid_to"]) == date(2026, 5, 31)
    assert found["covered_procedure_codes"] == ["E0601"]
    assert date.fromisoformat(found["date_of_service"]) == date(2026, 3, 14)


@needs_browser
def test_the_fields_are_enough_to_settle_the_question_the_denial_raises(
    practice_url: str, tmp_path: Path
) -> None:
    """The comparison the agent makes, made here to prove the inputs support it.

    The tool does not do this — deciding is the agent's job — but if the typed
    fields could not carry the decision, they would not be worth typing.
    """
    found: dict[str, Any] = {}

    async def body(page: Any, stream: EventStream, shots: Path) -> None:
        outcome = await read_auth_record(page, HERO_CLAIM, base_url=practice_url, stream=stream)
        found.update(outcome.detail)

    drive(practice_url, tmp_path, body)

    service = date.fromisoformat(found["date_of_service"])
    covers = (
        date.fromisoformat(found["valid_from"]) <= service <= date.fromisoformat(found["valid_to"])
    )

    assert covers, "the Authorization does not cover the date of service"
    assert "E0601" in found["covered_procedure_codes"], "the denied line is out of scope"


@needs_browser
def test_the_tool_does_not_decide_whether_the_authorization_covers_the_claim(
    practice_url: str, tmp_path: Path
) -> None:
    """No verdict in the result. The one reasoning step belongs to the agent."""
    detail: dict[str, Any] = {}

    async def body(page: Any, stream: EventStream, shots: Path) -> None:
        outcome = await read_auth_record(page, HERO_CLAIM, base_url=practice_url, stream=stream)
        detail.update(outcome.detail)

    drive(practice_url, tmp_path, body)

    for verdict in ("covers", "covered", "valid", "conclusion", "appealable"):
        assert verdict not in detail, f"the tool reached a conclusion: {verdict}"


@needs_browser
def test_a_chart_with_no_authorization_says_so_rather_than_failing(
    practice_url: str, tmp_path: Path
) -> None:
    """A patient with nothing on file is an answer about the world, not a fault."""
    seen: dict[str, Any] = {}

    async def body(page: Any, stream: EventStream, shots: Path) -> None:
        outcome = await read_auth_record(page, SECOND_CLAIM, base_url=practice_url, stream=stream)
        seen.update({"outcome": outcome.outcome, **outcome.detail})

    drive(practice_url, tmp_path, body)

    assert seen["outcome"] == "not_found"
    assert "No authorization on file" in str(seen["reason"])


# --- write_note ------------------------------------------------------------


@needs_browser
def test_a_note_is_written_and_still_there_on_reload(practice_url: str, tmp_path: Path) -> None:
    """The write-back is why this system could not be a static page."""
    note = "CHP-2026-0044719 covers E0601 on 14-MAR-2026. CO-197 is refutable."
    results: list[Any] = []

    async def body(page: Any, stream: EventStream, shots: Path) -> None:
        results.append(
            await write_note(
                page, HERO_CLAIM, text=note, base_url=practice_url, stream=stream, screenshots=shots
            )
        )
        # A fresh navigation, not the page the save redirected to.
        await page.goto(f"{practice_url}/search.do")
        await read_auth_record(page, HERO_CLAIM, base_url=practice_url, stream=stream)
        results.append(note in await page.content())

    drive(practice_url, tmp_path, body)

    assert results[0].ok, results[0]
    assert results[1], "the note was gone when the chart was opened again"


@needs_browser
def test_an_empty_note_is_refused_rather_than_written(practice_url: str, tmp_path: Path) -> None:
    outcomes: list[Any] = []

    async def body(page: Any, stream: EventStream, shots: Path) -> None:
        outcomes.append(
            await write_note(page, HERO_CLAIM, text="   ", base_url=practice_url, stream=stream)
        )

    drive(practice_url, tmp_path, body)

    assert outcomes[0].outcome == "refused"


@needs_browser
def test_the_saved_profile_means_no_sign_on_is_typed(practice_url: str, tmp_path: Path) -> None:
    """The second session arrives authenticated, which is the profile's whole job."""
    pages: list[str] = []

    async def body(page: Any, stream: EventStream, shots: Path) -> None:
        await page.goto(f"{practice_url}/search.do")
        pages.append(await page.content())

    drive(practice_url, tmp_path, body)

    assert "Practice Sign On" not in pages[0]
    assert "Find a Chart" in pages[0]
