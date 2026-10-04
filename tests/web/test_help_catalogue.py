"""The help centre and the documentation are one body of text, not two.

Every document under ``docs/`` has a card, derived from the document; every
link a rendered page makes to another document lands on a help page rather
than on a raw ``.md`` file the browser cannot open; every image resolves; and
every console guide sends its reader on to the documents behind it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from prama.web import help_catalog

ROOT = help_catalog.REPO_ROOT
DOCS = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "docs").rglob("*.md"))
ENTRIES = [e for s in help_catalog.SECTIONS for e in s.entries]
#: A relative link left in rendered HTML: one _relink could not make live.
_DEAD_DOC = re.compile(r'href="(?!/|[a-z]+:|#)([^"#]+\.md)')
_IMAGE = re.compile(r'src="([^"]+)"')


def test_there_are_documents_to_check() -> None:
    """So a moved docs folder cannot make this suite vacuously green."""
    assert len(DOCS) > 40


@pytest.mark.parametrize("document", DOCS)
def test_every_document_has_a_card(document: str) -> None:
    assert document in {e.path for e in ENTRIES}, f"{document} is not in the help centre"


def test_slugs_are_unique() -> None:
    """Two entries with one slug: the second silently replaced the first. It did, once:
    the console's "Business glossary" guide opened the glossary of terms instead."""
    slugs = [e.slug for e in ENTRIES]
    assert len(slugs) == len(set(slugs))
    assert help_catalog.BY_SLUG["glossary"].origin == "guide"


def test_cards_say_something() -> None:
    for entry in ENTRIES:
        assert entry.title and entry.summary, entry.path
        assert not entry.summary.lower().startswith(("copyright", "proprietary")), entry.path


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e.slug)
def test_rendered_links_and_images_resolve(entry: help_catalog.HelpEntry) -> None:
    rendered = help_catalog.render_entry(entry)
    assert rendered is not None, entry.path
    base = entry.source().parent
    for href in _DEAD_DOC.findall(rendered.html):
        target = (base / href).resolve()
        # A document outside docs/ (a tool's guide, a case study) is a file in
        # the repository, not a help page; one inside docs/ must have become one.
        assert not target.is_relative_to((ROOT / "docs").resolve()), (
            f"{entry.path} links {href}, which help did not make live"
        )
    for src in _IMAGE.findall(rendered.html):
        if src.startswith("/help/assets/"):
            assert help_catalog.asset(src.removeprefix("/help/assets/")), (entry.path, src)
        elif src.startswith("/help/images/"):
            name = src.removeprefix("/help/images/")
            assert help_catalog.asset(name, help_catalog.DOCS_DIR), (entry.path, src)
        elif not src.startswith(("http", "data:")):
            pytest.fail(f"{entry.path} embeds {src}, which the help centre cannot serve")


@pytest.mark.parametrize("entry", [e for e in ENTRIES if e.origin == "guide"], ids=lambda e: e.slug)
def test_every_console_guide_links_into_the_documentation(entry: help_catalog.HelpEntry) -> None:
    rendered = help_catalog.render_entry(entry)
    assert rendered is not None
    linked = set(re.findall(r'href="/help/([\w-]+)', rendered.html)) - {entry.slug}
    documents = {s for s in linked if help_catalog.BY_SLUG.get(s, entry).origin == "doc"}
    assert documents, f"the {entry.slug} guide leads nowhere further"


def test_the_assets_route_refuses_to_leave_its_directory() -> None:
    for bad in ("../../LICENSE", "diagrams/../../../LICENSE", ".hidden.svg", "a/.b/c.svg"):
        assert help_catalog.asset(bad) is None, bad
    assert (
        help_catalog.asset("prama-mark.svg")
        == (help_catalog.ASSETS_DIR / "prama-mark.svg").resolve()
    )
    assert isinstance(help_catalog.asset("prama-mark.svg"), Path)
