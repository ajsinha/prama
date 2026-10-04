"""A semantic-type validator, ``nhs_number``: the worked example of docs/developer/validators.md.

An NHS number is ten digits whose last digit is a modulus-11 check over the
first nine. A regular expression can say "ten digits"; it cannot say whether the
check digit is right, so this is an **ALGORITHM** validator: the screen
``^[0-9]{10}$`` runs in the warehouse and narrows, and ``check`` decides each
value that survives it. A control then reads ``CHECK patients.nhs_number IS
VALID 'nhs_number'``.

A validator is a pure function of one value. This module imports nothing that
can read a clock, a file, the network or a model, which is what admission
checks before the validator is usable (`prama_kernel.plugins.PluginRegistry`).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import ClassVar

from prama.classify.validators import VALID, Expressibility, Judgement, SemanticValidator


class NhsNumberValidator(SemanticValidator):
    """An NHS number: ten digits, the last a modulus-11 check digit over the first nine."""

    name: ClassVar[str] = "nhs_number"
    label: ClassVar[str] = "NHS number"
    authority: ClassVar[str] = "NHS Data Dictionary"
    expressibility: ClassVar[Expressibility] = Expressibility.ALGORITHM
    screen_pattern: ClassVar[str] = r"^[0-9]{10}$"
    beyond_shape: ClassVar[str] = "the modulus-11 check digit is part of the standard"

    def check(self, value: str) -> Judgement:
        total = sum(
            int(digit) * weight for digit, weight in zip(value[:9], range(10, 1, -1), strict=True)
        )
        expected = 11 - total % 11
        if expected == 11:
            expected = 0
        if expected == 10:
            # No check digit can be 10, so no number with this body was ever issued.
            return Judgement(valid=False, reason="this body has no valid check digit")
        actual = int(value[9])
        if actual == expected:
            return VALID
        return Judgement(valid=False, reason=f"check digit is {actual}, should be {expected}")
