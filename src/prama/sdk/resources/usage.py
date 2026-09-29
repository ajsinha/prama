"""Dataset usage from warehouse query history, and what it says to work on first.

A priority signal only: usage orders a list and never feeds a quality score.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.sdk.base import Resource, endpoint, namespace, seg
from prama.sdk.resources._text_files import Upload, upload


@namespace("usage")
class Usage(Resource):
    """Import query history; read daily usage, co-access, and priorities."""

    @endpoint("GET", "/usage/export-query/{warehouse}")
    def export_query(self, warehouse: str) -> Any:
        """The query to run in ``snowflake``, ``bigquery`` or ``databricks``."""
        return self._get(f"/usage/export-query/{seg(warehouse)}")

    @endpoint("POST", "/usage/import/{warehouse}")
    def import_history(self, warehouse: str, history: Upload) -> Any:
        """Record that query's result (a JSON list or a ``.csv``) as daily usage."""
        return self._call(
            "POST",
            f"/usage/import/{seg(warehouse)}",
            files={"history": upload(history, "history.json")},
        )

    @endpoint("GET", "/usage/daily")
    def daily(self, *, days: int | None = None, dataset: str | None = None) -> Any:
        """Queries and readers per dataset, day and source over the last *days* days."""
        return self._get("/usage/daily", days=days, dataset=dataset)

    @endpoint("GET", "/usage/coaccess")
    def coaccess(self, *, days: int | None = None) -> Any:
        """Pairs of datasets read by the same query, busiest first."""
        return self._get("/usage/coaccess", days=days)

    @endpoint("GET", "/usage/priorities")
    def priorities(self, *, days: int | None = None) -> Any:
        """Most used, least controlled first. Never an input to any score."""
        return self._get("/usage/priorities", days=days)
