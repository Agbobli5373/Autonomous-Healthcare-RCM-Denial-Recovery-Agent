/**
 * What arrives over the socket, and the queue it accumulates into.
 *
 * The line this file does not cross: it never works out a cell state, and it
 * never decides whether a claim was closed by a rule. Both arrive already
 * decided, because the rules behind them live in Python - `ClaimMatrix` for the
 * cells, `Determination.was_guardrailed` for the rule - and a second copy here
 * would be a second copy in a second language, untyped, in a project whose
 * central claim is that its rules live in one place.
 *
 * What it does do is order and group by fields the server already sent. That is
 * presentation, not judgement: the answer was decided elsewhere and this only
 * chooses where to put it on screen.
 */

export type Phase = string;

export type CellState = "pending" | "running" | "done" | "na" | "failed";

/** The five Actions from the glossary. `null` until a claim is determined. */
export type Action = "appeal" | "corrected_claim" | "rebill" | "patient_bill" | "close";

export interface Priority {
  amount_at_stake: string;
  likelihood: number;
  expected_recovery: string;
}

/** Everything the server worked out about a claim, so the client need not. */
export interface Derived {
  cells: Record<Phase, CellState> | null;
  action: Action | null;
  guardrail: string | null;
  guardrailed: boolean;
  priority: Priority | null;
}

export interface HelloMessage {
  type: "hello";
  phases: Phase[];
}

export interface EventMessage {
  type: "event";
  run_id: string;
  seq: number;
  kind: string;
  claim_id: string | null;
  derived: Derived;
}

export interface ReplayedMessage {
  type: "replayed";
}

/** Discriminated, so no field has to be defended with a fallback. */
export type StreamMessage = HelloMessage | EventMessage | ReplayedMessage;

export interface Claim {
  claimId: string;
  runId: string;
  action: Action | null;
  guardrail: string | null;
  guardrailed: boolean;
  priority: Priority | null;
  cells: Record<Phase, CellState> | null;
}

/**
 * Fold one event into the queue.
 *
 * Wholesale replacement, not a merge. Every event carries its claim's whole
 * state as of that event, so the latest one simply wins - and events arrive in
 * the order they happened, over a transport that preserves it.
 *
 * Merging field by field looked harmless and was not. Keeping an earlier value
 * when a later event carried none mixed two runs together: a Determination from
 * one run rendered against the phases and the run label of another, so the
 * console attributed a decision to a run that never made it. Worse, folding a
 * boolean with `||` made it monotonic - a claim rule-closed once could never
 * leave the rule section, however many times it was later worked and appealed.
 */
export function applyEvent(claims: Map<string, Claim>, message: StreamMessage): Map<string, Claim> {
  if (message.type !== "event" || message.claim_id === null) {
    return claims;
  }

  const updated = new Map(claims);
  updated.set(message.claim_id, {
    claimId: message.claim_id,
    runId: message.run_id,
    action: message.derived.action,
    guardrail: message.derived.guardrail,
    guardrailed: message.derived.guardrailed,
    priority: message.derived.priority,
    cells: message.derived.cells,
  });
  return updated;
}

/**
 * Split the queue the way the analyst reads it.
 *
 * A claim a rule closed is not low-priority work; it is not work. It carries no
 * Priority at all - `null`, not zero, because nothing was weighed - so it cannot
 * be ranked among things that were, and sorting it last would say it was merely
 * cheap. It gets its own section instead.
 *
 * `guardrailed` is read, not computed. The server decided it.
 */
export function partition(claims: Iterable<Claim>): { ranked: Claim[]; ruled: Claim[] } {
  const ranked: Claim[] = [];
  const ruled: Claim[] = [];
  for (const claim of claims) {
    (claim.guardrailed ? ruled : ranked).push(claim);
  }
  ranked.sort((a, b) => expectedRecovery(b) - expectedRecovery(a));
  ruled.sort((a, b) => a.claimId.localeCompare(b.claimId));
  return { ranked, ruled };
}

/**
 * The ranking key: what Priority says is expected back.
 *
 * A claim with no Priority sorts last rather than first. It should not reach
 * here at all - the only determinations without one are the rule-closed claims,
 * which are in the other list - but a claim mid-run has no Priority yet either,
 * and it belongs below the ones that have been weighed.
 */
function expectedRecovery(claim: Claim): number {
  return claim.priority ? Number(claim.priority.expected_recovery) : 0;
}
