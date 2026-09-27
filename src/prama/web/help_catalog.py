"""The help centre's catalogue: what exists, where its text lives, and how it renders.

After Maya's ``help_catalog.py`` and ``guide_render.py``, with one difference
that matters here: **the help centre restates nothing.** Every entry points at a
Markdown file that is already the authority — a console guide shipped inside
the package, or a document of the design corpus in the repository's ``docs/``.
A help page written separately from the document it summarises is a second
copy, and a second copy drifts in the flattering direction.

Documents are read at request time and cached by modification time, so
editing a guide is visible on the next page load without a restart.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import re
import threading
from pathlib import Path

import markdown

#: Console guides, shipped inside the package so an installed wheel has them.
GUIDES_DIR = Path(__file__).parent / "guides"

#: The repository root, when running from a checkout. The design corpus lives
#: in ``docs/`` there and is not part of the wheel; entries under it say so on
#: the page rather than 404ing.
REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclasses.dataclass(frozen=True, slots=True)
class HelpEntry:
    """One document in the help centre."""

    slug: str
    title: str
    summary: str
    #: ``guide`` (in the package) or ``doc`` (relative to the repository root).
    origin: str
    path: str
    icon: str = "bi-file-earmark-text"

    def source(self) -> Path:
        base = GUIDES_DIR if self.origin == "guide" else REPO_ROOT
        return base / self.path


@dataclasses.dataclass(frozen=True, slots=True)
class HelpSection:
    title: str
    entries: tuple[HelpEntry, ...]


def _g(slug: str, title: str, summary: str, icon: str) -> HelpEntry:
    return HelpEntry(slug, title, summary, "guide", f"{slug}.md", icon)


def _d(slug: str, title: str, summary: str, path: str, icon: str = "bi-journal-text") -> HelpEntry:
    return HelpEntry(slug, title, summary, "doc", path, icon)


SECTIONS: tuple[HelpSection, ...] = (
    HelpSection(
        "Using the console",
        (
            _g(
                "console-tour",
                "A tour of the console",
                "Each area, in the order the work runs.",
                "bi-compass",
            ),
            _g(
                "accounts",
                "Accounts, roles and sign-in",
                "Who can do what, and how an administrator manages people.",
                "bi-people",
            ),
            _g(
                "api-keys",
                "API keys",
                "Minting, scoping, expiring and revoking a key for a program.",
                "bi-key",
            ),
            _g(
                "agents",
                "Steward agents",
                "Persistent AI agents that read, think through the gateway, and propose.",
                "bi-robot",
            ),
            _g(
                "code",
                "Application code",
                "Send a ZIP or a git location; Prama reads its lineage and never runs it.",
                "bi-file-earmark-code",
            ),
            _g(
                "lineage",
                "Lineage",
                "Scan SQL, see what feeds what, and what a defect reaches.",
                "bi-bezier2",
            ),
            _g(
                "models",
                "Models",
                "Local and remote LLMs, profiles, and the call ledger.",
                "bi-cpu",
            ),
            _g(
                "themes",
                "Themes and display",
                "Every theme, row density, and why colours are derived.",
                "bi-palette",
            ),
        ),
    ),
    HelpSection(
        "Getting started",
        (
            _d(
                "quickstart",
                "Quickstart",
                "From a fresh clone to a running console.",
                "QUICKSTART.md",
                "bi-rocket-takeoff",
            ),
            _d(
                "glossary",
                "Glossary",
                "Every term Prama uses, defined once.",
                "docs/glossary.md",
                "bi-book",
            ),
            _d(
                "corpus",
                "The design corpus",
                "What each design document covers.",
                "docs/README.md",
                "bi-collection",
            ),
        ),
    ),
    HelpSection(
        "Operating Prama",
        (
            _d(
                "runbook",
                "Runbook",
                "Day-two operations.",
                "docs/operations/runbook.md",
                "bi-tools",
            ),
            _d(
                "troubleshooting",
                "Troubleshooting",
                "Symptoms, causes and remedies.",
                "docs/operations/troubleshooting.md",
                "bi-bandaid",
            ),
            _d(
                "cli",
                "CLI reference",
                "Every command.",
                "docs/operations/cli-reference.md",
                "bi-terminal",
            ),
            _d(
                "configuration",
                "Configuration reference",
                "Every setting and its default.",
                "docs/operations/configuration-reference.md",
                "bi-sliders",
            ),
        ),
    ),
    HelpSection(
        "Concepts and design",
        (
            _d(
                "semantic-layer",
                "The business semantic layer",
                "The conceptual heart: declarations a business owner makes.",
                "docs/03-business-semantic-layer.md",
                "bi-diagram-3",
            ),
            _d(
                "pql",
                "The rule language (PQL)",
                "How a control is written, checked and compiled.",
                "docs/07-rule-language-spec.md",
                "bi-code-square",
            ),
            _d(
                "architecture",
                "Architecture",
                "Components and how they fit.",
                "docs/06-architecture.md",
                "bi-building",
            ),
            _d(
                "security",
                "Security, governance and compliance",
                "Identity, scopes, evidence and audit.",
                "docs/13-security-governance-compliance.md",
                "bi-shield-lock",
            ),
            _d(
                "data-model",
                "Data model and APIs",
                "Tables and endpoints.",
                "docs/14-data-model-and-apis.md",
                "bi-database",
            ),
            _d(
                "banking-pack",
                "Banking domain pack",
                "What the banking pack ships, and what it does not claim.",
                "docs/12-banking-domain-pack.md",
                "bi-bank",
            ),
            _d(
                "roadmap",
                "Implementation roadmap",
                "What is built and what is next.",
                "docs/19-implementation-roadmap.md",
                "bi-signpost-split",
            ),
            _d(
                "roadmap-intelligence",
                "Intelligence and lineage roadmap",
                "LLM gateway, lineage workbench, code-to-lineage, steward agents.",
                "docs/23-intelligence-and-lineage-roadmap.md",
                "bi-stars",
            ),
        ),
    ),
)

#: The corpus's image directory, served read-only at ``/help/assets``.
ASSETS_DIR = REPO_ROOT / "docs" / "assets"

BY_SLUG: dict[str, HelpEntry] = {e.slug: e for s in SECTIONS for e in s.entries}


@dataclasses.dataclass(frozen=True, slots=True)
class Rendered:
    html: str
    toc: str


_cache: dict[Path, tuple[float, Rendered]] = {}
_lock = threading.Lock()

#: Links between corpus documents are written as relative file paths
#: (``07-rule-language-spec.md``). Rewritten to the help page for the same
#: document where one exists, so reading a document in the console does not
#: strand the reader on a link to a file the browser cannot open.
_BY_FILENAME: dict[str, str] = {Path(e.path).name: e.slug for e in BY_SLUG.values()}
_LINK = re.compile(r'href="(?:\./|\.\./)*(?:docs/)?([\w.-]+\.md)(#[\w-]*)?"')


def _relink(html: str) -> str:
    def swap(match: re.Match[str]) -> str:
        slug = _BY_FILENAME.get(match.group(1))
        if slug is None:
            return match.group(0)
        return f'href="/help/{slug}{match.group(2) or ""}"'

    # The corpus's own images (the lockup, the seal) are served beside it.
    return _LINK.sub(swap, html).replace('src="assets/', 'src="/help/assets/')


def render_entry(entry: HelpEntry) -> Rendered | None:
    """The entry as HTML, or ``None`` when its source is not on this host."""
    path = entry.source()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    with _lock:
        cached = _cache.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists"])
    html = _relink(md.convert(path.read_text(encoding="utf-8")))
    rendered = Rendered(html=html, toc=getattr(md, "toc", ""))
    with _lock:
        _cache[path] = (mtime, rendered)
    return rendered
