"""The agent loop that plans over the browser tools.

All model calls happen here, orchestrator-side. The Anthropic key is read in this
process and never reaches the sandbox, which runs the mocks and the analysis
kernel and has no idea a model is involved.
"""

from rcm_agent.agent.loop import AgentRun, PortalAccess, TokenUsage, work_the_portal
from rcm_agent.agent.model import HARD_JUDGEMENT, NAVIGATION, Escalation

__all__ = [
    "HARD_JUDGEMENT",
    "NAVIGATION",
    "AgentRun",
    "Escalation",
    "PortalAccess",
    "TokenUsage",
    "work_the_portal",
]
