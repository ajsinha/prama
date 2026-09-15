"""A violated constraint in a versioned DAO refuses in the taxonomy.

QA round 4, `DB-179`. `VersionedDao.create`, `.amend` and `.correct` called
`self._session.flush()` directly. `UnitOfWork._guarded` — the thing that turns
SQLAlchemy's failures into the Prama taxonomy — was therefore not in the path,
and a violated constraint reached the caller as
`sqlalchemy.exc.IntegrityError: (sqlite3.IntegrityError) UNIQUE constraint
failed: ctl_control.tenant_id, ctl_control.identity`.

`CLAUDE.md` is unambiguous that this is a defect in its own right: *"Only
`src/prama/db/**` may import `sqlalchemy`. Everything else talks to DAOs through
the unit of work."* `tests/architecture/test_layering.py` enforces that by
import scanning — and **an import scan cannot see what a function raises**. The
rule held for every line of code and failed on the exception.

The difference is not cosmetic. A duplicate identity is *recoverable*: read the
existing control and amend it, which is exactly what `ControlDao.declare` does
and what `ConflictError`'s remedy says. The raw error names an index the caller
has never heard of, carries no remedy, and reads like corruption.

**The triage was wrong about how to reach it, which is why this docstring says
so.** It described the losing side of a concurrent amendment. That race does not
occur on SQLite — writers serialise, so the second session reads the winner's
committed row and amends forward from it; the staged version of this test
reproduced nothing. The reachable path needs no concurrency at all:
`uq_ctl_control_identity` is violated by two `create` calls in **one** session,
deterministically, on every engine. A defect that is real and a story about how
it happens that is wrong are separable, and only the first one belongs in a test.

**What a careless version of this test would assert.** `pytest.raises(Exception)`
— satisfied by the raw `IntegrityError` this file exists to eliminate. The
assertion is on the *type* of the refusal, and the control underneath is that
uncontended writes still succeed, so the repair cannot be satisfied by refusing
everything.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.errors import ConflictError
from prama.db import Database


async def test_a_duplicate_identity_is_a_conflict_not_an_integrityerror(
    estate: Database, two_tenants: tuple[str, str]
) -> None:
    ours, _ = two_tenants

    # BaseException, deliberately: the point is which type arrives, and naming a
    # narrower one here would make the test pass by catching only the right answer.
    with pytest.raises(BaseException) as caught:
        async with estate.unit_of_work() as uow:
            await uow.controls.create(
                tenant_id=ours, identity_fields={"identity": "isin-not-null"}, pql="x"
            )
            await uow.flush()
            await uow.controls.create(
                tenant_id=ours, identity_fields={"identity": "isin-not-null"}, pql="y"
            )
            await uow.flush()

    raised = type(caught.value)
    assert issubclass(raised, ConflictError), (
        f"a duplicate control identity raised {raised.__module__}.{raised.__name__} "
        "instead of ConflictError. A caller above prama.db is holding a SQLAlchemy "
        "exception, which the layering rule forbids — and the import scan that "
        "enforces that rule cannot see an exception travelling up the stack."
    )
    assert caught.value.remedy, (
        "a duplicate identity is recoverable by amending what is already there, "
        "and the refusal does not say so"
    )
    assert "identity" in str(caught.value), (
        f"the refusal does not carry the driver's detail, so the caller cannot "
        f"tell which constraint they violated: {caught.value}"
    )


def test_the_guard_is_shared_with_the_unit_of_work_not_copied() -> None:
    """Asserted on the wiring, because agreeing today is not the property.

    Two translations of the same failure is the restatement `CLAUDE.md` warns
    about — *"anything restated in a second place will drift, silently, in the
    flattering direction"*. The DAO and the unit of work must reach one
    implementation, so a remedy improved in one place cannot be missing in the
    other. (An earlier draft of the extraction dropped the `DatabaseError`
    remedy while copying; mypy caught it, which is luck, not design.)
    """
    import inspect

    from prama.db import guard, session
    from prama.db.dao import base

    assert "guard" in inspect.getsource(base.Dao._guarded_flush)
    assert "guard" in inspect.getsource(session.UnitOfWork._guarded)
    assert "IntegrityError" in inspect.getsource(guard.guarded)


async def test_ordinary_declarations_still_write(
    estate: Database, two_tenants: tuple[str, str]
) -> None:
    """The counterfactual to the refusal.

    Routing every flush in `VersionedDao` through the guard touches `create`,
    `amend` and `correct` alike — thirteen call sites. A guard that translated
    *successful* flushes into refusals would satisfy the test above and make the
    semantic layer unwritable.
    """
    ours, _ = two_tenants

    async with estate.unit_of_work() as uow:
        entity, first = await uow.domains.create(
            tenant_id=ours, name="settlement", description="where money moves"
        )
        await uow.flush()
        amended = await uow.domains.amend(
            str(entity.id), tenant_id=ours, description="clearing and settlement"
        )
        await uow.commit()

    assert first.version == 1
    assert amended.version == 2
    assert amended.description == "clearing and settlement"


async def test_one_current_version_survives_an_amendment(
    estate: Database, two_tenants: tuple[str, str]
) -> None:
    """The property the partial unique index exists for, which never broke.

    The repair is to an error path, and a repair to an error path is exactly the
    kind that can quietly change what the data does. `uq_sem_domain_current`
    permits one current row per entity; that must remain true.
    """
    ours, _ = two_tenants

    async with estate.unit_of_work() as uow:
        entity, _ = await uow.domains.create(tenant_id=ours, name="settlement", description="a")
        await uow.flush()
        await uow.domains.amend(str(entity.id), tenant_id=ours, description="b")
        await uow.commit()
        domain_id = str(entity.id)

    async with estate.unit_of_work() as uow:
        history = await uow.domains.history(domain_id, tenant_id=ours)

    current = [version for version in history if version.valid_to is None]
    assert len(current) == 1, f"{len(current)} current versions after one amendment"
    assert current[0].description == "b"
