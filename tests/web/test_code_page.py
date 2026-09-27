"""The Code page receives an upload into lineage, and refuses a hostile one.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

from prama.db import Database


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in entries.items():
            archive.writestr(name, body)
    return buffer.getvalue()


async def test_an_upload_is_read_into_lineage(
    ui: Any, started_database: Database, tenant_id: str, tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.chdir(tmp_path)  # codeintake.workdir is relative
    body = _zip({"load.sql": b"INSERT INTO stg.a (amt) SELECT t.notional FROM raw.trades t;"})
    reply = await ui.post(
        "/code/zip", data={"source": "app"}, files={"archive": ("app.zip", body, "application/zip")}
    )
    assert reply.status_code == 303
    async with started_database.unit_of_work() as uow:
        assert await uow.lineage.edges(tenant_id, dataset="stg.a")
    page = await ui.get("/code")
    assert "succeeded" in page.text


async def test_a_hostile_upload_is_refused_on_the_page(
    ui: Any, started_database: Database, tenant_id: str, tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.chdir(tmp_path)
    body = _zip({"../../escape.sql": b"select 1"})
    await ui.post(
        "/code/zip", data={"source": "evil"}, files={"archive": ("e.zip", body, "application/zip")}
    )
    page = await ui.get("/code")
    assert "climbs out" in page.text or "could not be received" in page.text
    assert not (tmp_path.parent / "escape.sql").exists()
