"""Help by subject: every reading is real, and nothing a reader needs is orphaned.

A subject gathers the console guide, architecture, SDK, developer and design
pages on one thing a person wants to understand (prama/web/help_subjects.py).
These keep it honest: a subject cannot name a document that does not exist, a
subject cannot share a slug with a document, and a document a person reads to
use, run, script or extend Prama cannot be left out of every subject.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import html
from typing import Any

import pytest

from prama.web import help_catalog, help_subjects


def test_every_reading_is_a_help_entry() -> None:
    for subject in help_subjects.SUBJECTS.values():
        assert subject.readings, subject.slug
        for role, slug in subject.readings:
            assert role in help_subjects.ROLES, (subject.slug, role)
            assert slug in help_catalog.BY_SLUG, f"{subject.slug} reads {slug!r}, which is not help"


def test_subject_and_document_slugs_never_collide() -> None:
    shared = set(help_subjects.SUBJECTS) & set(help_catalog.BY_SLUG)
    assert not shared, f"one /help/<slug> would hide the other: {sorted(shared)}"


def test_every_subject_is_in_exactly_one_category() -> None:
    placed = [s for c in help_subjects.CATEGORIES for s in c.subjects]
    assert sorted(placed) == sorted(help_subjects.SUBJECTS), "a subject is unplaced or placed twice"


def test_nothing_a_reader_needs_is_orphaned() -> None:
    """Every console guide, and every architecture, developer, SDK, agent and operations
    document, is part of at least one subject."""
    read = {slug for s in help_subjects.SUBJECTS.values() for _, slug in s.readings}
    needed = [
        e
        for e in help_catalog.BY_SLUG.values()
        if e.origin == "guide" or e.path.startswith(help_subjects.MUST_BELONG)
    ]
    assert len(needed) > 40
    orphans = sorted(e.slug for e in needed if e.slug not in read)
    assert orphans == [], f"in no subject: {orphans}"


async def test_the_index_is_by_category_and_subject(stranger: Any) -> None:
    page = (await stranger.get("/help")).text
    for category in help_subjects.CATEGORIES:
        assert f'id="cat-{category.id}"' in page, category.id
    for slug in help_subjects.SUBJECTS:
        assert f'href="/help/{slug}"' in page, slug
    assert 'href="/help/library"' in page


@pytest.mark.parametrize("slug", sorted(help_subjects.SUBJECTS))
async def test_a_subject_page_opens_with_its_first_reading(stranger: Any, slug: str) -> None:
    reply = await stranger.get(f"/help/{slug}")
    assert reply.status_code == 200, reply.text[:300]
    subject = help_subjects.SUBJECTS[slug]
    first = help_catalog.BY_SLUG[subject.readings[0][1]]
    assert 'id="opening"' in reply.text and html.escape(first.title) in reply.text
    for _, other in subject.readings[1:]:
        assert f'href="/help/{other}"' in reply.text, (slug, other)


async def test_the_library_lists_every_document(stranger: Any) -> None:
    page = (await stranger.get("/help/library")).text
    for entry in help_catalog.BY_SLUG.values():
        assert f'href="/help/{entry.slug}"' in page, entry.slug


async def test_a_document_says_which_subject_it_belongs_to(stranger: Any) -> None:
    page = (await stranger.get("/help/architecture-semantic-layer")).text
    assert 'href="/help/the-estate"' in page  # the breadcrumb leads back to its subject
