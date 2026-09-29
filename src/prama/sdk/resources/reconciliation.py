"""Reconciliations, the break workbench, and the period-end certificate.

A reconciliation is a RECONCILE control and runs like any control (through
``client.runs``); these namespaces read what the run recorded and work the
breaks it left.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from prama.sdk.base import Resource, body, endpoint, namespace, seg


@namespace("reconciliation")
class Reconciliation(Resource):
    """RECONCILE controls, their latest results, and the certificate that closes a period."""

    @endpoint("GET", "/reconciliations")
    def list(self) -> Any:
        """Every reconciliation with its latest result and break counts, and every queue."""
        return self._get("/reconciliations")

    @endpoint("GET", "/reconciliations/{control_id}")
    def get(self, control_id: str, *, history: int | None = None) -> Any:
        """One reconciliation: the control, its latest result, and its recent runs."""
        return self._get(f"/reconciliations/{seg(control_id)}", history=history)

    @endpoint("POST", "/reconciliations/certificate")
    def certify(self, definition: str, *, period_end: date | str | None = None) -> Any:
        """A certificate of what is outstanding, signed by you. Needs ``attestation:sign``."""
        when = period_end.isoformat() if isinstance(period_end, date) else period_end
        return self._post(
            "/reconciliations/certificate", body(definition=definition, period_end=when)
        )


@namespace("breaks")
class Breaks(Resource):
    """The break workbench: breaks in working order, and what people do about them."""

    @endpoint("GET", "/breaks")
    def workbench(self, definition: str, *, show: str | None = None) -> Any:
        """Breaks for one reconciliation. ``show="all"`` adds the cleared ones."""
        return self._get("/breaks", definition=definition, show=show)

    @endpoint("GET", "/breaks/{break_id}")
    def get(self, break_id: str) -> Any:
        """One break, with its deterministic explanation (``because``) and its trail."""
        return self._get(f"/breaks/{seg(break_id)}")

    @endpoint("POST", "/breaks/{break_id}/assign")
    def assign(self, break_id: str, owner: str) -> Any:
        """Hand a break to a person or team; the handover goes into its trail."""
        return self._post(f"/breaks/{seg(break_id)}/assign", {"owner": owner})

    @endpoint("POST", "/breaks/{break_id}/explain")
    def explain(self, break_id: str, text: str) -> Any:
        """Record what you found. Appends to the trail; never rewrites it."""
        return self._post(f"/breaks/{seg(break_id)}/explain", {"text": text})

    @endpoint("POST", "/breaks/{break_id}/accept")
    def accept(self, break_id: str, reason: str) -> Any:
        """Accept a break as a known reconciling item. A reason is required."""
        return self._post(f"/breaks/{seg(break_id)}/accept", {"reason": reason})
