import { PHASES, partition, type Claim, type Phase } from "./claims";

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
  return <span className={`pill p-${action}`}>{ABBREVIATION[action] ?? "??"}</span>;
}

/**
 * The five phases as filled or hollow pips.
 *
 * `na` is drawn as a struck pip rather than a faint one: a claim a rule closed
 * has no EMR visit and no appeal package in its future, and a dimmer version of
 * "pending" would say the work is merely unimportant.
 */
function Phases({ cells }: { cells: Record<Phase, CellStateName> | null }) {
  return (
    <span className="cells">
      {PHASES.map((phase) => (
        <span key={phase} className={`cell c-${cells?.[phase] ?? "pending"}`} title={phase} />
      ))}
    </span>
  );
}

type CellStateName = "pending" | "running" | "done" | "na" | "failed";

function Row({ claim, ranked }: { claim: Claim; ranked: boolean }) {
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
      <Phases cells={claim.cells} />
      {ranked && (
        <span className="amt">
          {claim.priority ? claim.priority.expected_recovery : "—"}
          {claim.priority && <span className="sm">of {claim.priority.amount_at_stake}</span>}
        </span>
      )}
    </div>
  );
}

export function Queue({ claims }: { claims: Claim[] }) {
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
        <Row key={claim.claimId} claim={claim} ranked />
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
        <Row key={claim.claimId} claim={claim} ranked={false} />
      ))}
      <p className="rulenote">
        A rule decided these. No judgement was exercised and nothing was weighed,
        so they carry no score and are not ranked.
      </p>
    </div>
  );
}
