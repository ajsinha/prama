"""What must never be sent to a model, or come back from one.

Moved here from ``prama.assistant.safety`` so the model layer can apply it to
*prompts* as well as answers. It used to run on answers only, so a secret or
a card number embedded in a prompt reached the provider intact (FR-CHT-013).
The assistant imports it from here; there is one list.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re

#: Shapes that must never leave. Each is (pattern, what it is).
SECRET_SHAPES: tuple[tuple[str, str], ...] = (
    (r"\b(?:postgres|postgresql|mysql|mongodb)(?:\+\w+)?://[^\s\"']+", "a connection string"),
    (r"\b(?:sk|pk)-[A-Za-z0-9]{16,}", "an API key"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "a private key"),
    (r"\baws_secret_access_key\s*[=:]\s*\S+", "an AWS secret"),
    (r"\bpassword\s*[=:]\s*\S{6,}", "a password"),
)

#: A run of 13 to 19 digits, optionally grouped by spaces or hyphens. Only
#: withheld when it passes the Luhn check, so a trade id or a notional of the
#: same length is not mangled.
_CARD = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")


def _luhn(digits: str) -> bool:
    total = 0
    for index, character in enumerate(reversed(digits)):
        value = int(character)
        if index % 2:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


def _card(match: re.Match[str]) -> str:
    digits = re.sub(r"[ -]", "", match.group(0))
    return "[a card number withheld]" if _luhn(digits) else match.group(0)


def redact(text: str) -> str:
    """Remove anything that must not leave, leaving a marker that it was there."""
    result = text
    for pattern, kind in SECRET_SHAPES:
        result = re.sub(pattern, f"[{kind} withheld]", result, flags=re.IGNORECASE)
    return _CARD.sub(_card, result)
