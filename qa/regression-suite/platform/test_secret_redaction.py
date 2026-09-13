"""Redaction must not break the record it was redacting.

QA round 2, `SEC-209` and `CFG-118`. Two ways a secret reaches somewhere it
should not, both in the code written to stop that happening.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import logging

import pytest

from prama.core.config.coercion import Coercer
from prama.core.log import RedactionFilter


class _Captured(logging.Handler):
    """A handler that keeps the fully formatted line, as a real sink would."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@pytest.fixture
def logger_with_redaction() -> logging.Logger:
    log = logging.getLogger("prama.qa.redaction")
    log.handlers.clear()
    log.setLevel(logging.DEBUG)
    log.propagate = False
    handler = _Captured()
    handler.addFilter(RedactionFilter())
    log.addHandler(handler)
    return log


def test_a_secret_passed_as_a_logging_argument_is_redacted(
    logger_with_redaction: logging.Logger, capsys: pytest.CaptureFixture[str]
) -> None:
    """`logger.warning("password=%s", secret)` — the idiomatic spelling.

    `RedactionFilter` substitutes over `record.msg` *before* %-formatting, so
    the template `password=%s` becomes `password=***` and the placeholder is
    gone. `record.getMessage()` then raises `TypeError: not all arguments
    converted`, logging traps it, prints "--- Logging error ---" with a
    traceback that echoes the real secret in its `Arguments:` line, and drops
    the record.

    So the outcome is worse than either thing anyone predicted: the line is
    lost *and* the secret is printed to stderr by the error path of the
    logging module itself.
    """
    handler = logger_with_redaction.handlers[0]
    assert isinstance(handler, _Captured)

    logger_with_redaction.warning("password=%s", "hunter2-the-actual-secret")

    captured = capsys.readouterr()
    # The record must survive...
    assert handler.lines, "the record was dropped instead of being written"
    # ...with the secret masked...
    assert "hunter2-the-actual-secret" not in handler.lines[0]
    # ...and nothing may have escaped to stderr along the way.
    assert "hunter2-the-actual-secret" not in captured.err
    assert "Logging error" not in captured.err


def test_a_secret_in_the_message_itself_is_still_redacted(
    logger_with_redaction: logging.Logger,
) -> None:
    """The case that already worked, pinned so the fix cannot lose it."""
    handler = logger_with_redaction.handlers[0]
    assert isinstance(handler, _Captured)
    logger_with_redaction.warning("password=hunter2")
    assert "hunter2" not in handler.lines[0]


def test_a_coercion_failure_on_a_secret_key_does_not_print_the_secret() -> None:
    """`Coercer._fail` puts `repr(value)` in the error context regardless of key.

    A coercion failure on `security.session_secret` therefore prints the real
    secret, and that error goes on to be logged and rendered into an API
    problem document — the two places a secret most needs not to be.
    """
    with pytest.raises(Exception) as failure:
        Coercer("security.session_secret").to_int("supersecretvalue123")
    assert "supersecretvalue123" not in str(failure.value)


def test_a_coercion_failure_on_an_ordinary_key_still_shows_the_value() -> None:
    """Masking everything would make every type error undiagnosable.

    The value is the single most useful thing in a configuration type error,
    so it is withheld only where the key says it is a secret.
    """
    with pytest.raises(Exception) as failure:
        Coercer("server.port").to_int("not-a-number")
    assert "not-a-number" in str(failure.value)
