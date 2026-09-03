/**
 * Staying connected, and staying cheap.
 *
 * Two properties, and both are about what happens when things go wrong rather
 * than when they go right. A socket that drops must come back knowing exactly
 * where it got to — server-sent events would have carried that in
 * `Last-Event-ID`, and #56 knowingly took the trade that makes it ours. And a
 * burst of events must cost one render rather than one render each, because the
 * queue is a table and re-rendering it per event is how a live console becomes
 * unusable exactly when something is happening.
 */

import { applyEvents } from "../src/claims";
import { NOTHING_SEEN, backoffMs, cursorAfter, socketUrl } from "../src/live";
import { determination, event } from "./fixtures";

describe("knowing where the client got to", () => {
  it("starts having seen nothing", () => {
    expect(cursorAfter(NOTHING_SEEN, { type: "hello", phases: [] }).size).toBe(0);
  });

  it("advances only on events, which are the only things with a place", () => {
    const cursor = cursorAfter(NOTHING_SEEN, determination("CLM-1", "appeal"));

    expect([...cursor]).toEqual([["2026-01-01T00-00-00Z", 1]]);
    expect(cursorAfter(cursor, { type: "replayed" })).toBe(cursor);
  });

  it("keeps a place in every run, not just the newest", () => {
    // One pair could not express this, and the gap it left was silent: with two
    // runs in flight the client's last event comes from the newer one, and
    // everything the older one recorded next fell below the cursor.
    let cursor = cursorAfter(NOTHING_SEEN, event({ run_id: "2026-01-01T00-00-00Z", seq: 9 }));
    cursor = cursorAfter(cursor, event({ run_id: "2026-02-02T00-00-00Z", seq: 0 }));

    expect([...cursor]).toEqual([
      ["2026-01-01T00-00-00Z", 9],
      ["2026-02-02T00-00-00Z", 0],
    ]);
  });

  it("does not go backwards on an event it has already passed", () => {
    const cursor = cursorAfter(NOTHING_SEEN, event({ seq: 9 }));

    expect(cursorAfter(cursor, event({ seq: 4 }))).toBe(cursor);
  });
});

describe("the address it reconnects to", () => {
  const origin = { protocol: "http:", host: "localhost:8090" };

  it("asks for everything when it has seen nothing", () => {
    expect(socketUrl(origin, NOTHING_SEEN)).toBe("ws://localhost:8090/events");
  });

  it("names its place in each run, in the shape the server parses", () => {
    // Pinned to the same literal as `test_console_live.py`'s
    // `test_the_query_a_reconnecting_console_actually_sends`. Nothing else in
    // either suite crosses this boundary: when the two disagreed, the server
    // ignored the query and replayed everything, both suites stayed green, and
    // every reconnect silently duplicated the whole history.
    const cursor = new Map([["2026-01-01T00-00-00Z", 12]]);

    expect(socketUrl(origin, cursor)).toBe(
      "ws://localhost:8090/events?after=2026-01-01T00-00-00Z%3A12",
    );
  });

  it("names each run separately", () => {
    const cursor = new Map([
      ["2026-01-01T00-00-00Z", 12],
      ["2026-02-02T00-00-00Z", 3],
    ]);

    expect(socketUrl(origin, cursor)).toBe(
      "ws://localhost:8090/events" +
        "?after=2026-01-01T00-00-00Z%3A12&after=2026-02-02T00-00-00Z%3A3",
    );
  });

  it("follows the page onto https, so a hosted console is the same bundle", () => {
    expect(socketUrl({ protocol: "https:", host: "rcm.example" }, NOTHING_SEEN)).toBe(
      "wss://rcm.example/events",
    );
  });

  it("escapes a run id rather than trusting it to be url-safe", () => {
    expect(socketUrl(origin, new Map([["a b&c", 1]]))).toContain("after=a%20b%26c%3A1");
  });
});

describe("backing off between attempts", () => {
  it("retries almost at once the first time", () => {
    // A dropped socket is usually a server restarting during development, and
    // waiting seconds to notice it came back is the whole cost of getting this
    // wrong in the common case.
    expect(backoffMs(0)).toBeLessThanOrEqual(500);
  });

  it("grows, so a server that is actually gone is not hammered", () => {
    expect(backoffMs(3)).toBeGreaterThan(backoffMs(1));
  });

  it("stops growing, so a console left open overnight still reconnects", () => {
    expect(backoffMs(50)).toBe(backoffMs(10));
    expect(backoffMs(50)).toBeLessThanOrEqual(10_000);
  });
});

describe("folding a burst", () => {
  it("applies many events in one pass", () => {
    const folded = applyEvents(new Map(), [
      determination("CLM-1", "appeal"),
      determination("CLM-2", "rebill"),
    ]);

    expect([...folded.keys()]).toEqual(["CLM-1", "CLM-2"]);
  });

  it("leaves the map it was given alone", () => {
    const before = new Map();

    applyEvents(before, [determination("CLM-1", "appeal")]);

    expect(before.size).toBe(0);
  });

  it("ends where folding one at a time would", () => {
    const messages = [
      determination("CLM-1", "appeal"),
      determination("CLM-1", "rebill"),
      determination("CLM-2", "close", { guardrail: "no-denial" }),
    ];

    const batched = applyEvents(new Map(), messages);

    expect(batched.get("CLM-1")?.action).toBe("rebill");
    expect(batched.get("CLM-2")?.guardrailed).toBe(true);
  });

  it("returns the same map when a batch holds nothing for the queue", () => {
    // Run-level events carry no claim. A new map per socket frame would re-render
    // the table for work that belongs to nobody.
    const before = new Map();

    expect(applyEvents(before, [{ type: "replayed" }])).toBe(before);
  });
});
