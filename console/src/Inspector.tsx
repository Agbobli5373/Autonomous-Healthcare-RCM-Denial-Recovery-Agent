/**
 * How the Determination was actually reached.
 *
 * This is the layer for someone judging the agent rather than someone using it,
 * and it is where the project's distinctive claims stop being assertions. Every
 * panel reads what the run recorded. Nothing is reconstructed - a reconstruction
 * silently becomes a lie the day the code that built it changes, and this is the
 * one screen whose whole value is that it cannot.
 *
 * Where a run recorded nothing for a layer, the layer says so. An empty panel
 * that looked like a rendering failure would be worse than an honest absence,
 * and on the rule-closed claim two of these absences are the point.
 */

import { useEffect, useState } from "react";

import { ACTIONS } from "./actions";
import type { EventMessage, QueueEntry } from "./claims";

type Layer = "withheld" | "guardrails" | "model" | "browser";

/**
 * The tabs and what each one draws, in one place.
 *
 * Declaring the tabs in one list and rendering them from a second was a way to
 * add a fifth layer to the strip and forget to give it a panel.
 */
const LAYERS: {
  key: Layer;
  title: string;
  panel: (entry: QueueEntry, runEvents: EventMessage[]) => React.ReactNode;
}[] = [
  {
    key: "withheld",
    title: "Options withheld",
    panel: (entry) => <Withheld events={entry.events} />,
  },
  { key: "guardrails", title: "Guardrails", panel: (entry) => <Guardrails events={entry.events} /> },
  { key: "model", title: "Model exchange", panel: (entry) => <ModelExchange events={entry.events} /> },
  {
    key: "browser",
    title: "Browser work",
    panel: (entry, runEvents) => <BrowserWork entry={entry} runEvents={runEvents} />,
  },
];

interface RuleOutcome {
  rule: string;
  fired: boolean;
  guardrail?: string;
}

function firstEvent(events: EventMessage[], kind: string, tool?: string): EventMessage | undefined {
  return events.find((event) => event.kind === kind && (tool === undefined || event.tool === tool));
}

/**
 * Which rule answered the claim, according to the run - or `undefined`.
 *
 * Read, never inferred. Concluding "a rule answered it" from the *absence* of a
 * model call is the exact inference the guardrail trace was added to replace:
 * an absent call proves the model was not asked, and says nothing about why. A
 * run that stopped early has no model call either, and saying a rule closed it
 * would be the inspector asserting something untrue about how a Determination
 * was reached - on the one screen whose whole value is that it does not.
 */
function ruleThatFired(events: EventMessage[]): RuleOutcome | undefined {
  const trace = firstEvent(events, "guardrails");
  const evaluated = trace?.detail.evaluated;
  if (!Array.isArray(evaluated)) {
    return undefined;
  }
  return (evaluated as RuleOutcome[]).find((rule) => rule.fired);
}

/** What the run said about a claim it never finished. */
function Unfinished({ what }: { what: string }) {
  return (
    <Absent>
      This run recorded no {what} for this claim, and no guardrail answering it either. It did not
      get that far - which is not the same as a rule having closed the claim.
    </Absent>
  );
}

function Absent({ children }: { children: React.ReactNode }) {
  return <p className="absent">{children}</p>;
}

/**
 * What the model was offered, and what it was not.
 *
 * The narrowed enum is the project's most distinctive idea and the one no
 * product surface would ever show: an Action removed before the model was asked,
 * because the fact that would settle it cannot be checked here. Shown by
 * comparing the five Actions against the options the run recorded.
 */
function Withheld({ events }: { events: EventMessage[] }) {
  const call = firstEvent(events, "tool_call", "judge_denial");
  if (!call) {
    const fired = ruleThatFired(events);
    if (!fired) {
      return <Unfinished what="model call" />;
    }
    return (
      <Absent>
        No model was asked about this claim, so it was offered nothing:{" "}
        <strong>{fired.rule}</strong> answered it first — see Guardrails.
      </Absent>
    );
  }

  const offered = call.detail.options;
  if (!Array.isArray(offered)) {
    // Absent is not the same as empty. Defaulting to `[]` would have drawn all
    // five Actions struck through and asserted they were withheld, from a
    // record that said nothing at all.
    return <Absent>This run did not record which options the model was offered.</Absent>;
  }

  const every = Object.keys(ACTIONS);
  const missing = every.filter((action) => !offered.includes(action));
  // The reason is in the facts the model was given - `judgement` writes it there
  // so the model is told why an option is absent. Shown here rather than
  // pointed at: the rationale that also carries it is behind this panel.
  const facts = typeof call.detail.facts === "string" ? call.detail.facts : "";
  const why = facts
    .split("\n")
    .filter((line) => line.includes("not among your options"))
    .join(" ");

  return (
    <>
      <h4>What it was offered</h4>
      <div className="opts">
        {every.map((action) => (
          <span key={action} className={offered.includes(action) ? "opt" : "opt gone"}>
            {action}
          </span>
        ))}
      </div>
      {missing.length === 0 ? (
        <p>
          All {every.length} Actions were on the table. Nothing was removed for this denial.
        </p>
      ) : (
        <p>
          <strong>{missing.join(", ")}</strong> {missing.length === 1 ? "was" : "were"} struck from
          the options before the model was asked — not discouraged in the prompt, absent from the
          schema it had to answer with.
        </p>
      )}
      {missing.length > 0 &&
        (why ? (
          <p className="note">{why}</p>
        ) : (
          <p className="note">
            This run did not record why. The reason is normally in the facts the model was given.
          </p>
        ))}
    </>
  );
}

/**
 * Which rules ran, in order, and which one answered.
 *
 * This is what makes "guardrails run before any model call" checkable. The
 * absence of a model call proves the model was not asked; it says nothing about
 * whether the rules were consulted, or in what order.
 */
function Guardrails({ events }: { events: EventMessage[] }) {
  const trace = firstEvent(events, "guardrails");
  if (!trace) {
    return <Absent>This run did not record which guardrails ran.</Absent>;
  }

  const evaluated = trace.detail.evaluated;
  if (!Array.isArray(evaluated) || evaluated.length === 0) {
    // Same rule as above: an empty list would have printed "every rule passed",
    // which is a claim about how the Determination was reached.
    return <Absent>This run recorded a guardrail trace with no rules in it.</Absent>;
  }

  const rules = evaluated as RuleOutcome[];
  const fired = rules.find((rule) => rule.fired);

  return (
    <>
      <h4>Rules evaluated, in order</h4>
      <ol className="rules">
        {rules.map((rule) => (
          <li key={rule.rule} className={rule.fired ? "fired" : ""}>
            <span className="rule">{rule.rule}</span>
            <span className="verdict">
              {rule.fired ? `fired · ${rule.guardrail ?? "answered"}` : "passed"}
            </span>
          </li>
        ))}
      </ol>
      {fired ? (
        <p>
          A rule answered this claim, so <strong>no model was consulted at all</strong>. Rules after
          it never ran — the loop stops — which is why they are not listed. Expressed as a
          confidence threshold instead, a sufficiently confident model could have filed a void
          appeal.
        </p>
      ) : (
        <p>
          Every rule passed, so the question went to a model. The order is the safety property, and
          this is the record of it.
        </p>
      )}
    </>
  );
}

/** The facts put to the model, and the tool input that came back. */
function ModelExchange({ events }: { events: EventMessage[] }) {
  const call = firstEvent(events, "tool_call", "judge_denial");
  const result = firstEvent(events, "tool_result", "judge_denial");

  if (!call) {
    const fired = ruleThatFired(events);
    if (!fired) {
      return <Unfinished what="model exchange" />;
    }
    return (
      <Absent>
        No exchange. <strong>{fired.rule}</strong> answered this claim before any model call was
        made, and that absence is the point rather than a gap.
      </Absent>
    );
  }

  const facts = typeof call.detail.facts === "string" ? call.detail.facts : null;

  return (
    <>
      <h4>Facts put to the model</h4>
      {facts === null ? (
        // An empty box under "read off the extracted document" would assert a
        // property of a record that does not exist. Runs written before the
        // exchange was recorded have no facts to show.
        <Absent>This run did not record the facts the model was given.</Absent>
      ) : (
        <>
          <pre className="exchange">{facts}</pre>
          <p className="note">
            Read off the extracted document, not looked up from the fixtures. A misread code would
            be here, and the Determination would have been made on it.
          </p>
        </>
      )}
      <h4>What came back</h4>
      {result ? (
        <>
          <pre className="exchange">{JSON.stringify(result.detail.returned, null, 2)}</pre>
          {result.outcome !== "ok" && (
            <p className="note">
              Recorded <strong>{result.outcome}</strong>: the answer was outside the options it was
              given, so it was refused and fallen back from.
            </p>
          )}
        </>
      ) : (
        <Absent>The call was recorded but no result was.</Absent>
      )}
    </>
  );
}

/**
 * What the agent did in a browser.
 *
 * Screenshots are named for the `seq` of the event that references them, so an
 * image, its tool call and any absorbed retries share one key.
 */
function BrowserWork({ entry, runEvents }: { entry: QueueEntry; runEvents: EventMessage[] }) {
  // The agent's browser tools do not tag their events with a claim, so the
  // captures arrive at run level. Reading only the claim's own events made this
  // panel say "no browser work" however much of it a run had done.
  const all = [...entry.events, ...runEvents].sort((a, b) => a.seq - b.seq);
  const shots = all.filter((event) => event.screenshot);
  const retries = all.filter((event) => event.kind === "retry");

  if (shots.length === 0) {
    return (
      <Absent>
        This run recorded no browser work. An analysis run reads a committed document rather than
        fetching one, so there is nothing to show — which is not the same as a capture having gone
        missing.
      </Absent>
    );
  }

  return (
    <>
      <h4>Captured in sequence</h4>
      <div className="shots">
        {shots.map((event) => (
          <figure className="shot" key={event.seq}>
            <img
              src={`/runs/${entry.runId}/screenshots/${event.screenshot}`}
              alt={`${event.tool ?? event.kind} at step ${event.seq}`}
              loading="lazy"
            />
            <figcaption>
              seq {String(event.seq).padStart(4, "0")} · {event.tool ?? event.kind}
            </figcaption>
          </figure>
        ))}
      </div>
      {retries.length > 0 && (
        <p className="note">
          {retries.length} mechanical {retries.length === 1 ? "retry" : "retries"} absorbed inside
          the tools, never reaching the caller. Here because an auditor should see them, and out of
          the caller&rsquo;s hands because otherwise every caller would have to decide what to do
          about a retry that already worked.
        </p>
      )}
    </>
  );
}

function move(
  event: React.KeyboardEvent,
  current: Layer,
  select: (layer: Layer) => void,
): void {
  const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
  if (step === 0) {
    return;
  }
  event.preventDefault();
  const at = LAYERS.findIndex((tab) => tab.key === current);
  const next = LAYERS[(at + step + LAYERS.length) % LAYERS.length];
  if (next) {
    select(next.key);
    document.getElementById(`tab-${next.key}`)?.focus();
  }
}

export function Inspector({
  entry,
  runEvents,
  onClose,
}: {
  entry: QueueEntry;
  runEvents: EventMessage[];
  onClose: () => void;
}) {
  const [layer, setLayer] = useState<Layer>("withheld");

  useEffect(() => {
    // Dismissible without reaching for the mouse, and without disturbing the
    // claim underneath - the inspector is a second look at it, not a place.
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <aside className="inspector" aria-label={`How ${entry.claimId} was decided`}>
      <header className="insphead">
        <h3>Inspector</h3>
        <span className="id">{entry.claimId}</span>
        <button className="ghost" onClick={onClose}>
          Close
        </button>
      </header>

      <div className="tabs" role="tablist">
        {LAYERS.map((tab) => (
          <button
            key={tab.key}
            id={`tab-${tab.key}`}
            role="tab"
            aria-selected={tab.key === layer}
            aria-controls={`panel-${tab.key}`}
            // Only the selected tab is in the tab order; the arrow keys move
            // between them. A strip where every tab is a separate stop is the
            // half-implemented version of this pattern.
            tabIndex={tab.key === layer ? 0 : -1}
            className="tab"
            onClick={() => setLayer(tab.key)}
            onKeyDown={(event) => move(event, tab.key, setLayer)}
          >
            {tab.title}
          </button>
        ))}
      </div>

      <div
        className="panel"
        role="tabpanel"
        id={`panel-${layer}`}
        aria-labelledby={`tab-${layer}`}
        tabIndex={0}
      >
        {LAYERS.find((tab) => tab.key === layer)?.panel(entry, runEvents)}
      </div>
    </aside>
  );
}
