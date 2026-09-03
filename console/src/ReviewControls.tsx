/**
 * Approving or rejecting a Determination.
 *
 * The console's reason to exist, and the one act on this screen that writes
 * anything down. Three rules shape it, and each of them is a decision recorded
 * elsewhere rather than a preference:
 *
 * A claim a rule closed gets **no control at all**. A rule was never a
 * judgement, so asking for a verdict would invent a decision that does not
 * exist and quietly reframe a rule as an opinion.
 *
 * A verdict is signed. Nothing verifies the name - there is no sign-in yet, and
 * that is #72's business - so it is a signature rather than an identity. An
 * unverified name still answers "who approved this"; the first version recorded
 * every verdict as `console`, and the record could not.
 *
 * A rejection **must** carry a reason. A rejected appeal that vanishes teaches
 * nobody anything, and the reasons are the only evidence that would ever improve
 * the agent.
 *
 * A verdict is shown as standing only where its digest matches the Determination
 * on screen. A re-run that changes the reading leaves the old verdict over what
 * its reviewer actually read; showing it as current would assert a sign-off
 * nobody gave, which is the failure the digest exists to prevent, arriving
 * through the screen rather than through the write path.
 *
 * And the screen says plainly that **nothing yet acts on this**. Filing an
 * approved appeal is a separate effort; a reviewer who clicks Approve and
 * expects an agent to move has been misled by the button.
 */

import { useState } from "react";

import { ACTIONS } from "./actions";
import type { Action, QueueEntry } from "./claims";
import { recordVerdict, type Review } from "./reviews";

const REVIEWER = "rcm.reviewer";

/** Kept so a reviewer types their name once a session rather than once a claim. */
function remembered(): string {
  try {
    return localStorage.getItem(REVIEWER) ?? "";
  } catch {
    // Private browsing, or storage disabled. A forgotten name is a nuisance;
    // a screen that will not render is worse.
    return "";
  }
}

function remember(name: string, set: (name: string) => void) {
  set(name);
  try {
    localStorage.setItem(REVIEWER, name);
  } catch {
    // As above - the verdict still records the name, it is only not remembered.
  }
}

function Recorded({ review }: { review: Review }) {
  return (
    <div className="recorded">
      <div>
        <span className="k">Review recorded</span> <strong>{review.verdict}</strong> by{" "}
        {review.reviewer}
        {review.reason && <> — {review.reason}</>}
        {review.counter_action && (
          <> (would have chosen {ACTIONS[review.counter_action].title})</>
        )}
      </div>
      <div className="k">Determination digest</div>
      <div className="digest">sha256:{review.determination_digest}</div>
      <p className="note">
        A re-run producing a different Determination invalidates this verdict rather than filing
        against it.
      </p>
    </div>
  );
}

export function ReviewControls({
  entry,
  digest,
  review,
  onRecorded,
}: {
  entry: QueueEntry;
  digest: string | null;
  review: Review | null;
  onRecorded: (review: Review) => void;
}) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [counterAction, setCounterAction] = useState<Action | "">("");
  const [refusal, setRefusal] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reviewer, setReviewer] = useState(() => remembered());

  if (entry.guardrailed) {
    // No control, not a disabled one. A disabled button says "you may not do
    // this"; the truth is that there is nothing here to decide.
    return (
      <div className="actions">
        <span className="note">Nothing to review — a rule decided this.</span>
      </div>
    );
  }

  // `stands` is the server's answer, not a comparison made here: the rule lives
  // in one language, next to the tests that hold it. `reviewed()` refuses a stale
  // verdict and the POST answers 409; rendering one as current would make the
  // same false claim silently, which is the worse of the two.
  if (review?.stands) {
    return <Recorded review={review} />;
  }

  // Bound to a const so the narrowing survives into the closure below: a prop
  // could in principle change, and TypeScript is right not to assume it will not.
  const seen = digest;
  const determination = entry.determination;
  if (!determination || seen === null) {
    return (
      <div className="actions">
        <span className="note">Not determined yet, so there is nothing to approve.</span>
      </div>
    );
  }

  // An arrow bound after the guard, not a hoisted declaration: a hoisted one is
  // analysed before the narrowing above and cannot see it.
  // Cancel discards the draft rather than hiding it. Left standing, a reason and
  // a counter-action typed into a rejection travelled into the approval clicked
  // next - an approval carrying a disagreement inside it.
  const abandon = () => {
    setRejecting(false);
    setReason("");
    setCounterAction("");
  };

  const send = async (verdict: "approved" | "rejected") => {
    setBusy(true);
    setRefusal(null);
    const result = await recordVerdict(entry.claimId, {
      verdict,
      reviewer: reviewer.trim(),
      reason: reason.trim(),
      // A counter-action belongs to a rejection: it names what the Reviewer
      // would have chosen instead, and there is no instead in an agreement.
      counter_action: verdict === "rejected" ? counterAction || null : null,
      determination_digest: seen,
    });
    setBusy(false);
    if ("message" in result) {
      setRefusal(result.message);
      return;
    }
    onRecorded(result);
  };

  return (
    <div className="review">
      {refusal && (
        <p className="refusal" role="alert">
          {refusal}
        </p>
      )}

      {review && (
        <p className="superseded">
          A re-run has replaced the Determination {review.reviewer} marked{" "}
          <strong>{review.verdict}</strong>. That verdict stands over what they read, not over
          this — so this reading is unreviewed.
        </p>
      )}

      <label className="field who">
        <span className="k">Recorded by</span>
        <input
          value={reviewer}
          onChange={(event) => remember(event.target.value, setReviewer)}
          placeholder="your name"
        />
      </label>

      {rejecting ? (
        <div className="rejecting">
          <label className="field">
            <span className="k">Why</span>
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="What the agent got wrong, in a sentence."
              rows={2}
            />
          </label>
          <label className="field">
            <span className="k">Would have chosen</span>
            <select
              value={counterAction}
              onChange={(event) => setCounterAction(event.target.value as Action | "")}
            >
              <option value="">— not saying —</option>
              {Object.entries(ACTIONS).map(([action, { title }]) => (
                <option key={action} value={action}>
                  {title}
                </option>
              ))}
            </select>
          </label>
          <div className="actions">
            <button
              className="btn"
              disabled={busy || reason.trim() === "" || reviewer.trim() === ""}
              onClick={() => void send("rejected")}
            >
              Record rejection
            </button>
            <button className="ghost" onClick={abandon}>
              Cancel
            </button>
            {reason.trim() === "" && (
              <span className="note">A rejection needs a reason — it is the only thing that
                would ever improve the agent.</span>
            )}
          </div>
        </div>
      ) : (
        <div className="actions">
          <button
            className="btn primary"
            disabled={busy || reviewer.trim() === ""}
            onClick={() => void send("approved")}
          >
            Approve {ACTIONS[determination.action]?.title.toLowerCase()}
          </button>
          <button
            className="btn"
            disabled={busy || reviewer.trim() === ""}
            onClick={() => setRejecting(true)}
          >
            Reject
          </button>
          <span className="note">
            Recording a verdict is all this does. Nothing files it — that is a separate piece of
            work, and this screen would be lying if it implied otherwise.
          </span>
        </div>
      )}
    </div>
  );
}
