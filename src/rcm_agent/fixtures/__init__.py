"""Generating the synthetic EOB documents the demo runs on.

The outputs are committed under `data/fixtures/`, so a run never depends on the
generator: a generator bug becomes a test failure rather than a demo failure.
The generator stays in the repo as the honest record of how the synthetic data
was constructed, and makes variants cheap when the difficulty needs tuning.
"""

from rcm_agent.fixtures.generate import generate_fixtures
from rcm_agent.fixtures.spec import CLAIMS, ClaimSpec, LineSpec

__all__ = ["CLAIMS", "ClaimSpec", "LineSpec", "generate_fixtures"]
