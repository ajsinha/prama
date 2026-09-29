"""Static URLs carry a digest of their content, so a browser cannot mix versions.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import httpx
import pytest

from prama.web import rendering


async def test_every_stylesheet_and_script_is_versioned_by_its_content(
    ui: httpx.AsyncClient,
) -> None:
    """The defect this guards: a cached themes.css without the Maya tokens met
    a fresh shell.css that needed them, and every light theme went white."""
    text = (await ui.get("/estate")).text
    links = re.findall(r'(?:href|src)="(/static/[^"]+)"', text)
    assert any("css/themes.css" in link for link in links)
    for link in links:
        path, _, query = link.partition("?")
        body = (rendering.STATIC_DIR / path.removeprefix("/static/")).read_bytes()
        assert f"v={hashlib.sha256(body).hexdigest()[:12]}" in query, link
        assert (await ui.get(link)).status_code == 200, link


def test_the_version_changes_when_the_content_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rendering, "STATIC_DIR", tmp_path)
    monkeypatch.setattr(rendering, "_STATIC_VERSIONS", {})
    sheet = tmp_path / "a.css"
    sheet.write_text("body { color: red }")
    before = rendering.static_version("a.css")
    sheet.write_text("body { color: blue }")
    os.utime(sheet, ns=(1, sheet.stat().st_mtime_ns + 1_000_000))
    assert rendering.static_version("a.css") != before
    assert rendering.static_version("missing.css") == ""
