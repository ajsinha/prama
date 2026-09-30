"""Column lineage: read SQL and exports into the store, and ask what a column reaches.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from prama_sdk.base import Resource, body, endpoint, namespace, seg
from prama_sdk.resources._files import FileLike, upload


@namespace("lineage")
class Lineage(Resource):
    """Column lineage: scans, imports, edges, impact, gaps, and the edges waiting on you."""

    @endpoint("POST", "/lineage/scan")
    def scan(
        self,
        source: str,
        files: FileLike | Sequence[FileLike],
        *,
        dialect: str = "ansi",
    ) -> Any:
        """Read SQL files (paths, or SQL text) into the store as a run of *source*.

        Returns the run: statements, edges, gaps and the share understood.
        """
        many = list(files) if isinstance(files, list | tuple) else [files]
        return self._call(
            "POST",
            "/lineage/scan",
            data={"source": source, "dialect": dialect},
            files=[
                ("files", upload(f, f"statement-{i}.sql", "application/sql"))
                for i, f in enumerate(many, 1)
            ],
        )

    @endpoint("POST", "/lineage/dbt")
    def dbt(self, manifest: FileLike, *, source: str = "dbt", dialect: str = "ansi") -> Any:
        """A dbt project's column lineage, from its ``target/manifest.json``."""
        return self._call(
            "POST",
            "/lineage/dbt",
            data={"source": source, "dialect": dialect},
            files={"manifest": upload(manifest, "manifest.json", "application/json")},
        )

    @endpoint("GET", "/lineage/history/query")
    def history_query(self, warehouse: str) -> Any:
        """The export query for ``snowflake``, ``databricks`` or ``bigquery`` history."""
        return self._get("/lineage/history/query", warehouse=warehouse)

    @endpoint("POST", "/lineage/history")
    def history(self, warehouse: str, rows: list[dict[str, Any]], *, source: str = "") -> Any:
        """Column lineage from rows of a warehouse's query history."""
        return self._post(
            "/lineage/history", body(warehouse=warehouse, rows=rows, source=source or None)
        )

    @endpoint("POST", "/lineage/import")
    def import_export(self, vendor: str, export: FileLike, *, source: str = "") -> Any:
        """Lineage from a ``manta`` or ``alation`` export; ``dropped`` says what did not come."""
        return self._call(
            "POST",
            "/lineage/import",
            data={"vendor": vendor, "source": source},
            files={"export": upload(export, f"{vendor}.json", "application/json")},
        )

    @endpoint("GET", "/lineage/conflicts")
    def conflicts(self) -> Any:
        """Columns where an imported catalog and Prama's own parse disagree."""
        return self._get("/lineage/conflicts")

    @endpoint("GET", "/lineage/edges")
    def edges(self, *, dataset: str = "", status: str = "", limit: int | None = None) -> Any:
        """Current edges; *dataset* keeps those touching it, *status* one status."""
        return self._get(
            "/lineage/edges", dataset=dataset or None, status=status or None, limit=limit
        )

    @endpoint("POST", "/lineage/edges/{edge_id}/decide")
    def decide(self, edge_id: str, decision: str, *, note: str = "") -> Any:
        """``confirmed`` or ``rejected``. The decision outlives re-scans."""
        return self._post(
            f"/lineage/edges/{seg(edge_id)}/decide", {"decision": decision, "note": note}
        )

    def confirm(self, edge_id: str, *, note: str = "") -> Any:
        return self.decide(edge_id, "confirmed", note=note)

    def reject(self, edge_id: str, *, note: str = "") -> Any:
        return self.decide(edge_id, "rejected", note=note)

    @endpoint("GET", "/lineage/proposals")
    def proposals(self) -> Any:
        """Inferred edges waiting on a person, and the controls lineage implies."""
        return self._get("/lineage/proposals")

    @endpoint("GET", "/lineage/impact")
    def impact(self, column: str) -> Any:
        """Everything a defect in ``dataset.column`` reaches, ranked, and its trust."""
        return self._get("/lineage/impact", column=column)

    @endpoint("POST", "/lineage/change")
    def change(self, before: str, after: str, *, dialect: str = "ansi") -> Any:
        """What changing a SQL file from *before* to *after* puts at risk (``at_risk``)."""
        return self._post("/lineage/change", {"before": before, "after": after, "dialect": dialect})

    @endpoint("GET", "/lineage/gaps")
    def gaps(self, *, runs: int | None = None) -> Any:
        """What the latest scans could not read."""
        return self._get("/lineage/gaps", runs=runs)

    @endpoint("GET", "/lineage/runs")
    def runs(self, *, limit: int | None = None) -> Any:
        return self._get("/lineage/runs", limit=limit)

    @endpoint("GET", "/lineage/sources")
    def sources(self) -> Any:
        return self._get("/lineage/sources")

    @endpoint("POST", "/lineage/openlineage")
    def openlineage(self, event: dict[str, Any]) -> Any:
        """Send one OpenLineage RunEvent. Replaying it is safe."""
        return self._post("/lineage/openlineage", event)
