/**
 * What arrives over the socket, and the queue it accumulates into.
 *
 * The line this file does not cross: it never works out a cell state and never
 * decides whether a rule fired. Both arrive already decided, because the rules
 * behind them live in Python and a second copy here would be a second copy in a
 * second language. What it does do is order and group by fields the server
 * already sent - which is presentation, not judgement.
 */

export const PHASES = ["portal", "analysis", "emr", "appeal", "report"] as const;
export type Phase = (typeof PHASES)[number];

export type CellState = "pending" | "running" | "done" | "na" | "failed";

export interface Priority {
  amount_at_stake: string;
  likelihood: number;
  expected_recovery: string;
}

export interface StreamMessage {
  type: "event" | "replayed";
  run_id?: string;
  seq?: number;
  kind?: string;
  claim_id?: string | null;
  detail?: Record<string, unknown>;
  derived?: { cells: Record<Phase, CellState> | null; action: string | null };
}

export interface Claim {
  claimId: string;
  runId: string;
  action: string | null;
  guardrail: string | null;
  priority: Priority | null;
  cells: Record<Phase, CellState> | null;
}

/**
 * Fold one event into the queue.
 *
 * Events arrive in the order they happened, so later ones simply overwrite what
 * earlier ones said. A claim worked twice belongs to the run that worked it
 * last, which is the one an analyst would be looking at.
 */
export function applyEvent(claims: Map<string, Claim>, message: StreamMessage): Map<string, Claim> {
  const claimId = message.claim_id;
  if (message.type !== "event" || !claimId) {
    return claims;
  }

  const existing = claims.get(claimId);
  const next: Claim = existing
    ? { ...existing }
    : {
        claimId,
        runId: message.run_id ?? "",
        action: null,
        guardrail: null,
        priority: null,
        cells: null,
      };

  next.runId = message.run_id ?? next.runId;
  if (message.derived?.cells) {
    next.cells = message.derived.cells;
  }
  if (message.derived?.action) {
    next.action = message.derived.action;
  }
  if (message.kind === "determination" && message.detail) {
    next.guardrail = (message.detail.guardrail as string | null) ?? null;
    next.priority = (message.detail.priority as Priority | null) ?? null;
  }

  const updated = new Map(claims);
  updated.set(claimId, next);
  return updated;
}

/**
 * Split the queue the way the analyst reads it.
 *
 * A claim a rule closed is not low-priority work; it is not work. It carries no
 * Priority at all - `null`, not zero, because nothing was weighed - so it cannot
 * be ranked among things that were, and sorting it last would say it was merely
 * cheap. It gets its own section instead.
 */
export function partition(claims: Iterable<Claim>): { ranked: Claim[]; ruled: Claim[] } {
  const ranked: Claim[] = [];
  const ruled: Claim[] = [];
  for (const claim of claims) {
    (claim.guardrail ? ruled : ranked).push(claim);
  }
  ranked.sort((a, b) => recovery(b) - recovery(a));
  ruled.sort((a, b) => a.claimId.localeCompare(b.claimId));
  return { ranked, ruled };
}

function recovery(claim: Claim): number {
  return claim.priority ? Number(claim.priority.expected_recovery) : 0;
}
