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
                "metadata",
                "Metadata and business context",
                "Your own fields, the business meaning, and rules that grow from metadata.",
                "bi-tags",
            ),
            _g(
                "queue",
                "Discussion and your queue",
                "Comments with @mentions, and everything waiting on you in one place.",
                "bi-inbox",
            ),
            _g(
                "glossary",
                "Business glossary",
                "Terms, their meanings, what they name; imported from Alation or Collibra.",
                "bi-book-half",
            ),
            _g(
                "delegates",
                "DQ delegates",
                "Your own Python checks, named from PQL and judged by Prama.",
                "bi-braces",
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
        "Python SDK",
        (
            _d(
                "sdk",
                "The Python SDK",
                "Everything Prama does, from Python, against your running server.",
                "docs/sdk/README.md",
                "bi-filetype-py",
            ),
            _d(
                "sdk-controls",
                "SDK: controls and runs",
                "Author, derive, accept and run controls; PQL tooling.",
                "docs/sdk/controls.md",
                "bi-shield-check",
            ),
            _d(
                "sdk-evidence",
                "SDK: evidence and assurance",
                "The ledger, incidents, scorecards, attestations, reports.",
                "docs/sdk/evidence.md",
                "bi-link-45deg",
            ),
            _d(
                "sdk-reconciliation",
                "SDK: reconciliation",
                "Reconciliations, the break workbench, the certificate.",
                "docs/sdk/reconciliation.md",
                "bi-arrow-left-right",
            ),
            _d(
                "sdk-contracts",
                "SDK: data contracts",
                "Check, diff, import and export contracts.",
                "docs/sdk/contracts.md",
                "bi-file-earmark-check",
            ),
            _d(
                "sdk-usage",
                "SDK: usage",
                "Query history in, priorities out.",
                "docs/sdk/usage.md",
                "bi-graph-up",
            ),
            _d(
                "sdk-administration",
                "SDK: administration",
                "People, roles, keys, models, agents, config, audit.",
                "docs/sdk/administration.md",
                "bi-people",
            ),
            _d(
                "sdk-knowledge",
                "SDK: knowledge and code",
                "Lineage, code, glossary, metadata, delegates, packs, connectors.",
                "docs/sdk/knowledge-and-code.md",
                "bi-bezier2",
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
                "docs/reference/glossary.md",
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
                "docs/corpus/03-business-semantic-layer.md",
                "bi-diagram-3",
            ),
            _d(
                "pql",
                "The rule language (PQL)",
                "How a control is written, checked and compiled.",
                "docs/corpus/07-rule-language-spec.md",
                "bi-code-square",
            ),
            _d(
                "architecture",
                "Architecture",
                "Components and how they fit.",
                "docs/corpus/06-architecture.md",
                "bi-building",
            ),
            _d(
                "security",
                "Security, governance and compliance",
                "Identity, scopes, evidence and audit.",
                "docs/corpus/13-security-governance-compliance.md",
                "bi-shield-lock",
            ),
            _d(
                "data-model",
                "Data model and APIs",
                "Tables and endpoints.",
                "docs/corpus/14-data-model-and-apis.md",
                "bi-database",
            ),
            _d(
                "banking-pack",
                "Banking domain pack",
                "What the banking pack ships, and what it does not claim.",
                "docs/corpus/12-banking-domain-pack.md",
                "bi-bank",
            ),
            _d(
                "roadmap",
                "Implementation roadmap",
                "What is built and what is next.",
                "docs/corpus/19-implementation-roadmap.md",
                "bi-signpost-split",
            ),
            _d(
                "competitive-analysis",
                "Competitive analysis, vendor by vendor",
                "Who Prama meets in a deal, where each is better today, and how Prama wins.",
                "docs/corpus/20-competitive-analysis.md",
                "bi-bar-chart-steps",
            ),
            _d(
                "roadmap-intelligence",
                "Intelligence and lineage roadmap",
                "LLM gateway, lineage workbench, code-to-lineage, steward agents.",
                "docs/corpus/23-intelligence-and-lineage-roadmap.md",
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

#: Documents link each other by relative file path (``../corpus/07-rule-language-spec.md``)
#: and embed images the same way (``../assets/diagrams/x.svg``). Both are resolved
#: against the directory of the document being rendered — by path, not by bare
#: file name, because four documents are called ``README.md`` — and rewritten to
#: the help page for the target where one exists, and to ``/help/assets/...`` for
#: an image under ``docs/assets``. Reading a document in the console must not
#: strand the reader on a link to a file the browser cannot open.
_BY_PATH: dict[Path, str] = {e.source().resolve(): e.slug for e in BY_SLUG.values()}
_HREF = re.compile(r'href="(?!/|[a-z]+:)([^"#]+\.md)(#[^"]*)?"')
_SRC = re.compile(r'src="(?!/|[a-z]+:)([^"]+)"')


def _relink(html: str, base: Path) -> str:
    """``html`` rendered from a document in directory ``base``, with its links made live."""

    def page(match: re.Match[str]) -> str:
        slug = _BY_PATH.get((base / match.group(1)).resolve())
        if slug is None:
            return match.group(0)
        return f'href="/help/{slug}{match.group(2) or ""}"'

    def image(match: re.Match[str]) -> str:
        target = (base / match.group(1)).resolve()
        if not target.is_relative_to(ASSETS_DIR.resolve()):
            return match.group(0)
        return f'src="/help/assets/{target.relative_to(ASSETS_DIR.resolve()).as_posix()}"'

    return _SRC.sub(image, _HREF.sub(page, html))


def asset(name: str) -> Path | None:
    """The image ``name`` under ``docs/assets`` (subfolders allowed), or ``None``.

    A closed set by construction: the path must resolve inside the assets
    directory, no segment may be hidden, and only image types are served.
    """
    if "\\" in name or any(part.startswith(".") for part in name.split("/")):
        return None
    root = ASSETS_DIR.resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path


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
    html = _relink(md.convert(path.read_text(encoding="utf-8")), path.parent)
    rendered = Rendered(html=html, toc=getattr(md, "toc", ""))
    with _lock:
        _cache[path] = (mtime, rendered)
    return rendered
