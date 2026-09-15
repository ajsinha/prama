"""One reading of a timestamp with no offset, everywhere.

QA round 4, `EVD-110` and `Q-89` — the second found while fixing the first, in
the code the first one's fix was derived from.

`CLAUDE.md` fixes the storage: *"SQLite has no date type; timestamps are
ISO-8601 UTC text in `VARCHAR(32)`, which sorts chronologically."* And
`UtcDateTime.process_bind_param` refuses to write a naive datetime at all. So a
stored value with no offset was written by something that is not Prama, and the
only defensible reading of it is UTC.

**`EVD-110`.** `Archivist.tier_of` subtracted a parsed `finished_at` from an
aware clock reading. A naive value raised `TypeError: can't subtract
offset-naive and offset-aware datetimes` — not caught anywhere, and `plan()`
iterates the whole ledger, so **one bad record stopped the entire retention
sweep** and every record after it went un-tiered. The function already had an
`except ValueError` for an unparseable timestamp, chosen with care: stay hot
rather than age out on a guess. The author thought about the value being wrong
and not about it being *incomplete*.

**`Q-89`, the more interesting one.** `UtcDateTime.process_result_value` has two
paths, and they disagreed. A datetime the driver had already parsed got
`replace(tzinfo=UTC)` — naive means UTC. A *string* got
`fromisoformat(text).astimezone(UTC)` — and `astimezone` on a naive value reads
it as **local time**. Same column, same stored bytes, two instants.

It is invisible on a UTC host, which is most CI. On a host in `Asia/Kolkata` the
two paths were 5½ hours apart. And it fell along the engine boundary: SQLite
hands back text, PostgreSQL's driver hands back a datetime — so the same row
read differently on the two engines whose schemas this project keeps
byte-identical precisely so they cannot mean different things.

**What a careless version of this test would do.** Run in the ambient timezone.
Every assertion here would have passed on a UTC machine before the fix, which is
exactly why the defect survived. `TZ` is pinned to a non-UTC zone with a
half-hour offset, so a reading that is wrong by the local offset cannot coincide
with a reading that is right.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pytest

from prama.db.types import UtcDateTime
from prama.evidence.record import EvidenceRecord
from prama.evidence.retention import Archivist, Tier

NAIVE = "2026-01-01T00:00:00"
AWARE = "2026-01-01T00:00:00Z"


def a_record(finished_at: str) -> EvidenceRecord:
    return EvidenceRecord(
        plan_id="p", control_id="c", dataset="trades", verdict="pass", finished_at=finished_at
    )


def test_a_naive_finished_at_does_not_stop_the_sweep() -> None:
    """`EVD-110`. The TypeError was uncaught and `plan()` iterates everything."""
    assert Archivist().tier_of(a_record(NAIVE)) is Archivist().tier_of(a_record(AWARE))


def test_one_unreadable_record_does_not_hide_the_rest() -> None:
    """The consequence, stated on the operation that actually runs.

    `tier_of` raising is a nuisance; `plan()` raising is the defect, because the
    sweep is what moves evidence to cold storage and it stops at the first bad
    row. Asserting on `tier_of` alone would pass a fix that repaired the parse
    and left the sweep fragile some other way.
    """
    from prama.evidence.ledger import Ledger

    ledger = Ledger()
    for finished_at in (AWARE, NAIVE, AWARE):
        ledger.append(a_record(finished_at))

    plan = Archivist().plan(ledger)
    assert sum(len(records) for records in plan.values()) == 3, (
        f"the sweep did not tier every record: { {k: len(v) for k, v in plan.items()} }"
    )


def test_an_unparseable_timestamp_still_stays_hot() -> None:
    """The judgement that was already right, and must survive the repair.

    Aging a record out because its date did not parse would delete evidence on a
    guess. Widening the `except` to cover `TypeError` would have been the lazy
    fix and would have swept naive timestamps into the same bucket — correct by
    accident, and wrong the moment a naive timestamp is the normal case.
    """
    assert Archivist().tier_of(a_record("not-a-date")) is Tier.HOT


@pytest.mark.parametrize(
    "stored,expected",
    [
        (NAIVE, datetime(2026, 1, 1, tzinfo=UTC)),
        (AWARE, datetime(2026, 1, 1, tzinfo=UTC)),
        ("2026-01-01T05:30:00+05:30", datetime(2026, 1, 1, tzinfo=UTC)),
    ],
    ids=["naive", "zulu", "real-offset"],
)
def test_the_column_reads_the_same_whatever_the_driver_hands_back(
    stored: str, expected: datetime
) -> None:
    """`Q-89`, in-process. A real offset is still honoured, not flattened."""
    assert UtcDateTime().process_result_value(stored, None) == expected


def test_the_two_paths_agree_on_a_host_that_is_not_utc() -> None:
    """`Q-89` as it actually failed, which needs a timezone this host may not be.

    Run in a subprocess so `TZ` is set before anything reads it — changing it
    in-process is honoured inconsistently across platforms, and a test that
    silently keeps the ambient zone is the measurement that hid this defect.
    """
    script = textwrap.dedent(
        """
        from datetime import datetime
        from prama.db.types import UtcDateTime
        column = UtcDateTime()
        from_text = column.process_result_value("2026-01-01T00:00:00", None)
        from_driver = column.process_result_value(datetime(2026, 1, 1), None)
        print(from_text.isoformat(), from_driver.isoformat())
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ, "TZ": "Asia/Kolkata"},
        cwd=Path.cwd(),
    )
    assert result.returncode == 0, result.stderr[-400:]
    from_text, from_driver = result.stdout.split()

    assert from_text == from_driver, (
        f"on a host in Asia/Kolkata the same stored timestamp read back as "
        f"{from_text} from text and {from_driver} from a parsed datetime. SQLite "
        "returns text and PostgreSQL's driver returns a datetime, so this is the "
        "two engines disagreeing about a value the schema keeps identical."
    )
    assert from_text.startswith("2026-01-01T00:00:00+00:00"), (
        f"a naive stored timestamp was not read as UTC: {from_text}"
    )
