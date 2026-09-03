/**
 * Staying connected to a run in flight.
 *
 * The socket address is relative to the page, so a local `rcm-agent console` and
 * a hosted instance are the same bundle.
 *
 * A dropped connection has to come back knowing exactly where it got to.
 * Server-sent events would have carried that in `Last-Event-ID` and handed over
 * reconnect-and-resume for free; #56 chose WebSocket for the channel back a
 * later effort wants, and this is the half of that trade the client pays.
 *
 * The cursor is a sequence number **per run**, not one number and not one pair.
 * `seq` restarts with every run, so a single number cannot say where a client
 * is; and a single `(run, seq)` pair - which this was first - asks "is this
 * event newer than the last thing you were sent?", which is only the right
 * question while one run is in flight. With two, the last event a client saw
 * comes from the newer one, and everything the older run records next is either
 * dropped or sent again depending on which side is guessing.
 */

import type { StreamMessage } from "./claims";

/** How far the client has got in each run it has heard of. */
export type Cursor = ReadonlyMap<string, number>;

export const NOTHING_SEEN: Cursor = new Map();

/** Where the client has got to, having received this message. */
export function cursorAfter(cursor: Cursor, message: StreamMessage): Cursor {
  if (message.type !== "event") {
    return cursor;
  }
  const reached = cursor.get(message.run_id);
  if (reached !== undefined && reached >= message.seq) {
    return cursor;
  }
  const moved = new Map(cursor);
  moved.set(message.run_id, message.seq);
  return moved;
}

/**
 * The address to reconnect to, naming what has already been received.
 *
 * One `after=<run>:<seq>` for each run, which is the shape
 * `rcm_agent.console.server` parses. The two halves are pinned to the same
 * literal from both sides — `live.test.ts` here, `test_console_live.py` there —
 * because nothing else in either suite crosses the boundary, and when these
 * disagreed the server quietly ignored the query and replayed everything.
 */
export function socketUrl(origin: { protocol: string; host: string }, cursor: Cursor): string {
  const scheme = origin.protocol === "https:" ? "wss:" : "ws:";
  const base = `${scheme}//${origin.host}/events`;
  if (cursor.size === 0) {
    return base;
  }
  const asked = [...cursor].map(
    ([runId, seq]) => `after=${encodeURIComponent(`${runId}:${seq}`)}`,
  );
  return `${base}?${asked.join("&")}`;
}

const FIRST_RETRY_MS = 250;
const LONGEST_RETRY_MS = 8_000;

/**
 * How long to wait before trying again, having failed this many times.
 *
 * Nearly immediate at first, because the usual cause is a server restarting
 * during development and waiting seconds to notice it came back is the entire
 * cost of getting this wrong. Doubling from there, and capped: a console left
 * open overnight has to still reconnect in the morning rather than having backed
 * off to next week.
 */
export function backoffMs(attempt: number): number {
  return Math.min(FIRST_RETRY_MS * 2 ** attempt, LONGEST_RETRY_MS);
}
