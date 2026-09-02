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
You are working a denied medical claim, using a browser. You have two unrelated \
systems open, and they know nothing about each other:

- The **payer's provider portal**, which holds the claim and its EOB document \
(the Explanation of Benefits). This is the payer's side of the story.
- The **practice-management system**, which holds the provider's own records for \
the same patient: what was done, when, and what the payer authorised in advance.

Your job has three parts. Obtain the claim's EOB. Establish whether a prior \
Authorization covered the service on the date it was delivered. Then record what \
you found as a note on the patient's chart, so a human picking this up later can \
see the reasoning without repeating it.

Each tool returns a structured outcome rather than raising, and the outcome tells \
you something true:

- `ok` — it did what you asked.
- `session_expired` — the portal signed you out. Nothing you were doing was \
wrong; the session is simply no longer valid, and anything needing a signed-in \
session will keep landing on the login page until that changes.
- `not_found` — the system was read correctly and the thing is genuinely not \
there. Asking again the same way will get the same answer.
- `refused` — the request was rejected as it stands.
- `unavailable` — the tool tried several times and could not complete. This one \
is about the tool, not the system it was reading.

`read_auth_record` gives you the Authorization as dates and codes, not prose, \
because deciding whether it covers the claim means comparing a date of service \
against a validity range and checking the procedure code is in scope. That \
comparison is yours to make; no tool makes it for you, and the note you write \
should say what you concluded and on what basis.

Work out the order yourself from what you get back. When you are done, say so in \
one or two short sentences and stop calling tools. If you conclude the work \
cannot be completed, say that instead — do not keep trying past the point of \
learning something new.

Be economical: one tool call at a time, and no commentary between them."""


TOOL_NAMES: tuple[str, ...] = (
    "log_in",
    "search_claims",
    "open_claim",
    "download_eob",
    "read_auth_record",
    "write_note",
)
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
        {
            "name": "read_auth_record",
            "description": (
                "Look a claim up in the practice-management system and read the "
                "prior Authorization on the patient's chart. Returns typed "
                "fields: the authorization number, the validity range as two "
                "dates, the covered HCPCS codes, and the claim's date of "
                "service. It reports what the chart says and does not decide "
                "whether the Authorization covers the claim — that is yours. "
                "Returns not_found when the chart holds no Authorization, which "
                "is a real answer about the patient rather than a fault. This is "
                "a different system from the portal and a different browser "
                "session; the portal's sign-in has nothing to do with it."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "claim_id": {
                        "type": "string",
                        "description": f"The claim to look up, e.g. {claim_id!r}.",
                    }
                },
                "required": ["claim_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "write_note",
            "description": (
                "Write a note onto the patient's chart in the practice-"
                "management system, and confirm it is there afterwards. Use it "
                "to record what you concluded and why, in a few sentences a "
                "colleague could act on. Say what the payer claimed, what the "
                "chart showed, and how the dates and codes compared."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "claim_id": {
                        "type": "string",
                        "description": f"The claim whose chart to write on, e.g. {claim_id!r}.",
                    },
                    "text": {
                        "type": "string",
                        "description": "The note. Plain prose, no markup.",
                    },
                },
                "required": ["claim_id", "text"],
                "additionalProperties": False,
            },
        },
    ]


def opening_message(claim_id: str) -> str:
    return (
        f"Work claim {claim_id}. The payer denied it saying no prior "
        "authorization was on file. Obtain the EOB, establish whether an "
        "Authorization in fact covered the service, and record what you find on "
        "the patient's chart.\n\n"
        "The portal is open and not signed in. The practice-management system is "
        "already signed in from a saved profile."
    )
