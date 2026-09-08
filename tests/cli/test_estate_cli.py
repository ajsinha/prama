"""The estate CLI: export, diff and maturity.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest

from prama.cli.base import EXIT_DRIFT, EXIT_OK, Application
from prama.cli.commands import all_commands
from prama.core import pjson
from prama.db import Database
from prama.semantic.relationships import (
    MatchKey,
    RelationshipDeclaration,
    RelationshipKind,
    Tolerance,
)
from prama.semantic.services import DatasetService, RelationshipService
from prama.semantic.values import Grain


async def run(argv: list[str]) -> tuple[int, str]:
    """Invoke the CLI exactly as a shell would.

    In a thread because the commands call ``asyncio.run`` themselves, and the
    test is already inside a loop. Driving the real entry point rather than the
    functions beneath it is the point: this is the code a user runs.
    """

    def invoke() -> tuple[int, str]:
        out = io.StringIO()
        return Application(all_commands()).run(argv, out=out), out.getvalue()

    return await asyncio.to_thread(invoke)


@pytest.fixture
async def populated(started_database: Database, tenant_id: str, tmp_path: Path) -> Path:
    """A small estate plus a config file pointing at the same database."""
    async with started_database.unit_of_work() as uow:
        datasets = DatasetService(uow)
        sub, _ = await datasets.declare(
            tenant_id=tenant_id,
            name="Sub-ledger",
            owner_id="fin-ops",
            grain=Grain(("account_code", "accounting_date")),
        )
        gl, _ = await datasets.declare(tenant_id=tenant_id, name="General Ledger")
        await RelationshipService(uow).declare(
            tenant_id=tenant_id,
            declaration=RelationshipDeclaration(
                kind=RelationshipKind.RECONCILES_WITH,
                from_dataset_id=str(sub.id),
                to_dataset_id=str(gl.id),
                match_keys=(MatchKey("account_code"),),
                compare=("amount",),
                tolerance=Tolerance(absolute=1.0, currency="EUR"),
            ),
        )
    config = tmp_path / "application.yaml"
    config.write_text(
        "database:\n"
        "  dialect: sqlite\n"
        f"  sqlite:\n    path: {started_database.settings.sqlite.path}\n"
        f"  schema_dir: {started_database.settings.schema_dir}\n"
    )
    return config


class TestExport:
    async def test_export_writes_the_documented_layout(
        self, populated: Path, tenant_id: str, tmp_path: Path
    ) -> None:
        out = tmp_path / "estate"
        code, _ = await run(
            [
                "--config",
                str(populated),
                "estate",
                "export",
                "--tenant",
                tenant_id,
                "--out",
                str(out),
            ]
        )
        assert code == EXIT_OK
        assert (out / "datasets" / "sub_ledger.yaml").is_file()
        assert (out / "datasets" / "general_ledger.yaml").is_file()
        assert len(list((out / "relationships").glob("*.yaml"))) == 1

    async def test_dry_run_writes_nothing(
        self, populated: Path, tenant_id: str, tmp_path: Path
    ) -> None:
        out = tmp_path / "estate"
        code, text = await run(
            [
                "--config",
                str(populated),
                "estate",
                "export",
                "--tenant",
                tenant_id,
                "--out",
                str(out),
                "--dry-run",
            ]
        )
        assert code == EXIT_OK
        assert "would write" in text
        assert not out.exists()

    async def test_exported_yaml_omits_nulls_at_every_depth(
        self, populated: Path, tenant_id: str, tmp_path: Path
    ) -> None:
        # The noise a reviewer reads past lives in the nested value objects.
        out = tmp_path / "estate"
        await run(
            [
                "--config",
                str(populated),
                "estate",
                "export",
                "--tenant",
                tenant_id,
                "--out",
                str(out),
            ]
        )
        text = next((out / "relationships").glob("*.yaml")).read_text()
        assert "null" not in text
        assert "right:" not in text  # an omitted match-key side
        assert "relative:" not in text  # an unset tolerance bound

    async def test_a_relationship_is_named_readably_not_by_its_sentence(
        self, populated: Path, tenant_id: str, tmp_path: Path
    ) -> None:
        out = tmp_path / "estate"
        await run(
            [
                "--config",
                str(populated),
                "estate",
                "export",
                "--tenant",
                tenant_id,
                "--out",
                str(out),
            ]
        )
        document = pjson.loads(
            pjson.dumps(
                __import__("yaml").safe_load(
                    next((out / "relationships").glob("*.yaml")).read_text()
                )
            )
        )
        assert document["metadata"]["name"] == "sub_ledger_reconciles_with_general_ledger"
        # The full sentence survives, where wrapping it is harmless.
        assert "these two should agree" in document["spec"]["description"]


class TestDiff:
    async def test_a_fresh_export_is_in_sync(
        self, populated: Path, tenant_id: str, tmp_path: Path
    ) -> None:
        out = tmp_path / "estate"
        await run(
            [
                "--config",
                str(populated),
                "estate",
                "export",
                "--tenant",
                tenant_id,
                "--out",
                str(out),
            ]
        )
        code, text = await run(
            ["--config", str(populated), "estate", "diff", "--tenant", tenant_id, "--dir", str(out)]
        )
        assert code == EXIT_OK
        assert "in sync" in text

    async def test_an_edit_in_git_is_reported_and_exits_non_zero(
        self, populated: Path, tenant_id: str, tmp_path: Path
    ) -> None:
        out = tmp_path / "estate"
        await run(
            [
                "--config",
                str(populated),
                "estate",
                "export",
                "--tenant",
                tenant_id,
                "--out",
                str(out),
            ]
        )
        path = out / "datasets" / "sub_ledger.yaml"
        path.write_text(path.read_text().replace("criticality: 4", "criticality: 1"))

        code, text = await run(
            ["--config", str(populated), "estate", "diff", "--tenant", tenant_id, "--dir", str(out)]
        )
        assert code == EXIT_DRIFT
        assert "criticality" in text
        # Reported, never resolved: both edits are legitimate.
        assert "declared differently" in text

    async def test_json_output_is_machine_readable(
        self, populated: Path, tenant_id: str, tmp_path: Path
    ) -> None:
        out = tmp_path / "estate"
        await run(
            [
                "--config",
                str(populated),
                "estate",
                "export",
                "--tenant",
                tenant_id,
                "--out",
                str(out),
            ]
        )
        code, text = await run(
            [
                "--config",
                str(populated),
                "--json",
                "estate",
                "diff",
                "--tenant",
                tenant_id,
                "--dir",
                str(out),
            ]
        )
        assert code == EXIT_OK
        assert pjson.loads(text)["in_sync"] is True


class TestMaturity:
    async def test_maturity_prints_its_components_and_next_actions(
        self, populated: Path, tenant_id: str
    ) -> None:
        code, text = await run(
            ["--config", str(populated), "estate", "maturity", "--tenant", tenant_id]
        )
        assert code == EXIT_OK
        assert "%" in text
        assert "weight" in text  # never a black box
        assert "controls" in text  # and always actionable

    async def test_maturity_json_carries_the_full_breakdown(
        self, populated: Path, tenant_id: str
    ) -> None:
        code, text = await run(
            ["--config", str(populated), "--json", "estate", "maturity", "--tenant", tenant_id]
        )
        body = pjson.loads(text)
        assert code == EXIT_OK
        assert set(body) >= {"score", "percent", "stage", "completion", "next_actions"}
