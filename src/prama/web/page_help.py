"""
"About this page": a few lines at the foot of every console page.

After Maya's ``page_help.py``. A console this rich hides its ideas in plain sight:
what a screen is for, what can be done there, and the concept that makes sense of
it. Each page therefore ends with a sentence and two or three tiles, and a link to
the help page that is the full account. The words are short on purpose: the help
centre restates nothing, and neither does this. It points.

One entry per page, keyed by the route's path template. ``tests/web/test_page_help.py``
fails when a page has none, when an entry names a page that no longer exists, or when
its "More in Help" names a help page that does not, so a new screen cannot ship
without saying what it is.

One tile is not written here at all. **Who can use this page** is derived from the
permission the page was registered with (``UiRoutes.page``) and from the built-in
roles that grant it, so it cannot disagree with the check that actually runs.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass(frozen=True, slots=True)
class Tile:
    heading: str
    #: A Bootstrap icon name, without the ``bi-`` prefix.
    icon: str
    #: Short, and may hold inline markup (``<strong>``, ``<code>``).
    text: str


@dataclasses.dataclass(frozen=True, slots=True)
class PageHelp:
    #: What the page is for, in one sentence.
    what: str
    tiles: tuple[Tile, ...]
    #: The help page that is the full account (a slug in ``help_catalog.BY_SLUG``,
    #: optionally with ``#anchor``), or None.
    more: str | None = None


def _p(what: str, *tiles: tuple[str, str, str], more: str | None = None) -> PageHelp:
    return PageHelp(what, tuple(Tile(*t) for t in tiles), more)


#: GET routes that answer with something other than a page, and so have no foot.
EXEMPT: dict[str, str] = {
    "/controls/backtest": "a stream of server-sent events the studio draws, not a page",
    "/attestations/{attestation_id}/pack": "a file to download: the signed pack",
    "/reports/declarations": "a file to download: the declaration pack",
    "/reports/controls": "a file to download: the control pack",
}

PAGES: dict[str, PageHelp] = {
    # -- public ------------------------------------------------------------------------
    "/": _p(
        "What Prama is: data quality the business declares, proved by evidence anyone can check.",
        (
            "Declare, then prove",
            "megaphone",
            "Owners say what the data means; Prama derives the controls, runs them, and seals "
            "every verdict in a ledger.",
        ),
        (
            "Four ways in",
            "signpost-split",
            "The console, the API, the Python SDK and the CLI all write to one ledger.",
        ),
        (
            "Start here",
            "flag",
            "Sign in, or read the <strong>Quickstart</strong> to run it yourself.",
        ),
        more="quickstart",
    ),
    "/about": _p(
        "Who built Prama, and why it exists.",
        (
            "Where it sits",
            "bar-chart-steps",
            "The competitive landscape page compares Prama with the tools it meets, including "
            "where they are ahead.",
        ),
        more="competitive-analysis",
    ),
    "/about/competitive": _p(
        "Prama against the categories it competes with, capability by capability.",
        (
            "Read it honestly",
            "bar-chart",
            "Each row says where Prama is ahead, level or behind, and the full analysis names "
            "vendors.",
        ),
        more="competitive-analysis",
    ),
    "/legal": _p(
        "The licence and legal notice, read from the files that are the authority.",
        (
            "One source",
            "file-earmark-text",
            "This page renders <code>LICENSE</code> and <code>NOTICE</code> as they are; it is "
            "never a second copy.",
        ),
    ),
    "/sign-in": _p(
        "Signing in to an estate.",
        (
            "The estate",
            "building",
            "Asked only when the installation has several estates and no default.",
        ),
        (
            "A fresh installation",
            "key",
            "The bootstrap admin is <code>admin</code> / <code>prama-dev-admin</code>; change the "
            "password at once.",
        ),
        more="accounts",
    ),
    # -- help --------------------------------------------------------------------------
    "/help": _p(
        "Every guide and document, one card each, rendered from the file that is its authority.",
        (
            "Derived, not written twice",
            "diagram-3",
            "A card's title and summary come from its document, so help and docs cannot disagree.",
        ),
        (
            "Where to begin",
            "flag",
            "<strong>Getting started</strong> for the console; <strong>How it fits "
            "together</strong> for the architecture.",
        ),
        more="console-tour",
    ),
    "/help/{slug}": _p(
        "One guide or document, rendered from its Markdown source.",
        (
            "The source",
            "file-earmark-code",
            "The path at the foot names the file. Edit that, and this page changes on the next "
            "load.",
        ),
        more="corpus",
    ),
    "/help/case-studies": _p(
        "Worked estates over fabricated banking data, each run against your own server.",
        (
            "Run one",
            "terminal",
            "<code>python run.py</code> in a study's folder; what it does appears in this console.",
        ),
        more="sdk",
    ),
    "/help/case-studies/{slug}": _p(
        "One case study: what it builds, what it plants, and what Prama should find.",
        (
            "Checkable numbers",
            "check2-square",
            "The data is seeded, so the figures in the study are the figures you will see.",
        ),
        more="sdk",
    ),
    # -- account and administration ----------------------------------------------------
    "/account": _p(
        "You: who you are signed in as, your roles, and what they let you do.",
        (
            "Roles, not people",
            "person-badge",
            "What you may do comes from your roles; an administrator changes them.",
        ),
        more="accounts",
    ),
    "/account/password": _p(
        "Change your password.",
        (
            "The default password",
            "shield-exclamation",
            "Until the bootstrap admin's default password is changed, every page says so.",
        ),
        more="accounts",
    ),
    "/account/keys": _p(
        "Your API keys: for scripts, the SDK and CI.",
        (
            "Bounded by you",
            "shield-lock",
            "A key can never do more than your roles allow, whatever scopes it names.",
        ),
        (
            "Shown once",
            "eye-slash",
            "The key is displayed when created and never again; only its hash is stored.",
        ),
        more="api-keys",
    ),
    "/admin/users": _p(
        "The people in this estate: add them, set roles, reset passwords.",
        (
            "Four roles",
            "people",
            "<strong>admin</strong>, <strong>owner</strong>, <strong>steward</strong> and "
            "<strong>auditor</strong>; each card says what it may do.",
        ),
        more="accounts",
    ),
    "/admin/keys": _p(
        "Every API key in the estate, whoever holds it.",
        (
            "Revoke, not create",
            "key",
            "Keys are minted by their holder; an administrator can see and revoke any of them.",
        ),
        more="api-keys",
    ),
    # -- the estate --------------------------------------------------------------------
    "/estate": _p(
        "The estate as the business describes it: every declared dataset and how they relate.",
        (
            "The four counts",
            "grid-3x3-gap",
            "Datasets declared, not connected, incomplete and Tier 1; each one filters the map.",
        ),
        (
            "The map",
            "diagram-3",
            "A dot per dataset, coloured by tier, joined by declared relationships. Switch on "
            "<strong>Relate two datasets</strong> to declare one.",
        ),
        (
            "Coverage gaps",
            "exclamation-triangle",
            "What the estate cannot yet answer for, listed rather than hidden.",
        ),
        more="architecture-semantic-layer",
    ),
    "/estate/gaps": _p(
        "What the business declared and Prama cannot act on.",
        (
            "From declarations",
            "list-check",
            "Unreachable, unowned or unshaped: drawn from what owners said, which no crawler "
            "would see.",
        ),
        more="architecture-semantic-layer",
    ),
    "/estate/{dataset_id}": _p(
        "One dataset: what it is, its attributes, its relationships, and what can be controlled.",
        (
            "Critical data elements",
            "star",
            "Attributes marked critical carry the strictest controls and the tightest review.",
        ),
        (
            "What can be controlled",
            "shield-check",
            "Says which kinds of control the declaration supports, and what it would need "
            "for the rest.",
        ),
        more="architecture-semantic-layer",
    ),
    "/declarations": _p(
        "Every declaration, with what each one still cannot produce.",
        (
            "Incomplete",
            "hourglass-split",
            "A dataset with no grain, owner or rhythm cannot yield the controls those imply.",
        ),
        (
            "The tier decides review",
            "layers",
            "Tier 1 and 2 changes wait for approval, Tier 1 by a second person; Tier 3 and 4 "
            "take effect at once.",
        ),
        more="semantic-layer",
    ),
    "/declarations/new": _p(
        "Declare a dataset in business terms: meaning, grain, rhythm, owner, tier.",
        (
            "No SQL",
            "chat-quote",
            "Everything here is a sentence an owner would say; Prama derives the controls from it.",
        ),
        (
            "Held at Tier 1",
            "people",
            "A Tier-1 declaration is recorded and held until someone other than its author "
            "approves it.",
        ),
        more="semantic-layer",
    ),
    "/relationships": _p(
        "How datasets relate: reconciles-with, derives-from, feeds, same-entity-as.",
        (
            "Confirm or reject",
            "check2-circle",
            "A proposed relationship waits for a person; controls derived from it are held until "
            "it is confirmed.",
        ),
        (
            "Defects one dataset cannot see",
            "arrow-left-right",
            "A relationship yields controls across two datasets, such as a reconciliation.",
        ),
        more="architecture-semantic-layer",
    ),
    "/relationships/new": _p(
        "Declare that two datasets relate, and how.",
        (
            "It becomes controls",
            "diagram-2",
            "A declared relationship is derived into controls like any other declaration.",
        ),
        more="architecture-semantic-layer",
    ),
    "/glossary": _p(
        "The business glossary: terms, what they mean, and the data they name.",
        (
            "Bind a term",
            "link-45deg",
            "Binding a term to an attribute carries its meaning into derivation and search.",
        ),
        (
            "Bring yours",
            "box-arrow-in-down",
            "<code>prama glossary import</code> takes an Alation or Collibra export.",
        ),
        more="glossary",
    ),
    "/metadata": _p(
        "Metadata and business context: find data by what it means, and see where meaning "
        "diverges.",
        (
            "Find data",
            "search",
            "Search by business context and metadata across datasets, not inside one.",
        ),
        (
            "Same meaning, different datasets",
            "intersect",
            "Where one meaning is held in several places, and where they disagree.",
        ),
        (
            "Most used, least controlled",
            "graph-up",
            "From query history: where a missing control would hurt most.",
        ),
        more="metadata",
    ),
    "/metadata/d/{slug}": _p(
        "One dataset's metadata, its business context, and the rules they imply.",
        (
            "Rules from metadata",
            "magic",
            "A field such as <em>mandatory</em> implies a rule; <strong>Propose rule</strong> "
            "sends it for review.",
        ),
        ("Discussion", "chat-left-text", "Comments with @mentions reach the named person's queue."),
        more="metadata",
    ),
    "/queue": _p(
        "Everything waiting on you: mentions, approvals, breaks and reviews.",
        (
            "Resolve, not read",
            "check2-circle",
            "An item leaves when it is resolved, not when it is seen.",
        ),
        more="queue",
    ),
    # -- controls ----------------------------------------------------------------------
    "/controls": _p(
        "Every control in the estate, grouped by whether it actually runs.",
        (
            "Proposed is not running",
            "pause-circle",
            "A proposal checks nothing until somebody starts it.",
        ),
        (
            "Starting follows the tier",
            "people",
            "A Tier-1 control a person wrote is started by a different person.",
        ),
        (
            "Silence, never delete",
            "volume-mute",
            "Silencing needs an expiry and a reason; retired controls keep their evidence.",
        ),
        more="pql",
    ),
    "/controls/studio": _p(
        "Write a control in PQL, check it as you type, and see what it would have done.",
        (
            "Datasets you can write against",
            "table",
            "Listed beside the editor: the estate's datasets, by the names PQL uses.",
        ),
        (
            "What would it have done?",
            "clock-history",
            "Where the data allows, run the control day by day over last month first.",
        ),
        more="pql",
    ),
    "/controls/build": _p(
        "Build a control from a form, for anyone who will never write PQL.",
        (
            "It writes PQL",
            "code-slash",
            "The control appears as PQL as soon as you build it: the same text a person would "
            "type.",
        ),
        more="pql",
    ),
    "/proposals": _p(
        "Controls Prama derived from declarations and mining, waiting for a person.",
        (
            "Accept or reject",
            "check2-square",
            "Accepting starts a control; rejecting asks why, and that rejection is remembered.",
        ),
        (
            "AI proposes, never decides",
            "robot",
            "A proposal may come from a model; the verdict on data never does.",
        ),
        more="architecture-controls-and-pql",
    ),
    "/proposals/{dataset_id}": _p(
        "The proposals for one dataset.",
        (
            "Derived from what was said",
            "diagram-3",
            "Each proposal names the declaration or metadata that implied it.",
        ),
        more="architecture-controls-and-pql",
    ),
    "/schedule": _p(
        "When controls run, and what the scheduler did on its last ticks.",
        (
            "One server runs it",
            "hdd-network",
            "Across several servers a lease decides which one ticks; the others skip.",
        ),
        (
            "Run a tick now",
            "play-circle",
            "Runs what is due immediately, rather than waiting for the interval.",
        ),
        more="architecture-execution",
    ),
    # -- assurance ---------------------------------------------------------------------
    "/incidents": _p(
        "What is wrong now: one row per failing control, not one per run.",
        (
            "One problem, one row",
            "list-ul",
            "A control failing hourly for a week is one incident, not a hundred and sixty-eight.",
        ),
        (
            "Open one",
            "search",
            "The failing rows, the control's history, and what lies upstream in the lineage.",
        ),
        more="architecture-evidence-and-assurance",
    ),
    "/incidents/{control_id}": _p(
        "One failing control: what it says, the rows that failed, and where to look.",
        (
            "Upstream",
            "diagram-2",
            "From the lineage store: what feeds this data, so the cause can be found where it "
            "began.",
        ),
        (
            "The PQL",
            "code-slash",
            "The control exactly as it ran; its plan id ties it to the evidence.",
        ),
        more="architecture-evidence-and-assurance",
    ),
    "/reconciliation": _p(
        "Every reconciliation and its latest result, from the same ledger as everything else.",
        ("Break queues", "inboxes", "Open one to work its breaks, most urgent first."),
        more="sdk-reconciliation",
    ),
    "/reconciliation/{definition}": _p(
        "Every break for one reconciliation, ordered by what needs a person, not by size.",
        (
            "Why this order",
            "sort-down",
            "A large timing break clears itself; a small genuine one is somebody's missing trade.",
        ),
        (
            "Assign, note, accept",
            "person-check",
            "Accepting a break needs a reason: an acceptance nobody explained cannot be defended.",
        ),
        more="sdk-reconciliation",
    ),
    "/scorecards": _p(
        "A score per dataset, and exactly how it was derived.",
        (
            "Derived from evidence",
            "calculator",
            "Each score is computed from the latest verdicts, weighted by criticality, never "
            "typed in.",
        ),
        ("Grey until proven", "circle-half", "No evidence means no score, not a good one."),
        more="architecture-evidence-and-assurance",
    ),
    "/evidence": _p(
        "The evidence ledger: every verdict Prama has recorded, chained so any edit shows.",
        (
            "Is it intact?",
            "shield-check",
            "The chain is recomputed when this page opens; the head and Merkle root stand for "
            "all of it.",
        ),
        (
            "Prove it elsewhere",
            "box-arrow-up-right",
            "<code>prama evidence export</code> then <code>scripts/verify_evidence.py</code> "
            "checks it without Prama.",
        ),
        (
            "Verdicts, not opinions",
            "cpu",
            "A deterministic engine decides every verdict; no model does.",
        ),
        more="architecture-evidence-and-assurance",
    ),
    "/attestations": _p(
        "Sign-offs: a named person stating that the evidence supports a claim.",
        (
            "Accountability",
            "pen",
            "Controls and evidence with no sign-off have nobody accountable for them.",
        ),
        more="sdk-evidence",
    ),
    "/attestations/new": _p(
        "See exactly what you would attest to, then sign it.",
        (
            "What the evidence says",
            "clipboard-data",
            "The coverage and verdicts behind the statement are shown before anybody signs.",
        ),
        more="sdk-evidence",
    ),
    "/attestations/{attestation_id}": _p(
        "One signed attestation: the statement, its coverage, and whether it is intact.",
        (
            "The pack",
            "file-earmark-zip",
            "Download the pack: the artefact that leaves the building, checkable on its own.",
        ),
        more="sdk-evidence",
    ),
    "/reports": _p(
        "Packs to hand to an auditor or a regulator.",
        ("Declaration pack", "journal-text", "What the business says its data is."),
        ("Control pack", "shield-check", "Every control, why it exists, and the SQL it becomes."),
        more="sdk-evidence",
    ),
    # -- intelligence, code and lineage ------------------------------------------------
    "/lineage": _p(
        "Column lineage from every source Prama has read, and what a defect reaches.",
        (
            "How an edge is known",
            "patch-check",
            "<strong>parsed</strong> from SQL, <strong>inferred</strong> and waiting for a "
            "person, or <strong>confirmed</strong> by one.",
        ),
        ("Impact", "bullseye", "Name a column to see everything downstream of a defect in it."),
        more="lineage",
    ),
    "/code": _p(
        "Send an application's code, as a ZIP or a git location; Prama reads its lineage.",
        ("Read, never run", "file-earmark-lock", "The code is parsed, never executed."),
        (
            "Runs",
            "list-task",
            "Each intake shows the files read, the edges found, the gaps, and what is not yet "
            "read.",
        ),
        more="code",
    ),
    "/models": _p(
        "The language models Prama may use: providers, profiles, budgets and the call ledger.",
        (
            "Profiles",
            "signpost",
            "A purpose such as authoring routes to an ordered list of models.",
        ),
        (
            "Budgets",
            "cash-coin",
            "Every model call, from any path, is checked against them; a refusal is recorded.",
        ),
        (
            "The call ledger",
            "journal-check",
            "Every call is hash-chained; by default it keeps hashes of the prompt and answer, "
            "not the text.",
        ),
        more="models",
    ),
    "/agents": _p(
        "Steward agents: AI that reads the estate and proposes, never approves.",
        (
            "Goals",
            "bullseye",
            "Each steward works towards goals; a goal can wait for a person before it runs.",
        ),
        (
            "The kill switch",
            "power",
            "Suspending a steward stops its key and its model access at once.",
        ),
        more="agents",
    ),
    "/delegates": _p(
        "Python checks PQL cannot say: uploaded, vetted, approved, and judged by Prama.",
        (
            "The delegate measures",
            "rulers",
            "It returns counts; the control's threshold, in Prama, decides the verdict.",
        ),
        (
            "Four eyes",
            "people",
            "An upload is approved by someone other than the person who uploaded it.",
        ),
        more="delegates",
    ),
}


def _who(scope: str | None) -> Tile:
    """The tile no person writes: the permission the page checks, and who holds it."""
    if scope is None:
        return Tile("Who can use this page", "unlock", "Anyone; no sign-in is needed.")
    from prama.security.accounts import BUILTIN_ROLES
    from prama.security.scopes import SCOPES, permits

    roles = [name for name, (_, granted) in BUILTIN_ROLES.items() if permits(granted, scope)]
    meaning = SCOPES.get(scope, "")
    return Tile(
        "Who can use this page",
        "shield-lock",
        f"Needs <code>{scope}</code>{f' ({meaning})' if meaning else ''}. Built-in roles that "
        f"grant it: {', '.join(f'<strong>{r}</strong>' for r in roles) or 'none'}.",
    )


def for_route(path: str | None) -> dict[str, Any] | None:
    """The help for the page at route template *path*, ready for the template, or None."""
    if not path or path not in PAGES:
        return None
    from prama.web.routes.base import PAGE_SCOPES

    entry = PAGES[path]
    tiles = list(entry.tiles)
    if path in PAGE_SCOPES:
        tiles.append(_who(PAGE_SCOPES[path]))
    return {"what": entry.what, "tiles": tiles, "more": entry.more}


__all__ = ["EXEMPT", "PAGES", "PageHelp", "Tile", "for_route"]
