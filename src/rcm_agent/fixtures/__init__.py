"""Generating the synthetic EOB documents the demo runs on.

The outputs are committed under `data/fixtures/`, so a run never depends on the
generator: a generator bug becomes a test failure rather than a demo failure.
The generator stays in the repo as the honest record of how the synthetic data
was constructed, and makes variants cheap when the difficulty needs tuning.

**Nothing is re-exported here on purpose.** Importing the generator pulls in
reportlab and Pillow, and `naming` lives in this package but is needed by the
mocks at run time — so a convenience re-export made `rcm_agent.fixtures.naming`
drag two rendering libraries behind it, and the mocks could not be imported in
the sandbox without installing dependencies they never use.
"""
