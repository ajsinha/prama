"""Work that processes many things survives one of them being wrong.

QA round 4: `IMP-007`, `CON-153`, `CTR-047`, `CLI-140`. Four unrelated modules,
one habit — a single malformed input aborting an operation whose whole purpose
is to handle a heterogeneous pile of inputs, or reaching the caller in a
library's voice rather than Prama's.

`IMP-007` is the one worth the most. `Collector`'s own docstring states the
contract: *"an importer built around a collector cannot forget to report a
construct it skipped, because skipping means calling `unmapped` and there is
nowhere else to put it."* And `Collector.control` let `PqlSyntaxError` escape
`parse_control` — so one carried-over expression that did not parse aborted an
entire multi-hundred-control migration. The class was built to make "report it
and keep going" the only available move, and the one method that does the
parsing had a second exit nobody noticed.

`CON-153`. `ObjectStoreConnector.health()` recognised an unusable URI scheme and
returned `MISCONFIGURED` with a clear sentence. `open()` did not look, and
`_connect` builds the scheme into DuckDB SQL, so `async with connector:` — the
idiomatic form used everywhere else — produced a DuckDB error about secret
providers. Two entry points, the same question, two answers.

`CTR-047`. `_freeze` put raw values in a set, so a nested list or object raised
`TypeError: unhashable type: 'list'`. `.jsonl` is one of the two formats
`prama contract diff` accepts, which makes a nested value ordinary input.

`CLI-140`. A file that exists, is a file, and is still not a database gave the
driver's `IOException` to a CLI user.

**What a careless version of these tests would assert.** For `IMP-007`, that the
bad control is absent from the result — true if the importer silently drops it,
which is the worse outcome. The assertion is that the good controls are *still
there* and the bad one is *reported*, which is the contract. For `CON-153`, that
`open()` raises — it did before, just in DuckDB's words; the assertion is on the
type and on `health()` and `open()` agreeing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from prama.contract.diff import compare
from prama.core.errors import PramaError, ValidationError

GOOD = "CHECK positions_eod.isin IS NOT NULL SEVERITY major DIMENSION completeness BECAUSE 'x'"
UNPARSEABLE = "CHECK positions_eod.isin >>> SEVERITY major"


# -- IMP-007: an importer reports what it could not bring across ------------


def test_one_unparseable_control_does_not_abort_the_migration() -> None:
    from prama.importers.spi import Collector

    collector = Collector("dbt")
    collector.control(GOOD)
    collector.control(UNPARSEABLE, caveat="carried over verbatim")
    collector.control(GOOD.replace("isin", "account_id"))

    result = collector.result()
    assert len(result.controls) == 2, (
        f"{len(result.controls)} controls survived an import containing one "
        "unparseable expression; before the repair the PqlSyntaxError escaped and "
        "the whole migration stopped at the bad one"
    )


def test_what_did_not_come_across_is_reported_rather_than_dropped() -> None:
    """The half that separates a repair from a swallow.

    Catching the error and returning would also make the test above pass, and
    would be strictly worse than crashing: a migration that silently loses
    controls reads as a complete one.
    """
    from prama.importers.spi import Collector

    collector = Collector("dbt")
    collector.control(UNPARSEABLE)
    result = collector.result()

    assert len(result.unmapped) == 1, "the unparseable control was dropped, not reported"
    rendered = result.unmapped[0].render()
    assert "CHECK positions_eod.isin" in rendered, (
        f"the report does not quote the source construct, so it cannot be found again: {rendered}"
    )
    assert result.unmapped[0].remedy, "reported with nothing to do about it"


def test_a_clean_import_reports_nothing_unmapped() -> None:
    """The control. Reporting everything as unmapped would satisfy both above."""
    from prama.importers.spi import Collector

    collector = Collector("dbt")
    collector.control(GOOD, caveat="severity guessed")
    result = collector.result()

    assert len(result.controls) == 1
    assert not result.unmapped
    assert len(result.caveats) == 1, "the caveat on a control that did import was lost"


# -- CON-153: open() and health() answer the same question -------------------


async def test_opening_a_connector_with_an_unusable_uri_refuses_in_the_taxonomy() -> None:
    from prama.connect.sources.objectstore import ObjectStoreConnector

    connector = ObjectStoreConnector({"uri": "ftp://bucket/prefix"})

    with pytest.raises(BaseException) as caught:
        async with connector:
            pass

    raised = type(caught.value)
    assert issubclass(raised, PramaError), (
        f"`async with connector:` raised {raised.__module__}.{raised.__name__} — the "
        "idiomatic form reported in DuckDB's words while health() had the right "
        "answer all along"
    )
    assert "ftp" in str(caught.value)


async def test_open_and_health_give_the_same_reason() -> None:
    """Derived once, so the two cannot drift into disagreeing again."""
    from prama.connect.sources.objectstore import ObjectStoreConnector

    connector = ObjectStoreConnector({"uri": "ftp://bucket/prefix"})
    report = await connector.health()

    with pytest.raises(PramaError) as caught:
        await connector.open()

    assert report.detail in str(caught.value), (
        f"health() says {report.detail!r} and open() says {caught.value}; they are "
        "answering the same question from two pieces of text again"
    )


async def test_a_recognised_scheme_is_not_refused_before_it_is_tried() -> None:
    """The counterfactual. Refusing every URI would satisfy both tests above."""
    from prama.connect.sources.objectstore import ObjectStoreConnector

    connector = ObjectStoreConnector({"uri": "s3://bucket/prefix"})
    assert connector._scheme_problem() == "", (
        "a legitimate s3 URI is reported as not naming an object store"
    )


# -- CTR-047: a nested JSON value is ordinary input --------------------------


@pytest.mark.parametrize(
    "left,right,identical",
    [
        ({"id": 1, "tags": ["a"]}, {"id": 1, "tags": ["a"]}, True),
        ({"id": 1, "tags": ["a"]}, {"id": 1, "tags": ["b"]}, False),
        ({"id": 1, "m": {"k": [1, 2]}}, {"id": 1, "m": {"k": [1, 2]}}, True),
        # Order is meaningful in a JSON array and not in a JSON object.
        ({"t": [1, 2]}, {"t": [2, 1]}, False),
        ({"m": {"a": 1, "b": 2}}, {"m": {"b": 2, "a": 1}}, True),
    ],
    ids=["same-list", "different-list", "deep-nesting", "list-order", "object-order"],
)
def test_a_keyless_diff_handles_nested_values(left: dict, right: dict, identical: bool) -> None:
    result = compare([left], [right])
    assert (result.added == 0 and result.removed == 0) is identical, (
        f"comparing {left} with {right} reported added={result.added} removed={result.removed}"
    )


# -- CLI-140: a file that is not the database it claims to be ----------------


def test_a_file_that_is_not_a_database_is_refused_by_name(tmp_path: Path) -> None:
    from prama.connect.sources.query import executor_for

    impostor = tmp_path / "estate.duckdb"
    impostor.write_text("id,name\n1,not a database at all\n")

    with pytest.raises(ValidationError) as caught:
        executor_for(impostor, "duckdb")

    message = str(caught.value)
    assert "estate.duckdb" in message, f"the refusal does not name the file: {message}"
    assert caught.value.remedy
    assert caught.value.context.get("detail"), (
        "the engine's own complaint was discarded; it is the part that says what "
        "is actually wrong with the file"
    )


def test_a_real_database_still_opens(tmp_path: Path) -> None:
    """The counterfactual.

    The repair wraps the builder call, so an over-broad `except` would turn every
    successful open into a refusal — and every control run with it.
    """
    from prama.connect.sources.query import executor_for

    real = tmp_path / "estate.duckdb"
    duckdb = pytest.importorskip("duckdb")
    connection = duckdb.connect(str(real))
    connection.execute("CREATE TABLE positions_eod (isin VARCHAR)")
    connection.execute("INSERT INTO positions_eod VALUES ('GB00B03MLX29')")
    connection.close()

    execute, close = executor_for(real, "duckdb")
    try:
        assert execute("SELECT isin FROM positions_eod") == [{"isin": "GB00B03MLX29"}]
    finally:
        close()
