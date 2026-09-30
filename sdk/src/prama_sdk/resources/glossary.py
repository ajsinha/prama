"""The business glossary: terms, imports from Alation or Collibra, and bindings.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama_sdk.base import Resource, endpoint, namespace, seg
from prama_sdk.resources._files import FileLike, upload


@namespace("glossary")
class Glossary(Resource):
    """Business terms and what each names."""

    @endpoint("GET", "/glossary/terms")
    def list(self, *, q: str = "") -> Any:
        """Every term with its bindings; *q* searches names, synonyms and definitions."""
        return self._get("/glossary/terms", q=q or None)

    def search(self, q: str) -> Any:
        return self.list(q=q)

    @endpoint("GET", "/glossary/terms/{name}")
    def get(self, name: str) -> Any:
        return self._get(f"/glossary/terms/{seg(name)}")

    @endpoint("POST", "/glossary/import")
    def import_export(self, vendor: str, export: FileLike) -> Any:
        """Terms from an ``alation`` or ``collibra`` export; ``dropped`` lists what did not come."""
        return self._call(
            "POST",
            "/glossary/import",
            data={"vendor": vendor},
            files={"export": upload(export, f"{vendor}.json", "application/json")},
        )

    @endpoint("POST", "/glossary/terms/{name}/bindings")
    def bind(self, name: str, kind: str, ref: str) -> Any:
        """Bind a term to a ``concept`` (by name), ``dataset`` or ``attribute`` (dataset.column)."""
        return self._post(f"/glossary/terms/{seg(name)}/bindings", {"kind": kind, "ref": ref})
