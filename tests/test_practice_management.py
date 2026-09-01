# starlette's TestClient carries no usable types in this version - it is being
# deprecated in favour of an httpx2-based client - so every `response.text` is
# Unknown. Contained here rather than sprinkled through the assertions.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from rcm_agent.mocks import fixtures_data
from rcm_agent.mocks.portal import create_app as create_portal
from rcm_agent.mocks.practice_management import create_app, storage_state
from rcm_agent.mocks.practice_management.app import SEEDED_SESSION, SESSION_COOKIE

CREDENTIALS = {"loginForm.userName": "rcm.demo", "loginForm.password": "demo"}
"""Struts-era field names, kept in the tests so a rename cannot pass silently."""

HERO_PATIENT = "PAT-40219"
HERO_CLAIM = "CLM-2026-0001"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as instance:
        yield instance


@pytest.fixture
def signed_on(client: TestClient) -> TestClient:
    client.post("/signin.do", data=CREDENTIALS)
    return client


def chart_of(client: TestClient, claim_id: str = HERO_CLAIM) -> str:
    return client.get(f"/chart.do?cid={claim_id}").text


def dmy(value: date) -> str:
    """The format the system prints dates in. Asserted, not assumed."""
    return value.strftime("%d-%b-%Y").upper()


# --- sign on ---------------------------------------------------------------


def test_an_anonymous_visitor_is_sent_to_the_sign_on_page(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)

    assert response.headers["location"] == "/signin.do"


@pytest.mark.parametrize("path", ["/search.do", f"/chart.do?cid={HERO_CLAIM}"])
def test_nothing_is_reachable_without_signing_on(client: TestClient, path: str) -> None:
    response = client.get(path, follow_redirects=False)

    assert response.headers["location"] == "/signin.do"


def test_signing_on_lands_on_the_patient_search(client: TestClient) -> None:
    response = client.post("/signin.do", data=CREDENTIALS, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/search.do"


def test_empty_credentials_are_refused(client: TestClient) -> None:
    response = client.post("/signin.do", data=dict.fromkeys(CREDENTIALS, ""))

    assert "required" in response.text


def test_signing_out_ends_the_session_rather_than_only_dropping_the_cookie(
    signed_on: TestClient,
) -> None:
    """Deleting the cookie proves nothing: the caller can just set it again.

    An earlier version signed everyone on as one shared constant, so signing out
    cleared the browser and left the session itself perfectly usable. This puts
    the cookie back by hand, which is exactly what that version failed.
    """
    token = signed_on.cookies.get(SESSION_COOKIE)
    assert token is not None

    signed_on.get("/signout.do")
    signed_on.cookies.set(SESSION_COOKIE, token)

    assert signed_on.get("/search.do", follow_redirects=False).status_code == 303


def test_signing_on_mints_a_session_of_its_own(client: TestClient) -> None:
    """Not the seeded constant. Two browsers must not share one session."""
    client.post("/signin.do", data=CREDENTIALS)

    assert client.cookies.get(SESSION_COOKIE) not in (None, SEEDED_SESSION)


# --- the saved profile -----------------------------------------------------


def test_a_seeded_session_cookie_is_already_signed_on(client: TestClient) -> None:
    """This is the whole point of the second Solari profile: no login on screen."""
    client.cookies.set(SESSION_COOKIE, SEEDED_SESSION)

    assert client.get("/search.do", follow_redirects=False).status_code == 200


def test_the_storage_state_actually_signs_the_browser_on() -> None:
    """Asserting the shape of the JSON would prove nothing about whether it works.

    So the cookie is taken out of the generated storage state and handed to a
    client, which is what Solari does with an uploaded profile.
    """
    state = storage_state("http://127.0.0.1:8081")
    cookie = state["cookies"][0]

    with TestClient(create_app()) as browser:
        browser.cookies.set(cookie["name"], cookie["value"])

        assert browser.get("/search.do", follow_redirects=False).status_code == 200


def test_the_storage_state_carries_the_host_it_was_asked_for() -> None:
    """A cookie scoped to the wrong host restores nothing, silently."""
    state = storage_state("https://abc123.preview.getsolari.com:443/x")

    assert state["cookies"][0]["domain"] == "abc123.preview.getsolari.com"
    assert state["cookies"][0]["secure"] is True


def test_the_storage_state_is_the_same_every_time_it_is_written() -> None:
    """A profile regenerated twice must not differ, or the diff is noise."""
    assert storage_state("http://localhost:8081") == storage_state("http://localhost:8081")


def test_a_saved_profile_still_works_against_a_process_that_never_issued_it() -> None:
    """The whole reason the seeded id is a constant rather than minted at run time.

    A profile is captured once and replayed on every later run. If only sessions
    this process issued were honoured, the saved profile would be dead by the
    second run and would fall back to the sign-on page without saying so.
    """
    cookie = storage_state("http://127.0.0.1:8081")["cookies"][0]

    with TestClient(create_app()) as later_run:
        later_run.cookies.set(cookie["name"], cookie["value"])

        assert later_run.get("/search.do", follow_redirects=False).status_code == 200


def test_a_session_minted_by_one_process_does_not_work_against_another() -> None:
    """The seeded id is the exception, not the rule. Everything else is per process."""
    with TestClient(create_app()) as first:
        first.post("/signin.do", data=CREDENTIALS)
        token = first.cookies.get(SESSION_COOKIE)

    with TestClient(create_app()) as second:
        second.cookies.set(SESSION_COOKIE, token or "")

        assert second.get("/search.do", follow_redirects=False).status_code == 303


@pytest.mark.parametrize(
    ("key", "expected"),
    [("path", "/"), ("httpOnly", True), ("sameSite", "Lax"), ("expires", 2556057600)],
)
def test_the_storage_state_carries_what_playwright_needs(key: str, expected: object) -> None:
    """Playwright rejects a cookie missing these, and Solari stores Playwright's format.

    Nothing here loads the file in a real browser — that check is manual — so
    these assert the fields that would make the load fail silently if dropped.
    """
    assert storage_state("http://127.0.0.1:8081")["cookies"][0][key] == expected


# --- looking a patient up --------------------------------------------------


def test_the_search_starts_empty_rather_than_listing_every_patient(
    signed_on: TestClient,
) -> None:
    """A practice does not open on a list of everyone it has ever seen."""
    page = signed_on.get("/search.do").text

    assert HERO_PATIENT not in page


def test_a_patient_can_be_found_by_patient_id(signed_on: TestClient) -> None:
    results = signed_on.get(f"/search.do?q={HERO_PATIENT}").text

    assert "RIVERA" in results


def test_a_patient_can_be_found_by_claim_number(signed_on: TestClient) -> None:
    """The agent arrives holding a claim number, not a name."""
    results = signed_on.get(f"/search.do?q={HERO_CLAIM}").text

    assert HERO_PATIENT in results


def test_a_patient_can_be_found_by_surname(signed_on: TestClient) -> None:
    results = signed_on.get("/search.do?q=rivera").text

    assert HERO_PATIENT in results


def test_a_search_that_matches_nothing_says_so(signed_on: TestClient) -> None:
    assert "No charts matched" in signed_on.get("/search.do?q=zzzz").text


def test_an_unknown_patient_chart_is_not_found(signed_on: TestClient) -> None:
    assert signed_on.get("/chart.do?cid=CLM-0000").status_code == 404


# --- the Authorization -----------------------------------------------------


def test_the_chart_shows_the_authorization_number(signed_on: TestClient) -> None:
    record = fixtures_data.find_record(HERO_CLAIM)
    assert record is not None and record.authorization is not None

    assert record.authorization.authorization_number in chart_of(signed_on)


def test_the_chart_shows_the_validity_range_as_two_readable_dates(
    signed_on: TestClient,
) -> None:
    """The agent compares this range against the date of service. It has to be legible."""
    record = fixtures_data.find_record(HERO_CLAIM)
    assert record is not None and record.authorization is not None
    chart = chart_of(signed_on)

    assert dmy(record.authorization.valid_from) in chart
    assert dmy(record.authorization.valid_to) in chart


def test_the_chart_shows_the_covered_hcpcs_scope(signed_on: TestClient) -> None:
    record = fixtures_data.find_record(HERO_CLAIM)
    assert record is not None and record.authorization is not None

    chart = chart_of(signed_on)
    for code in record.authorization.covered_procedure_codes:
        assert code in chart


def test_the_chart_shows_the_date_of_service_beside_the_range(signed_on: TestClient) -> None:
    """Both halves of the comparison on one screen, or the agent has to remember one."""
    record = fixtures_data.find_record(HERO_CLAIM)
    assert record is not None

    assert dmy(record.date_of_service) in chart_of(signed_on)


def test_a_chart_without_an_authorization_says_none_is_on_file(signed_on: TestClient) -> None:
    """Finding one proves nothing unless the screen can say there is none."""
    record = fixtures_data.find_record("CLM-2026-0002")
    assert record is not None and record.authorization is None

    assert "No authorization on file" in chart_of(signed_on, record.claim_id)


# --- writing a note back ---------------------------------------------------


def test_a_note_is_visible_after_a_reload(signed_on: TestClient) -> None:
    """The write-back is the reason this cannot be a static mock."""
    signed_on.post(
        "/note.do",
        data={"noteForm.claimNo": HERO_CLAIM, "noteForm.noteText": "Appeal packet submitted."},
    )

    assert "Appeal packet submitted." in chart_of(signed_on)


def test_saving_a_note_redirects_rather_than_re_rendering(signed_on: TestClient) -> None:
    """Post-redirect-get, so the reload that proves persistence is a plain GET."""
    response = signed_on.post(
        "/note.do",
        data={"noteForm.claimNo": HERO_CLAIM, "noteForm.noteText": "x"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"/chart.do?cid={HERO_CLAIM}")


def test_notes_accumulate_rather_than_replacing_each_other(signed_on: TestClient) -> None:
    for note in ("first note", "second note"):
        signed_on.post("/note.do", data={"noteForm.claimNo": HERO_CLAIM, "noteForm.noteText": note})

    chart = chart_of(signed_on)
    assert "first note" in chart
    assert "second note" in chart


def test_a_note_lands_only_on_the_chart_it_was_written_to(signed_on: TestClient) -> None:
    other = fixtures_data.find_record("CLM-2026-0002")
    assert other is not None
    signed_on.post(
        "/note.do", data={"noteForm.claimNo": HERO_CLAIM, "noteForm.noteText": "hero only"}
    )

    assert "hero only" not in chart_of(signed_on, other.claim_id)


def test_an_empty_note_is_not_saved(signed_on: TestClient) -> None:
    signed_on.post("/note.do", data={"noteForm.claimNo": HERO_CLAIM, "noteForm.noteText": "  "})

    assert "No notes on this chart" in chart_of(signed_on)


def test_a_note_cannot_be_written_without_a_session(client: TestClient) -> None:
    response = client.post(
        "/note.do",
        data={"noteForm.claimNo": HERO_CLAIM, "noteForm.noteText": "unauthenticated"},
        follow_redirects=False,
    )

    assert response.headers["location"] == "/signin.do"


def test_a_note_is_escaped_rather_than_rendered(signed_on: TestClient) -> None:
    signed_on.post(
        "/note.do",
        data={"noteForm.claimNo": HERO_CLAIM, "noteForm.noteText": "<script>alert(1)</script>"},
    )

    assert "<script>alert(1)</script>" not in chart_of(signed_on)


# --- a different system, not a reskin --------------------------------------


def _classes(html: str) -> set[str]:
    return {c for value in re.findall(r'class="([^"]*)"', html) for c in value.split()}


def _colours(html: str) -> set[str]:
    return {match.lower() for match in re.findall(r"#[0-9a-fA-F]{3,6}", html)}


def test_the_two_systems_share_no_styling_vocabulary(signed_on: TestClient) -> None:
    """Both appear in the same video. If they read as one thing, the demo loses half its claim.

    Class names and colours are a proxy for "looks different", not a proof of it
    — but they are the part that rots silently, and a shared stylesheet is how a
    reskin would happen by accident.
    """
    with TestClient(create_portal(latency=0.0)) as portal_client:
        portal = portal_client.get("/login").text
    practice = signed_on.get("/search.do").text

    assert not _classes(portal) & _classes(practice), "the two share a class name"
    assert not _colours(portal) & _colours(practice), "the two share a colour"


def test_neither_system_carries_the_other_name(signed_on: TestClient) -> None:
    with TestClient(create_portal(latency=0.0)) as portal_client:
        portal = portal_client.get("/login").text

    assert "NORTHWIND" not in portal
    assert "CASCADE HEALTH PLAN" not in signed_on.get("/search.do").text


def test_the_signed_on_pages_carry_a_navigation_rail_the_portal_has_none_of(
    signed_on: TestClient,
) -> None:
    """The layout difference a viewer registers before reading a single word."""
    assert "Patient Search" in signed_on.get("/search.do").text
    assert "Authorizations" in chart_of(signed_on)


# --- no automation hooks ---------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/signin.do", "/search.do", f"/search.do?q={HERO_CLAIM}", f"/chart.do?cid={HERO_CLAIM}"],
)
def test_no_page_carries_an_automation_hook(signed_on: TestClient, path: str) -> None:
    """Same discipline as the payer portal, for the same reason."""
    html = signed_on.get(path).text

    assert "data-testid" not in html
    assert "aria-" not in html
    assert not re.search(r"\srole\s*=", html)
    assert not re.search(r'\sid\s*=\s*"[^"]+"', html), "a stable element id crept in"
