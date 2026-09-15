"""One translation from SQLAlchemy's failures into the Prama taxonomy.

`UnitOfWork._guarded` did this, and the versioned DAOs called
`self._session.flush()` directly — so the losing side of a genuine concurrent
amendment got a raw `sqlite3.IntegrityError` instead of the documented
`ConflictError`. The data was fine, only one current row survived; the *error*
was not translated, and `tests/architecture/test_layering.py` says nothing above
`prama.db` ever sees SQLAlchemy. QA round 4, `DB-179`.

Extracted here rather than copied into the DAO, because a second copy of a
translation is the thing `CLAUDE.md` warns will drift: *"anything restated in a
second place will drift, silently, in the flattering direction."* One function,
two callers.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from prama.core.errors import ConflictError, DatabaseError


def first_line(exc: BaseException) -> str:
    """The driver's own first line, which is the part that names the constraint.

    Truncated, because a driver that decides to include the whole statement and
    all its bound parameters turns a refusal into a wall — and `context` is read
    in a log line and an error page, both of which have a width.
    """
    text = str(exc).strip()
    return text.splitlines()[0][:400] if text else exc.__class__.__name__


async def guarded(session: AsyncSession, operation: Any) -> None:
    """Run *operation*, translating SQLAlchemy's failures and rolling back.

    A violated unique or foreign key is a `ConflictError` — somebody else got
    there first, and the caller can re-read and retry. Anything else from the
    driver is a `DatabaseError`: not the caller's to fix, and not theirs to see
    a stack trace about.
    """
    try:
        await operation()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(
            "the change conflicts with data already present",
            remedy=(
                "A unique key or foreign key was violated. Re-read the current state "
                "and retry, or correct the input."
            ),
            context={"detail": first_line(exc)},
            cause=exc,
        ) from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        raise DatabaseError(
            "the database rejected the transaction",
            code="DB.TRANSACTION_FAILED",
            remedy="Inspect the detail below; the transaction has been rolled back.",
            context={"detail": first_line(exc)},
            cause=exc,
        ) from exc
