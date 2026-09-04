# The hosted console: one committed example run, served by the same command a
# reviewer runs locally.
#
# Nothing here can start a run, and the image carries no Solari and no model
# credentials. That is guaranteed by the `COPY` lines below naming five paths
# rather than the tree — `.env` is not under any of them — with `.dockerignore`
# as a second line for the day someone writes `COPY . .`. The console has no
# route that reaches the agent either; `tests/test_hosted_console.py` enumerates
# them rather than promising it here. The agent's work is already done; this
# serves what it recorded.
#
# The run it serves is `docs/example-run`, produced by `rcm-agent
# publishable-run` and committed. One artifact for both, so there is one thing
# to inspect and one thing to trust rather than two that might differ.

FROM python:3.12-slim

# uv, because that is what the project builds with and `uv.lock` is the
# reproducible answer to "which versions".
#
# Installed with pip rather than copied out of `ghcr.io/astral-sh/uv`. The
# multi-stage copy is the idiomatic form and it is also two guesses - that the
# tag exists and that the binary sits where the copy expects - neither of which
# could be checked here, because no Docker daemon was available to build this.
# `pip install uv` has one stable interface and fails loudly if it cannot.
RUN pip install --no-cache-dir uv

WORKDIR /app

# The manifest first, so a change to the source does not re-resolve the world.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

COPY docs/example-run ./docs/example-run

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Verdicts go to a scratch disk, not into the image and not onto a volume.
# Named in the environment rather than only in the CMD so a deploy can point it
# somewhere else without editing this file.
# The free tier's disk resets when the instance wakes, which is how accumulated
# decisions clear themselves and every Reviewer arrives at a clean queue — the
# hosting doing the job a "reset demo" button would otherwise have to, and that
# button would have existed only here, which is a small lie to tell in a
# product surface.
ENV RCM_REVIEWS_DIR=/tmp/reviews

# Documentation only, and the default the CMD falls back to. The host assigns
# `$PORT` and does not read this.
EXPOSE 8090

# `$PORT` because the host assigns one. `--no-open` because there is no browser
# on this machine to open.
CMD ["sh", "-c", "rcm-agent console --host 0.0.0.0 --port ${PORT:-8090} --runs-dir docs/example-run --reviews-dir ${RCM_REVIEWS_DIR} --no-open"]
