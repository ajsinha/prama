"""Business context and metadata on datasets, the rules they imply, and finding data by meaning.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama_sdk.base import Resource, body, endpoint, namespace, seg


@namespace("metadata")
class Metadata(Resource):
    """Templates, values and context; implied rules; search by what data means."""

    @endpoint("GET", "/metadata/search")
    def search(self, q: str) -> Any:
        return self._get("/metadata/search", q=q)

    @endpoint("GET", "/metadata/ask")
    def ask(self, q: str) -> Any:
        """Ranked and explained by a discover model, when one is configured."""
        return self._get("/metadata/ask", q=q)

    @endpoint("GET", "/metadata/correlation")
    def correlation(self) -> Any:
        """Same meaning across datasets, where they disagree, and queried-together hints."""
        return self._get("/metadata/correlation")

    @endpoint("GET", "/metadata/templates")
    def templates(self) -> Any:
        return self._get("/metadata/templates")

    @endpoint("POST", "/metadata/templates/starter")
    def install_starter(self, starter: str) -> Any:
        """``data-quality-attribute`` or ``data-quality-dataset``."""
        return self._post("/metadata/templates/starter", {"starter": starter})

    @endpoint("POST", "/metadata/templates")
    def save_template(
        self, document: dict[str, Any] | None = None, *, yaml: str | None = None
    ) -> Any:
        """Save your own template, as a mapping or as YAML text."""
        return self._post("/metadata/templates", body(document=document, yaml=yaml))

    @endpoint("GET", "/metadata/proposals")
    def proposals(self, *, dataset: str = "") -> Any:
        """Controls the metadata implies, waiting for a person to accept or reject."""
        return self._get("/metadata/proposals", dataset=dataset or None)

    @endpoint("PUT", "/metadata/{target}/values")
    def set(self, target: str, **values: Any) -> Any:
        """``client.metadata.set("trades.account_id", mandatory="yes")``.

        Returns what changed and the proposals now implied for the dataset.
        """
        return self._put(f"/metadata/{seg(target)}/values", {"values": values})

    @endpoint("PUT", "/metadata/{target}/context")
    def set_context(self, target: str, text: str) -> Any:
        """Business context on a dataset or attribute, recorded as an amendment."""
        return self._put(f"/metadata/{seg(target)}/context", {"text": text})

    @endpoint("POST", "/metadata/{dataset}/rules")
    def author_rule(self, dataset: str, pql: str) -> Any:
        """A rule written by hand. It is proposed; somebody else approves it."""
        return self._post(f"/metadata/{seg(dataset)}/rules", {"pql": pql})

    @endpoint("GET", "/metadata/{dataset}")
    def describe(self, dataset: str) -> Any:
        """Context, metadata, attributes, rules and implied rules of one dataset."""
        return self._get(f"/metadata/{seg(dataset)}")
