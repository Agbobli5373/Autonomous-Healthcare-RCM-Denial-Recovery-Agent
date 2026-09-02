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

  deliver(message: unknown): void {
    act(() => this.onmessage?.({ data: JSON.stringify(message) }));
  }
}

function determination(claimId: string, action: string, guardrail: string | null = null) {
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
    derived: {
      cells: { portal: "done", analysis: "done", emr: "pending", appeal: "pending", report: "pending" },
      action,
    },
  };
}

function open(): FakeSocket {
  (globalThis as unknown as { WebSocket: unknown }).WebSocket = FakeSocket;
  render(<App />);
  const socket = FakeSocket.last;
  if (!socket) {
    throw new Error("the console never opened a socket");
  }
  act(() => socket.onopen?.());
  return socket;
}

describe("the console", () => {
  it("connects to the run stream on the page's own host", () => {
    const socket = open();

    expect(socket.url).toMatch(/\/events$/);
  });

  it("does not claim the queue is empty until it knows", () => {
    const socket = open();

    expect(screen.queryByText(/nothing to work yet/i)).toBeNull();

    socket.deliver({ type: "replayed" });

    expect(screen.getByText(/nothing to work yet/i)).toBeDefined();
  });

  it("says so when the connection dropped, rather than looking merely empty", () => {
    const socket = open();

    act(() => socket.onerror?.());

    expect(screen.getByText(/disconnected/i)).toBeDefined();
    expect(screen.queryByText(/nothing to work yet/i)).toBeNull();
  });

  it("shows three claims reaching three different actions", () => {
    const socket = open();

    socket.deliver(determination("CLM-2026-0001", "appeal"));
    socket.deliver(determination("CLM-2026-0002", "close", "unappealable-remark:MA130"));
    socket.deliver(determination("CLM-2026-0003", "rebill"));
    socket.deliver({ type: "replayed" });

    expect(screen.getByText("AP")).toBeDefined();
    expect(screen.getByText("RB")).toBeDefined();
    expect(screen.getByText("CL")).toBeDefined();
  });

  it("puts the rule-closed claim in its own section, naming the rule", () => {
    const socket = open();

    socket.deliver(determination("CLM-2026-0002", "close", "unappealable-remark:MA130"));
    socket.deliver({ type: "replayed" });

    expect(screen.getByText(/closed by rule/i)).toBeDefined();
    expect(screen.getByText("unappealable-remark:MA130")).toBeDefined();
    expect(screen.getByText(/nothing was weighed/i)).toBeDefined();
  });

  it("shows no score anywhere for a claim a rule closed", () => {
    const socket = open();

    socket.deliver(determination("CLM-2026-0002", "close", "unappealable-remark:MA130"));
    socket.deliver({ type: "replayed" });

    expect(screen.queryByText(/562\.50/)).toBeNull();
    expect(screen.queryByText(/confidence/i)).toBeNull();
  });
});

describe("more than one claim closed by a rule", () => {
  it("lays every one of them out the same way", () => {
    const socket = open();

    socket.deliver(determination("CLM-A", "close", "unappealable-remark:MA130"));
    socket.deliver(determination("CLM-B", "close", "no-denial"));
    socket.deliver({ type: "replayed" });

    // A sibling selector reached only the first row, so a second rule-closed
    // claim kept the ranked layout and its columns drifted out of line.
    const ruled = document.querySelectorAll(".qrow.norank");
    expect(ruled).toHaveLength(2);
  });
});
