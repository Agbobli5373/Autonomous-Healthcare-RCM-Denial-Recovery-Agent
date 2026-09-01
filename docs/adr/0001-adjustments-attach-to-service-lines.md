# Adjustments attach to Service Lines, not to Claims

Real 835 remittances carry CAS segments per service line, and one claim routinely
mixes outcomes — a contractual write-off on one line alongside a prior-authorization
denial on another. We model Adjustments at Service Line grain rather than collapsing
one denial onto each Claim.

## Consequences

The domain's own guardrails depend on this grain. "A lone `CO-45` write-off means the
claim was paid correctly" is only expressible if the model can see what else sits on
the claim; flattened to claim level it is unstateable. Likewise a claim carrying both
patient responsibility and a genuine denial would otherwise have to pick one.

The cost is one extra layer of nesting for three demo claims, and slightly larger
synthetic fixtures. That is cheap against being wrong in a way a domain-literate
reviewer would notice immediately.

## Also decided here

The adjudication outcome carried in code is **two-valued** — denied or unprocessable —
not three. A front-end rejection never produces a remittance, so nothing in the data
path can carry one. `Rejection` remains defined in `CONTEXT.md` because the word is
load-bearing and routinely misused for a denial, but it is glossary vocabulary rather
than a state the type system can reach. Modelling a state nothing populates would be
its own kind of dishonesty.
