/**
 * The queue as a table: what is worth working, and what a rule already settled.
 *
 * Two sections rather than one list with a sort. The difference between "low
 * value" and "not work" is the most important thing this console says, and a
 * single ranked list cannot say it.
 */

import { partition, type CellState, type Claim, type Phase } from "./claims";

/**
 * Two characters per Action, so the column never becomes the widest thing in a
 * row. Keyed on the glossary's five; an Action added there without being added
 * here renders its own name rather than a shrug, which is wrong on screen but
 * legible - and findable.
 */
const ABBREVIATION: Record<string, string> = {
  appeal: "AP",
  corrected_claim: "CC",
  rebill: "RB",
  patient_bill: "PB",
  close: "CL",
};

function Action({ action }: { action: string | null }) {
  if (!action) {
    return <span className="pill p-pending">··</span>;
  }
  return <span className={`pill p-${action}`}>{ABBREVIATION[action] ?? action}</span>;
}

/**
 * The five phases as filled or hollow pips.
 *
 * `na` is drawn as a struck pip rather than a faint one: a claim a rule closed
 * has no EMR visit and no appeal package in its future, and a dimmer version of
 * "pending" would say the work is merely unimportant.
 */
function Phases({ cells, phases }: { cells: Record<Phase, CellState> | null; phases: Phase[] }) {
  return (
    <span className="cells">
      {phases.map((phase) => (
        <span key={phase} className={`cell c-${cells?.[phase] ?? "pending"}`} title={phase} />
      ))}
    </span>
  );
}


function Row({ claim, ranked, phases }: { claim: Claim; ranked: boolean; phases: Phase[] }) {
  return (
    <div className={ranked ? "qrow" : "qrow norank"}>
      <span className="qmain">
        <span className="qtop">
          <span className="id">{claim.claimId}</span>
          <Action action={claim.action} />
        </span>
        <span className="sub">
          {claim.guardrail ? claim.guardrail : claim.runId}
        </span>
      </span>
      <Phases cells={claim.cells} phases={phases} />
      {ranked && (
        <span className="amt">
          {claim.priority ? claim.priority.expected_recovery : "—"}
          {claim.priority && <span className="sm">of {claim.priority.amount_at_stake}</span>}
        </span>
      )}
    </div>
  );
}

export function Queue({ claims, phases }: { claims: Claim[]; phases: Phase[] }) {
  const { ranked, ruled } = partition(claims);

  return (
    <div className="queue">
      <div className="sect">
        <h2>Work queue</h2>
        <span className="count">{ranked.length}</span>
      </div>
      <div className="colhead">
        <span>Claim</span>
        <span>Phases</span>
        <span className="right">Recovery</span>
      </div>
      {ranked.map((claim) => (
        <Row key={claim.claimId} claim={claim} ranked phases={phases} />
      ))}

      {/* Always visible, even when empty: the point is that the agent refused to
          appeal these, and a section that disappears makes that invisible. */}
      <div className="sect">
        <h2>Closed by rule</h2>
        <span className="count">{ruled.length}</span>
      </div>
      <div className="colhead norank">
        <span>Claim</span>
        <span>Phases</span>
      </div>
      {ruled.map((claim) => (
        <Row key={claim.claimId} claim={claim} ranked={false} phases={phases} />
      ))}
      <p className="rulenote">
        A rule decided these. No judgement was exercised and nothing was weighed,
        so they carry no score and are not ranked.
      </p>
    </div>
  );
}
