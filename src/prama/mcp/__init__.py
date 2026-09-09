"""Prama over MCP: read and propose, and nothing else.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.mcp.protocol import PROTOCOL_VERSION, Request, error, json_schema, result
from prama.mcp.server import INSTRUCTIONS, Server, serve_stdio

__all__ = [
    "INSTRUCTIONS",
    "PROTOCOL_VERSION",
    "Request",
    "Server",
    "error",
    "json_schema",
    "result",
    "serve_stdio",
]
