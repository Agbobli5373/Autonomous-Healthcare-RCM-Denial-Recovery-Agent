/**
 * The console shell, before it has a run to show.
 *
 * A walking skeleton on purpose: everything here is the foundation the queue,
 * the claim detail and the inspector are built on - the palette, both themes,
 * the type, and the rule that motion stops when a viewer asks it to. Nothing
 * here reads a run, because nothing here needs to yet.
 */

// Mirrors `matrix.PHASES`, which is the source of truth. Held here only while
// the console has no run to read: once the server streams derived state, the
// phases arrive with it rather than being spelled out twice in two languages.
const PHASES = ["portal", "analysis", "emr", "appeal", "report"] as const;

export function App() {
  return (
    <div className="shell">
      <header className="appbar">
        <span className="mark" aria-hidden="true">
          R
        </span>
        <span className="wordmark">Denial Recovery</span>
        <span className="spacer" />
        <span className="runchip">no run loaded</span>
      </header>

      <nav className="rail" aria-label="Run phases">
        {PHASES.map((phase) => (
          <span className="step" key={phase}>
            <span className="pip" />
            <span className="lbl">{phase}</span>
          </span>
        ))}
      </nav>

      <main className="empty">
        <h1>Nothing to work yet.</h1>
        <p>
          The console reads a run directory. Start one with{" "}
          <code>rcm-agent determine-all</code> and its claims will appear here,
          ranked by what they are worth.
        </p>
      </main>
    </div>
  );
}
