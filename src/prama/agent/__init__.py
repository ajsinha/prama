"""Agents: run the work where the data is, send findings, not data.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from prama.agent.capability import AgentCapabilities, Fitness, Unassignable, fits
from prama.agent.coordinator import Coordinator, ZoneWork, fleet_health
from prama.agent.identity import (
    AgentIdentity,
    AgentRegistry,
    AgentState,
    EnrolmentToken,
    sign_payload,
)
from prama.agent.protocol import (
    Assignment,
    Hello,
    Receipt,
    Refusal,
    Report,
    Response,
)
from prama.agent.residency import (
    Boundary,
    Redaction,
    ResidencyPolicy,
    SampleDisposition,
)
from prama.agent.runner import Agent, AgentOutcome
from prama.agent.spool import Gap, Spool

__all__ = [
    "Agent",
    "AgentCapabilities",
    "AgentIdentity",
    "AgentOutcome",
    "AgentRegistry",
    "AgentState",
    "Assignment",
    "Boundary",
    "Coordinator",
    "EnrolmentToken",
    "Fitness",
    "Gap",
    "Hello",
    "Receipt",
    "Redaction",
    "Refusal",
    "Report",
    "ResidencyPolicy",
    "Response",
    "SampleDisposition",
    "Spool",
    "Unassignable",
    "ZoneWork",
    "fits",
    "fleet_health",
    "sign_payload",
]
