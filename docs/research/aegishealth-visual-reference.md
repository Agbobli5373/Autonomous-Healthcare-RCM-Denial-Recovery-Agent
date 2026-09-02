# aegishealth.us — what it does visually, and what transfers to a dense console

Research for issue #53 (part of the map in #52). Investigated 2026-09-02 against
the live site: rendered pages, computed styles read out of the DOM, and the
shipped stylesheet (`/_next/static/chunks/0z_7v2owv7j7z.css`).

**Domain correction.** The ticket names `ageishealth.us`. That domain does not
exist — NXDOMAIN from both `8.8.8.8` and `1.1.1.1`. The site meant is
**`aegishealth.us`** ("Aegis" — *AI Denial Management Platform for Healthcare*),
a YC-backed denial-management startup, i.e. a direct commercial analogue of this
project. Everything below is that site. Worth fixing the spelling in #52 so the
next reader does not repeat the dead end.

Claims are tagged:

- **[MEASURED]** — read from computed styles or the stylesheet; reproducible.
- **[SEEN]** — visible in a screenshot in `docs/research/aegishealth/`.
- **[INFER]** — my reading, argue with it.

---

## Bottom line

The useful thing about this reference is **not the marketing page**. It is that
the marketing page contains six embedded product mockups, and *those* are drawn
at genuine console density — 11–14px type, 36px rows, 6px corners, hairline
rules — while the page around them is drawn at 72px. The site is effectively
two design systems stacked, and only the inner one is ours.

**Transfers (the inner system):** monospace reserved for machine identifiers;
the one-line fact bar; status as a 2-character tinted pill; severity as a 4%
row wash *plus* a pill, never wash alone; the left-rule citation block; context
chips; the filled/hollow step rail; the document rail with uppercase category
micro-labels; a single navy primary with everything else greyscale; semantic
colour permitted *only inside data*; 6px / pill radius pair; a real dark palette.

**Does not transfer (the outer system):** 72px/400 display type, 80px section
padding, the 6,242px pinned feature scroll, scroll-triggered reveal animation,
trust-signal furniture (backers, press, FAQ), and — the only genuinely dangerous
one — **Aegis presents model output as "Confidence 94%" and "Win prob. 85%"**.
ADR-0002 forbids exactly that framing here. Copy the pill, not the percentage.

The site also ships **zero `prefers-reduced-motion` rules and zero
`forced-colors`/`prefers-contrast` rules** [MEASURED]. Do not inherit that; #52
lists the accessibility bar as unspecified and this reference will not settle it.

---

## 1. What the site is

**Marketing, with one page that leans product.** Five routes exist: `/`,
`/examples`, `/blog`, `/contact`, `/terms-of-service`. There is no app
subdomain, no `/login`, no `/dashboard`. Both hero CTAs ("Get Started",
"Request Demo") go to `cal.com/aegishealth/aegis-intro` — a booking link, not a
signup.

**`/examples` is as close to a product screen as the public gets** [SEEN
`17-examples.png`, `18-examples-lower.png`]. It presents three fictitious denial
cases behind numbered pill tabs, each with a claim summary, a metadata fact bar,
an 8-document evidence rail with a working document viewer (a real UB-04 form
renders), and a **"Process with Aegis"** button that appears to trigger a live
agent run. I did not press it — it initiates work on a third party's
infrastructure and nothing in the ticket needs the result. The page footnotes
itself: *"Fictitious sample cases for demonstration… only the payer names are
real."*

Everything else is conventional B2B SaaS marketing: hero, backer logos, 3-step
explainer, 5-feature showcase, integration diagram, stat row, press links, FAQ,
footer.

**No content addressed to an AI agent was found.** `robots.txt` is a plain
allow-all with `Disallow: /api/`; there is no `llms.txt` or `.well-known/ai.txt`
(both 404); the only `sr-only` strings are legitimate control labels ("Open main
menu", "Toggle theme", "Scroll left"/"Scroll right"). Nothing to quote.

---

## 2. The visual system

### Type

**The families are not what the code says.** The site loads **Geist Sans**
(variable, 100–900) and declares Geist Mono and an unused `--font-inter`. But
`body` and `h1` both compute to `ui-sans-serif, system-ui` [MEASURED] — the
Tailwind `font-sans` utility overrides the Geist class. What actually renders is
the **OS UI stack**: Segoe UI Variable on Windows, SF Pro on macOS. Geist Mono
reports `unloaded`; the mono runs are `ui-monospace` (Consolas / SF Mono).

That is worth knowing before anyone budgets for a typeface: **none of the
"premium" here is bought.** It is the system font set large, light and tight.

| Role | Size / weight | Tracking | Leading |
|---|---|---|---|
| Hero H1 | 72px / **400** | −4.32px (−0.06em) | 82.8px (1.15) |
| Section H2 | 60px / **400** | −1.5px (−0.025em) | 75px (1.25) |
| Stat numeral | 48px / 500 | −1.2px | 48px (1.0) |
| Card H3 | 20px / 600 | −0.4px | 28px |
| Body | 20px / 400 · 16px / 400 | −0.32 / −0.28px | 28 / 26px |
| Lead paragraph | 18px / 400 | −0.32px | 27px |
| Eyebrow chip | 14px / 400, uppercase | −0.35px | 20px |
| Button label | 14px / 500 | normal | 20px |
| **Mockup card title** | **12px / 600** | −0.3px | 16px |
| **Mockup status badge** | **9px / 600** | normal | 16px |
| Mono — record ID | 14px / 500 | −0.35px | 20px |
| Mono — status stamp | 12px / 500, uppercase | **+0.6px** | 16px |
| Mono — field label | 11px / 500, uppercase | **+0.55px**, 60% alpha | 16.5px |

All [MEASURED]. Two things to take from the table. First, **the display sizes
are set at weight 400, not 600/700** — the size does the work, the weight stays
out of the way. Second, **tracking flips sign with scale**: negative and
increasingly so as type grows (−0.06em at 72px), positive only on the uppercase
mono micro-labels (+0.05em). That single rule is most of the typographic
"feel".

**Monospace is semantic, not decorative.** It appears on exactly three things:
record identifiers (`A7B9C2D4E8F1`), machine status stamps (`READY TO TRANSMIT`),
and field labels inside data displays (`ICN`). Prose is never mono; mono is never
prose.

### Colour roles

Semantic tokens, light theme [MEASURED]:

| Token | Value | What it *means* here |
|---|---|---|
| `--foreground` / `--primary` / `--ring` | `hsl(204 44% 14%)` = **#142733** | Ink. Every heading, every value, every identifier. One text colour. |
| `--muted-foreground` | `hsl(204 8% 46%)` = **#6C777F** | Everything that qualifies rather than states: payer names, descriptions, timestamps, units. |
| `--muted-foreground-subtle` | `hsl(204 16% 30%)` | The half-step for secondary headings. |
| `--button-primary` | `hsl(217 70% 29%)` = **#163E7E** | The one action. Used 5 times on the whole home page. Hover **lightens** to `39% L`, it does not darken. |
| `--secondary` / `--muted` / `--accent` | `hsl(0 0% 96%)` = **#F5F5F5** | Pure neutral, zero hue. Inert surfaces only. |
| `--border` | `hsl(206 47% 58% / .15)` | **Structure is blue, not grey.** Every hairline carries a trace of the brand hue at 15% alpha. |
| `--border-navbar` | `hsl(206 100% 33% / .15)` | Deeper blue — the chrome edge. |
| `--border-hero` / `--border-section` / `--border-footer` | `hsl(198 92.5% 64.2% / .3 → .5)` | Sky cyan at 30–50%: the *section boundary* lines you can see running the full width of every screenshot. |
| `--destructive` | `hsl(0 84.2% 60.2%)` | Declared, never used on a control. |

Inside the product mockups a second, warmer set appears, and it appears **only
attached to data** [SEEN `21-crop-denial-queue.png`, `08-features-05.png`]:

- **emerald** (`#009767`) — a good outcome: overturn rate, win probability, "Enabled".
- **amber / yellow** — caution: the P2 priority band.
- **pink / red** (`#E30076`, `#9F0712`) — money at risk: "Revenue at Risk $2.4M", the P1 band, denial codes.
- **violet → blue gradient** (`#8b5cf6` → `#3b82f6`) — the irreversible action ("Submit Appeal") and the animated "data is flowing" connector beams.
- **blue-600** — the currently-selected thing (active feature row, selected context chip).

The discipline is the point: **the page chrome is monochrome ink-on-white; hue
only ever means something, and only ever inside a data surface.**

Contrast: ink on white ≈ **15.4:1**. Muted `#6C777F` on white ≈ **4.6:1** — it
clears AA for body text by 0.1 and carries most of the running prose. That is a
marketing-site tolerance, not a console-under-fluorescent-light tolerance.

### Spacing rhythm

- Container **1400px** with **24px** gutters; prose columns capped at **600px / 576px** [MEASURED].
- Fixed header **64px**, background white at **95% alpha**, hairline bottom border.
- Section vertical padding **64–80px**; Tailwind's 4px base unit throughout.
- Breakpoints 640 / 768 / 1024 / 1280 / 1536 (untouched Tailwind defaults).
- The home page is **11,816px tall at 1440 wide**. The features section alone is
  **6,242px** — five stacked full-height panes, ~1,250px of scroll per feature,
  each pane repeating the same left-hand tab list with a different mockup beside
  it. Nothing is `position: sticky`; it is five near-identical screens.

### Corners and shadows

Radii, by frequency across the live DOM [MEASURED]:

- **pill / 9999px** — 43 uses. Status badges only.
- **6px** — 39 uses. **Every real control**: buttons, eyebrow chips, inputs, selects, context chips.
- **8px** — 20 uses. Panels inside mockups.
- **12px** — 5 uses. The mockup "window" frame itself.

There is nothing above 12px. No 16/20/24px pillow cards. **Tight corners are
doing a large share of the "instrument, not brochure" impression.**

Two shadows and one glow:

1. `0 1px 3px rgb(0 0 0 / .1), 0 1px 2px -1px rgb(0 0 0 / .1)` — 18 uses. Buttons and small tiles.
2. `0 0 0 1px hsl(navy / .05), 0 4px 20px rgb(0 0 0 / .15)` — 16 uses. **A hairline ring plus a soft 20px lift** — the floating product-mockup card. The ring is what stops it looking like a drop-shadowed 2014 card.
3. An animated **blue-tinted** glow, `rgba(59 130 246 / .15) 0 ~4px ~12px`, values changing frame to frame on the integration tiles. Blue-tinted shadow reads as emission, not weight.

Borders are `1px` and blue-tinted (`rgba(98 155 198 / .15)`); the active feature
row gets `2px` in blue-600. Two widths, one hue family.

### Iconography

**Lucide**, uniformly: `viewBox="0 0 24 24"`, `stroke-width="2"`, rendered at
**16px** (`size-4`) or **12px** (`h-3 w-3`) [MEASURED]. Outline only, no fills,
no duotone, no brand-illustrated icon set. Icons sit inline before headings and
inside chips; they never appear as decorative 48px feature glyphs.

### Imagery

**Every raster image on `/` and `/examples` is a logo or a compliance badge**
[MEASURED — enumerated every `<img>`]: the Aegis mark, five investor logos, six
EHR/payer logos, and the Oneleet "HIPAA Compliant" badge. There is no
photography, no illustration, no 3D render.

What stands in for imagery is **line art of the logo at ~2% contrast** — giant
outlined concentric rings behind the hero, a giant outlined wordmark under the
footer [SEEN `01-hero.png`, `12-faq-footer.png`] — plus **diagonal-hatch grid
blocks** in the page margins and behind each mockup. The hatch is a 6×6 SVG
tile, `fill="#132531" fill-opacity="0.15"`, in a `#C9CCCF` hairline box
[MEASURED]. Read together: an architectural drawing that has left its
construction grid visible.

**The one exception is `/blog`** [SEEN `20-blog.png`], which uses exactly the
teal-graded stock-clinician photography — corridors, scrubs, glowing data
overlays — that the rest of the site refuses. It is instructive: put those
images next to the home page and you can see precisely how much of the premium
came from leaving them out.

### Motion

Seven keyframes ship in total: `accordion-down`/`up`, `enter`/`exit`,
`glow-flow` (3s infinite), `gradient-slide` (2.5s infinite), `logo-spin` (0.5s
on hover), `pulse`, `spin` [MEASURED]. On top of that sits Framer-Motion-style
scroll reveal — inline `opacity`/`transform` on nearly every block, which is why
a naive screenshot of this site comes back blank.

The mockups add one device worth stealing: a **blinking text cursor mid-sentence**
in the appeal-letter window, showing generation in progress [SEEN
`03-how-it-works-steps.png`].

**No `prefers-reduced-motion` block exists.** No `forced-colors` or
`prefers-contrast` block exists. There is exactly one `focus-visible` rule.

### Dark mode and responsive

Dark is a **genuine second palette**, not an inversion [SEEN `13-dark-hero.png`,
`14-dark-features.png`]: background `hsl(240 10% 4%)` (near-black, faintly blue),
surfaces `hsl(240 10% 10%)`, muted text `hsl(240 5% 65%)`, borders keep the same
blue hue at 20% alpha — and the primary button **flips role**, becoming light sky
`hsl(204 100% 78%)` with ink text. The priority row washes become deep red/amber
and stay legible. This is the part of the system most obviously built by someone
who tested both themes.

Mobile (390px) collapses to one column, turns the horizontal integration diagram
vertical, and keeps the "Request Demo" button in the header beside a hamburger
[SEEN `15-mobile-hero.png`, `16-mobile-features.png`].

---

## 3. What actually earns "premium" here

Six devices. Each is falsifiable — remove it and the page visibly cheapens.

1. **The absence of photography.** [MEASURED] Not a single human face, hospital
   corridor or stock stethoscope on the home page. In a category where every
   competitor opens with a smiling clinician, refusing the photograph is the
   loudest possible signal. The blog proves the counterfactual.

2. **Large type at weight 400.** [MEASURED] 72px and 60px headings set at
   *normal* weight with −0.06em / −0.025em tracking. Bold display type reads as
   advertising; light display type at the same size reads as a printed report.
   This is one CSS property and it is doing an enormous amount of work.

3. **Exposed construction.** [SEEN] Diagonal-hatch blocks in the margins,
   cyan section-boundary rules running edge to edge, mockups sitting on visible
   hatched frames, a dot-grid behind the integration diagram. The layout grid is
   presented as ornament. It says "instrument" rather than "brochure", and it is
   free — an inline SVG tile and a 1px border.

4. **Colour rationing.** [MEASURED] The entire home page uses its primary
   navy on **five** elements. Everything else is ink, muted grey, white, and
   hairlines. Hue is then spent all at once, and only inside data: emerald for a
   good outcome, amber for caution, pink for money at risk, violet for the
   irreversible button. Because nothing else is coloured, an emerald `78%` reads
   as information rather than decoration.

5. **Mockups drawn at real density.** [SEEN `21-crop-denial-queue.png`] The
   embedded product screens run 12px card titles, 11px column labels, 9px
   badges, ~36px rows, 4px progress bars, 6px corners. They are not simplified
   "illustrative UI" — they look like software that has to hold real rows. The
   contrast between the 72px page and the 12px card *is* the premium effect:
   confidence that the product can be shown small.

6. **Restraint in the shadow language.** [MEASURED] Two shadows total, both
   subtle; the important one pairs a 5%-alpha hairline **ring** with a soft
   20px lift, so cards read as sitting on the page rather than hovering above
   it. No coloured drop shadows on cards, no glassmorphism, no gradient borders
   except the deliberate blue→violet "flow" beams.

What does **not** earn it: motion (there is barely any of consequence),
photography (none), or novelty layout (it is a standard SaaS scroll).

---

## 4. What does not transfer to the console

The console holds, above the fold: a live 3 × 5 claim/phase matrix, a
Determination with an Action, a 300+ character rationale, a guardrail label, up
to 10 evidence items, a Priority score, a screenshot strip, and an approve/reject
control. Against that payload:

**Wrong by an order of magnitude**

- **72px/400 display type.** Three rows of the matrix cost less vertical space
  than one hero line. The console's largest type should be a claim identifier or
  a dollar figure, around 24–28px. Nothing on the screen should be a headline.
- **80px section padding, 1400px container, 600px prose column.** The rationale
  is the only thing that wants a measure cap; everything else wants full bleed
  and 12–16px gutters.
- **The 6,242px feature scroll.** The console has one fold. Anything an analyst
  must see before approving cannot be below it, and nothing may be revealed by
  scrolling *past* it.

**Wrong in kind**

- **Scroll-triggered reveal.** This is the actively dangerous one. In a live
  console, a row fading in from `opacity: 0` is indistinguishable from a row
  whose state just changed. Entry animation must be reserved for *actual new
  events*, and state change must have its own distinct treatment. Also: no
  `prefers-reduced-motion` support ships here; the console needs it.
- **Trust furniture.** Backer logos, press strip, FAQ accordion, case-study stat
  row, compliance badges. All of it is persuasion aimed at a buyer. The analyst
  is not being sold to; they already opened the tool.
- **Hero line art at 2% contrast.** Charming behind a headline, illegible noise
  behind a data grid.
- **Stock clinical photography** (the `/blog` treatment). Never.
- **9px badge type and 4%-alpha row washes.** These are mockup-scale decisions,
  read at leisure on a marketing page. Floor real badge type at 11px, and never
  let a severity wash be the *only* channel — the site already backs it with a
  pill and a rank label, and the console should keep all three.
- **`rgba(98 155 198 / .15)` hairlines.** Roughly 4% effective contrast on white.
  A page with six elements can afford invisible borders; a 3 × 5 matrix cannot.
  Keep the blue tint, raise the alpha until the gridlines are actually visible.
- **36px buttons at 8/16 padding for the approve control.** Fine for "Get
  Started". The control that files an appeal should not be the same object as
  the control that opens a booking link.

**Wrong for this domain specifically — read this one twice**

Aegis labels a model's output **"Confidence 94%"** in the appeal-generation card
and **"Win prob. 85%"** with a green bar in the denial queue [SEEN
`21-crop-denial-queue.png`, `05-features-02.png`]. ADR-0002 makes guardrails
**rules**, not thresholds, and #52 states plainly that the console "must not
quietly present a guardrail as a confidence score". The visual pattern — a small
tinted stat tile, a thin bar, a percentage — is genuinely good and worth taking
for **Priority**, which *is* a score. It must not be reused for the guardrail,
which is a named rule with a pass/fail and a reason. Take the tile; change the
noun.

---

## 5. Nearest honest comparators

Where the marketing reference runs out, these are the products whose patterns
actually fit. Each is listed with the one thing it contributes; none is being
recommended wholesale. [INFER throughout — these are pattern citations from the
products' public surfaces, not screenshotted here.]

| Product | The pattern it contributes |
|---|---|
| **Linear** | The density baseline. 13–14px UI type, ~32–36px rows, status as a small glyph plus one word rather than a coloured block, and colour reserved almost entirely for state. Also the command palette as the primary way to act, and optimistic state so a decision registers instantly. This is the closest thing to "premium and dense" that exists. |
| **GitHub Actions run view** / **Temporal Web UI** | The literal shape of 3 claims × 5 phases: a matrix of runs × steps, each cell carrying its own state icon and elapsed time, updating live, each cell expandable into the log that produced it. Steal the cell vocabulary (queued / running / passed / failed / skipped) and the elapsed-time-in-cell habit. |
| **Stripe Dashboard — Radar review queue & payment detail** | The canonical "approve or decline against a clock" screen: a score, the list of rules that fired with pass/fail, the evidence considered, and a two-control decision. Note especially that Stripe shows *which rules fired* rather than a single opaque number — which is exactly the ADR-0002 distinction. Its payment timeline is also the right model for a claim's event history. |
| **Sentry issue detail** | How to present long machine-generated text so a human can skim it. A fixed summary header that never scrolls away, the most relevant frame expanded and the rest collapsed, metadata in a rail rather than inline. Directly applicable to a 300+ character rationale plus a 10-item evidence list. |
| **LangSmith / Braintrust human-review queues** | The newest and most on-point: a model's long output shown beside the inputs it used, with per-item accept/reject and a required note. Built for precisely the problem "a model wrote several sentences and a person must judge them". Worth looking at for where the reject reason goes. |
| **Vercel / Netlify deploy logs** | Live-streaming output that does not fight the reader: phase headers, a sticky status chip, autoscroll that yields the moment the user scrolls up. The console's browser-work strip and phase progress have the same problem. |
| **Datadog / Grafana** | Dense monitoring layout without card chrome: hairline separators instead of boxes, tabular numerals so columns align, sparklines inside rows, controls in a fixed header. Contributes the discipline of "a border is cheaper than a card". |
| **GitHub pull-request review** | The approve/request-changes control itself: a deliberate two-step (open the review, state the verdict, submit), the verdict recorded as a first-class object with an author and a comment, and the reviewer's identity attached. The right mental model for "an analyst approved this appeal". |

Two more, further afield but each carries one idea:

- **Superhuman / Gmail triage** — keyboard-first work against a clock, and the
  "advance to next item" affordance immediately after a decision so the operator
  never lands on an empty screen.
- **Trading blotters (Bloomberg and descendants)** — colour applied only to the
  value that changed, never as a row background, and monospaced numerals so a
  column of dollar amounts can be scanned by shape.

---

## Method, and what I did not do

Pages visited: `/`, `/examples`, `/blog`, `/contact`. Design tokens were read
from computed styles in the live DOM and from the shipped stylesheet fetched
directly. Screenshots were captured by driving headless Chrome over the DevTools
Protocol with the scroll-reveal animations neutralised — without that the
captures come back blank, which is itself a finding about the site.

Not done, deliberately: I did not press **"Process with Aegis"** on `/examples`
(it triggers work on a third party's system), did not fill or submit the
`/contact` form, and did not enter any data anywhere. No cookie or consent
banner was presented. No page contained text addressed to an automated agent.

## Screenshot index — `docs/research/aegishealth/`

| File | What it shows |
|---|---|
| `01-hero.png` | Hero: 72px/400 type, ghosted logo line art, hatched margins, both button styles |
| `02-how-it-works.png` | Section head + the horizontal step rail with filled/hollow nodes |
| `03-how-it-works-steps.png` | Claim-card mockup and the document window with a live typing cursor |
| `04-features-01.png` … `08-features-05.png` | The five feature panes and their product mockups (denial queue, appeal generation, submission portal, workflow config, performance metrics) |
| `09-integrations.png` | Orthogonal connector diagram on a dot grid; uppercase letterspaced node labels |
| `10-case-studies.png` | Five-stat row separated by vertical hairlines — no cards, no icons, no colour |
| `11-press.png` | List rows with logo tile, muted source, ink headline, trailing arrow |
| `12-faq-footer.png` | Accordion cards; 4-column footer divided by full-height hairlines; giant outlined wordmark |
| `13-dark-hero.png`, `14-dark-features.png` | The dark palette, including the primary-button role flip |
| `15-mobile-hero.png`, `16-mobile-features.png` | 390px behaviour |
| `17-examples.png` | Numbered pill tabs, bulleted lead-in facts, the fact bar, dual actions |
| `18-examples-lower.png` | Document rail with uppercase category micro-labels + document viewer |
| `19-contact.png` | Form treatment (not submitted) |
| `20-blog.png` | The one page that uses stock clinical photography — the counterfactual |
| `21-crop-denial-queue.png` | 2× crop: row washes, progress bars, P1/P2/P3 pills, column labels |
| `24-crop-examples-meta.png` | 2× crop: the one-line fact bar with middot separators and code chips |
