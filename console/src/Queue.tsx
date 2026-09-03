/**
 * The queue as a table: what is worth working, and what a rule already settled.
 *
 * Two sections rather than one list with a sort. The difference between "low
 * value" and "not work" is the most important thing this console says, and a
 * single ranked list cannot say it.
 */

import { ACTIONS } from "./actions";
import {
  partition,
  type Action as ActionName,
  type CellState,
  type Phase,
  type QueueEntry,
} from "./claims";

function Action({ action }: { action: ActionName | null }) {
  if (!action) {
    return <span className="pill p-pending">··</span>;
  }
  return <span className={`pill p-${action}`}>{ACTIONS[action].abbreviation}</span>;
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


function Row({
  claim,
  ranked,
  phases,
  onOpen,
}: {
  claim: QueueEntry;
  ranked: boolean;
  phases: Phase[];
  onOpen: (claimId: string) => void;
}) {
  return (
    <button
      type="button"
      className={ranked ? "qrow" : "qrow norank"}
      onClick={() => onOpen(claim.claimId)}
      aria-label={`Open ${claim.claimId}`}
    >
      <span className="qmain">
        <span className="qtop">
          <span className="id">{claim.claimId}</span>
          <Action action={claim.action} />
        </span>
        <span className="sub">
          {claim.determination?.guardrail ?? claim.runId}
        </span>
      </span>
      <Phases cells={claim.cells} phases={phases} />
      {ranked && (
        <span className="amt">
          {claim.determination?.priority?.expected_recovery ?? "—"}
          {claim.determination?.priority && (
            <span className="sm">of {claim.determination.priority.amount_at_stake}</span>
          )}
        </span>
      )}
    </button>
  );
}

export function Queue({
  claims,
  phases,
  onOpen,
}: {
  claims: QueueEntry[];
  phases: Phase[];
  onOpen: (claimId: string) => void;
}) {
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
        <Row key={claim.claimId} claim={claim} ranked phases={phases} onOpen={onOpen} />
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
        <Row key={claim.claimId} claim={claim} ranked={false} phases={phases} onOpen={onOpen} />
      ))}
      <p className="rulenote">
        A rule decided these. No judgement was exercised and nothing was weighed,
        so they carry no score and are not ranked.
      </p>
    </div>
  );
}
