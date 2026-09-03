# A Review is a second record, bound by digest

A human approves or rejects a Determination. The Determination is **not** touched: the
verdict is a separate record in a separate store, and it names the Determination it was
given for by a SHA-256 digest of the exact bytes the run wrote.

## Why not a status on the Determination

A Determination is a judgement made at a moment, and the project already treats it that
way — frozen, written once to `claims/<id>.json`. Adding `status: approved` would make
the artifact ambiguous: is `action: appeal` what the agent judged, or what survived
review? Two actors made two decisions, so there are two records. It also keeps the
run directory final, which is a designed property rather than an accident — `run.json`
carries a terminal status and the reliability measurement reads those summaries, so a
verdict arriving hours later must not reach back into a run that has closed. Reviews
therefore live in `reviews/`, outside `runs/`, keyed by claim and append-only.

## Why the digest, and why it is the whole point

Keyed on the claim alone, yesterday's `approved` would sit over a Determination that a
re-run had replaced. Whatever acted on it would file an appeal a human approved for a
reading that no longer exists — a void appeal on a patient's claim, reached by ordinary
bookkeeping rather than by anything a Guardrail inspects. The digest makes that failure
impossible to reach by accident: a verdict authorises exactly one reading, and anything
holding one has to ask.

The consequence is that the digest must be recomputable by anyone holding
`claims/<id>.json`. That forces two things which look incidental and are not. The
serialisation is written once, in `claim_json`, and both the writer and the digest call
it — written twice, the two would be joined by nothing but coincidence, and the digest
would go on matching itself while quietly ceasing to describe the file. And artifacts
are written with `newline=""`, because the default translated newlines to the host's:
a run on Windows wrote CRLF while the digest was taken over the LF form, so the one
claim the digest makes was false on the machine that wrote it.

## Where the check lives

At the seam, in Python, once. The write path refuses a mismatched digest before it
looks at anything else — a stale page can be wrong about the rest too, and answering it
with "a rejection must carry a reason" sends the Reviewer to fix the wrong thing. The
read path marks each standing verdict with whether it still `stands`, rather than
leaving the browser to compare digests: the same rule implemented in a second language
is a rule with two chances to be wrong, and the next consumer of that endpoint would
inherit the stale verdict in silence.

## What this does not do

Nothing acts on a Review. Filing an approved appeal is a separate effort, out of scope
for the console, and the screen says so plainly — a Reviewer who clicks Approve and
expects an agent to move has been misled by the button.
