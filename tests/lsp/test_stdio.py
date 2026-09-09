"""``prama lsp serve``, launched the way an editor launches it.

The unit tests drive ``handle`` directly, which is the right place for edge
cases and the wrong place to discover that the process writes a banner to
stdout and corrupts the stream on the first message. This starts the real
command in a real subprocess and speaks the real protocol to it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from prama.lsp import protocol

GOOD = "CHECK positions.notional IS NOT NULL SEVERITY critical DIMENSION completeness BECAUSE 'CDE'"


def _conversation(catalogue: Path | None, text: str) -> list[dict]:
    """Start the server, say the usual things, and collect what comes back."""
    command = [sys.executable, "-m", "prama.cli.main", "lsp", "serve"]
    if catalogue is not None:
        command += ["--catalogue", str(catalogue)]

    request = b""
    for payload in (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {"textDocument": {"uri": "file:///s.pql", "text": text}},
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "textDocument/hover",
            "params": {
                "textDocument": {"uri": "file:///s.pql"},
                "position": {"line": 0, "character": 19},
            },
        },
        {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
        {"jsonrpc": "2.0", "method": "exit"},
    ):
        body = json.dumps(payload).encode()
        request += f"Content-Length: {len(body)}\r\n\r\n".encode() + body

    finished = subprocess.run(command, input=request, capture_output=True, timeout=120, check=False)
    assert finished.returncode == 0, finished.stderr.decode()

    import io

    stream = io.BytesIO(finished.stdout)
    out = []
    while (message := protocol.read_message(stream)) is not None:
        out.append(message)
    return [{"method": m.method, "id": m.id, "params": m.params} for m in out], finished


@pytest.fixture
def catalogue(tmp_path: Path) -> Path:
    path = tmp_path / "catalogue.json"
    path.write_text(
        json.dumps(
            {
                "written_at": "2026-09-09T00:00:00Z",
                "datasets": {"positions": {"notional": "DECIMAL(18,2)"}},
            }
        )
    )
    return path


class TestTheProcess:
    def test_it_answers_over_a_real_pipe(self, catalogue: Path) -> None:
        messages, _ = _conversation(catalogue, GOOD)
        # read_message parses only method+id+params, so a response arrives with
        # an empty method; what matters is that the stream framed cleanly and
        # every message was recoverable.
        assert len(messages) == 4

    def test_nothing_but_protocol_goes_to_stdout(self, catalogue: Path) -> None:
        """A single stray line corrupts the framing and the editor reports a
        protocol error rather than the banner you meant to show it."""
        _, finished = _conversation(catalogue, GOOD)
        assert finished.stdout.startswith(b"Content-Length:")
        assert b"prama lsp:" in finished.stderr
        assert b"prama lsp:" not in finished.stdout

    def test_the_banner_names_the_catalogue(self, catalogue: Path) -> None:
        _, finished = _conversation(catalogue, GOOD)
        assert b"1 dataset(s)" in finished.stderr

    def test_without_a_catalogue_it_says_nothing_is_schema_checked(self) -> None:
        """The state somebody has to be able to tell apart from an empty
        estate."""
        _, finished = _conversation(None, GOOD)
        assert b"no catalogue, nothing schema-checked" in finished.stderr

    def test_a_clean_file_publishes_no_diagnostics(self, catalogue: Path) -> None:
        messages, _ = _conversation(catalogue, GOOD)
        [published] = [m for m in messages if m["method"] == "textDocument/publishDiagnostics"]
        assert published["params"]["diagnostics"] == []

    def test_a_typo_comes_back_as_a_diagnostic(self, catalogue: Path) -> None:
        messages, _ = _conversation(catalogue, GOOD.replace("notional", "notionl"))
        [published] = [m for m in messages if m["method"] == "textDocument/publishDiagnostics"]
        [found] = published["params"]["diagnostics"]
        assert "notionl" in found["message"]
        assert found["severity"] == 1

    def test_a_missing_catalogue_file_refuses_rather_than_starting_empty(
        self, tmp_path: Path
    ) -> None:
        """Starting with a silently empty catalogue shows a clean file that has
        not been checked, which is the confusion the unchecked level exists to
        prevent."""
        finished = subprocess.run(
            [
                sys.executable,
                "-m",
                "prama.cli.main",
                "lsp",
                "serve",
                "--catalogue",
                str(tmp_path / "absent.json"),
            ],
            input=b"",
            capture_output=True,
            timeout=120,
            check=False,
        )
        assert finished.returncode != 0
        assert b"no catalogue at" in finished.stderr
