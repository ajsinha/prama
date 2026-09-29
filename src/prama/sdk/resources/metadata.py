"""Business context on datasets, and finding data by meaning.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.sdk.base import Resource, endpoint, namespace, seg


@namespace("metadata")
class Metadata(Resource):
    """Business context on datasets, and finding data by what it means."""

    @endpoint("GET", "/metadata/search")
    def search(self, q: str) -> Any:
        return self._get("/metadata/search", q=q)

    @endpoint("GET", "/metadata/ask")
    def ask(self, q: str) -> Any:
        """Ranked and explained by a discover model, when one is configured."""
        return self._get("/metadata/ask", q=q)

    @endpoint("GET", "/metadata/correlation")
    def correlation(self) -> Any:
        return self._get("/metadata/correlation")

    @endpoint("GET", "/metadata/{dataset}")
    def describe(self, dataset: str) -> Any:
        return self._get(f"/metadata/{seg(dataset)}")
