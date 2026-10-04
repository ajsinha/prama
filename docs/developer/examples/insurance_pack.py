"""A domain pack in miniature: the worked example of docs/developer/packs.md.

The banking pack (`prama.packs.banking`) is the real one. This is the same shape
with one contribution of each kind a pack makes most often, for a different
industry, small enough to read in one sitting:

* a **PQL function**, ``COVERED_ON(inception, expiry, as_of)``, registered by an
  explicit ``install`` and never on import;
* a **claims readout**: what the pack discharges with controls and, the half
  that matters, what it does not claim to.

A pack contributes to the core registries and adds no mechanism of its own: the
function is an ordinary `prama.pql.functions.Function`, compiled and checked
against its reference implementation like every other.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from prama.pql.families import BOOLEAN, TEMPORAL
from prama.pql.functions import UNSET, Function, FunctionRegistry


def _iso(value: Any) -> str | None:
    try:
        return date.fromisoformat(str(value).strip()[:10]).isoformat()
    except ValueError:
        return None


def _covered_on(arguments: list[Any]) -> Any:
    inception, expiry, as_of = (_iso(a) for a in arguments)
    if inception is None or expiry is None or as_of is None:
        return UNSET
    return inception <= as_of <= expiry


COVERED_ON = Function(
    name="COVERED_ON",
    summary="Whether a policy's cover, inception to expiry inclusive, includes a date.",
    arity=(3, 3),
    returns=BOOLEAN,
    argument_types=(TEMPORAL, TEMPORAL, TEMPORAL),
    # ISO-8601 dates compare correctly as text on every engine, which is why
    # Prama keeps dates as ISO text: no engine-specific date type is needed.
    sql="({0} <= {2} AND {2} <= {1})",
    evaluate=_covered_on,
)

FUNCTIONS: tuple[Function, ...] = (COVERED_ON,)


def install(registry: FunctionRegistry) -> FunctionRegistry:
    """Add the pack's functions to *registry*. Idempotent, and never run on import."""
    for function in FUNCTIONS:
        registry.register(function)
    return registry


def claims() -> dict[str, list[str]]:
    """What the pack discharges with controls, and what it only supports or leaves alone."""
    return {
        "discharged": ["a claim's loss date falls within its policy's cover"],
        "supported_not_discharged": [
            "reserving adequacy: an actuarial judgement, not a property of the data"
        ],
        "not_claimed": ["Solvency II reporting templates"],
    }
