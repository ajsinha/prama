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
        # affinity.py is the one place a raw thread is allowed outside this
        # list's original members: some native libraries are thread-*bound*
        # rather than merely thread-unsafe, and using them from another thread
        # deadlocks instead of failing. Keeping that in one reviewed primitive
        # is the point of the rule, not an exception to it.
        allowed_files = {
            "ids.py",
            "bounded_queue.py",
            "supervisor.py",
            "leases.py",
            "limits.py",
            "affinity.py",
        }
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
    #: Bare ``prompt`` was here and had to go. It is a *business* word in this
    #: codebase — ``RelationshipKind.prompt`` is the plain-language question a
    #: user picks a relationship from — so it matched modules with no model
    #: anywhere near them. A guard that cries wolf gets an exclusion list, and
    #: an exclusion list is how a real violation eventually gets waved through.
    #: The narrower forms below are the ones that actually mean a model call.
    MODEL_HINT = re.compile(
        r"\b(llm|openai|anthropic|bedrock|vertex|completion|chat_model"
        r"|system_prompt|user_prompt|prompt_template|build_prompt|render_prompt)\b",
        re.IGNORECASE,
    )

    @staticmethod
    def executable(source: str) -> str:
        """The code, with comments and docstrings removed.

        Both are prose about the rule rather than an instance of breaking it —
        this very class documents what a verdict is, and a scan that counts
        that as evidence teaches people to stop writing the explanation.
        """
        stripped = ast.parse(source)
        for node in ast.walk(stripped):
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                docstring = ast.get_docstring(node, clean=False)
                if docstring:
                    node.body = node.body[1:]
        return ast.unparse(stripped)

    #: The one module that names a model client in order to *forbid* it. The
    #: exemption is not a bare allowlist: the test below proves the mentions are
    #: confined to the forbidden tables — the module never imports one and never
    #: calls one. An allowlist without that proof is how a real violation
    #: eventually gets waved through.
    NAMES_MODELS_TO_BAN_THEM = "src/prama/classify/plugins.py"

    def test_the_exemption_is_a_ban_list_not_a_model_call(self) -> None:
        """``plugins.py`` refuses a validator that imports a model client, so
        it has to name them. This proves the mentions are only that."""
        from prama.classify import plugins

        source = (SRC / "classify" / "plugins.py").read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not self.MODEL_HINT.search(alias.name), alias.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not self.MODEL_HINT.search(node.module), node.module
        # And the names it does hold are the ones it refuses.
        banned = {**plugins.FORBIDDEN, **plugins.FORBIDDEN_PRAMA}
        assert any(self.MODEL_HINT.search(name) for name in banned)
        assert all("CON-007" in banned[n] for n in banned if self.MODEL_HINT.search(n))

    def test_no_module_both_calls_a_model_and_produces_a_verdict(self) -> None:
        offenders = []
        for path in python_files(SRC):
            if relative(path) == self.NAMES_MODELS_TO_BAN_THEM:
                continue
            code = self.executable(path.read_text())
            if self.MODEL_HINT.search(code) and self.FORBIDDEN.search(code):
                offenders.append(relative(path))
        assert not offenders, (
            "A module that talks to a model must not also produce a verdict "
            f"(CON-007, NFR-AI-002): {offenders}"
        )

    def test_the_guard_still_fires_on_a_module_that_would_break_the_rule(self) -> None:
        """The counterfactual. A control that cannot fail is worth nothing, and
        that goes double for an architecture guard which passes by default and
        would go on passing if its patterns stopped matching anything.
        """
        offender = self.executable(
            "\n".join(
                [
                    '"""A docstring mentioning a verdict, which must not count."""',
                    "def decide(row):",
                    "    answer = llm_client.completion(prompt_template.format(row=row))",
                    '    return {"verdict": "pass" if answer else "fail"}',
                ]
            )
        )
        assert self.MODEL_HINT.search(offender)
        assert self.FORBIDDEN.search(offender)

    def test_the_guard_ignores_prose_about_the_rule(self) -> None:
        """The false positive that forced the narrowing: a module using the
        business word ``prompt`` and describing verdicts in a docstring."""
        innocent = self.executable(
            "\n".join(
                [
                    '"""This module produces no verdict of any kind."""',
                    "def label(kind):",
                    "    return kind.prompt",
                ]
            )
        )
        assert not (self.MODEL_HINT.search(innocent) and self.FORBIDDEN.search(innocent))


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


class TestLanguageLayering:
    """The language must not depend on what compiles it."""

    def test_pql_does_not_import_the_ir_or_a_backend(self) -> None:
        # The direction is pql → ir → backend. Reversing it anywhere makes the
        # language unusable without the execution stack, and produced a
        # circular import the moment the linter reached for a lowered plan to
        # compare two controls.
        for path in (Path("src/prama/pql")).rglob("*.py"):
            imported = imported_modules(path)
            offending = {m for m in imported if m.startswith(("prama.ir", "prama.backend"))}
            assert not offending, f"{path} imports {sorted(offending)}"

    def test_the_ir_does_not_import_a_backend(self) -> None:
        for path in (Path("src/prama/ir")).rglob("*.py"):
            imported = imported_modules(path)
            offending = {m for m in imported if m.startswith("prama.backend")}
            assert not offending, f"{path} imports {sorted(offending)}"

    def test_no_engine_name_is_branched_on_outside_the_dialects(self) -> None:
        """Nothing asks which engine it is talking to; it asks the dialect.

        The rule is about *comparisons*, not about the string appearing at all.
        A default argument of "postgresql" names a choice; ``if dialect ==
        "sqlite"`` makes a decision, and that decision belongs in one file or
        it will be made differently in several.
        """
        comparisons = re.compile(
            r"""(==|!=|\bis\b|\bin\b)\s*\(?\s*["'](postgresql|duckdb|sqlite)["']"""
        )
        for path in Path("src/prama/backend").rglob("*.py"):
            if path.name == "dialect.py":
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                assert not comparisons.search(line), f"{path}:{number} branches on an engine"


class TestSingleMutationChannel:
    """`FR-IND-007`: nothing enters the estate except through a proposal.

    The rule is about authority rather than about imports, but it has an import
    shape, and the import shape is what can be enforced before there is any
    activation code to get wrong. A module that *infers* rules — Γ, the miners,
    the inducers, the importers — has no business touching the database or the
    executor. It produces candidates; somebody decides; the decision is what
    reaches the estate.

    Set now, while the answer is trivially yes, for the same reason as the
    no-model-verdicts tripwire: this rule is cheapest to hold when it has never
    once been broken.
    """

    #: Packages whose entire job is to propose.
    INFERRING = ("derive", "mine", "classify", "induce", "importers")

    #: What proposing must not reach. ``db`` is where the estate lives and
    #: ``execute`` is what makes a control run; a generator that can call
    #: either can install a control without anybody agreeing to it.
    FORBIDDEN_TARGETS = ("prama.db", "prama.execute", "prama.schedule")

    def test_no_inferring_package_can_reach_the_estate_or_the_executor(self) -> None:
        offenders: list[str] = []
        for package in self.INFERRING:
            root = SRC / package
            if not root.exists():
                continue
            for path in python_files(root):
                for module in imported_modules(path):
                    if any(module.startswith(target) for target in self.FORBIDDEN_TARGETS):
                        offenders.append(f"{relative(path)} imports {module}")
        assert not offenders, (
            "A module that infers rules must not be able to install or run them "
            f"(FR-IND-007): {offenders}"
        )

    def test_the_proposal_queue_does_not_depend_on_any_generator(self) -> None:
        """The seam runs one way. If the queue imported the generators, adding
        a new source of rules would mean editing the queue, and the thin
        adapter that keeps the two sides ignorant of each other would have no
        reason to exist.
        """
        offenders: list[str] = []
        for path in python_files(SRC / "propose"):
            if path.name == "adapt.py":
                continue  # the seam itself, and the only place that knows both
            for module in imported_modules(path):
                if any(module.startswith(f"prama.{p}") for p in self.INFERRING):
                    offenders.append(f"{relative(path)} imports {module}")
        assert not offenders, f"the queue should not know about generators: {offenders}"
