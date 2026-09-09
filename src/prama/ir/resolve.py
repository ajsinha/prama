"""Lowering a control with everything it needs to resolve.

``lower`` takes a validator registry and a code-list mapping, and defaults both
to empty. That default is right for a unit test and wrong everywhere else: a
control saying ``IN CODELIST 'iso4217'`` lowered without the lists refuses to
compile, and the failure surfaces as "the codelist is not registered" long
after the place that forgot to pass it.

So there is one function that lowers a control properly, and every call site
uses it. The alternative — each caller remembering — is how three of six call
sites end up subtly different, which is exactly what happened before this
existed.

**As-of matters.** Code lists change: ZWG replaced ZWL in 2024, XCG replaced
ANG in 2025. A plan resolves its lists at a stated date and freezes the values
into the IR, so a list edited on Tuesday cannot silently change what Monday's
evidence meant.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from prama.classify.codelists import REGISTRY as CODELISTS
from prama.ir.lower import Lowerer
from prama.ir.model import ControlPlan


def resolved(
    control: Any,
    *,
    as_of: date | None = None,
    binding: str = "",
    **kwargs: Any,
) -> ControlPlan:
    """Lower a control with the shipped code lists resolved."""
    # ``as_of`` is passed only when given. Spelling the default explicitly
    # produced a *different plan id* for the same control — the Lowerer's own
    # default is the empty string and ``None`` serialises as null — and two
    # callers producing different content hashes for identical text is the
    # exact drift content addressing exists to prevent.
    if as_of is not None:
        kwargs["as_of"] = as_of
    return Lowerer(
        binding=binding,
        codelists=CODELISTS.resolve(as_of),
        **kwargs,
    ).control(control)
