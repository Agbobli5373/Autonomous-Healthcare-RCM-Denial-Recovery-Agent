/**
 * The reducer, which is the only place in this console holding real logic.
 *
 * Everything else renders what the server sent. This folds a stream of events
 * into a queue, and the properties worth pinning are that it never invents a
 * cell state and that a rule-closed claim leaves the ranked list entirely.
 */

import { applyEvent, partition, type Claim, type StreamMessage } from "../src/claims";

const CELLS = {
  portal: "done",
  analysis: "done",
  emr: "pending",
  appeal: "pending",
  report: "pending",
} as const;

function determination(claimId: string, action: string, guardrail: string | null = null): StreamMessage {
  return {
    type: "event",
    run_id: "2026-01-01T00-00-00Z",
    seq: 1,
    kind: "determination",
    claim_id: claimId,
    detail: {
      action,
      guardrail,
      priority: guardrail
        ? null
        : { amount_at_stake: "1250.00", likelihood: 0.45, expected_recovery: "562.50" },
    },
    derived: { cells: { ...CELLS }, action },
  };
}

function fold(messages: StreamMessage[]): Claim[] {
  let claims = new Map<string, Claim>();
  for (const message of messages) {
    claims = applyEvent(claims, message);
  }
  return [...claims.values()];
}

describe("folding events into a queue", () => {
  it("takes the cell state it was given rather than working one out", () => {
    const [claim] = fold([determination("CLM-1", "appeal")]);

    expect(claim?.cells).toEqual(CELLS);
  });

  it("ignores messages that belong to no claim", () => {
    const runLevel: StreamMessage = {
      type: "event",
      run_id: "r",
      kind: "tool_call",
      claim_id: null,
      derived: { cells: null, action: null },
    };

    expect(fold([runLevel])).toHaveLength(0);
  });

  it("ignores the end-of-replay marker", () => {
    expect(fold([{ type: "replayed" }])).toHaveLength(0);
  });

  it("lets a later event overwrite an earlier one for the same claim", () => {
    const claims = fold([determination("CLM-1", "appeal"), determination("CLM-1", "rebill")]);

    expect(claims).toHaveLength(1);
    expect(claims[0]?.action).toBe("rebill");
  });
});

describe("splitting the queue", () => {
  it("keeps a rule-closed claim out of the ranked list entirely", () => {
    const { ranked, ruled } = partition(
      fold([
        determination("CLM-1", "appeal"),
        determination("CLM-2", "close", "unappealable-remark:MA130"),
      ]),
    );

    expect(ranked.map((c) => c.claimId)).toEqual(["CLM-1"]);
    expect(ruled.map((c) => c.claimId)).toEqual(["CLM-2"]);
  });

  it("carries no Priority on a rule-closed claim, so there is no score to show", () => {
    const { ruled } = partition(fold([determination("CLM-2", "close", "no-denial")]));

    expect(ruled[0]?.priority).toBeNull();
  });

  it("ranks by what is expected back, largest first", () => {
    const small = determination("CLM-SMALL", "appeal");
    small.detail = {
      ...small.detail,
      priority: { amount_at_stake: "100.00", likelihood: 0.4, expected_recovery: "40.00" },
    };

    const { ranked } = partition(fold([small, determination("CLM-BIG", "appeal")]));

    expect(ranked.map((c) => c.claimId)).toEqual(["CLM-BIG", "CLM-SMALL"]);
  });
});
