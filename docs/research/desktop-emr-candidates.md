# Desktop-GUI EMR / practice-management candidates for the computer-use demo

Research for GitHub issue #4 — "Which open-source practice-management or EMR app can run in a Linux GUI?"

Date: 2026-09-01. Sources are project-primary only (upstream docs, upstream repos, distro package
records, upstream manuals). Every factual claim below carries its source URL.

## Scope and the one discriminator that matters

The demo requires the agent to drive a **native desktop GUI** (X11 window, VNC-visible) — not a
browser. Anything served over HTTP into a browser collapses the demo into "Claude uses a website",
which is the leg we are explicitly not trying to prove. So the first question asked of every
candidate is: does it paint its own toolkit widgets (GTK / Qt / Java Swing / Electron), or does it
render HTML in a browser?

The result is stark. **Almost the entire modern open-source EMR field is web.** Of the eleven
projects named in the ticket, exactly three have a genuine native desktop client, and one of those
three is a Windows Delphi binary.

## Comparison table

| Project | Desktop or Web? | Install effort (headless Linux) | Billing screen? | Licence | Seedable? | Verdict |
|---|---|---|---|---|---|---|
| **Open Hospital** (Informatici Senza Frontiere) | **Native desktop — Java Swing** | **Very low.** One `.tar.gz` (515 MB) with bundled Zulu JRE 17 + MariaDB 10.6; run `./oh.sh -P`. Trivially scriptable into a Dockerfile. **~1–2 h** incl. Xvfb/VNC | **Yes** — Accounting → Bill Manager: new/edit/delete bill, line items, payments, receipts, bill states (pending / paid / closed) | GPL-3.0 | **Yes** — `oh.sh -D` loads `create_all_demo.sql`; or plain SQL into the bundled MariaDB | ✅ **Recommended target** |
| **GNUmed** | **Native desktop — Python + wxPython (wxGTK)** | **Low–moderate.** `apt install postgresql gnumed-server gnumed-client` then `gm-bootstrap_server`. Bootstrap is the fiddly step. **~2–4 h** | **Yes** — `gmBillingWidgets.py`; data model `bill.bill`, `bill.bill_item`, `ref.billable` with invoice ID, close date, VAT, comment | GPL-2.0-or-later | **Yes** — `server/sql/test-data/` exists; schema is plain PostgreSQL so SQL fixtures work. Public demo DB also available | ✅ **Strong runner-up** |
| **GNU Health** (successor to the "Medical" OpenERP/Odoo module) | **Native desktop — GTK client** (`gnuhealth-client`, derived from the Tryton GTK client); web + Android clients also exist | **High.** Server needs PostgreSQL ≥15, Python ≥3.10, Tryton 7.0, Gunicorn, a dedicated OS user, `gnuhealth-control`, then module activation that "will take a while". Docker images exist but add their own debugging. **~1 day** | **Yes** — Accounting package (chart of accounts, invoice handling), Services module generates invoices, Insurance package handles price lists | GPL-3.0-or-later | Yes, but via Tryton ORM/XML rather than raw SQL — the schema is ERP-shaped and unfriendly to hand-written fixtures | ⚠️ Real desktop client, but the server install eats too much of a one-week budget |
| **VistA / WorldVistA + CPRS** | **Native desktop — but Windows Delphi**; on Linux only under WINE | **High/risky.** VistA itself is an M/MUMPS (GT.M) stack; the WorldVistA teaching demo ships as a *Windows* virtual machine. CPRS `.exe` "can be run using WINE emulator in Linux". **Days** | Yes (clinical orders/notes; CPRS is the clinician cockpit), but it is a VA clinical record, not a claims/AR system | Public domain (US federal) / AGPL for OpenVista derivatives | Demo VM ships with "anonymous patient data"; seeding beyond that means MUMPS-level work | ❌ WINE + MUMPS is a multi-day yak shave |
| **OpenEMR** | **Web** — PHP, browser-only, "exclusively a web-based application" | n/a | Yes — strongest claims/billing story of the whole field (electronic billing) | GPL-3.0 | Yes | ❌ Web — disqualified on the premise |
| **OpenMRS** | **Web** — Java `.war` on Tomcat/Jetty, browser UI | n/a | No billing in core | MPL-2.0 with Health Disclaimer | Yes | ❌ Web |
| **OSCAR EMR** | **Web** — Java web app in Apache Tomcat, MySQL | n/a | Yes (Canadian billing) | GPL-2.0 | Yes | ❌ Web |
| **FreeMED** | **Web** — Apache + PHP 8.3 + MySQL | n/a | Practice-management billing claimed; not evidenced in repo README | GPL-2.0-or-later | Yes | ❌ Web |
| **HospitalRun** | **Web** — React/TypeScript + PouchDB. **Repo archived 9 Jan 2023, read-only** | n/a | Not present | MIT | n/a | ❌ Web **and** dead |
| **"Medical" (Odoo module)** | **Web.** The module was renamed and moved off OpenERP to Tryton in April 2011, becoming GNU Health. Odoo's own GTK desktop client stopped at 6.1 and was discontinued at v7 in favour of the web client | n/a | Yes (Odoo accounting) | GPL-3.0 (module) | Yes | ❌ The desktop path here *is* GNU Health; Odoo itself is browser-only |
| **Care2x** | **Web** — PHP. Stagnant: the GitHub repo is a revival of "Care2x 2.7 version from sourceforge", stuck at 2.7-alpha | n/a | HIS billing modules exist | GNU GPL | Yes | ❌ Web and effectively unmaintained |
| **FreeHealth / FreeMedForms** (found, not in ticket) | **Native desktop — C++/Qt5** | Unknown; would need a source build | Not evidenced | GPL (per project pages) | Unknown | ⚠️ Genuinely native, but dormant — no visible recent release activity, 80 open issues, and packaging is stale |
| **Elexis** (found, not in ticket) | **Native desktop — Java, Eclipse RCP** | Moderate (Eclipse RCP product + DB) | **Yes** — accounting and invoicing incl. Swiss TARMED | Eclipse Public License | Unknown | ⚠️ Native and has real billing, but Swiss-specific, German-language, and heavier than Open Hospital |
| **OpenVista CIS** (found, not in ticket) | **Native desktop — C# + Gtk#/GTK on Mono** | High — Mono + VistA server | Clinical, not billing | AGPL | n/a | ❌ Mono-era codebase, last active early 2010s |

## Detailed findings

### 1. Open Hospital — the recommended target

**Type: native desktop.** The upstream repo states it "provides a graphical user interface (GUI)
made with Java Swing" and is "deployed as a desktop application" in standalone or client/server
mode. A React web UI exists but is explicitly marked work-in-progress — the Swing app is the real,
shipped product.
Source: <https://github.com/informatici/openhospital>

**Install effort: the lowest of any candidate.** PORTABLE mode is "a self-contained package that
includes Java, MariaDB/MySQL Server and all the data, without requiring any software installation".
The current release (v1.15.1, 14 Aug 2026) ships `OpenHospital-v1.15.0-linux_x86_64-portable.tar.gz`
at 515.22 MB. You extract it and run `./oh.sh`. Bundled versions for 1.15.0 are Zulu JRE 17.60.17
(64-bit) and MariaDB 10.6.23.
Sources: <https://github.com/informatici/openhospital/releases>,
<https://www.open-hospital.org/download-open-source-emr-medical-record-software/>,
<https://www.open-hospital.org/wp-content/OH_manuals/admin/AdminManual.html>

**Scriptable?** Yes — `curl` the tarball, untar, `./oh.sh -P -l en -D`. The whole thing is one layer
in a Dockerfile plus an X server. Useful `oh.sh` flags (expert mode `-E`): `-P` portable,
`-C` client, `-S` server, `-l <lang>` (ar, de, en, es, fr, it, pt, sq), `-D` initialise with demo
data, `-i` initialise database, `-e`/`-r` export/restore, `-d` debug logging, `-h` help.
Source: <https://www.open-hospital.org/wp-content/OH_manuals/admin/AdminManual.html>

**Billing screen: yes, and it is the right shape.** The user manual documents an Accounting menu
opening a *Patients Bills Management* window via **Bill Manager**. New Bill lets you attach a
patient and add line items drawn from medical services, operations, laboratory exams, or free-text
custom charges; you can add and remove entries, record payments and refunds, print receipts, and
bills move through Draft/Pending → Paid → Closed states. Standard operations are New Bill, Edit
Bill, Delete Bill, Receipt, Report. The manual also notes bills moved to deleted status still appear
in the list but are excluded from reports.
Source: <https://www.open-hospital.org/wp-content/OH_manuals/user/UserManual.html>

That is a genuine list-plus-detail billing worklist with an editable status and editable text — the
exact affordance the demo needs ("find claim X, read its status, update it, leave a note"). The
manual is candid that "the billing process is not linked with other functions of Open Hospital",
which for us is a *feature*: bills are free-standing records we can populate at will.

**Licence: GPL-3.0.** Shipping install instructions, a Dockerfile, and screenshots in a public repo
is entirely fine; we are documenting and orchestrating unmodified upstream software, not
redistributing a modified binary. If we ever vendored a patched build we would need to ship sources
under GPL-3 terms — we will not.
Source: <https://github.com/informatici/openhospital>

**Seeding: first-class.** `oh.sh -D` loads a demo database from `create_all_demo.sql`, described as
loading "a demo database in order to test the software". Beyond that, the bundled MariaDB is a
normal MySQL-protocol server, so synthetic patients and bills can be inserted with plain SQL
fixtures at container build time.
Source: <https://www.open-hospital.org/wp-content/OH_manuals/admin/AdminManual.html>

**Known risks.** (a) Java Swing under Xvfb/VNC works but exposes no accessibility tree by default,
so the agent must drive it purely from screenshots and coordinates — which is exactly what the demo
is meant to prove, but it does mean no DOM-style shortcuts. (b) The demo dataset originates from a
Ugandan hospital deployment, so names and wards will not look like a US payer worklist; seed our own
rows if that matters. (c) The vocabulary is *patient bill*, not *payer claim* — see the credibility
gap below.

### 2. GNUmed — strong runner-up, the purest desktop clinical app

**Type: native desktop.** Upstream describes it as running on GNU/Linux, Windows and macOS; the
Debian package description is "medical practice management - Client … contains the wxpython client",
depending on `python3-wxgtk4.0`. It is Python + wxPython over PostgreSQL.
Sources: <https://www.gnumed.de/documentation/>,
<https://packages.debian.org/sid/misc/gnumed-client>, <https://en.wikipedia.org/wiki/GNUmed>

**Install effort: low-to-moderate, and fully apt-driven.** Client: `apt-get install gnumed-client`,
then run `gnumed`. Server: `apt-get install postgresql postgresql-client gnumed-server` then
`gm-bootstrap_server`. Both packages are current in Debian sid (client 1.8.24+dfsg-3, server
22.34-2); the server package ships the SQL but does not build the database itself, hence the
bootstrap step.
Sources: <https://www.gnumed.de/documentation/GNUmedInstallation.html>,
<https://www.gnumed.de/documentation/GNUmedDatabaseInstallation.html>,
<https://packages.debian.org/sid/gnumed-server>

Two cautions on the bootstrap: upstream warns the procedure "will irrevocably delete any GNUmed
databases pre-existing in the PostgreSQL server", and `gm-bootstrap_server` is historically the step
where installs go wrong. In a throwaway container that warning is harmless.

**Zero-install escape hatch.** Upstream runs a public test database at `publicdb.gnumed.de:5432`
with username `any-doc` / password `any-doc`. `apt install gnumed-client` plus that connection gives
a working GUI in minutes with no server work at all. **Do not use this for the demo** — writes would
land on a third-party public server, and our "synthetic" claim data would be published to strangers.
It is useful only for a first look at the UI.
Source: <https://www.gnumed.de/documentation/GNUmedFAQ.html>

**Billing screen: yes.** The client tree contains `gmBillingWidgets.py` alongside
`gmEncounterWidgets.py`, `gmSOAPWidgets.py`, `gmNarrativeWidgets.py` and
`gmProgressNotesEAWidgets.py`. The business layer documents `cBill` (invoice_id, close_date,
apply_vat, comment, receiver identity/address, currency, total_amount), `cBillItem`
(net_amount_per_unit, unit_count, amount_multiplier, pk_bill, pk_billable, date_to_bill) and
`cBillable` (billable_code, description, raw_amount, vat_multiplier, active), backed by tables
`bill.bill`, `bill.bill_item` and `ref.billable`.
Sources: <https://github.com/ncqgm/gnumed/tree/master/gnumed/gnumed/client/wxpython>,
<https://www.gnumed.de/documentation/api/business/gmBilling.html>

`cBill.comment` plus `close_date` gives us a free-text field and a status-ish field — enough to
stage "read the claim note, append the appeal outcome, close it".

**Licence: GPL-2.0-or-later.** Public setup instructions are fine.
Source: <https://en.wikipedia.org/wiki/GNUmed>

**Seeding: good.** The server SQL tree is organised by schema version and includes a `test-data`
directory plus test-account/sample-data initialisation scripts. Because it is plain PostgreSQL, SQL
fixtures against `bill.bill` / `bill.bill_item` / `ref.billable` are straightforward.
Source: <https://github.com/ncqgm/gnumed/tree/master/gnumed/gnumed/server/sql>

**Known risks.** The user manual is explicitly a stub ("Content is being resurrected from the wiki")
and documents *no* billing section at all, so UI navigation will be discovery-by-clicking. Bills also
require the `ref.billable` catalogue to be populated before a bill can be created — an extra seeding
step. GNUmed's billing is a German private-practice invoice model, with no concept of a payer claim
or denial.
Source: <https://www.gnumed.de/documentation/GNUmedManual.html>

### 3. GNU Health — real GTK client, but the server is a one-week budget's worth of work

`gnuhealth-client` is unambiguously "a GTK client" that "allows to connect to the GNU Health HMIS
component server from the desktop", derived from the Tryton GTK client; current release 5.0.2
(20 Apr 2026), installed with `pip install --upgrade gnuhealth-client`, requiring Python ≥3.10.
Sources: <https://pypi.org/project/gnuhealth-client/>, <https://en.wikipedia.org/wiki/GNU_Health>

Billing is genuinely present: the Accounting package provides chart of accounts, general ledger and
invoice handling; a Services module generates invoices for selected services; an Insurance package
manages price lists. Licence is GPL-3.0-or-later.
Source: <https://en.wikipedia.org/wiki/GNU_Health>

The blocker is the server. The vanilla install requires PostgreSQL ≥15, Python 3.10+, Gunicorn 23,
Tryton 7.0, a dedicated `gnuhealth` OS user, `/opt/gnuhealth` layout, PostgreSQL auth changes,
database user provisioning, `gnuhealth-control`, then instance creation involving "quite a few
tasks" and module activation that "will take a while". Roughly 40 server modules.
Source: <https://docs.gnuhealth.org/his/techguide/installation/vanilla.html>

Docker images exist (official `gnuhealth/his` on Docker Hub plus community compose setups), which
helps, but a Tryton ERP whose accounting must be configured before invoices can exist is not a
one-day job, and seeding goes through the Tryton ORM rather than raw SQL.
Source: <https://hub.docker.com/r/gnuhealth/his>

**Historical note that resolves the ticket's "Medical (the Odoo module)" entry:** GNU Health *is*
that module. It began in 2008 as "Medical" on OpenERP, moved to the Tryton framework in April 2011,
and was renamed GNU Health in June 2011. Separately, Odoo's own GTK desktop client ended at the 6.1
series and was discontinued in favour of the web client from v7 onward. So there is no live
"Medical on Odoo desktop" path — the desktop lineage went to Tryton/GNU Health, and Odoo went
browser-only.
Sources: <https://en.wikipedia.org/wiki/GNU_Health>,
<https://launchpad.net/openobject-client/+series>

### 4. VistA / WorldVistA + CPRS — native, but Windows-native

CPRS is built from Delphi sources (the upstream repo carries `BUILD-Delphi.rst` build instructions),
which makes it a Windows binary. WorldVistA's own demo page lists dependencies as "an MS
Windows based computer" or "the WINE emulator in Linux" for the CPRS session, and the VistA demo
itself ships as a virtual machine containing a Linux/GTM server with anonymous patient data —
requiring a Windows host to run.
Sources: <https://github.com/WorldVistA/VistA/blob/master/BUILD-Delphi.rst>,
<https://worldvista.org/software-download/worldvista-ehr-demos/>

Running CPRS under WINE against a self-hosted GT.M/MUMPS VistA instance is a multi-day project with
a real chance of not working at all, and the payoff is a *clinical* record system, not an AR/claims
one. Rejected on install cost and schedule risk, not on desktop-ness.

### 5. The web pile (fast disposal)

- **OpenEMR** — PHP, "exclusively a web-based application", GPL-3.0, has the field's best electronic
  billing. Ironically the best domain fit and the worst premise fit.
  <https://github.com/openemr/openemr>
- **OpenMRS** — Java, builds `webapp/target/openmrs.war` for Tomcat/Jetty, browser UI, MPL-2.0, no
  billing in core. <https://github.com/openmrs/openmrs-core>
- **OSCAR EMR** — Java web app inside Apache Tomcat with MySQL/MariaDB, JDK 21 + Maven 3 + Tomcat 9,
  GPL-2.0. <https://oscaremr.atlassian.net/wiki/spaces/OS/pages/424312833>
- **FreeMED** — Apache + PHP 8.3 + MySQL, browser-accessed, GPL-2.0-or-later.
  <https://github.com/freemed/freemed>
- **HospitalRun** — React + TypeScript + PouchDB, MIT, and the frontend repo was
  "archived by the owner on Jan 9, 2023. It is now read-only."
  <https://github.com/HospitalRun/hospitalrun-frontend>
- **Care2x** — PHP web app; the GitHub repo is a revival of the SourceForge 2.7 tree that has not
  moved meaningfully since 2015. <https://github.com/care2x/care2x>

### 6. Also-found native desktop projects (not in the ticket)

- **FreeHealth / FreeMedForms** — genuinely native, "coded in C++ / Qt5", desktop builds for
  Debian/Ubuntu, macOS and Windows. But the repo shows no recent release activity and 80 open
  issues, and the packaged builds target long-obsolete OS versions. Dormant.
  <https://github.com/FreeHealth/freehealth>, <https://sourceforge.net/projects/freehealth/>
- **Elexis** — an Eclipse RCP (Java) desktop program covering EMR, lab, "accounting, billing (swiss
  TARMED-System)", under the Eclipse Public License. Native and billing-capable, but Swiss- and
  German-language-specific and heavier to stand up than Open Hospital.
  <https://sourceforge.net/projects/elexis/>, <https://github.com/elexis/elexis-3-core>
- **OpenVista CIS** — "a cross platform application based on C# and Gtk#/GTK that runs on the MS and
  Mono .NET frameworks", AGPL, fronting a VistA server. Mono-era, last active early 2010s.
  <https://sourceforge.net/projects/openvista/>

## The credibility gap nobody in this field closes

Worth stating plainly before the recommendation: **no open-source desktop EMR models US payer claims
or denials.** None of them have a claim status field, a CARC/RARC denial reason code, a payer, an
835 remittance, or an appeal workflow. What they have is:

- Open Hospital: a *patient bill* with line items and a pending/paid/closed status
- GNUmed: an *invoice* with an invoice ID, a comment, and a close date
- GNU Health: a Tryton *customer invoice*
- OpenEMR: real claims and EDI 837 — and it is a web app

So whichever real app we pick, the on-screen vocabulary will read "bill", not "denied claim". The
agent's denial reasoning lives in our own logic; the desktop app is the system-of-record it has to
manipulate without an API. That trade is acceptable and should be stated openly in the demo
narration rather than papered over.

## Recommendation

**Primary: Open Hospital 1.15.x in PORTABLE mode.**

It is the only candidate that is simultaneously (a) a true native desktop GUI, (b) installable in
about an hour on a headless box with a single tarball and one script, (c) equipped with a real
list-and-detail billing screen with an editable status, (d) permissively documented under GPL-3.0 so
our setup instructions can be public, and (e) seedable both by an official demo-data flag and by raw
SQL. Nothing else scores on all five. Concretely:

```
# in the container / VM image
curl -LO <OpenHospital-v1.15.x-linux_x86_64-portable.tar.gz>
tar xzf OpenHospital-*.tar.gz
chmod +x oh.sh
./oh.sh -E -P -l en -D      # portable, English, demo data
# then seed our synthetic "claims" as bills via SQL into the bundled MariaDB
```

Run it under Xvfb + a VNC server; the agent drives it purely from screenshots.

**Runner-up: GNUmed**, if Open Hospital's Swing rendering or Ugandan-hospital demo data proves
awkward. `apt install` + `gm-bootstrap_server` is very Dockerfile-friendly, and `bill.bill` /
`bill.bill_item` / `ref.billable` are pleasant to seed. Budget an extra hour or two for the
bootstrap and for populating the billables catalogue, and accept that the UI is undocumented.

**Rejected for this budget:** GNU Health (server too heavy), VistA/CPRS (WINE + MUMPS), and every
web app on the list.

## Fallback: a purpose-built mock desktop app

If Open Hospital's hospital-bill vocabulary is judged to undermine the RCM story — i.e. the demo
script needs literal "DENIED — CO-97", "appeal submitted", "claim #" on screen — then building a
small mock desktop app is a **legitimate and arguably better** answer, not a cop-out. It is also
cheaper than every option above except Open Hospital itself.

**What it must contain to be credible.** The failure mode of a mock is that it looks like a toy
built to be automated. To avoid that, it needs:

1. **A login screen.** Real clinical software gates on credentials; an agent that has to
   authenticate is doing real work.
2. **A worklist grid, not a single record.** 40–200 rows of claims with columns: Claim ID, Patient,
   DOS, Payer, Billed, Paid, Status, Denial Code, Last Worked. Sortable, filterable, paginated —
   pagination in particular forces genuine navigation rather than one screenshot.
3. **Master-detail navigation.** Double-click a row to open a claim detail window with tabs
   (Claim Info / Line Items / Remittance / Notes / History). Multi-window, multi-tab is what makes
   this a *desktop* automation problem.
4. **A modal edit dialog** with a status dropdown (New / Submitted / Denied / Appealed / Paid /
   Written Off), a denial-reason dropdown carrying real CARC codes (CO-97 bundled, CO-45 fee
   schedule, CO-16 missing information, PR-204 non-covered), a free-text note box, and Save/Cancel.
5. **Deliberate friction.** A confirmation dialog on save; a status bar message; a field that
   validates and shows an error; a couple of screens where the target control is below the fold and
   needs scrolling. Real software is mildly hostile and the demo should show the agent coping.
6. **Durable state.** SQLite on disk so an update is visibly still there after a refresh or restart —
   this is what proves the agent actually changed the system of record.
7. **An audit/history tab** appending "who changed what, when" — the artefact a reviewer will look
   for to confirm the write landed.
8. **No API, no CLI, no HTTP.** The point is that the only entry point is the GUI. Do not add a
   convenience back door, or the demo proves nothing.

**Lightest plausible toolkit: Python + Tkinter + SQLite.** `tkinter` is "the standard Python
interface to the Tcl/Tk GUI toolkit" and ships in the standard library (an optional module — on
Debian/Ubuntu it needs `python3-tk`), and `python -m tkinter` verifies the install. `ttk.Treeview`
gives a real sortable data grid, `Toplevel` gives real child windows, and `ttk.Notebook` gives real
tabs — the three widgets the spec above actually needs. `sqlite3` is also stdlib. That means the
entire mock is **one `pip install`-free Python file plus a seed script**, in the region of 500–700
lines, and roughly **half a day to a day** of work. No licensing questions for a public repo.
Source: <https://docs.python.org/3/library/tkinter.html>

**If a more polished look is wanted: PySide6.** Official Qt for Python, `pip install PySide6`,
prebuilt wheels for Linux x86-64/ARM64 on Python 3.10–3.14, available under
LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only. Nicer tables and native-feeling dialogs, at the cost
of a 100 MB+ dependency and slightly more code. Only worth it if the demo video's visual polish is
a scored criterion.
Source: <https://pypi.org/project/PySide6/>

**Decision rule.** Spend the first two hours installing Open Hospital portable and looking at the
Bill Manager under VNC. If the screen reads convincingly as a claims worklist for the demo
narration, ship it and spend the saved days on the agent. If it does not, stop, and build the Tk
mock — one day, fully under our control, with the exact denial vocabulary the story needs.

## Sources

- Open Hospital repo — <https://github.com/informatici/openhospital>
- Open Hospital releases — <https://github.com/informatici/openhospital/releases>
- Open Hospital downloads/sizes — <https://www.open-hospital.org/download-open-source-emr-medical-record-software/>
- Open Hospital User's Guide (Bill Manager) — <https://www.open-hospital.org/wp-content/OH_manuals/user/UserManual.html>
- Open Hospital Administrator's Guide (`oh.sh`, portable, demo data) — <https://www.open-hospital.org/wp-content/OH_manuals/admin/AdminManual.html>
- GNUmed documentation home — <https://www.gnumed.de/documentation/>
- GNUmed client installation — <https://www.gnumed.de/documentation/GNUmedInstallation.html>
- GNUmed database installation — <https://www.gnumed.de/documentation/GNUmedDatabaseInstallation.html>
- GNUmed FAQ (public test DB) — <https://www.gnumed.de/documentation/GNUmedFAQ.html>
- GNUmed user manual (stub) — <https://www.gnumed.de/documentation/GNUmedManual.html>
- GNUmed `gmBilling` API — <https://www.gnumed.de/documentation/api/business/gmBilling.html>
- GNUmed client widgets — <https://github.com/ncqgm/gnumed/tree/master/gnumed/gnumed/client/wxpython>
- GNUmed server SQL / test-data — <https://github.com/ncqgm/gnumed/tree/master/gnumed/gnumed/server/sql>
- Debian `gnumed-client` — <https://packages.debian.org/sid/misc/gnumed-client>
- Debian `gnumed-server` — <https://packages.debian.org/sid/gnumed-server>
- GNUmed overview/licence — <https://en.wikipedia.org/wiki/GNUmed>
- GNU Health vanilla install — <https://docs.gnuhealth.org/his/techguide/installation/vanilla.html>
- GNU Health GTK client — <https://pypi.org/project/gnuhealth-client/>
- GNU Health history/licence/accounting — <https://en.wikipedia.org/wiki/GNU_Health>
- GNU Health HIS Docker image — <https://hub.docker.com/r/gnuhealth/his>
- Odoo GTK client series (ends at 6.1) — <https://launchpad.net/openobject-client/+series>
- WorldVistA EHR demos — <https://worldvista.org/software-download/worldvista-ehr-demos/>
- VistA CPRS Delphi build — <https://github.com/WorldVistA/VistA/blob/master/BUILD-Delphi.rst>
- OpenEMR — <https://github.com/openemr/openemr>
- OpenMRS core — <https://github.com/openmrs/openmrs-core>
- OSCAR EMR 19 installation — <https://oscaremr.atlassian.net/wiki/spaces/OS/pages/424312833>
- FreeMED — <https://github.com/freemed/freemed>
- HospitalRun frontend (archived) — <https://github.com/HospitalRun/hospitalrun-frontend>
- Care2x — <https://github.com/care2x/care2x>
- FreeHealth — <https://github.com/FreeHealth/freehealth>, <https://sourceforge.net/projects/freehealth/>
- Elexis — <https://sourceforge.net/projects/elexis/>, <https://github.com/elexis/elexis-3-core>
- OpenVista — <https://sourceforge.net/projects/openvista/>
- Python `tkinter` — <https://docs.python.org/3/library/tkinter.html>
- PySide6 — <https://pypi.org/project/PySide6/>
