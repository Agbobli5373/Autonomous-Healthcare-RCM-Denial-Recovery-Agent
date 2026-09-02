"""What the model can do, and what it is told about doing it.

The four browser tools, described for a planner rather than for a programmer.
Two rules shaped every description here:

**Say what an outcome means, not what to do about it.** The tools return
`session_expired`, `not_found`, `refused`, `unavailable`. The descriptions
explain what each one tells you about the world; they do not say "if you see
session_expired, call log_in". The recovery has to be the model's decision or
this is a scripted sequence wearing a costume, and the acceptance criteria for
this work say so explicitly.

**The credentials are not the model's business.** `log_in` takes no arguments.
The orchestrator holds the user and password and always will, so putting them in
the tool schema would place them in the model's context for no gain — and every
transcript, log and cache entry would carry them from then on.
"""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """\
You are working a denied medical claim in a payer's provider portal, using a \
browser. Your goal is to obtain the claim's EOB document — the Explanation of \
Benefits — and stop.

You have four tools. Each returns a structured outcome rather than raising, and \
the outcome tells you something true about the portal:

- `ok` — it did what you asked.
- `session_expired` — the portal signed you out. Nothing you were doing was \
wrong; the session is simply no longer valid, and anything needing a signed-in \
session will keep landing on the login page until that changes.
- `not_found` — the portal was read correctly and the thing is genuinely not \
there. Asking again the same way will get the same answer.
- `refused` — the portal rejected the credentials.
- `unavailable` — the tool tried several times and could not complete. This one \
is about the tool, not the portal.

Work out the order yourself from what you get back. When you have the EOB, say \
so in one short sentence and stop calling tools. If you conclude the EOB cannot \
be obtained, say that instead — do not keep trying past the point of learning \
something new.

Be economical: one tool call at a time, and no commentary between them."""


TOOL_NAMES: tuple[str, ...] = ("log_in", "search_claims", "open_claim", "download_eob")
"""The names, in one place.

They were written out in the schemas here and again as a cascade in the loop, and
a test asserting a third hardcoded copy could not have caught either drifting.
The loop now dispatches on this tuple and the test compares the two sides.
"""


def tool_schemas(claim_id: str) -> list[dict[str, Any]]:
    """The tool definitions sent to the model.

    `claim_id` is interpolated into the descriptions rather than only into the
    first user message, because a tool description is the thing the model reads
    at the moment it is choosing arguments.
    """
    return [
        {
            "name": "log_in",
            "description": (
                "Sign in to the payer portal and land on the denial worklist. "
                "Takes no arguments: the credentials are held by the system "
                "running you, not by you. Safe to call at any point."
            ),
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "search_claims",
            "description": (
                "Read the denial worklist, turning pages until the wanted claim "
                "is on screen. Returns the claim numbers it saw and how many "
                "pages it walked. Requires a signed-in session."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "looking_for": {
                        "type": "string",
                        "description": (
                            f"A claim number to walk the pages for, e.g. {claim_id!r}. "
                            "Omit to read the queue without looking for anything "
                            "in particular."
                        ),
                    }
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "open_claim",
            "description": (
                "Open one claim's detail page from the worklist. The claim must "
                "be on the page currently shown, which is what `search_claims` "
                "is for. Requires a signed-in session."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "claim_id": {
                        "type": "string",
                        "description": f"The claim number to open, e.g. {claim_id!r}.",
                    }
                },
                "required": ["claim_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "download_eob",
            "description": (
                "Download the EOB document from the claim detail page currently "
                "open, saving it to the orchestrator's disk. This is the goal. "
                "Requires that claim's detail page to be open."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "claim_id": {
                        "type": "string",
                        "description": f"The claim whose EOB to download, e.g. {claim_id!r}.",
                    }
                },
                "required": ["claim_id"],
                "additionalProperties": False,
            },
        },
    ]


def opening_message(claim_id: str) -> str:
    return (
        f"Obtain the EOB document for claim {claim_id}. "
        "You are starting with a browser open and not signed in."
    )
