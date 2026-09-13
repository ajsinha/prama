import asyncio
import io
import tempfile
import traceback
from pathlib import Path

from prama.cli.base import EXIT_DRIFT, EXIT_OK, Application
from prama.cli.commands import all_commands
from prama.core import pjson
from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.db import Database
from prama.semantic.relationships import (
    MatchKey,
    RelationshipDeclaration,
    RelationshipKind,
    Tolerance,
)
from prama.semantic.services import DatasetService, RelationshipService
from prama.semantic.services.graph import ConceptService, ConnectionService, JourneyService
from prama.semantic.values import Grain

REPO_ROOT = Path("/home/ashutosh/PycharmProjects/prama")

results = {}


def record(case_id, ok, observed):
    if ok is None:
        status = "BLOCKED"
    else:
        status = "PASS" if ok else "FAIL"
    results[case_id] = (status, observed)
    print(f"{case_id}: {status} :: {observed}")


def make_config(tmp_dir: Path):
    return (
        ConfigurationBuilder()
        .with_defaults(DEFAULTS)
        .with_mapping(
            {
                "database": {
                    "dialect": "sqlite",
                    "sqlite": {"path": str(tmp_dir / "prama-test.db")},
                    "schema_dir": str(REPO_ROOT / "schema"),
                    "verify_on_start": True,
                },
                "security": {
                    "session_secret": "test-only-not-a-secret",
                    "cookies_https_only": False,
                },
            },
            name="test",
        )
        .build()
    )


async def new_db(tmp_dir):
    config = make_config(tmp_dir)
    database = Database.from_config(config)
    database.initialise(applied_by="qa")
    await database.start()
    return database, config


async def make_tenant(database, slug="acme"):
    async with database.unit_of_work() as uow:
        tenant = uow.tenants.create(slug=slug, display_name=slug)
        await uow.flush()
        return str(tenant.id)


async def run_cli(argv):
    def invoke():
        out = io.StringIO()
        return Application(all_commands()).run(argv, out=out), out.getvalue()

    return await asyncio.to_thread(invoke)


def write_config_file(tmp_dir: Path, database: Database) -> Path:
    config_path = tmp_dir / "application.yaml"
    config_path.write_text(
        "database:\n"
        "  dialect: sqlite\n"
        f"  sqlite:\n    path: {database.settings.sqlite.path}\n"
        f"  schema_dir: {database.settings.schema_dir}\n"
    )
    return config_path


async def main():
    tmp_dir = Path(tempfile.mkdtemp())
    database, config = await new_db(tmp_dir)
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            sub, _ = await dsvc.declare(
                tenant_id=tenant,
                name="Sub-ledger",
                owner_id="fin-ops",
                grain=Grain(("account_code", "accounting_date")),
            )
            gl, _ = await dsvc.declare(tenant_id=tenant, name="General Ledger")
            await RelationshipService(uow).declare(
                tenant_id=tenant,
                declaration=RelationshipDeclaration(
                    kind=RelationshipKind.RECONCILES_WITH,
                    from_dataset_id=str(sub.id),
                    to_dataset_id=str(gl.id),
                    match_keys=(MatchKey("account_code"),),
                    compare=("amount",),
                    tolerance=Tolerance(absolute=1.0, currency="EUR"),
                ),
            )
            jsvc = JourneyService(uow)
            await jsvc.declare(
                tenant_id=tenant,
                name="Reconciliation Journey",
                steps=[{"kind": "dataset", "dataset_id": str(sub.id)}],
            )
            csvc = ConnectionService(uow)
            await csvc.configure(tenant_id=tenant, name="A Connection", source_type="filesystem")
            concsvc = ConceptService(uow)
            concept, _ = await concsvc.declare_concept(tenant_id=tenant, name="A Concept")
            await concsvc.declare_property(
                tenant_id=tenant, concept_id=str(concept.id), name="A Property"
            )
            domain, _ = await uow.domains.create(tenant_id=tenant, name="Domain One")

        config_file = write_config_file(tmp_dir, database)

        # ---------- SEM-255, SEM-256, SEM-257 ----------
        out_dir = tmp_dir / "estate_export"
        code, text = await run_cli(
            [
                "--config",
                str(config_file),
                "estate",
                "export",
                "--tenant",
                tenant,
                "--out",
                str(out_dir),
            ]
        )
        all_files = sorted(p.relative_to(out_dir) for p in out_dir.rglob("*.yaml"))
        all_files_str = [str(p) for p in all_files]
        has_datasets = any("datasets" in f for f in all_files_str)
        has_relationships = any("relationships" in f for f in all_files_str)
        has_journeys = any("journeys" in f for f in all_files_str)
        has_connections = any("connections" in f for f in all_files_str)
        has_concepts = any("concepts" in f for f in all_files_str)
        has_domains = any("domains" in f for f in all_files_str)
        ok255 = (
            code == EXIT_OK
            and has_datasets
            and has_relationships
            and has_journeys
            and has_connections
            and not has_concepts
            and not has_domains
        )
        record(
            "SEM-255",
            ok255,
            f"exit={code}; files={all_files_str}; has_concepts={has_concepts} "
            f"(expect False); has_domains={has_domains} (expect False)",
        )

        # SEM-256: exported paths do not use domain layout, even though sub is
        # not domain-scoped here. Add a domain-scoped dataset and re-export.
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            domain_scoped, _ = await dsvc.declare(
                tenant_id=tenant, name="Domain Scoped DS", domain_id=str(domain.id)
            )
        out_dir2 = tmp_dir / "estate_export2"
        code2, _ = await run_cli(
            [
                "--config",
                str(config_file),
                "estate",
                "export",
                "--tenant",
                tenant,
                "--out",
                str(out_dir2),
            ]
        )
        all_files2 = sorted(str(p.relative_to(out_dir2)) for p in out_dir2.rglob("*.yaml"))
        domain_scoped_path_exists = (out_dir2 / "datasets" / "domain_scoped_ds.yaml").is_file()
        no_domains_subfolder = not any(f.startswith("domains/") for f in all_files2)
        ok256 = code2 == EXIT_OK and domain_scoped_path_exists and no_domains_subfolder
        record(
            "SEM-256",
            ok256,
            f"exit={code2}; files={all_files2}; domain-scoped dataset landed flat at "
            f"datasets/domain_scoped_ds.yaml={domain_scoped_path_exists}; no domains/ "
            f"subfolder used={no_domains_subfolder}",
        )

        # SEM-257: relationship file naming
        rel_files = sorted((out_dir / "relationships").glob("*.yaml"))
        rel_name_1 = rel_files[0].stem if rel_files else None
        code3, _ = await run_cli(
            [
                "--config",
                str(config_file),
                "estate",
                "export",
                "--tenant",
                tenant,
                "--out",
                str(tmp_dir / "estate_export3"),
            ]
        )
        rel_files_2 = sorted((tmp_dir / "estate_export3" / "relationships").glob("*.yaml"))
        rel_name_2 = rel_files_2[0].stem if rel_files_2 else None
        stable_within_install = rel_name_1 == rel_name_2
        record(
            "SEM-257",
            stable_within_install and rel_name_1 is not None,
            f"first export relationship filename={rel_name_1!r}; second export (same "
            f"install, same relationship id)={rel_name_2!r}; stable={stable_within_install} "
            f"-- re-minted ULIDs after a restore were not simulated (would require a fresh "
            f"install importing the same logical relationship under a new id, which this "
            f"CLI has no import path to produce)",
        )

        # ---------- SEM-258 ----------
        dry_run_dir = tmp_dir / "estate_dry_run"
        code4, text4 = await run_cli(
            [
                "--config",
                str(config_file),
                "estate",
                "export",
                "--tenant",
                tenant,
                "--out",
                str(dry_run_dir),
                "--dry-run",
            ]
        )
        ok258 = code4 == EXIT_OK and "would write" in text4 and not dry_run_dir.exists()
        record(
            "SEM-258",
            ok258,
            f"exit={code4}; 'would write' in output={('would write' in text4)}; "
            f"directory exists after dry-run={dry_run_dir.exists()}",
        )

        # ---------- SEM-254 ----------
        # Use a freshly (re-)exported directory that reflects the *current*
        # live store, so it starts genuinely in sync regardless of dataset
        # declarations made earlier for other cases (e.g. SEM-256's).
        out_dir_254 = tmp_dir / "estate_export_254"
        await run_cli(
            [
                "--config",
                str(config_file),
                "estate",
                "export",
                "--tenant",
                tenant,
                "--out",
                str(out_dir_254),
            ]
        )
        code5, text5 = await run_cli(
            [
                "--config",
                str(config_file),
                "estate",
                "diff",
                "--tenant",
                tenant,
                "--dir",
                str(out_dir_254),
            ]
        )
        ok_in_sync = code5 == EXIT_OK and "in sync" in text5

        edit_path = out_dir_254 / "datasets" / "sub_ledger.yaml"
        edit_text = edit_path.read_text()
        edit_path.write_text(edit_text.replace("criticality: 4", "criticality: 1"))
        code6, text6 = await run_cli(
            [
                "--config",
                str(config_file),
                "estate",
                "diff",
                "--tenant",
                tenant,
                "--dir",
                str(out_dir_254),
            ]
        )
        ok_drift_exit = code6 == EXIT_DRIFT

        code7, text7 = await run_cli(
            [
                "--config",
                str(config_file),
                "--json",
                "estate",
                "diff",
                "--tenant",
                tenant,
                "--dir",
                str(out_dir_254),
            ]
        )
        # restore edit for a fresh json-in-sync check
        edit_path.write_text(edit_text)
        code8, text8 = await run_cli(
            [
                "--config",
                str(config_file),
                "--json",
                "estate",
                "diff",
                "--tenant",
                tenant,
                "--dir",
                str(out_dir_254),
            ]
        )
        json_drift = pjson.loads(text7)
        json_ok = pjson.loads(text8)
        ok254 = (
            ok_in_sync
            and ok_drift_exit
            and code7 == EXIT_DRIFT
            and json_drift["in_sync"] is False
            and isinstance(json_drift["drifts"], list)
            and code8 == EXIT_OK
            and json_ok["in_sync"] is True
        )
        record(
            "SEM-254",
            ok254,
            f"fresh export in-sync exit={code5} ('in sync' in text={ok_in_sync}); after edit "
            f"exit={code6} (expect EXIT_DRIFT={EXIT_DRIFT}); json drift exit={code7} "
            f"in_sync={json_drift.get('in_sync')} drifts_count={len(json_drift.get('drifts', []))}; "
            f"json in-sync exit={code8} in_sync={json_ok.get('in_sync')}",
        )

        # ---------- SEM-259 ----------
        import prama.cli.estate as estate_cli_module

        has_apply_command = hasattr(estate_cli_module, "EstateApplyCommand")
        commands_offered = [c.name for c in estate_cli_module.EstateCommand().commands()]
        module_doc = estate_cli_module.__doc__ or ""
        doc_confirms_absence = "approval workflow" in module_doc and "apply" in module_doc.lower()
        ok259 = (not has_apply_command) and ("apply" not in commands_offered) and doc_confirms_absence
        record(
            "SEM-259",
            ok259,
            f"commands offered by EstateCommand={commands_offered}; "
            f"EstateApplyCommand class exists={has_apply_command}; module docstring "
            f"documents the deliberate absence={doc_confirms_absence}",
        )

        # ---------- SEM-260 ----------
        # Documentation-only claim about re-applying a file; there is no apply
        # code path to exercise (confirmed absent by SEM-259), so this cannot
        # be executed -- only the module docstring's text can be inspected.
        doc_text = estate_cli_module.__doc__ or ""
        gitops_doc = __import__("prama.semantic.gitops", fromlist=["x"]).__doc__ or ""
        claim_present = "amendment" in gitops_doc and "rewriting the past" in gitops_doc
        record(
            "SEM-260",
            None,
            f"BLOCKED: no apply/re-apply code path exists anywhere in the codebase to "
            f"execute (confirmed by SEM-259 -- there is no CLI apply command and no "
            f"other entry point that writes a GitOps file back into the store); the "
            f"module docstring's claim is documentation only (claim text present="
            f"{claim_present}), so the case cannot be run against real behaviour, only "
            f"read as documentation",
        )

        # ---------- SEM-261 ----------
        # Two-sided disagreement on the *same field*: simulate with the diff
        # command by editing the exported file differently from a subsequent
        # in-store amendment on the same field, then diffing.
        out_dir_conflict = tmp_dir / "estate_conflict"
        code_c1, _ = await run_cli(
            [
                "--config",
                str(config_file),
                "estate",
                "export",
                "--tenant",
                tenant,
                "--out",
                str(out_dir_conflict),
            ]
        )
        conflict_path = out_dir_conflict / "datasets" / "sub_ledger.yaml"
        conflict_text = conflict_path.read_text()
        conflict_path.write_text(conflict_text.replace("owner: fin-ops", "owner: git-editor"))
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            await dsvc.amend(
                tenant_id=tenant,
                dataset_id=str(sub.id),
                reason="ownership changed in the UI",
                owner_id="ui-editor",
            )
        code_c2, text_c2 = await run_cli(
            [
                "--config",
                str(config_file),
                "estate",
                "diff",
                "--tenant",
                tenant,
                "--dir",
                str(out_dir_conflict),
            ]
        )
        ok261 = (
            code_c2 == EXIT_DRIFT
            and "owner" in text_c2
            and "declared differently" in text_c2
            and "resolved" not in text_c2
        )
        record(
            "SEM-261",
            ok261,
            f"exit={code_c2}; 'owner' named={('owner' in text_c2)}; "
            f"'declared differently' present={('declared differently' in text_c2)}; "
            f"'resolved' absent={('resolved' not in text_c2)}; output={text_c2!r}",
        )
    except Exception:
        for missing in (
            "SEM-254",
            "SEM-255",
            "SEM-256",
            "SEM-257",
            "SEM-258",
            "SEM-259",
            "SEM-260",
            "SEM-261",
        ):
            if missing not in results:
                record(missing, False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    print("\n\n==== SUMMARY PART 2 ====")
    for k, v in results.items():
        r, o = v
        print(f"{k}\t{r}\t{o}")


asyncio.run(main())
