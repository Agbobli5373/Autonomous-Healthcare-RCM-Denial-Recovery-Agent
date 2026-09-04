# The hosted console sleeps, and its verdicts are meant to disappear

A reviewer opens a URL and uses the console for real: works the queue, reads the
determinations, opens the inspector, approves and rejects. It runs on a free
tier that goes to sleep when nobody is using it. **That is the design, not a
limitation being absorbed.**

## Why an exported run rather than a live one

The agent's work is already done before the host ever sees it. A run needs
Solari credentials and a sandbox, and a hosted console cannot start one per
visitor — so it serves `docs/example-run`, produced by `rcm-agent
publishable-run` and committed. The same artifact the repository commits is the
one the host serves, so there is one thing to inspect and one thing to trust.

No Solari and no model credentials are deployed. `.dockerignore` keeps `.env`
out of the build context entirely rather than out of the image, because a layer
that never sees it cannot leak it however the Dockerfile is later edited, and
`tests/test_hosted_console.py` enumerates the served routes rather than
promising anything about them in prose.

## Why sleeping solves a problem instead of causing one

Recording a Review is a filesystem write, so several people using one instance
share a queue. Left running, the third visitor would arrive at two strangers'
decisions.

The free tier's disk resets when the instance wakes, so accumulated verdicts
clear themselves and each Reviewer arrives at a clean queue. **The volume has to
be writable, not persistent** — a scratch disk is not a compromise here, it is
the mechanism. Recorded verdicts go to `/tmp/reviews`.

This is also why there is no "reset demo" control. A button that existed only in
the hosted build would be a small lie to tell in a product surface, and the
hosting already does its job.

## Why the cold start needs a second host

Waking takes about half a minute, and **while the instance is asleep it serves
nothing at all** — no markup it could serve helps, because it is not running to
serve it. A reader arriving from an application and meeting a blank tab
concludes the demo is broken.

So `docs/hosting/waking.html` is a single self-contained file with no build step
and no requests for assets, hosted somewhere that does not sleep. It paints on
the first byte, says how long the wait is and what will be there, polls the
console's `/healthz`, and forwards when it answers. `/healthz` is the one route
that sends an allow-origin header, because that page reads it cross-origin;
`no-cors` would resolve on the platform's own error page and forward to a
console that is not there.

The page also carries a `?console=` override, restricted to local addresses. A
public page on a trusted domain that forwards wherever a link tells it is an
open redirect, and the convenience of pointing it at a development console is
not worth handing that out.

## What this does not decide

Whether the repository is public. Hosting an exported artifact is independent of
that gate, and precedes it.
