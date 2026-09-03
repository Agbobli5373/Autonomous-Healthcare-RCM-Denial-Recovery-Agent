/** Stream messages shaped the way the server actually sends them. */

import type { EventMessage, Priority, Claim } from "../src/claims";

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

/** A rationale the length a live model actually writes. */
export const RATIONALE =
  "Cascade denied the E0601 CPAP device line CO-197 with remark N706 (missing " +
  "documentation), saying no prior authorization was on file for the date of " +
  "service. If an authorization was in fact obtained and covers that DOS and " +
  "HCPCS code, the correct route is an appeal with the auth number attached.";

/** Ten items, because that is what an appeal actually asks for. */
export const EVIDENCE = Array.from({ length: 10 }, (_, i) => `Evidence item ${i + 1}`);

export function claimRecord(claimId: string): Claim {
  return {
    claim_id: claimId,
    payer: "Cascade Health Plan",
    patient_id: "PAT-40219",
    date_of_service: "2026-03-14",
    service_lines: [
      {
        line_number: 1,
        procedure_code: "E1390",
        charge: "450.00",
        adjustments: [
          { group: "CO", reason_code: "45", amount: "92.50", remark_codes: [] },
        ],
      },
      {
        line_number: 2,
        procedure_code: "E0601",
        charge: "1250.00",
        adjustments: [
          { group: "CO", reason_code: "197", amount: "1250.00", remark_codes: ["N706"] },
        ],
      },
    ],
    governing: { group: "CO", reason_code: "197", remark_codes: ["N706"] },
  };
}

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
    ts: "2026-01-01T00:00:00+00:00",
    phase: "analysis",
    kind: "determination",
    tool: null,
    claim_id: claimId,
    outcome: "ok",
    screenshot: null,
    detail: {},
    derived: {
      cells: { ...CELLS },
      action,
      guardrailed: guardrail !== null,
      determination:
        action === null
          ? null
          : {
              claim_id: claimId,
              action,
              rationale: RATIONALE,
              evidence_required: guardrail ? [] : EVIDENCE,
              guardrail,
              priority:
                options.priority !== undefined ? options.priority : guardrail ? null : SCORED,
            },
      claim: claimRecord(claimId),
    },
  };
}
