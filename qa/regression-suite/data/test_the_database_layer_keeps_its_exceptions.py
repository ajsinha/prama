"""Nothing above `prama.db` is handed a SQLAlchemy or stdlib exception.

QA round 4, `DB-065` and `DB-086`. Two holes in the same wall, both found by
asking not *what does this catch* but *what can actually arrive here*.

`CLAUDE.md`: *"Only `src/prama/db/**` may import `sqlalchemy`. Everything else
talks to DAOs through the unit of work."* `tests/architecture/test_layering.py`
enforces that by scanning imports — and **an import scan cannot see what a
function raises.** Every defect in this file passed that scan.

`DB-065`. `EngineFactory` caught `SQLAlchemyError` around `create_engine`. A
driver that is not installed raises `ModuleNotFoundError`, which is an
`ImportError` and not a `SQLAlchemyError`, so it escaped. The sting is that
`_creation_error`'s remedy already carries `dialect.driver_hint` — *the exact
sentence naming the package to install* — and the one failure that hint exists
for was the one that never reached it. The help was written, and the branch that
could show it did not run. (`CFG-062` was the same shape in the config loader:
`except OSError` around a `UnicodeDecodeError`, with a remedy already saying
"UTF-8 is expected".)

`DB-086`. `close()` set `self._closed` and nothing ever read it. Using a unit of
work after its `async with` block produced SQLAlchemy's own wording about
instances not bound to a session — which sends the reader to look at the
database, when the cause is that a value was read outside the block that made
it.

**What a careless version of this test would assert.** That something raises.
Both sites raised before the repair, loudly. The assertions are on the *type*,
on the remedy carrying the hint that already existed, and — for the closed unit
of work — on one guard at `_dao`, the chokepoint every one of the twenty-odd DAO
properties already passes through, rather than twenty copies of the same check.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.core.errors import DatabaseError
from prama.db import Database


def test_a_missing_driver_is_a_databaseerror_carrying_the_install_hint() -> None:
    """`DB-065`. `mysql+aiomysql` is a driver this project does not ship."""
    from prama.db.engine import EngineFactory

    factory = EngineFactory.__new__(EngineFactory)

    class _Dialect:
        name = "mysql"
        driver_hint = "Install the driver with `pip install prama[mysql]`."

        def prepare_filesystem(self) -> None: ...

        def sync_url(self):
            from sqlalchemy import make_url

            return make_url("mysql+aiomysql://user:secret@host/db")

        def engine_kwargs(self, is_async: bool) -> dict:  # noqa: ARG002
            # The name is load-bearing: `EngineFactory` passes it by keyword.
            # Renaming it to silence the unused-argument lint made this test
            # fail with a TypeError that looked exactly like a real defect.
            return {}

    factory._sync = None
    factory._dialect = _Dialect()  # type: ignore[assignment]

    with pytest.raises(BaseException) as caught:
        factory.sync_engine()

    raised = type(caught.value)
    assert issubclass(raised, DatabaseError), (
        f"a missing driver raised {raised.__module__}.{raised.__name__} rather than "
        "DatabaseError. ModuleNotFoundError is an ImportError, not a SQLAlchemyError, "
        "so `except SQLAlchemyError` never saw it."
    )
    assert "pip install" in (caught.value.remedy or ""), (
        "the refusal does not carry driver_hint — which is the one sentence that "
        f"tells the reader what to do: {caught.value.remedy!r}"
    )
    assert "secret" not in str(caught.value), "the password is in the error text"


async def test_a_closed_unit_of_work_refuses_in_our_own_words(estate: Database) -> None:
    """`DB-086`. The flag was set on close and never read."""
    async with estate.unit_of_work() as uow:
        pass

    with pytest.raises(BaseException) as caught:
        _ = uow.domains

    raised = type(caught.value)
    assert issubclass(raised, DatabaseError), (
        f"using a closed unit of work raised {raised.__module__}.{raised.__name__}; "
        "a caller above prama.db is reading SQLAlchemy's wording"
    )
    assert "closed" in str(caught.value).lower()
    assert caught.value.remedy


async def test_the_transaction_boundary_refuses_too(estate: Database) -> None:
    """`flush`, `commit` and `rollback` are reachable without touching a DAO.

    Guarding only `_dao` would leave the three methods most likely to be called
    on a stale handle — by a caller trying to "just save it" after the fact —
    still reporting in SQLAlchemy's voice.
    """
    async with estate.unit_of_work() as uow:
        pass

    for call in (uow.flush, uow.commit, uow.rollback):
        with pytest.raises(DatabaseError, match="closed"):
            await call()


async def test_an_open_unit_of_work_is_untouched(
    estate: Database, two_tenants: tuple[str, str]
) -> None:
    """The counterfactual to the refusal.

    The guard sits at `_dao`, which every DAO property and every flush passes
    through. A check written slightly wrong there does not break one call site,
    it breaks all of them — so the control is that ordinary work still works.
    """
    ours, _ = two_tenants

    async with estate.unit_of_work() as uow:
        entity, version = await uow.domains.create(
            tenant_id=ours, name="settlement", description="where money moves"
        )
        await uow.flush()
        assert uow.domains is uow.domains, "the DAO cache no longer returns one instance"
        await uow.commit()

    assert version.version == 1
    assert str(entity.id)
