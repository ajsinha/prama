# QA round 4

The same 4,660 cases, run against the tree after batches **A–D**. Round 3's logs
are in `../logs-round3/` and are the baseline.

**The comparison rule.** A case that **passed in round 3 and fails here is a
regression introduced by batches A–D**, and is the most important thing this
round can find. Round 3's baseline is hours old and the delta is roughly ten
source files, so unlike round 3 — which compared across ten batches — this round
can attribute a regression to a specific change.

**Why it is being run at all**, given how small the delta is: two of the changed
files have estate-wide reach. `core/ids.py` is the minting path for every
identifier in the system and was rewritten under a lock; ULID sort order is
load-bearing for the evidence ledger's sequence and for `Archivist.bundle()`'s
ranges. `cli/base.py` moved pack installation into every CLI invocation.

**Two conditions, both learned the hard way on 2026-09-13.** Every agent must run
with `helm` on `PATH` and `PRAMA_TEST_POSTGRES_DSN` set. Finding `Q-74` was a
chart test that had been failing since the `OPS-014` fix and skipped through six
consecutive green gate runs because one binary was absent. A skip reports neither
pass nor fail, and a suite summarised by its first number looks green whatever
the second one says.

The tree is frozen for the whole round. If `src/` changes midway, areas measured
before and after are not comparable and the round-over-round question — the only
question this round exists to answer — becomes unanswerable for half the
catalogue.

Format is identical to round 3: a header with counts and a **regressions**
section first, then the full per-case table in id order, then a section per FAIL.
