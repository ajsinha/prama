"""Identifiers, time, JSON and the plugin registry.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from prama.core import pjson
from prama.core.clock import FixedClock, ManualClock, SystemClock
from prama.core.errors import PramaError, RegistryError
from prama.core.ids import (
    TenantId,
    UlidFactory,
    is_ulid,
    new_ulid,
    ulid_timestamp_millis,
)
from prama.core.registry import Capability, Plugin, PluginManifest, Registry, RegistryCatalogue


class TestErrors:
    def test_an_error_cannot_be_raised_without_a_remedy(self) -> None:
        with pytest.raises(TypeError):
            PramaError("something failed")  # type: ignore[call-arg]

    def test_rendering_states_what_why_and_next(self) -> None:
        rendered = str(PramaError("it broke", remedy="do this", context={"k": 1}))
        assert "it broke" in rendered
        assert "Next: do this" in rendered
        assert "k=1" in rendered


class TestIds:
    def test_ulids_minted_in_a_tight_loop_are_strictly_increasing(self) -> None:
        ids = [new_ulid() for _ in range(2000)]
        assert ids == sorted(ids)
        assert len(set(ids)) == len(ids)

    def test_within_one_millisecond_monotonicity_still_holds(self) -> None:
        factory = UlidFactory(clock=FixedClock(datetime(2026, 3, 31, tzinfo=UTC)))
        ids = [factory.new() for _ in range(500)]
        assert ids == sorted(ids)

    def test_timestamp_round_trips(self) -> None:
        clock = FixedClock(datetime(2026, 3, 31, 6, 30, tzinfo=UTC))
        value = UlidFactory(clock=clock).new()
        assert ulid_timestamp_millis(value) == clock.epoch_millis()

    def test_typed_ids_render_with_a_prefix_but_store_bare(self) -> None:
        tenant = TenantId.new()
        assert tenant.qualified.startswith("tenant:")
        assert is_ulid(str(tenant))
        assert TenantId.parse(tenant.qualified) == tenant


class TestClock:
    def test_system_clock_is_utc_aware(self) -> None:
        assert SystemClock().now().tzinfo is not None

    def test_manual_clock_advances_wall_and_monotonic_together(self) -> None:
        clock = ManualClock()
        before = clock.now()
        clock.advance(90)
        assert (clock.now() - before).total_seconds() == 90
        assert clock.monotonic() == 90

    def test_a_clock_does_not_run_backwards(self) -> None:
        with pytest.raises(ValueError, match="backwards"):
            ManualClock().advance(-1)

    def test_naive_instants_are_refused(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            FixedClock(datetime(2026, 1, 1))


class TestJson:
    def test_canonical_encoding_is_order_independent(self) -> None:
        # Evidence records are hashed; a hash that depends on insertion order is
        # not a hash of the content.
        assert pjson.canonical({"b": 1, "a": 2}) == pjson.canonical({"a": 2, "b": 1})

    def test_non_finite_floats_become_null(self) -> None:
        assert pjson.loads(pjson.dumps({"x": math.nan, "y": math.inf})) == {"x": None, "y": None}

    def test_naive_datetimes_are_refused(self) -> None:
        with pytest.raises(TypeError, match="naive"):
            pjson.dumps({"t": datetime(2026, 1, 1)})

    def test_aware_datetimes_serialise_with_a_z(self) -> None:
        assert "Z" in pjson.dumps({"t": datetime(2026, 1, 1, tzinfo=UTC)})


class _Backend(Plugin):
    pass


class _Duck(_Backend):
    plugin_key = "duckdb"

    @classmethod
    def manifest(cls) -> PluginManifest:
        return PluginManifest(
            key="duckdb",
            kind="backend",
            display_name="DuckDB",
            version="1.0",
            capabilities=(Capability("pushdown.sql", {"dialect": "duckdb"}),),
        )


class _Mislabelled(_Backend):
    @classmethod
    def manifest(cls) -> PluginManifest:
        return PluginManifest(key="x", kind="connector", display_name="X", version="1")


class TestRegistry:
    def test_registration_and_capability_lookup(self) -> None:
        registry: Registry[_Backend] = Registry("backend", _Backend)
        registry.register(_Duck)
        assert registry.keys() == ["duckdb"]
        assert [m.key for m in registry.with_capability("pushdown.sql")] == ["duckdb"]
        assert registry.manifest("duckdb").attribute("pushdown.sql", "dialect") == "duckdb"

    def test_unknown_key_lists_what_is_available(self) -> None:
        registry: Registry[_Backend] = Registry("backend", _Backend)
        registry.register(_Duck)
        with pytest.raises(RegistryError) as caught:
            registry.get("spark")
        assert "duckdb" in caught.value.remedy

    def test_a_manifest_declaring_the_wrong_kind_is_refused_at_registration(self) -> None:
        registry: Registry[_Backend] = Registry("backend", _Backend)
        with pytest.raises(RegistryError, match="declares kind"):
            registry.register(_Mislabelled)

    def test_duplicate_registration_requires_explicit_replace(self) -> None:
        registry: Registry[_Backend] = Registry("backend", _Backend)
        registry.register(_Duck)
        with pytest.raises(RegistryError, match="already registered"):
            registry.register(_Duck)
        registry.register(_Duck, replace=True)

    def test_disabled_plugins_are_hidden_and_refused(self) -> None:
        registry: Registry[_Backend] = Registry("backend", _Backend)
        registry.register(_Duck)
        registry.disable(["duckdb"])
        assert registry.keys() == []
        with pytest.raises(RegistryError, match="disabled"):
            registry.get("duckdb")

    def test_catalogue_holds_registries_by_kind(self) -> None:
        catalogue = RegistryCatalogue()
        catalogue.create("backend", _Backend)
        assert catalogue.kinds() == ["backend"]
        with pytest.raises(RegistryError, match="already exists"):
            catalogue.create("backend", _Backend)
