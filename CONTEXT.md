# Denial Recovery

The language of working denied medical claims: reading a payer's remittance, deciding what can be recovered and how, and assembling the evidence to recover it.

This glossary is deliberately narrow. It covers US payer-side revenue cycle management as the agent encounters it, not clinical care and not the payer's internal adjudication.

## The remittance

**Remittance**:
A payer's statement of what it paid, denied and adjusted for a set of claims. The electronic form is the 835.
_Avoid_: EOB, ERA, remit

**EOB**:
The human-readable explanation of benefits, as a document a person reads. The agent downloads EOBs; it reasons over the Remittance data inside them.
_Avoid_: using interchangeably with Remittance — one is a document, the other is the data

**Claim**:
A provider's request for payment from a payer for services delivered to a patient on a date of service.

**Service Line**:
One billed service within a Claim, carrying its own charge and its own Adjustments. Outcomes differ per line — a single Claim routinely mixes a paid line, a written-off line and a denied line.
_Avoid_: line item, charge

**Adjustment**:
One reason a Service Line was paid at less than its charge, always a triple of Group Code, Reason Code and zero or more Remark Codes, with an amount.
_Avoid_: adjudication, reduction

**Group Code**:
Who bears the adjusted amount: `CO` provider, `PR` patient, `OA` other, `PI` payer-initiated. It determines liability and therefore whether anything is appealable at all.

**Reason Code**:
The CARC identifying why an amount was adjusted. Deliberately underspecified — several require a Remark Code to be meaningful.
_Avoid_: CARC alone as a claim's "denial code"; a Reason Code without its Group Code is ambiguous

**Remark Code**:
The RARC qualifying a Reason Code. Carries the detail the CARC omits, including whether appeal rights exist.
_Avoid_: RARC alone as an identifier

## Outcomes

**Denial**:
An adjudicated refusal to pay a Service Line. It appears on a Remittance and carries appeal rights.
_Avoid_: rejection — a different thing entirely

**Rejection**:
A claim refused before adjudication, at the clearinghouse or the payer's front door. It never produces a Remittance and has no appeal rights. **Out of scope** for this project: nothing in the remittance path can carry one, so it exists here only to keep the word from being misused for a Denial.
_Avoid_: using for a Denial

**Unprocessable**:
A claim returned by Medicare as incomplete or invalid. It arrives on a Remittance and looks like a Denial, but carries no appeal rights. The trap the agent must not fall into.

**Write-off**:
A contractual adjustment where the provider accepts less than charged under its payer agreement. Standing alone it means the Claim was paid correctly.
_Avoid_: treating as a Denial

**Patient Responsibility**:
An amount the patient owes — deductible, coinsurance or copay. Never appealable, because nothing was refused.
_Avoid_: treating as a Denial

## The decision

**Determination**:
The agent's conclusion about one Denial: an Action, the rationale for it, and the evidence the Action requires. The primary output of analysis.
_Avoid_: recommendation, classification, prediction

**Action**:
What a Determination calls for. Exactly one of: **appeal**, **corrected claim**, **rebill**, **patient bill**, **close**. Most denial volume is correction work rather than appeal work, so "appeal" is one option among five, not the default.
_Avoid_: recoverable / non-recoverable as a binary

**Guardrail**:
A rule that fixes an Action without reference to any score, because the law or the contract leaves no judgement to exercise. Unprocessable, Patient Responsibility and a lone Write-off are all guardrailed away from appeal.
_Avoid_: threshold, confidence cutoff — a Guardrail is not a score

**Priority**:
How worth working a Determination is relative to others, from the amount at stake and the likelihood of recovery. Ranks a worklist. It never decides an Action.
_Avoid_: recoverability score, confidence

**Review**:
A person's verdict on one Determination — approved or rejected, who decided, when, and on a rejection why. A second record rather than a change to the Determination: two actors made two decisions, and mutating the first would leave `action: appeal` ambiguous between what the agent judged and what survived review. A Review names the Determination it was given for by digest, so a re-run that changes the reading leaves the verdict over what its Reviewer actually read instead of authorising a reading nobody saw.
_Avoid_: approval — the glossary already gives *approval* to Authorization, and a payer's advance approval for a service is a different thing entirely; sign-off, status

**Verdict**:
What a Review carries: **approved** or **rejected**. Nothing else — a Determination a Guardrail closed is not put to a Reviewer at all, because a rule was never a judgement and asking for a verdict would invent a decision that does not exist.

**Counter-action**:
The Action a Reviewer would have chosen instead, recorded on a rejecting Review. Optional, and only on a rejection — there is no *instead* inside an agreement. It is not a Determination: the agent did not judge it, and recording it as one would put a human's opinion where the record of the agent's reasoning belongs.

**Reviewer**:
The person who gives a Verdict. Named on the Review; nothing yet verifies the name, so it is a signature rather than an identity.
_Avoid_: approver, user

## The evidence

**Authorization**:
A payer's advance approval for a service, with an authorization number, a validity date range and a scope of covered services. Lives in the practice-management system, not on the Claim. Proving that a valid Authorization covered the date of service is how a prior-authorization Denial is overturned.
_Avoid_: pre-auth, auth (in prose), referral — a referral is a different instrument

**Practice Record**:
What the practice-management system holds about one episode of care — the Patient's name, the date of service, the ordering provider, and the Authorization if there is one. The provider's view of the episode the Claim describes from the payer's side; the two are read as a pair, which is why the Patient's name lives here and the Claim carries only an id.
_Avoid_: chart (for the record itself — a chart is the screen it is shown on), encounter

**Supporting Document**:
Any other evidence attached to an Appeal — clinical notes, operative reports, proof of timely submission. Unlike an Authorization it has no fields the agent reasons over; it is attached, not compared.

**Appeal**:
A formal request that a payer reconsider a Denial.

**Appeal Package**:
The Appeal letter together with the Authorization or Supporting Documents it cites, assembled and ready to submit.

## The parties

**Payer**:
The insurer responsible for adjudicating and paying a Claim.
_Avoid_: insurer, carrier, plan

**Provider**:
The clinician or organisation that delivered the service and submitted the Claim.

**Patient**:
The person who received the service.
_Avoid_: member, beneficiary, subscriber — these name a person's relationship to a Payer, not to the Provider
