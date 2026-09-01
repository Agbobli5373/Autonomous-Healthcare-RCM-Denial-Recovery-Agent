# starlette's TestClient carries no usable types in this version - it is being
# deprecated in favour of an httpx2-based client - so every `response.text` is
# Unknown. Contained here rather than sprinkled through the assertions.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false

from __future__ import annotations

import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from rcm_agent.mocks import fixtures_data
from rcm_agent.mocks.portal import create_app
from rcm_agent.mocks.portal.app import EXPIRE_ON_CLAIM_VIEW, PAGE_SIZE, page_count

CREDENTIALS = {"ctl00$phBody$txtUserId": "provider", "ctl00$phBody$txtPwd": "demo"}
"""The portal's form field names are deliberately ugly, so the tests carry them too."""

HERO_CLAIM = "CLM-2026-0001"
"""The CO-197 prior-authorization claim the demo follows."""


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(latency=0.0)) as instance:
        yield instance


@pytest.fixture
def signed_in(client: TestClient) -> TestClient:
    client.post("/login", data=CREDENTIALS)
    return client


@pytest.fixture
def working(client: TestClient) -> TestClient:
    """Signed in and past the deliberate expiry, the way the agent gets there.

    The portal bounces the first claim-detail view on purpose. Anything that
    wants to look at a claim has to recover first, exactly as the agent does.
    """
    client.post("/login", data=CREDENTIALS)
    client.get(f"/clm/{HERO_CLAIM}", follow_redirects=False)
    client.post("/login", data=CREDENTIALS)
    return client


def open_claim(client: TestClient, claim_id: str) -> str:
    """Open a claim detail and return its HTML."""
    return client.get(f"/clm/{claim_id}").text


# --- sign in ---------------------------------------------------------------


def test_an_anonymous_visitor_is_sent_to_the_login_page(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)

    assert response.headers["location"] == "/login"


def test_the_worklist_is_not_reachable_without_signing_in(client: TestClient) -> None:
    response = client.get("/wl", follow_redirects=False)

    assert response.headers["location"] == "/login"


def test_signing_in_lands_on_the_worklist(client: TestClient) -> None:
    response = client.post("/login", data=CREDENTIALS, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/wl"


def test_empty_credentials_are_refused(client: TestClient) -> None:
    response = client.post("/login", data=dict.fromkeys(CREDENTIALS, ""))

    assert "required" in response.text


# --- the worklist arrives asynchronously -----------------------------------


def test_the_worklist_page_carries_no_rows_of_its_own(signed_in: TestClient) -> None:
    """Reading this page is not reading the claims.

    The rows arrive by XHR, so anything that sleeps a fixed interval and scrapes
    gets the spinner. Waiting on a condition is the only thing that works.
    """
    shell = signed_in.get("/wl").text

    assert "Retrieving claims" in shell
    assert HERO_CLAIM not in shell


def test_the_rows_arrive_from_a_separate_request(signed_in: TestClient) -> None:
    rows = signed_in.get("/wl/rows?p=1").text

    assert "<table" in rows


def test_the_rows_endpoint_also_requires_a_session(client: TestClient) -> None:
    assert client.get("/wl/rows?p=1").status_code == 401


# --- pagination ------------------------------------------------------------


def test_every_committed_claim_appears_somewhere_in_the_queue(signed_in: TestClient) -> None:
    pages = page_count()
    seen = "".join(signed_in.get(f"/wl/rows?p={n}").text for n in range(1, pages + 1))

    for claim in fixtures_data.worklist():
        assert claim.claim_id in seen


def test_the_queue_spans_more_than_one_page(signed_in: TestClient) -> None:
    assert len(fixtures_data.worklist()) > PAGE_SIZE


def test_the_hero_claim_is_not_on_the_first_page(signed_in: TestClient) -> None:
    """Forces navigation rather than scraping one screen.

    It falls out of the ordering rather than being special-cased: the queue is
    newest first and the prior-authorization claim is the oldest of the three.
    """
    assert HERO_CLAIM not in signed_in.get("/wl/rows?p=1").text
    assert HERO_CLAIM in signed_in.get("/wl/rows?p=2").text


def test_a_nonsense_page_number_falls_back_to_the_first(signed_in: TestClient) -> None:
    assert "Page 1 of" in signed_in.get("/wl/rows?p=banana").text


def test_a_page_past_the_end_shows_the_last(signed_in: TestClient) -> None:
    assert "Page 2 of 2" in signed_in.get("/wl/rows?p=99").text


# --- claim detail ----------------------------------------------------------


def test_claim_detail_shows_the_cas_triple_per_service_line(working: TestClient) -> None:
    """Per line, never flattened to one code per claim (ADR-0001)."""
    detail = open_claim(working, HERO_CLAIM)

    claim = fixtures_data.find(HERO_CLAIM)
    assert claim is not None
    for line in claim.service_lines:
        assert line.procedure_code in detail
        for adjustment in line.adjustments:
            assert adjustment.reason_code in detail
            assert f"{adjustment.amount:.2f}" in detail
            for remark in adjustment.remark_codes:
                assert remark in detail


def test_the_mixed_outcome_claim_shows_both_of_its_lines(working: TestClient) -> None:
    """A write-off beside a denial. If the portal hid it, the guardrail could not fire."""
    detail = open_claim(working, HERO_CLAIM)

    assert re.search(r">\s*45\s*<", detail), "the CO-45 write-off line is missing"
    assert re.search(r">\s*197\s*<", detail), "the CO-197 denial line is missing"


def test_the_eob_link_opens_a_new_tab(working: TestClient) -> None:
    detail = open_claim(working, HERO_CLAIM)

    assert 'target="_blank"' in detail


def test_an_unknown_claim_is_not_found(signed_in: TestClient) -> None:
    assert signed_in.get("/clm/CLM-9999").status_code == 404


def test_a_mistyped_claim_does_not_consume_the_expiry_budget(signed_in: TestClient) -> None:
    """Otherwise the expiry depends on how many claim numbers the agent fumbles."""
    signed_in.get("/clm/CLM-9999")
    signed_in.get("/clm/CLM-8888")

    response = signed_in.get(f"/clm/{HERO_CLAIM}", follow_redirects=False)

    assert response.status_code == 303, "the 404s burned the budget"


# --- the EOB document ------------------------------------------------------


def test_the_portal_serves_the_committed_fixture_pdf(working: TestClient) -> None:
    """The same bytes the extraction reads, so the two cannot drift apart."""
    claim = fixtures_data.find(HERO_CLAIM)
    assert claim is not None
    open_claim(working, HERO_CLAIM)

    response = working.get(f"/doc/{HERO_CLAIM}")

    assert response.headers["content-type"] == "application/pdf"
    assert response.content == claim.eob_path.read_bytes()


def test_the_document_is_served_as_a_download(working: TestClient) -> None:
    """The friction is download capture, and an inline PDF fires no download event."""
    open_claim(working, HERO_CLAIM)

    disposition = working.get(f"/doc/{HERO_CLAIM}").headers["content-disposition"]

    assert disposition.startswith("attachment")


def test_the_document_cannot_be_deep_linked(working: TestClient) -> None:
    """Otherwise the spinner, the pagination and the expiry are all skippable."""
    response = working.get(f"/doc/{HERO_CLAIM}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/clm/{HERO_CLAIM}"


def test_the_document_requires_a_session(client: TestClient) -> None:
    response = client.get(f"/doc/{HERO_CLAIM}", follow_redirects=False)

    assert response.headers["location"] == "/login"


# --- the deliberate session expiry -----------------------------------------


def test_the_session_expires_on_the_specified_navigation(signed_in: TestClient) -> None:
    """Action-triggered, so the recovery lands identically on every run."""
    response = signed_in.get(f"/clm/{HERO_CLAIM}", follow_redirects=False)
    for _ in range(EXPIRE_ON_CLAIM_VIEW - 1):
        assert response.status_code == 200
        response = signed_in.get(f"/clm/{HERO_CLAIM}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login?e=1"


def test_the_expiry_fires_once_and_not_on_every_session(signed_in: TestClient) -> None:
    """Otherwise the agent loops between the bounce and the login page forever.

    A per-session counter restarts at zero, so the recovered session expires on
    its first claim detail too and the claim is never reachable. The friction is
    one interruption to recover from, not a wall.
    """
    for _ in range(EXPIRE_ON_CLAIM_VIEW):
        signed_in.get(f"/clm/{HERO_CLAIM}", follow_redirects=False)
    signed_in.post("/login", data=CREDENTIALS)

    for _ in range(3):
        assert signed_in.get(f"/clm/{HERO_CLAIM}", follow_redirects=False).status_code == 200


def test_the_expiry_is_reachable_on_the_path_the_demo_actually_walks() -> None:
    """Sign in, worklist, paginate, open the one claim. That is the whole browser leg.

    An earlier version expired on the second claim detail, and the demo opens
    exactly one — so the friction existed and never fired on the only path that
    matters, while every test still passed.
    """
    with TestClient(create_app(latency=0.0)) as client:
        client.post("/login", data=CREDENTIALS)
        client.get("/wl")
        client.get("/wl/rows?p=1")
        client.get("/wl/rows?p=2")

        response = client.get(f"/clm/{HERO_CLAIM}", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/login?e=1"


def test_an_expired_session_says_so_on_the_login_page(signed_in: TestClient) -> None:
    for _ in range(EXPIRE_ON_CLAIM_VIEW):
        signed_in.get(f"/clm/{HERO_CLAIM}", follow_redirects=False)

    assert "session has ended" in signed_in.get("/login?e=1").text


def test_signing_in_again_recovers_the_session(signed_in: TestClient) -> None:
    """The agent's recovery has to actually work, not just be detectable."""
    for _ in range(EXPIRE_ON_CLAIM_VIEW):
        signed_in.get(f"/clm/{HERO_CLAIM}", follow_redirects=False)

    signed_in.post("/login", data=CREDENTIALS)

    assert signed_in.get(f"/clm/{HERO_CLAIM}").status_code == 200


def test_the_expiry_is_the_same_on_every_run() -> None:
    """Two independent sessions must bounce at exactly the same navigation."""
    outcomes: list[int] = []
    for _ in range(2):
        with TestClient(create_app(latency=0.0)) as client:
            client.post("/login", data=CREDENTIALS)
            for view in range(1, 5):
                if client.get(f"/clm/{HERO_CLAIM}", follow_redirects=False).status_code == 303:
                    outcomes.append(view)
                    break

    assert outcomes == [EXPIRE_ON_CLAIM_VIEW, EXPIRE_ON_CLAIM_VIEW]


# --- no automation hooks ---------------------------------------------------


@pytest.mark.parametrize("path", ["/login", "/wl", "/wl/rows?p=1", f"/clm/{HERO_CLAIM}"])
def test_no_page_carries_an_automation_hook(working: TestClient, path: str) -> None:
    """Authoring hooks here would test the hooks and prove nothing about the agent."""
    html = working.get(path).text

    assert "data-testid" not in html
    assert "aria-" not in html
    assert not re.search(r"\srole\s*=", html)
    assert not re.search(r'\sid\s*=\s*"[^"]+"', html), "a stable element id crept in"
