"""``prama mcp``.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import io
import json

from prama.cli.base import EXIT_OK, Application
from prama.cli.commands import all_commands


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    return Application(all_commands()).run(argv, out=out), out.getvalue()


class TestToolsCommand:
    def test_it_answers_the_security_review_question(self) -> None:
        """ "What can this thing do to my estate?" — answerable from a change
        ticket, without starting a server or touching a database."""
        code, output = _run(["mcp", "tools"])
        assert code == EXIT_OK
        assert "No tool mutates the estate" in output
        assert "list_datasets" in output

    def test_it_marks_which_results_are_fenced(self) -> None:
        _, output = _run(["mcp", "tools"])
        assert "[fenced]" in output

    def test_the_json_form_states_the_guarantee_as_a_field(self) -> None:
        """So a CI check can assert on it rather than grepping prose."""
        _, output = _run(["--json", "mcp", "tools"])
        payload = json.loads(output)
        assert payload["any_mutates"] is False
        assert all(tool["mutates"] is False for tool in payload["tools"])
