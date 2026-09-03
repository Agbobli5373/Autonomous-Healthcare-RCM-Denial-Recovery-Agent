import { useEffect, useState } from "react";

import {
  applyEvent,
  type EventMessage,
  type Phase,
  type QueueEntry,
  type StreamMessage,
} from "./claims";

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
 * The queue, as the socket fills it.
 *
 * The socket address is relative to the page, so the console works wherever it
 * is served from - a local `rcm-agent console` and a hosted instance are the
 * same bundle.
 */
export function useQueue(): Stream {
  const [entries, setEntries] = useState<Map<string, QueueEntry>>(new Map());
  const [phases, setPhases] = useState<Phase[]>([]);
  const [runEvents, setRunEvents] = useState<Map<string, EventMessage[]>>(new Map());
  const [connection, setConnection] = useState<Connection>("connecting");

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${window.location.host}/events`);

    socket.onopen = () => setConnection("replaying");
    socket.onmessage = (frame: MessageEvent<string>) => {
      const message = JSON.parse(frame.data) as StreamMessage;
      if (message.type === "hello") {
        setPhases(message.phases);
        return;
      }
      if (message.type === "replayed") {
        setConnection("ready");
        return;
      }
      if (message.claim_id === null) {
        setRunEvents((current) => {
          const next = new Map(current);
          next.set(message.run_id, [...(next.get(message.run_id) ?? []), message]);
          return next;
        });
        return;
      }
      setEntries((current) => applyEvent(current, message));
    };
    // Told apart from "nothing to show" on purpose: an empty queue that never
    // connected is a broken console, and saying so is better than an honest
    // looking blank page.
    socket.onclose = () => setConnection((was) => (was === "ready" ? "ready" : "lost"));
    socket.onerror = () => setConnection("lost");

    return () => socket.close();
  }, []);

  return { claims: [...entries.values()], phases, connection, runEvents };
}
