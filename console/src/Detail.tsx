/**
 * One claim, opened: what the payer refused beside what the agent determined.
 *
 * Side by side because approving is a comparison - *do I agree with this
 * reading?* - and a screen that showed only the conclusion would be handing over
 * something to be waved through.
 *
 * The evidence list is a full-width band beneath the split, not a third column.
 * A live model's rationale runs past three hundred characters and an appeal asks
 * for ten items; at that size the two halves starve each other. The split
 * carries the comparison and evidence lives below it.
 */

import { ACTIONS } from "./actions";
import type { QueueEntry, ServiceLine } from "./claims";

function Lines({ lines }: { lines: ServiceLine[] }) {
  return (
    // Its own scroll container, so a wide table never makes the page scroll
    // sideways underneath everything else.
    <div className="scrollx">
      <table className="lines">
        <thead>
          <tr>
            <th>Ln</th>
            <th>HCPCS</th>
            <th>Adjustment</th>
            <th className="right">Amount</th>
          </tr>
        </thead>
        <tbody>
          {lines.flatMap((line) =>
            // A line the payer paid in full carries no adjustment, and dropping
            // it would quietly remove part of what the payer said - CONTEXT.md
            // is explicit that a Claim routinely mixes a paid line, a
            // written-off line and a denied line.
            line.adjustments.length === 0
              ? [
                  <tr key={`${line.line_number}-paid`}>
                    <td>{line.line_number}</td>
                    <td>
                      {line.procedure_code}
                      {line.charge !== null && <div className="muted">charge {line.charge}</div>}
                    </td>
                    <td className="muted">no adjustment</td>
                    <td className="right" />
                  </tr>,
                ]
              : line.adjustments.map((adjustment, index) => (
              <tr key={`${line.line_number}-${index}`}>
                <td>{line.line_number}</td>
                <td>
                  {line.procedure_code}
                  {/* `null` when the remittance never stated one. The server
                      decides that: it is a fact about a document, not a rule for
                      a browser to apply to a placeholder zero. */}
                  {line.charge !== null && <div className="muted">charge {line.charge}</div>}
                </td>
                <td>
                  <span className="codechip">
                    {adjustment.group}-{adjustment.reason_code}
                  </span>
                  {adjustment.remark_codes.length > 0 && (
                    <div className="muted">{adjustment.remark_codes.join(" ")}</div>
                  )}
                </td>
                <td className="right">{adjustment.amount}</td>
              </tr>
            )),
          )}
        </tbody>
      </table>
    </div>
  );
}

export function Detail({ entry, onClose }: { entry: QueueEntry; onClose: () => void }) {
  const { determination, claim } = entry;
  const governing = claim?.governing ?? null;

  return (
    <section className="detail" aria-label={`Claim ${entry.claimId}`}>
      <div className="facts">
        <span className="k">claim</span> <span className="id">{entry.claimId}</span>
        {claim && (
          <>
            <span className="sep">·</span>
            <span className="k">payer</span> <span>{claim.payer}</span>
            <span className="sep">·</span>
            <span className="k">patient</span> <span className="id">{claim.patient_id}</span>
            <span className="sep">·</span>
            <span className="k">dos</span> <span className="id">{claim.date_of_service}</span>
          </>
        )}
        {governing && (
          <>
            <span className="sep">·</span>
            <span className="codechip">
              {governing.group}-{governing.reason_code}
            </span>
            {governing.remark_codes.map((remark: string) => (
              <span className="codechip" key={remark}>
                {remark}
              </span>
            ))}
          </>
        )}
        <button className="ghost" onClick={onClose}>
          Close
        </button>
      </div>

      <div className="split">
        <div className="half">
          <h3>What the payer said</h3>
          {claim ? (
            <Lines lines={claim.service_lines} />
          ) : (
            <p className="muted">This run did not record the claim.</p>
          )}
        </div>

        <div className="half">
          <h3>What the agent determined</h3>
          {determination ? (
            <>
              {determination.guardrail && (
                <div className="badge">Closed by rule · {determination.guardrail}</div>
              )}
              <div className="verdict">
                <span className="big">{ACTIONS[determination.action].title}</span>
              </div>
              <p className={determination.guardrail ? "rationale cite ruled" : "rationale cite"}>
                {determination.rationale}
              </p>
              {determination.priority ? (
                <div className="score">
                  <div className="stat">
                    <div className="lab">At stake</div>
                    <div className="val">{determination.priority.amount_at_stake}</div>
                  </div>
                  {/* A recovery likelihood, never a confidence: it says what
                      this claim is worth chasing, not how sure anyone is of the
                      reading. Priority is a score; a guardrail is not, and this
                      tile never appears on one. */}
                  <div className="stat">
                    <div className="lab">Likelihood</div>
                    <div className="val">{determination.priority.likelihood.toFixed(2)}</div>
                  </div>
                  <div className="stat">
                    <div className="lab">Expected</div>
                    <div className="val">{determination.priority.expected_recovery}</div>
                  </div>
                </div>
              ) : determination.guardrail ? (
                // Not "0" and not a dash. A rule decided this, so nothing was
                // weighed - there is no score missing, there is no score.
                <p className="noscore">
                  No Priority. A rule decided this, so nothing was weighed — this is not a low
                  score, it is the absence of a judgement.
                </p>
              ) : (
                // Gated on the rule, not on the absent score. A close a *model*
                // judged also carries no Priority - a claim being abandoned has
                // nothing to rank - and saying a rule decided it would be the
                // screen asserting something untrue about how it was reached.
                <p className="noscore">
                  No Priority. This claim is being closed, so there is nothing to recover and
                  nothing to rank.
                </p>
              )}
            </>
          ) : (
            <p className="muted">Not determined yet.</p>
          )}
        </div>
      </div>

      {determination && determination.evidence_required.length > 0 && (
        <div className="ev">
          <h3>Evidence required · {determination.evidence_required.length} items</h3>
          <ol className="evlist">
            {determination.evidence_required.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}
