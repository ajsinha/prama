"""The asynchronous PostgreSQL engine must be constructible.

QA round 2, `DB-070`, `DB-072`, `DB-148`, `DB-279`. One root cause behind all
four: `PostgresDialect.engine_kwargs` sets `poolclass=QueuePool`, and then sets
it *again* inside the `is_async` branch — the one place it must not. SQLAlchemy
refuses outright: "Pool class QueuePool cannot be used with asyncio engine".

PostgreSQL is one of two supported dialects and async is the path the web and
API use, so this is not a corner. The SQLite dialect gets it right three lines
earlier — `NullPool if is_async else QueuePool` — so the pattern was known and
simply not applied.

Nothing in the suite caught it: `tests/conftest.py` defines `postgres_config`
and nothing references it, and no test anywhere constructs an async engine. A
dialect with no coverage on its asynchronous path did not work on it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import QueuePool

from prama.db.dialects import dialect_for
from prama.db.settings import DbSettings


@pytest.fixture
def postgres_dialect():
    return dialect_for(DbSettings(dialect="postgres"))


def test_the_async_pool_is_not_the_synchronous_one(postgres_dialect) -> None:
    """Stated as a property rather than a name.

    Asserting `poolclass is AsyncAdaptedQueuePool` would pin one valid answer
    and reject the others — NullPool is equally correct for asyncio. What must
    be true is that it is not the synchronous pool, which is the thing
    SQLAlchemy refuses.
    """
    assert postgres_dialect.engine_kwargs(is_async=True).get("poolclass") is not QueuePool


def test_the_synchronous_engine_still_uses_a_real_pool(postgres_dialect) -> None:
    """The counterfactual.

    Setting NullPool everywhere would pass the test above and quietly remove
    connection pooling from the synchronous DDL path, which is a performance
    defect wearing a correctness fix's clothes.
    """
    assert postgres_dialect.engine_kwargs(is_async=False).get("poolclass") is QueuePool


def test_an_async_engine_can_actually_be_constructed(postgres_dialect) -> None:
    """The assertion that matters: SQLAlchemy accepts these arguments.

    No server is needed — the refusal was at construction, before any
    connection was attempted.
    """
    engine = create_async_engine(
        "postgresql+asyncpg://prama:prama@127.0.0.1:55432/prama",
        **postgres_dialect.engine_kwargs(is_async=True),
    )
    assert engine is not None


class TestTheConnectionOptionsSurviveTranslation:
    """The async path translates libpq options for asyncpg, and lost two.

    Both are the same shape as the pool defect above: a value that was
    configured, carried most of the way, and quietly dropped or mangled at the
    point where the two drivers differ.
    """

    def test_a_configured_timeout_never_becomes_unlimited(self) -> None:
        """`0` means *unlimited* in PostgreSQL, so rounding must not reach it.

        `int(0.0005 * 1000)` is `0`, so `statement_timeout: 500us` asked for
        half a millisecond and configured no limit at all — the opposite of
        the request, in the direction that hides a runaway query rather than
        stopping it.
        """
        from prama.db.dialects import _statement_timeout_ms

        assert _statement_timeout_ms(0.0005) >= 1
        assert _statement_timeout_ms(0.4999) >= 1
        # Asking for no limit still gets no limit — the fix must not make
        # "unlimited" unreachable.
        assert _statement_timeout_ms(0) == 0
        # And ordinary values are unchanged.
        assert _statement_timeout_ms(60) == 60_000

    @pytest.mark.parametrize("mode", ["require", "verify-ca", "verify-full"])
    def test_a_mode_that_demands_tls_is_passed_to_asyncpg(self, mode: str) -> None:
        """asyncpg does not read `sslmode`, and its default connects without TLS.

        The old comment said asyncpg "does not understand sslmode; the driver
        negotiates TLS itself". True of the keyword, not of the requirement:
        `require` asks for a connection that fails rather than falls back to
        plaintext. An operator who asked for TLS got it on the synchronous
        path and not on the asynchronous one.
        """
        import dataclasses

        settings = DbSettings(dialect="postgres")
        settings = dataclasses.replace(
            settings, postgres=dataclasses.replace(settings.postgres, sslmode=mode)
        )
        connect = dialect_for(settings).engine_kwargs(is_async=True)["connect_args"]
        assert connect.get("ssl") == mode

    @pytest.mark.parametrize("mode", ["disable", "allow", "prefer"])
    def test_a_permissive_mode_is_left_to_the_driver(self, mode: str) -> None:
        """The counterfactual.

        Passing `ssl=` for every mode would force TLS on deployments that
        asked not to have it — a fix that breaks the configuration it was
        meant to honour. These three are asyncpg's own default behaviour, so
        nothing is passed.
        """
        import dataclasses

        settings = DbSettings(dialect="postgres")
        settings = dataclasses.replace(
            settings, postgres=dataclasses.replace(settings.postgres, sslmode=mode)
        )
        connect = dialect_for(settings).engine_kwargs(is_async=True)["connect_args"]
        assert "ssl" not in connect


# ---------------------------------------------------------------------------
# Against a real server
# ---------------------------------------------------------------------------


def _dsn() -> str | None:
    """A reachable PostgreSQL, or None.

    Read from the environment so this is opt-in, and probed rather than
    assumed: a test that fails because nobody started a database teaches people
    to ignore it.
    """
    import os
    import socket
    from urllib.parse import urlparse

    dsn = os.environ.get("PRAMA_TEST_POSTGRES_DSN")
    if not dsn:
        return None
    # The convention in this repository is a plain libpq DSN — the rest of the
    # suite passes it straight to psycopg. The asyncpg driver is selected here
    # rather than demanded of the caller, so one environment variable serves
    # both and nobody has to remember which spelling this test wanted.
    if "+" not in dsn.split("://", 1)[0]:
        dsn = dsn.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
            "postgres://", "postgresql+asyncpg://", 1
        )
    parsed = urlparse(dsn)
    probe = socket.socket()
    probe.settimeout(1)
    try:
        probe.connect((parsed.hostname or "127.0.0.1", parsed.port or 5432))
    except OSError:
        return None
    finally:
        probe.close()
    return dsn


@pytest.mark.postgres
async def test_the_async_engine_connects_and_applies_its_settings() -> None:
    """The whole point, against a real server.

    Construction was the failure, so construction is most of the fix — but a
    pool class that constructs and then cannot check out a connection would
    pass every test above. This one connects, and confirms the server actually
    received the statement_timeout the dialect claims to send.

    Marked `postgres` and skipped without a server. That marker previously
    matched nothing at all: it was declared in pyproject, `postgres_config`
    was declared in conftest, and no test used either — which is precisely how
    a dialect came to be unable to open a connection with nobody noticing.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    dsn = _dsn()
    if dsn is None:
        pytest.skip("set PRAMA_TEST_POSTGRES_DSN to a reachable server")

    dialect = dialect_for(DbSettings(dialect="postgres"))
    engine = create_async_engine(dsn, **dialect.engine_kwargs(is_async=True))
    try:
        async with engine.connect() as connection:
            assert (await connection.execute(text("select 1"))).scalar() == 1
            timeout = (await connection.execute(text("show statement_timeout"))).scalar()
            assert timeout not in ("0", 0), (
                "the server reports no statement timeout; a configured limit "
                "rounded down to unlimited"
            )
    finally:
        await engine.dispose()
