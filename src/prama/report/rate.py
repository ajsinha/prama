"""Printing a rate without rounding towards good news.

A dataset with 412 failing rows in 1,284,301 scores 99.968%, and one decimal
place renders that as **100.0%**. Technically correct, and exactly the failure
this product exists not to commit: the number a business owner reads says the
data is perfect, and it is not.

So the rule here is one-directional. A rate that is not exactly whole may never
print as if it were — precision is added until the display distinguishes it
from perfection, and past the point where that stops being readable it degrades
to ``>99.99%`` rather than to ``100%``. The same rule applies at the bottom: a
rate of 0.0001 is not ``0.0%``, because "nothing passed" and "almost nothing
passed" are different facts about a remediation that is underway.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

#: How far precision is allowed to grow before the display gives up and says
#: "close to, but not". Four decimals is a basis point, which is the smallest
#: difference anyone in this domain acts on.
MAX_DECIMALS = 4


def percent(value: float, *, decimals: int = 1) -> str:
    """A rate as a percentage that never flatters.

    ``decimals`` is the *preferred* precision, not a cap: it grows as far as
    :data:`MAX_DECIMALS` when the shorter form would round a real defect away.
    """
    if value >= 1.0:
        return "100%"
    if value <= 0.0:
        return "0%"

    scaled = value * 100
    for places in range(decimals, MAX_DECIMALS + 1):
        rendered = f"{scaled:.{places}f}"
        # Rejected when the text says perfect (or says nothing at all) and the
        # value does not. Adding a decimal is cheap; a green 100% over a real
        # failure is not.
        if float(rendered) not in (100.0, 0.0):
            return f"{rendered}%"
    return "&gt;99.99%" if scaled > 50 else "&lt;0.0001%"


def plain(value: float, *, decimals: int = 1) -> str:
    """The same, without HTML entities — for logs, CLI output and alt text."""
    return percent(value, decimals=decimals).replace("&gt;", ">").replace("&lt;", "<")
