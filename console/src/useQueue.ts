import { useEffect, useRef, useState } from "react";

import {
  applyEvents,
  type EventMessage,
  type Phase,
  type QueueEntry,
  type StreamMessage,
} from "./claims";
import { NOTHING_SEEN, backoffMs, cursorAfter, socketUrl, type Cursor } from "./live";

export type Connection = "connecting" | "replaying" | "ready" | "lost";

export interface Stream {
  claims: QueueEntry[];
  phases: Phase[];
  connection: Connection;
  /**
   * Events belonging to a run rather than to any one claim, by run.
   *
   * The browser tools do not tag their captures with a claim, so this is where
   * the agent's browser work arrives. The queue drops these - a row that
   * answers to nobody - and the inspector needs them.
   */
  runEvents: Map<string, EventMessage[]>;
}

/**
 * How long arriving events are gathered before the queue is set.
 *
 * A socket delivers one frame per event, each on its own turn of the loop, so a
 * run catching up sets state once per event and re-renders the whole table each
 * time - exactly when the console is busiest and most worth reading. Gathering
 * for a frame's worth of time makes a burst cost about what one event costs.
 *
 * A timer rather than `requestAnimationFrame`: a console in a background tab
 * gets no frames, and would sit on a growing buffer until someone looked at it.
 * The flush is cheap enough that keeping up regardless is the better trade.
 */
const FRAME_MS = 16;

/**
 * The queue, as the socket fills it.
 *
 * The socket address is relative to the page, so the console works wherever it
 * is served from - a local `rcm-agent console` and a hosted instance are the
 * same bundle.
 *
 * A dropped connection reconnects on its own and resumes from the last event it
 * saw, so nothing is delivered twice and nothing is missed. That is work rather
 * than a given: server-sent events would have carried the cursor in
 * `Last-Event-ID`, and #56 chose WebSocket for the channel back a later effort
 * wants.
 */
export function useQueue(): Stream {
  const [entries, setEntries] = useState<Map<string, QueueEntry>>(new Map());
  const [phases, setPhases] = useState<Phase[]>([]);
  const [runEvents, setRunEvents] = useState<Map<string, EventMessage[]>>(new Map());
  const [connection, setConnection] = useState<Connection>("connecting");

  // A ref rather than state: a reconnect happens from inside a closure that
  // would otherwise capture whatever the cursor was when the effect ran, and
  // resume from there - re-receiving everything since.
  const cursor = useRef<Cursor>(NOTHING_SEEN);

  useEffect(() => {
    let watching = true;
    let socket: WebSocket | null = null;
    let attempt = 0;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let gathering: ReturnType<typeof setTimeout> | undefined;
    let pending: EventMessage[] = [];

    const flush = () => {
      gathering = undefined;
      const batch = pending;
      pending = [];
      if (batch.length === 0) {
        return;
      }
      setEntries((current) => applyEvents(current, batch));

      const runLevel = batch.filter((message) => message.claim_id === null);
      if (runLevel.length > 0) {
        setRunEvents((current) => {
          const next = new Map(current);
          for (const message of runLevel) {
            next.set(message.run_id, [...(next.get(message.run_id) ?? []), message]);
          }
          return next;
        });
      }
    };

    const connect = () => {
      socket = new WebSocket(socketUrl(window.location, cursor.current));

      socket.onopen = () => {
        attempt = 0;
        setConnection("replaying");
      };

      socket.onmessage = (frame: MessageEvent<string>) => {
        const message = JSON.parse(frame.data) as StreamMessage;
        cursor.current = cursorAfter(cursor.current, message);

        if (message.type === "hello") {
          setPhases(message.phases);
          return;
        }
        if (message.type === "replayed") {
          // Not the end of the stream. It means the client is level with what is
          // on disk; events go on arriving as the agent records them.
          setConnection("ready");
          return;
        }
        pending.push(message);
        gathering ??= setTimeout(flush, FRAME_MS);
      };

      // Said plainly, and said again on every drop. An earlier version kept
      // "up to date" once it had been true, so a console whose socket had died
      // went on describing a queue it was no longer being told about.
      socket.onclose = () => {
        if (!watching) {
          return;
        }
        setConnection("lost");
        retry = setTimeout(connect, backoffMs(attempt));
        attempt += 1;
      };
      socket.onerror = () => setConnection("lost");
    };

    connect();

    return () => {
      watching = false;
      clearTimeout(retry);
      clearTimeout(gathering);
      socket?.close();
    };
  }, []);

  return { claims: [...entries.values()], phases, connection, runEvents };
}
