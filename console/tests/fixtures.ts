/** Stream messages shaped the way the server actually sends them. */

import type { EventMessage, Priority } from "../src/claims";

export const CELLS = {
  portal: "done",
  analysis: "done",
  emr: "pending",
  appeal: "pending",
  report: "pending",
} as const;

export const PHASES = ["portal", "analysis", "emr", "appeal", "report"];

const SCORED: Priority = {
  amount_at_stake: "1250.00",
  likelihood: 0.45,
  expected_recovery: "562.50",
};

export function determination(
  claimId: string,
  action: EventMessage["derived"]["action"],
  options: { guardrail?: string | null; priority?: Priority | null } = {},
): EventMessage {
  const guardrail = options.guardrail ?? null;
  return {
    type: "event",
    run_id: "2026-01-01T00-00-00Z",
    seq: 1,
    kind: "determination",
    claim_id: claimId,
    derived: {
      cells: { ...CELLS },
      action,
      guardrail,
      guardrailed: guardrail !== null,
      priority: options.priority !== undefined ? options.priority : guardrail ? null : SCORED,
    },
  };
}
