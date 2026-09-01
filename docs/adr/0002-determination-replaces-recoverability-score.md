# A Determination replaces the recoverable/non-recoverable score

FR-2 of the PRD asks the agent to "classify denial reasons into recoverable vs
non-recoverable categories" and score recovery probability. We are not building that.
The analysis output is a **Determination**: one of five Actions — appeal, corrected
claim, rebill, patient bill, close — plus its rationale and the evidence it requires.

## Why

Most denial volume in reality is correction work rather than appeal work. Coordination
of benefits is recovered by rebilling to the correct payer; a missing modifier is
recovered by a corrected claim. A recoverable/non-recoverable binary cannot express
the difference between "recoverable, by appealing" and "recoverable, by rebilling",
and it collapses two genuinely different pieces of work into one label.

The binary also invites a specific failure: an agent that always answers "recoverable"
scores well on a corpus that is mostly recoverable, while being useless. The five-way
Action has no such degenerate strategy.

## Guardrails are rules, not thresholds

Some determinations are fixed by law or contract and never reach judgement. Medicare
`MA130` unprocessable claims carry no appeal rights; `PR-1/2/3` are patient
responsibility and nothing was refused; a lone `CO-45` is a contractual write-off on a
correctly paid claim. These are **Guardrails** — hard rules that fix the Action before
any scoring happens. Expressing legal unappealability as a confidence threshold would
mean a sufficiently confident model could file a legally void appeal, which is worse
than failing.

## Scoring survives, in its proper place

A separate **Priority** figure — amount at stake against likelihood of recovery —
ranks a worklist, satisfying the billing-specialist user story about prioritising
high-value claims. It never decides an Action. Ranking and deciding are different
jobs and are kept apart deliberately.
