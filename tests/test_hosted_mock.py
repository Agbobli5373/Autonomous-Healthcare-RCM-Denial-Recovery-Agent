"""What a hosted mock is allowed to write down.

`preview_url` returns a URL whose query string carries an access token for the
port. The run directory is an audit trail that gets committed — issue #21 exists
to check exactly this before an example run is published — so the token must not
reach it. It did, in the first working version of this: two of them, in
`events.ndjson`, found by grepping a real run rather than by reasoning about it.
"""

from __future__ import annotations

import json

from rcm_agent.sandbox import HostedMock

TOKENED = "https://example-8080.preview.getsolari.com?pt_token=not-a-real-token"
"""Invented, not a trimmed copy of a real one.

A real host and the first characters of a real token were here briefly. Both were
already dead and the token was far too short to use, but a string shaped like a
credential is the thing secret scanning is right to shout about - the same
lesson the practice system's session id taught one ticket ago.
"""


def test_the_event_detail_carries_no_access_token() -> None:
    mock = HostedMock(name="payer-portal", port=8080, url=TOKENED)

    assert "pt_token" not in json.dumps(mock.as_event_detail())


def test_the_event_detail_still_identifies_the_exposed_port() -> None:
    """Redaction that removed the evidence would defeat the point of recording it."""
    detail = HostedMock(name="payer-portal", port=8080, url=TOKENED).as_event_detail()

    assert detail["port"] == 8080
    assert detail["name"] == "payer-portal"
    assert detail["url"] == "https://example-8080.preview.getsolari.com"


def test_a_url_without_a_query_string_survives_intact() -> None:
    plain = "https://example-8080.preview.getsolari.com"

    assert HostedMock(name="x", port=8080, url=plain).url_without_token == plain


def test_the_usable_url_is_still_available_to_the_caller() -> None:
    """The terminal needs the real thing; only the artifact is redacted."""
    mock = HostedMock(name="payer-portal", port=8080, url=TOKENED)

    assert mock.url == TOKENED
