"""acme.fx_sanity — the delegate that must be refused, kept to prove it is.

It fetches today's FX rates from the internet. So a verdict would depend on
when it ran and on a server outside the bank, and the rows it was given could
leave with the request. Prama refuses it from its source, before importing it,
so this module's top-level code never runs.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary; see LICENSE.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Iterable, Mapping
from typing import Any

from prama.delegates import DqDelegate, Measurement

RATES = json.load(urllib.request.urlopen("https://fx.example.invalid/latest"))


class FxSanity(DqDelegate):
    name = "acme.fx_sanity"
    requires = ("currency", "rate")

    def measure(self, rows: Iterable[Mapping[str, Any]], params: Mapping[str, Any]) -> Measurement:  # noqa: ARG002
        kept = list(rows)
        wrong = sum(1 for r in kept if abs(float(r["rate"]) - RATES[r["currency"]]) > 0.01)
        return Measurement(scanned=len(kept), violating=wrong)
