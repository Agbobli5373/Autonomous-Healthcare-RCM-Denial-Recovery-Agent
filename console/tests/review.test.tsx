/**
 * Approving and rejecting.
 *
 * Three of these tests pin decisions rather than behaviour, and each is a thing
 * the screen would otherwise get quietly wrong: a rule-closed claim offering a
 * control that should not exist, a rejection recorded with nothing to learn
 * from, and a button implying an agent will act when nothing will.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { ReviewControls } from "../src/ReviewControls";
import type { QueueEntry } from "../src/claims";
import type { Review } from "../src/reviews";
import { claimRecord } from "./fixtures";

const DIGEST = "a".repeat(64);

function entry(overrides: Partial<QueueEntry> = {}): QueueEntry {
  return {
    claimId: "CLM-2026-0001",
    runId: "2026-01-01T00-00-00Z",
    action: "appeal",
    guardrailed: false,
    determination: {
      claim_id: "CLM-2026-0001",
      action: "appeal",
      rationale: "the authorization covered the date of service",
      evidence_required: ["Authorization record"],
      guardrail: null,
      priority: { amount_at_stake: "1250.00", likelihood: 0.45, expected_recovery: "562.50" },
    },
    determinationDigest: DIGEST,
    claim: claimRecord("CLM-2026-0001"),
    cells: null,
    events: [],
    ...overrides,
  };
}

function show(overrides: Partial<QueueEntry> = {}, review: Review | null = null) {
  const recorded = vi.fn();
  render(
    <ReviewControls
      entry={entry(overrides)}
      digest={overrides.determinationDigest ?? DIGEST}
      review={review}
      onRecorded={recorded}
    />,
  );
  return recorded;
}

let sent: { url: string; body: Record<string, unknown> } | null = null;

beforeEach(() => {
  sent = null;
  localStorage.setItem("rcm.reviewer", "isaac");
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    sent = { url, body: JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown> };
    return Promise.resolve({
      ok: true,
      json: () =>
        Promise.resolve({
          claim_id: "CLM-2026-0001",
          reviewed_at: "2026-03-20T09:30:00+00:00",
          reviewer: "console",
          verdict: sent?.body.verdict,
          reason: sent?.body.reason ?? "",
          counter_action: sent?.body.counter_action ?? null,
          determination_digest: DIGEST,
          run_id: "2026-01-01T00-00-00Z",
          stands: true,
        }),
    } as Response);
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("a claim a rule closed", () => {
  it("offers no control at all, not a disabled one", () => {
    // A disabled button says "you may not do this". The truth is that there is
    // nothing here to decide: a rule was never a judgement.
    show({ guardrailed: true });

    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText(/a rule decided this/i)).toBeDefined();
  });
});

describe("approving", () => {
  it("sends the digest of the Determination on screen", async () => {
    // The only thing standing between a tab left open overnight and a verdict
    // recorded against a reading that has since been replaced.
    const recorded = show();

    fireEvent.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => expect(recorded).toHaveBeenCalled());
    expect(sent?.url).toBe("/reviews/CLM-2026-0001");
    expect(sent?.body).toMatchObject({ verdict: "approved", determination_digest: DIGEST });
  });

  it("says plainly that nothing acts on it", () => {
    // A reviewer who clicks Approve and expects an agent to move has been
    // misled by the button. Filing is a separate effort.
    show();

    expect(screen.getByText(/nothing files it/i)).toBeDefined();
  });
});

describe("rejecting", () => {
  it("cannot be recorded without a reason", () => {
    show();

    fireEvent.click(screen.getByRole("button", { name: /^reject$/i }));

    const record = screen.getByRole("button", { name: /record rejection/i });
    expect(record).toHaveProperty("disabled", true);
    expect(screen.getByText(/needs a reason/i)).toBeDefined();
  });

  it("sends the reason and the action the reviewer would have chosen", async () => {
    const recorded = show();

    fireEvent.click(screen.getByRole("button", { name: /^reject$/i }));
    fireEvent.change(screen.getByRole("textbox", { name: /why/i }), {
      target: { value: "no authorization was ever obtained" },
    });
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "rebill" } });
    fireEvent.click(screen.getByRole("button", { name: /record rejection/i }));

    await waitFor(() => expect(recorded).toHaveBeenCalled());
    expect(sent?.body).toMatchObject({
      verdict: "rejected",
      reason: "no authorization was ever obtained",
      counter_action: "rebill",
    });
  });
});

describe("when the server refuses", () => {
  it("shows what the reviewer should do, and records nothing", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve({
        ok: false,
        status: 409,
        json: () => Promise.resolve({ detail: "this page was looking at a different Determination" }),
      } as Response),
    );
    const recorded = show();

    fireEvent.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toMatch(/different determination/i),
    );
    expect(recorded).not.toHaveBeenCalled();
  });
});

describe("once a verdict stands", () => {
  it("shows it with the digest it was given for, and offers no second one", () => {
    show({}, {
      claim_id: "CLM-2026-0001",
      reviewed_at: "2026-03-20T09:30:00+00:00",
      reviewer: "isaac",
      verdict: "rejected",
      reason: "no authorization exists",
      counter_action: "rebill",
      determination_digest: DIGEST,
      run_id: "2026-01-01T00-00-00Z",
      stands: true,
    });

    expect(screen.getByText("rejected")).toBeDefined();
    expect(screen.getByText(/no authorization exists/)).toBeDefined();
    expect(screen.getByText(new RegExp(DIGEST))).toBeDefined();
    expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
  });
});

describe("a claim nothing has decided", () => {
  it("has nothing to approve", () => {
    show({ determination: null, determinationDigest: null });

    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText(/nothing to approve/i)).toBeDefined();
  });
});

describe("a verdict a re-run has outlived", () => {
  // The failure the digest exists to prevent, arriving through the screen
  // instead of through the write path. `reviewed()` refuses a stale verdict and
  // the POST answers 409 - but rendering one as standing is the same claim made
  // silently: a human reading "approved" over a Determination nobody approved.
  const OLD = "b".repeat(64);

  function superseded() {
    show({}, {
      claim_id: "CLM-2026-0001",
      reviewed_at: "2026-03-20T09:30:00+00:00",
      reviewer: "isaac",
      verdict: "approved",
      reason: "",
      counter_action: null,
      determination_digest: OLD,
      run_id: "2026-01-01T00-00-00Z",
      stands: false,
    });
  }

  it("does not show it as the verdict standing on this Determination", () => {
    superseded();

    expect(screen.queryByText(new RegExp(OLD))).toBeNull();
    expect(screen.getByText(/re-run has replaced/i)).toBeDefined();
  });

  it("asks for a verdict on the reading now on screen", () => {
    superseded();

    expect(screen.getByRole("button", { name: /approve/i })).toBeDefined();
  });
});

describe("who decided", () => {
  it("records the name the reviewer gave, not the application's", () => {
    // Every verdict was signed `console`, so the record could not answer the
    // first question anyone asks of it.
    const recorded = show();

    fireEvent.click(screen.getByRole("button", { name: /approve/i }));

    return waitFor(() => expect(recorded).toHaveBeenCalled()).then(() => {
      expect(sent?.body).toMatchObject({ reviewer: "isaac" });
    });
  });

  it("will not take a verdict from nobody", () => {
    localStorage.clear();
    show();

    expect(screen.getByRole("button", { name: /approve/i })).toHaveProperty("disabled", true);
  });
});

describe("abandoning a rejection", () => {
  it("does not let its reason and counter-action ride into the approval", async () => {
    // Reject, pick an Action, cancel, approve - and the approval carried a
    // disagreement inside it, plus a reason for a verdict that had none.
    const recorded = show();

    fireEvent.click(screen.getByRole("button", { name: /^reject$/i }));
    fireEvent.change(screen.getByRole("textbox", { name: /why/i }), { target: { value: "no auth exists" } });
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "rebill" } });
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    fireEvent.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => expect(recorded).toHaveBeenCalled());
    expect(sent?.body).toMatchObject({ verdict: "approved", reason: "", counter_action: null });
  });
});
