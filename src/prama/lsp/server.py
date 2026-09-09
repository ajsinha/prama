"""A Language Server for PQL.

Speaks LSP over stdio, so an editor that has never heard of Prama can offer
diagnostics, completion and hover over a ``.pql`` file. Every answer comes from
:mod:`prama.pql.analysis`, which is the same module the console's editor calls —
because two implementations of "is this column real" is how an editor comes to
underline something the compiler accepts, and the first time that happens people
stop reading the underlines.

**Where the catalogue comes from is a decision, not a detail.** A language
server that connected to a database would need credentials, would block the
editor while a query ran, and would silently offer nothing whenever the network
was down — which reads identically to "this estate declares nothing". So the
catalogue is supplied at construction: the CLI loads it once from a file, and a
server started without one says so on every unchecked control rather than
pretending the estate is empty.

Positions are the other thing to get right. LSP counts lines and characters from
**zero**; PQL's own positions count from one, as an editor displays them. The
conversion happens here, at the boundary, exactly once. Doing it in the analysis
module would make every other caller wrong.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sys
from typing import Any, BinaryIO

from prama.core.log import get_logger
from prama.lsp import protocol
from prama.pql.analysis import LanguageService
from prama.pql.types import Catalogue
from prama.version import VERSION

_log = get_logger(__name__)

#: Full sync. Incremental sync is a real optimisation for a large file and a
#: real source of drift for a small one: a server whose copy of the text has
#: diverged from the editor's reports diagnostics at the wrong lines, and the
#: symptom is indistinguishable from a bad parser. PQL files are suites, not
#: source trees; the whole text is cheap.
TEXT_DOCUMENT_SYNC_FULL = 1


class PqlLanguageServer:
    """The dispatch loop, and one method per LSP request it answers."""

    def __init__(
        self,
        *,
        catalogue: Catalogue | None = None,
        catalogue_source: str = "",
    ) -> None:
        self._service = LanguageService(catalogue)
        #: Where the catalogue came from, said out loud in the server's
        #: initialisation reply. A client whose completions are empty needs to
        #: know whether the estate is empty or the server was started without it.
        self._catalogue_source = catalogue_source
        self._documents: dict[str, str] = {}
        self._shutdown_requested = False

    # -- the loop -----------------------------------------------------------

    def serve(self, stdin: BinaryIO, stdout: BinaryIO) -> int:
        """Read, dispatch, write, until the client goes away."""
        while True:
            message = protocol.read_message(stdin)
            if message is None:
                return 0
            for reply in self.handle(message):
                protocol.write_message(stdout, reply)
            if message.method == "exit":
                # The protocol's own answer to "did the client mean to leave":
                # exiting after shutdown is 0, exiting without it is 1, and a
                # server that returned 0 either way loses the only signal that
                # an editor crashed.
                return 0 if self._shutdown_requested else 1

    def handle(self, message: protocol.Message) -> list[dict[str, Any]]:
        """Everything to send in response to one message.

        A list, because a single ``didChange`` produces no response and one
        diagnostics notification, while a request produces exactly one response.
        Returning a list rather than an optional makes the notification path a
        normal case instead of a special one.
        """
        handler = getattr(self, "_" + message.method.replace("/", "_").replace("$", "dollar"), None)
        if handler is None:
            if message.is_notification:
                # Unknown notifications are ignored, per the protocol. Replying
                # to one desynchronises clients that count responses.
                _log.debug("ignoring notification %s", message.method)
                return []
            return [
                protocol.error(
                    message.id,
                    protocol.METHOD_NOT_FOUND,
                    f"prama-lsp does not implement {message.method}",
                )
            ]
        try:
            replies: list[dict[str, Any]] = handler(message)
            return replies
        except Exception as exc:  # a server that dies takes the editor's session
            _log.exception("handling %s failed", message.method)
            if message.is_notification:
                return []
            return [protocol.error(message.id, protocol.INTERNAL_ERROR, str(exc))]

    # -- lifecycle ----------------------------------------------------------

    def _initialize(self, message: protocol.Message) -> list[dict[str, Any]]:
        return [
            protocol.response(
                message.id,
                {
                    "capabilities": {
                        "textDocumentSync": TEXT_DOCUMENT_SYNC_FULL,
                        "completionProvider": {"triggerCharacters": ["."]},
                        "hoverProvider": True,
                    },
                    "serverInfo": {
                        "name": "prama-pql",
                        "version": VERSION,
                        # Not a capability, but the thing a user needs when
                        # completion comes back empty: whether the estate is
                        # empty or the server was started without it.
                        "catalogue": self._catalogue_description(),
                    },
                },
            )
        ]

    def _initialized(self, _message: protocol.Message) -> list[dict[str, Any]]:
        return []

    def _shutdown(self, message: protocol.Message) -> list[dict[str, Any]]:
        # Named for the protocol's method, so dispatch finds it by construction.
        # The flag it sets is _shutdown_requested: an attribute of the same name
        # would shadow this handler and getattr would return a boolean the loop
        # then tries to call.
        self._shutdown_requested = True
        return [protocol.response(message.id, None)]

    def _exit(self, _message: protocol.Message) -> list[dict[str, Any]]:
        return []

    def _dollar_malformed(self, _message: protocol.Message) -> list[dict[str, Any]]:
        return []

    # -- documents ----------------------------------------------------------

    def _textDocument_didOpen(  # noqa: N802 - the protocol's own spelling
        self, message: protocol.Message
    ) -> list[dict[str, Any]]:
        document = message.params.get("textDocument") or {}
        uri = str(document.get("uri", ""))
        self._documents[uri] = str(document.get("text", ""))
        return [self._diagnostics_for(uri)]

    def _textDocument_didChange(  # noqa: N802
        self, message: protocol.Message
    ) -> list[dict[str, Any]]:
        uri = str((message.params.get("textDocument") or {}).get("uri", ""))
        changes = message.params.get("contentChanges") or []
        if changes:
            self._documents[uri] = str(changes[-1].get("text", ""))
        return [self._diagnostics_for(uri)]

    def _textDocument_didClose(  # noqa: N802
        self, message: protocol.Message
    ) -> list[dict[str, Any]]:
        uri = str((message.params.get("textDocument") or {}).get("uri", ""))
        self._documents.pop(uri, None)
        # Cleared explicitly. Diagnostics left behind on a closed file reappear
        # in the editor's problem list with no way to make them go away.
        return [
            protocol.notification(
                "textDocument/publishDiagnostics", {"uri": uri, "diagnostics": []}
            )
        ]

    # -- language features --------------------------------------------------

    def _textDocument_completion(  # noqa: N802
        self, message: protocol.Message
    ) -> list[dict[str, Any]]:
        text, line, column = self._at(message)
        items = self._service.completions(text, line, column)
        return [
            protocol.response(
                message.id,
                {
                    # Not incomplete: this list is everything the estate can
                    # satisfy, and marking it incomplete would have the editor
                    # re-ask on every keystroke for an answer that will not
                    # change.
                    "isIncomplete": False,
                    "items": [
                        {
                            "label": item.label,
                            "kind": item.kind,
                            "detail": item.detail,
                            "documentation": item.documentation,
                        }
                        for item in items
                    ],
                },
            )
        ]

    def _textDocument_hover(  # noqa: N802
        self, message: protocol.Message
    ) -> list[dict[str, Any]]:
        text, line, column = self._at(message)
        hover = self._service.hover(text, line, column)
        if hover.is_empty:
            # Null, not an empty string. An empty hover box that follows the
            # cursor around is worse than none.
            return [protocol.response(message.id, None)]
        return [
            protocol.response(
                message.id,
                {"contents": {"kind": "markdown", "value": hover.markdown()}},
            )
        ]

    # -- helpers ------------------------------------------------------------

    def _at(self, message: protocol.Message) -> tuple[str, int, int]:
        """The document and a one-based position.

        LSP counts from zero and PQL counts from one. Converted here, once, at
        the boundary — doing it inside the analysis would make every other
        caller of that module wrong by one.
        """
        uri = str((message.params.get("textDocument") or {}).get("uri", ""))
        position = message.params.get("position") or {}
        return (
            self._documents.get(uri, ""),
            int(position.get("line", 0)) + 1,
            int(position.get("character", 0)) + 1,
        )

    def _diagnostics_for(self, uri: str) -> dict[str, Any]:
        text = self._documents.get(uri, "")
        out = []
        for diagnostic in self._service.diagnostics(text):
            if not diagnostic.has_position:
                # Reported at the top of the file *and said to be*, rather than
                # underlining line one as though the problem were there. An
                # editor given a guessed range sends the reader to the wrong
                # place, which is worse than no range at all.
                message = f"{diagnostic.message} (no position in the source)"
                start = {"line": 0, "character": 0}
                end = {"line": 0, "character": 0}
            else:
                message = diagnostic.message
                start = {
                    "line": diagnostic.line - 1,
                    "character": max(0, diagnostic.column - 1),
                }
                end = {
                    "line": diagnostic.line - 1,
                    "character": max(0, diagnostic.column - 1) + max(1, diagnostic.length),
                }
            if diagnostic.remedy:
                message = f"{message}\n{diagnostic.remedy}"
            out.append(
                {
                    "range": {"start": start, "end": end},
                    "severity": diagnostic.severity,
                    "source": "prama",
                    "message": message,
                }
            )
        return protocol.notification(
            "textDocument/publishDiagnostics", {"uri": uri, "diagnostics": out}
        )

    def _catalogue_description(self) -> str:
        count = len(self._service.catalogue.datasets)
        if not count:
            return (
                "no catalogue: nothing will be checked against a schema, and "
                "completion offers keywords and functions only. Start with "
                "--catalogue to change that."
            )
        return f"{count} dataset(s) from {self._catalogue_source or 'the caller'}"


def serve_stdio(*, catalogue: Catalogue | None = None, catalogue_source: str = "") -> int:
    """Run a server on this process's stdin and stdout."""
    server = PqlLanguageServer(catalogue=catalogue, catalogue_source=catalogue_source)
    return server.serve(sys.stdin.buffer, sys.stdout.buffer)


__all__ = ["TEXT_DOCUMENT_SYNC_FULL", "PqlLanguageServer", "serve_stdio"]
