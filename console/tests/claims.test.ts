/**
 * The reducer, which is the only place in this console holding real logic.
 *
 * Everything else renders what the server sent. The properties worth pinning are
 * that it never invents a cell state, never decides whether a rule closed a
 * claim, and that a rule-closed claim leaves the ranked list entirely.
 */

import { applyEvent, partition, type Claim, type StreamMessage } from "../src/claims";
import { CELLS, determination } from "./fixtures";

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

  it("takes the server's word for whether a rule closed the claim", () => {
    const [claim] = fold([determination("CLM-2", "close", { guardrail: "no-denial" })]);

    expect(claim?.guardrailed).toBe(true);
  });

  it("ignores messages that belong to no claim", () => {
    const runLevel: StreamMessage = {
      type: "event",
      run_id: "r",
      seq: 0,
      kind: "tool_call",
      claim_id: null,
      derived: { cells: null, action: null, guardrail: null, guardrailed: false, priority: null },
    };

    expect(fold([runLevel])).toHaveLength(0);
  });

  it("ignores the messages that are not events", () => {
    expect(fold([{ type: "replayed" }, { type: "hello", phases: [] }])).toHaveLength(0);
  });

  it("lets a later event overwrite an earlier one for the same claim", () => {
    const claims = fold([determination("CLM-1", "appeal"), determination("CLM-1", "rebill")]);

    expect(claims).toHaveLength(1);
    expect(claims[0]?.action).toBe("rebill");
  });

  it("keeps what earlier events said when a later one carries nothing new", () => {
    const later: StreamMessage = {
      type: "event",
      run_id: "2026-01-01T00-00-00Z",
      seq: 9,
      kind: "phase_end",
      claim_id: "CLM-1",
      derived: { cells: null, action: null, guardrail: null, guardrailed: false, priority: null },
    };

    const [claim] = fold([determination("CLM-1", "appeal"), later]);

    expect(claim?.action).toBe("appeal");
    expect(claim?.priority).not.toBeNull();
  });
});

describe("splitting the queue", () => {
  it("keeps a rule-closed claim out of the ranked list entirely", () => {
    const { ranked, ruled } = partition(
      fold([
        determination("CLM-1", "appeal"),
        determination("CLM-2", "close", { guardrail: "unappealable-remark:MA130" }),
      ]),
    );

    expect(ranked.map((c) => c.claimId)).toEqual(["CLM-1"]);
    expect(ruled.map((c) => c.claimId)).toEqual(["CLM-2"]);
  });

  it("sections by what the server decided, not by whether a score is present", () => {
    // A rule-closed claim should never carry a Priority. If one ever did, it
    // still belongs in the ruled section - the section follows the rule, not
    // the presence of a number.
    const odd = determination("CLM-2", "close", {
      guardrail: "no-denial",
      priority: { amount_at_stake: "80.00", likelihood: 0.1, expected_recovery: "8.00" },
    });

    const { ranked, ruled } = partition(fold([odd]));

    expect(ruled.map((c) => c.claimId)).toEqual(["CLM-2"]);
    expect(ranked).toHaveLength(0);
  });

  it("ranks by what is expected back, largest first", () => {
    const small = determination("CLM-SMALL", "appeal", {
      priority: { amount_at_stake: "100.00", likelihood: 0.4, expected_recovery: "40.00" },
    });

    const { ranked } = partition(fold([small, determination("CLM-BIG", "appeal")]));

    expect(ranked.map((c) => c.claimId)).toEqual(["CLM-BIG", "CLM-SMALL"]);
  });

  it("sorts a claim with no score yet below one that has been weighed", () => {
    const midRun = determination("CLM-MID", null, { priority: null });

    const { ranked } = partition(fold([midRun, determination("CLM-DONE", "appeal")]));

    expect(ranked.map((c) => c.claimId)).toEqual(["CLM-DONE", "CLM-MID"]);
  });
});
