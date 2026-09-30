"""The Prama agent: a daemon beside the data that runs controls and reports findings.

Installed on its own (``pip install prama-agent``) on a machine that can reach
the data and the Prama server's HTTPS endpoint, and nothing else of Prama. It
depends on ``prama-kernel`` — the plan model, judge, evidence record, residency
and spool it shares with the server, so a verdict judged here is the verdict the
server would give — and on ``prama-sdk``, the only way it talks to the server.
It never imports the server (``prama``), and the server's build fails if it does.

    prama-agent enrol --server https://prama.example.com --token … --name eu-01 --state DIR
    prama-agent run --config /etc/prama-agent/agent.yaml

The guide is ``docs/agent/README.md`` in the Prama repository.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from prama_agent.config import AgentConfig, Source, load_config, parse_config
from prama_agent.daemon import EXIT_OK, EXIT_REFUSED, CycleResult, Daemon, capabilities_for
from prama_agent.executors import Executors, SqliteExecutor
from prama_agent.link import FleetLink, LinkUnavailable, SdkFleetLink
from prama_agent.runner import Agent, AgentOutcome
from prama_agent.state import Identity, load_identity, save_identity
from prama_agent.version import VERSION

__version__ = VERSION

__all__ = [
    "EXIT_OK",
    "EXIT_REFUSED",
    "VERSION",
    "Agent",
    "AgentConfig",
    "AgentOutcome",
    "CycleResult",
    "Daemon",
    "Executors",
    "FleetLink",
    "Identity",
    "LinkUnavailable",
    "SdkFleetLink",
    "Source",
    "SqliteExecutor",
    "capabilities_for",
    "load_config",
    "load_identity",
    "parse_config",
    "save_identity",
]
