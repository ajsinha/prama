"""The Language Server Protocol, framed and dispatched.

JSON-RPC 2.0 over a stream, with LSP's ``Content-Length`` framing. Small on
purpose: this file knows about messages and knows nothing about PQL, and
:mod:`prama.lsp.server` knows about PQL and nothing about framing. Anything that
mixed the two would be untestable without a subprocess, and an LSP server that
can only be tested through a subprocess is one whose edge cases are never tested.

The framing has one property worth stating, because getting it wrong produces a
hang rather than an error: the header block is separated from the body by a
blank line, the length is in **bytes** and not characters, and a client that
sent multibyte content would otherwise desynchronise the stream permanently
from the first accented character onwards.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any, BinaryIO

ENCODING = "utf-8"

#: JSON-RPC error codes the protocol defines. Named rather than inlined: a
#: client distinguishes them, and a server that returned -32603 for a malformed
#: request tells the client to retry something that will never work.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INTERNAL_ERROR = -32603


@dataclasses.dataclass(frozen=True, slots=True)
class Message:
    """One JSON-RPC message.

    ``id`` absent means a notification, which must **not** be answered. A server
    that replies to a notification desynchronises clients that count responses,
    and the symptom appears much later as a request answered with the wrong
    result.
    """

    method: str = ""
    params: dict[str, Any] = dataclasses.field(default_factory=dict)
    id: Any = None

    @property
    def is_notification(self) -> bool:
        return self.id is None


def read_message(stream: BinaryIO) -> Message | None:
    """The next message, or ``None`` at end of stream.

    ``None`` rather than an exception: a client that closed the pipe has exited,
    which is the ordinary way an editor session ends and not a failure to log.
    """
    length = _read_headers(stream)
    if length is None:
        return None
    body = stream.read(length)
    if not body:
        return None
    try:
        payload = json.loads(body.decode(ENCODING))
    except (ValueError, UnicodeDecodeError):
        return Message(method="$/malformed", params={})
    return Message(
        method=str(payload.get("method", "")),
        params=payload.get("params") or {},
        id=payload.get("id"),
    )


def write_message(stream: BinaryIO, payload: dict[str, Any]) -> None:
    # ensure_ascii=False so real UTF-8 goes on the wire, which is what the
    # spec says and what makes the byte length below load-bearing rather
    # than incidentally equal to the character count.
    body = json.dumps(payload, ensure_ascii=False).encode(ENCODING)
    # Bytes, not characters. A length in characters desynchronises the stream
    # permanently from the first multibyte character onwards, and the symptom
    # is a hang rather than an error.
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    stream.write(body)
    stream.flush()


def response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def notification(method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "method": method, "params": params}


def _read_headers(stream: BinaryIO) -> int | None:
    length: int | None = None
    while True:
        line = stream.readline()
        if not line:
            return None
        stripped = line.strip()
        if not stripped:
            # The blank line ends the header block. A header with no
            # Content-Length is unusable, and guessing a length here would read
            # into the next message.
            return length
        name, _, value = stripped.decode("ascii", "replace").partition(":")
        if name.strip().lower() == "content-length":
            try:
                length = int(value.strip())
            except ValueError:
                return None


__all__ = [
    "ENCODING",
    "INTERNAL_ERROR",
    "INVALID_REQUEST",
    "METHOD_NOT_FOUND",
    "PARSE_ERROR",
    "Message",
    "error",
    "notification",
    "read_message",
    "response",
    "write_message",
]
