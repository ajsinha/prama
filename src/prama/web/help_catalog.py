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


#: Documents that keep the slug, card text and icon they had before the
#: catalogue was derived: their URLs are linked from elsewhere, and their card
#: text was chosen. Every other document under ``docs/`` gets a card derived
#: from the document itself (title from its heading, summary from its first
#: paragraph), so adding a document adds a card and the two cannot disagree.
CURATED: dict[str, tuple[str, str, str]] = {
    "QUICKSTART.md": (
        "quickstart",
        "From a fresh clone to a running console.",
        "bi-rocket-takeoff",
    ),
    "docs/README.md": ("corpus", "Every document, and who should read which.", "bi-collection"),
    "docs/reference/glossary.md": ("terms", "Every term Prama uses, defined once.", "bi-book"),
    "docs/architecture/README.md": (
        "architecture",
        "Every component and how they fit.",
        "bi-building",
    ),
    "docs/sdk/README.md": (
        "sdk",
        "Everything Prama does, from Python, against your running server.",
        "bi-filetype-py",
    ),
    "docs/sdk/controls.md": (
        "sdk-controls",
        "Author, derive, accept and run controls; PQL tooling.",
        "bi-shield-check",
    ),
    "docs/sdk/evidence.md": (
        "sdk-evidence",
        "The ledger, incidents, scorecards, attestations, reports.",
        "bi-link-45deg",
    ),
    "docs/sdk/reconciliation.md": (
        "sdk-reconciliation",
        "Reconciliations, the break workbench, the certificate.",
        "bi-arrow-left-right",
    ),
    "docs/sdk/contracts.md": (
        "sdk-contracts",
        "Check, diff, import and export contracts.",
        "bi-file-earmark-check",
    ),
    "docs/sdk/usage.md": ("sdk-usage", "Query history in, priorities out.", "bi-graph-up"),
    "docs/sdk/administration.md": (
        "sdk-administration",
        "People, roles, keys, models, agents, config, audit.",
        "bi-people",
    ),
    "docs/sdk/knowledge-and-code.md": (
        "sdk-knowledge",
        "Lineage, code, glossary, metadata, delegates, packs, connectors.",
        "bi-bezier2",
    ),
    "docs/operations/runbook.md": ("runbook", "Day-two operations.", "bi-tools"),
    "docs/operations/troubleshooting.md": (
        "troubleshooting",
        "Symptoms, causes and remedies.",
        "bi-bandaid",
    ),
    "docs/operations/cli-reference.md": ("cli", "Every command.", "bi-terminal"),
    "docs/operations/configuration-reference.md": (
        "configuration",
        "Every setting and its default.",
        "bi-sliders",
    ),
    "docs/corpus/03-business-semantic-layer.md": (
        "semantic-layer",
        "The conceptual heart: declarations a business owner makes.",
        "bi-diagram-3",
    ),
    "docs/corpus/07-rule-language-spec.md": (
        "pql",
        "How a control is written, checked and compiled.",
        "bi-code-square",
    ),
    "docs/corpus/06-architecture.md": (
        "reference-architecture",
        "The design intent: planes, services, topologies.",
        "bi-diagram-2",
    ),
    "docs/corpus/13-security-governance-compliance.md": (
        "security",
        "Identity, scopes, evidence and audit.",
        "bi-shield-lock",
    ),
    "docs/corpus/14-data-model-and-apis.md": ("data-model", "Tables and endpoints.", "bi-database"),
    "docs/corpus/12-banking-domain-pack.md": (
        "banking-pack",
        "What the banking pack ships, and what it does not claim.",
        "bi-bank",
    ),
    "docs/corpus/19-implementation-roadmap.md": (
        "roadmap",
        "What is built and what is next.",
        "bi-signpost-split",
    ),
    "docs/corpus/20-competitive-analysis.md": (
        "competitive-analysis",
        "Who Prama meets in a deal, where each is better today, and how Prama wins.",
        "bi-bar-chart-steps",
    ),
    "docs/corpus/23-intelligence-and-lineage-roadmap.md": (
        "roadmap-intelligence",
        "LLM gateway, lineage workbench, code-to-lineage, steward agents.",
        "bi-stars",
    ),
}

#: Sections of documents, in reading order: a title, the folders it gathers,
#: and the icon a derived card gets.
FOLDERS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("How Prama fits together", ("docs/architecture",), "bi-building"),
    ("Developer guides", ("docs/developer",), "bi-tools"),
    ("Python SDK", ("docs/sdk",), "bi-filetype-py"),
    ("Agents beside the data", ("docs/agent",), "bi-hdd-network"),
    ("Operations", ("docs/operations",), "bi-gear"),
    ("Design corpus", ("docs/corpus",), "bi-journal-text"),
    ("Design notes", ("docs/design",), "bi-pencil-square"),
    ("Reference", ("docs/reference",), "bi-bookmark"),
    ("Publications and reviews", ("docs/publications", "docs/reviews"), "bi-newspaper"),
)

_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_SAME_FOLDER_LINK = re.compile(r"\]\((?:\./)?([\w.-]+\.md)[#)]")


def _plain(text: str) -> str:
    """Markdown inline syntax removed: links to their text, no emphasis or code marks."""
    text = _MD_LINK.sub(r"\1", text)
    return re.sub(r"[*_`]", "", text).strip()


#: A paragraph that is a document's metadata rather than its subject:
#: "Status: proposal.", "Requirements: FR-CON.", "Written 2026-09-27."
_METADATA = re.compile(r"^(?:[A-Z][\w -]{0,24}:|Written \d|Copyright|Ashutosh Sinha ·)")


#: The heading of an index column that says what each listed document is for.
_DESCRIBES = re.compile(r"What it (?:answers|covers|is)|When you need it")


def _index_summaries() -> dict[Path, str]:
    """What each document answers, as the index tables say it.

    ``docs/README.md`` and each folder's README list their documents in tables;
    one whose last column is headed "What it answers" (or covers, or is, or
    "When you need it") says what each document is for. That sentence is the
    card's summary: written once, in the index, and read from there.
    """
    found: dict[Path, str] = {}
    docs = REPO_ROOT / "docs"
    readmes = [docs / "README.md", *sorted(docs.rglob("*/README.md"))]
    for readme in (r for r in readmes if r.is_file()):
        describing = False  # inside a table whose last column describes its documents
        previous = ""
        for row in readme.read_text(encoding="utf-8").splitlines():
            if not row.startswith("|"):
                describing, previous = False, row
                continue
            if re.fullmatch(r"\|[-|: ]+\|", row.strip()):  # the rule under a header
                last = previous.strip().strip("|").split("|")[-1].strip()
                describing = bool(_DESCRIBES.match(last))
                continue
            previous = row
            if not describing:
                continue
            target = re.search(r"\]\(([^)#:]+\.md)", row)
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            if target and len(cells) >= 2 and cells[-1] and target.group(1) not in cells[-1]:
                path = (readme.parent / target.group(1)).resolve()
                found.setdefault(path, _plain(cells[-1]))
    return found


def _derive(path: Path) -> tuple[str, str]:
    """A document's title (its first heading) and summary.

    The summary is what the index says the document answers, else the first
    sentence of its first paragraph of prose.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    title = next((_plain(ln[2:]) for ln in lines if ln.startswith("# ")), path.stem)
    paragraph: list[str] = []
    seen_title = False
    for line in lines:
        if line.startswith("# "):
            seen_title = True
            continue
        stripped = line.strip()
        prose = stripped and not stripped.startswith(
            ("<", "!", ">", "#", "|", "```", "---", "*Copyright", "*Generated", "- ", "* ")
        )
        if seen_title and prose and not (not paragraph and _METADATA.match(_plain(stripped))):
            paragraph.append(stripped)
        elif paragraph:
            break
    indexed = _INDEX.get(path.resolve())
    text = indexed or _plain(" ".join(paragraph))
    sentence = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    if len(sentence) > 150:
        sentence = sentence[:147].rsplit(" ", 1)[0] + "…"
    return title, sentence


_INDEX = _index_summaries()


def _slug(relative: str) -> str:
    """``docs/developer/connectors.md`` -> ``developer-connectors``; a README is its folder."""
    parts = Path(relative).with_suffix("").parts[1:]  # drop "docs"
    if parts[-1] == "README":
        parts = parts[:-1]
    if parts[0] == "corpus":  # "corpus-03-business..." -> "business..."
        parts = (re.sub(r"^\d\d-", "", parts[-1]),)
    return "-".join(p.lower() for p in parts)


def _ordered(folder: Path) -> list[Path]:
    """The folder's README first, then documents in the order it links them, then the rest."""
    files = sorted(folder.rglob("*.md"))
    readme = folder / "README.md"
    linked: list[Path] = []
    if readme.is_file():
        for name in _SAME_FOLDER_LINK.findall(readme.read_text(encoding="utf-8")):
            candidate = folder / name
            if candidate in files and candidate not in linked and candidate != readme:
                linked.append(candidate)
    head = [readme] if readme in files else []
    return head + linked + [f for f in files if f not in head and f not in linked]


def _doc(relative: str, icon: str) -> HelpEntry:
    if relative in CURATED:
        slug, summary, icon = CURATED[relative]
        title, _ = _derive(REPO_ROOT / relative) if (REPO_ROOT / relative).is_file() else (slug, "")
        return HelpEntry(slug, title, summary, "doc", relative, icon)
    title, summary = _derive(REPO_ROOT / relative)
    return HelpEntry(_slug(relative), title, summary, "doc", relative, icon)


def _sections() -> tuple[HelpSection, ...]:
    start = HelpSection(
        "Getting started",
        (
            _g(
                "console-tour",
                "A tour of the console",
                "Each area, in the order the work runs.",
                "bi-compass",
            ),
            _doc("QUICKSTART.md", ""),
            _doc("docs/README.md", ""),
            _doc("docs/reference/glossary.md", ""),
        ),
    )
    console = HelpSection(
        "Using the console",
        (
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
    )
    taken = {e.path for e in start.entries}
    sections = [start, console]
    for title, folders, icon in FOLDERS:
        entries = tuple(
            _doc(path.relative_to(REPO_ROOT).as_posix(), icon)
            for folder in folders
            for path in _ordered(REPO_ROOT / folder)
            if path.relative_to(REPO_ROOT).as_posix() not in taken
        )
        if entries:  # an installed wheel has no docs/; its help is the guides
            sections.append(HelpSection(title, entries))
    return tuple(sections)


SECTIONS: tuple[HelpSection, ...] = _sections()

#: The corpus's image directory, served read-only at ``/help/assets``.
ASSETS_DIR = REPO_ROOT / "docs" / "assets"
#: Images a document keeps beside itself (the article's figures), served at ``/help/images``.
DOCS_DIR = REPO_ROOT / "docs"

BY_SLUG: dict[str, HelpEntry] = {}
for _entry in (e for s in SECTIONS for e in s.entries):
    if _entry.slug in BY_SLUG:  # one would silently shadow the other
        raise RuntimeError(f"two help entries share the slug {_entry.slug!r}")
    BY_SLUG[_entry.slug] = _entry


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
        for prefix, root in (("assets", ASSETS_DIR), ("images", DOCS_DIR)):
            if target.is_relative_to(root.resolve()):
                return f'src="/help/{prefix}/{target.relative_to(root.resolve()).as_posix()}"'
        return match.group(0)

    return _SRC.sub(image, _HREF.sub(page, html))


def asset(name: str, root: Path | None = None) -> Path | None:
    """The file ``name`` under ``root`` (``docs/assets`` by default), or ``None``.

    A closed set by construction: the path must resolve inside ``root`` and no
    segment may be hidden. The route serving it also refuses anything that is
    not an image type.
    """
    if "\\" in name or any(part.startswith(".") for part in name.split("/")):
        return None
    root = (root or ASSETS_DIR).resolve()
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
