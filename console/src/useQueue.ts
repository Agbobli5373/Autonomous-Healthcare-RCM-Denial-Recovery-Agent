import { useEffect, useRef, useState } from "react";

import { applyEvent, type Claim, type StreamMessage } from "./claims";

export type Connection = "connecting" | "replaying" | "ready" | "lost";

/**
 * The queue, as the socket fills it.
 *
 * Relative to the page, so the console works wherever it is served from - a
 * local `rcm-agent console` and a hosted instance are the same bundle.
 */
export function useQueue(): { claims: Claim[]; connection: Connection } {
  const [claims, setClaims] = useState<Map<string, Claim>>(new Map());
  const [connection, setConnection] = useState<Connection>("connecting");
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${window.location.host}/events`);
    socketRef.current = socket;

    socket.onopen = () => setConnection("replaying");
    socket.onmessage = (frame: MessageEvent<string>) => {
      const message = JSON.parse(frame.data) as StreamMessage;
      if (message.type === "replayed") {
        setConnection("ready");
        return;
      }
      setClaims((current) => applyEvent(current, message));
    };
    // Distinguished from "nothing to show": an empty queue that never connected
    // is a broken console, and saying so is better than an honest-looking blank.
    socket.onclose = () => setConnection((was) => (was === "ready" ? "ready" : "lost"));
    socket.onerror = () => setConnection("lost");

    return () => socket.close();
  }, []);

  return { claims: [...claims.values()], connection };
}
