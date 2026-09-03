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

/** One adjustment on a service line: what the payer refused, and why. */
export interface Adjustment {
  group: string;
  reason_code: string;
  amount: string;
  remark_codes: string[];
}

export interface ServiceLine {
  line_number: number;
  procedure_code: string;
  /** `null` when the remittance never stated one - the server decides that. */
  charge: string | null;
  adjustments: Adjustment[];
}

/** The denial the Determination answers, named by the server. */
export interface GoverningDenial {
  group: string;
  reason_code: string;
  remark_codes: string[];
}

/** What the payer refused: the Claim itself, and the left half of the comparison. */
export interface Claim {
  claim_id: string;
  payer: string;
  patient_id: string;
  date_of_service: string;
  service_lines: ServiceLine[];
  // Which of these adjustments is *the* denial is a domain question - a
  // contractual write-off is not one, however large - so the server answers it.
  governing: GoverningDenial | null;
}

/** What the agent decided. The right half. */
export interface Determination {
  claim_id: string;
  action: Action;
  rationale: string;
  evidence_required: string[];
  guardrail: string | null;
  priority: Priority | null;
}

/** Everything the server worked out about a claim, so the client need not. */
export interface Derived {
  cells: Record<Phase, CellState> | null;
  action: Action | null;
  guardrailed: boolean;
  determination: Determination | null;
  claim: Claim | null;
}

export interface HelloMessage {
  type: "hello";
  phases: Phase[];
}

export interface EventMessage {
  type: "event";
  run_id: string;
  seq: number;
  ts: string;
  phase: string;
  kind: string;
  tool: string | null;
  claim_id: string | null;
  outcome: string | null;
  /** Named for the event's `seq`, so an image and its tool call share a key. */
  screenshot: string | null;
  /**
   * What the emitting tool recorded. Its shape is that tool's business, which is
   * why the queue reads `derived` instead - but the inspector shows what a run
   * actually said, so it reads this.
   */
  detail: Record<string, unknown>;
  derived: Derived;
}

export interface ReplayedMessage {
  type: "replayed";
}

/** Discriminated, so no field has to be defended with a fallback. */
export type StreamMessage = HelloMessage | EventMessage | ReplayedMessage;

/**
 * One row of the queue: a Claim, and everything the server worked out about it.
 *
 * Not a `Claim` - that word belongs to the thing in `CONTEXT.md`, which this
 * holds rather than is.
 */
export interface QueueEntry {
  claimId: string;
  runId: string;
  action: Action | null;
  guardrailed: boolean;
  determination: Determination | null;
  claim: Claim | null;
  cells: Record<Phase, CellState> | null;
  /**
   * This run's events for this claim, in the order they happened.
   *
   * Kept because the inspector shows what the run recorded rather than a
   * summary of it. Reset when a later run picks the claim up: mixing two runs'
   * events under one claim is the same mistake the derived fields refuse.
   */
  events: EventMessage[];
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
export function applyEvent(claims: Map<string, QueueEntry>, message: StreamMessage): Map<string, QueueEntry> {
  if (message.type !== "event" || message.claim_id === null) {
    return claims;
  }

  const previous = claims.get(message.claim_id);
  const sameRun = previous?.runId === message.run_id;

  const updated = new Map(claims);
  updated.set(message.claim_id, {
    claimId: message.claim_id,
    runId: message.run_id,
    action: message.derived.action,
    guardrailed: message.derived.guardrailed,
    determination: message.derived.determination,
    claim: message.derived.claim,
    cells: message.derived.cells,
    // The derived fields are replaced wholesale; the events accumulate. Both
    // are scoped to one run, for the same reason.
    events: sameRun && previous ? [...previous.events, message] : [message],
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
export function partition(claims: Iterable<QueueEntry>): { ranked: QueueEntry[]; ruled: QueueEntry[] } {
  const ranked: QueueEntry[] = [];
  const ruled: QueueEntry[] = [];
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
function expectedRecovery(claim: QueueEntry): number {
  const priority = claim.determination?.priority;
  return priority ? Number(priority.expected_recovery) : 0;
}
