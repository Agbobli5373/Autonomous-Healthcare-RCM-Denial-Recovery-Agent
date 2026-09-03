/**
 * The socket, as the queue sees it.
 *
 * Three things are pinned here and each is a way the console lies or stalls when
 * it is wrong: a chip reading "up to date" over a dead socket, a reconnect that
 * asks for the whole history again, and a table that re-renders once per event
 * when a run is at its busiest.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import type { StreamMessage } from "../src/claims";
import { useQueue } from "../src/useQueue";
import { determination, event } from "./fixtures";

class FakeSocket {
  static opened: FakeSocket[] = [];

  onopen: (() => void) | null = null;
  onmessage: ((frame: MessageEvent<string>) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closedByClient = false;

  constructor(public url: string) {
    FakeSocket.opened.push(this);
    // The real thing opens on a later turn of the loop, and the hook must not
    // depend on having been open before it was asked to do anything.
    queueMicrotask(() => this.onopen?.());
  }

  close() {
    this.closedByClient = true;
  }

  deliver(...messages: StreamMessage[]) {
    for (const message of messages) {
      this.onmessage?.({ data: JSON.stringify(message) } as MessageEvent<string>);
    }
  }

  drop() {
    this.onclose?.();
  }
}

const latest = () => FakeSocket.opened[FakeSocket.opened.length - 1]!;

let renders = 0;

function Probe() {
  const { claims, connection } = useQueue();
  renders += 1;
  return (
    <div>
      <span data-testid="connection">{connection}</span>
      <span data-testid="count">{claims.length}</span>
    </div>
  );
}

beforeEach(() => {
  FakeSocket.opened = [];
  renders = 0;
  vi.stubGlobal("WebSocket", FakeSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("what the chip says", () => {
  it("does not keep claiming to be up to date over a socket that has gone", async () => {
    // The version this replaces kept "up to date" after a drop, on the grounds
    // that it had once been true. A console reporting a live queue while
    // receiving nothing is worse than one that admits it is blind.
    render(<Probe />);
    await waitFor(() => expect(FakeSocket.opened).toHaveLength(1));
    latest().deliver({ type: "hello", phases: [] }, { type: "replayed" });
    await waitFor(() => expect(screen.getByTestId("connection").textContent).toBe("ready"));

    latest().drop();

    await waitFor(() => expect(screen.getByTestId("connection").textContent).toBe("lost"));
  });
});

describe("coming back", () => {
  it("reconnects on its own", async () => {
    render(<Probe />);
    await waitFor(() => expect(FakeSocket.opened).toHaveLength(1));

    latest().drop();

    await waitFor(() => expect(FakeSocket.opened.length).toBeGreaterThan(1), { timeout: 3000 });
  });

  it("asks only for what it has not seen", async () => {
    // Without the cursor the server replays everything, and the client folds a
    // history it already holds — the duplicate half of the resume problem.
    render(<Probe />);
    await waitFor(() => expect(FakeSocket.opened).toHaveLength(1));
    latest().deliver(
      { type: "hello", phases: [] },
      event({ run_id: "2026-04-04T00-00-00Z", seq: 7 }),
    );

    latest().drop();

    await waitFor(() => expect(FakeSocket.opened.length).toBeGreaterThan(1), { timeout: 3000 });
    expect(latest().url).toContain("after=2026-04-04T00-00-00Z%3A7");
  });

  it("does not reconnect after the console has gone away", async () => {
    const view = render(<Probe />);
    await waitFor(() => expect(FakeSocket.opened).toHaveLength(1));

    view.unmount();
    latest().drop();

    await new Promise((resume) => setTimeout(resume, 600));
    expect(FakeSocket.opened).toHaveLength(1);
  });
});

describe("a burst", () => {
  it("costs about what one event costs", async () => {
    // Time is driven rather than waited on. A real socket delivers a burst
    // frame after frame within a millisecond or two; `setTimeout(0)` under jsdom
    // is nearer seven, which spreads sixty events over half a second and models
    // something slower than the case worth defending against.
    vi.useFakeTimers();
    try {
      render(<Probe />);
      await act(async () => void (await vi.advanceTimersByTimeAsync(1)));
      const socket = latest();
      socket.deliver({ type: "hello", phases: [] });
      const before = renders;

      for (let i = 0; i < 60; i += 1) {
        socket.deliver(determination(`CLM-${i}`, "appeal"));
        await act(async () => void (await vi.advanceTimersByTimeAsync(1)));
      }
      await act(async () => void (await vi.advanceTimersByTimeAsync(40)));

      expect(screen.getByTestId("count").textContent).toBe("60");
      // Sixty events over sixty milliseconds. Uncoalesced that is sixty renders
      // of the whole table; a frame's worth of gathering makes it a handful.
      expect(renders - before).toBeLessThan(8);
    } finally {
      vi.useRealTimers();
    }
  });
});
