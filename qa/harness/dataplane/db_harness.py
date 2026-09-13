"""Reusable real-database harness for execute/run.py cases, mirroring
tests/conftest.py + tests/execute/test_control_run.py's fixtures without pytest."""
import asyncio, tempfile, os
from pathlib import Path
from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.db import Database

REPO_ROOT = Path("/home/ashutosh/PycharmProjects/prama")

def new_database():
    tmpdir = tempfile.mkdtemp()
    config = (
        ConfigurationBuilder()
        .with_defaults(DEFAULTS)
        .with_mapping(
            {
                "database": {
                    "dialect": "sqlite",
                    "sqlite": {"path": str(Path(tmpdir) / "prama-test.db")},
                    "schema_dir": str(REPO_ROOT / "schema"),
                    "verify_on_start": True,
                },
                "security": {"session_secret": "test-only-not-a-secret", "cookies_https_only": False},
            },
            name="test",
        )
        .build()
    )
    database = Database.from_config(config)
    database.initialise(applied_by="qa-harness")
    return database

async def start(database):
    await database.start()

async def stop(database):
    await database.stop()

async def make_tenant(database):
    async with database.unit_of_work() as uow:
        tenant = uow.tenants.create(slug=f"acme-{id(database)}", display_name="Acme Bank")
        await uow.flush()
        return str(tenant.id)

def rows_for(**metrics):
    def execute(_query):
        return [dict(metrics)]
    return execute

def rows_seq(rows):
    def execute(_query):
        return list(rows)
    return execute

def exploding(message="the warehouse refused the query"):
    def execute(_query):
        raise RuntimeError(message)
    return execute

async def declare(database, tenant_id, pql, *, identity="i1", active=True, schedule=None):
    async with database.unit_of_work() as uow:
        kwargs = dict(tenant_id=tenant_id, identity=identity, pql=pql, criticality=1)
        if schedule is not None:
            kwargs["schedule"] = schedule
        control, _ = await uow.controls.declare(**kwargs)
        if active:
            await uow.controls.activate(str(control.id), tenant_id=tenant_id, approved_by="alice")
        return str(control.id)

CLEAN = (
    "CHECK positions_eod.notional IS NOT NULL "
    "SEVERITY critical DIMENSION completeness BECAUSE 'CDE for FRTB'"
)
UNIQUE = (
    "CHECK positions_eod HAS UNIQUE KEY (account_id, instrument_id) "
    "SEVERITY critical DIMENSION uniqueness BECAUSE 'declared grain'"
)
SCREENED = (
    "CHECK positions_eod.lei IS VALID 'lei' SEVERITY major DIMENSION validity BECAUSE 'ISO 17442'"
)
SEGMENTED = (
    "CHECK positions_eod.notional IS NOT NULL FOR EACH region "
    "SEVERITY critical DIMENSION completeness BECAUSE 'per-region completeness'"
)
