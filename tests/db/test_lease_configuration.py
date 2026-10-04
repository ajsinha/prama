"""``concurrency.lease`` is read: the provider it names, and the lease it describes.

The section shipped in configuration with four settings and nothing read any
of them: every lease was the database provider with constants written at each
call site, whatever an operator set.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from prama.core.concurrency.leases import MemoryLeaseProvider
from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.core.errors import ConfigError
from prama.db import Database
from prama.db.lease_provider import DatabaseLeaseProvider


def _database(tmp_path: Path, **lease: Any) -> Database:
    builder = ConfigurationBuilder().with_defaults(DEFAULTS)
    builder.with_mapping(
        {
            "database": {"dialect": "sqlite", "sqlite": {"path": str(tmp_path / "p.db")}},
            "concurrency": {"lease": lease},
        },
        name="test",
    )
    return Database.from_config(builder.build())


def test_the_configured_lease_is_the_default_for_every_holder(tmp_path: Path) -> None:
    database = _database(tmp_path, ttl="45s", renew_interval="15s", clock_skew_allowance="3s")
    provider = database.lease_provider()
    assert isinstance(provider, DatabaseLeaseProvider)
    held = provider.hold("anything")
    assert held._settings.ttl_seconds == 45.0
    assert held._settings.renew_interval_seconds == 15.0
    assert held._settings.clock_skew_allowance_seconds == 3.0


async def test_the_memory_provider_is_one_per_process(tmp_path: Path) -> None:
    database = _database(tmp_path, provider="memory")
    first, second = database.lease_provider(), database.lease_provider()
    assert isinstance(first, MemoryLeaseProvider) and first is second
    # One instance, so the second holder is refused: a fresh provider per call
    # would have granted both, and two servers would both run the work.
    assert await first.acquire("scheduler", "a", 30.0) is not None
    assert await second.acquire("scheduler", "b", 30.0) is None


def test_an_unknown_provider_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"concurrency\.lease\.provider"):
        _database(tmp_path, provider="redis")


def test_a_renewal_slower_than_the_lease_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="renew_interval must be shorter"):
        _database(tmp_path, ttl="10s", renew_interval="20s")
