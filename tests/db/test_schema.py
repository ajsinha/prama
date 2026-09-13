"""The schema contract: two files, one logical schema, no migrations.

These are the tests that make the "no migrations" decision safe. If they pass,
the two authoritative files describe the same schema, use only portable types,
and match both the ORM metadata and a freshly built database.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from prama.db import Database
from prama.db.models import Base, EvidenceBase
from prama.db.schema import SchemaLoader
from prama.db.schema.verifier import DriftKind

#: Physical types with identical semantics in PostgreSQL and SQLite. Anything
#: else means the two files describe subtly different databases — see the
#: PORTABLE TYPE SET header in schema/*.sql for the reasoning on each exclusion.
PORTABLE_TYPES = {"VARCHAR", "STRING", "TEXT", "INTEGER", "REAL", "FLOAT"}

#: VARCHAR *with* a width is portable; a bare VARCHAR is not, because SQLite
#: would accept it and PostgreSQL would treat it as unbounded.
PORTABLE_DECLARATION = re.compile(r"\bVARCHAR\s*\(\s*\d+\s*\)|\b(TEXT|INTEGER|REAL)\b")

NON_PORTABLE = re.compile(
    r"\b(BOOLEAN|TIMESTAMPTZ|TIMESTAMP|DATETIME|JSONB|JSON|SMALLINT|BIGINT|NUMERIC|"
    r"DECIMAL|CHAR\s*\(|SERIAL|BIGSERIAL|AUTOINCREMENT|UUID|BYTEA|BLOB|DOUBLE|"
    r"FLOAT|DATE|TIME)\b",
    re.IGNORECASE,
)


def all_tables() -> dict[str, Any]:
    """Every ORM table, across both declarative bases.

    Two bases, one pair of schema files. The split exists so no platform
    operation can create, truncate or cascade into the evidence ledger — but
    the files remain the single authority for what the database contains, so
    every agreement check below has to look at both. Checking only ``Base``
    would let an evidence table drift from its declaration unnoticed, which is
    the one table where that matters most.
    """
    merged = dict(Base.metadata.tables)
    merged.update(EvidenceBase.metadata.tables)
    return merged


def _body(path: Path) -> list[str]:
    """Statement lines with comments removed, for comparison."""
    return [line for line in path.read_text().splitlines() if not line.startswith("--")]


class TestParity:
    def test_both_files_exist(self, repo_root: Path) -> None:
        assert (repo_root / "schema" / "sqlite.sql").is_file()
        assert (repo_root / "schema" / "postgres.sql").is_file()

    def test_the_two_files_are_identical_apart_from_their_headers(self, repo_root: Path) -> None:
        # The strongest possible parity check, and the reason the restricted
        # type set is worth its cost: there is nothing to reconcile.
        assert _body(repo_root / "schema" / "sqlite.sql") == _body(
            repo_root / "schema" / "postgres.sql"
        )

    @pytest.mark.parametrize("dialect", ["sqlite", "postgres"])
    def test_only_portable_column_types_are_used(self, repo_root: Path, dialect: str) -> None:
        for line in _body(repo_root / "schema" / f"{dialect}.sql"):
            offending = NON_PORTABLE.search(line)
            assert offending is None, (
                f"{dialect}.sql uses a non-portable type {offending.group(0)!r}: {line.strip()}"
            )

    @pytest.mark.parametrize("dialect", ["sqlite", "postgres"])
    def test_every_varchar_declares_a_width(self, repo_root: Path, dialect: str) -> None:
        # A bare VARCHAR is unbounded in PostgreSQL and meaningless in SQLite:
        # the width is the whole reason VARCHAR earns its place over TEXT.
        bare = re.compile(r"\bVARCHAR\b(?!\s*\()", re.IGNORECASE)
        for line in _body(repo_root / "schema" / f"{dialect}.sql"):
            assert not bare.search(line), f"{dialect}.sql: {line.strip()}"

    @pytest.mark.parametrize("dialect", ["sqlite", "postgres"])
    def test_every_primary_key_column_declares_not_null(
        self, repo_root: Path, dialect: str
    ) -> None:
        # PostgreSQL implies it; SQLite does not for a non-INTEGER primary key
        # and would happily store a NULL id.
        for line in _body(repo_root / "schema" / f"{dialect}.sql"):
            if "PRIMARY KEY," in line:
                assert "NOT NULL" in line, f"{dialect}.sql: {line.strip()}"

    @pytest.mark.parametrize("dialect", ["sqlite", "postgres"])
    def test_every_statement_is_idempotent(self, repo_root: Path, dialect: str) -> None:
        schema = SchemaLoader().load(repo_root / "schema" / f"{dialect}.sql")
        for statement in schema.statements:
            if statement.upper().startswith("CREATE"):
                assert "IF NOT EXISTS" in statement.upper(), statement[:80]


class TestModelAgreement:
    """The ORM and the schema file must describe the same tables.

    Derive, never restate: the models are checked against the file rather than
    trusted to match it.
    """

    def test_every_orm_table_exists_in_the_schema_file(self, repo_root: Path) -> None:
        schema = SchemaLoader().load(repo_root / "schema" / "sqlite.sql")
        missing = set(all_tables()) - set(schema.table_names)
        assert not missing, f"declared in ORM but not in schema/sqlite.sql: {sorted(missing)}"

    def test_every_schema_table_has_an_orm_model(self, repo_root: Path) -> None:
        schema = SchemaLoader().load(repo_root / "schema" / "sqlite.sql")
        missing = set(schema.table_names) - set(all_tables())
        assert not missing, f"in schema/sqlite.sql but no ORM model: {sorted(missing)}"

    def test_columns_and_nullability_agree(self, repo_root: Path) -> None:
        schema = SchemaLoader().load(repo_root / "schema" / "sqlite.sql")
        problems: list[str] = []
        for name, table in all_tables().items():
            spec = schema.table(name)
            assert spec is not None
            declared = {c.name: c for c in spec.columns}
            for column in table.columns:
                found = declared.get(column.name)
                if found is None:
                    problems.append(f"{name}.{column.name}: in ORM, not in schema file")
                    continue
                if found.nullable != column.nullable:
                    problems.append(
                        f"{name}.{column.name}: schema nullable={found.nullable}, "
                        f"ORM nullable={column.nullable}"
                    )
            for column_name in declared:
                if column_name not in table.columns:
                    problems.append(f"{name}.{column_name}: in schema file, not in ORM")
        assert not problems, "\n".join(problems)

    def test_orm_uses_only_portable_physical_types(self) -> None:
        """Every ORM column must land on TEXT, INTEGER or REAL.

        The portable decorators (UtcDateTime, JsonText, BoolInt) are logical
        types over those three; anything else would reintroduce the engine
        difference the restricted type set exists to remove.
        """
        offenders = []
        for name, table in all_tables().items():
            for column in table.columns:
                physical = type(column.type).__name__.upper()
                if physical not in PORTABLE_TYPES:
                    impl = getattr(column.type, "impl", None)
                    physical = getattr(impl, "__name__", type(impl).__name__).upper()
                if physical not in PORTABLE_TYPES:
                    offenders.append(f"{name}.{column.name}: {physical}")
        assert not offenders, "\n".join(offenders)

    def test_orm_string_widths_match_the_schema_file(self, repo_root: Path) -> None:
        """Derive, never restate: a width declared twice will drift."""
        schema = SchemaLoader().load(repo_root / "schema" / "sqlite.sql")
        problems = []
        for name, table in all_tables().items():
            spec = schema.table(name)
            assert spec is not None
            for column in table.columns:
                declared = spec.column(column.name)
                if declared is None or not declared.type.upper().startswith("VARCHAR"):
                    continue
                width = int(re.search(r"\d+", declared.type).group())
                orm_width = getattr(column.type, "length", None)
                if orm_width is None:
                    impl = getattr(column.type, "impl", None)
                    orm_width = getattr(impl, "length", None)
                if orm_width != width:
                    problems.append(
                        f"{name}.{column.name}: schema VARCHAR({width}), ORM {orm_width}"
                    )
        assert not problems, "\n".join(problems)


class TestTheEvidenceLedgerIsSeparate:
    """One database, two declarative bases, and the split is the enforcement.

    The evidence ledger outlives the semantic layer it describes and is
    retained for years after it. Keeping it out of ``Base`` means nothing that
    operates on the platform's metadata — a create_all, a drop, a tenant
    cascade — can reach it by accident.
    """

    def test_the_two_metadatas_do_not_overlap(self) -> None:
        overlap = set(Base.metadata.tables) & set(EvidenceBase.metadata.tables)
        assert not overlap, f"a table declared under both bases: {sorted(overlap)}"

    def test_the_ledger_tables_are_under_evidence_base(self) -> None:
        assert {"ev_record", "ev_run", "ev_sample"} <= set(EvidenceBase.metadata.tables)
        assert not {"ev_record", "ev_run", "ev_sample"} & set(Base.metadata.tables)

    def test_no_evidence_table_references_a_platform_table(self) -> None:
        """No foreign key out of the ledger, deliberately.

        A referential link would let a tenant deletion take the evidence of
        what was checked along with it — exactly the record somebody would
        later need — and would stop a record outliving the declaration it
        refers to, which is the normal case over a seven-year retention.
        """
        for name, table in EvidenceBase.metadata.tables.items():
            for column in table.columns:
                assert not column.foreign_keys, f"{name}.{column.name} has a foreign key"

    def test_the_ledger_has_no_cascade_in_the_schema_file(self, repo_root: Path) -> None:
        """The counterfactual for the above, read from the authority itself.

        Scoped to the ``ev_*`` definitions rather than to everything after
        them: the platform tables that follow have foreign keys for good
        reasons, and a check that swept them in would fail for the wrong
        reason and get relaxed.
        """
        lines = _body(repo_root / "schema" / "sqlite.sql")
        inside = False
        checked = 0
        for line in lines:
            if line.startswith("CREATE TABLE IF NOT EXISTS ev_"):
                inside = True
            elif inside and line.startswith(");"):
                inside = False
            elif inside:
                checked += 1
                assert "REFERENCES" not in line.upper(), line.strip()
        assert checked > 20, "the ledger definitions were not found in the schema file"


class TestBootstrapAndVerify:
    def test_init_is_idempotent(self, sqlite_database: Database) -> None:
        first = sqlite_database.initialise()
        second = sqlite_database.initialise()
        assert first.digest == second.digest
        assert second.created is False

    def test_a_freshly_built_database_verifies_clean(self, sqlite_database: Database) -> None:
        report = sqlite_database.verify()
        assert report.ok, report.summary()
        assert report.drifts == ()

    def test_a_dropped_table_is_blocking_drift(self, sqlite_database: Database) -> None:
        from sqlalchemy import text

        with sqlite_database.sync_engine().begin() as conn:
            conn.execute(text("DROP TABLE setting"))
        report = sqlite_database.verify()
        assert not report.ok
        assert any(d.kind is DriftKind.MISSING_TABLE for d in report.blocking_drifts)

    def test_an_extra_table_is_reported_but_not_blocking(self, sqlite_database: Database) -> None:
        # An operator's own table is not Prama's business to refuse.
        from sqlalchemy import text

        with sqlite_database.sync_engine().begin() as conn:
            conn.execute(text("CREATE TABLE operator_scratch (x TEXT)"))
        report = sqlite_database.verify()
        assert report.ok
        assert any(d.kind is DriftKind.EXTRA_TABLE for d in report.drifts)

    def test_drift_raises_with_an_actionable_remedy(self, sqlite_database: Database) -> None:
        from sqlalchemy import text

        from prama.core.errors import SchemaDriftError

        with sqlite_database.sync_engine().begin() as conn:
            conn.execute(text("DROP TABLE audit_event"))
        with pytest.raises(SchemaDriftError) as caught:
            sqlite_database.verify().raise_if_blocking()
        assert "no migrations" in caught.value.remedy
        assert "prama db init" in caught.value.remedy

    def test_the_applied_digest_is_recorded(self, sqlite_database: Database) -> None:
        from sqlalchemy import text

        with sqlite_database.sync_engine().connect() as conn:
            row = conn.execute(text("SELECT file_digest, dialect FROM schema_state")).one()
        assert len(row[0]) == 64
        assert row[1] == "sqlite"

    def test_verification_survives_an_unbootstrapped_database(
        self, sqlite_config, tmp_path
    ) -> None:
        from prama.core.config import ConfigurationBuilder
        from prama.core.config.defaults import DEFAULTS

        config = (
            ConfigurationBuilder()
            .with_defaults(DEFAULTS)
            .with_mapping(
                {
                    "database": {
                        "dialect": "sqlite",
                        "sqlite": {"path": str(tmp_path / "empty.db")},
                        "schema_dir": sqlite_config.get_str("database.schema_dir"),
                    }
                },
                name="test",
            )
            .build()
        )
        report = Database.from_config(config).verify()
        assert not report.ok  # every table is missing, and it says so
        assert len(report.blocking_drifts) >= 9


class TestSqliteDoesNotInventColumns:
    """QA finding Q-08. A control on a column that does not exist reported
    **pass over the whole table** on SQLite.

    SQLite accepts a double-quoted identifier it cannot resolve as a *string
    literal*, for MySQL compatibility. So `"no_such_column" IS NOT NULL` is the
    constant string `'no_such_column'` — not null on every row — and the
    control passes 1,000 rows without looking at anything. The identical control
    is an `error` on DuckDB: two engines, opposite verdicts, and the wrong one
    is silent.

    A typo in a column name is the commonest way a control stops checking
    anything, and this made it the least visible failure in the product.
    """

    def prepared(self, database: Database) -> Any:
        """A table with two rows, through the engine Prama actually opens."""
        from sqlalchemy import text

        with database.sync_engine().begin() as conn:
            conn.execute(text("CREATE TABLE dqs_probe (a TEXT)"))
            conn.execute(text("INSERT INTO dqs_probe VALUES ('x'), ('y')"))
        return text

    def test_an_unknown_column_is_an_error_not_a_string(self, started_database: Database) -> None:
        from sqlalchemy.exc import OperationalError

        text = self.prepared(started_database)
        with (
            started_database.sync_engine().connect() as conn,
            pytest.raises(OperationalError, match="no such column"),
        ):
            conn.execute(text('SELECT COUNT(*) FROM dqs_probe WHERE "no_such_column" IS NOT NULL'))

    def test_a_real_column_still_works(self, started_database: Database) -> None:
        """The counterfactual. Turning the fallback off must not break quoting
        of columns that do exist — which is every query Prama emits."""
        text = self.prepared(started_database)
        with started_database.sync_engine().connect() as conn:
            found = conn.execute(
                text('SELECT COUNT(*) FROM dqs_probe WHERE "a" IS NOT NULL')
            ).scalar()
        assert found == 2

    def test_a_genuine_string_literal_still_works(self, started_database: Database) -> None:
        """Single quotes are how you mean a string, and always were."""
        text = self.prepared(started_database)
        with started_database.sync_engine().connect() as conn:
            found = conn.execute(text("SELECT COUNT(*) FROM dqs_probe WHERE a = 'x'")).scalar()
        assert found == 1
