# The Solari browser SDK ships no type stubs, so the session handle and the
# browser it wraps are both `Any`. Absorbed here, exactly as `sandbox.py` absorbs
# the sandbox SDK: this module is the untyped boundary, and the `Page` that
# crosses out of it is typed by patchright, which does ship stubs.
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false

"""Opening a Solari cloud browser, and always giving it back.

The tools take a `Page` and do not know where the browser is. That seam is why
they can be exercised against a local Chromium in the test suite and driven
against a cloud browser in the demo without a branch anywhere: this module is
the only thing that knows the difference.

**Stealth and CAPTCHA solving are off, and are named here so that staying off is
a decision rather than a default.** The platform offers both. This project does
not evade bot detection and does not solve CAPTCHAs — that is why the portal it
drives is a mock in the first place, since no real payer portal permits automated
access. Turning either on would quietly undo the reason the mock exists.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from rcm_agent.config import fingerprint
from rcm_agent.events import EventStream

if TYPE_CHECKING:  # pragma: no cover
    from patchright.async_api import Page


def as_storage_state(saved: dict[str, Any]) -> Any:
    """Hand a saved profile to Playwright, at the one place the types meet.

    `mocks.practice_management.storage_state` returns a plain dict because that
    module is uploaded to the sandbox and must not import patchright; Playwright
    wants its own `StorageState`. The two are the same bytes, so the conversion
    is a name for the boundary rather than a transformation — and having a name
    keeps the cast from being sprinkled through every caller.
    """
    return saved


DOWNLOADS_ARE_ACCEPTED = True
"""The EOB arrives as a download; a context that refuses them cancels it silently."""


@contextlib.asynccontextmanager
async def cloud_browser(
    api_key: str,
    stream: EventStream,
    *,
    profile_id: str | None = None,
    storage_state: dict[str, Any] | None = None,
    label: str = "browser",
) -> AsyncGenerator[Page]:
    """Yield a page on a Solari cloud browser, and release the session after.

    Closing is not optional and not best-effort: a browser left open holds one of
    the three concurrent sessions the Free tier allows, and the SDK's own note is
    that closing the browser alone would leave the session held until its plan
    deadline. So the session is closed, not just the browser — the `finally` here
    is the point of the function, the same as in `sandbox_session`.
    """
    from solari_browser import Solari

    client = Solari(api_key)
    stream.emit(
        phase="portal",
        kind="tool_call",
        tool="open_browser",
        detail={
            "system": label,
            "key": fingerprint(api_key),
            "profile": profile_id or ("saved storage state" if storage_state else "none"),
        },
    )

    # Inside the `try`, so a launch that fails still closes the client. The
    # failure this matters for is the concurrency limit, which arrives exactly
    # when a second browser is being opened beside a first — and leaking the
    # client there would make the next attempt worse, not better.
    session: Any = None
    try:
        session = await client.launch(
            profile_id=profile_id,
            # Both deliberate, and both must stay false. See the module docstring.
            stealth=False,
            captcha=False,
        )
        # A saved profile, applied to the context. Solari profiles *are*
        # Playwright storage states, and this SDK exposes `profile_id` on launch
        # but no way to create one, so the state goes on the context directly.
        # Same bytes, same effect, and reproducible from this repository rather
        # than from whoever last signed on by hand.
        context = await session.raw.new_context(
            accept_downloads=DOWNLOADS_ARE_ACCEPTED,
            storage_state=as_storage_state(storage_state) if storage_state else None,
        )
        page: Page = await context.new_page()
        stream.emit(
            phase="portal",
            kind="tool_result",
            tool="open_browser",
            outcome="ok",
            detail={"system": label, "session": session.id, "expires_at": session.expires_at},
        )
        yield page
    finally:
        if session is not None:
            with contextlib.suppress(Exception):
                await session.close()
        with contextlib.suppress(Exception):
            await client.close()
