"""Column lineage.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.sdk.base import Resource, endpoint, namespace


@namespace("lineage")
class Lineage(Resource):
    """Column lineage: what a defect reaches, and OpenLineage events in."""

    @endpoint("GET", "/lineage/impact")
    def impact(self, column: str) -> Any:
        return self._get("/lineage/impact", column=column)

    @endpoint("POST", "/lineage/openlineage")
    def openlineage(self, event: dict[str, Any]) -> Any:
        return self._post("/lineage/openlineage", event)
