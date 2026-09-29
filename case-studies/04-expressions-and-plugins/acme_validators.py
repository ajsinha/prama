"""A validator plugin, of the kind a bank writes for its own identifiers.

Registered through the ``prama.validators`` entry point in a real deployment;
loaded directly here so the study runs from a checkout with nothing installed.

The point of this file is what it *does not* do. It reads no clock, opens no
socket, touches no filesystem and asks no model — and none of that is taken on
trust: ``PluginRegistry.admit`` scans this source before the validator is
usable, runs it twice on the same inputs, and folds a hash of this class into
the plan id of every control that names it. Edit the algorithm below and every
control using it changes identity, rather than silently changing what last
month's evidence meant.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.classify.validators import Judgement, SemanticValidator


class AcmeBookCode(SemanticValidator):
    """Acme's internal trading-book code: ``XX-NNNN-C``.

    Two letters for the desk, four digits for the book, and a check character
    that is the letters and digits weighted mod 23. SQL can express the shape
    and cannot express the check character — which is exactly the two-stage
    case: the pattern is a *screen*, this is the residual, and a control over
    this column reports ``indeterminate`` rather than a pass until the residual
    has run.
    """

    name = "acme_book"
    label = "Acme trading-book code"
    authority = "Acme Markets internal standard BK-4"
    screen_pattern = r"^[A-Z]{2}-[0-9]{4}-[A-Z]$"
    beyond_shape = "the check character is part of the standard"

    #: The alphabet the check character is drawn from. 23 letters, omitting
    #: I, O and Q — the three that are misread as 1 and 0 on a printed
    #: confirmation, which is the whole reason a scheme like this exists.
    ALPHABET = "ABCDEFGHJKLMNPRSTUVWXYZ"

    def check(self, value: str) -> Judgement:
        desk, book, given = value.split("-")
        total = 0
        for position, character in enumerate(desk + book, start=1):
            total += position * (ord(character) - 55 if character.isalpha() else int(character))
        expected = self.ALPHABET[total % 23]
        if given == expected:
            return Judgement(valid=True)
        return Judgement(
            valid=False,
            reason=(f"the check character is {given}, and {value[:-1]}{expected} would be valid"),
        )


def book_code(desk: str, number: int) -> str:
    """Build a valid code. Used by the generator, so the study's data is real.

    A study whose identifiers fail their own validator would have every
    validity control fail for the wrong reason and prove nothing.
    """
    validator = AcmeBookCode()
    stem = f"{desk}-{number:04d}"
    total = 0
    for position, character in enumerate(stem.replace("-", ""), start=1):
        total += position * (ord(character) - 55 if character.isalpha() else int(character))
    return f"{stem}-{validator.ALPHABET[total % 23]}"
