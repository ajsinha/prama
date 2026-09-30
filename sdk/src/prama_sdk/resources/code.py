"""Application code: receive it, read its lineage (never executing it), review a change.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama_sdk.base import Resource, body, endpoint, namespace, seg
from prama_sdk.resources._files import FileLike, upload


@namespace("code")
class Code(Resource):
    """Code intake and change review."""

    @endpoint("POST", "/code/zip")
    def add_zip(self, source: str, archive: FileLike, *, dialect: str = "ansi") -> Any:
        """Receive a ZIP (a path or its bytes) and read its lineage. Returns the run."""
        return self._call(
            "POST",
            "/code/zip",
            data={"source": source, "dialect": dialect},
            files={"archive": upload(archive, f"{source}.zip", "application/zip")},
        )

    @endpoint("POST", "/code/git")
    def add_git(
        self,
        source: str,
        url: str,
        *,
        ref: str = "main",
        credential_ref: str | None = None,
        dialect: str = "ansi",
    ) -> Any:
        """Fetch one ref of a repository and read its lineage. Private addresses are refused."""
        return self._post(
            "/code/git",
            body(source=source, url=url, ref=ref, credential_ref=credential_ref, dialect=dialect),
        )

    @endpoint("GET", "/code/sources")
    def sources(self) -> Any:
        return self._get("/code/sources")

    @endpoint("GET", "/code/runs")
    def runs(self, *, limit: int | None = None) -> Any:
        """Recent readings with their coverage: files read, edges, gaps."""
        return self._get("/code/runs", limit=limit)

    @endpoint("GET", "/code/runs/{run_id}/units")
    def units(self, run_id: str) -> Any:
        """Each file one reading looked at, and the gaps it left."""
        return self._get(f"/code/runs/{seg(run_id)}/units")

    @endpoint("POST", "/code/review")
    def review(
        self,
        base: FileLike,
        head: FileLike,
        *,
        dialect: str = "ansi",
        offline: bool = False,
        base_label: str = "base",
        head_label: str = "head",
    ) -> Any:
        """What a change (two ZIPs) does to lineage and the controls resting on it.

        ``fails`` is true when a live control loses its basis; ``markdown`` is the
        pull-request comment.
        """
        return self._call(
            "POST",
            "/code/review",
            data={
                "dialect": dialect,
                "offline": str(offline).lower(),
                "base_label": base_label,
                "head_label": head_label,
            },
            files={
                "base": upload(base, "base.zip", "application/zip"),
                "head": upload(head, "head.zip", "application/zip"),
            },
        )

    @endpoint("POST", "/code/review/git")
    def review_git(
        self,
        url: str,
        base: str,
        head: str,
        *,
        credential_ref: str | None = None,
        dialect: str = "ansi",
        offline: bool = False,
    ) -> Any:
        """The same review over two refs of a repository."""
        return self._post(
            "/code/review/git",
            body(
                url=url,
                base=base,
                head=head,
                credential_ref=credential_ref,
                dialect=dialect,
                offline=offline,
            ),
        )
