"""The PQL language server.

Driven through ``handle`` rather than a subprocess, which is why the protocol
layer is a separate module: a server that could only be tested by launching a
process is one whose edge cases are never tested.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import io
import json

import pytest

from prama.lsp import PqlLanguageServer, protocol
from prama.pql.types import Catalogue

URI = "file:///suite.pql"
GOOD = "CHECK positions.notional IS NOT NULL SEVERITY critical DIMENSION completeness BECAUSE 'CDE'"
CATALOGUE = Catalogue.of(positions={"notional": "DECIMAL(18,2)", "account_id": "VARCHAR(32)"})


@pytest.fixture
def server() -> PqlLanguageServer:
    return PqlLanguageServer(catalogue=CATALOGUE, catalogue_source="a test")


def _send(server: PqlLanguageServer, method: str, params=None, request_id=None):
    return server.handle(protocol.Message(method=method, params=params or {}, id=request_id))


def _open(server: PqlLanguageServer, text: str = GOOD):
    return _send(server, "textDocument/didOpen", {"textDocument": {"uri": URI, "text": text}})


class TestLifecycle:
    def test_it_advertises_what_it_can_do(self, server: PqlLanguageServer) -> None:
        [reply] = _send(server, "initialize", {}, 1)
        capabilities = reply["result"]["capabilities"]
        assert capabilities["hoverProvider"] is True
        assert "." in capabilities["completionProvider"]["triggerCharacters"]

    def test_it_says_where_its_catalogue_came_from(self, server: PqlLanguageServer) -> None:
        """A client whose completions are empty needs to know whether the estate
        is empty or the server was started without it."""
        [reply] = _send(server, "initialize", {}, 1)
        assert "1 dataset(s) from a test" in reply["result"]["serverInfo"]["catalogue"]

    def test_no_catalogue_says_nothing_is_schema_checked(self) -> None:
        [reply] = _send(PqlLanguageServer(), "initialize", {}, 1)
        note = reply["result"]["serverInfo"]["catalogue"]
        assert "no catalogue" in note
        assert "--catalogue" in note

    def test_an_unknown_request_is_refused_not_ignored(self, server: PqlLanguageServer) -> None:
        [reply] = _send(server, "textDocument/rename", {}, 7)
        assert reply["error"]["code"] == protocol.METHOD_NOT_FOUND

    def test_an_unknown_notification_is_ignored(self, server: PqlLanguageServer) -> None:
        """Replying to a notification desynchronises clients that count
        responses, and the symptom appears much later as a request answered
        with the wrong result."""
        assert _send(server, "$/setTrace", {"value": "off"}) == []

    def test_a_handler_that_raises_answers_rather_than_dying(
        self, server: PqlLanguageServer
    ) -> None:
        """A server that dies takes the editor's session with it."""
        [reply] = _send(server, "textDocument/hover", {"position": "not a dict"}, 3)
        assert reply["error"]["code"] == protocol.INTERNAL_ERROR

    def test_exiting_without_shutdown_is_a_nonzero_status(self) -> None:
        """The only signal an editor has that the server crashed rather than
        being asked to stop."""
        server = PqlLanguageServer(catalogue=CATALOGUE)
        stream = io.BytesIO()
        for payload in ({"jsonrpc": "2.0", "method": "exit"},):
            protocol.write_message(stream, payload)
        stream.seek(0)
        assert server.serve(stream, io.BytesIO()) == 1

    def test_exiting_after_shutdown_is_zero(self) -> None:
        server = PqlLanguageServer(catalogue=CATALOGUE)
        stream = io.BytesIO()
        protocol.write_message(stream, {"jsonrpc": "2.0", "id": 1, "method": "shutdown"})
        protocol.write_message(stream, {"jsonrpc": "2.0", "method": "exit"})
        stream.seek(0)
        assert server.serve(stream, io.BytesIO()) == 0


class TestDiagnostics:
    def test_opening_a_clean_file_publishes_an_empty_list(self, server: PqlLanguageServer) -> None:
        """Published, not withheld. An editor holding stale diagnostics after a
        fix shows problems that are not there."""
        [message] = _open(server)
        assert message["method"] == "textDocument/publishDiagnostics"
        assert message["params"]["diagnostics"] == []

    def test_a_typo_is_underlined_where_it_is(self, server: PqlLanguageServer) -> None:
        [message] = _open(server, GOOD.replace("notional", "notionl"))
        [found] = message["params"]["diagnostics"]
        assert found["severity"] == 1
        # Zero-based, as LSP counts. The conversion happens once, here.
        assert found["range"]["start"]["line"] == 0
        assert found["range"]["start"]["character"] == 16
        assert found["range"]["end"]["character"] == 23

    def test_the_remedy_is_carried_into_the_message(self, server: PqlLanguageServer) -> None:
        """LSP has nowhere else to put it, and a diagnostic that names a
        problem without naming the fix is one somebody has to ask about."""
        [message] = _open(server, GOOD.replace("notional", "notionl"))
        [found] = message["params"]["diagnostics"]
        assert "notional" in found["message"].split("\n", 1)[1]

    def test_an_unlocated_diagnostic_says_so_rather_than_pointing_at_line_one(
        self, server: PqlLanguageServer, monkeypatch
    ) -> None:
        """An editor given a guessed range sends the reader to the wrong place,
        which is worse than no range at all.

        Constructed rather than provoked: every finding the checker and the
        linter currently produce carries a position, so this guards the
        conversion against the first one that does not, not a live path.
        """
        from prama.pql.analysis import Diagnostic

        monkeypatch.setattr(
            server._service,
            "diagnostics",
            lambda _text: [Diagnostic(message="something is wrong", level="warning")],
        )
        [message] = _open(server, GOOD)
        [found] = message["params"]["diagnostics"]
        assert "(no position in the source)" in found["message"]
        assert found["range"]["start"] == {"line": 0, "character": 0}
        assert found["range"]["end"] == {"line": 0, "character": 0}

    def test_every_finding_the_checker_produces_today_is_located(
        self, server: PqlLanguageServer
    ) -> None:
        """Stated as a fact about now, so the test above is honestly labelled
        as a guard rather than as coverage of something reachable."""
        texts = [
            GOOD.replace("notional", "notionl"),
            GOOD.replace("'CDE'", "''"),
            "CHECK ledger.amount IS NOT NULL SEVERITY major DIMENSION completeness BECAUSE 'x'",
        ]
        for text in texts:
            found = server._service.diagnostics(text)
            assert found, text
            assert all(d.has_position for d in found), text

    def test_an_undeclared_dataset_is_information_not_a_warning(
        self, server: PqlLanguageServer
    ) -> None:
        """A warning says "probably wrong"; this says "nobody has looked", and
        rendering the second as the first trains people to dismiss both."""
        [message] = _open(
            server,
            "CHECK ledger.amount IS NOT NULL SEVERITY major DIMENSION completeness BECAUSE 'x'",
        )
        assert all(d["severity"] == 3 for d in message["params"]["diagnostics"])

    def test_editing_republishes(self, server: PqlLanguageServer) -> None:
        _open(server, GOOD.replace("notional", "notionl"))
        [message] = _send(
            server,
            "textDocument/didChange",
            {"textDocument": {"uri": URI}, "contentChanges": [{"text": GOOD}]},
        )
        assert message["params"]["diagnostics"] == []

    def test_closing_clears_them(self, server: PqlLanguageServer) -> None:
        """Diagnostics left behind on a closed file sit in the editor's problem
        list with no way to make them go away."""
        _open(server, GOOD.replace("notional", "notionl"))
        [message] = _send(server, "textDocument/didClose", {"textDocument": {"uri": URI}})
        assert message["params"]["diagnostics"] == []


class TestCompletionAndHover:
    def test_completion_after_a_dot_offers_declared_columns(
        self, server: PqlLanguageServer
    ) -> None:
        _open(server, "CHECK positions.")
        [reply] = _send(
            server,
            "textDocument/completion",
            {"textDocument": {"uri": URI}, "position": {"line": 0, "character": 16}},
            2,
        )
        assert [i["label"] for i in reply["result"]["items"]] == ["notional", "account_id"]

    def test_the_list_is_not_marked_incomplete(self, server: PqlLanguageServer) -> None:
        """Marking it incomplete has the editor re-ask on every keystroke for
        an answer that will not change."""
        _open(server, "CHECK positions.")
        [reply] = _send(
            server,
            "textDocument/completion",
            {"textDocument": {"uri": URI}, "position": {"line": 0, "character": 16}},
            2,
        )
        assert reply["result"]["isIncomplete"] is False

    def test_hover_returns_markdown(self, server: PqlLanguageServer) -> None:
        _open(server)
        [reply] = _send(
            server,
            "textDocument/hover",
            {"textDocument": {"uri": URI}, "position": {"line": 0, "character": 19}},
            3,
        )
        assert reply["result"]["contents"]["kind"] == "markdown"
        assert "positions.notional" in reply["result"]["contents"]["value"]

    def test_hover_over_nothing_is_null(self, server: PqlLanguageServer) -> None:
        """An empty hover box that follows the cursor around is worse than
        none."""
        _open(server, "     ")
        [reply] = _send(
            server,
            "textDocument/hover",
            {"textDocument": {"uri": URI}, "position": {"line": 0, "character": 2}},
            3,
        )
        assert reply["result"] is None


class TestFraming:
    def test_a_message_survives_a_round_trip(self) -> None:
        stream = io.BytesIO()
        protocol.write_message(stream, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        stream.seek(0)
        message = protocol.read_message(stream)
        assert message is not None
        assert message.method == "initialize"
        assert message.id == 1

    def test_the_length_is_in_bytes_not_characters(self) -> None:
        """A length in characters desynchronises the stream permanently from the
        first multibyte character onwards, and the symptom is a hang rather than
        an error."""
        stream = io.BytesIO()
        protocol.write_message(stream, {"method": "x", "params": {"text": "café — ✓"}})
        raw = stream.getvalue()
        header, _, body = raw.partition(b"\r\n\r\n")
        declared = int(header.split(b":")[1])
        assert declared == len(body)
        assert declared != len(body.decode("utf-8"))

    def test_two_messages_read_in_order(self) -> None:
        stream = io.BytesIO()
        protocol.write_message(stream, {"method": "first"})
        protocol.write_message(stream, {"method": "second"})
        stream.seek(0)
        assert protocol.read_message(stream).method == "first"
        assert protocol.read_message(stream).method == "second"
        assert protocol.read_message(stream) is None

    def test_a_closed_stream_is_none_not_an_exception(self) -> None:
        """A client that closed the pipe has exited, which is how an editor
        session ordinarily ends and not a failure to log."""
        assert protocol.read_message(io.BytesIO()) is None

    def test_malformed_json_does_not_kill_the_loop(self) -> None:
        body = b"{not json"
        stream = io.BytesIO(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        message = protocol.read_message(stream)
        assert message is not None
        assert message.method == "$/malformed"

    def test_a_notification_is_recognised_by_the_absent_id(self) -> None:
        assert protocol.Message(method="exit").is_notification
        assert not protocol.Message(method="initialize", id=0).is_notification


class TestTheCatalogueFile:
    def test_a_missing_file_is_refused_rather_than_read_as_empty(self, tmp_path) -> None:
        """An empty catalogue silently turns every schema check off, and the
        editor then shows a clean file that has not been checked."""
        from prama.cli.lsp import load_catalogue
        from prama.core.errors import ValidationError

        with pytest.raises(ValidationError, match="no catalogue at"):
            load_catalogue(tmp_path / "absent.json")

    def test_an_unreadable_file_is_refused(self, tmp_path) -> None:
        from prama.cli.lsp import load_catalogue
        from prama.core.errors import ValidationError

        path = tmp_path / "bad.json"
        path.write_text("{not json")
        with pytest.raises(ValidationError, match="not readable as a catalogue"):
            load_catalogue(path)

    def test_a_file_without_datasets_is_refused(self, tmp_path) -> None:
        from prama.cli.lsp import load_catalogue
        from prama.core.errors import ValidationError

        path = tmp_path / "empty.json"
        path.write_text(json.dumps({"written_at": "2026-09-09T00:00:00Z"}))
        with pytest.raises(ValidationError, match="no 'datasets' object"):
            load_catalogue(path)

    def test_a_good_file_loads(self, tmp_path) -> None:
        from prama.cli.lsp import load_catalogue

        path = tmp_path / "cat.json"
        path.write_text(json.dumps({"datasets": {"positions": {"notional": "DECIMAL(18,2)"}}}))
        catalogue = load_catalogue(path)
        schema = catalogue.get("positions")
        assert schema is not None
        assert schema.column_names == ("notional",)
