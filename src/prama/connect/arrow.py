"""Turning a column of values into an Arrow array without losing any of them.

Every connector reaches this problem and each was solving a piece of it. The
rule is the same wherever the data came from: **a value that does not fit the
column's natural type must not be dropped, truncated, or silently made into a
different number.**

Three ways that happens in practice, all of them found by running real sources:

* **A value too large for int64.** MySQL's unsigned BIGINT goes past it, and
  ``18446744073709551615`` is a real identifier. Arrow's inference raises rather
  than producing anything, so a table holding one could not be read at all.
* **A column whose values disagree about their type.** In MongoDB a field is
  ``100`` in one document and ``"one hundred"`` in the next, because nothing
  stopped it. That is not corrupt data to be rejected — it is the finding the
  estate is being examined for, and it has to survive into a control.
* **A decimal that would round differently as a float.** Handled at the driver
  boundary rather than here, because by this point the damage is done.

The fallback is always the values' own decimal or text form, and deliberately
never a float. A float makes the read succeed and the number wrong, which is
the failure this whole tree is built to avoid; a string is visibly a string, and
a control asserting a numeric property of it fails loudly rather than passing on
a value that was quietly reinterpreted.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

__all__ = ["to_array"]


def to_array(values: list[Any]) -> Any:
    """One column as an Arrow array. Tries hardest to keep the values intact.

    In order of how much is preserved:

    1. Let Arrow infer, which is right almost always.
    2. ``uint64``, which covers the unsigned-integer case exactly.
    3. The values' own strings, which cover everything else.
    """
    import pyarrow as pa

    try:
        return pa.array(values)
    except (pa.ArrowInvalid, pa.ArrowTypeError, OverflowError):
        pass
    try:
        return pa.array(values, type=pa.uint64())
    except (pa.ArrowInvalid, pa.ArrowTypeError, OverflowError, TypeError):
        return pa.array([None if v is None else str(v) for v in values], type=pa.string())
