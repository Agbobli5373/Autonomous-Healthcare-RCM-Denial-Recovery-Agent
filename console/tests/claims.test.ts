/**
 * The reducer, which is the only place in this console holding real logic.
 *
 * Everything else renders what the server sent. The properties worth pinning are
 * that it never invents a cell state, never decides whether a rule closed a
 * claim, and that a rule-closed claim leaves the ranked list entirely.
 */

import { applyEvent, partition, type QueueEntry, type StreamMessage } from "../src/claims";
import { CELLS, determination } from "./fixtures";

function fold(messages: StreamMessage[]): QueueEntry[] {
  let claims = new Map<string, QueueEntry>();
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
      ts: "2026-01-01T00:00:00+00:00",
      phase: "setup",
      kind: "tool_call",
      tool: "provision_sandbox",
      claim_id: null,
      outcome: null,
      screenshot: null,
      detail: {},
      derived: {
        cells: null,
        action: null,
        guardrailed: false,
        determination: null,
        determination_digest: null,
        claim: null,
      },
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

  it("takes the latest event wholesale, because each one is complete", () => {
    // The server carries a claim's whole state on every event, so a later one
    // never has less than an earlier one. This is the contract that makes
    // wholesale replacement safe; `test_console_replay.py` pins the other side.
    const determined = determination("CLM-1", "appeal");
    const laterInSameRun = {
      ...determined,
      seq: 9,
      kind: "phase_end",
    };

    const [claim] = fold([determined, laterInSameRun]);

    expect(claim?.action).toBe("appeal");
    expect(claim?.determination?.priority).not.toBeNull();
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

describe("a claim worked by more than one run", () => {
  it("leaves the rule section when a later run determined otherwise", () => {
    // The bug this pins: folding `guardrailed` with `||` made it monotonic, so a
    // claim a rule closed once could never leave - it sat under "Closed by rule",
    // labelled with the old rule, showing an appeal and a live Priority.
    const closed = determination("CLM-1", "close", { guardrail: "unappealable-remark:MA130" });
    const reworked = { ...determination("CLM-1", "appeal"), run_id: "2026-02-02T00-00-00Z" };

    const { ranked, ruled } = partition(fold([closed, reworked]));

    expect(ruled).toHaveLength(0);
    expect(ranked.map((c) => c.claimId)).toEqual(["CLM-1"]);
    expect(ranked[0]?.determination?.guardrail).toBeNull();
  });

  it("never mixes one run's Determination with another run's phases", () => {
    // Field-by-field merging attributed a Determination to a run that never
    // made one: the Action and Priority from the older run, the run label and
    // the phases from the newer.
    const determined = determination("CLM-1", "rebill");
    const laterRunTouchesIt = {
      ...determination("CLM-1", null, { priority: null }),
      run_id: "2026-02-02T00-00-00Z",
    };

    const [claim] = fold([determined, laterRunTouchesIt]);

    expect(claim?.runId).toBe("2026-02-02T00-00-00Z");
    expect(claim?.action).toBeNull();
    expect(claim?.determination).toBeNull();
  });
});
