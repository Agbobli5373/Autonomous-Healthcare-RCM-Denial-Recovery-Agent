# Solari platform capabilities — Browser, Sandbox, Desktop

Research for issue #2. Investigated 2026-09-01 against primary sources only:
Solari's own docs, its npm/PyPI package metadata, and the `solari-cookbook`
source on GitHub.

Every claim below carries a source URL. Claims are tagged:

- **[DOC]** — stated in primary documentation or verifiable registry metadata.
- **[CODE]** — read directly out of runnable cookbook source.
- **[INFER]** — reasoned from the above, not stated outright.
- **[NOT FOUND]** — searched for, not documented.

---

## Bottom line

**Does the PRD's architecture stand as written? Partly.**

Solari is real, current, and materially better documented than the ticket's
framing feared. All three primitives exist, both Python and TypeScript SDKs are
published, and the `solari-cookbook` repo is genuine. The PRD's core bet — drive
a browser, process files in a sandbox, operate a GUI app on a desktop — is
supported.

Four things must change:

1. **The `Browser → Sandbox → Desktop` file handoff is not a platform feature.**
   Browser lives on a separate gateway and a separate SDK package from
   Sandbox/Desktop; there is no endpoint that moves a file between them. Bytes
   must transit the orchestrator process. Sandbox ↔ Desktop *can* share a
   volume; Browser cannot. Rewrite the data-flow section as an explicit
   orchestrator-mediated hop.
2. **The Free tier allows 1 concurrent sandbox, and VMs/Desktops appear to
   share that counter.** A workflow holding a Sandbox and a Desktop open at the
   same time will not run on Free. Either sequence the primitives (kill one
   before creating the next) or budget $20 for Starter.
3. **Session recording does not produce a video.** It produces gzipped NDJSON
   rrweb events plus an expiring replay URL. The 45–90s demo video (issue #6)
   cannot be exported from Solari; it must be screen-captured locally.
4. **Python has no umbrella client.** TypeScript's `SolariClient` bundles
   sandbox + desktop but *not* browser; Python ships three separate packages
   that each need an explicit `base_url`. This is a real cost to issue #9's
   orchestrator-language decision.

Nothing in the PRD requires a capability that does not exist. The gaps are
integration seams the PRD assumed were free and are not.

---

## 1. Does Solari exist?

**Yes — confirmed, and it is a Pinetree Research product.** [DOC]

| Asset | URL | Evidence |
| --- | --- | --- |
| Marketing site | https://www.getsolari.com/ | Live, three products described |
| Documentation | https://docs.getsolari.com/ | ~20 pages, full nav tree |
| API reference | https://docs.getsolari.com/api-reference | Base URL `https://api.getsolari.com` |
| Console | https://console.getsolari.com | Linked from docs nav |
| Cookbook | https://github.com/solari-sdk/solari-cookbook | Real, MIT, 9 examples |

The cookbook repo metadata (via GitHub API) shows it was created **2026-08-18**,
last pushed **2026-08-18**, with **98 stars and 245 forks** under org
`solari-sdk`, licence MIT.

**A note the PRD should absorb:** every published package is maintained by
**`pinetreeresearch` (hello@pinetree-research.com)** — verifiable on
[PyPI](https://pypi.org/project/solari-sandbox/) and the npm registry. Pinetree
Research is described in third-party company data as a Palo Alto developer of
autonomous computer-use agents founded in 2026
([Tracxn](https://tracxn.com/d/companies/pinetree-research/__b06FNuHdgO73hM2IfxVtG-MFX0kF8cyZRpzvSQDiu6s)).
Issue #1 states this build is "submitted to Pinetree Research." **Solari is the
evaluator's own platform**, and the fork-to-star ratio (245:98) is consistent
with a take-home exercise seeded from the cookbook. That validates issue #1's
open question about "fork of `solari-cookbook` vs standalone repo" — forking is
plainly the intended path.

### The `@harrychow_` handle — NOT VERIFIED

**[NOT FOUND]** I could not confirm any association between the handle
`@harrychow_` and Solari or Pinetree Research. Searched for
`"harrychow" Solari getsolari founder Pinetree Research`; results returned
Pinetree Research company data and an unrelated LinkedIn profile (James Sng),
but nothing tying that handle to the product. Treat the attribution as
unverified. It has no bearing on the technical findings.

### Similarly-named products — do not confuse

- **Solari Capital** — a venture investor ([PitchBook](https://pitchbook.com/profiles/investor/599622-13)). Unrelated.
- **Solari.com / Catherine Austin Fitts' Solari Report** — financial commentary. Unrelated.
- **Solari (Udine)** — Italian maker of split-flap departure boards. Unrelated.
- **Pinetree Health** on Wellfound is a *different* entity from Pinetree Research.

---

## 2. SDKs and languages

**Both Python and TypeScript exist and are published.** [DOC]

Per https://docs.getsolari.com/languages, five bindings ship, at two support
levels:

| Language | Install | Stated support |
| --- | --- | --- |
| TypeScript | `npm install @solarisdk/sandbox` | "Full: computer-use, PTY, viewer, snapshots" |
| Python | `pip install solari-sandbox` | "Full: computer-use, PTY, viewer, snapshots" |
| Go | `go get github.com/solari-sdk/solari-sandbox-go` | "Core: commands, files, code, git" |
| Rust | `solari-sandbox = "0.1"` | "Core: commands, files, code, git" |
| C++ | CMake, `solari::` | "Core: commands, files, code, git" |

The docs state "TypeScript and Python are at full parity," with the other three
shipping only "the **core surface**."

### Registry reality check [DOC]

| Package | Registry | Latest | First → latest publish |
| --- | --- | --- | --- |
| `@solarisdk/browser` | npm | 0.1.2 | 2026-07-08 → 2026-09-01 |
| `@solarisdk/sandbox` | npm | 0.1.2 | 2026-07-08 → 2026-07-20 |
| `@solarisdk/sdk` (umbrella) | npm | 0.1.2 | 2026-07-08 → 2026-07-20 |
| `solari-sandbox` | PyPI | 0.2.0 | 2026-07-27 |
| `solari-desktop` | PyPI | 0.2.0 | 2026-07-27 |
| `solari-browser` | PyPI | ≥0.1.2 (pinned in cookbook) | — |

All are `0.x`. `@solarisdk/browser` was republished **2026-09-01** — the day of
this research — so the surface is actively moving. **Pin exact versions.**

### The parity claim is softer than it reads — MISMATCH RISK

Three concrete asymmetries, all from primary sources:

1. **TypeScript has an umbrella client; Python does not.** `@solarisdk/sdk`
   describes itself as "one unified client (`SolariClient`) plus the `solari`
   CLI," re-exporting `@solarisdk/desktop`, `@solarisdk/sandbox`, and
   `@solarisdk/core`. Python has no equivalent — the cookbook imports
   `solari_browser.Solari`, `solari_sandbox.SandboxClient`, and
   `solari_desktop.DesktopClient` as three separate clients. [CODE]

2. **The umbrella does not include Browser even in TypeScript.** `@solarisdk/sdk`
   bundles desktop + sandbox + core only. Browser is always a separate package.
   This is the first hint of the gateway split (see §8). [DOC]

3. **Python must pass `base_url` explicitly.** From the cookbook, verbatim:

   > `# The standalone SandboxClient requires base_url (only the umbrella`
   > `# SolariClient in @solarisdk/sdk defaults it).`

   Source: [`sandbox-code-interpreter-py/main.py`](https://github.com/solari-sdk/solari-cookbook/blob/main/examples/sandbox-code-interpreter-py/main.py) [CODE]

Additionally, https://docs.getsolari.com/quickstart shows **TypeScript only** —
no Python quickstart. Python coverage lives in the cookbook, not the docs.

**Cookbook language split** (https://github.com/solari-sdk/solari-cookbook):
5 TypeScript, 4 Python. Python covers all three primitives (browser quickstart,
session recording, code interpreter, desktop computer-use), so **Python is a
viable orchestrator language** — input for issue #9 — but you will assemble
three clients yourself and lean on the cookbook over the docs.

---

## 3. Auth model

- **Single key across all three products.** The cookbook README states one
  `SOLARI_API_KEY` works across browser, sandbox and desktop; getsolari.com
  echoes this ("One API key works across browsers, sandboxes, and desktops,
  and every product bills to the same balance"). [DOC]
- **Format:** `slr_live_<id>_<secret>`, sent as an HTTP `Bearer` token
  (https://docs.getsolari.com/api-reference). Env var `SOLARI_API_KEY`
  (https://docs.getsolari.com/quickstart). [DOC]
- **Exception:** sandbox `/files/download` and `/files/upload` authenticate with
  "the signed token in the query string" rather than the bearer header
  (https://docs.getsolari.com/api-reference). [DOC]
- **No scopes.** [NOT FOUND] Nothing in the docs describes scoped, read-only, or
  per-product keys. The quickstart instead warns, verbatim:

  > "Anyone with your key can run sessions and read every profile in your
  > account. If it leaks, rotate it from the console."

  https://docs.getsolari.com/profiles repeats this: "A profile holds a real
  login. Anyone with your API key can attach it to a session and act as that
  account," and advises "separate keys per environment."

**Implication for this build:** the key is all-or-nothing. Since profiles store
real logins and the key can read them all, the demo's `.env` handling and the
"no real PHI" constraint from issue #1 both point the same way — synthetic
credentials only, key never committed.

---

## 4. Cloud Browser

Driven through **the Playwright API**, which is the single most useful fact here.
https://docs.getsolari.com/browser-api states: "The browser object returned by
`client.launch()` exposes the same surface as the Playwright page API." Also
exposed: `wsEndpoint` (Playwright/Patchright) and `cdpEndpoint` (Puppeteer,
browser-use, other CDP clients). [DOC]

### Persistent profiles across runs — YES [DOC]

https://docs.getsolari.com/profiles. Profiles save "your login, your cookies and
site data, so you don't have to sign in again," in Playwright's `storageState`
format (cookies + localStorage across origins).

```js
const profile = await client.profiles.create({ name: "amazon-seller" })
await client.profiles.save(profile.id, storageState)
const session = await client.sessions.create({ profileId: "prof_abc123" })
```

Three creation paths: programmatic, interactive login via the console's
"Open editor," or uploading an existing `storage-state.json`. Free tier caps
profiles at **3** (https://docs.getsolari.com/pricing).

**Useful for the demo:** log into the payer portal once by hand in the console,
save the profile, and the agent starts every run already authenticated — no
credential handling in the automation path at all.

### Session recording and replay URL — YES, but it is not a video [DOC][CODE]

https://docs.getsolari.com/recording:

- Enable at creation: `client.launch({ recording: true })`.
- Replay URL: `await client.sessions.getReplayUrl(sessionId)` → object with
  `url` and `expiresInSeconds`.
- Download: `await client.sessions.downloadReplay(sessionId)`.
- Format: **NDJSON**, "a line-by-line log of everything that happened on the
  page."

The cookbook confirms these are **rrweb** events and documents two traps
verbatim ([`browser-session-recording-py/main.py`](https://github.com/solari-sdk/solari-cookbook/blob/main/examples/browser-session-recording-py/main.py)):

> "The upload happens asynchronously AFTER the session is released, so the
> first poll usually 404s even on a perfectly good recording. Retry before
> concluding there is no replay."

> "The object is stored gzipped, but the HTTP client honours Content-Encoding
> and hands back decompressed bytes — so this is already plain NDJSON. Don't
> gzip.decompress() it."

The example polls up to 10 times at 3s intervals (~30s) before giving up. The
README adds: "Recording is per session, not per account... without it the replay
endpoint 404s forever." Retention period: [NOT FOUND]. The docs warn recordings
capture input values including passwords and payment data.

> **MISMATCH — issue #6 (demo video).** A replay is an rrweb event log requiring
> an rrweb player, not an MP4. And it covers the **Browser only** — Sandbox has
> no recording, and the Desktop's `streamUrl` is a *live* VNC stream, not a
> recording. A 45–90s video spanning all three primitives must be captured
> locally with screen-recording software. Budget for that.

### Proxies — YES [DOC]

https://docs.getsolari.com/proxies, plus a `proxy-countries` endpoint in the API
reference and a `browser-stealth-proxy-ts` cookbook example showing "stealth
mode + residential proxy egress." Billed at **$1.00/GB (Starter) down to
$0.10/GB (Professional+)** (https://docs.getsolari.com/pricing).

### Stealth — claimed, unquantified, and out of scope here [DOC]

https://docs.getsolari.com/stealth claims stealth makes the browser "look like
an ordinary person's," helps with "sites that block bots," and names
**Cloudflare, DataDome, Akamai, PerimeterX** as defences it addresses. There are
**no stated success rates, guarantees, or limitation caveats** — notable by its
absence. Captcha solving is a separate paid feature
(https://docs.getsolari.com/captcha) at $0.005–$0.01/solve.

> **Note, not a mismatch.** Issue #1's standing constraints already rule out
> "CAPTCHA solving and no bot-detection evasion... regardless of how the portal
> decision lands." Solari offers both; this project must leave `stealth` and
> `captcha` switched off. That constraint is *stronger* than the platform's
> defaults, so it needs to be an explicit, reviewable choice in the code — and
> it pushes issue #8 firmly toward a mock portal.

---

## 5. Sandbox

### Stateful Python kernel — YES, genuinely, with a caveat [CODE]

This was the ticket's sharpest question and the cookbook answers it directly.
From [`sandbox-code-interpreter-py/main.py`](https://github.com/solari-sdk/solari-cookbook/blob/main/examples/sandbox-code-interpreter-py/main.py), verbatim:

```python
# A context is the kernel. Reuse the id to keep state across calls;
# omit it and each call starts fresh.
ctx = await sandbox.create_code_context("python")

await sandbox.run_code("import math\nradius = 7", context_id=ctx)

# `radius` and `math` are still defined here — different call,
# same kernel.
result = await sandbox.run_code(
    "area = math.pi * radius ** 2\nprint(f'area = {area:.2f}')\narea",
    context_id=ctx,
)
```

**The caveat matters:** state persists *only* if you thread `context_id`
through every call. Omit it and each call starts fresh. https://docs.getsolari.com/sandboxes
confirms "variables and imports you set stick around."

Result shape, verbatim from the same file:

> "There is no top-level `.stdout`. Output arrives as a list of items: type
> `"stdout"`/`"stderr"` for streams, `"result"` for the value of the final
> expression (plus png/svg/html for rich media)."

So: `result.error` for failures, `result.results` list otherwise, each item
carrying `.type` and `.text`. Matplotlib figures return natively as rich media.

### API surface [DOC][CODE]

From https://docs.getsolari.com/sandboxes and the cookbook:
`commands.run()` / `.start()`, `pty.create()`, `runCode()` / `run_code()`,
`git.clone|status|commit|push|pull()`,
`files.write|readText|list|search|watch()`, `previewUrl()`, `snapshot()`,
`setTimeout()`, `pause()`, `kill()`.

### Preinstalled packages — pdfplumber and OCR [DOC][INFER]

**[NOT FOUND]** for the `base` template — the docs do not enumerate what ships
preinstalled. But the *install* path is documented and, helpfully, the docs'
own example is nearly this project's use case. From
https://docs.getsolari.com/templates, verbatim:

```js
const image = Image.base("ubuntu:22.04")
  .kind("sandbox")
  .aptInstall(["ffmpeg", "poppler-utils"])
  .pipInstall(["pandas", "pdfplumber"])
  .runCommands("mkdir -p /work")
  .env({ HF_HOME: "/work/.hf" })
  .workdir("/work")

const tpl = await templates.build(image, { name: "media-tools" })
```

Steps run "apt → pip → run → env → workdir."

- **pdfplumber: documented as installable** — it is literally the doc's example. [DOC]
- **poppler-utils** (`pdftotext`, `pdftoppm`) likewise. [DOC]
- **OCR (tesseract): [INFER]** — not named anywhere in the docs, but
  `aptInstall(["tesseract-ocr"])` plus `pipInstall(["pytesseract"])` follows the
  documented mechanism exactly. Unverified until run.

**Recommendation:** build one custom template with the PDF/OCR stack baked in
rather than `pip install`-ing at runtime. It removes a per-run failure mode and
cuts cold-start work — which matters against the 15-minute reviewer budget.

### Filesystem persistence — three tiers [DOC]

1. **Within a live sandbox:** changes persist until `kill()` or idle timeout.
2. **Snapshots** (https://docs.getsolari.com/snapshots): `await sbx.snapshot("after-setup")`
   "saves the exact state of a running machine." Restore via
   `sandboxes.create({ template: "base", fromSnapshot: snapId })`, or
   `revert(snapshotId)` to rewind the same machine in place. "Snapshots work the
   same way for both VMs and sandboxes."
3. **Volumes** (https://docs.getsolari.com/volumes): "A volume is durable storage
   that outlives any single machine." Created with an optional `sizeMb`
   (example: 4096), attached at a chosen mount path. "When the machine goes
   away, the data stays" — persists "until you delete it." Managed via
   `create()`, `list()`, `get()`, `delete()` on both `SandboxClient` and
   `DesktopClient`.

### How files move in and out [DOC][CODE]

`files.write()` / `files.readText()` / `files.list()`, plus "upload/download of
larger blobs" over `/files/upload` and `/files/download`. From
[`sandbox-quickstart-ts/index.ts`](https://github.com/solari-sdk/solari-cookbook/blob/main/examples/sandbox-quickstart-ts/index.ts):

```ts
await sandbox.files.write("/tmp/hello.txt", "written from the SDK\n")
console.log("file  :", (await sandbox.files.readText("/tmp/hello.txt")).trim())
console.log("ls    :", (await sandbox.files.list("/tmp")).map((e) => e.name).join(" "))
```

Two gotchas from the same file, verbatim:

> "`cmd` is NOT shell-interpreted — argv goes in `args`. For pipes, globs or
> redirection, run a shell explicitly: `run("sh", { args: ["-c", "..."] })`."

> "Opens the control channel. Needed for files/git/code; commands alone can
> take a one-shot HTTP path without it." — i.e. **`connect()` is mandatory
> before any file operation.**

---

## 6. Desktop

### What the Linux GUI ships with — DOCS AND COOKBOOK DISAGREE

**[DOC]** https://docs.getsolari.com/templates lists four templates:

| Template | Contents (per docs) |
| --- | --- |
| `base` | "the standard headless sandbox (the sandbox default)" |
| `default` / `workstation` | "the standard Ubuntu desktop" |
| `office` | desktop + "LibreOffice, GIMP, Inkscape, a file manager and PDF viewer" |
| `code` | "desktop + developer tools (git, Python, Node) and VS Code in the browser" |

**[CODE]** But [`desktop-computer-use-py/main.py`](https://github.com/solari-sdk/solari-cookbook/blob/main/examples/desktop-computer-use-py/main.py) says, verbatim:

> "The `default` template ships mousepad, thunar, Chrome, VS Code and
> LibreOffice — `open()` fails if the binary isn't in the image, so check with
> `exec("command", args=["-v", name])` if unsure."

> **CONTRADICTION.** The docs imply LibreOffice is the `office` template's
> differentiator and VS Code is `code`'s; the cookbook says `default` already
> has both, plus Chrome, mousepad (editor) and thunar (file manager) — i.e. an
> XFCE-flavoured image. **Do not trust either list.** Probe at runtime with
> `exec("command", args=["-v", <binary>])`, exactly as the cookbook advises.
> This directly affects issue #11 (which application the Desktop operates) and
> issue #4 (which open-source PM/EMR app can run in the GUI).

### VNC visibility — YES [DOC][CODE]

`streamUrl` "is ready when you create the VM" (https://docs.getsolari.com/desktops)
and is available on the object immediately — the cookbook prints it right after
`create()`. The console renders it in an in-browser "View" tab. The health check
returns `{ ready, display, vnc }`, confirming VNC underneath. The API reference
lists an "RFB stream channel" (RFB is the VNC wire protocol).

**Billing note:** the live screen is not free — "VMs add $0.02 / hour for the
live screen" (https://docs.getsolari.com/pricing).

### Input primitives — all present [CODE][DOC]

From the cookbook example and https://docs.getsolari.com/desktops:

```python
desktop = await client.create(template="default", resolution="1280x720",
                              timeout_ms=10 * 60_000)
await desktop.connect()
health = await desktop.health()          # poll .ready before driving the GUI
pid = await desktop.open("mousepad")
await desktop.mouse.click(320, 300, humanize=True)
await desktop.keyboard.type("hello from a Solari desktop")
shot = await desktop.screenshot(format="png")   # bytes, png or jpeg
```

Also documented: `mouse.move/drag/scroll` (with `humanize` for human-like
paths), `keyboard.press(["ctrl", "s"])`, `fs.write/readText/list`,
`clipboard.set/get`, `exec()` / `execStream()`.

**Three operational traps, verbatim from the cookbook** — all directly relevant
to issue #12 (vision vs selectors):

> "Wait for X11 to be up before driving the GUI." (the example polls
> `health().ready` up to 30 times, 1s apart)

> "Click INSIDE the editor's text area before typing. Mousepad opens in the
> top-left quadrant, so screen-centre (640, 360) is already past its right edge
> — clicking there focuses whatever is behind it and your keystrokes go to the
> wrong window, **silently**. Nothing errors; you just get an empty document.
> Always confirm with a screenshot rather than trusting that a click landed."

> "`close()` drops only the local channel; `destroy()` ends the session."

That middle one is the single most important line in the cookbook for this
build: **desktop clicks fail silently.** Every GUI step needs a screenshot
assertion after it, which is an argument for vision-based verification in
issue #12 regardless of how targeting is done.

### Installing an arbitrary application — three routes [DOC][CODE]

1. **Runtime:** `await desktop.execStream("apt-get", { args: ["install", "-y", "jq"] })`
   — the docs' own example, so apt works. (https://docs.getsolari.com/desktops)
2. **Custom template:** `Image.base(...).kind("desktop").aptInstall([...])` then
   `templates.build()`. (https://docs.getsolari.com/templates)
3. **Snapshot:** install once by hand, `snapshot("app-installed")`, then
   `create({ fromSnapshot })`. (https://docs.getsolari.com/snapshots)

**Recommendation for issue #4:** route 2 or 3. Installing a practice-management
app via apt on every run will blow the reviewer's 15-minute budget and adds a
network-dependent failure mode to the demo's critical path.

---

## 7. Limits that bite a one-week demo

All figures from https://docs.getsolari.com/pricing unless noted.

| | Free | Starter | Professional |
| --- | --- | --- | --- |
| Monthly fee | $0 | $20 | $200 |
| Credits | $3 | $20 | $200 |
| Max session time | **1 hour** | 5 hours | 24 hours |
| Concurrent browsers | 3 | 20 | 150 |
| **Concurrent sandboxes** | **1** | 2 | 10 |
| Profiles | 3 | — | — |
| Browser | $0.15/hr | $0.10/hr | $0.07/hr |
| Sandbox/VM | $0.0525/vCPU-hr | $0.035 | $0.0245 |
| 1 vCPU / 2 GB sandbox | $0.086/hr | — | $0.040/hr |
| Captcha | — | $0.01/solve | $0.005 |
| Proxies | — | $1.00/GB | $0.10/GB |
| VM live screen | +$0.02/hr | +$0.02/hr | +$0.02/hr |

Credits "don't roll over and stop launching new resources when depleted."
Whether a card is required for Free: [NOT FOUND].

### The concurrency limit is the real blocker — MISMATCH

The pricing table says **"Concurrent: 1 sandbox"** on Free, with **no separate
column for VMs**. Since Desktops and Sandboxes are the same microVM engine
(getsolari.com: "Sandboxes are the same engine headless"), and the API reference
groups them as "Sandbox API — VM operations plus files, volumes, snapshots,
templates," the limit **almost certainly covers both**. [DOC for the number,
INFER for VMs sharing it]

> **MISMATCH — PRD architecture.** A workflow that holds a Sandbox open (parsing
> a denial PDF) *while* a Desktop is open (pulling records from the PM app)
> needs 2 concurrent VMs. **That will not run on Free.** Two options: (a)
> strictly sequence — `kill()` the sandbox, persist to a volume, then create the
> desktop; or (b) spend $20 on Starter for 2 concurrent. Option (a) is also
> better demo hygiene, but it forces the volume handoff described in §8.
>
> **Verify this by experiment in issue #7** — it is the single highest-value
> thing that ticket can establish.

### Cost runway

$3/month on Free buys roughly **20 browser-hours**, or **~35 hours** of a
1 vCPU/2 GB sandbox, or **~24 hours** of a 2 vCPU desktop with live screen
(≈$0.125/hr). For a one-week demo this is adequate *if* machines are killed
promptly — but `timeoutMs` is a **rolling idle window, not a hard deadline**
(cookbook README, verbatim: "it resets on every use"). A forgotten VM idles at
cost. **Always `kill()` in a `finally` block**, as every cookbook example does.

### Cold start

Marketing figures from https://www.getsolari.com/: browsers "8ms to spin up"
and 199ms end-to-end; sandboxes "90ms to spin up"; desktops "0.78ms to resume"
from memory snapshot. These are vendor benchmarks — treat as best case. The
cookbook's own, more sober phrasing: a sandbox "boots from a memory snapshot, so
it's usually ready in about a second." [CODE]

### Region — one only, and it is far away [DOC]

https://docs.getsolari.com/regions: **`us-west` (US West, N. California) is the
only region**, and the default. Stated latency: 200–400ms nearby, "+60–80ms each
way" cross-country, "+120–200ms each way" transoceanic.

> **Practical flag.** Driving a GUI over VNC from outside North America means
> every click round-trips ~250–400ms on top of the base figure. For a live demo,
> pre-record or budget generous waits. This is not a blocker but it will make
> the desktop feel sluggish.

---

## 8. Can the three primitives share state? — THE KEY MISMATCH

**Partly. Sandbox ↔ Desktop yes; Browser → anything, no.**

### Sandbox ↔ Desktop: supported [DOC]

https://docs.getsolari.com/volumes: volumes attach to "sandboxes or VMs," and
"the same volume can be attached to many machines at once." `SandboxClient` and
`DesktopClient` both expose volume management. Snapshots likewise "work the same
way for both VMs and sandboxes." Whether concurrent multi-mount is safe for
simultaneous *writes* is [NOT FOUND] — the docs don't state concurrency
semantics. For a sequential Sandbox → Desktop handoff this is irrelevant.

### Browser → Sandbox: NOT supported as a platform feature [DOC]

The API reference is explicit that Browser and Sandbox are **separate gateways**,
and there is **no documented endpoint moving a file between a browser session and
a sandbox**. Corroborating evidence:

- `@solarisdk/sdk` (the "unified" client) bundles **desktop + sandbox + core —
  not browser**. Browser is always a separate package in both languages.
- Browser is configured with `baseUrl`/`wsEndpoint`/`cdpEndpoint`; sandboxes use
  a control WebSocket and signed-token file endpoints.
- Volumes are documented for sandboxes and VMs only — **never for browser
  sessions**.

### What actually works [DOC][INFER]

Browser downloads land **in the orchestrator's memory**, not on any shared disk.
From https://docs.getsolari.com/browser-api, verbatim:

```js
const [download] = await Promise.all([
  page.waitForEvent("download"),
  page.locator("a:has-text('Export CSV')").click(),
])

const stream = await download.createReadStream()
const chunks: Buffer[] = []
for await (const c of stream) chunks.push(c as Buffer)
const bytes = Buffer.concat(chunks)
```

Note also: **the download wait must be armed *before* the click** — a standard
Playwright pattern, but a common source of hangs.

So the real data flow is a three-hop, orchestrator-mediated path:

```
Cloud Browser                    Orchestrator                Sandbox            Desktop
  page.click()                        │                         │                  │
  waitForEvent("download") ──────────►│                         │                  │
  download.createReadStream() ───────►│  bytes in process       │                  │
                                      ├── files.write(path) ───►│                  │
                                      │                    parse PDF               │
                                      │                    write to volume ───────►│
                                      │                         │            fs.readText()
                                      │                         │            drive GUI
```

- **Hop 1 (Browser → Orchestrator):** `download.createReadStream()`. [DOC]
- **Hop 2 (Orchestrator → Sandbox):** `files.write()` or `/files/upload`. [DOC]
- **Hop 3 (Sandbox → Desktop):** shared volume, *or* orchestrator again via
  `files.readText()` then `desktop.fs.write()`. [DOC]

> **MISMATCH — PRD data flow.** The PRD assumes "files move Browser → Sandbox →
> Desktop" as though the platform ferries them. It does not. The orchestrator is
> a mandatory intermediary for anything leaving the browser, and it holds file
> bytes **in memory**. Consequences the PRD must absorb:
>
> - The orchestrator is a stateful component on the critical path, not glue.
>   It needs explicit error handling at each hop — which is exactly the
>   "record partial progress" semantics issue #1 lists as unspecified.
> - Large EOB PDFs are buffered in process memory. Fine at demo scale; worth a
>   noted limitation.
> - **PHI-adjacent bytes transit the orchestrator.** With synthetic data only
>   (issue #1's constraint) this is safe, but the README should say so plainly,
>   because a reviewer will ask.
> - Combined with the Free-tier 1-concurrent-VM limit, the natural shape is
>   **strictly sequential**: browser → kill; sandbox → volume → kill;
>   desktop → kill. Document that as the intended architecture rather than
>   discovering it mid-build.

---

## 9. Mismatch summary

| # | PRD assumption | Reality | Severity |
| --- | --- | --- | --- |
| 1 | Files move Browser → Sandbox → Desktop | Separate gateways; orchestrator must ferry bytes. Only Sandbox↔Desktop share volumes. | **High** — architecture change |
| 2 | Sandbox and Desktop both available | Free tier = **1 concurrent sandbox**, VMs likely share it | **High** — sequence, or pay $20 |
| 3 | Session recording yields a demo video | rrweb NDJSON + expiring URL; browser only; no MP4 | **Medium** — issue #6 |
| 4 | Python/TS at parity | True for features; Python lacks the umbrella client, docs quickstart is TS-only | **Medium** — issue #9 |
| 5 | Desktop ships a known app set | Docs and cookbook contradict each other | **Medium** — probe at runtime; issues #4, #11 |
| 6 | GUI automation is reliable | Clicks fail **silently** off-target | **Medium** — screenshot-assert every step; issue #12 |
| 7 | Fork `solari-cookbook` | Repo real, MIT, 245 forks — intended path | **None** — confirmed |
| 8 | Stateful Python kernel | True, but only with `context_id` threaded through | **Low** — thread it |
| 9 | pdfplumber/OCR available | pdfplumber documented; OCR inferred only | **Low** — bake a template |
| 10 | Latency acceptable | `us-west` only; +120–200ms/way transoceanic | **Low** — pad waits |

---

## 10. What I searched

For transparency, since the ticket asked for it:

- Web search: `Solari cloud browser sandbox desktop AI agents getsolari`;
  `getsolari.ai cloud primitives computer use agents`;
  `"harrychow" Solari getsolari founder Pinetree Research`.
- Fetched and read: getsolari.com; docs.getsolari.com root, `/quickstart`,
  `/languages`, `/pricing` (twice), `/sessions`, `/browser-api`, `/profiles`,
  `/recording`, `/stealth`, `/desktops` (twice), `/sandboxes`, `/templates`,
  `/snapshots`, `/volumes`, `/regions`, `/api-reference`.
- GitHub API: repo metadata and full recursive file tree for
  `solari-sdk/solari-cookbook`.
- Read cookbook source verbatim: `README.md`,
  `sandbox-code-interpreter-py/main.py`, `desktop-computer-use-py/main.py`,
  `sandbox-quickstart-ts/index.ts`, `browser-session-recording-py/main.py`,
  and two `requirements.txt`.
- Registry metadata: PyPI `solari-sandbox`, `solari-desktop`;
  npm registry `@solarisdk/browser`, `@solarisdk/sandbox`, `@solarisdk/sdk`.

**Notes on what I could not confirm:** the `@harrychow_` attribution;
free-tier card requirement; recording retention period; `base` template's
preinstalled package list; tesseract/OCR availability; volume concurrent-write
semantics; snapshot resume latency; whether VMs formally share the sandbox
concurrency counter. `npmjs.com` returned HTTP 403 to direct fetches, so npm
facts come from `registry.npmjs.org` instead. Docs pages were read via an
extraction step rather than raw HTML, so exact wording outside the marked
verbatim quotes may be lightly paraphrased — the cookbook quotes are verbatim
from raw source.

---

## 11. Recommended next actions

1. **Issue #7 (prove one primitive end to end)** should specifically test
   whether a Sandbox and a Desktop can be alive simultaneously on the Free tier.
   That one experiment resolves mismatch #2 and shapes the whole architecture.
2. **Amend the PRD's data-flow section** to show the orchestrator as a
   mandatory, stateful intermediary (§8 diagram).
3. **Build one custom template** with pdfplumber + poppler-utils + OCR baked in;
   snapshot the desktop with the PM app installed. Protects the 15-minute
   reviewer budget.
4. **Decide the demo-video capture method now** (issue #6) — it is local screen
   recording, not a Solari export.
5. **Adopt screenshot-after-every-GUI-action** as a standing rule (issue #12).
6. **Pin exact SDK versions** — `@solarisdk/browser` shipped a release on the
   day of this research.
