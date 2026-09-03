/**
 * The console: a queue of claims, read from what runs recorded.
 *
 * Claim-centric on purpose. No analyst thinks in runs, so a run is plumbing here
 * - it names where a claim was worked and has no screen of its own.
 */

import { useState } from "react";

import { Detail } from "./Detail";
import { Queue } from "./Queue";
import { useQueue } from "./useQueue";

const CONNECTION_TEXT = {
  connecting: "connecting",
  replaying: "reading runs",
  ready: "up to date",
  lost: "disconnected",
} as const;

export function App() {
  const { claims, phases, connection, runEvents } = useQueue();
  const [openClaimId, setOpenClaimId] = useState<string | null>(null);
  const selected = claims.find((claim) => claim.claimId === openClaimId) ?? null;

  return (
    <div className="shell">
      <header className="appbar">
        <span className="mark" aria-hidden="true">
          R
        </span>
        <span className="wordmark">Denial Recovery</span>
        <span className="spacer" />
        <span className={`runchip ${connection === "lost" ? "bad" : ""}`}>
          {CONNECTION_TEXT[connection]}
        </span>
      </header>

      <nav className="rail" aria-label="Run phases">
        {phases.map((phase) => (
          <span className="step" key={phase}>
            <span className="pip" />
            <span className="lbl">{phase}</span>
          </span>
        ))}
      </nav>

      {claims.length === 0 && connection === "ready" ? (
        <main className="empty">
          <h1>Nothing to work yet.</h1>
          <p>
            The console reads a run directory. Start one with{" "}
            <code>rcm-agent determine-all</code> and its claims will appear here,
            ranked by what they are worth.
          </p>
        </main>
      ) : (
        <main>
          {selected ? (
            <Detail
              entry={selected}
              runEvents={runEvents.get(selected.runId) ?? []}
              onClose={() => setOpenClaimId(null)}
            />
          ) : (
            <Queue claims={claims} phases={phases} onOpen={setOpenClaimId} />
          )}
        </main>
      )}
    </div>
  );
}
