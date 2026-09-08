"""PostgreSQL's dialect: the parts that are specific, and why.

The connector itself needs a server. Everything decided *before* a connection
is made — the SQL, the session settings, the sampling method — is decided here,
and is where the mistakes that matter would live.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.connect.capability import PushdownFeature
from prama.connect.sources.sql import PostgresConnector, PostgresDialect
from prama.connect.spi import SamplePlan, SamplingStrategy, SnapshotKind

DIALECT = PostgresDialect()


class TestSafety:
    def test_the_session_is_read_only_at_the_server(self) -> None:
        # Not "we are careful not to write". A customer pointing Prama at a
        # production database should be protected by their server, not by our
        # discipline in query construction.
        setup = DIALECT.session_setup_sql(statement_timeout_ms=30_000)
        assert any("default_transaction_read_only = on" in s for s in setup)

    def test_every_statement_carries_a_timeout(self) -> None:
        setup = DIALECT.session_setup_sql(statement_timeout_ms=30_000)
        assert any("statement_timeout = 30000" in s for s in setup)

    def test_reading_never_waits_behind_the_business(self) -> None:
        # A lock_timeout is what stops a profiling query queueing behind, and
        # then blocking, the transactions the bank is actually running.
        setup = DIALECT.session_setup_sql(statement_timeout_ms=30_000)
        assert any("lock_timeout" in s for s in setup)

    def test_an_abandoned_session_cannot_sit_in_a_transaction_forever(self) -> None:
        setup = DIALECT.session_setup_sql(statement_timeout_ms=30_000)
        assert any("idle_in_transaction_session_timeout" in s for s in setup)


class TestCatalogue:
    def test_discovery_asks_only_for_objects_the_role_can_read(self) -> None:
        # Listing tables that then fail to read produces a catalogue full of
        # objects nobody can use, and support tickets about each one.
        sql = DIALECT.list_objects_sql(include_views=True)
        assert "has_table_privilege" in sql

    def test_system_schemas_are_left_out(self) -> None:
        sql = DIALECT.list_objects_sql(include_views=True)
        for schema in ("pg_catalog", "information_schema", "pg_toast"):
            assert f"'{schema}'" in sql

    def test_views_can_be_excluded(self) -> None:
        def relkinds(sql: str) -> str:
            return sql.split("c.relkind IN ")[1].split(")")[0]

        assert "'v'" in relkinds(DIALECT.list_objects_sql(include_views=True))
        assert "'v'" not in relkinds(DIALECT.list_objects_sql(include_views=False))
        assert "'r'" in relkinds(DIALECT.list_objects_sql(include_views=False))

    def test_row_counts_come_from_the_catalogue_not_from_a_scan(self) -> None:
        # count(*) on a billion-row table, issued because somebody opened a
        # page, is the single easiest way to make a DBA ban a tool.
        sql = DIALECT.list_objects_sql(include_views=True)
        assert "reltuples" in sql
        assert "count(*)" not in sql.lower()
        assert DIALECT.has_cheap_row_estimate

    def test_a_never_analysed_table_reports_unknown_rather_than_minus_one(self) -> None:
        # reltuples is -1 before ANALYZE has run. Passing that through would
        # show "-1 rows" in the UI.
        assert "reltuples < 0 THEN NULL" in DIALECT.list_objects_sql(include_views=True)
        assert "reltuples < 0 THEN NULL" in str(DIALECT.estimate_rows_sql())

    def test_column_comments_are_collected(self) -> None:
        # Often the only business description of a column that exists anywhere.
        assert "col_description" in DIALECT.describe_sql()

    def test_dropped_columns_are_not_offered(self) -> None:
        # pg_attribute keeps them. Showing a dropped column as part of a live
        # schema would make every declaration against it fail mysteriously.
        assert "attisdropped" in DIALECT.describe_sql()


class TestSnapshot:
    def test_the_snapshot_is_a_wal_position(self) -> None:
        assert DIALECT.snapshot_kind is SnapshotKind.LSN
        assert DIALECT.snapshot_kind.is_exact

    def test_a_read_replica_reports_a_position_that_actually_moves(self) -> None:
        # pg_current_wal_lsn() does not advance on a standby, so every snapshot
        # taken against a replica would be identical and evidence would quietly
        # stop being replayable. Many estates profile the replica by policy.
        sql = str(DIALECT.snapshot_sql())
        assert "pg_is_in_recovery()" in sql
        assert "pg_last_wal_replay_lsn" in sql


class TestSampling:
    def test_sampling_is_done_by_the_server(self) -> None:
        sql = DIALECT.sample_from(("sales", "orders"), SamplePlan(fraction=0.05))
        assert "TABLESAMPLE" in sql
        assert "5%" not in sql and "(5)" in sql

    def test_bernoulli_not_system(self) -> None:
        # SYSTEM picks whole pages, so rows inserted together are selected
        # together: any column correlated with insertion order — a date, a
        # branch, a batch id — comes back skewed, and a profile built on it is
        # worse than no profile.
        assert "BERNOULLI" in DIALECT.sample_from(("s", "t"), SamplePlan(fraction=0.1))

    def test_a_seeded_sample_is_reproducible(self) -> None:
        # An evidence record that cannot be reproduced is an assertion.
        assert "REPEATABLE (42)" in DIALECT.sample_from(
            ("s", "t"), SamplePlan(fraction=0.1, seed=42)
        )

    def test_a_full_read_does_not_sample(self) -> None:
        assert "TABLESAMPLE" not in DIALECT.stream_sql(("s", "t"), SamplePlan())

    def test_a_fraction_is_clamped_to_something_the_server_accepts(self) -> None:
        assert "(100)" in DIALECT.sample_from(("s", "t"), SamplePlan(fraction=5.0))
        assert "TABLESAMPLE" in DIALECT.sample_from(("s", "t"), SamplePlan(fraction=0.0))

    def test_stratified_sampling_is_not_silently_downgraded(self) -> None:
        # TABLESAMPLE cannot stratify. Returning an unstratified sample under
        # the name of a stratified one is the kind of quiet substitution that
        # makes a profile untrustworthy without making it look wrong.
        from prama.connect.sources.sql.postgres import sample_plan_is_supported

        assert not sample_plan_is_supported(SamplePlan(strategy=SamplingStrategy.STRATIFIED))
        assert sample_plan_is_supported(SamplePlan(strategy=SamplingStrategy.SYSTEMATIC))


class TestManifest:
    def test_the_connector_declares_what_it_can_push_down(self) -> None:
        capabilities = {c.name for c in PostgresConnector.manifest().capabilities}
        assert PushdownFeature.REGEX.value in capabilities
        assert PushdownFeature.SAMPLING.value in capabilities
        assert PushdownFeature.EXACT_SNAPSHOT.value in capabilities

    def test_the_description_states_the_two_guarantees(self) -> None:
        description = PostgresConnector.manifest().description
        assert "read-only" in description
        assert "timeout" in description
