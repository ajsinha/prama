"""Architecture rules, enforced by the build rather than by memory.

Each test here corresponds to a hard rule in CLAUDE.md. They are cheap, they run
on every commit, and they fail the build — which is the only reliable way a
layering rule survives contact with a deadline.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "prama"


def python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def relative(path: Path) -> str:
    return str(path.relative_to(SRC.parent.parent))


class TestDatabaseConfinement:
    """CLAUDE.md rule 3: database code lives in exactly one package."""

    def test_only_prama_db_imports_sqlalchemy(self) -> None:
        offenders = []
        for path in python_files(SRC):
            if "db" in path.relative_to(SRC).parts[:1]:
                continue
            if any(m.split(".")[0] == "sqlalchemy" for m in imported_modules(path)):
                offenders.append(relative(path))
        assert not offenders, (
            "SQLAlchemy may only be imported inside src/prama/db. "
            f"Offenders: {offenders}. Use a repository and the unit of work."
        )

    def test_database_drivers_appear_only_where_they_belong(self) -> None:
        """Two places may hold a driver, for two unrelated reasons.

        ``prama.db`` talks to *Prama's own store*. ``prama.connect.sources``
        talks to *a customer's source*, which is the data plane and genuinely
        needs the driver. Anywhere else, a driver import means a layer has
        started doing persistence itself.
        """
        drivers = {"sqlite3", "aiosqlite", "asyncpg", "psycopg", "psycopg2", "pymysql", "duckdb"}
        allowed_roots = (("db",), ("connect", "sources"))
        offenders = []
        for path in python_files(SRC):
            parts = path.relative_to(SRC).parts
            if any(parts[: len(root)] == root for root in allowed_roots):
                continue
            if drivers & {m.split(".")[0] for m in imported_modules(path)}:
                offenders.append(relative(path))
        assert not offenders, (
            "database drivers belong in src/prama/db (Prama's own store) or "
            f"src/prama/connect/sources (a customer's source): {offenders}"
        )

    def test_a_connector_never_touches_pramas_own_store(self) -> None:
        """The constraint that makes the previous exemption safe.

        A connector reads a customer's data. If it could also reach Prama's
        store, the two would be one blast radius, and a bug in a third-party
        connector could corrupt the evidence ledger.
        """
        offenders = []
        for path in python_files(SRC / "connect"):
            imports = imported_modules(path)
            if any(m == "prama.db" or m.startswith("prama.db.") for m in imports):
                offenders.append(relative(path))
            if any(m.split(".")[0] == "sqlalchemy" for m in imports):
                offenders.append(relative(path))
        assert not offenders, (
            f"a connector must not reach Prama's own store or its ORM: {offenders}"
        )

    def test_core_does_not_depend_on_db(self) -> None:
        # prama.core is the foundation; a dependency on prama.db would make the
        # layering circular and the confinement rule unenforceable.
        offenders = [
            relative(path)
            for path in python_files(SRC / "core")
            if any(m.startswith("prama.db") for m in imported_modules(path))
        ]
        assert not offenders, f"prama.core must not import prama.db: {offenders}"

    def test_no_module_outside_dialects_branches_on_the_dialect_name(self) -> None:
        """CLAUDE.md rule 3: the dialect is chosen in configuration, once."""
        pattern = re.compile(r"==\s*[\"'](sqlite|postgres)[\"']|[\"'](sqlite|postgres)[\"']\s*==")
        allowed = {"dialects.py", "settings.py", "test_layering.py"}
        offenders = []
        for path in python_files(SRC):
            if path.name in allowed:
                continue
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if pattern.search(line):
                    offenders.append(f"{relative(path)}:{lineno}")
        assert not offenders, (
            f"Dialect branching belongs in prama/db/dialects.py alone. Offenders: {offenders}"
        )


class TestNoMigrations:
    """CLAUDE.md rule 2: there are no migrations."""

    def test_no_migration_tooling_is_present(self, repo_root: Path) -> None:
        forbidden = {"alembic", "yoyo", "flyway", "liquibase", "django.db.migrations"}
        offenders = []
        for path in python_files(SRC):
            if forbidden & {m.split(".")[0] for m in imported_modules(path)}:
                offenders.append(relative(path))
        assert not offenders, f"Prama has no migrations: {offenders}"
        assert not (repo_root / "alembic.ini").exists()
        assert not (repo_root / "migrations").exists()

    def test_ddl_is_never_emitted_from_orm_metadata(self) -> None:
        """``Base.metadata.create_all`` would make the ORM a second authority.

        Checked against the parsed AST, not the raw text, so that a docstring
        may name the forbidden call in order to explain why it is forbidden.
        """
        offenders = []
        for path in python_files(SRC):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in (
                    "create_all",
                    "drop_all",
                ):
                    offenders.append(relative(path))
                    break
        assert not offenders, (
            "schema/*.sql is the authority; metadata.create_all would silently "
            f"become a second one. Offenders: {offenders}"
        )


class TestConcurrencyHygiene:
    """CLAUDE.md doctrine: structured concurrency only."""

    def test_no_bare_threads_outside_the_concurrency_package(self) -> None:
        allowed_files = {"ids.py", "bounded_queue.py", "supervisor.py", "leases.py", "limits.py"}
        offenders = []
        for path in python_files(SRC):
            if path.name in allowed_files:
                continue
            source = path.read_text()
            if "threading.Thread(" in source or "ThreadPoolExecutor(" in source:
                offenders.append(relative(path))
        assert not offenders, (
            f"Use prama.core.concurrency.TaskSupervisor, not raw threads: {offenders}"
        )

    def test_no_fire_and_forget_tasks(self) -> None:
        """``asyncio.create_task`` without an owner loses the exception."""
        allowed_files = {"supervisor.py", "leases.py"}
        offenders = []
        for path in python_files(SRC):
            if path.name in allowed_files:
                continue
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                if "asyncio.create_task" in line and not line.lstrip().startswith("#"):
                    offenders.append(f"{relative(path)}:{lineno}")
        assert not offenders, f"Spawn through TaskSupervisor so failures surface: {offenders}"

    def test_no_unbounded_queues(self) -> None:
        offenders = []
        for path in python_files(SRC):
            if path.name == "bounded_queue.py":
                continue
            source = path.read_text()
            for construct in ("asyncio.Queue(", "queue.Queue(", "queue.SimpleQueue("):
                if construct in source:
                    offenders.append(f"{relative(path)}: {construct}")
        assert not offenders, f"Use prama.core.concurrency.BoundedQueue: {offenders}"


class TestModelVerdicts:
    """CLAUDE.md rule 6: AI authors, a deterministic engine adjudicates.

    Wave 1 ships no model integration at all, so this test is a tripwire set
    now, before there is anything to trip it. That is the point: the rule is
    cheapest to hold when it has never once been broken.
    """

    FORBIDDEN = re.compile(r"\b(verdict|pass_fail|is_violation|assert_outcome)\b", re.IGNORECASE)
    MODEL_HINT = re.compile(
        r"\b(llm|openai|anthropic|bedrock|vertex|completion|chat_model|prompt)\b", re.IGNORECASE
    )

    def test_no_module_both_calls_a_model_and_produces_a_verdict(self) -> None:
        offenders = []
        for path in python_files(SRC):
            source = path.read_text()
            code = "\n".join(
                line for line in source.splitlines() if not line.lstrip().startswith("#")
            )
            if self.MODEL_HINT.search(code) and self.FORBIDDEN.search(code):
                offenders.append(relative(path))
        assert not offenders, (
            "A module that talks to a model must not also produce a verdict "
            f"(CON-007, NFR-AI-002): {offenders}"
        )


class TestFileLength:
    """CLAUDE.md rule 4: no source file over 1500 lines of code."""

    def test_every_source_file_is_within_the_ceiling(self, repo_root: Path) -> None:
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "scripts/check_file_length.py"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


class TestDocumentation:
    def test_every_module_has_a_docstring_and_a_copyright_line(self) -> None:
        missing_doc, missing_copyright = [], []
        for path in python_files(SRC):
            source = path.read_text()
            tree = ast.parse(source, filename=str(path))
            if not ast.get_docstring(tree):
                missing_doc.append(relative(path))
            elif "Ashutosh Sinha" not in (ast.get_docstring(tree) or ""):
                missing_copyright.append(relative(path))
        assert not missing_doc, f"missing module docstring: {missing_doc}"
        assert not missing_copyright, f"missing copyright notice: {missing_copyright}"


@pytest.mark.parametrize("filename", ["LICENSE", "NOTICE", "CLAUDE.md"])
def test_governing_documents_are_present(repo_root: Path, filename: str) -> None:
    assert (repo_root / filename).is_file()
