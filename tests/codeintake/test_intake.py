"""Code intake refuses hostile input with a named reason, and never executes code.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest

from prama.codeintake.archive import IntakeRefused, Limits, extract
from prama.codeintake.git import check_location
from prama.db import Database


def _zip(path: Path, entries: dict[str, bytes], *, links: dict[str, str] | None = None) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in entries.items():
            archive.writestr(name, body)
        for name, target in (links or {}).items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, target)
    return path


@pytest.mark.parametrize(
    ("entries", "reason"),
    [
        ({"../../etc/cron.d/x": b"x"}, "climbs out"),
        ({"/etc/passwd": b"x"}, "absolute path"),
        ({"C:/Windows/x": b"x"}, "absolute path"),
    ],
)
def test_a_path_that_escapes_is_refused(
    tmp_path: Path, entries: dict[str, bytes], reason: str
) -> None:
    archive = _zip(tmp_path / "bad.zip", entries)
    with pytest.raises(IntakeRefused, match=reason):
        extract(archive, tmp_path / "out")
    # Nothing was written anywhere: not in the root, not outside it.
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").rglob("*"))
    assert not (tmp_path.parent / "etc").exists()


def test_a_bomb_is_refused_before_extraction(tmp_path: Path) -> None:
    archive = _zip(tmp_path / "bomb.zip", {"zeros.sql": b"\x00" * 5_000_000})
    with pytest.raises(IntakeRefused, match="bomb"):
        extract(archive, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_too_many_entries_or_too_large_a_file_is_refused(tmp_path: Path) -> None:
    many = _zip(tmp_path / "many.zip", {f"f{i}.sql": b"select 1" for i in range(20)})
    with pytest.raises(IntakeRefused, match="entries"):
        extract(many, tmp_path / "a", Limits(max_entries=10))
    big = _zip(tmp_path / "big.zip", {"big.sql": b"select 1;" * 2000})
    with pytest.raises(IntakeRefused, match="per-file"):
        extract(big, tmp_path / "b", Limits(max_file=1000, max_ratio=1e9))


def test_a_symlink_is_recorded_and_never_created(tmp_path: Path) -> None:
    archive = _zip(tmp_path / "l.zip", {"ok.sql": b"select 1"}, links={"root": "/"})
    snapshot = extract(archive, tmp_path / "out")
    assert "root" in snapshot.symlinks
    assert not (tmp_path / "out" / "root").exists()
    assert "ok.sql" in snapshot.files  # the control: ordinary files arrive


def test_nothing_received_is_executable(tmp_path: Path) -> None:
    archive = _zip(tmp_path / "x.zip", {"run.sh": b"#!/bin/sh\ntouch /tmp/pwned"})
    extract(archive, tmp_path / "out")
    assert not (tmp_path / "out" / "run.sh").stat().st_mode & 0o111


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("file:///etc", "not https or ssh"),
        ("http://github.com/a/b", "not https or ssh"),
        ("ext::sh -c touch% /tmp/pwned", "not https or ssh"),
        ("-uhttps://x/y", "may not begin with '-'"),
        ("https://169.254.169.254/latest/meta-data", "non-public address"),
        ("https://127.0.0.1/repo.git", "non-public address"),
        ("https://10.0.0.8/repo.git", "non-public address"),
    ],
)
def test_a_location_that_is_not_a_public_repository_is_refused(url: str, reason: str) -> None:
    with pytest.raises(IntakeRefused, match=reason):
        check_location(url)


def test_an_allow_list_is_enforced_and_a_listed_host_passes() -> None:
    with pytest.raises(IntakeRefused, match="allowed_hosts"):
        check_location(
            "https://gitlab.example/x.git", allowed_hosts=["git.bank.example"], resolve=False
        )
    assert check_location(
        "git@git.bank.example:risk/etl.git", allowed_hosts=["git.bank.example"], resolve=False
    )


async def test_a_received_zip_is_read_into_lineage_and_its_tree_deleted(
    tmp_path: Path, started_database: Database, tenant_id: str
) -> None:
    from prama.codeintake.service import analyse

    marker = tmp_path / "executed.marker"
    archive = _zip(
        tmp_path / "app.zip",
        {
            "etl/load.sql": b"INSERT INTO stg.a (amt) SELECT t.notional FROM raw.trades t;",
            "setup.py": f"open({str(marker)!r}, 'w').write('ran')".encode(),
            "README.md": b"docs",
        },
    )
    snapshot = extract(archive, tmp_path / "quarantine")
    async with started_database.unit_of_work() as uow:
        source = await uow.code.ensure_source(tenant_id, "app", kind="zip")
        run = await analyse(uow, tenant_id, source, snapshot)
        units = {u.path: u for u in await uow.code.units(tenant_id, run.id)}
        edges = await uow.lineage.edges(tenant_id, dataset="stg.a")
    assert run.status == "succeeded", run.error
    assert units["etl/load.sql"].kind == "sql" and units["etl/load.sql"].statements == 1
    assert units["setup.py"].kind == "python"
    assert edges and edges[0].unit_id == units["etl/load.sql"].id
    assert not marker.exists(), "code in the archive was executed"
    assert not snapshot.root.exists(), "the extracted tree was kept"
