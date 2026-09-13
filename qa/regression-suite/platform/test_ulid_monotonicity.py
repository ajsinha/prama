"""A ULID must never sort before one already issued.

QA round 3, `CFG-168`, recorded as `Q-70`. `UlidFactory.new()` read the clock
*outside* the lock that guards the state the reading is compared against::

    def new(self) -> str:
        ms = self._clock.epoch_millis()      # outside
        with self._lock:                     # too late
            if ms == self._last_ms: ...
            else:
                self._last_ms = ms           # a stale ms written back

Two threads either side of a millisecond boundary are enough:

1. **A** reads ``ms = 100`` and is descheduled before taking the lock.
2. **B** reads ``ms = 101``, takes the lock, sets ``_last_ms = 101``, emits.
3. **A** takes the lock. ``100 != 101``, so it takes the ``else`` branch, sets
   ``_last_ms = 100`` — regressing the high-water mark — and emits an id
   stamped 100, which sorts *before* the id B has already issued.

Round 2 recorded `CFG-168` as PASS because it ran the case once, unloaded.
Round 3 ran it repeatedly: 8 failures in 15 runs under contention (16 threads,
100k ids), 25 passes in 25 in isolation, with ``ids.py`` byte-identical to
round 2. A defect that only appears under load is not a smaller defect; it is
one that reaches production before it reaches a test.

**These tests do not reproduce it with load**, for two reasons. A test that
fails eight times in fifteen is a coin, not a control. And an attempt to force
the interleaving by blocking inside the clock cannot work *once the bug is
fixed*: with the reading taken under the lock, a thread held inside the clock
holds the lock too, so the second minter simply waits instead of racing. The
test would deadlock rather than assert.

So the invariant is driven where it actually lives — the reading the factory
receives. **A stalled thread and a clock that went backwards present the
factory with exactly the same thing: a millisecond lower than one already
used.** An NTP correction does it too. Scripting that sequence tests the real
property, deterministically, in milliseconds.

Why it matters more than a sort order usually would: ULIDs are the identifier
scheme for the whole system — `SERIAL` and `AUTOINCREMENT` are forbidden so an
id can be minted client-side without a round trip — and order is load-bearing
downstream. The evidence ledger is a *sequence* and `Archivist.bundle()` exports
a **range**.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from prama.core.clock import Clock
from prama.core.ids import UlidFactory, ulid_timestamp_millis

BASE = 1_774_000_000_000


class ScriptedClock(Clock):
    """Returns a fixed sequence of milliseconds, then holds the last one."""

    def __init__(self, sequence: list[int]) -> None:
        self._sequence = list(sequence)
        self._index = 0
        self._guard = threading.Lock()

    def now(self) -> datetime:  # pragma: no cover - not the axis under test
        return datetime.fromtimestamp(self.epoch_millis() / 1000, tz=UTC)

    def monotonic(self) -> float:  # pragma: no cover - not the axis under test
        return 0.0

    def epoch_millis(self) -> int:
        with self._guard:
            value = self._sequence[min(self._index, len(self._sequence) - 1)]
            self._index += 1
            return value


def test_a_reading_lower_than_one_already_used_cannot_produce_a_smaller_id() -> None:
    """The reading a stalled thread presents, without needing a stalled thread."""
    factory = UlidFactory(clock=ScriptedClock([BASE, BASE + 1, BASE]))

    first = factory.new()
    later = factory.new()
    stale = factory.new()

    assert first < later, "a plainly increasing clock must produce increasing ids"
    assert stale > later, (
        "an id minted from a reading below the high-water mark sorts before an "
        f"id already issued: {stale!r} <= {later!r}"
    )
    assert ulid_timestamp_millis(stale) >= ulid_timestamp_millis(later)


def test_the_high_water_mark_never_regresses() -> None:
    """The low reading must not be written back over a later one.

    Distinct from the ordering assertion above: an implementation could clamp
    the id it emits and still store the stale millisecond, which would leave
    the *next* caller free to repeat the whole problem.
    """
    factory = UlidFactory(clock=ScriptedClock([BASE, BASE + 1, BASE]))
    for _ in range(3):
        factory.new()

    assert factory._last_ms == BASE + 1, (
        f"a reading below the high-water mark was written back over it: "
        f"_last_ms is {factory._last_ms}, expected {BASE + 1}"
    )


def test_a_clock_that_walks_backwards_still_yields_a_sorted_sequence() -> None:
    """A sustained backwards correction, not just a single dip."""
    walk = [BASE + n for n in (0, 1, 2, 1, 0, 1, 3, 2, 4)]
    factory = UlidFactory(clock=ScriptedClock(walk))

    ids = [factory.new() for _ in walk]

    assert ids == sorted(ids), "ids are not in issue order"
    assert len(set(ids)) == len(ids), "an id was issued twice"


def test_concurrent_minting_is_ordered_by_issue() -> None:
    """The property under real threads, with the clock as the source of jitter.

    The scheduler is not asked to produce the race — that is what made the
    original case a coin. Every thread draws from a clock that steps back and
    forth across a boundary, so a reading below the high-water mark is
    guaranteed to occur many times regardless of how threads interleave.
    """
    jitter = [BASE + (n % 3) for n in range(4000)]
    factory = UlidFactory(clock=ScriptedClock(jitter))
    minted: list[str] = []
    guard = threading.Lock()

    def mint() -> None:
        for _ in range(250):
            value = factory.new()
            with guard:
                minted.append(value)

    threads = [threading.Thread(target=mint) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "a minting thread did not finish"

    assert len(set(minted)) == len(minted), "an id was issued twice under contention"

    # Deliberately NOT asserting `minted == sorted(minted)`. The append happens
    # after `new()` returns, so a thread can mint and be descheduled before
    # recording; the list is not issue order and an assertion on it would fail
    # for a reason unrelated to the defect. Ordering is asserted deterministically
    # by the tests above, which is where it can be asserted honestly.
    #
    # What is observable here: nothing may have been emitted from above the
    # high-water mark the factory finished on.
    ceiling = factory._last_ms
    assert all(ulid_timestamp_millis(value) <= ceiling for value in minted)
