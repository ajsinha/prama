"""Evidence and assurance: the ledger, incidents, scorecards, attestations, reports.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from prama.sdk.base import Resource, body, endpoint, namespace, seg


@namespace("evidence")
class Evidence(Resource):
    """The hash-chained evidence ledger: read it, verify it, anchor it, export it."""

    @endpoint("GET", "/evidence")
    def list(
        self,
        *,
        control_id: str | None = None,
        dataset: str | None = None,
        verdict: str | None = None,
        run_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Any:
        """Records matching every filter given, newest first; ``since``/``until`` are ISO-8601."""
        return self._get(
            "/evidence",
            control_id=control_id,
            dataset=dataset,
            verdict=verdict,
            run_id=run_id,
            since=since,
            until=until,
            limit=limit,
            offset=offset,
        )

    @endpoint("GET", "/evidence/{sequence}")
    def get(self, sequence: int) -> Any:
        """One record, by its position in the chain."""
        return self._get(f"/evidence/{seg(sequence)}")

    @endpoint("GET", "/evidence/latest")
    def latest(self) -> Any:
        """Each control's current record, keyed by control id."""
        return self._get("/evidence/latest")

    @endpoint("GET", "/evidence/status")
    def status(self) -> Any:
        """Whether anything has been observed (``observed`` / ``no_runs``), and unfinished runs."""
        return self._get("/evidence/status")

    @endpoint("GET", "/evidence/verify")
    def verify(self) -> Any:
        """Check the stored chain: ``records``, ``intact``, ``head``, ``merkle_root``, breaches."""
        return self._get("/evidence/verify")

    @endpoint("GET", "/evidence/compare")
    def compare(self, original: int, replayed: int | None = None) -> Any:
        """Why two records of a control differ; ``replayed`` defaults to its newest record."""
        return self._get("/evidence/compare", original=original, replayed=replayed)

    @endpoint("GET", "/evidence/runs")
    def runs(self, *, limit: int | None = None) -> Any:
        """Recent runs, newest first."""
        return self._get("/evidence/runs", limit=limit)

    @endpoint("GET", "/evidence/runs/{run_id}")
    def run(self, run_id: str) -> Any:
        """One run and the records it wrote."""
        return self._get(f"/evidence/runs/{seg(run_id)}")

    @endpoint("POST", "/evidence/anchor")
    def anchor(self) -> Any:
        """Anchor the chain head with the configured witness now (needs ``admin``)."""
        return self._post("/evidence/anchor")

    @endpoint("GET", "/evidence/anchors")
    def anchors(self) -> Any:
        """Every anchoring attempt, failures included."""
        return self._get("/evidence/anchors")

    @endpoint("GET", "/evidence/export")
    def export(self) -> Any:
        """The chain as zip bytes (manifest, records, anchor receipts) for an auditor.

        Unzipped, ``python3 scripts/verify_evidence.py DIR`` checks it without Prama.
        """
        return self._call("GET", "/evidence/export", raw=True)


@namespace("incidents")
class Incidents(Resource):
    """Controls whose latest evidence is not a pass, and the discussion on them."""

    @endpoint("GET", "/incidents")
    def list(
        self,
        *,
        verdict: str | None = None,
        dataset: str | None = None,
        criticality: int | None = None,
    ) -> Any:
        """What is currently wrong, failures first, with ``passing`` and ``observation``."""
        return self._get("/incidents", verdict=verdict, dataset=dataset, criticality=criticality)

    @endpoint("GET", "/incidents/{control_id}")
    def get(self, control_id: str) -> Any:
        """One incident: the control's sentence, history, when it began, sample, feeders."""
        return self._get(f"/incidents/{seg(control_id)}")

    @endpoint("GET", "/incidents/{control_id}/comments")
    def comments(self, control_id: str) -> Any:
        """The discussion on this incident."""
        return self._get(f"/incidents/{seg(control_id)}/comments")

    @endpoint("POST", "/incidents/{control_id}/comments")
    def comment(self, control_id: str, text: str, *, parent_id: str | None = None) -> Any:
        """Comment on an incident; ``@username`` reaches that person's queue."""
        return self._post(
            f"/incidents/{seg(control_id)}/comments", body(body=text, parent_id=parent_id)
        )


@namespace("scorecards")
class Scorecards(Resource):
    """Quality scores derived from evidence, per dataset and estate-wide, by dimension."""

    @endpoint("GET", "/scorecards")
    def list(self) -> Any:
        """A card per dataset, the estate's card, and whether the breakdown is real."""
        return self._get("/scorecards")

    @endpoint("GET", "/scorecards/estate")
    def estate(self) -> Any:
        """The estate-wide card."""
        return self._get("/scorecards/estate")

    @endpoint("GET", "/scorecards/{dataset}")
    def get(self, dataset: str) -> Any:
        """One dataset's card."""
        return self._get(f"/scorecards/{seg(dataset)}")


@namespace("attestations")
class Attestations(Resource):
    """Signed statements whose figures are derived from the ledger, not typed."""

    @endpoint("GET", "/attestations")
    def list(self) -> Any:
        """Attestations nothing has replaced, most recent period first."""
        return self._get("/attestations")

    @endpoint("GET", "/attestations/history")
    def history(self, scope: str) -> Any:
        """Everything ever signed for one scope, superseded ones included."""
        return self._get("/attestations/history", scope=scope)

    @endpoint("GET", "/attestations/draft")
    def draft(
        self, *, scope: str | None = None, start: str | None = None, end: str | None = None
    ) -> Any:
        """What would be attested to, before signing; the period defaults to this month."""
        return self._get("/attestations/draft", scope=scope, start=start, end=end)

    @endpoint("POST", "/attestations")
    def sign(
        self,
        attester_name: str,
        statement: str,
        period_start: str,
        period_end: str,
        *,
        scope: str | None = None,
        dispositions: Mapping[str, str] | None = None,
        supersedes: str | None = None,
        supersedes_because: str | None = None,
    ) -> Any:
        """Sign: the figures are derived from the ledger now, sealed and recorded."""
        return self._post(
            "/attestations",
            body(
                attester_name=attester_name,
                statement=statement,
                period_start=period_start,
                period_end=period_end,
                scope=scope,
                dispositions=dict(dispositions) if dispositions is not None else None,
                supersedes=supersedes,
                supersedes_because=supersedes_because,
            ),
        )

    @endpoint("GET", "/attestations/{attestation_id}")
    def get(self, attestation_id: str) -> Any:
        """One attestation, and whether its content and seal still verify."""
        return self._get(f"/attestations/{seg(attestation_id)}")

    @endpoint("GET", "/attestations/{attestation_id}/pack")
    def pack(self, attestation_id: str) -> Any:
        """The attestation pack, as HTML bytes."""
        return self._call("GET", f"/attestations/{seg(attestation_id)}/pack", raw=True)


@namespace("reports")
class Reports(Resource):
    """The print packs: HTML bytes to save or print, or the JSON they are rendered from."""

    @endpoint("GET", "/reports")
    def list(self) -> Any:
        """Which packs this estate can produce, and in which formats."""
        return self._get("/reports")

    @endpoint("GET", "/reports/declarations")
    def declarations(self, *, as_json: bool = False) -> Any:
        """The declaration pack: HTML bytes, or with ``as_json=True`` the content it renders."""
        return self._call(
            "GET",
            "/reports/declarations",
            params={"format": "json" if as_json else "html"},
            raw=not as_json,
        )

    @endpoint("GET", "/reports/controls")
    def controls(self, *, as_json: bool = False) -> Any:
        """The control pack: HTML bytes, or with ``as_json=True`` the content it renders."""
        return self._call(
            "GET",
            "/reports/controls",
            params={"format": "json" if as_json else "html"},
            raw=not as_json,
        )
