"""The documentation is checked like code.

A document that names a module which does not exist is worse than one that says
nothing: a reader trusts it, goes looking, and concludes the product is broken.
Twenty-two such references were found in one pass over this corpus — modules the
roadmap named that the code had put somewhere else — so the check is now
permanent rather than an afternoon's tidy-up.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: Everything that makes a claim about the code and is meant to be believed.
#:
#: `qa/catalogue` is here on purpose: a test case naming a module that does not
#: exist is a case that will never run, and this guard has already caught two of
#: them. `qa/logs` is deliberately absent, and the distinction is the point —
#: a defect log's job is to name things that are broken or missing. It says
#: `prama.profile.from_rows` precisely *because* importing that fails. Holding
#: a defect report to "every module named here must exist" would forbid it from
#: reporting the defect it was written to report.
DOCUMENTS = sorted(
    [
        *ROOT.glob("docs/**/*.md"),
        *ROOT.glob("qa/catalogue/*.md"),
        ROOT / "README.md",
        ROOT / "QUICKSTART.md",
        ROOT / "CLAUDE.md",
    ]
)

#: A backticked repository path, e.g. `src/prama/pql/parser.py`.
PATH_REF = re.compile(r"`(src/prama/[\w/.]+|tests/[\w/.]+|schema/[\w.]+|scripts/[\w.]+)`")

#: A backticked dotted module, e.g. `prama.execute.transport`.
MODULE_REF = re.compile(r"`(prama\.[a-z_][\w.]*)`")

#: A relative markdown link to another document.
DOC_LINK = re.compile(r"\]\(([^)#:]+\.md)[^)]*\)")


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _resolves(reference: str) -> bool:
    """Whether a dotted name is a module, a package, or a name defined in one.

    Documents legitimately name classes — `prama.connect.spi.Verification` — and
    an earlier version of this check could only see modules, so naming a class
    failed as though it did not exist. Resolved by parsing rather than
    importing: a test that imported every module a document mentions would run
    arbitrary import side effects to check a piece of prose.
    """
    parts = reference.split(".")
    for candidate in (
        ROOT / "src" / Path(*parts).with_suffix(".py"),
        ROOT / "src" / Path(*parts),
    ):
        if candidate.exists():
            return True
    if len(parts) < 2:
        return False
    # The last segment may be a name defined in the module before it.
    *module_parts, attribute = parts
    module = ROOT / "src" / Path(*module_parts).with_suffix(".py")
    if not module.exists():
        return False
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name == attribute:
                return True
        elif isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == attribute for target in node.targets
            ):
                return True
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == attribute
        ):
            return True
    return False


@pytest.mark.parametrize("document", DOCUMENTS, ids=relative)
class TestEveryReferenceResolves:
    def test_referenced_paths_exist(self, document: Path) -> None:
        missing = [
            reference
            for reference in PATH_REF.findall(document.read_text(encoding="utf-8"))
            if not (ROOT / reference).exists()
        ]
        assert not missing, (
            f"{relative(document)} names {missing}, which do not exist. A reader "
            "trusts a path, goes looking, and concludes the product is broken."
        )

    def test_referenced_modules_exist(self, document: Path) -> None:
        missing = [
            reference
            for reference in MODULE_REF.findall(document.read_text(encoding="utf-8"))
            if not _resolves(reference)
        ]
        assert not missing, (
            f"{relative(document)} names {missing}, which do not exist. This is "
            "the drift that put `prama.pql.grammar` and `prama.stream` in the "
            "roadmap for two waves."
        )

    def test_links_to_other_documents_resolve(self, document: Path) -> None:
        broken = [
            link
            for link in DOC_LINK.findall(document.read_text(encoding="utf-8"))
            if not (document.parent / link).resolve().exists()
        ]
        assert not broken, f"{relative(document)} links to {broken}, which do not exist"


class TestEveryDesignDocumentSaysWhatIsBuilt:
    """The corpus describes an intention; the reader needs the state too.

    Without this, a design document reads as a description of the product — and
    for two years of this repository's life that was how the README read, while
    the product it described did not exist.
    """

    DESIGN = sorted(ROOT.glob("docs/[0-2][0-9]-*.md"))

    @pytest.mark.parametrize("document", DESIGN, ids=relative)
    def test_it_has_an_as_built_section(self, document: Path) -> None:
        text = document.read_text(encoding="utf-8")
        assert re.search(
            r"^#+\s*(as built|what ships today|what is built today|how to read this)",
            text,
            re.IGNORECASE | re.MULTILINE,
        ), (
            f"{relative(document)} describes a design and never says how much of "
            "it exists. Add an 'As built' section naming what is built, what is "
            "not, and what is built but has never met the real thing."
        )

    def test_there_are_design_documents_to_check(self) -> None:
        """So a glob that stops matching cannot make this suite vacuously green."""
        assert len(self.DESIGN) >= 20


class TestGeneratedDocumentsAreMarked:
    GENERATED = (
        "docs/operations/cli-reference.md",
        "docs/operations/configuration-reference.md",
    )

    @pytest.mark.parametrize("relative_path", GENERATED)
    def test_it_warns_against_editing_by_hand(self, relative_path: str) -> None:
        """An unmarked generated file invites an edit that the next regeneration
        silently discards."""
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "Generated by scripts/generate_docs.py" in text
        assert "Do not edit by hand" in text

    def test_they_are_current(self) -> None:
        """The same check the gate runs, so a stale reference fails here too."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "scripts/generate_docs.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
