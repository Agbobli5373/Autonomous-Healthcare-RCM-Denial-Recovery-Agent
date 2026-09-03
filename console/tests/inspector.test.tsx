/**
 * The four layers, and the absences that are themselves the answer.
 *
 * Everything here is read from what a run recorded. The tests that matter most
 * are the ones where a layer has nothing to show: on a rule-closed claim, "no
 * model was asked" and "no exchange" are not gaps in the record, they are the
 * record - and a panel that rendered empty would look like a bug instead.
 */

import { fireEvent, render, screen } from "@testing-library/react";

import { Inspector } from "../src/Inspector";
import type { EventMessage, QueueEntry } from "../src/claims";
import { claimRecord } from "./fixtures";

const FACTS =
  "Claim CLM-2026-0001, Cascade Health Plan.\nTotal refused: 1250.00.\n\n" +
  "  line 2 · E0601 · CO-197 · remark N706 · 1250.00";

function event(overrides: Partial<EventMessage>): EventMessage {
  return {
    type: "event",
    run_id: "2026-01-01T00-00-00Z",
    seq: 1,
    ts: "2026-01-01T00:00:00+00:00",
    phase: "analysis",
    kind: "phase_start",
    tool: null,
    claim_id: "CLM-2026-0001",
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
    ...overrides,
  };
}

function entry(events: EventMessage[]): QueueEntry {
  return {
    claimId: "CLM-2026-0001",
    runId: "2026-01-01T00-00-00Z",
    action: "appeal",
    guardrailed: false,
    determination: null,
    determinationDigest: null,
    claim: claimRecord("CLM-2026-0001"),
    cells: null,
    events,
  };
}

const JUDGED = [
  event({
    seq: 4,
    kind: "guardrails",
    detail: {
      evaluated: [
        { rule: "unappealable-remark", fired: false },
        { rule: "nothing-was-refused", fired: false },
        { rule: "non-appealable-code", fired: false },
      ],
    },
  }),
  event({
    seq: 5,
    kind: "tool_call",
    tool: "judge_denial",
    detail: {
      denial: "CO-197",
      model: "claude-opus-5",
      options: ["appeal", "corrected_claim", "rebill", "patient_bill", "close"],
      facts: FACTS,
    },
  }),
  event({
    seq: 6,
    kind: "tool_result",
    tool: "judge_denial",
    outcome: "ok",
    detail: { denial: "CO-197", returned: { action: "appeal", rationale: "the auth covered it" } },
  }),
];

const RULE_CLOSED = [
  event({
    seq: 4,
    kind: "guardrails",
    detail: {
      evaluated: [
        {
          rule: "unappealable-remark",
          fired: true,
          guardrail: "unappealable-remark:MA130",
        },
      ],
    },
  }),
];

function open(events: EventMessage[], runEvents: EventMessage[] = []) {
  render(<Inspector entry={entry(events)} runEvents={runEvents} onClose={() => {}} />);
}

function tab(name: RegExp) {
  fireEvent.click(screen.getByRole("tab", { name }));
}

describe("what the agent was not allowed to choose", () => {
  it("shows every Action, and that none was removed", () => {
    open(JUDGED);

    for (const action of ["appeal", "corrected_claim", "rebill", "patient_bill", "close"]) {
      expect(screen.getByText(action)).toBeDefined();
    }
    expect(screen.getByText(/Actions were on the table/i)).toBeDefined();
    expect(document.querySelectorAll(".opt.gone")).toHaveLength(0);
  });

  it("marks an Action struck from the options before the model was asked", () => {
    // The project's most distinctive idea, and the one no product surface would
    // ever show: `appeal` absent from the schema rather than discouraged in the
    // prompt. `CO-236` is the case; no fixture claim carries one, so this is
    // the only place it can be seen.
    const withheld = JUDGED.map((e) =>
      e.tool === "judge_denial" && e.kind === "tool_call"
        ? {
            ...e,
            detail: {
              ...e.detail,
              denial: "CO-236",
              options: ["corrected_claim", "rebill", "patient_bill", "close"],
            },
          }
        : e,
    );

    open(withheld);

    expect(document.querySelectorAll(".opt.gone")).toHaveLength(1);
    expect(screen.getByText(/struck from the options before the model was asked/i)).toBeDefined();
  });

  it("says plainly that a rule-closed claim was offered nothing", () => {
    open(RULE_CLOSED);

    expect(screen.getByText(/no model was asked about this claim/i)).toBeDefined();
  });
});

describe("which guardrails ran", () => {
  it("lists them in order with the one that answered marked", () => {
    open(RULE_CLOSED);
    tab(/guardrails/i);

    expect(screen.getByText("unappealable-remark")).toBeDefined();
    expect(screen.getByText(/fired · unappealable-remark:MA130/)).toBeDefined();
    expect(screen.getByText(/no model was consulted at all/i)).toBeDefined();
  });

  it("explains why the rules after the one that fired are absent", () => {
    // A rule listed as `passed` that never ran would be a record of something
    // that did not happen.
    open(RULE_CLOSED);
    tab(/guardrails/i);

    expect(document.querySelectorAll(".rules li")).toHaveLength(1);
    expect(screen.getByText(/rules after it never ran/i)).toBeDefined();
  });

  it("shows every rule passing on a claim that went to a model", () => {
    open(JUDGED);
    tab(/guardrails/i);

    expect(document.querySelectorAll(".rules li")).toHaveLength(3);
    expect(document.querySelectorAll(".rules li.fired")).toHaveLength(0);
    expect(screen.getByText(/the order is the safety property/i)).toBeDefined();
  });
});

describe("the model exchange", () => {
  it("shows the facts put to the model and what came back", () => {
    open(JUDGED);
    tab(/model exchange/i);

    expect(screen.getByText(/Total refused: 1250\.00/)).toBeDefined();
    expect(screen.getByText(/the auth covered it/)).toBeDefined();
  });

  it("says there was no exchange when a rule answered first", () => {
    open(RULE_CLOSED);
    tab(/model exchange/i);

    expect(screen.getByText(/absence is the point rather than a gap/i)).toBeDefined();
  });

  it("says so when a returned answer was refused", () => {
    const refused = JUDGED.map((e) =>
      e.kind === "tool_result" ? { ...e, outcome: "failed" } : e,
    );

    open(refused);
    tab(/model exchange/i);

    expect(screen.getByText(/outside the options it was given/i)).toBeDefined();
  });
});

describe("the browser work", () => {
  it("shows captured screenshots in sequence, keyed by the event that took them", () => {
    open([
      ...JUDGED,
      event({ seq: 12, kind: "tool_result", tool: "log_in", screenshot: "0012-log_in.png" }),
      event({ seq: 14, kind: "tool_result", tool: "download_eob", screenshot: "0014-download.png" }),
    ]);
    tab(/browser work/i);

    const images = document.querySelectorAll<HTMLImageElement>(".shot img");
    expect(images).toHaveLength(2);
    expect(images[0]?.getAttribute("src")).toBe(
      "/runs/2026-01-01T00-00-00Z/screenshots/0012-log_in.png",
    );
    expect(screen.getByText(/seq 0012 · log_in/)).toBeDefined();
  });

  it("counts the retries the tools absorbed", () => {
    open([
      ...JUDGED,
      event({ seq: 12, kind: "tool_result", tool: "log_in", screenshot: "0012-log_in.png" }),
      event({ seq: 13, kind: "retry", tool: "search_claims" }),
    ]);
    tab(/browser work/i);

    expect(screen.getByText(/1 mechanical retry/i)).toBeDefined();
  });

  it("tells an analysis run apart from a missing capture", () => {
    // A run that never opened a browser has nothing to show, and saying that is
    // different from an empty panel that looks like a failure to render.
    open(JUDGED);
    tab(/browser work/i);

    expect(screen.getByText(/not the same as a capture having gone missing/i)).toBeDefined();
  });
});

describe("dismissing it", () => {
  it("closes on Escape, without touching the claim underneath", () => {
    let closed = false;
    render(<Inspector entry={entry(JUDGED)} runEvents={[]} onClose={() => (closed = true)} />);

    fireEvent.keyDown(window, { key: "Escape" });

    expect(closed).toBe(true);
  });
});

describe("a run that stopped before it decided", () => {
  // The bug this pins: both panels concluded "a rule answered it" from the mere
  // absence of a model call — the exact inference the guardrail trace exists to
  // replace. A truncated run has no model call either, and saying a rule closed
  // the claim is the inspector asserting something untrue about how a
  // Determination was reached, on the screen whose value is that it does not.
  const TRUNCATED = [event({ seq: 2, kind: "phase_start" })];

  it("does not claim a rule answered a claim no rule touched", () => {
    open(TRUNCATED);

    expect(screen.queryByText(/a rule answered it/i)).toBeNull();
    expect(screen.getByText(/did not get that far/i)).toBeDefined();
  });

  it("says the same on the exchange, rather than inventing a guardrail", () => {
    open(TRUNCATED);
    tab(/model exchange/i);

    expect(screen.queryByText(/a guardrail answered this claim/i)).toBeNull();
    expect(screen.getByText(/not the same as a rule having closed the claim/i)).toBeDefined();
  });

  it("names the rule that answered, when one actually did", () => {
    open(RULE_CLOSED);

    expect(screen.getByText("unappealable-remark")).toBeDefined();
  });
});

describe("a record that says nothing", () => {
  it("does not read an absent options list as everything being withheld", () => {
    // `?? []` drew all five Actions struck through and asserted they were
    // withheld, from a record that had said nothing at all.
    const noOptions = JUDGED.map((e) =>
      e.kind === "tool_call" ? { ...e, detail: { facts: FACTS } } : e,
    );

    open(noOptions);

    expect(document.querySelectorAll(".opt.gone")).toHaveLength(0);
    expect(screen.getByText(/did not record which options/i)).toBeDefined();
  });

  it("does not show an empty box under a claim about what is in it", () => {
    const noFacts = JUDGED.map((e) =>
      e.kind === "tool_call" ? { ...e, detail: { options: ["appeal", "close"] } } : e,
    );

    open(noFacts);
    tab(/model exchange/i);

    expect(screen.getByText(/did not record the facts/i)).toBeDefined();
    // The returned value is still shown; it is the facts box that must not be
    // an empty rectangle under a sentence describing its contents.
    expect(document.querySelectorAll(".exchange")).toHaveLength(1);
  });
});

describe("browser work recorded against the run", () => {
  it("finds captures the agent did not tag with a claim", () => {
    // The browser tools emit with no claim_id, so the queue drops those events.
    // Reading only the claim's own would have made this panel say "no browser
    // work" however much of it a run had done.
    const runLevel = [
      event({ seq: 8, kind: "tool_result", tool: "log_in", claim_id: null, screenshot: "0008.png" }),
      event({ seq: 9, kind: "retry", tool: "search_claims", claim_id: null }),
    ];

    open(JUDGED, runLevel);
    tab(/browser work/i);

    expect(document.querySelectorAll(".shot img")).toHaveLength(1);
    expect(screen.getByText(/1 mechanical retry/i)).toBeDefined();
  });

  it("orders run-level and claim-level captures together by seq", () => {
    open(
      [...JUDGED, event({ seq: 20, kind: "tool_result", tool: "download_eob", screenshot: "b.png" })],
      [event({ seq: 8, kind: "tool_result", tool: "log_in", claim_id: null, screenshot: "a.png" })],
    );
    tab(/browser work/i);

    const captions = [...document.querySelectorAll(".shot figcaption")].map((c) => c.textContent);
    expect(captions[0]).toMatch(/seq 0008/);
    expect(captions[1]).toMatch(/seq 0020/);
  });
});
