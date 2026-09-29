"""Domain packs: what the banking pack ships, what it does not claim, and its readers.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.sdk.base import Resource, body, endpoint, namespace, seg


@namespace("packs")
class Packs(Resource):
    """The banking pack, and Prama's own SOC 2 readiness."""

    @endpoint("GET", "/packs/banking")
    def banking(self) -> Any:
        """Calendars, cross-field checks, obligations, reconciliations, message formats."""
        return self._get("/packs/banking")

    @endpoint("GET", "/packs/banking/claims")
    def claims(self) -> Any:
        """What the pack discharges, what it only supports, and what it leaves alone."""
        return self._get("/packs/banking/claims")

    @endpoint("GET", "/packs/banking/calendars/{name}")
    def calendar(self, name: str, *, year: int | None = None) -> Any:
        """Closures of ``TARGET2``, ``FederalReserve``, ``London`` or ``NYSE`` for a year."""
        return self._get(f"/packs/banking/calendars/{seg(name)}", year=year)

    @endpoint("GET", "/packs/banking/reconciliations")
    def reconciliations(self) -> Any:
        return self._get("/packs/banking/reconciliations")

    @endpoint("GET", "/packs/banking/reconciliations/{identity}")
    def reconciliation(self, identity: str) -> Any:
        """A reference reconciliation's keys, tolerance and expected breaks, with reasons."""
        return self._get(f"/packs/banking/reconciliations/{seg(identity)}")

    @endpoint("POST", "/packs/banking/parse")
    def parse(self, message: str, *, fmt: str | None = None) -> Any:
        """Parse one FIX, ISO 8583, FpML, SWIFT MT or ISO 20022 message; ``defects`` lists
        what is structurally wrong. *fmt* (``fix``, ``iso8583``, ``fpml``, ``swift``,
        ``pacs008``, ``camt053``) is inferred when not given."""
        return self._post("/packs/banking/parse", body(message=message, format=fmt))

    @endpoint("GET", "/packs/banking/concepts")
    def concepts(self) -> Any:
        return self._get("/packs/banking/concepts")

    @endpoint("GET", "/packs/banking/concepts/{name}")
    def concept(self, name: str) -> Any:
        """One concept: its properties, and where it ends."""
        return self._get(f"/packs/banking/concepts/{seg(name)}")

    @endpoint("GET", "/packs/banking/recognise")
    def recognise(self, columns: list[str], *, concept: str = "") -> Any:
        """Which concept these columns are: every candidate, or none with why."""
        return self._get("/packs/banking/recognise", columns=columns, concept=concept or None)

    @endpoint("GET", "/packs/soc2")
    def soc2(self) -> Any:
        """Prama's own SOC 2 readiness, gaps first."""
        return self._get("/packs/soc2")
