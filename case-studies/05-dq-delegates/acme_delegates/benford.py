"""acme.benford_first_digit — do the amounts' leading digits look naturally occurring?

Amounts that arise naturally across several orders of magnitude (payments,
invoices, expense claims) follow Benford's law: about 30% begin with a 1 and
under 5% with a 9. Invented amounts do not, and the classic signature is a
pile-up just under an approval limit.

Why this is a delegate: it is a property of the whole distribution, not of
any row, and it needs a statistical test. It counts *findings* (the digits
whose share departs significantly from Benford), so its threshold is a count
of digits, never a rate of rows. Too few amounts establish nothing, and the
verdict says so rather than passing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary; see LICENSE.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

from prama.delegates import DqDelegate, Measurement, Parameter

EXPECTED = {digit: math.log10(1 + 1 / digit) for digit in range(1, 10)}


def first_digit(value: Any) -> int | None:
    try:
        number = abs(float(value))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number == 0:
        return None
    text = f"{number:.15e}"  # scientific notation: the mantissa's first digit
    return int(text[0])


class BenfordFirstDigit(DqDelegate):
    name = "acme.benford_first_digit"
    version = "1"
    requires = ("payment_id", "amount")
    parameters = (
        Parameter("min_rows", "number", 300, doc="Fewer amounts than this establish nothing."),
        Parameter("z_critical", "number", 3.29, doc="3.29 is two-sided 99.9%."),
    )
    unit = "findings"
    summary = "the amounts' first digits follow Benford's law, digit by digit"

    def measure(self, rows: Iterable[Mapping[str, Any]], params: Mapping[str, Any]) -> Measurement:
        kept = list(rows)
        digits = [first_digit(row.get("amount")) for row in kept]
        tested = [d for d in digits if d is not None]
        n = len(tested)
        if n < int(params["min_rows"]):
            return Measurement(
                scanned=len(kept),
                violating=0,
                observations={"amounts_tested": n},
                note=f"{n} amounts cannot establish a first-digit distribution",
                established=False,
            )
        counts = {d: tested.count(d) for d in EXPECTED}
        flagged: list[int] = []
        chi_square = mad = 0.0
        for digit, expected in EXPECTED.items():
            observed = counts[digit] / n
            mad += abs(observed - expected) / 9
            chi_square += (counts[digit] - n * expected) ** 2 / (n * expected)
            spread = math.sqrt(expected * (1 - expected) / n)
            z = (abs(observed - expected) - 1 / (2 * n)) / spread
            if z > float(params["z_critical"]):
                flagged.append(digit)
        excess = {d for d in flagged if counts[d] / n > EXPECTED[d]}
        samples = tuple(
            {"payment_id": row.get("payment_id"), "amount": row.get("amount")}
            for row, digit in zip(kept, digits, strict=True)
            if digit in excess
        )[:10]
        return Measurement(
            scanned=len(kept),
            violating=len(flagged),
            observations={
                "amounts_tested": n,
                "mad": round(mad, 6),
                "chi_square": round(chi_square, 3),
                **{f"share_digit_{d}": round(counts[d] / n, 6) for d in EXPECTED},
            },
            samples=samples,
            note=(
                f"first digit(s) {', '.join(map(str, flagged))} depart from Benford's law"
                if flagged
                else "every first digit is within Benford's expectation"
            )
            + f" (MAD {mad:.4f}; above 0.015 is nonconformity by Nigrini's bands)",
        )
