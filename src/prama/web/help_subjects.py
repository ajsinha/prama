"""Help by subject: one page per thing a person wants to understand.

After Maya's help catalogue. Prama's documents are written by kind (a console
guide, an architecture page, an SDK page, a developer guide, a design document),
so the material on one subject (lineage, say) was five cards in five sections,
and a reader had to know the folder layout to find the page they needed. A
subject gathers them in one place, by what each is for:

* **use** it in the console: the task-first guide, rendered in full at the top;
* **run** it: install, configure, operate;
* **how** it works: the architecture;
* **script** it: the Python SDK;
* **extend** it: the developer guide;
* **why** it is built this way: the design corpus and notes;
* **reference**: a glossary, a catalogue.

A subject restates nothing. Its readings are help entries (``help_catalog.BY_SLUG``),
and their titles and summaries are the ones derived from the documents themselves.
``tests/web/test_help_subjects.py`` fails when a subject names an entry that does
not exist, when a slug is shared, or when a console guide, or an architecture,
developer, SDK, agent or operations document, belongs to no subject. The design
corpus and the publications stay in the library, where a reader looking for the
reasoning goes.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

#: role -> (label on the subject page, icon)
ROLES: dict[str, tuple[str, str]] = {
    "use": ("Use it in the console", "window"),
    "run": ("Install and run it", "gear"),
    "how": ("How it works", "diagram-3"),
    "script": ("Script it", "code-square"),
    "extend": ("Extend it", "tools"),
    "why": ("Why it is built this way", "journal-text"),
    "ref": ("Reference", "bookmark"),
}


@dataclasses.dataclass(frozen=True, slots=True)
class Subject:
    slug: str
    title: str
    icon: str
    summary: str
    #: (role, help entry slug), in reading order. The first is the subject's
    #: opening: rendered in full on the subject page.
    readings: tuple[tuple[str, str], ...]
    badge: str = ""


@dataclasses.dataclass(frozen=True, slots=True)
class Category:
    id: str
    name: str
    icon: str
    blurb: str
    subjects: tuple[str, ...]


def _s(
    slug: str, title: str, icon: str, summary: str, *readings: tuple[str, str], badge: str = ""
) -> Subject:
    return Subject(slug, title, icon, summary, tuple(readings), badge)


_SUBJECTS: tuple[Subject, ...] = (
    # -- start here --------------------------------------------------------------------
    _s(
        "getting-started",
        "Getting started",
        "flag",
        "Install Prama, run it, sign in, and find your way round the console.",
        ("use", "console-tour"),
        ("run", "quickstart"),
        ("run", "developer-ide"),
        ("how", "architecture"),
        ("ref", "terms"),
        badge="Start here",
    ),
    _s(
        "python-sdk",
        "The Python SDK",
        "code-square",
        "Everything the console does, from a script, against your running server.",
        ("script", "sdk"),
        ("script", "sdk-usage"),
        ("extend", "developer-sdk-methods"),
        ("how", "architecture-packages"),
    ),
    # -- the estate --------------------------------------------------------------------
    _s(
        "the-estate",
        "Declaring the estate",
        "diagram-3",
        "Datasets, their grain and tier, and how they relate: what owners say, in their words.",
        ("use", "declaring"),
        ("how", "architecture-semantic-layer"),
        ("script", "sdk"),
        ("why", "semantic-layer"),
    ),
    _s(
        "meaning-and-metadata",
        "Metadata and the glossary",
        "tags",
        "Business context, your own metadata fields, the glossary, and finding data by meaning.",
        ("use", "metadata"),
        ("use", "glossary"),
        ("how", "architecture-semantic-layer"),
        ("script", "sdk-knowledge"),
        ("extend", "developer-importers"),
    ),
    _s(
        "working-together",
        "Discussion and your queue",
        "inbox",
        "Comments with @mentions, and everything waiting on you in one place.",
        ("use", "queue"),
        ("script", "sdk-knowledge"),
    ),
    # -- controls ----------------------------------------------------------------------
    _s(
        "controls-and-pql",
        "Controls and PQL",
        "shield-check",
        "Proposals, accepting and silencing controls, writing PQL, and the rule builder.",
        ("use", "controls"),
        ("how", "architecture-controls-and-pql"),
        ("script", "sdk-controls"),
        ("extend", "developer-pql-functions"),
        ("extend", "developer-validators"),
        ("extend", "developer-importers"),
        ("why", "pql"),
    ),
    _s(
        "python-checks",
        "Python checks (DQ delegates)",
        "braces",
        "Checks PQL cannot say, written in Python: they measure, Prama decides.",
        ("use", "delegates"),
        ("extend", "developer-delegates"),
        ("how", "architecture-execution"),
        ("why", "design-dq-delegates"),
    ),
    _s(
        "contracts",
        "Data contracts in CI",
        "file-earmark-check",
        "Check data against a contract in a pipeline, and diff two versions of a dataset.",
        ("script", "sdk-contracts"),
        ("how", "architecture-controls-and-pql"),
        ("run", "cli"),
    ),
    _s(
        "domain-packs",
        "The banking pack",
        "bank",
        "Calendars, message standards and concepts a bank's data is checked against.",
        ("why", "banking-pack"),
        ("extend", "developer-packs"),
    ),
    # -- running and proving -----------------------------------------------------------
    _s(
        "sources-and-runs",
        "Sources and runs",
        "plug",
        "Connecting to data, when controls run, and on which engine.",
        ("how", "architecture-execution"),
        ("extend", "developer-connectors"),
        ("extend", "developer-backends-and-dialects"),
        ("run", "configuration"),
        ("why", "connectivity-and-formats"),
    ),
    _s(
        "evidence-and-sign-off",
        "Evidence, incidents and sign-off",
        "patch-check",
        "What is failing, how good each dataset is, whether the record is intact, and signing it.",
        ("use", "evidence"),
        ("how", "architecture-evidence-and-assurance"),
        ("script", "sdk-evidence"),
        ("extend", "developer-scorers"),
        ("why", "security"),
    ),
    _s(
        "reconciliation-and-breaks",
        "Reconciliation and breaks",
        "arrow-left-right",
        "Two datasets that must agree, the breaks between them, and working the queue.",
        ("use", "reconciliation"),
        ("script", "sdk-reconciliation"),
        ("how", "architecture-execution"),
    ),
    _s(
        "alerts-and-monitors",
        "Monitors and alerts",
        "bell",
        "Watching metrics over time, and telling the right person once.",
        ("how", "architecture-evidence-and-assurance"),
        ("extend", "developer-monitors-and-notifiers"),
        ("run", "configuration"),
    ),
    # -- lineage and intelligence ------------------------------------------------------
    _s(
        "lineage-and-code",
        "Lineage and code",
        "bezier2",
        "Column lineage from SQL and application code, and what a defect reaches.",
        ("use", "lineage"),
        ("use", "code"),
        ("how", "architecture-lineage-and-code"),
        ("script", "sdk-knowledge"),
        ("extend", "developer-code-readers"),
        ("why", "design-code-lineage-and-steward-agents"),
        ("why", "design-gap-manta-alation"),
    ),
    _s(
        "models-and-ai",
        "Models and the AI boundary",
        "cpu",
        "Language models, steward agents, budgets and the call ledger; AI proposes, never decides.",
        ("use", "models"),
        ("use", "agents"),
        ("how", "architecture-intelligence"),
        ("extend", "developer-llm-providers"),
        ("why", "design-llm-gateway"),
        ("why", "roadmap-intelligence"),
    ),
    _s(
        "agents-beside-the-data",
        "Agents beside the data",
        "hdd-network",
        "A daemon on the customer's machine that runs controls where the data is.",
        ("run", "agent"),
        ("how", "architecture-agents-and-fleet"),
        ("script", "sdk-fleet"),
        ("extend", "developer-agent-executors"),
        ("why", "design-agent-fleet-http"),
        ("why", "distributed-execution"),
    ),
    # -- administer and operate --------------------------------------------------------
    _s(
        "people-and-access",
        "People, roles and keys",
        "people",
        "Accounts, roles, API keys, and what each person may do.",
        ("use", "accounts"),
        ("use", "api-keys"),
        ("how", "architecture-platform"),
        ("script", "sdk-administration"),
        ("why", "security"),
    ),
    _s(
        "operating-prama",
        "Running Prama in production",
        "gear",
        "Deploying, configuring, watching and fixing a Prama installation.",
        ("run", "operations"),
        ("run", "runbook"),
        ("run", "troubleshooting"),
        ("run", "operations-observability"),
        ("ref", "cli"),
        ("ref", "configuration"),
        ("ref", "operations-metrics-reference"),
        ("extend", "developer-secrets-and-leases"),
    ),
    _s(
        "display",
        "Themes and display",
        "palette",
        "The four themes, row density, and why the colours are derived.",
        ("use", "themes"),
        ("ref", "reference-brand"),
    ),
    # -- build on it -------------------------------------------------------------------
    _s(
        "extending-prama",
        "Extending Prama",
        "tools",
        "The plugin model, the gate a change must pass, and a guide per extension point.",
        ("extend", "developer"),
        ("run", "developer-ide"),
        ("how", "architecture-platform"),
        ("extend", "developer-api-and-console"),
        ("extend", "developer-schema-and-daos"),
        ("how", "architecture-packages"),
    ),
)

CATEGORIES: tuple[Category, ...] = (
    Category(
        "start",
        "Start here",
        "flag",
        "Install Prama, find your way round, and drive it from Python.",
        ("getting-started", "python-sdk"),
    ),
    Category(
        "estate",
        "The estate",
        "diagram-3",
        "What the data is, in the business's words, and who is talking about it.",
        ("the-estate", "meaning-and-metadata", "working-together"),
    ),
    Category(
        "controls",
        "Controls",
        "shield-check",
        "The checks: derived, written, delegated to Python, or carried by a pack.",
        ("controls-and-pql", "python-checks", "contracts", "domain-packs"),
    ),
    Category(
        "assurance",
        "Running and proving",
        "patch-check",
        "Where controls run, what they found, and the evidence that proves it.",
        (
            "sources-and-runs",
            "evidence-and-sign-off",
            "reconciliation-and-breaks",
            "alerts-and-monitors",
        ),
    ),
    Category(
        "intelligence",
        "Lineage and intelligence",
        "bezier2",
        "What feeds what, the models Prama may use, and agents beside the data.",
        ("lineage-and-code", "models-and-ai", "agents-beside-the-data"),
    ),
    Category(
        "operate",
        "Administer and extend",
        "gear",
        "People and access, running it in production, and building on it.",
        ("people-and-access", "operating-prama", "display", "extending-prama"),
    ),
)

SUBJECTS: dict[str, Subject] = {s.slug: s for s in _SUBJECTS}

#: Folders whose every document must belong to a subject: everything a person
#: reads to use, run, script or extend Prama. The design corpus, the design
#: notes and the publications are the library's.
MUST_BELONG = ("docs/architecture", "docs/developer", "docs/sdk", "docs/agent", "docs/operations")


def _order() -> list[str]:
    return [slug for category in CATEGORIES for slug in category.subjects]


def category_of(slug: str) -> Category:
    return next(c for c in CATEGORIES if slug in c.subjects)


def subjects_reading(entry_slug: str) -> list[Subject]:
    """The subjects a help entry is part of, for the "part of" chips on its page."""
    return [s for s in _SUBJECTS if any(slug == entry_slug for _, slug in s.readings)]


def view(slug: str) -> dict[str, Any] | None:
    """A subject page's model: the subject, its readings resolved, its neighbours."""
    from prama.web import help_catalog

    subject = SUBJECTS.get(slug)
    if subject is None:
        return None
    category = category_of(slug)
    order = _order()
    i = order.index(slug)
    readings = []
    for role, entry_slug in subject.readings:
        entry = help_catalog.BY_SLUG[entry_slug]
        label, icon = ROLES[role]
        readings.append({"role": role, "label": label, "icon": icon, "entry": entry})
    return {
        "subject": subject,
        "category": category,
        "opening": readings[0],
        "further": readings[1:],
        "siblings": [SUBJECTS[s] for s in category.subjects if s != slug],
        "prev": SUBJECTS[order[i - 1]] if i else None,
        "next": SUBJECTS[order[i + 1]] if i + 1 < len(order) else None,
    }


def catalog() -> list[dict[str, Any]]:
    """The help index's model: each category with its subjects."""
    return [{"category": c, "subjects": [SUBJECTS[s] for s in c.subjects]} for c in CATEGORIES]


__all__ = [
    "CATEGORIES",
    "MUST_BELONG",
    "ROLES",
    "SUBJECTS",
    "Category",
    "Subject",
    "catalog",
    "category_of",
    "subjects_reading",
    "view",
]
