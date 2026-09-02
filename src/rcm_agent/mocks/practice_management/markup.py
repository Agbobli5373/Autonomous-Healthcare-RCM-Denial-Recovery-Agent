"""The practice-management system's HTML.

**A different system, not a reskin of the payer portal.** Both appear as browser
sessions in the same video, and if they read as one thing the demo quietly loses
half of what it is claiming — that the agent operates two unrelated systems. So
they are different down to their lineage:

|  | Payer portal | This |
| --- | --- | --- |
| Stack it imitates | ASP.NET WebForms | Struts / JSP |
| Session cookie | `CHPSESSID` | `JSESSIONID` |
| Field names | `ctl00$phBody$txtUserId` | `noteForm.noteText` |
| URLs | `/clm/{id}` | `/chart.do?cid=` |
| Layout | full-width nested tables | sidebar rail beside content |
| Palette | cool navy on blue-grey | warm cream, dark slate, amber |
| Type | Verdana | Trebuchet MS |

A test asserts the two share no class name and no colour, because "looks
different" is the kind of requirement that rots silently.

**There are still no automation hooks**, for the same reason as the portal: no
`data-testid`, no stable `id`, no ARIA, no semantic class names. The agent finds
things by what is on the screen.
"""

from __future__ import annotations

from datetime import date
from html import escape

from rcm_agent.practice_io import PracticeRecord, render_chart_date

PRODUCT = "NORTHWIND PRACTICE MANAGER"
"""Invented, and audibly so.

Northwind is the canonical sample-database name, which reads to anyone technical
as "this is demo data" — the opposite of passing the mock off as a real vendor's
software.
"""

CLINIC = "Cascade Valley Respiratory Associates"

_STYLE = """
body{font:13px "Trebuchet MS",Tahoma,sans-serif;background:#fbf9f5;margin:0;color:#20242b}
.k1{background:#232830;color:#f2ede2;padding:9px 16px;border-bottom:3px solid #c07818}
.k2{float:right;font-size:11px;color:#a89f8d;padding-top:2px}
.k3{font-size:15px;letter-spacing:.08em}
/* Flex, not a guessed min-height: the rail stopped partway down the page and
   left the dark column hanging in mid-air on any chart taller than 420px. */
.x1{display:flex;min-height:calc(100vh - 41px)}
.m1{width:158px;flex:none;background:#333a45;padding:10px 0}
.m1 a{display:block;color:#d7cfc0;padding:6px 16px;text-decoration:none;font-size:12px}
.m1 a:hover{background:#3f4756;color:#fdfcf9}
.m2{flex:1;padding:16px 20px;min-width:0}
.g1{background:#fdfcf9;border:1px solid #d9d3c7;padding:0 0 10px;margin-bottom:14px}
.g2{background:#f3efe6;padding:7px 12px;border-bottom:1px solid #d9d3c7;
    font-weight:bold;font-size:12px;color:#4a3d28}
.p1{padding:10px 12px}
/* Grid, not floats: floated terms escaped their panel and collapsed into a
   column of orphaned labels at the foot of the page. Every string was still
   present, so nothing failed except the reading of it. Grid also keeps this
   visibly unlike the payer portal, which lays everything out in nested tables. */
.p1 dl{display:grid;grid-template-columns:150px 1fr;margin:0}
.p1 dt{color:#7a7060;font-size:11px;padding:3px 0}
.p1 dd{margin:0;padding:3px 0;font-size:12px}
.s1{background:#c07818;color:#fffaf2;border:0;padding:6px 14px;font-size:12px;cursor:pointer}
.s2{border:1px solid #c2b9a6;padding:4px;font-size:12px;background:#fffdf8}
.q1{padding:8px 12px;color:#7a7060;font-size:11px}
.q2{color:#8f3b12;padding:8px 12px;font-size:12px}
.n2{border-top:1px dotted #d9d3c7;padding:8px 12px;font-size:12px}
.n3{color:#7a7060;font-size:11px}
.z1{width:340px;margin:70px auto;background:#fdfcf9;border:1px solid #d9d3c7}
"""


def _dmy(value: date) -> str:
    """The date format this whole system prints, in one place.

    It was written out four times, and the two the agent has to compare - the
    date of service and the ends of the validity range - are among them.

    Delegated to `practice_io` because the agent has to read these back, and a
    renderer and a parser that disagree about month names would fail only on a
    machine with a different locale.
    """
    return render_chart_date(value)


def _shell(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head><title>"
        f"{escape(title)}</title><style>{_STYLE}</style></head><body>"
        f'<div class="k1"><span class="k2">{escape(CLINIC)}</span>'
        f'<span class="k3">{escape(PRODUCT)}</span></div>{body}'
        "</body></html>"
    )


def _page(title: str, body: str) -> str:
    """The authenticated chrome: a navigation rail beside the content.

    The rail is what makes this unmistakably not the payer portal at a glance,
    which is why it is on every signed-in page even where nothing on it is used.
    """
    return _shell(
        title,
        '<div class="x1"><div class="m1">'
        '<a href="/search.do">Patient Search</a>'
        '<a href="/search.do">Charts</a>'
        '<a href="/search.do">Claims &amp; Billing</a>'
        '<a href="/search.do">Authorizations</a>'
        '<a href="/signout.do">Sign Out</a>'
        "</div>"
        f'<div class="m2">{body}</div></div>',
    )


def sign_on(message: str = "") -> str:
    warning = f'<div class="q2">{escape(message)}</div>' if message else ""
    return _shell(
        "Practice Sign On",
        f"""
        <div class="z1"><div class="g2">Practice Sign On</div>
        {warning}
        <form method="post" action="/signin.do">
        <div class="p1">
          <dl>
            <dt>User Name</dt><dd>
              <input class="s2" type="text" name="loginForm.userName" size="22"></dd>
            <dt>Password</dt><dd>
              <input class="s2" type="password" name="loginForm.password" size="22"></dd>
            <dt>&nbsp;</dt><dd>
              <input class="s1" type="submit" value="Sign On"></dd>
          </dl>
        </div></form></div>
        """,
    )


def search(query: str, results: list[PracticeRecord], searched: bool) -> str:
    if not searched:
        found = '<div class="q1">Enter a patient ID, claim number or surname.</div>'
    elif not results:
        found = f'<div class="q2">No charts matched &quot;{escape(query)}&quot;.</div>'
    else:
        found = "".join(
            f'<div class="n2"><a href="/chart.do?cid={escape(record.claim_id)}">'
            f"{escape(record.patient_name)}</a>"
            f'<div class="n3">{escape(record.patient_id)} &middot; '
            f"claim {escape(record.claim_id)} &middot; "
            f"DOS {_dmy(record.date_of_service)}</div></div>"
            for record in results
        )

    return _page(
        "Patient Search",
        f"""
        <div class="g1"><div class="g2">Find a Chart</div>
        <form method="get" action="/search.do">
        <div class="p1">
          <input class="s2" type="text" name="q" size="28" value="{escape(query)}">
          <input class="s1" type="submit" value="Search">
        </div></form></div>
        <div class="g1"><div class="g2">Results</div>{found}</div>
        """,
    )


def _authorization_block(record: PracticeRecord) -> str:
    """The record the `CO-197` denial claims does not exist.

    The validity range is printed as two dates a person can read and compare
    against the date of service above it, because that comparison is the entire
    reasoning step the agent is here to perform.
    """
    # Status is constant because an Authorization on file is one the payer
    # granted; a refused request never becomes a record to find. It was briefly
    # a fixture field that nothing read, which meant a fixture could have said
    # DENIED while the screen said APPROVED.
    authorization = record.authorization
    if authorization is None:
        return (
            '<div class="g1"><div class="g2">Prior Authorization</div>'
            '<div class="q1">No authorization on file for this episode.</div></div>'
        )

    codes = ", ".join(escape(code) for code in authorization.covered_procedure_codes)
    return f"""
        <div class="g1"><div class="g2">Prior Authorization</div>
        <div class="p1"><dl>
          <dt>Authorization No.</dt><dd>{escape(authorization.authorization_number)}</dd>
          <dt>Status</dt><dd>APPROVED</dd>
          <dt>Valid From</dt><dd>{_dmy(authorization.valid_from)}</dd>
          <dt>Valid Through</dt><dd>{_dmy(authorization.valid_to)}</dd>
          <dt>Covered HCPCS</dt><dd>{codes}</dd>
        </dl></div></div>
        """


def chart(record: PracticeRecord, notes: list[str], saved: bool = False) -> str:
    confirmation = '<div class="q1">Note saved to the chart.</div>' if saved else ""
    written = (
        "".join(f'<div class="n2">{escape(note)}</div>' for note in notes)
        or '<div class="q1">No notes on this chart.</div>'
    )

    return _page(
        f"Chart - {record.patient_name}",
        f"""
        <div class="g1"><div class="g2">Patient</div>
        <div class="p1"><dl>
          <dt>Name</dt><dd>{escape(record.patient_name)}</dd>
          <dt>Patient ID</dt><dd>{escape(record.patient_id)}</dd>
          <dt>Date of Service</dt><dd>{_dmy(record.date_of_service)}</dd>
          <dt>Claim No.</dt><dd>{escape(record.claim_id)}</dd>
          <dt>Ordering Provider</dt><dd>{escape(record.ordering_provider)}</dd>
        </dl></div></div>
        {_authorization_block(record)}
        <div class="g1"><div class="g2">Chart Notes</div>
        {confirmation}{written}
        <form method="post" action="/note.do">
        <div class="p1">
          <input type="hidden" name="noteForm.claimNo" value="{escape(record.claim_id)}">
          <textarea class="s2" name="noteForm.noteText" rows="3" cols="58"></textarea>
          <div><input class="s1" type="submit" value="Save Note"></div>
        </div></form></div>
        """,
    )
