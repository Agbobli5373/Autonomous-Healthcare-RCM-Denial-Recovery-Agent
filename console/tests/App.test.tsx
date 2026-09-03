/**
 * The console, driven by a stand-in socket.
 *
 * Two things here are worth more than the rest. An empty queue must read as
 * *waiting* and never as broken - a blank page is indistinguishable from a
 * failure, and that is the first thing a reviewer would see. And three claims
 * reaching three different Actions is the demo's whole argument: an agent that
 * answered `appeal` everywhere would get one of them right.
 */

import { act, render, screen } from "@testing-library/react";

import { App } from "../src/App";
import { PHASES, determination, event } from "./fixtures";

class FakeSocket {
  static last: FakeSocket | null = null;
  onopen: (() => void) | null = null;
  onmessage: ((frame: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public url: string) {
    FakeSocket.last = this;
  }

  close(): void {}

  /**
   * One frame, and the moment it takes to land.
   *
   * The queue gathers arriving events for a frame before it sets state, so
   * asserting straight after delivery asserts before the flush.
   */
  async deliver(message: unknown): Promise<void> {
    act(() => this.onmessage?.({ data: JSON.stringify(message) }));
    await act(async () => {
      await new Promise((landed) => setTimeout(landed, 20));
    });
  }
}

const REAL_WEBSOCKET = globalThis.WebSocket;

afterEach(() => {
  // Restored, or every later test in the process inherits the stand-in.
  (globalThis as unknown as { WebSocket: unknown }).WebSocket = REAL_WEBSOCKET;
});

async function open(): Promise<FakeSocket> {
  (globalThis as unknown as { WebSocket: unknown }).WebSocket = FakeSocket;
  render(<App />);
  const socket = FakeSocket.last;
  if (!socket) {
    throw new Error("the console never opened a socket");
  }
  act(() => socket.onopen?.());
  await socket.deliver({ type: "hello", phases: PHASES });
  return socket;
}

describe("the console", () => {
  it("connects to the run stream on the page's own host", async () => {
    const socket = await open();

    // Relative to wherever the bundle is served from: the same build has to work
    // locally and hosted, so a hardcoded host would break one of them.
    expect(socket.url).toBe(`ws://${window.location.host}/events`);
  });

  it("names the phases the server sent, rather than a list of its own", async () => {
    await open();

    for (const phase of PHASES) {
      expect(screen.getByText(phase)).toBeDefined();
    }
  });

  it("does not claim the queue is empty until it knows", async () => {
    const socket = await open();

    expect(screen.queryByText(/nothing to work yet/i)).toBeNull();

    await socket.deliver({ type: "replayed" });

    expect(screen.getByText(/nothing to work yet/i)).toBeDefined();
  });

  it("says so when the connection dropped, rather than looking merely empty", async () => {
    const socket = await open();

    act(() => socket.onerror?.());

    expect(screen.getByText(/disconnected/i)).toBeDefined();
    expect(screen.queryByText(/nothing to work yet/i)).toBeNull();
  });

  it("shows three claims reaching three different actions", async () => {
    const socket = await open();

    await socket.deliver(determination("CLM-2026-0001", "appeal"));
    await socket.deliver(determination("CLM-2026-0002", "close", { guardrail: "unappealable-remark:MA130" }));
    await socket.deliver(determination("CLM-2026-0003", "rebill"));
    await socket.deliver({ type: "replayed" });

    expect(screen.getByText("AP")).toBeDefined();
    expect(screen.getByText("RB")).toBeDefined();
    expect(screen.getByText("CL")).toBeDefined();
  });

  it("puts the rule-closed claim in its own section, naming the rule", async () => {
    const socket = await open();

    await socket.deliver(determination("CLM-2026-0002", "close", { guardrail: "unappealable-remark:MA130" }));
    await socket.deliver({ type: "replayed" });

    expect(screen.getByText(/closed by rule/i)).toBeDefined();
    expect(screen.getByText("unappealable-remark:MA130")).toBeDefined();
    expect(screen.getByText(/nothing was weighed/i)).toBeDefined();
  });

  it("shows no score for a rule-closed claim even if one somehow reached it", async () => {
    const socket = await open();

    // Given a Priority it should never have, to pin the rendering rather than
    // the fixture: nothing was weighed, so nothing is shown.
    await socket.deliver(
      determination("CLM-2026-0002", "close", {
        guardrail: "unappealable-remark:MA130",
        priority: { amount_at_stake: "80.00", likelihood: 0.1, expected_recovery: "8.00" },
      }),
    );
    await socket.deliver({ type: "replayed" });

    const row = document.querySelector(".qrow.norank");
    expect(row).not.toBeNull();
    expect(row?.textContent).not.toMatch(/\d+\.\d\d/);
  });
});

describe("more than one claim closed by a rule", () => {
  it("lays every one of them out the same way", async () => {
    const socket = await open();

    await socket.deliver(determination("CLM-A", "close", { guardrail: "unappealable-remark:MA130" }));
    await socket.deliver(determination("CLM-B", "close", { guardrail: "no-denial" }));
    await socket.deliver({ type: "replayed" });

    // A sibling selector reached only the first row, so a second rule-closed
    // claim kept the ranked layout and its columns drifted out of line.
    const ruled = document.querySelectorAll(".qrow.norank");
    expect(ruled).toHaveLength(2);
  });
});

describe("opening a claim", () => {
  it("replaces the queue with the claim, and goes back", async () => {
    const socket = await open();

    await socket.deliver(determination("CLM-2026-0001", "appeal"));
    await socket.deliver({ type: "replayed" });

    act(() => {
      screen.getByLabelText("Open CLM-2026-0001").click();
    });

    expect(screen.getByText(/what the payer said/i)).toBeDefined();

    act(() => {
      screen.getByText("Close").click();
    });

    expect(screen.queryByText(/what the payer said/i)).toBeNull();
    expect(screen.getByText(/work queue/i)).toBeDefined();
  });
});

describe("a claim the agent is still working", () => {
  it("reads as pending rather than as missing", async () => {
    // Mid-run there is no Determination, no Action and no Priority - and a row
    // rendering those absences as blanks says the claim is empty rather than
    // that it is in progress. The phases are the answer: one of them is running.
    const socket = await open();

    await socket.deliver(
      event({
        claim_id: "CLM-2026-0004",
        kind: "phase_start",
        derived: {
          cells: {
            portal: "done",
            analysis: "running",
            emr: "pending",
            appeal: "pending",
            report: "pending",
          },
        },
      }),
    );
    await socket.deliver({ type: "replayed" });

    expect(screen.getByText("CLM-2026-0004")).toBeDefined();
    expect(document.querySelectorAll(".c-running")).toHaveLength(1);
    expect(screen.queryByText(/nothing to work yet/i)).toBeNull();
  });
});
