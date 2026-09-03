/**
 * A human's verdict on a Determination, and how the page records one.
 *
 * Fetched rather than streamed: a Review is not something the agent did, and the
 * socket carries a run's events. Putting it there would make one transport
 * describe two different things.
 *
 * Whether a verdict still `stands` is decided by the server, not here. A
 * verdict is given for one reading, and a re-run that changes the reading leaves
 * it over what its reviewer actually read; comparing digests in the browser
 * would put that safety rule in a second language.
 *
 * The digest goes with every request. It is this page saying *which*
 * Determination it was looking at, and it is the only thing standing between a
 * tab left open overnight and a verdict recorded against a reading that has
 * since been replaced.
 */

import type { Action } from "./claims";

export type Verdict = "approved" | "rejected";

export interface Review {
  claim_id: string;
  reviewed_at: string;
  reviewer: string;
  verdict: Verdict;
  reason: string;
  counter_action: Action | null;
  determination_digest: string;
  run_id: string;
  /** Whether it was given for the Determination that stands now. */
  stands: boolean;
}

export async function fetchReviews(): Promise<Map<string, Review>> {
  const response = await fetch("/reviews");
  if (!response.ok) {
    return new Map();
  }
  const body = (await response.json()) as Record<string, Review>;
  return new Map(Object.entries(body));
}

export interface Refused {
  /** What to tell the reviewer, in their words rather than the server's. */
  message: string;
}

export async function recordVerdict(
  claimId: string,
  body: {
    verdict: Verdict;
    reviewer: string;
    reason: string;
    counter_action: Action | null;
    determination_digest: string;
  },
): Promise<Review | Refused> {
  const response = await fetch(`/reviews/${encodeURIComponent(claimId)}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

  if (response.ok) {
    return (await response.json()) as Review;
  }

  // A refusal is an answer, not a failure. The two that matter say something a
  // reviewer can act on: reload, or give a reason.
  const detail = await response
    .json()
    .then((body: { detail?: unknown }) => (typeof body.detail === "string" ? body.detail : null))
    .catch(() => null);

  return {
    message:
      detail ??
      `The verdict was not recorded (${response.status}). Nothing has been written down.`,
  };
}
