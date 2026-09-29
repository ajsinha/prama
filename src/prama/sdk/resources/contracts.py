"""Data contracts: import, export, diff, and the gate a build calls.

A file argument is a path (its suffix says the format: ``.json``, ``.jsonl``,
``.csv``, ``.yaml``), Python rows or a document, or ``(filename, bytes)``.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from prama.sdk.base import Resource, endpoint, namespace, seg
from prama.sdk.resources._text_files import Upload, upload


@namespace("contracts")
class Contracts(Resource):
    """ODCS contracts, and whether data keeps them."""

    @endpoint("POST", "/contracts/import")
    def read(self, contract: Upload) -> Any:
        """An ODCS contract read as a declaration, its quality checks as PQL, and what
        did not come across. Stores nothing."""
        return self._call(
            "POST",
            "/contracts/import",
            files={"contract": upload(contract, "contract.json")},
        )

    @endpoint("GET", "/contracts/export/{dataset}")
    def export(self, dataset: str) -> Any:
        """A declared dataset, by slug, as an ODCS contract document."""
        return self._get(f"/contracts/export/{seg(dataset)}")

    @endpoint("POST", "/contracts/check")
    def check(self, contract: Upload, data: Upload, *, allow_additions: bool = False) -> Any:
        """Whether *data* keeps *contract*'s promises. ``result["breached"]`` is the gate;
        a breach is a result, not an exception."""
        return self._call(
            "POST",
            "/contracts/check",
            files={
                "contract": upload(contract, "contract.json"),
                "data": upload(data, "rows.json"),
            },
            data={"allow_additions": "true" if allow_additions else "false"},
        )

    @endpoint("POST", "/contracts/diff")
    def diff(
        self,
        before: Upload,
        after: Upload,
        *,
        key: Sequence[str] = (),
        ignore: Sequence[str] = (),
    ) -> Any:
        """What changed between two versions of a dataset, rows matched by *key*."""
        return self._call(
            "POST",
            "/contracts/diff",
            files={"before": upload(before, "before.json"), "after": upload(after, "after.json")},
            data={"key": ",".join(key), "ignore": ",".join(ignore)},
        )
