"""Steward agents: persistent AI agents that read, think through the gateway, and propose.

Separate from `prama.agent`, the execution agents that run compiled controls
and sign evidence. Nothing probabilistic belongs in that process, and a steward
never runs a control or writes evidence (docs/design/code-lineage §B1).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
