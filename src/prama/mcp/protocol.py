"""The MCP wire format, and nothing else.

JSON-RPC 2.0 messages, newline-delimited, over stdio. Implemented directly
rather than through the official SDK for one reason that outweighs the
convenience: Prama installs into air-gapped estates with everything vendored
and no build step, and this is roughly two hundred lines of JSON handling. A
dependency whose transitive tree has to be audited by a bank's security team is
a poor trade for code of this size.

The consequence is stated rather than hidden: when MCP's schema moves, this
moves by hand. The protocol version this build speaks is a constant below, and
a client asking for a different one is told so rather than quietly served
something else.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

#: The revision of MCP this build implements. Pinned, printed in the
#: handshake, and reported back to a client that asks for a different one — a
#: server that silently accepts any version negotiates nothing.
PROTOCOL_VERSION = "2025-06-18"

# JSON-RPC 2.0 reserved codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


@dataclasses.dataclass(frozen=True, slots=True)
class Request:
    """One incoming message.

    ``id`` is None for a notification, and the distinction is load-bearing: a
    notification must not be replied to, and replying anyway is how a client
    ends up waiting for a response to a message it has already forgotten.
    """

    method: str
    params: dict[str, Any] = dataclasses.field(default_factory=dict)
    id: Any = None

    @property
    def is_notification(self) -> bool:
        return self.id is None

    @classmethod
    def parse(cls, payload: dict[str, Any]) -> Request:
        method = payload.get("method")
        if not isinstance(method, str) or not method:
            raise ValueError("a JSON-RPC request needs a method")
        params = payload.get("params") or {}
        if not isinstance(params, dict):
            raise ValueError("params must be an object")
        return cls(method=method, params=params, id=payload.get("id"))


def result(request_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def error(
    request_id: Any, code: int, message: str, *, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    """A JSON-RPC error.

    ``data`` carries Prama's remedy. The taxonomy's whole point is that a
    failure says what to do next, and a protocol adapter that flattens it to a
    message string throws that away at the boundary where it is needed most —
    the caller is a model, and a model given a remedy retries correctly.
    """
    body: dict[str, Any] = {"code": code, "message": message}
    if data:
        body["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": body}


def json_schema(arguments: Any) -> dict[str, Any]:
    """A tool's arguments as the JSON Schema MCP expects.

    ``choices`` become an ``enum`` and ``maximum_length`` becomes
    ``maxLength``. Both matter more here than in a docstring: a model given an
    enum stops inventing dataset names, and a bounded string is a bounded
    injection surface.
    """
    properties: dict[str, Any] = {}
    required: list[str] = []
    for argument in arguments:
        schema: dict[str, Any] = {
            "type": "integer" if argument.kind == "integer" else "string",
            "description": argument.description,
        }
        if argument.choices:
            schema["enum"] = list(argument.choices)
        if argument.kind != "integer":
            schema["maxLength"] = argument.maximum_length
        properties[argument.name] = schema
        if argument.required:
            required.append(argument.name)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
