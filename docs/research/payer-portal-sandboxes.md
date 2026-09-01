# Payer-portal sandboxes that permit automated access

Research ticket: GitHub issue #5 — "Are there payer-portal sandboxes that permit automated access?"
Researched: 2026-09-01. Primary sources only (vendor/agency documentation and published terms).

---

## Bottom line

**No.** There is no authorised, automatable, browser-based payer portal reachable inside a one-week budget.

Every environment falls into exactly one of three buckets:

1. **Free and instant, but API-only.** Availity's Demo plan, Optum/Change Healthcare's sandbox, CMS BCDA, CMS AB2D. These return JSON or bulk-FHIR NDJSON. There is no claim-status screen to drive and no PDF to download, so they cannot demonstrate browser computer-use at all.
2. **Has a real HTML portal, but access is gated behind a provider identity we do not have.** Availity Essentials, Office Ally Service Center, UnitedHealthcare Provider Portal, state Medicaid portals (eMedNY ePACES, MS MESA). All require a genuine organisation NPI and/or Tax ID, and several require a signed trading-partner or ETIN certification. Multi-week at best, and dishonest at worst.
3. **Has a real HTML portal but explicitly forbids bots.** Availity Essentials, UnitedHealthcare, Aetna, Blue Shield of California, CMS Enterprise Portal. See the payer-position section below.

The single closest near-miss is the **CMS Blue Button 2.0 sandbox**, which is free, self-service, instant, and does render one genuine HTML page a browser agent can drive — the synthetic-beneficiary Medicare login and OAuth consent screen. But it is *only* a login/consent screen. After consent, all data arrives as FHIR `ExplanationOfBenefit` JSON over the API. There is no claim-status search UI, no denial worklist, and no EOB or denial-letter PDF anywhere in the environment. It also cannot carry the demo's other requirements (see "Why Blue Button 2.0 still does not work" below).

**Recommendation: build the mock portal.** This finding settles the downstream decision. A locally-hosted mock payer portal is the only way to demonstrate authorised browser computer-use over claim status and EOB/denial-PDF retrieval within the budget, and it is fully consistent with the project's hard constraint of never solving CAPTCHAs and never evading bot detection.

---

## Environment matrix

| Environment | Portal or API? | Access path | Time to access | Automation permitted? | Source |
|---|---|---|---|---|---|
| **Availity API Developer Portal — Demo plan** | **API only.** Canned JSON responses per endpoint. The portal HTML is a developer console for keys/subscriptions, not a payer portal. | Self-service account (email + MFA via authenticator app) → register app → subscribe to Demo plan. Demo subscriptions are "automatically approved". Free. | **Minutes.** | API automation: yes, that is its purpose. Browser automation of the real portal: explicitly no. | [developer.availity.com/partner/gettingstarted](https://developer.availity.com/partner/gettingstarted) |
| **Availity Essentials** (the real multi-payer provider portal; the front door for Aetna, many BCBS plans, Anthem/Wellpoint, Molina) | **Real HTML portal** with claim status and remittance viewing. | Organisation registration requires org type, primary service location, **Tax ID (EIN or SSN)** and **organisation NPI**; faster approval offered if you supply details from a health-plan cheque received in the last six months. Registrant becomes primary administrator. | **Days to weeks**, and requires being an actual healthcare or healthcare-adjacent business. Not obtainable for a demo project. | **No.** Availity states it moved to "eliminate bot access to Availity Essentials, our provider portal", offering RESTful APIs as the sanctioned alternative. | [Availity payer registration guide](https://essentials.availity.com/availity/help-open/source/portal_payers/get_started/payer_registration_guide/_topics/c_payer_reg_guide_initial_considerations_providers.html) · [availity.com/blog/why-apis-are-better-than-bots](https://www.availity.com/blog/why-apis-are-better-than-bots/) |
| **Optum / Change Healthcare Medical Network sandbox** | **API only.** `https://sandbox-apigw.optum.com/medicalnetwork/`, OAuth2 client credentials, X12 transactions translated to JSON. Requires "canned patient" and "canned provider" values. | "Request Sandbox Access" form → **the Optum team reaches out** and issues client id/secret. Free, "without any financial obligation before signing a contract". | **Unbounded** — human-in-the-loop email round trip, no published SLA. Not safely inside a week. | API automation is the intended use. No browser surface exists to automate. | [Create a Sandbox Account](https://developer.optum.com/eligibilityandclaims/docs/create-a-sandbox-account) · [API URLs](https://developer.optum.com/eligibilityandclaims/docs/api-urls) |
| **Waystar** | **API / EDI only** (REST, web services, SFTP, HL7, X12). Test/sandbox accounts are documented but the docs page is gated. | Register on the Waystar developer/partner portal; sandbox and production access are partner- or customer-gated. No published self-service path. | **Unknown, sales-gated.** Assume weeks. | No public terms permitting third-party automated access; no public browser test portal. | [developer.waystar.com](https://developer.waystar.com/) |
| **Office Ally Service Center** | **Real HTML portal** (free clearinghouse web portal), plus SFTP/SOAP EDI. **No developer sandbox found.** | Account setup requires listing **all NPIs you bill with**; NPI validation/registration with payers is a prerequisite for eligibility transactions; Office Ally phones you within one business day to onboard. Per-payer EDI enrollment forms and **electronic trading partner agreements** on top. | **Days to weeks**, and requires being a real billing provider. | No sanctioned automated-browser path published. Payer-specific trading partner agreements govern the EDI channel. | [Service Center](https://cms.officeally.com/products/service-center) · [Service Center user manual](https://cms.officeally.com/OfficeAlly/Forms/Forms/OA_ServiceCenter_UserManual_r060822.pdf) · [EDI/TPA packets](https://cms.officeally.com/resources/forms-manuals) |
| **CMS Blue Button 2.0 sandbox** | **Hybrid — the only browser surface in the whole field.** One real HTML Medicare login + OAuth consent page at `sandbox.bluebutton.cms.gov`; everything after that is FHIR JSON. **No claim-status UI, no EOB/denial PDFs.** | Self-service: create a sandbox account, register an app, then log in as a published synthetic beneficiary. Credentials are documented publicly: `BBUser00000` / `PW00000!` through `BBUser29999` / `PW29999!` (trailing `!` required). Free. | **Minutes.** | Grey. CMS's portal-automation policy carves out only APIs (below), and `sandbox.bluebutton.cms.gov/robots.txt` disallows exactly `/v1/o/`, `/v2/o/`, `/v3/o/` — the OAuth authorize paths where that HTML login page lives. Terms also state "**Developer credentials may not be embedded in open source projects.**" | [Get Started with Sandbox](https://bluebutton.cms.gov/api-documentation/developer-sandbox/) · [API Terms of Service](https://bluebutton.cms.gov/terms/) · [api-terms-of-use.html](https://cmsgov.github.io/bluebutton-developer-help/api-terms-of-use.html) |
| **CMS BCDA** (Beneficiary Claims Data API) | **API only.** Bulk FHIR NDJSON export. | Sandbox is open to anyone; **generic credentials are published in the guide**. Free. | **Minutes.** | Scripted API access is the intended use. No browser surface. | [bcda.cms.gov/guide.html](https://bcda.cms.gov/guide.html) · [How to Access Claims Data](https://bcda.cms.gov/build.html) |
| **CMS AB2D** (Claims Data to Part D Sponsors) | **API only.** Bulk FHIR, `sandbox.ab2d.cms.gov`. | Sandbox open to anyone, public bearer-token instructions, no attestation needed. Free. | **Minutes.** | Scripted API access intended. No browser surface. Production is restricted to Part D sponsors. | [Access Sandbox Test Claims Data](https://ab2d.cms.gov/access-sandbox-data) |
| **CMS DPC** (Data at the Point of Care) | **API** (bulk FHIR) plus a **developer credential portal** at `dpc.cms.gov` — that portal manages client tokens, it is not a claim-status portal. | Request a sandbox account; CMS emails confirmation, then **your account must be assigned to an organisation by CMS** before you can create a client token. Intended for FFS provider organisations and health IT implementers. Production onboarding was paused pending ID-verification rework. | **Unbounded** — two-stage manual assignment. Not safely inside a week. | API automation intended; the portal itself is credential management only. | [dpc.cms.gov/faq](https://dpc.cms.gov/faq) · [About the DPC Pilot](https://dpc.cms.gov/pilot) |
| **CMS HETS 270/271 test environment** | **Neither — no browser UI at all.** Real-time X12 270/271 over SOAP+MIME / CORE connectivity. | Complete and sign the **HETS Trading Partner Agreement**, email a signed copy to `mcare@cms.hhs.gov`, wait for CMS approval, receive a submitter ID, then run **testing coordinated by the MCARE Help Desk**. Annual TPA recertification required. | **Weeks.** Hard blocker. | Irrelevant — there is nothing to drive with a browser. | [How to Get Connected — HETS 270/271](https://www.cms.gov/Research-Statistics-Data-and-Systems/CMS-Information-Technology/HETSHelp/HowtoGetConnectedHETS270271) · [HETS TPA form](https://www.cms.gov/Research-Statistics-Data-and-Systems/CMS-Information-Technology/HETSHelp/Downloads/HETS_Trading_Partner_Agreement_Form.pdf) |
| **State Medicaid test portals** — e.g. NY eMedNY ePACES | **Real HTML portal**, and a test region exists for trading partners. | ePACES enrolment requires **NPI or MMIS provider ID**, a valid email, and **an active, certified ETIN** belonging to the submitting entity, obtained via a paper ETIN application plus a signed certification statement. | **Weeks.** | Access is bound to a certified real-world submitter identity; no sanctioned third-party automation. | [ePACES enrolment overview](https://www.emedny.org/hipaa/QuickRefDocs/ePACES-Enrollment_Overview.pdf) · [ETIN information](https://www.emedny.org/info/etin/) |
| **State Medicaid test portals** — e.g. MS Medicaid MESA | Portal + EDI. Trading-partner test environment ("MESA TPI"). | All newly enrolled trading partners must **enrol and then certify by testing in the TPI environment** before their Trading Partner ID is activated for production. | **Weeks.** | Bound to an enrolled trading-partner identity. | [MS Medicaid EDI enrolment and testing](https://medicaid.ms.gov/electronic-data-interchange-edi-testing/) |
| **Clearinghouse test harnesses generally** | **API / file exchange.** X12 837/835/270/271/276/277 over SFTP or SOAP. | Trading-partner agreement plus certification testing per payer. | **Weeks.** | Nothing browser-drivable. | (pattern confirmed across Office Ally, Waystar, Optum, HETS, state Medicaid sources above) |

---

## Why Blue Button 2.0 still does not work for this demo

It is the only candidate that clears the "free, instant, self-service, has an HTML page" bar, so it deserves an explicit rejection rather than a silent one.

1. **Wrong artefact.** The demo needs claim status plus **EOB / denial-letter PDFs**. Blue Button 2.0 returns FHIR `ExplanationOfBenefit` **JSON**. There are no PDFs in the sandbox, and no denial-letter concept at all.
2. **Wrong surface.** Exactly one screen is browser-drivable: the synthetic-beneficiary login and consent page. Everything a denial-recovery agent would actually *do* — search claims, open a denial, download a document — has no UI. The demo would show a browser agent typing `BBUser00000` into a login box and then stopping.
3. **Wrong actor.** Blue Button 2.0 is a *beneficiary*-authorisation API. The PRD's agent is a *provider-side* RCM actor. The consent model does not match the story.
4. **`robots.txt` points the other way.** `sandbox.bluebutton.cms.gov/robots.txt` reads:
   ```
   User-agent: *
   Disallow: /v1/o/
   Disallow: /v2/o/
   Disallow: /v3/o/
   ```
   Those are the OAuth paths that serve the login and consent HTML. Under this project's stated constraint — automate only where automation is authorised — a `Disallow` on the one page we would drive is a stop sign, not a technicality to argue past.
5. **Public-repo friction.** The Blue Button API terms state "**Developer credentials may not be embedded in open source projects**" ([terms](https://bluebutton.cms.gov/terms/)). A public demo repo would have to keep its client id/secret out of the tree and out of CI, which is doable but is extra work for an environment that cannot demonstrate the target workflow anyway.
6. **CMS's own portal-automation policy cuts against it.** CMS's published guidance on proper use of CMS systems states that use of scripts or automation tools on CMS websites is not allowed and that "**This does not apply to scripted interactions with public-facing application programming interfaces (APIs) maintained by CMS**" ([CMS Agent/Broker FAQ](https://www.agentbrokerfaq.cms.gov/s/article/What-are-proper-uses-of-CMS-systems-that-agents-and-brokers-are-required-to-abide-by-when-accessing-HealthCare-gov-the-CMS-Enterprise-Portal-and-the-Direct-Enrollment-Pathways)). The carve-out is for APIs. Driving CMS *web pages* with a script is the thing being excluded.

---

## Published positions of the payers named in the PRD

Factual summary of what each organisation's own published terms say about automated or scripted access. This section documents *whether* automation is permitted; it deliberately contains nothing about circumventing any protection.

### UnitedHealthcare

UnitedHealth Group's Terms of Use, under "Restrictions on Use of Online Services", prohibits users from:

> "use software or other means to access, 'scrape,' 'crawl,' or 'spider,' any web pages or other services from the Online Services."
>
> — <https://www.unitedhealthgroup.com/terms-of-use.html>

Separately, UHCprovider.com's provider-portal authentication guidance states that following its security updates, bots will no longer be able to sign in to the provider portal, and directs organisations needing automation to use an **API** instead ([uhcprovider.com/en/access/provider-portal-authentication.html](https://www.uhcprovider.com/en/access/provider-portal-authentication.html)). Portal registration itself requires a One Healthcare ID, an organisation **Tax ID (TIN)**, and an **NPI** for clinicians and physicians ([uhcprovider.com/en/access.html](https://www.uhcprovider.com/en/access.html)).

**Position: automated browser access to the provider portal is not permitted. API is the sanctioned channel.**

### Aetna

Aetna's web and mobile terms of use prohibit the use of:

> "any robot, spider, site search/retrieval application or other manual or automatic device to retrieve, index, 'scrape' 'data mine' or in any way gather the Applications or reproduce or circumvent the navigational structure or presentation of the Applications without our express prior written consent."
>
> — <https://www.aetna.com/legal-notices/disclaimer.html>

Aetna's provider-facing transactions run through **Availity Essentials**, so Availity's no-bots policy applies on top.

**Position: not permitted without express prior written consent.**

### Blue Cross Blue Shield

BCBS is a federation, so terms are per-plan, but the direction is uniform. Blue Shield of California's Provider Connection portal states:

> "Organizations are also prohibited from using 'automated' scrapping programs on our site to mine data. Scrapping programs impact portal performance and will result in the account being disabled."
>
> — <https://www.blueshieldca.com/en/provider/about-pc>

Blue Cross NC's enrolment platform terms similarly prohibit using "any scraper, crawler, spider, robot or other automated means of any kind to access or copy data on the Platform or bypass robot exclusion headers or other measures" ([enroll.bluecrossnc.com/agents/terms_of_service](https://enroll.bluecrossnc.com/agents/terms_of_service)). Many BCBS plans (BCBSIL, BCBSTX, BCBSMT, BCBSNM, BCBSOK) route provider self-service through Availity Essentials, which independently bars bots.

**Position: not permitted; account disablement is the stated consequence.**

### Medicare / CMS

CMS's published guidance on proper use of CMS systems states that use of scripts or automation tools to conduct person searches or to complete applications and submit enrollments on CMS websites is not allowed, that users conducting automated activities may have their CMS Portal accounts disabled immediately and permanently, and that this restriction **does not apply to scripted interactions with public-facing APIs maintained by CMS** ([CMS Agent/Broker FAQ](https://www.agentbrokerfaq.cms.gov/s/article/What-are-proper-uses-of-CMS-systems-that-agents-and-brokers-are-required-to-abide-by-when-accessing-HealthCare-gov-the-CMS-Enterprise-Portal-and-the-Direct-Enrollment-Pathways)). The same guidance prohibits credential sharing: only the person who created a CMS Portal account may use its credentials.

**Position: scripted access to CMS web portals is not permitted; scripted access to CMS public APIs is expressly permitted.**

### Availity (front door for Aetna and much of BCBS)

> "eliminate bot access to Availity Essentials, our provider portal"
>
> — <https://www.availity.com/blog/why-apis-are-better-than-bots/> (published 2022-04-01)

Availity's sanctioned alternative is RESTful API connections. Note that the general `availity.com` terms of use cover the marketing site and contain no scraping clause; the operative restriction is the Availity Essentials Organization Access Agreement plus the published bot policy above.

**Position: bots are not permitted on the portal; API is the sanctioned channel.**

---

## Consolidated answer to the ticket's sub-questions

- **Is there an official sandbox with a real HTML portal a browser agent can drive?** Only Blue Button 2.0, and only for a login/consent screen. Everything else is API-only or is a real production portal requiring a real provider identity.
- **What does access cost?** Every sandbox found is free. Cost is not the blocker; identity and time are.
- **What requires a signed agreement, an NPI, or a provider credential we will not have?** HETS (signed Trading Partner Agreement + submitter ID + coordinated testing), all state Medicaid portals (NPI/MMIS + certified ETIN, or trading-partner certification), Availity Essentials (org NPI + Tax ID), Office Ally (all billing NPIs + per-payer EDI enrolment/TPAs), UnitedHealthcare Provider Portal (TIN + NPI), Waystar (partner/customer relationship), DPC (assignment to a provider organisation by CMS).
- **May a public repository demonstrate against any of these?** Only against the API sandboxes, and even there Blue Button 2.0 forbids embedding developer credentials in open source projects. No public repository can honestly demonstrate authorised browser automation against any real payer portal.
- **Anything reachable in one week?** The API-only sandboxes (Availity Demo, BCDA, AB2D, Blue Button 2.0) are reachable in minutes. **None of them demonstrates browser computer-use over claim status and EOB/denial-PDF retrieval.**

---

## Downstream decision

Build the **mock payer portal**. It is the only option that satisfies all three of: authorised automation, a genuine browser surface with claim search and PDF download, and a one-week budget. It also keeps the public repo clean of any credential or terms-of-service risk.

Worth keeping in the design: model the mock portal on the *shape* of the real ones (login, claim search by member ID and date of service, a claim-detail page with a denial reason code, and a downloadable EOB PDF) so the agent logic transfers if a sanctioned API or a partner-granted portal becomes available later. If a real integration is ever needed, the sanctioned path every payer names is the **API**, not the browser — Availity's API marketplace, Optum's Medical Network APIs, or CMS's public APIs.

---

## Source verification notes

Most quotes above were retrieved by direct fetch of the cited URL. The following were extracted via search-engine retrieval of the cited page because the origin returned HTTP 403 or a JS-only shell to direct fetch, and should be spot-checked in a browser before being quoted externally:

- Aetna `legal-notices/disclaimer.html` (403 on direct fetch)
- UHCprovider `provider-portal-authentication.html` bots statement (302 redirect on direct fetch)
- CMS Agent/Broker FAQ scripts-and-automation policy (JS-rendered page)
- Blue Cross NC `enroll` terms of service (HTTP 406 on direct fetch)

Directly fetched and confirmed: UnitedHealth Group terms of use, Blue Shield of California Provider Connection, Availity bots blog post, Availity getting-started guide, Blue Button 2.0 sandbox guide and terms, Optum sandbox account docs, `sandbox.bluebutton.cms.gov/robots.txt`.
