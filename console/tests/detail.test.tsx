/**
 * The claim detail: a comparison, not a conclusion.
 *
 * The properties worth pinning are the ones a layout quietly breaks. Both halves
 * have to survive a rationale of the length a live model writes and an evidence
 * list of the length an appeal asks for - the reason evidence is a band beneath
 * the split rather than a third column. And a rule-closed claim has to read as
 * the absence of a judgement, never as a low score.
 */

import { render, screen } from "@testing-library/react";

import { Detail } from "../src/Detail";
import type { QueueEntry } from "../src/claims";
import { EVIDENCE, RATIONALE, claimRecord } from "./fixtures";

function claim(overrides: Partial<QueueEntry> = {}): QueueEntry {
  return {
    claimId: "CLM-2026-0001",
    runId: "2026-01-01T00-00-00Z",
    action: "appeal",
    guardrailed: false,
    determination: {
      claim_id: "CLM-2026-0001",
      action: "appeal",
      rationale: RATIONALE,
      evidence_required: EVIDENCE,
      guardrail: null,
      priority: { amount_at_stake: "1250.00", likelihood: 0.45, expected_recovery: "562.50" },
    },
    claim: claimRecord("CLM-2026-0001"),
    cells: null,
    ...overrides,
  };
}

describe("the claim detail", () => {
  it("shows what the payer refused beside what the agent determined", () => {
    render(<Detail entry={claim()} onClose={() => {}} />);

    expect(screen.getByText(/what the payer said/i)).toBeDefined();
    expect(screen.getByText(/what the agent determined/i)).toBeDefined();
    // Twice each: once as a chip in the fact bar, where a biller reads the
    // governing codes first, and once in the line it actually sits on.
    expect(screen.getAllByText("CO-197")).toHaveLength(2);
    expect(screen.getAllByText("N706")).toHaveLength(2);
    expect(screen.getByText("Appeal")).toBeDefined();
  });

  it("names the payer, the patient and the date of service", () => {
    render(<Detail entry={claim()} onClose={() => {}} />);

    expect(screen.getByText("Cascade Health Plan")).toBeDefined();
    expect(screen.getByText("PAT-40219")).toBeDefined();
    expect(screen.getByText("2026-03-14")).toBeDefined();
  });

  it("holds a full rationale and a ten-item evidence list", () => {
    render(<Detail entry={claim()} onClose={() => {}} />);

    expect(screen.getByText(RATIONALE)).toBeDefined();
    expect(screen.getByText(/10 items/)).toBeDefined();
    expect(document.querySelectorAll(".evlist li")).toHaveLength(10);
  });

  it("keeps evidence out of the split, so neither half starves", () => {
    render(<Detail entry={claim()} onClose={() => {}} />);

    // A third column is what the prototype ruled out: at this size the payer's
    // lines and the rationale cannot both survive it.
    expect(document.querySelector(".split .evlist")).toBeNull();
    expect(document.querySelector(".ev .evlist")).not.toBeNull();
  });

  it("reads a rule-closed claim as the absence of a judgement", () => {
    const ruled = claim({
      action: "close",
      guardrailed: true,
      determination: {
        claim_id: "CLM-2026-0002",
        action: "close",
        rationale: "Remark MA130 carries no appeal rights.",
        evidence_required: [],
        guardrail: "unappealable-remark:MA130",
        priority: null,
      },
    });

    render(<Detail entry={ruled} onClose={() => {}} />);

    expect(screen.getByText(/closed by rule/i)).toBeDefined();
    expect(screen.getByText(/nothing was weighed/i)).toBeDefined();
    expect(screen.getByText(/absence of a judgement/i)).toBeDefined();
  });

});

describe("what the remittance did not say", () => {
  it("shows no charge when the document never stated one", () => {
    // `null`, not `"0"`: whether a placeholder zero means "absent" is a fact
    // about a remittance, decided by the server. The client is simply told.

    const noCharge = claim();
    noCharge.claim = {
      ...claimRecord("CLM-2026-0001"),
      service_lines: claimRecord("CLM-2026-0001").service_lines.map((line) => ({
        ...line,
        charge: null,
      })),
    };

    render(<Detail entry={noCharge} onClose={() => {}} />);

    expect(screen.queryByText(/charge/)).toBeNull();
  });

  it("shows a charge when one is actually known", () => {
    render(<Detail entry={claim()} onClose={() => {}} />);

    expect(screen.getByText(/charge 1250\.00/)).toBeDefined();
  });
});

describe("a close a model judged, not a rule", () => {
  function judgedClose() {
    // #35: a close carries no Priority, because a claim being abandoned has
    // nothing to recover and nothing to rank. It is NOT guardrailed - a model
    // decided it.
    return claim({
      action: "close",
      guardrailed: false,
      determination: {
        claim_id: "CLM-2026-0009",
        action: "close",
        rationale: "Nothing here is recoverable; the balance is a contractual write-off.",
        evidence_required: [],
        guardrail: null,
        priority: null,
      },
    });
  }

  it("does not claim a rule decided it", () => {
    // The bug: the copy was gated on the absent Priority rather than on the
    // rule, so a close a model judged said "A rule decided this" — the screen
    // asserting something untrue about how the decision was reached.
    render(<Detail entry={judgedClose()} onClose={() => {}} />);

    expect(screen.queryByText(/a rule decided this/i)).toBeNull();
    expect(screen.queryByText(/closed by rule/i)).toBeNull();
  });

  it("says why there is no score, truthfully", () => {
    render(<Detail entry={judgedClose()} onClose={() => {}} />);

    expect(screen.getByText(/nothing to recover and nothing to rank/i)).toBeDefined();
    expect(document.querySelector(".score")).toBeNull();
  });
});

describe("a line the payer paid", () => {
  it("still appears, rather than vanishing from what the payer said", () => {
    // CONTEXT.md: "a single Claim routinely mixes a paid line, a written-off
    // line and a denied line". Mapping over adjustments dropped the paid one
    // entirely, silently removing part of the payer's own statement.
    const withPaidLine = claim();
    withPaidLine.claim = {
      ...claimRecord("CLM-2026-0001"),
      service_lines: [
        ...claimRecord("CLM-2026-0001").service_lines,
        { line_number: 3, procedure_code: "A4253", charge: "78.00", adjustments: [] },
      ],
    };

    render(<Detail entry={withPaidLine} onClose={() => {}} />);

    expect(screen.getByText("A4253")).toBeDefined();
    expect(screen.getByText(/no adjustment/i)).toBeDefined();
  });
});
