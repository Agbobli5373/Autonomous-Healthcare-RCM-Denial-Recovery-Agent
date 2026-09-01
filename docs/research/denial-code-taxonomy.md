# Denial-code taxonomy — CARC, RARC, and Claim Adjustment Group Codes

Research for issue #3. Investigated 2026-09-01 against primary sources only:
the X12 External Code Lists, CMS (cms.gov, MLN, Internet-Only Manuals), the
eCFR/Social Security Act, CAQH CORE (the federally-adopted operating-rule
author), HHS OIG, and KFF's analysis of CMS-published Marketplace
transparency data.

Every claim below carries a source URL. Claims are tagged:

- **[DOC]** — stated verbatim in a primary code list, regulation, or agency page.
- **[DATA]** — a published statistic from a government or research primary.
- **[INFER]** — reasoned from the above, not stated outright. Treat as a design
  opinion, not a fact.
- **[NOT FOUND]** — searched for, not retrievable from a public primary source.

> **Scope note.** This is a vocabulary and classification reference for a demo
> built on **synthetic data only**. Nothing here is billing advice, and no code
> mapping below should be used to adjudicate a real claim.

---

## Bottom line

1. **Three code sets, not one.** A denial on an 835 is always a *tuple*:
   `Group Code + CARC (+ one or more RARCs)`. The group code says **who owes the
   money**; the CARC says **why**; the RARC says **which specific thing was
   wrong**. Modelling the CARC alone loses the two facts that most determine
   recoverability.
2. **The lists are free to read; the tooling around them is not.** X12 publishes
   the full CARC, RARC and Group Code lists openly on x12.org — the historic WPC
   paywall does *not* block the code text itself. What costs money is the update
   subscription, and what is genuinely gated is the **AMA CPT** licence you must
   accept to download NCCI edit files. That matters for what the demo may embed.
3. **Rejection ≠ denial, and Medicare has a third state.** A front-end rejection
   (999 / 277CA) never adjudicates, produces no 835, and has **no appeal
   rights**. A denial adjudicates and does. Medicare adds "returned as
   unprocessable" (RARC **MA130**) — it arrives *on an 835* but still carries no
   appeal rights. The domain model needs three states, not two.
4. **Recoverability is rarely readable from the code alone.** X12 itself
   mandates that CARC 16, 96, 234 and 252 *must* be accompanied by a RARC,
   because the CARC is deliberately underspecified. Four of the highest-volume
   denial families (auth, medical necessity, bundling, timely filing) flip
   between recoverable and hopeless on claim context the code does not carry.
5. **The demo should ship 12 codes**, split roughly 7 recoverable / 5 not, and
   should include at least two codes that are *not denials at all* (PR-1/2/3)
   and one that is *procedurally unappealable* (MA130). Without those a
   classifier can score well by always answering "appeal it".

---

## 1. The real vocabulary

### 1.1 Three code sets, one federal mandate

CMS states the mandate plainly: **[DOC]**

> "Under HIPAA, all payers, including Medicare, are required to use claims
> adjustment reason codes (CARCs) and remittance advice remark codes (RARCs)
> approved by X12 recognized code set maintainers. Payers are not allowed to use
> their own proprietary codes to explain any adjustment in the claim payment."
>
> — [CMS, *Health Care Payment and Remittance Advice and Electronic Funds Transfer*](https://www.cms.gov/priorities/key-initiatives/burden-reduction/administrative-simplification/transactions/health-care-payment-remittance-advice-electronic-funds-transfer)

| Set | What it answers | Maintainer | List |
| --- | --- | --- | --- |
| **CAGC** — Claim Adjustment Group Code | Who bears the unpaid balance | X12 | [x12.org/codes/claim-adjustment-group-codes](https://x12.org/codes/claim-adjustment-group-codes) |
| **CARC** — Claim Adjustment Reason Code | Why the payment differs from the charge | X12 (CARC Committee) | [x12.org/codes/claim-adjustment-reason-codes](https://x12.org/codes/claim-adjustment-reason-codes) |
| **RARC** — Remittance Advice Remark Code | Which specific element or policy drove it | X12 (RARC Committee) | [x12.org/codes/remittance-advice-remark-codes](https://x12.org/codes/remittance-advice-remark-codes) |

X12 defines two RARC flavours, and the distinction is load-bearing for an
extraction agent: **supplemental** RARCs explain an adjustment already described
by a CARC, while **informational** RARCs are *alerts* and are prefaced with
`Alert:` — they explain nothing about liability and must not be treated as a
denial reason. **[DOC]**
([X12 RARC list](https://x12.org/codes/remittance-advice-remark-codes))

Update cadence, per CMS: the **CARC Committee reviews requests 3 times a year**;
the **RARC Committee reviews requests 12 times a year**. **[DOC]**
([CMS EFT/ERA page](https://www.cms.gov/priorities/key-initiatives/burden-reduction/administrative-simplification/transactions/health-care-payment-remittance-advice-electronic-funds-transfer))
Published list updates land on or around **March 1, July 1, and November 1**.
**[DOC]** ([CMS MLN, *Remittance Advice Resources and FAQs*, ICN905367](https://www.cms.gov/Outreach-and-Education/Medicare-Learning-Network-MLN/MLNProducts/Downloads/ICN905367.pdf))

### 1.2 Group codes — who owes the money

Only four are current, all effective 05/20/2018: **[DOC]**
([X12 CAGC list](https://x12.org/codes/claim-adjustment-group-codes))

| Code | X12 definition | Who ends up owing it | Demo meaning |
| --- | --- | --- | --- |
| **CO** | Contractual Obligation | **Provider.** Written off under the participation contract; cannot be billed to the patient. | The denials worth appealing live here. This is real lost revenue. |
| **PR** | Patient Responsibility | **Patient.** Billable to the member. | Usually *not* an appeal target — it's an A/R collection, not a recovery. |
| **OA** | Other Adjustment | Neither, or resolved elsewhere. Used when neither CO nor PR fits. | Signals "route it somewhere else" (COB, duplicate, prior-payer impact). |
| **PI** | Payor Initiated Reduction | **Provider**, but by payer policy rather than contract. | Rare in the wild; include only if you want an edge case. |

CMS's own gloss: "A Contractual Obligation (CO) Group Code assigns
responsibility to the provider and Patient Responsibility (PR) Group Code
assigns responsibility to the patient." **[DOC]**
([CMS MLN ICN905367](https://www.cms.gov/Outreach-and-Education/Medicare-Learning-Network-MLN/MLNProducts/Downloads/ICN905367.pdf);
see also [Medicare Claims Processing Manual, Pub. 100-04, Ch. 22 — Remittance Advice](https://www.cms.gov/regulations-and-guidance/guidance/manuals/downloads/clm104c22_remit_phase3_apr24-03_r2.pdf))

That the group code carries liability semantics is not folklore — X12 encodes it
in the CARC usage notes. CARC 45 reads: *"(Use only with Group Codes PR or CO
depending upon liability)"*, and CARC 18 reads *"(Use only with Group Code OA
except where state workers' compensation regulations requires CO)"*. **[DOC]**
([X12 CARC list](https://x12.org/codes/claim-adjustment-reason-codes))

**Design consequence [INFER]:** `(group, carc)` must be the primary key of the
classifier's input, not `carc`. `CO-50` (payer says not medically necessary,
provider eats it) and `PR-50` (same clinical finding, but a valid ABN shifted
liability to the patient) are the *same CARC* and opposite business outcomes.

### 1.3 How they combine on an 835 / EOB

The 835 Health Care Claim Payment/Advice is the HIPAA-adopted remittance
standard (ASC X12N/005010X221). **[DOC]**
([45 CFR 162.1602](https://www.law.cornell.edu/cfr/text/45/162.1602))

Adjustments live in the **CAS** segment, which appears twice — once at claim
level (loop 2100) and once per service line (loop 2110): **[DOC]**
([X12 835 005010X221A1 structure reference](https://www.stedi.com/edi/hipaa/transaction-set/835-W1))

```
CAS  *  CO  *  197  *  450.00  *
       |      |       |
       |      |       └─ CAS03  adjustment amount (positive = reduces payment)
       |      └───────── CAS02  CARC — the reason
       └──────────────── CAS01  CAGC — who owes it

LQ   *  HE  *  N706                 ← loop 2110 service-line remark code
MOA  *  ...  *  MA130  *  ...       ← claim-level remarks (outpatient/professional)
MIA  *  ...                         ← claim-level remarks (inpatient)
```

Key structural facts an extractor must handle: **[DOC]**

- One CAS segment holds up to **six adjustment trios** (`reason, amount,
  quantity`) — but **all six share the single CAS01 group code**. A claim with
  both a CO write-off and a PR deductible needs *two* CAS segments.
- A negative CAS03 *increases* the payment; a positive one decreases it.
- RARCs at line level are in **LQ** (`LQ01 = "HE"`, up to 99 per line); at claim
  level they are in **MOA** (outpatient/professional) or **MIA** (inpatient).
- Therefore **a single denied line can carry one CARC and many RARCs.** Model
  the relationship as one-to-many, not one-to-one.

On a paper EOB the same tuple is flattened into a "reason code / remark code"
column pair, sometimes with payer-proprietary display text layered on top —
which is why CMS's "no proprietary codes" rule matters: the underlying X12 code
is required to be there. **[INFER]**

### 1.4 The federally-mandated *combinations* (CAQH CORE 360)

This is the piece most denial taxonomies miss. Under ACA §1104, HHS adopted the
**Phase III CAQH CORE EFT & ERA Operating Rule Set**, effective **January 1,
2014**, at 45 CFR 162.1601–162.1603. **[DOC]**
([CMS, EFT/ERA operating rules](https://www.cms.gov/priorities/key-initiatives/burden-reduction/administrative-simplification/transactions/health-care-payment-remittance-advice-electronic-funds-transfer))

Within it, the **CORE Payment & Remittance Uniform Use of CARCs and RARCs (835)
Rule** ("CORE 360") defines four universal business scenarios and publishes an
*exhaustive* allowed set of `CAGC + CARC + RARC` combinations for each — "no
other code combinations are allowed for use in the CORE-defined Business
Scenarios." **[DOC]**
([CAQH CORE Operating Rules](https://www.dataspring.com/core/operating-rules);
[rule PDF](https://www.caqh.org/hubfs/CARCsRARCs_835_Rule.pdf))

| # | CORE-defined business scenario | Approx. allowed combinations |
| --- | --- | --- |
| 1 | Additional Information Required — Missing/Invalid/Incomplete **Documentation** | ~300 |
| 2 | Additional Information Required — Missing/Invalid/Incomplete **Data from Submitted Claim** | ~300 |
| 3 | **Billed Service Not Covered** by Health Plan | ~375 |
| 4 | **Benefit for Billed Service Not Separately Payable** | ~35 |

**[DOC]** ([CAQH CORE, *EFT & ERA Rules Overview*](https://www.caqh.org/hubfs/43908627/drupal/core/phase-iii/policy-rules/EFT-ERA_Rules_Overview.pdf);
cross-referenced in [CMS Transmittal R1281OTN](https://www.cms.gov/regulations-and-guidance/guidance/transmittals/downloads/r1281otn.pdf))

**Why this is the best gift to the demo [INFER]:** scenarios 1 and 2 are the
*fixable* bucket (send documents / correct data), scenarios 3 and 4 are the
*arguable* bucket (coverage and bundling disputes). That is almost exactly the
recoverability axis the agent needs, and it is federally defined rather than
invented. Using CORE scenario as the classifier's coarse label, with
recoverability as the fine label, gives the demo a defensible taxonomy rather
than a hand-rolled one.

### 1.5 Licensing — what is actually paywalled

The ticket flags a historic WPC paywall. Current state, verified:

| Asset | Access | Evidence |
| --- | --- | --- |
| CARC / RARC / CAGC **code text and definitions** | **Free to read** on x12.org. Full lists render publicly with start/modified dates. | Retrieved in full, 2026-09-01, from [x12.org/codes](https://x12.org/codes). CARC page marked "Status Last Reviewed: 8/1/2026". **[DOC]** |
| Reuse of that text | **Copyright-restricted.** "All X12 work products are copyrighted. Any use of any X12 work product must be compliant with US Copyright laws and X12 Intellectual Property policies." | [x12.org/codes](https://x12.org/codes) **[DOC]** |
| Code List Update **Subscription** (change feeds) | **Paid.** | [x12.org/codes](https://x12.org/codes) **[DOC]** |
| WPC's role | Historic distributor; lists moved to x12.org. CMS still points at "the official Washington Publishing Company website pages" for change requests. WPC states most of its publications are now available through X12. | [CMS EFT/ERA page](https://www.cms.gov/priorities/key-initiatives/burden-reduction/administrative-simplification/transactions/health-care-payment-remittance-advice-electronic-funds-transfer); [wpc-edi.com](https://wpc-edi.com/) **[DOC]** |
| CAQH CORE **code-combination workbooks** | Rule documents are public PDFs; the maintained combination tables are distributed by CAQH CORE and could not be retrieved programmatically. | **[NOT FOUND]** |
| CMS **NCCI edit files** | Free download, **but gated behind an AMA CPT licence click-through**: "A license agreement will appear. To continue to the table, accept the terms and conditions of the AMA copyright." | [CMS MLN, *How to Use the NCCI Tools*](https://www.cms.gov/Outreach-and-Education/MLN/Educational-Tools/MLN901346-How-to-use-the-Medicare-NCCI/ncci-medicare/chapter_2_using_the_ncci_tools/) **[DOC]** |

**Practical rule for this repo [INFER]:** the demo may reference code *numbers*
freely and should paraphrase definitions rather than bulk-copying X12 text into
source. It should **not** embed AMA CPT code descriptors in synthetic fixtures —
use HCPCS Level II codes, or opaque placeholders like `PROC-A`. Ship a
`SOURCES.md` naming X12 and CMS as maintainers.

---

## 2. Rejection vs. denial — the distinction the domain model depends on

This is not pedantry; it changes which action the agent may take.

| | **Rejection** | **Denial** | **Medicare "unprocessable"** |
| --- | --- | --- | --- |
| Where it happens | Clearinghouse or payer **front end**, before adjudication | Payer **adjudication** | Medicare front-end edits, surfaced post-835 |
| Transaction | **999** (batch/syntax) or **277CA** Claim Acknowledgment | **835** remittance | **835** remittance |
| Carries CARC/RARC? | No — 277CA uses its own status/error codes | Yes — `CAGC + CARC + RARC` | Yes, but with **RARC MA130** |
| Appeal rights | **None** | **Yes** | **None** |
| Correct action | Fix and **resubmit** as a new claim | **Appeal** (or corrected claim, depending on cause) | Fix and **resubmit** |

Evidence:

- **Front-end flow.** "Your MAC conducts initial or front-end edits to determine
  if the file is readable and issues a 999 Acknowledgement… Claims that pass
  these initial edits, commonly known as front-end edits or pre-edits, are then
  edited against implementation guide requirements… If errors are detected at
  this level, only the individual claims that included those errors would be
  rejected for correction and resubmission," returned via the **277CA**.
  **[DOC]** ([Medicare Claims Processing Manual, Pub. 100-04, Ch. 24 — General EDI and EDI Support](https://www.cms.gov/Regulations-and-Guidance/Guidance/Manuals/downloads/clm104c24.pdf))
- **No appeal rights, in regulation.** 42 CFR 405.926 lists actions that are
  *not* initial determinations and therefore not appealable, including at
  paragraph (s): *"Claim submissions on forms or formats that are incomplete,
  invalid, or do not meet the requirements for a Medicare claim and returned or
  rejected to the provider or supplier."* **[DOC]**
  ([42 CFR 405.926](https://www.law.cornell.edu/cfr/text/42/405.926))
- **The MA130 hybrid.** RARC MA130: *"Your claim contains incomplete and/or
  invalid information, and no appeal rights are afforded because the claim is
  unprocessable. Please submit a new claim with the complete/correct
  information."* **[DOC]**
  ([X12 RARC list](https://x12.org/codes/remittance-advice-remark-codes); Medicare's
  "returned as unprocessable" policy sits at
  [Pub. 100-04, Ch. 1, §80.3](https://www.cms.gov/regulations-and-guidance/guidance/manuals/downloads/clm104c01.pdf))
- **The explicit "don't appeal" flag.** RARC **N211**: *"Alert: You may not
  appeal this decision."* **[DOC]** ([X12 RARC list](https://x12.org/codes/remittance-advice-remark-codes))
- **What a real denial gets.** Five appeal levels — Redetermination (MAC),
  Reconsideration (QIC), OMHA, Medicare Appeals Council, Federal District Court,
  under SSA §1869 and 42 CFR part 405 subpart I. **[DOC]**
  ([CMS, *Original Medicare (Fee-for-Service) Appeals*](https://www.cms.gov/medicare/appeals-grievances/fee-for-service))
  A redetermination "must be filed within 120 calendar days from the date a
  party receives the notice of the initial determination," with a good-cause
  extension. **[DOC]** ([42 CFR 405.942](https://www.law.cornell.edu/cfr/text/42/405.942))

**Modelling recommendation [INFER]:** give the claim a three-valued
`adjudication_outcome`: `REJECTED` (never adjudicated, no CARC, resubmit only),
`DENIED` (adjudicated, has `CAGC+CARC`, appealable), `UNPROCESSABLE`
(adjudicated-shaped, has CARC 16 + MA130, **not** appealable). Then make the
appeal-scorer *structurally incapable* of emitting an appeal for the first and
third. A guardrail beats a confidence threshold here, because MA130 and N211 are
deterministic signals — no model judgement is required or wanted.

Two second-order traps worth encoding: **[INFER]**

- A **corrected claim** (837 with frequency code 7) is a third action distinct
  from both resubmit and appeal, and is the right move for most CARC 16 / CARC
  31 / CARC 140 cases. A binary appeal / don't-appeal output will systematically
  mis-handle the largest bucket.
- The **120-day appeal clock** runs from remittance receipt, and the **timely
  filing clock** (below) runs from date of service. An appeal-worth score that
  ignores dates will happily recommend appealing a claim whose window shut.

---

## 3. What actually drives volume

The honest headline is that **public denial-reason data is coarse**, and the
demo should say so rather than overclaim realism.

| Finding | Value | Source |
| --- | --- | --- |
| ACA Marketplace in-network claims denied, 2024 | **19%** (2023: 20%) | [KFF, *Claims Denials and Appeals in ACA Marketplace Plans in 2024*](https://www.kff.org/patient-consumer-protections/claims-denials-and-appeals-in-aca-marketplace-plans-in-2024/) **[DATA]** |
| Out-of-network claims denied, 2024 | **37%** (2023: 36%) | same **[DATA]** |
| Denial reason: "Other" / unclassified | **36%** | same **[DATA]** |
| Denial reason: administrative | **25%** | same **[DATA]** |
| Denial reason: excluded service | **13%** | same **[DATA]** |
| Denial reason: **lack of prior authorization or referral** | **9%** | same **[DATA]** |
| Denial reason: **medical necessity** | **5%** | same **[DATA]** |
| Share of denied in-network claims appealed by consumers | **<1%** | same **[DATA]** |
| Internal appeals where the insurer upheld its denial, 2024 | **66%** (i.e. ~34% overturned) | same **[DATA]** |
| Medicare Advantage denials **overturned by the MAO itself** on appeal, 2014–16 | **75%** (~216,000/yr) | [HHS OIG, OEI-09-16-00410](https://oig.hhs.gov/reports/all/2018/medicare-advantage-appeal-outcomes-and-audit-findings-raise-concerns-about-service-and-payment-denials/) **[DATA]** |
| MA **prior-auth** denials that in fact met Medicare coverage rules | **13%** | [HHS OIG, OEI-09-18-00260](https://oig.hhs.gov/oei/reports/OEI-09-18-00260.asp) (Apr 2022) **[DATA]** |
| MA **payment** denials that in fact met coverage and billing rules | **18%** | same **[DATA]** |

Three readings that should shape the demo: **[INFER]**

1. **The "administrative" + "other" 61% is where CARC 16, 22, 31, 109 and 18
   live.** These are mostly *not* appeals — they are corrections and rebills.
   A recovery agent that only knows how to appeal addresses the minority of
   volume.
2. **The appeal-worth thesis is empirically sound.** Under 1% of denials are
   appealed, yet MAOs overturn 75% of the ones that are. That gap is precisely
   the demo's premise, and OIG is a citable primary for it.
3. **Prior auth and medical necessity are low-frequency, high-value.** ~14% of
   denials combined, but they are the two with the richest documentation story
   and the strongest overturn evidence — the right hero cases for a demo.

Forward-looking: under **CMS-0057-F** (published 17 Jan 2024), impacted payers —
MA, Medicaid/CHIP FFS and managed care, and FFE QHP issuers — must, beginning
2026, **provide a specific reason for a denied prior authorization**. **[DOC]**
([CMS, *Interoperability and Prior Authorization Final Rule*](https://www.cms.gov/newsroom/fact-sheets/cms-interoperability-prior-authorization-final-rule-cms-0057-f))
Denial-reason data should get materially better, which is a good note for the
demo's "what's next" slide.

---

## 4. Code reference

Group codes shown are the **typical** pairing. X12 constrains the group code for
only a handful of CARCs (18 → OA; 23 → OA; 45 → PR or CO "depending upon
liability"); for the rest the group code is set by payer contract and **must be
read off the 835, not assumed**. **[DOC]/[INFER]**

Recoverability legend:
**Yes** = appeal/rebill usually succeeds with the right packet ·
**Context** = cannot be judged from the code; needs dates, payer, service type,
or an edit lookup ·
**No** = do not generate an appeal.

| Code | Group | Plain-English meaning | Recoverable? | Documentation needed | Source |
| --- | --- | --- | --- | --- | --- |
| **CARC 197** | CO | Precertification / authorization / notification / pre-treatment **absent**. | **Context** — turns on whether an auth existed, whether the service was emergent, and whether the payer has a retro-auth window. | Auth number + approval letter if one existed; retro-auth request; clinical notes showing medical necessity; proof of emergent/urgent presentation; payer's own auth policy for the CPT on that DOS; call logs / reference numbers for notification attempts. | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) |
| **CARC 15** | CO | "The authorization number is missing, invalid, or does not apply to the billed services or provider." | **Yes** — usually a data error, not a coverage decision. | The correct auth number and approval letter; proof the auth covers this CPT/provider/DOS; **corrected claim**, not an appeal. | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) |
| **CARC 288** | CO | "Referral absent" — a required referral was not on file. | **Context** — some plans accept retroactive referrals, many do not. | Referral document with dates; PCP attestation; plan's referral policy; evidence of self-referral exception (e.g. emergency). | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) |
| **CARC 50** | CO *(PR if a valid ABN shifted liability)* | "These are non-covered services because this is not deemed a 'medical necessity' by the payer." | **Context** — genuinely arguable when clinicals support it; **not** an appeal if `PR` with a valid ABN, which means liability already moved to the patient. | Full clinical notes; physician letter of medical necessity; the governing **NCD or LCD** and a point-by-point map of how the record meets it; imaging/labs; documentation of failed conservative therapy. Frequently paired with RARC **N115** (decision based on an LCD). | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) · [CMS, Coverage Determination Process](https://www.cms.gov/medicare/coverage/determination-process) · [CMS BNI/ABN](https://www.cms.gov/medicare/forms-notices/beneficiary-notices-initiative) |
| **CARC 29** | CO | "The time limit for filing has expired." | **Context** — recoverable **only** with proof of original timely submission or a regulatory exception; otherwise dead. | Clearinghouse acceptance report / **277CA** showing the original submission date; payer acknowledgment; for Medicare, evidence of a 42 CFR 424.44(b) exception (contractor error, retroactive entitlement, Medicaid recovery, MA disenrollment). Medicare limit is 1 calendar year from date of service. | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) · [42 CFR 424.44](https://www.law.cornell.edu/cfr/text/42/424.44) |
| **CARC 22** | OA | "This care may be covered by another payer per coordination of benefits." | **Yes** — but by **rebilling**, not appealing. | Primary payer's EOB/835 with paid, allowed and adjusted amounts; corrected COB order; updated eligibility. Usually paired with RARC **MA04** ("Secondary payment cannot be considered without the identity of or payment information from the primary payer") or **N4** (missing prior carrier EOB). | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) · [X12 RARC](https://x12.org/codes/remittance-advice-remark-codes) |
| **CARC 109** | OA | "Claim/service not covered by this payer/contractor. You must send the claim/service to the correct payer/contractor." | **Yes** — route to the correct payer. Never an appeal. | Correct payer ID and member ID; eligibility verification for the DOS. Watch the *other* payer's timely-filing clock, which is already running. | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) |
| **CARC 97** | CO | "The benefit for this service is included in the payment/allowance for another service/procedure that has already been adjudicated." (bundling) | **Context** — arguable when the services were genuinely distinct. | Operative/procedure note proving separate session, site, or encounter; correct modifier (59, XE, XP, XS, XU, or 25); payer bundling policy. Paired with RARC **M15** (separately billed services bundled as components) or **N19** (incidental to primary procedure). | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) · [X12 RARC](https://x12.org/codes/remittance-advice-remark-codes) |
| **CARC 236** | CO | Procedure or procedure/modifier combination "is not compatible with another procedure or procedure/modifier combination provided on the same day according to the **National Correct Coding Initiative**." | **Context — requires an edit-file lookup.** Recoverable only if the PTP pair's **CCMI = 1**. CCMI **0** = "No modifiers associated with NCCI allow you use this PTP code pair" → dead. CCMI 9 = edit inactive. | The PTP edit's modifier indicator for that pair and quarter; op note supporting a distinct service; correct NCCI-associated modifier. Appeals go to the MAC/QIC, never to the NCCI contractor. | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) · [CMS, *Using the NCCI Tools* (CCMI table)](https://www.cms.gov/Outreach-and-Education/MLN/Educational-Tools/MLN901346-How-to-use-the-Medicare-NCCI/ncci-medicare/chapter_2_using_the_ncci_tools/) · [CMS NCCI PTP Edits](https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits) |
| **CARC 151** | CO | "Payment adjusted because the payer deems the information submitted does not support this many/frequency of services." (units / MUE) | **Context — depends on the MUE Adjudication Indicator.** MAI **1** (claim-line) and MAI **3** (clinical benchmark) can be reviewed on reopening/redetermination with records. MAI **2** is an *absolute* per-day policy edit grounded in statute or regulation — not recoverable. | Medical records evidencing the units actually furnished; correct units of service per the code's UOS definition; anatomic/repeat modifiers (59, XE/XP/XS/XU, 76, 77, 91). Note CMS: "A denial of services due to an MUE is a coding denial, not a medical necessity denial," and an ABN does **not** shift MUE liability to the patient. Often paired with RARC **N362** (days/units exceed acceptable maximum). | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) · [CMS Medicare NCCI FAQ Library](https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-faq-library) · [CMS MUE page](https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edits) |
| **CARC 16** | CO | "Claim/service lacks information or has submission/billing error(s)." X12 requires **at least one Remark Code** with it — the CARC alone is meaningless. | **Context — read the RARC.** With **N705/N706** (incomplete/missing documentation) or **N286/N290** (missing referring/rendering provider ID) → fix and resubmit. With **MA130** → **No**, see below. | Whatever the RARC names: the missing NPI, the missing documentation, the corrected data element. The right action is almost always a **corrected claim**, not an appeal. | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) · [X12 RARC](https://x12.org/codes/remittance-advice-remark-codes) |
| **CARC 31** | CO | "Patient cannot be identified as our insured." | **Yes** — an identity/eligibility data fix. | Corrected member ID, name, DOB; eligibility verification (270/271) for the DOS; corrected claim. Related: CARC **140** (ID number and name do not match), RARC **MA27**. | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) |
| **CARC 27** | CO or PR | "Expenses incurred after coverage terminated." | **Context** — recoverable only if the termination date on file is wrong; otherwise it is a patient-liability or bad-debt outcome. | Eligibility record for the DOS; employer/plan reinstatement notice; COBRA election evidence. Sibling code: CARC **26** (expenses incurred prior to coverage). | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) |
| **CARC B7** | CO | "This provider was not certified/eligible to be paid for this procedure/service on this date of service." | **Context** — recoverable when it is an enrolment/credentialing effective-date error, not when the provider truly lacked eligibility. | Enrolment record showing the effective date; credentialing approval letter; provider-type scope evidence. Related RARC **N95** (provider type/specialty may not bill this service). | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) · [X12 RARC](https://x12.org/codes/remittance-advice-remark-codes) |
| **CARC 96** | CO or PR | "Non-covered charge(s)." Requires at least one Remark Code. | **Context, leaning No.** If the RARC points at a **statutory exclusion** (SSA §1862(a)) it is not recoverable at all. If it points at plan policy (**N130** — consult plan benefit documents) there may be an argument. | Plan benefit document language; the specific exclusion cited; medical necessity packet if arguing an exception; ABN status if `PR`. | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) · [X12 RARC](https://x12.org/codes/remittance-advice-remark-codes) |
| **CARC 204** | CO or PR | "This service/equipment/drug is not covered under the patient's current benefit plan." | **No**, except when the patient is on the wrong plan record. | Only worth pursuing to correct eligibility/plan assignment. Otherwise this is benefit design — appealing it wastes the reviewer's time. | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) |
| **CARC 18** | **OA** (X12-constrained) | "Exact duplicate claim/service." | **No** when it is a true duplicate. **Context** only when it is a false positive — a genuinely distinct same-day service, or a crossover artifact flagged by RARC **N522** ("Duplicate of a claim processed, or to be processed, as a crossover claim"). | To dispute: op notes showing two distinct encounters plus modifier 76/77/59; original claim number and its adjudication. Otherwise: close the A/R line, do not appeal. | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) · [X12 RARC](https://x12.org/codes/remittance-advice-remark-codes) |
| **CARC 119** | CO or PR | "Benefit maximum for this time period or occurrence has been reached." | **No** — the benefit is exhausted. | None. Route to patient responsibility or secondary coverage. | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) |
| **CARC 45** | CO *(or PR "depending upon liability")* | "Charge exceeds fee schedule/maximum allowable or contracted/legislated fee arrangement." | **No.** This is the contractual write-off — it is how network participation works, not a denial. | None. If `CO-45` is the *only* adjustment, the claim was **paid correctly**. Flagging it as a denial is the single most common false positive in denial analytics. | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) |
| **CARC 1 / 2 / 3** | **PR** | Deductible / Coinsurance / Co-payment amount. | **No — these are not denials at all.** | None. Bill the patient. An agent that appeals `PR-1` is appealing the patient's deductible to the insurer. | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) |
| **CARC 23** | **OA** (X12-constrained) | "The impact of prior payer(s) adjudication including payments and/or adjustments." | **No** — informational COB accounting. | None. | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) |
| **CARC 253** | CO | "Sequestration - reduction in federal payment." | **No** — statutory percentage reduction. | None. | [X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes) |
| **RARC MA130** | — (rides with CARC 16) | "Your claim contains incomplete and/or invalid information, and **no appeal rights are afforded** because the claim is unprocessable. Please submit a new claim with the complete/correct information." | **No appeal, ever.** Correct and resubmit. | The specific data element named by the accompanying CARC/RARC. Reinforced by 42 CFR 405.926(s): rejected/returned claims are not initial determinations. | [X12 RARC](https://x12.org/codes/remittance-advice-remark-codes) · [42 CFR 405.926](https://www.law.cornell.edu/cfr/text/42/405.926) |
| **RARC N211** | — | "**Alert:** You may not appeal this decision." | **No appeal, ever.** | None. Deterministic hard stop. | [X12 RARC](https://x12.org/codes/remittance-advice-remark-codes) |

### 4.1 What the code alone can and cannot tell you

Judgeable **from the tuple alone** (deterministic — implement as rules, not ML):

- `PR-1 / PR-2 / PR-3`, `CO-45`, `OA-23`, `CO-253` → not denials; never appeal.
- Any RARC `MA130` or `N211` → no appeal rights, full stop.
- `CO-119`, `CO/PR-204` → benefit design; appeal only on an eligibility error.

**Not** judgeable from the code — requires claim context:

| Code | Missing context | Where it comes from |
| --- | --- | --- |
| `CO-29` | Was the original claim submitted on time? What is the payer's limit? | 277CA acceptance date, DOS, payer contract |
| `CO-197` | Was an auth obtained? Was it emergent? Is there a retro window? | Auth system, encounter type, payer policy |
| `CO-50` | Do the clinicals meet the governing NCD/LCD? Was an ABN signed? | Chart, coverage database, ABN record |
| `CO-236` | Is the PTP pair's CCMI 0 or 1, for that quarter? | CMS NCCI PTP edit file |
| `CO-151` | Is the MUE's MAI 1, 2, or 3? | CMS MUE file |
| `CO-16` | Which RARC? MA130 changes the answer entirely. | The LQ/MOA segments |
| `OA-18` | True duplicate, or two distinct same-day services? | Claim history, op notes |

X12 makes this explicit rather than leaving it to inference: CARC **16, 96, 234
and 252** each carry the usage note *"At least one Remark Code must be
provided."* **[DOC]**
([X12 CARC](https://x12.org/codes/claim-adjustment-reason-codes)) The standard
itself declares these CARCs insufficient on their own — a strong argument for
making the RARC a required field in the demo's domain model rather than an
optional annotation.

---

## Recommended demo subset

**Twelve codes.** Chosen so that (a) every high-volume real-world family is
represented, (b) roughly half are genuinely non-recoverable, (c) three require
*claim context* rather than code lookup, and (d) two are traps that punish a
model which has learned "denial → appeal".

| # | Tuple | Family | Label | Why it earns its place |
| --- | --- | --- | --- | --- |
| 1 | `CO-197` + `N706` | Prior authorization | **Context → often recoverable** | Highest-value appealable family; OIG shows 13% of MA prior-auth denials met coverage rules. Forces the agent to look for an auth record and an urgency flag. |
| 2 | `CO-50` + `N115` | Medical necessity | **Context → recoverable with clinicals** | The archetypal appeal. Requires reasoning against an LCD, not pattern-matching. |
| 3 | `PR-50` (same CARC, ABN on file) | Medical necessity, liability shifted | **Not recoverable** | Same CARC as #2, opposite outcome. Proves the classifier must read the **group code**. |
| 4 | `CO-29` | Timely filing | **Context → recoverable only with proof** | Forces date arithmetic and a submission-evidence check; punishes date-blind optimism. |
| 5 | `OA-22` + `MA04` | Coordination of benefits | **Recoverable — by rebill, not appeal** | Teaches that "recoverable" ≠ "appeal". Distinct action type. |
| 6 | `CO-16` + `MA130` | Unprocessable | **No appeal rights** | The rejection/denial trap. Looks like a denial, has a CARC, is legally unappealable. |
| 7 | `CO-236` | Bundling / NCCI PTP | **Context → depends on CCMI** | Recoverability lives in an external edit file, not the code. Great demo of tool use. |
| 8 | `CO-97` + `M15` | Bundling / payer policy | **Context → recoverable with op note** | Near-neighbour of #7 with a different resolution path; tests discrimination. |
| 9 | `OA-18` + `N522` | Duplicate | **Usually not recoverable** | Cheap volume in real remits; must be triaged out, not appealed. |
| 10 | `CO-96` + `N130` | Non-covered service | **Leaning not recoverable** | Separates plan-policy non-coverage (arguable) from statutory exclusion (dead). |
| 11 | `CO-45` | Contractual write-off | **Not a denial** | The classic false positive. If it is the only adjustment, the claim was paid correctly. |
| 12 | `PR-1` / `PR-2` / `PR-3` | Patient responsibility | **Not a denial** | Deductible/coinsurance/copay. An agent that appeals these has failed the domain. |

**Minimum viable eight**, if scope must shrink: 1, 2, 4, 5, 6, 9, 11, 12 — this
keeps prior auth, medical necessity, timely filing, COB, the unappealable trap,
duplicates, and both not-a-denial negatives.

**Never generate an appeal for** (hard guardrail, not a score threshold):
any adjustment whose RARC is **MA130** or **N211**; any `PR-1/2/3`;
`CO-45` standing alone; `OA-23`; `CO-253`; and `CO-236` where the PTP modifier
indicator is **0**. **[DOC]** for each, per the table in §4.

### Suggested domain model shape [INFER]

```
Remittance
└── Claim
    ├── adjudication_outcome : REJECTED | DENIED | UNPROCESSABLE
    └── ServiceLine
        └── Adjustment           # one per CAS trio
            ├── group_code       : CO | PR | OA | PI      ← required
            ├── reason_code      : CARC                    ← required
            ├── remark_codes     : [RARC]                  ← 0..n, required for 16/96/234/252
            ├── amount           : Money
            └── core_scenario    : 1 | 2 | 3 | 4 | null    ← CAQH CORE 360
```

Derive `recoverability` as a function of `(group_code, reason_code,
remark_codes, claim_context)` — never of `reason_code` alone. Emit an
`action` of `APPEAL | CORRECTED_CLAIM | REBILL_OTHER_PAYER | PATIENT_BILL |
CLOSE`, not a boolean. The five-way action is what makes the classification
non-trivial and what matches how an RCM team actually works.

---

## Sources

Primary code lists and standards
- [X12 — Claim Adjustment Reason Codes](https://x12.org/codes/claim-adjustment-reason-codes)
- [X12 — Remittance Advice Remark Codes](https://x12.org/codes/remittance-advice-remark-codes)
- [X12 — Claim Adjustment Group Codes](https://x12.org/codes/claim-adjustment-group-codes)
- [X12 — External Code Lists (copyright and subscription terms)](https://x12.org/codes)
- [Washington Publishing Company](https://wpc-edi.com/)
- [X12 835 005010X221A1 segment structure](https://www.stedi.com/edi/hipaa/transaction-set/835-W1)

Regulation
- [45 CFR 162.1602 — adopted standards for payment and remittance advice](https://www.law.cornell.edu/cfr/text/45/162.1602)
- [42 CFR 405.926 — actions that are not initial determinations](https://www.law.cornell.edu/cfr/text/42/405.926)
- [42 CFR 405.942 — time frame for filing a redetermination](https://www.law.cornell.edu/cfr/text/42/405.942)
- [42 CFR 424.44 — time limits for filing Medicare claims](https://www.law.cornell.edu/cfr/text/42/424.44)

CMS
- [Health Care Payment and Remittance Advice and EFT](https://www.cms.gov/priorities/key-initiatives/burden-reduction/administrative-simplification/transactions/health-care-payment-remittance-advice-electronic-funds-transfer)
- [Original Medicare (Fee-for-Service) Appeals](https://www.cms.gov/medicare/appeals-grievances/fee-for-service)
- [Medicare Coverage Determination Process (NCD/LCD)](https://www.cms.gov/medicare/coverage/determination-process)
- [Beneficiary Notices Initiative (ABN, Form CMS-R-131)](https://www.cms.gov/medicare/forms-notices/beneficiary-notices-initiative)
- [NCCI for Medicare](https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits)
- [Medicare NCCI PTP Edits](https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits)
- [Medicare NCCI Medically Unlikely Edits](https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-medically-unlikely-edits)
- [Medicare NCCI FAQ Library (MAI definitions, MUE-vs-medical-necessity)](https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-faq-library)
- [MLN — How to Use the NCCI Tools (CCMI table)](https://www.cms.gov/Outreach-and-Education/MLN/Educational-Tools/MLN901346-How-to-use-the-Medicare-NCCI/ncci-medicare/chapter_2_using_the_ncci_tools/)
- [Interoperability and Prior Authorization Final Rule (CMS-0057-F)](https://www.cms.gov/newsroom/fact-sheets/cms-interoperability-prior-authorization-final-rule-cms-0057-f)
- [MLN — Remittance Advice Resources and FAQs (ICN905367)](https://www.cms.gov/Outreach-and-Education/Medicare-Learning-Network-MLN/MLNProducts/Downloads/ICN905367.pdf) *(PDF)*
- [Medicare Claims Processing Manual, Ch. 22 — Remittance Advice](https://www.cms.gov/regulations-and-guidance/guidance/manuals/downloads/clm104c22_remit_phase3_apr24-03_r2.pdf) *(PDF)*
- [Medicare Claims Processing Manual, Ch. 24 — General EDI and EDI Support](https://www.cms.gov/Regulations-and-Guidance/Guidance/Manuals/downloads/clm104c24.pdf) *(PDF)*
- [Medicare Claims Processing Manual, Ch. 1 — General Billing Requirements (§80.3 unprocessable claims)](https://www.cms.gov/regulations-and-guidance/guidance/manuals/downloads/clm104c01.pdf) *(PDF)*

Operating rules
- [CAQH CORE — Operating Rules index](https://www.dataspring.com/core/operating-rules)
- [CAQH CORE — Uniform Use of CARCs and RARCs (835) Rule](https://www.caqh.org/hubfs/CARCsRARCs_835_Rule.pdf) *(PDF)*
- [CAQH CORE — EFT & ERA Rules Overview (business scenarios)](https://www.caqh.org/hubfs/43908627/drupal/core/phase-iii/policy-rules/EFT-ERA_Rules_Overview.pdf) *(PDF)*

Denial and appeal data
- [KFF — Claims Denials and Appeals in ACA Marketplace Plans in 2024](https://www.kff.org/patient-consumer-protections/claims-denials-and-appeals-in-aca-marketplace-plans-in-2024/)
- [KFF — Claims Denials and Appeals in ACA Marketplace Plans in 2023](https://www.kff.org/private-insurance/issue-brief/claims-denials-and-appeals-in-aca-marketplace-plans-in-2023/)
- [HHS OIG OEI-09-16-00410 — MA appeal outcomes (75% overturn)](https://oig.hhs.gov/reports/all/2018/medicare-advantage-appeal-outcomes-and-audit-findings-raise-concerns-about-service-and-payment-denials/)
- [HHS OIG OEI-09-18-00260 — MA prior authorization denials (Apr 2022)](https://oig.hhs.gov/oei/reports/OEI-09-18-00260.asp)

### Retrieval caveats

- **cms.gov blocks automated fetching** (HTTP 403 on both HTML and PDF paths).
  CMS HTML pages above were read through a browser session and quoted directly.
  CMS PDFs marked *(PDF)* were **not** machine-read; they are cited as the
  authoritative location of the policy, with the substantive quotes in this
  document taken from sources that could be read directly (X12 code text, the
  eCFR/Cornell regulation text, and CMS HTML pages). **[NOT FOUND]** for
  verbatim text of Pub. 100-04 Ch. 1 §80.3, Ch. 22 and Ch. 24.
- **CAQH CORE code-combination workbooks** could not be retrieved; scenario
  names and combination counts come from CAQH-published overview material and a
  CMS transmittal, not from the workbooks themselves. **[NOT FOUND]** for the
  per-scenario code lists.
- The **eCFR** redirected automated requests; regulation text was read from
  Cornell LII, which republishes the CFR verbatim.
