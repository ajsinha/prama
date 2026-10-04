"""Driving Prama end to end through the SDK, and narrating it.

A case study is a client of **your** Prama: the server `config/application.yaml`
describes (or the one `--config` names), reached through `prama_sdk`, as a
named person with that person's permissions. It never opens Prama's database
and never starts a server of its own, so what it does is exactly what a person
integrating with Prama could do, and it all appears in the console you already
have open.

The point of a study is that you can watch the thing work, so this prints each
stage as it happens, and prints what it *did not* do alongside what it did. The
stages are the product's own, in order:

    declare  →  derive (Γ)  →  accept  →  run  →  read

Each run gets an estate of its own, named with the time it started, so a
rerun starts clean without deleting anybody's evidence: the ledger is
append-only, and earlier runs stay as they were.

Nothing here reaches past the SDK. If a study needs something Prama does not
expose, that is a finding about Prama, and it belongs in the roadmap, not in a
helper that works around it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import prama_sdk as prama

from _common.defects import DefectLog
from _common.estate import Dataset, Relationship

RULE = "─" * 78

#: The repository root: where the server runs, and what relative paths in the
#: application's configuration are relative to.
ROOT = Path(__file__).resolve().parents[2]


def say(message: str = "") -> None:
    print(message, flush=True)


def stage(number: int, title: str, why: str) -> None:
    say()
    say(RULE)
    say(f"  {number}. {title}")
    say(f"     {why}")
    say(RULE)


def banner(title: str, subtitle: str) -> None:
    say()
    say("═" * 78)
    say(f"  {title}")
    say(f"  {subtitle}")
    say("═" * 78)


def arguments(description: str) -> argparse.Namespace:
    """The flags every study takes: which server, and as whom.

    ``--config`` is an ``application.yaml``: the study talks to the server that
    file describes (``server.host`` and ``server.port``), exactly as `prama_sdk.connect`
    does. To use another server, write another file and pass it.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--config",
        default=os.environ.get("PRAMA_CONFIG", str(ROOT / "config" / "application.yaml")),
        help="the application.yaml of the Prama server to use (default: this checkout's)",
    )
    parser.add_argument("--url", default="", help="the server's URL, instead of --config")
    parser.add_argument(
        "--username", default=os.environ.get("PRAMA_USERNAME", "admin"), help="who to sign in as"
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("PRAMA_PASSWORD", "prama-dev-admin"),
        help="their password (default: the development bootstrap admin's)",
    )
    parser.add_argument(
        "--estate",
        default=os.environ.get("PRAMA_TENANT", "default"),
        help=(
            "the estate to sign in to before creating this run's own (default: 'default', "
            "the one a fresh installation makes for its bootstrap admin)"
        ),
    )
    # Accepted and ignored: studies used to start a console of their own.
    parser.add_argument("--no-serve", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


@dataclasses.dataclass
class Source:
    """One place data lives, registered with Prama as a connection.

    ``source_type`` is what the server opens it as: ``sqlite`` (one file),
    ``duckdb`` (one file) or ``files`` (a directory of CSV, Parquet and
    JSON-lines files). The server reads it itself, so the path must be under
    one of the server's ``runs.roots``.
    """

    name: str
    source_type: str
    path: Path
    #: The declared datasets this source holds, by slug. A pass is scoped to
    #: them, so controls on other sources are not reached rather than erroring.
    datasets: set[str]
    config: dict[str, Any] = dataclasses.field(default_factory=dict)


class Harness:
    """One case study, from sign-in to a verified evidence chain."""

    def __init__(self, workspace: Path, *, title: str, args: argparse.Namespace) -> None:
        self.workspace = workspace.resolve()
        self.title = title
        self.args = args
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.client: prama.Client | None = None
        self.estate: dict[str, Any] = {}
        self.dataset_ids: dict[str, str] = {}
        #: The estate's business owner, a second person: Tier-1 and Tier-2
        #: declarations need an approver who is not their author.
        self.owner_id = ""
        #: The owner, signed in: they approve what the administrator declares.
        self.owner: prama.Client | None = None
        self.accepted = 0
        self.unsatisfiable: list[dict[str, str]] = []
        #: Comparisons PQL cannot say yet: declared and shown, not run, not claimed.
        self.comparisons: list[dict[str, str]] = []

    # -- sign in -------------------------------------------------------------

    @property
    def approver(self) -> prama.Client:
        """The owner's client: the second person, who approves."""
        if self.owner is None:
            raise RuntimeError("start() the study before approving anything")
        return self.owner

    @property
    def sdk(self) -> prama.Client:
        """The client acting in this study's estate."""
        if self.client is None:
            raise RuntimeError("start() the study before using the SDK")
        return self.client

    def start(self, *, tenant_slug: str, tenant_name: str) -> None:
        """Sign in to the running server and create this run's estate."""
        args = self.args
        try:
            operator = prama.connect(
                args.url or None,
                config=None if args.url else args.config,
                username=args.username,
                password=args.password,
                tenant=args.estate,
            )
            me = operator.auth.me()
        except prama.ServerUnavailable as error:
            say()
            say(f"  No Prama server answered: {error.message}")
            say("  Start the one this study should use, then run it again:")
            say("      python run_prama_web.py          (or: prama serve)")
            say("  or point the study at another: --config path/to/application.yaml")
            sys.exit(2)
        except prama.UnauthorisedError:
            say()
            say(f"  The server refused {args.username!r}.")
            say("  Pass --username and --password (or PRAMA_USERNAME / PRAMA_PASSWORD),")
            say("  and --estate when the server has more than one estate.")
            sys.exit(2)
        # The time says when the run was; the suffix makes two runs in the same
        # second two estates. A study on a small book finishes in under one, and
        # the second run was refused because the first had taken its name.
        slug = f"{tenant_slug}-{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
        made = operator.tenants.create(slug, tenant_name)
        self.estate = made["tenant"]
        self.client = operator.as_key(made["credentials"]["api_key"])
        operator.close()
        # A second person, because maker-checker is a control and not a formality:
        # the administrator declares, and the owner, signed in as themselves,
        # approves. Nobody names somebody else as approver: over the API that
        # is no longer possible, because it was a claim anyone could make.
        secret = secrets.token_urlsafe(18)
        owner = self.sdk.principals.create(
            "owner", roles=["owner"], password=secret, display_name="Olu Adeyemi (business owner)"
        )
        self.owner_id = str(owner["id"])
        self.owner = prama.connect(
            self.sdk.base_url, username="owner", password=secret, tenant=slug
        )
        say(f"  Prama server: {self.sdk.base_url}  (signed in as {me['username']})")
        say(f"  This run's estate: {slug} — {tenant_name}")

    # -- the stages ----------------------------------------------------------

    def declare(self, datasets: list[Dataset]) -> None:
        stage(
            2,
            "Declare the estate",
            "In business terms. Not one line of SQL is written in this step.",
        )
        for dataset in datasets:
            declared = self.sdk.datasets.declare(dataset.name, **dataset.to_api())
            self.dataset_ids[declared["slug"]] = declared["id"]
            if declared["lifecycle_state"] == "proposed":
                # Held until approved: the owner signs it off, as themselves.
                self.approver.datasets.approve(declared["id"], reason="reviewed for the study")
            for attribute in dataset.attributes:
                self.sdk.datasets.add_attribute(
                    declared["id"], attribute.name, **attribute.to_api()
                )
            say(
                f"  {dataset.name:<30} tier {dataset.criticality}  "
                f"{len(dataset.attributes)} attribute(s)"
            )
            say(f"    one row is: {dataset.grain_statement}")

    def derive_and_accept(self) -> None:
        stage(
            3,
            "Derive the controls (Γ), and accept them",
            "Every control below follows from a declaration above. Nobody wrote one.",
        )
        for slug, dataset_id in self.dataset_ids.items():
            # A case study accepts everything, and says so. A real estate
            # reviews them: the queue is on /proposals, and a control nobody
            # accepted does not run.
            derived = self.sdk.derive.dataset(
                dataset_id, declare=True, accept=True, reason="accepted for the study"
            )
            controls = derived.get("controls", [])
            self.accepted += len(controls)
            for item in derived.get("unsatisfiable", []):
                self.unsatisfiable.append(
                    {
                        "dataset": slug,
                        "rule": item.get("rule", ""),
                        "reason": item.get("reason", ""),
                    }
                )
            gaps = derived.get("unsatisfiable", [])
            note = f"  {len(gaps)} unsatisfiable" if gaps else ""
            say(f"  {slug:<30} {len(controls):>3} control(s){note}")
        say()
        say(f"  {self.accepted} control(s) accepted and now running.")
        if self.unsatisfiable:
            # Printed, always. Every tool of this kind reports what it
            # generated; almost none reports what it declined to, and without
            # this the set above looks complete when it is not.
            say()
            say(f"  {len(self.unsatisfiable)} declaration(s) produced no control at all:")
            for item in self.unsatisfiable:
                say(f"    ! {item['dataset']}: {item['reason']}")

    def relate(self, relationships: list[Relationship]) -> None:
        """Declare relationships, confirm them, and derive the controls only they imply.

        Referential integrity and reconciliation are facts about *two*
        datasets. Neither declaration implies them.
        """
        stage(
            3,
            "Declare the relationships",
            "Facts about two datasets. Neither declaration alone implies them.",
        )
        for relationship in relationships:
            declared = self.sdk.relationships.declare(**relationship.to_api(self.dataset_ids))
            # Confirming a Tier-1 relationship is approving it, by somebody other
            # than its author: the owner.
            self.approver.relationships.confirm(declared["id"], reason="confirmed for the study")
            derived = self.sdk.derive.relationship(
                declared["id"], declare=True, accept=True, reason="accepted for the study"
            )
            say(f"  {relationship.kind:<18} {relationship.render()[:70]}")
            for control in derived.get("controls", []):
                self.accepted += 1
                say(f"      → {str(control.get('pql', '')).splitlines()[0][:88]}")
            for spec in derived.get("comparisons", []):
                # Γ proposes a reconciliation as runnable RECONCILE PQL for a
                # reviewer to complete; it is never declared automatically.
                runnable = spec.get("pql") or ""
                if runnable:
                    say(f"      ≈ proposed: {runnable.splitlines()[0][:84]}")
                self.comparisons.append(
                    {
                        "kind": spec.get("kind", ""),
                        "left": spec.get("left", ""),
                        "right": spec.get("right", ""),
                    }
                )
                say(
                    f"      ≈ {spec.get('kind', '')}: {spec.get('left', '')} against "
                    f"{spec.get('right', '')} — a comparison spec, not a control"
                )
            for item in derived.get("unsatisfiable", []):
                self.unsatisfiable.append(
                    {
                        "dataset": relationship.left,
                        "rule": item.get("rule", ""),
                        "reason": item.get("reason", ""),
                    }
                )
                say(f"      ! {str(item.get('reason', ''))[:88]}")

    def author(self, pql: str, *, identity: str, reason: str) -> dict[str, Any]:
        """A control a person wrote, declared and then activated by an approver."""
        declared = self.sdk.controls.declare(pql, identity=identity, criticality=1)
        control = declared.get("control", declared)
        # By the owner, not the author: a Tier-1 control written by one person
        # is switched on by another (maker-checker), and Prama refuses otherwise.
        self.approver.controls.activate(control["id"], reason=reason)
        self.accepted += 1
        return control

    def connect(self, source: Source) -> str:
        """Register *source* with Prama as a connection; return its id."""
        connection = self.sdk.connections.create(
            source.name,
            source.source_type,
            description=f"{self.title}: {source.name}",
            config={"path": str(source.path), **source.config},
        )
        return str(connection["id"])

    def run(self, sources: list[Source]) -> list[dict[str, Any]]:
        stage(
            4,
            "Run them against the data",
            "The server reads each source itself and records evidence in the hash-chained ledger.",
        )
        reports = []
        for source in sources:
            connection_id = self.connect(source)
            try:
                report = self.sdk.runs.start(connection_id, datasets=sorted(source.datasets))
            except prama.ForbiddenError as error:
                say(f"  {source.name}: the server refused to read {source.path}")
                say(f"    {error.message}")
                say(f"    {error.remedy}")
                say("    Add the case-studies directory to runs.roots in the server's")
                say("    application.yaml (the shipped one does), and restart it.")
                sys.exit(3)
            reports.append(report)
            say(f"  {source.name} ({source.source_type})")
            say(f"    {_describe(report)}")
            for outcome in report.get("outcomes", []):
                if not outcome.get("ran", True):
                    error = str(outcome.get("error", ""))[:110]
                    say(f"    ! {outcome.get('dataset', '')}: {error}")
        return reports

    def report(self, planted: DefectLog) -> None:
        stage(
            5,
            "What Prama found, against what was planted",
            "Both columns, including the rows in neither. A study you cannot check is a brochure.",
        )
        latest = _records(self.sdk.evidence.latest())
        verification = self.sdk.evidence.verify()
        failing = [r for r in latest if r.get("verdict") == "fail"]
        indeterminate = [r for r in latest if r.get("verdict") == "indeterminate"]
        errored = [r for r in latest if r.get("verdict") == "error"]
        passing = [r for r in latest if r.get("verdict") == "pass"]

        say("  PLANTED")
        say(planted.render())
        say()
        say("  FOUND")
        ordered = sorted(failing, key=lambda r: (r.get("dataset", ""), r.get("control_id", "")))
        for record in ordered:
            dimensions = ", ".join(record.get("dimensions") or []) or "unclassified"
            say(
                f"    fail  {record.get('dataset', ''):<22} "
                f"{_finding(record.get('metrics') or {}):<28}[{dimensions}]"
            )
        if indeterminate:
            say()
            say("  NOT ESTABLISHED — a pass could not be reported, for one of two reasons.")
            screened = [r for r in indeterminate if r.get("detail")]
            silent = [r for r in indeterminate if not r.get("detail")]
            if screened:
                say()
                say("  (a) The SQL was a screen, not the exact test. Zero violations from a")
                say("      lower bound is not a pass; the residual validator has not run.")
                for record in sorted(screened, key=lambda r: r.get("dataset", "")):
                    say(f"    ?     {record.get('dataset', ''):<22} {_residual(record['detail'])}")
            if silent:
                say()
                say("  (b) The engine returned metrics the control could not be judged from.")
                say("      Reported rather than assumed either way.")
                for record in sorted(silent, key=lambda r: r.get("dataset", "")):
                    say(
                        f"    ?     {record.get('dataset', ''):<22} "
                        f"{_finding(record.get('metrics') or {})}"
                    )
        if errored:
            say()
            say("  COULD NOT RUN — these checked nothing, and no verdict says so.")
            for record in errored:
                detail = str(record.get("detail", ""))[:90]
                say(f"    !     {record.get('dataset', ''):<24} {detail}")

        say()
        say(
            f"  {len(passing)} passing · {len(failing)} failing · "
            f"{len(indeterminate)} not established · {len(errored)} could not run"
        )
        intact = verification.get("intact", verification.get("is_intact"))
        say(
            f"  Evidence chain: {verification.get('records', '?')} record(s), "
            f"{'verified' if intact else 'BROKEN'}"
        )
        if verification.get("merkle_root"):
            say(f"  Merkle root: {verification['merkle_root']}")
        if self.comparisons:
            say()
            say("  DERIVED FROM RELATIONSHIPS, FOR REVIEW")
            say("  Γ proposes each comparison; a reconciliation comes as runnable")
            say("  RECONCILE PQL for a reviewer to complete (normalisation, say). Only")
            say("  what a person activated runs, and only that is claimed above.")
            for spec in self.comparisons:
                say(f"    ≈ {spec['kind']}: {spec['left']} against {spec['right']}")

    def finish(self) -> None:
        """Say where to look, in the console of the server the study used."""
        base = self.sdk.base_url
        slug = self.estate.get("slug", "")
        stage(6, "Look at it", "In the console you already run: nothing was started for this.")
        say(f"  Sign in at {base}/sign-in with estate {slug!r}, as {self.args.username}.")
        say(f"  {base}/estate        the estate, as declared")
        say(f"  {base}/controls      what is running, and what is silenced")
        say(f"  {base}/incidents     what is currently wrong")
        say(f"  {base}/scorecards    the numbers, decomposed")
        say(f"  {base}/evidence      the ledger, and whether it verifies")
        say(f"  {base}/reports       the packs that leave the building")
        self.close()

    def close(self) -> None:
        for client in (self.client, self.owner):
            if client is not None:
                client.close()
        self.client = self.owner = None


def _records(latest: Any) -> list[dict[str, Any]]:
    """The latest record per control, whatever envelope the endpoint uses."""
    if isinstance(latest, dict):
        for key in ("records", "items", "latest"):
            if isinstance(latest.get(key), list):
                return list(latest[key])
        return [v for v in latest.values() if isinstance(v, dict)]
    return list(latest or [])


def _describe(report: dict[str, Any]) -> str:
    """One line for a run, from its report."""
    if report.get("summary"):
        return str(report["summary"])
    outcomes = report.get("outcomes", [])
    verdicts: dict[str, int] = {}
    for outcome in outcomes:
        verdict = str(outcome.get("verdict") or ("error" if not outcome.get("ran", True) else "?"))
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
    counted = ", ".join(f"{n} {v}" for v, n in sorted(verdicts.items()))
    return f"{len(outcomes)} control(s) ran: {counted or 'none'}"


def _finding(metrics: dict[str, float]) -> str:
    """What a record found, in the metric its own assertion produced.

    A uniqueness control reports distinct keys, not violating rows, and
    printing "0 of 72 rows" for a genuine duplicate is a report that argues
    against its own verdict. Each shape gets the number that means something.
    """
    scanned = int(metrics.get("scanned_rows", 0))
    if "distinct_keys" in metrics:
        duplicates = scanned - int(metrics["distinct_keys"])
        return f"{duplicates:,} duplicate(s) in {scanned:,} rows"
    if "violating_rows" in metrics:
        return f"{int(metrics['violating_rows']):,} of {scanned:,} rows"
    if metrics:
        return ", ".join(f"{k}={int(v):,}" for k, v in sorted(metrics.items()))
    return "no metrics returned"


def _residual(detail: str) -> str:
    """The residual named in the detail, without the paragraph around it."""
    if "residual (" in detail:
        return "screen only; residual not run: " + detail.split("residual (", 1)[1].split(")")[0]
    return "screen only; the residual has not run"
