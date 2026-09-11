"""Snowflake, tested as far as it honestly can be without an account.

There is no Snowflake here and there is not going to be one, so what these
tests cover is everything short of a warehouse answering: the SQL the dialect
produces, the refusals, and — most importantly — that the connector keeps
saying it is unverified.

That last one is the point. An unverified connector is a reasonable thing to
ship; an unverified connector that has quietly stopped saying so is not, and
the difference is one careless edit.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.connect.sources.sql.snowflake import SnowflakeConnector, SnowflakeDialect
from prama.connect.spi import ConnectorError, SamplePlan, SamplingStrategy, SnapshotKind


def connector(**changes) -> SnowflakeConnector:
    config = {
        "account": "xy12345.eu-west-1",
        "user": "prama",
        "password": "secret",
        "warehouse": "COMPUTE_WH",
        "database": "ANALYTICS",
        "schema": "PUBLIC",
    }
    config.update(changes)
    return SnowflakeConnector(config)


class TestItKeepsSayingItIsUnverified:
    """The guard that matters most here.

    A connector nobody has run is fine to ship and dangerous to forget about.
    These fail if the warning is removed, so removing it has to be deliberate.
    """

    def test_the_module_says_nobody_has_run_it(self) -> None:
        from prama.connect.sources.sql import snowflake

        assert "Nobody has run this against a Snowflake account" in (snowflake.__doc__ or "")

    def test_the_class_says_so_too(self) -> None:
        """Somebody reading the class in an editor sees it without scrolling."""
        assert "Never run against a real account" in (SnowflakeConnector.__doc__ or "")

    def test_the_catalogue_entry_says_so(self) -> None:
        """The source picker is where a person chooses this, so the warning has
        to survive into the UI rather than staying in the source."""
        description = SnowflakeConnector.manifest().description
        assert "NOT YET VERIFIED" in description

    def test_the_pyproject_extra_says_so(self) -> None:
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[3]
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
        assert "NOT YET VERIFIED against a real account" in text


class TestCostIsADesignConstraint:
    def test_row_estimates_come_from_the_catalogue_not_a_scan(self) -> None:
        """Every other source here can be scanned for free on a laptop. A
        `count(*)` over forty Snowflake tables is a line on an invoice."""
        sql = SnowflakeDialect().estimate_rows_sql()
        assert sql is not None
        assert "row_count" in sql.lower()
        assert "count(*)" not in sql.lower()

    def test_the_dialect_claims_a_cheap_estimate(self) -> None:
        assert SnowflakeDialect().has_cheap_row_estimate

    def test_discovery_does_not_scan(self) -> None:
        sql = SnowflakeDialect().list_objects_sql(include_views=False)
        assert "information_schema" in sql.lower()
        assert "count(*)" not in sql.lower()


class TestTimeTravelIsAnExactSnapshot:
    def test_the_snapshot_kind_is_exact(self) -> None:
        """The one place this connector promises more than the PostgreSQL one
        rather than less: a replay can read what the control read."""
        assert SnowflakeDialect().snapshot_kind.is_exact
        assert SnowflakeDialect().snapshot_kind is SnapshotKind.TRANSACTION_ID

    def test_it_asks_for_a_statement_identifier(self) -> None:
        assert "LAST_QUERY_ID" in (SnowflakeDialect().snapshot_sql() or "")


class TestIdentifiersAreQuoted:
    def test_names_are_quoted_because_snowflake_folds_upward(self) -> None:
        """Unquoted `positions` resolves to `POSITIONS`, so a table genuinely
        named `positions` is not found. Quoting uses the catalogue's spelling."""
        assert SnowflakeDialect().quote("positions") == '"positions"'

    def test_an_embedded_quote_is_doubled(self) -> None:
        assert SnowflakeDialect().quote('a"b') == '"a""b"'

    def test_a_qualified_path_quotes_every_part(self) -> None:
        assert SnowflakeDialect().qualify(("ANALYTICS", "positions")) == ('"ANALYTICS"."positions"')


class TestSamplingIsReal:
    def test_a_fractional_sample_uses_the_sample_clause(self) -> None:
        """Where a source has no sampling the base class reads ordinarily and
        calls the result approximate. Snowflake does not need that excuse."""
        plan = SamplePlan(strategy=SamplingStrategy.RESERVOIR, fraction=0.1)
        sql = SnowflakeDialect().sample_from(("S", "t"), plan)
        assert "SAMPLE BERNOULLI (10)" in sql

    def test_a_seeded_sample_is_reproducible(self) -> None:
        plan = SamplePlan(strategy=SamplingStrategy.RESERVOIR, fraction=0.5, seed=42)
        assert "SEED (42)" in SnowflakeDialect().sample_from(("S", "t"), plan)

    def test_a_row_sample_asks_for_rows(self) -> None:
        plan = SamplePlan(strategy=SamplingStrategy.RESERVOIR, rows=1000)
        assert "SAMPLE (1000 ROWS)" in SnowflakeDialect().sample_from(("S", "t"), plan)

    def test_the_dialect_claims_native_sampling(self) -> None:
        assert SnowflakeDialect().has_native_sampling


class TestSessionSetup:
    def test_a_statement_timeout_is_imposed(self) -> None:
        statements = SnowflakeDialect().session_setup_sql(statement_timeout_ms=30_000)
        assert any("STATEMENT_TIMEOUT_IN_SECONDS = 30" in s for s in statements)

    def test_read_only_is_documented_as_coming_from_the_role(self) -> None:
        """Snowflake has no session read-only switch, so a connector claiming it
        cannot write when only its manners stop it would be worse than one that
        made no claim."""
        source = SnowflakeDialect.session_setup_sql.__doc__ or ""
        assert "role" in source.lower()


class TestRefusals:
    @pytest.mark.parametrize("missing", ["account", "user", "database", "warehouse"])
    async def test_each_required_field_is_named(self, missing: str) -> None:
        with pytest.raises(ConnectorError, match=f"needs {missing}"):
            await connector(**{missing: ""}).open()

    async def test_it_says_why_a_warehouse_is_required(self) -> None:
        with pytest.raises(ConnectorError) as caught:
            await connector(warehouse="").open()
        assert "nothing to run on" in caught.value.remedy

    async def test_using_it_unopened_is_a_clear_error(self) -> None:
        with pytest.raises(ConnectorError, match="before it was opened"):
            await connector()._fetch("SELECT 1")

    async def test_a_missing_driver_names_the_extra(self) -> None:
        """The driver is not installed here, which is the ordinary case."""
        with pytest.raises(ConnectorError, match="driver is not installed") as caught:
            await connector().open()
        assert "prama[snowflake]" in caught.value.remedy


class TestTheOrdinarySqlContract:
    def test_it_declares_pushdown(self) -> None:
        assert connector().pushdown_capabilities()

    def test_it_can_run_controls(self) -> None:
        """There is a real query engine on the other end."""
        assert connector().can_run_controls

    def test_describe_takes_schema_then_name(self) -> None:
        sql = SnowflakeDialect().describe_sql()
        assert sql.index("table_schema") < sql.index("table_name")

    def test_placeholders_are_question_marks(self) -> None:
        """The driver's style, not the database's."""
        assert SnowflakeDialect().placeholder(1) == "?"
