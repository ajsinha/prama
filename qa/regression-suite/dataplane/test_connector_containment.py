"""A connector may not read outside the root it was given.

QA round 2, `CON-132`. `FilesystemConnector._resolve` built its target with
`self._root.joinpath(*path)` and checked nothing else, so a path component of
`..` walked straight out of the configured directory. `root_path` is what an
operator is shown as the boundary of a connection, and it bounded nothing:
`describe()` returned the columns of a file outside it and `snapshot()` hashed
that file's contents.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from prama.connect.sources.filesystem import FilesystemConnector
from prama.connect.spi import UnauthorisedError


@pytest.fixture
def estate(tmp_path: Path) -> Path:
    """A connection's root, and a secret sitting beside it."""
    root = tmp_path / "landing"
    root.mkdir()
    (root / "positions.csv").write_text("account_id,notional\nA1,10\n")
    outside = tmp_path / "private"
    outside.mkdir()
    (outside / "credentials.csv").write_text("user,password\nadmin,hunter2\n")
    return tmp_path


async def test_a_dotdot_path_cannot_escape_the_configured_root(estate: Path) -> None:
    connector = FilesystemConnector({"root_path": str(estate / "landing")})
    async with connector:
        # Inside the root, so this must work — a containment check that also
        # breaks ordinary reads would be indistinguishable from a broken
        # connector, and would be "fixed" by removing it.
        inside = await connector.describe(("positions.csv",))
        assert [c.name for c in inside.columns] == ["account_id", "notional"]

        with pytest.raises(UnauthorisedError) as refusal:
            await connector.describe(("..", "private", "credentials.csv"))
        # And the refusal must not leak what it refused to read.
        assert "password" not in str(refusal.value)


async def test_an_escaping_path_is_not_snapshotted(estate: Path) -> None:
    """Refusing `describe` and allowing `snapshot` would leak the file anyway.

    A digest of a file confirms its contents to anyone who can guess them, so
    the boundary has to hold on every method that takes a path, not only the
    one that returns columns.
    """
    connector = FilesystemConnector({"root_path": str(estate / "landing")})
    async with connector:
        with pytest.raises(UnauthorisedError):
            await connector.snapshot(("..", "private", "credentials.csv"))
