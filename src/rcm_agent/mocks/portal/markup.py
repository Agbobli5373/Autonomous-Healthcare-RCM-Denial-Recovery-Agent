"""The portal's HTML, written the way a 2009 enterprise portal really is.

**There are no automation hooks here, and that is the entire point.** No
`data-testid`, no stable `id`, no ARIA landmarks, no semantic class names.
Layout is nested tables; classes are opaque two-character names that could
change with the next stylesheet.

A mock authored with clean selectors would test the hooks its own author added
and prove nothing about operating software that was never meant to be
automated — which is the problem this project claims to solve. So the agent has
to find things the way a person does: by the text on the screen and its position
relative to other text.

Adding a hook here to make a test easier would quietly void the demo.
"""

from __future__ import annotations

from html import escape

from rcm_agent.mocks.fixtures_data import PortalClaim

_STYLE = """
body{font:12px Verdana,Geneva,sans-serif;background:#eef1f4;margin:0;color:#1b1b1b}
.h1{background:#1f3a5f;color:#fff;padding:10px 14px;font-weight:bold;font-size:14px}
.h2{background:#dce4ec;padding:6px 14px;border-bottom:1px solid #b6c2cf}
.w1{margin:14px;background:#fff;border:1px solid #b6c2cf}
.t1{border-collapse:collapse;width:100%}
.t1 td,.t1 th{border:1px solid #c9d2db;padding:5px 8px;font-size:11px;text-align:left}
.t1 th{background:#e7edf3}
.t2{border-collapse:collapse;width:100%;margin:0}
.t2 td,.t2 th{border:1px solid #dde3e9;padding:3px 6px;font-size:10px}
.b1{background:#1f3a5f;color:#fff;border:0;padding:5px 12px;font-size:11px;cursor:pointer}
.n1{padding:8px 14px;background:#f5f7f9;border-top:1px solid #c9d2db}
.e1{color:#8a1c1c;padding:8px 14px}
"""


def _page(title: str, body: str, payer: str = "CASCADE HEALTH PLAN") -> str:
    return (
        "<!doctype html><html><head><title>"
        f"{escape(title)}</title><style>{_STYLE}</style></head><body>"
        f'<div class="h1">{escape(payer.upper())} &mdash; PROVIDER PORTAL</div>{body}'
        "</body></html>"
    )


def login(message: str = "") -> str:
    warning = f'<div class="e1">{escape(message)}</div>' if message else ""
    return _page(
        "Provider Sign In",
        f"""
        <div class="w1"><div class="h2">Sign in to your provider account</div>
        {warning}
        <form method="post" action="/login">
        <table class="t1"><tr><td>User ID</td><td>
          <input type="text" name="ctl00$phBody$txtUserId" size="24"></td></tr>
        <tr><td>Password</td><td>
          <input type="password" name="ctl00$phBody$txtPwd" size="24"></td></tr>
        <tr><td></td><td>
          <input class="b1" type="submit" value="Sign In"></td></tr>
        </table></form></div>
        """,
    )


def worklist_shell(page: int) -> str:
    """The table arrives by XHR, so the agent must wait on a condition.

    A fixed sleep is the wrong tool and this is where that shows: the spinner is
    real markup that is later replaced, so anything reading the page too early
    sees "Retrieving claims" and no rows at all.
    """
    return _page(
        "Denial Worklist",
        f"""
        <div class="w1"><div class="h2">Denied Claims &mdash; Working Queue</div>
        <div class="n1">Retrieving claims, please wait&hellip;</div>
        <div class="w2"></div></div>
        <script>
        (function(){{
          var host=document.getElementsByClassName('w2')[0];
          var wait=document.getElementsByClassName('n1')[0];
          var x=new XMLHttpRequest();
          x.open('GET','/wl/rows?p={page}',true);
          x.onload=function(){{ wait.parentNode.removeChild(wait);
                               host.innerHTML=x.responseText; }};
          x.send();
        }})();
        </script>
        """,
    )


def worklist_rows(claims: list[PortalClaim], page: int, pages: int) -> str:
    rows = "".join(
        f'<tr><td><a href="/clm/{escape(c.claim_id)}">{escape(c.claim_id)}</a></td>'
        f"<td>{escape(c.patient_id)}</td>"
        f"<td>{c.date_of_service.strftime('%m/%d/%Y')}</td>"
        f"<td>{escape(c.status)}</td>"
        f'<td align="right">{c.denied_total:.2f}</td></tr>'
        for c in claims
    )
    links: list[str] = []
    for number in range(1, pages + 1):
        if number == page:
            links.append(f"<b>{number}</b>")
        else:
            links.append(f'<a href="/wl?p={number}">{number}</a>')

    return (
        '<table class="t1"><tr><th>Claim Number</th><th>Member</th>'
        "<th>Service Date</th><th>Status</th><th>Denied Amt</th></tr>"
        f"{rows}</table>"
        f'<div class="n1">Page {page} of {pages} &nbsp; ' + " &nbsp; ".join(links) + "</div>"
    )


def claim_detail(claim: PortalClaim) -> str:
    """Adjustments per service line, never flattened to one code per claim.

    ADR-0001 puts adjustments at line grain because one claim mixes outcomes, and
    the portal has to show them that way or the agent could not see it.
    """
    blocks: list[str] = []
    for line in claim.service_lines:
        adjustments = "".join(
            f"<tr><td>{escape(a.group)}</td><td>{escape(a.reason_code)}</td>"
            f"<td>{escape(' '.join(a.remark_codes)) or '&nbsp;'}</td>"
            f'<td align="right">{a.amount:.2f}</td></tr>'
            for a in line.adjustments
        )
        blocks.append(
            f"<tr><td>{line.line_number:03d}</td>"
            f"<td>{escape(line.procedure_code)}</td>"
            f'<td align="right">{line.charge:.2f}</td>'
            '<td><table class="t2"><tr><th>Grp</th><th>Reason</th>'
            f"<th>Remark</th><th>Amount</th></tr>{adjustments}</table></td></tr>"
        )

    return _page(
        f"Claim {claim.claim_id}",
        f"""
        <div class="w1"><div class="h2">Claim Detail</div>
        <table class="t1">
          <tr><td>Claim Number</td><td>{escape(claim.claim_id)}</td>
              <td>Member ID</td><td>{escape(claim.patient_id)}</td></tr>
          <tr><td>Service Date</td><td>{claim.date_of_service.strftime("%m/%d/%Y")}</td>
              <td>Status</td><td>{escape(claim.status)}</td></tr>
        </table>
        <div class="h2">Service Lines</div>
        <table class="t1"><tr><th>Ln</th><th>HCPCS</th><th>Billed</th>
          <th>Adjustments</th></tr>
        {"".join(blocks)}
        </table>
        <div class="n1">
          <a href="/doc/{escape(claim.claim_id)}" target="_blank">
            View Explanation of Benefits (PDF)</a>
          &nbsp;&nbsp; <a href="/wl">Back to worklist</a>
        </div></div>
        """,
        payer=claim.claim.payer,
    )
