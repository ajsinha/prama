"""Driving Prama end to end, and narrating it.

The point of a case study is that you can watch the thing work, so this prints
each stage as it happens and prints what it *did not* do alongside what it did.
The stages are the product's own, in order:

    declare  →  derive (Γ)  →  accept  →  run  →  read

Nothing here reaches past a public API. If a study needs something Prama does
not expose, that is a finding about Prama and it belongs in the roadmap, not in
a helper that works around it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from _common.defects import DefectLog
from _common.estate import Dataset, declare_estate
from prama.core.config import Configuration, ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.db import Database
from prama.derive import ControlGenerator
from prama.derive.persisted import dataset_declaration_of
from prama.execute import ControlRun

RULE = "─" * 78


def say(message: str = "") -> None:
    print(message, flush=True)


def stage(number: int, title: str, why: str) -> None:
    say()
    say(RULE)
    say(f"  {number}. {title}")
    say(f"     {why}")
    say(RULE)


def configure(workspace: Path, *, tenant: str = "") -> Configuration:
    """A configuration pointing at this study's own Prama database.

    Each study gets its own, so running one does not disturb another and
    deleting one is deleting a directory.
    """
    return (
        ConfigurationBuilder()
        .with_defaults(DEFAULTS)
        .with_mapping(
            {
                "database": {
                    "dialect": "sqlite",
                    "sqlite": {"path": str(workspace / "prama.db")},
                    "schema_dir": str(Path(__file__).resolve().parents[2] / "schema"),
                    "verify_on_start": True,
                },
                # A case study is not a deployment. The secret is fixed so the
                # study is reproducible, and it is worthless — which is why it
                # says so.
                "security": {
                    "session_secret": "case-study-only-not-a-secret",
                    "cookies_https_only": False,
                },
                "tenancy": {"default_tenant": tenant},
                "logging": {"level": "WARNING"},
            },
            name="case-study",
        )
        .build()
    )


@dataclasses.dataclass
class Source:
    """One place data lives, and how to run a query against it."""

    name: str
    engine: str
    execute: Any
    close: Any
    #: Which declared datasets this source holds. A pass is scoped to them, so
    #: controls on other sources are counted as not-reached rather than
    #: producing a table-not-found error each.
    datasets: set[str]
    #: The DQ delegates this pass may run (a `prama.delegates` host).
    delegates: Any = None


class Harness:
    """One case study, from an empty database to a running console."""

    def __init__(self, workspace: Path, *, title: str) -> None:
        self.workspace = workspace
        self.title = title
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._prama_db = workspace / "prama.db"
        if self._prama_db.exists():
            # A study is reproducible or it is anecdote. Every run starts from
            # nothing rather than adding to whatever the last one left.
            self._prama_db.unlink()
        self.config = configure(workspace)
        self.database = Database.from_config(self.config)
        self.tenant_id = ""
        self.dataset_ids: dict[str, str] = {}
        self.accepted = 0
        self.unsatisfiable: list[dict[str, str]] = []
        #: Reconciliations. Specifications rather than controls: the matching
        #: engine executes them, and it is not wired to the runner yet.
        self.comparisons: list[dict[str, str]] = []

    # -- stages ------------------------------------------------------------

    async def start(self, *, tenant_slug: str, tenant_name: str) -> None:
        self.database.initialise(applied_by="case-study")
        await self.database.start()
        async with self.database.unit_of_work() as uow:
            tenant = uow.tenants.create(slug=tenant_slug, display_name=tenant_name)
            await uow.flush()
            self.tenant_id = str(tenant.id)
        # Re-read with the tenant fixed, so the console needs no sign-in.
        self.config = configure(self.workspace, tenant=self.tenant_id)

    async def declare(self, datasets: list[Dataset]) -> None:
        stage(
            2,
            "Declare the estate",
            "In business terms. Not one line of SQL is written in this step.",
        )
        async with self.database.unit_of_work() as uow:
            self.dataset_ids = await declare_estate(
                uow, self.tenant_id, datasets, author="alice", approver="bob"
            )
        for dataset in datasets:
            say(
                f"  {dataset.name:<30} tier {dataset.criticality}  "
                f"{len(dataset.attributes)} attribute(s)"
            )
            say(f"    one row is: {dataset.grain_statement}")

    async def derive_and_accept(self) -> None:
        stage(
            3,
            "Derive the controls (Γ), and accept them",
            "Every control below follows from a declaration above. Nobody wrote one.",
        )
        generator = ControlGenerator()
        async with self.database.unit_of_work() as uow:
            for slug, dataset_id in self.dataset_ids.items():
                version = await uow.datasets.require_current(dataset_id, tenant_id=self.tenant_id)
                attributes = await uow.attributes.for_dataset(dataset_id, tenant_id=self.tenant_id)
                generation = generator.generate(dataset_declaration_of(version, attributes))
                for derived in generation.controls:
                    entity, _ = await uow.controls.declare(
                        tenant_id=self.tenant_id,
                        identity=derived.identity,
                        pql=derived.content,
                        rule=derived.rule,
                        source_ref=dataset_id,
                        criticality=version.criticality,
                        schedule="06:30" if version.criticality == 1 else "daily",
                        authored_by="gamma",
                    )
                    # A case study accepts everything, and says so. A real
                    # estate reviews them: the queue is on /proposals, and a
                    # control nobody accepted does not run.
                    await uow.controls.activate(
                        str(entity.id),
                        tenant_id=self.tenant_id,
                        approved_by="bob",
                        reason="accepted for the study",
                    )
                    self.accepted += 1
                for item in generation.unsatisfiable:
                    self.unsatisfiable.append(
                        {"dataset": slug, "rule": item.rule, "reason": item.reason}
                    )
                unsatisfiable = (
                    f"  {len(generation.unsatisfiable)} unsatisfiable"
                    if generation.unsatisfiable
                    else ""
                )
                say(f"  {slug:<30} {len(generation.controls):>3} control(s){unsatisfiable}")

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

    async def relate(self, declarations: list[Any]) -> None:
        """Declare relationships, and derive the controls only they imply.

        Referential integrity and reconciliation are facts about *two*
        datasets. Neither declaration implies them, which is why the
        single-dataset studies plant those defects and decline to claim them.
        """
        import dataclasses

        from prama.derive import RelationshipGenerator
        from prama.semantic.services import RelationshipService

        stage(
            3,
            "Declare the relationships",
            "Facts about two datasets. Neither declaration alone implies them.",
        )
        generator = RelationshipGenerator()
        async with self.database.unit_of_work() as uow:
            service = RelationshipService(uow)
            for declaration in declarations:
                # Two shapes of the same fact. The *service* stores dataset
                # identifiers, because a declaration has to survive a rename;
                # Γ writes controls against dataset *names*, because a control
                # has to name the thing that exists in the engine. The study
                # writes the readable one and converts here.
                await service.declare(
                    tenant_id=self.tenant_id,
                    declaration=dataclasses.replace(
                        declaration,
                        from_dataset_id=self.dataset_ids[declaration.from_dataset_id],
                        to_dataset_id=self.dataset_ids[declaration.to_dataset_id],
                    ),
                    authored_by="alice",
                    approved_by="bob",
                    criticality=1,
                )
                generation = generator.generate(declaration)
                say(f"  {declaration.kind.value:<18} {declaration.render()[:70]}")
                for derived in generation.controls:
                    entity, _ = await uow.controls.declare(
                        tenant_id=self.tenant_id,
                        identity=derived.identity,
                        pql=derived.content,
                        rule=derived.rule,
                        criticality=1,
                        schedule="06:30",
                        authored_by="gamma",
                    )
                    await uow.controls.activate(
                        str(entity.id), tenant_id=self.tenant_id, approved_by="bob"
                    )
                    self.accepted += 1
                    say(f"      → {derived.content.splitlines()[0][:88]}")
                for spec in generation.comparisons:
                    # A reconciliation is not a control. It is a *comparison
                    # specification* executed by the matching engine
                    # (prama.recon), which is not wired into the control runner
                    # — so it is printed here and not claimed as a finding.
                    self.comparisons.append(
                        {
                            "kind": spec.kind.value,
                            "left": spec.left,
                            "right": spec.right,
                        }
                    )
                    say(
                        f"      ≈ {spec.kind.value}: {spec.left} against {spec.right} "
                        "— a comparison spec, not a control"
                    )
                for item in generation.unsatisfiable:
                    self.unsatisfiable.append(
                        {
                            "dataset": declaration.from_dataset_id,
                            "rule": item.rule,
                            "reason": item.reason,
                        }
                    )
                    say(f"      ! {item.reason[:88]}")

    async def run(self, sources: list[Source]) -> list[Any]:
        stage(
            4,
            "Run them against the data",
            "One pass per source. Each records evidence into the hash-chained ledger.",
        )
        reports = []
        for source in sources:
            async with self.database.unit_of_work() as uow:
                report = await ControlRun(
                    uow,
                    self.tenant_id,
                    execute=source.execute,
                    sample=source.execute,
                    engine=source.engine,
                    triggered_by="manual",
                    datasets=source.datasets,
                    delegates=source.delegates,
                ).execute_all()
            reports.append(report)
            say(f"  {source.name} ({source.engine})")
            say(f"    {report.describe()}")
            for outcome in report.outcomes:
                if not outcome.ran:
                    say(f"    ! {outcome.record.dataset}: {outcome.error[:110]}")
        return reports

    async def report(self, planted: DefectLog) -> None:
        stage(
            5,
            "What Prama found, against what was planted",
            "Both columns, including the rows in neither. A study you cannot check is a brochure.",
        )
        async with self.database.unit_of_work() as uow:
            latest = await uow.evidence.latest_per_control(self.tenant_id)
            verification = await uow.evidence.verify(self.tenant_id)

        failing = [r for r in latest.values() if r.verdict == "fail"]
        indeterminate = [r for r in latest.values() if r.verdict == "indeterminate"]
        errored = [r for r in latest.values() if r.verdict == "error"]
        passing = [r for r in latest.values() if r.verdict == "pass"]

        say("  PLANTED")
        say(planted.render())
        say()
        say("  FOUND")
        for record in sorted(failing, key=lambda r: (r.dataset, r.control_id)):
            say(
                f"    fail  {record.dataset:<22} {_finding(record.metrics):<28}"
                f"[{', '.join(record.dimensions) or 'unclassified'}]"
            )
        if indeterminate:
            say()
            say("  NOT ESTABLISHED — a pass could not be reported, for one of two reasons.")
            screened = [r for r in indeterminate if r.detail]
            silent = [r for r in indeterminate if not r.detail]
            if screened:
                say()
                say("  (a) The SQL was a screen, not the exact test. Zero violations from a")
                say("      lower bound is not a pass; the residual validator has not run.")
                for record in sorted(screened, key=lambda r: r.dataset):
                    say(f"    ?     {record.dataset:<22} {_residual(record.detail)}")
            if silent:
                say()
                say("  (b) The engine returned metrics the control could not be judged from.")
                say("      Reported rather than assumed either way.")
                for record in sorted(silent, key=lambda r: r.dataset):
                    say(f"    ?     {record.dataset:<22} {_finding(record.metrics)}")
        if errored:
            say()
            say("  COULD NOT RUN — these checked nothing, and no verdict says so.")
            for record in errored:
                say(f"    !     {record.dataset:<24} {record.detail[:90]}")

        say()
        say(
            f"  {len(passing)} passing · {len(failing)} failing · "
            f"{len(indeterminate)} not established · {len(errored)} could not run"
        )
        say(
            f"  Evidence chain: {verification.records} record(s), "
            f"{'verified' if verification.is_intact else 'BROKEN'}"
        )
        say(f"  Merkle root: {verification.merkle_root}")
        if self.comparisons:
            say()
            say("  DECLARED BUT NOT EXECUTED HERE")
            say("  A reconciliation is a comparison specification, executed by the")
            say("  matching engine rather than as one SQL control. It is declared,")
            say("  stored and visible — and this study does not claim its findings.")
            for spec in self.comparisons:
                say(f"    ≈ {spec['kind']}: {spec['left']} against {spec['right']}")

    async def stop(self) -> None:
        await self.database.stop()

    # -- the console -------------------------------------------------------

    def serve(self, port: int = 8800) -> None:
        """Run the console so the reader can look at all of it."""
        try:
            import uvicorn
        except ImportError:
            say("\n  uvicorn is not installed; the console cannot start.")
            say("  Install it:  pip install 'prama[serve]'")
            return

        from prama.api import create_app

        stage(6, "Look at it", "The console reads the same ledger the run just wrote.")
        say(f"  http://127.0.0.1:{port}/estate        the estate, as declared")
        say(f"  http://127.0.0.1:{port}/controls      what is running, and what is silenced")
        say(f"  http://127.0.0.1:{port}/incidents     what is currently wrong")
        say(f"  http://127.0.0.1:{port}/scorecards    the numbers, decomposed")
        say(f"  http://127.0.0.1:{port}/evidence      the ledger, and whether it verifies")
        say(f"  http://127.0.0.1:{port}/reports       the packs that leave the building")
        say()
        say("  Ctrl-C to stop.")
        uvicorn.run(create_app(self.config), host="127.0.0.1", port=port, log_level="warning")


def banner(title: str, subtitle: str) -> None:
    say()
    say("═" * 78)
    say(f"  {title}")
    say(f"  {subtitle}")
    say("═" * 78)


def require_workspace(argv: list[str], default: Path) -> Path:
    return Path(argv[1]).resolve() if len(argv) > 1 else default


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
