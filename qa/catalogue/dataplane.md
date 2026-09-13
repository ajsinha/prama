# Getting to the data, and running against it

The connector SPI and every shipped source, profiling and its sketches,
discovery, the control run and its workers, and the schedule that decides when
any of it happens.

Derived by reading `src/prama/connect/**` (29 files, ~8,700 lines),
`src/prama/profile/**` (8 files), `src/prama/discover/**` (2 files),
`src/prama/execute/**` (11 files) and `src/prama/schedule/**` (6 files), plus
`src/prama/core/concurrency/bounded_queue.py` and
`src/prama/core/concurrency/leases.py` where the execution path depends on them.

Nothing here has been executed. Every case names the module or function it
exercises; the format and the priority vocabulary are defined in
[README.md](README.md).

## Summary

| Area | Cases | P1 | P2 | P3 |
|---|---:|---:|---:|---:|
| `connect/spi.py` — the connector contract | 24 | 14 | 8 | 2 |
| `connect/capability.py` — the pushdown matrix | 10 | 3 | 5 | 2 |
| `connect/arrow.py` — `to_array` | 10 | 8 | 2 | 0 |
| `connect/config_schema.py`, `registry.py`, `builtin.py` | 20 | 10 | 9 | 1 |
| `connect/cost.py` and `connect/pacing.py` | 18 | 5 | 12 | 1 |
| `connect/sources/sql/` — base and dialects | 39 | 19 | 20 | 0 |
| `connect/sources/sqlite.py` | 10 | 3 | 7 | 0 |
| `connect/sources/filesystem.py` | 11 | 5 | 5 | 1 |
| `connect/sources/objectstore.py` | 13 | 7 | 5 | 1 |
| `connect/sources/rest.py` | 16 | 10 | 5 | 1 |
| `connect/sources/mongo.py` | 10 | 7 | 3 | 0 |
| `connect/sources/query.py` — the executor seam | 9 | 6 | 2 | 1 |
| `connect/feed/` — arrival, patterns, trailers | 36 | 16 | 17 | 3 |
| `profile/sketches.py` — HLL, TDigest, CountMin, TopK | 27 | 17 | 9 | 1 |
| `profile/statistics.py` — column accumulation | 21 | 9 | 11 | 1 |
| `profile/profiler.py` — profiling end to end | 15 | 9 | 5 | 1 |
| `profile/segments.py`, `segmented.py`, `incremental.py` | 31 | 18 | 12 | 1 |
| `profile/recording.py` | 4 | 1 | 3 | 0 |
| `discover/relationships.py` | 11 | 3 | 7 | 1 |
| `execute/run.py` — the control run | 29 | 25 | 4 | 0 |
| `execute/claim.py`, `worker.py` — claims, leases, fencing | 25 | 15 | 10 | 0 |
| `core/concurrency/bounded_queue.py` | 15 | 9 | 6 | 0 |
| `execute/inflight.py`, `transport.py`, `kafka.py` | 30 | 19 | 11 | 0 |
| `execute/stream.py`, `watermark.py` | 28 | 19 | 7 | 2 |
| `execute/actions.py`, `preview.py` | 26 | 17 | 9 | 0 |
| `schedule/spec.py`, `trigger.py`, `due.py` | 32 | 22 | 10 | 0 |
| `schedule/cadence.py`, `budget.py` | 20 | 9 | 8 | 3 |
| **Total** | **540** | **305** | **212** | **23** |

Id ranges: `CON-001`–`CON-226`, `PRO-001`–`PRO-109`, `EXE-001`–`EXE-153`,
`SCH-001`–`SCH-052`. No gaps, no reuse.

The P1 share is high — 56% — and that is a property of the area rather than of
the grading. This is the tree that reaches a customer's production database,
decides what a control saw, and writes the number an auditor reads; most of what
can go wrong here goes wrong silently, which is the README's definition of P1.
Where a case is P2 or P3 it is because the failure is visible when it happens.

**Sixteen of these are claims the code does not appear to keep**, found while
reading rather than while running, and each names the evidence in its *Why*:
CON-014/CON-172 (a connector declaring `PREDICATE_PUSHDOWN` that issues
`find({})`), CON-021 (a read policy prefix that admits a neighbouring schema),
CON-043/CON-044/CON-167 (three batch builders that bypass `to_array`),
CON-099 (`_column_names` stale across `_fetch`), CON-105 (`fetch_size` read,
rendered in the form, never used), CON-117 (`sample_plan_is_supported` has no
caller), CON-118 (`select_sql` drops the predicate `stream_sql` applies),
CON-142 (the read policy's budgets bind on SQL sources only), CON-206
(`FeedDefinition` does not round-trip), EXE-018/EXE-019 (every evidence record
says wall-clock and `full`), EXE-043 (`drain` spins on a stranded unit), EXE-050
(a stranded unit is absent from the fleet report), EXE-096 (Kafka's unreadable
message is never dead-lettered as one), PRO-047 (a CountMin built per column and
never read), PRO-088 (the object-level snapshot makes per-segment reuse
unreachable on an append-only table), PRO-108 (`KEY_OVERLAP` declared and never
emitted), SCH-010 (no syntax produces a `DependencyTrigger`), SCH-014 (calendar
schedules are never staggered), SCH-046 (the budget's sort key and its docstring
disagree about what is shed first).

None has been executed. Each is written so that running it settles the question
either way.

## `connect/spi.py` — the connector contract

The eight operations every source implements, and the types that travel with
them. The conformance suite (`tests/connect/test_conformance.py`) covers health,
discover, describe, snapshot, read, a HEAD sample, a missing object, declared
capabilities and the read policy — for the two connectors that need no live
service. Everything below that it does not reach is marked as such in the *Why*.

### CON-001 · Every abstract method is abstract
- **Area:** `connect/spi.py::Connector`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** define a subclass of `Connector` that implements none of
  `health`, `discover`, `describe`, `snapshot`, `read`; instantiate it
- **Expected:** `TypeError` naming all five unimplemented methods
- **Why:** the contract is only a contract if a partial implementation cannot be
  registered; `ConnectorRegistry.register` takes classes, so a half-built
  connector would be discovered before anybody read it

### CON-002 · `open` and `close` default to doing nothing
- **Area:** `connect/spi.py::Connector.open` / `.close`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a minimal concrete connector overriding only the five
  abstract methods
- **Steps:** `await c.open()`; `await c.close()`
- **Expected:** both return `None`, raise nothing
- **Why:** a stateless connector must not be forced to write two empty overrides,
  and the default is what makes `async with` usable everywhere

### CON-003 · `__aenter__` opens and `__aexit__` closes
- **Area:** `connect/spi.py::Connector.__aenter__` / `__aexit__`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a connector recording calls to `open`/`close`
- **Steps:** `async with connector as c: pass`
- **Expected:** `open` called once before the body, `close` called once after,
  `c` is the connector itself
- **Why:** every shipped source acquires a driver, a thread or a pool in `open`;
  a context manager that did not close leaks one per use

### CON-004 · `__aexit__` closes when the body raises
- **Area:** `connect/spi.py::Connector.__aexit__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** as CON-003
- **Steps:** `async with connector: raise RuntimeError("boom")`
- **Expected:** the `RuntimeError` propagates and `close` was still called
- **Why:** `__aexit__` returns `None`, so the exception must not be suppressed —
  and the resource must still be released

### CON-005 · `close` is safe to call twice
- **Area:** `connect/spi.py::Connector.close`, and every override
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an opened connector of each shipped kind
- **Steps:** `await c.close()` twice
- **Expected:** no exception on the second call; no second driver-level close
- **Why:** every override nulls its handle first (`self._client, x = None, x`),
  so this is the property those two-step assignments exist to give — and nothing
  in the conformance suite asserts it

### CON-006 · Using a connector before `open` names the mistake
- **Area:** `connect/sources/*::_require` / `_duck` / `_http` / `_db`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a constructed but unopened connector of each kind
- **Steps:** call `describe`, `read` and `snapshot` without `open`
- **Expected:** `ConnectorError` with code `CONNECT.NOT_OPEN` and the remedy
  "use the connector as an async context manager, or call open() first"
- **Why:** each of the six drivers has its own version of this guard; a
  connector missing one raises the driver's own `AttributeError` instead

### CON-007 · `run_metric_query` refuses by default, with the alternative
- **Area:** `connect/spi.py::Connector.run_metric_query`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a connector that does not override it
- **Steps:** `await c.run_metric_query("SELECT 1")`
- **Expected:** `ConnectorError` naming the connector class, whose remedy says
  the controls are evaluated locally over `read` and to check
  `can_run_controls` first
- **Why:** the docstring promises "refuses with the alternative rather than with
  a bare error"; a caller that lands here is talking to a file, not making a
  mistake

### CON-008 · `can_run_controls` is False by default
- **Area:** `connect/spi.py::Connector.can_run_controls`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** read the property on a minimal subclass
- **Expected:** `False`
- **Why:** claiming a query engine a source does not have sends compiled SQL to
  a CSV; the safe default is the weaker claim

### CON-009 · Declaring no capabilities is legal only alongside `can_run_controls = False`
- **Area:** `connect/spi.py::Connector.pushdown_capabilities`, guarded by
  `tests/connect/test_conformance.py::test_every_connector_declares_what_it_can_push_down`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the built-in registry
- **Steps:** for every registered key, assert that an empty capability matrix
  implies `can_run_controls is False`
- **Expected:** holds for all nine; `rest` and `mongodb` are the empty-matrix
  cases and both report `False`
- **Why:** an empty matrix on a query engine is a field somebody forgot to fill
  in, and the cost is every control silently falling back to a full local scan

### CON-010 · `execute_plan` refuses with its own code
- **Area:** `connect/spi.py::Connector.execute_plan`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a connector claiming no pushdown
- **Steps:** `await c.execute_plan(object())`
- **Expected:** `ConnectorError` with code `CONNECT.NO_PUSHDOWN`, distinct from
  `CONNECT.ERROR`, remedy naming the Arrow backend
- **Why:** a distinct code is what lets a caller fall back rather than abort;
  nothing in `src/` calls `execute_plan`, so this refusal is the whole contract

### CON-011 · `supports` matches a capability by name
- **Area:** `connect/spi.py::Connector.supports`
- **Type:** functional
- **Priority:** P2
- **Precondition:** the SQLite connector
- **Steps:** `c.supports("pushdown.sql")`, `c.supports("pushdown.regex")`,
  `c.supports("")`
- **Expected:** `True`, `False`, `False`
- **Why:** `require_predicate_support` and the compiler both route through this
  one string comparison; a name typo here is a silently unfiltered read

### CON-012 · A predicate on a connector that cannot filter is refused
- **Area:** `connect/spi.py::Connector.require_predicate_support`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a connector not declaring `pushdown.predicate`
- **Steps:** `c.require_predicate_support(SamplePlan(predicate="d = '2026-04-01'"))`
- **Expected:** `ConnectorError`, code `CONNECT.NO_PREDICATE`, context carrying
  the predicate, remedy explaining that reading everything and calling it one
  segment would attribute the whole object's data to that segment
- **Why:** the docstring calls the alternative "the quiet disaster"; this is the
  guard that stands between segmented profiling and a wrong answer that looks
  right

### CON-013 · An empty predicate is never refused
- **Area:** `connect/spi.py::Connector.require_predicate_support`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a connector declaring nothing
- **Steps:** `c.require_predicate_support(SamplePlan())`
- **Expected:** returns `None`
- **Why:** an unfiltered read through a non-filtering connector is the ordinary
  case, and a guard that fired on it would make every plain read fail

### CON-014 · A connector that declares `pushdown.predicate` must actually apply it
- **Area:** `connect/spi.py::SamplePlan.predicate`, every `read` implementation
- **Type:** contract
- **Priority:** P1
- **Precondition:** a two-row-per-day table reachable through each connector
  that declares `PushdownFeature.PREDICATE_PUSHDOWN`
- **Steps:** read with `SamplePlan(predicate="<one day>")` and count rows
- **Expected:** exactly that day's rows; never the whole object
- **Why:** `require_predicate_support` only checks the *declaration*. The SPI
  says a connector that cannot apply a predicate MUST raise; it does not check
  that one which passes the declaration test then uses the predicate. Read
  `MongoConnector._sample`, which issues `find({})`, against `MongoConnector`'s
  declared `PREDICATE_PUSHDOWN`

### CON-015 · `SamplePlan.is_complete` is False as soon as a predicate is present
- **Area:** `connect/spi.py::SamplePlan.is_complete`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate on `SamplePlan()`, `SamplePlan(predicate="x")`,
  `SamplePlan(strategy=HEAD)`
- **Expected:** `True`, `False`, `False`
- **Why:** `ProfileProvenance.is_complete` reads straight through to this, and a
  segment's rates stated as the dataset's is a straightforward falsehood

### CON-016 · `SamplingStrategy.HEAD` is the only unrepresentative strategy
- **Area:** `connect/spi.py::SamplingStrategy.is_representative`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate for all six members
- **Expected:** `False` only for `HEAD`
- **Why:** a rate measured on HEAD may not be extrapolated; this one boolean is
  what stops "we sampled" from becoming "we measured"

### CON-017 · `SamplePlan.describe` renders each shape as a sentence
- **Area:** `connect/spi.py::SamplePlan.describe`
- **Type:** functional
- **Priority:** P3
- **Precondition:** none
- **Steps:** describe FULL; FULL with a predicate; SYSTEMATIC at `fraction=0.015`;
  RESERVOIR with `rows=1000`; STRATIFIED with neither
- **Expected:** `full scan`; `full scan where …`; `systematic sample at 1.5%`;
  `reservoir sample of 1,000 rows`; `stratified`
- **Why:** this string is stored on every metric point as `sampling` and read
  back by a monitor deciding whether two baselines are comparable

### CON-018 · `SnapshotKind.is_exact` excludes exactly two kinds
- **Area:** `connect/spi.py::SnapshotKind.is_exact`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate for all nine members
- **Expected:** `False` for `WALL_CLOCK` and `OBJECT_LISTING` only
- **Why:** `IncrementalPlanner._state` re-reads every segment when the snapshot
  is inexact; one wrong entry here makes incremental profiling trust a stale
  profile for ever

### CON-019 · `Snapshot.to_dict` always carries `exact`
- **Area:** `connect/spi.py::Snapshot.to_dict`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a snapshot of each kind, with and without `detail`
- **Steps:** serialise
- **Expected:** `kind`, `id`, `captured_at`, `exact` always present; `detail`
  only when non-empty
- **Why:** the evidence record carries this flag, and deterministic replay
  depends on it; a missing key reads as absent rather than false

### CON-020 · `HealthReport` distinguishes who has to fix it
- **Area:** `connect/spi.py::HealthReport.is_usable` /
  `.needs_access_request` / `.needs_reconfiguration`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate all three for each of the six `HealthState` values, and
  for `HEALTHY` with a non-empty `missing_permissions`
- **Expected:** `is_usable` true for HEALTHY and DEGRADED only;
  `needs_access_request` true for UNAUTHORISED *and* for any report carrying
  missing permissions; `needs_reconfiguration` true only for MISCONFIGURED
- **Why:** collapsing these into "connection failed" costs a day of the wrong
  investigation each time — the docstring's own claim

### CON-021 · `ReadPolicy.permits_path` treats an empty allow-list as "everything"
- **Area:** `connect/spi.py::ReadPolicy.permits_path`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** `ReadPolicy().permits_path(("risk","positions"))`;
  then `ReadPolicy(allowed_paths=("risk.*",))` against `risk.positions`,
  `risk`, `riskier.positions`, `()`
- **Expected:** `True`; then `True`, `True`, **`True`** (the prefix is
  `"risk."` after `rstrip("*")` — check whether `riskier.positions` matches and
  record which), `True` for the empty path
- **Why:** `rstrip("*")` strips every trailing asterisk, not one, and the
  comparison is a bare `startswith` with no separator anchoring — a policy
  meaning "the risk schema" may admit a neighbouring schema whose name shares
  the prefix

### CON-022 · `ReadPolicy.permits_now` treats no permitted hours as "any hour"
- **Area:** `connect/spi.py::ReadPolicy.permits_now`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `ReadPolicy().permits_now(3)`;
  `ReadPolicy(permitted_hours=(0,1,2)).permits_now(2)` and `.permits_now(3)`;
  `.permits_now(24)` and `.permits_now(-1)`
- **Expected:** `True`; `True`, `False`; `False`, `False`
- **Why:** an out-of-range hour must not wrap into a permitted one; nothing in
  `src/` calls this, so the whole permitted-hours feature rests on this method

### CON-023 · `Verification` defaults to the weaker claim
- **Area:** `connect/spi.py::Connector.describe_manifest`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** `Connector.describe_manifest(key="x", display_name="X")`
- **Expected:** `verification == "code_complete"` and the description carries
  `CODE COMPLETE — written and unit-tested; no live source has answered it`
- **Why:** a connector that forgets to say is one nobody has run; the default is
  the only thing stopping an unrun source from looking finished

### CON-024 · `DiscoveredObject.qualified_name` and `.leaf` survive an empty path
- **Area:** `connect/spi.py::DiscoveredObject`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** build with `path=()`
- **Expected:** `qualified_name == ""`, `leaf == ""`, no `IndexError`
- **Why:** discovery output is sorted and rendered by these two; an `IndexError`
  in a list comprehension takes the whole source picker down

## `connect/capability.py` — the pushdown matrix

### CON-025 · `require` refuses at compile time rather than degrading
- **Area:** `connect/capability.py::CapabilityMatrix.require`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `NO_PUSHDOWN`
- **Steps:** `NO_PUSHDOWN.require(PushdownFeature.REGEX)`
- **Expected:** `ConnectorError`, code `CONNECT.CAPABILITY_MISSING`, message
  containing "regex", context `{"feature": "pushdown.regex"}`, remedy stating
  that Prama will not substitute a construct that means almost the same thing
- **Why:** "almost the same thing" — a regex that matches slightly differently,
  a decimal that rounds differently — is invisible in development and
  load-bearing in production

### CON-026 · `require` passes silently for a declared feature
- **Area:** `connect/capability.py::CapabilityMatrix.require`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `BASELINE_SQL`
- **Steps:** `require(SQL)`, `require(FILTER)`, `require(AGGREGATION)`,
  `require(PREDICATE_PUSHDOWN)`
- **Expected:** all return `None`
- **Why:** the matrix is consulted per construct on every compile; a false
  refusal makes an entire dialect unusable

### CON-027 · `PushdownFeature.label` strips the namespace
- **Area:** `connect/capability.py::PushdownFeature.label`
- **Type:** functional
- **Priority:** P3
- **Precondition:** none
- **Steps:** evaluate for `APPROX_DISTINCT`, `EXACT_SNAPSHOT`, `SQL`
- **Expected:** `approx distinct`, `exact` (the value is `snapshot.exact`, so the
  label is the part after the first dot), `sql`
- **Why:** the label reaches a user-facing refusal; `EXACT_SNAPSHOT` reading as
  "exact" rather than "exact snapshot" is the kind of message that sends
  somebody to the wrong setting

### CON-028 · A matrix is immutable and never probed
- **Area:** `connect/capability.py::CapabilityMatrix`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a live source
- **Steps:** construct a matrix and attempt `matrix.features.add(...)` and
  `matrix.features = frozenset()`; then assert no connector issues a query
  during `pushdown_capabilities()`
- **Expected:** `AttributeError` on both mutations; `pushdown_capabilities` makes
  no round trip
- **Why:** "probing a production database to find out whether it supports a
  window function is both rude and unreliable" — the docstring's own claim, and
  nothing tests the no-round-trip half

### CON-029 · `to_capabilities` is deterministically ordered
- **Area:** `connect/capability.py::CapabilityMatrix.to_capabilities`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a matrix built from an unordered set of features
- **Steps:** build the same matrix twice from differently ordered arguments and
  compare the tuples
- **Expected:** identical, sorted by `feature.value`
- **Why:** a manifest's capability list reaches an artefact digest; a set
  iteration order that varies per process makes the same connector hash two ways

### CON-030 · Every capability in the rendered tuple carries the same attributes
- **Area:** `connect/capability.py::CapabilityMatrix.to_capabilities`
- **Type:** functional
- **Priority:** P3
- **Precondition:** `CapabilityMatrix.of(SQL, REGEX, regex_flavour="posix")`
- **Steps:** inspect both rendered `Capability` objects
- **Expected:** both carry `{"regex_flavour": "posix"}`, and each is a distinct
  dict (mutating one must not change the other)
- **Why:** `dict(self.attributes)` is copied per capability for exactly this
  reason; a shared dict is a manifest that changes under an unrelated edit

### CON-031 · `regex_flavour` defaults to `none`, not to a flavour
- **Area:** `connect/capability.py::CapabilityMatrix.regex_flavour`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a matrix declaring `REGEX` and no `regex_flavour`
- **Steps:** read the property
- **Expected:** `"none"`
- **Why:** a control depending on POSIX classes is not portable to RE2; a
  connector claiming regex and naming no flavour is the case a compiler must be
  able to see

### CON-032 · `nulls_sort_first` distinguishes unknown from False
- **Area:** `connect/capability.py::CapabilityMatrix.nulls_sort_first`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** matrices with the attribute absent, `True`, `False`, `0`
- **Steps:** read the property for each
- **Expected:** `None`, `True`, `False`, `False`
- **Why:** `None` means "nobody said" and `False` means "nulls sort last"; a
  compiler that read the first as the second orders a window's frame the wrong
  way round

### CON-033 · `max_decimal_precision` returns an int or `None`
- **Area:** `connect/capability.py::CapabilityMatrix.max_decimal_precision`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** matrices with the attribute absent, `38`, `"38"`, `None`
- **Steps:** read the property
- **Expected:** `None`, `38`, `38`, `None`
- **Why:** SQLite declares `max_decimal_precision=None` deliberately — "there is
  no limit because there are no decimals" and "nobody stated one" must not both
  become a number

### CON-034 · Every shipped connector's declared matrix matches its dialect's
- **Area:** `connect/builtin.py::BUILTIN`, `connect/sources/**::CAPABILITIES`
- **Type:** contract
- **Priority:** P2
- **Precondition:** the built-in registry
- **Steps:** for each SQL-backed key, compare
  `registry.capabilities(key).describe()` with
  `registry.get(key).dialect.capabilities.describe()`
- **Expected:** identical for `postgresql`, `clickhouse`, `snowflake`;
  `jdbc` deliberately declares the generic matrix and narrows per configured
  dialect at construction
- **Why:** `SqlConnector.pushdown_capabilities` returns the *dialect's* matrix
  while the registry serves the module-level constant — two sources for one
  claim, and the JDBC connector is the one where they legitimately differ

## `connect/arrow.py` — `to_array`

Fifty-four lines with a history: three ways a value gets lost between a driver
and an Arrow column, each found by running a real source.

### CON-035 · Arrow's own inference is tried first
- **Area:** `connect/arrow.py::to_array`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `to_array([1, 2, 3])`, `to_array(["a", "b"])`,
  `to_array([1.5, 2.5])`, `to_array([True, False])`
- **Expected:** `int64`, `string`, `double`, `bool` — not string
- **Why:** the fallbacks are for the cases inference cannot do; falling back
  unnecessarily turns every numeric column into text and every downstream
  numeric control into a type error

### CON-036 · An unsigned 64-bit value survives
- **Area:** `connect/arrow.py::to_array`, step 2
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** `to_array([18446744073709551615])`
- **Expected:** a `uint64` array whose sole value is exactly
  `18446744073709551615` — not a float, not a string, not an exception
- **Why:** MySQL's unsigned BIGINT goes past int64 and is a real identifier; the
  module docstring names this as the case that made such a table unreadable

### CON-037 · A column mixing int and str falls back to text, not to a raise
- **Area:** `connect/arrow.py::to_array`, step 3
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `to_array([100, "one hundred"])`
- **Expected:** a `string` array `["100", "one hundred"]`
- **Why:** in MongoDB this disagreement *is* the finding the estate is being
  examined for; it has to survive into a control rather than stopping the read

### CON-038 · The fallback is never a float
- **Area:** `connect/arrow.py::to_array`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** `to_array([Decimal("1953193.464900000000"), "x"])`
- **Expected:** `string`, and the decimal's element is exactly
  `"1953193.464900000000"` — every digit preserved
- **Why:** "a float makes the read succeed and the number wrong, which is the
  failure this whole tree is built to avoid"; a string is visibly a string and a
  numeric control on it fails loudly

### CON-039 · Nulls survive every fallback level
- **Area:** `connect/arrow.py::to_array`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** `to_array([None, None])`; `to_array([None, 18446744073709551615])`;
  `to_array([None, 1, "x"])`
- **Expected:** length 2, 2, 3; the null positions are Arrow nulls in every case
  — never the string `"None"`
- **Why:** the string fallback maps `None` explicitly; an off-by-one there turns
  a null rate of 4% into 0% and removes a completeness finding

### CON-040 · An empty list produces an empty array
- **Area:** `connect/arrow.py::to_array`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `to_array([])`
- **Expected:** a zero-length array; no exception
- **Why:** a batch of a table with a column and no rows reaches here; a raise
  turns "the table is empty" into "the source is broken"

### CON-041 · A value whose `str()` raises is not swallowed
- **Area:** `connect/arrow.py::to_array`, step 3
- **Type:** negative
- **Priority:** P2
- **Precondition:** an object whose `__str__` raises
- **Steps:** `to_array([that_object])`
- **Expected:** the original exception propagates; the read fails loudly rather
  than producing a column of nothing
- **Why:** the only `except` clauses cover `ArrowInvalid`, `ArrowTypeError`,
  `OverflowError` and `TypeError` around `pa.array`; a failure inside the
  comprehension is uncaught, and it should be

### CON-042 · A signed negative value is not coerced through `uint64`
- **Area:** `connect/arrow.py::to_array`, step 2
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** `to_array([-1, 18446744073709551615])`
- **Expected:** **not** a `uint64` array containing `18446744073709551615` and a
  wrapped `-1`; either a string array, or an exception — record which
- **Why:** step 2 is tried for any value that defeats inference, and `-1` as
  unsigned is `18446744073709551615`. Two rows becoming the same identifier is
  the exact class of silent reinterpretation this module exists to prevent

### CON-043 · `to_array` is used by every connector that builds a batch by hand
- **Area:** `connect/sources/sql/base.py::SqlConnector.read`,
  `connect/sources/mongo.py::MongoConnector.read`,
  `connect/sources/sqlite.py::SqliteConnector._read_batch`,
  `connect/sources/rest.py::RestConnector.read`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** grep each `RecordBatch.from_arrays` / `from_pydict` call site for
  `to_array`
- **Expected:** all four route through it
- **Why:** `SqliteConnector._read_batch` calls `pa.array(list(column))` directly
  and `RestConnector.read` calls `from_pydict`; neither has the unsigned or the
  mixed-type fallback, so the same data read through two connectors behaves
  differently

### CON-044 · A mixed-type column read over SQLite does not raise
- **Area:** `connect/sources/sqlite.py::SqliteConnector._read_batch`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a SQLite table with a `TEXT`-affinity column holding `100`
  in one row and `'one hundred'` in another (SQLite permits this)
- **Steps:** read the table
- **Expected:** a string column of both values
- **Why:** the counterfactual for CON-043. SQLite's dynamic typing makes this
  reachable, and `pa.array` raises `ArrowInvalid` on it, so the table cannot be
  read at all

## `connect/config_schema.py`, `registry.py`, `builtin.py`

The form is *derived* from each connector's own `self.config.get(...)` calls and
only annotated by a hand-written overlay. `audit()` is what stops the two halves
disagreeing.

### CON-045 · Every field a connector reads appears in its form
- **Area:** `connect/config_schema.py::ConfigSchemaDeriver.derive`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the built-in registry
- **Steps:** for each key, compare `registry.schema(key)` field names against a
  grep of `self.config.get("…"` in that connector's module and its bases
- **Expected:** identical sets
- **Why:** a setting the code honours that nobody can set is invisible; this is
  the whole reason the deriver exists rather than a hand-written table

### CON-046 · The MRO is walked, so inherited fields are offered
- **Area:** `connect/config_schema.py::ConfigSchemaDeriver.derive`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the `postgresql` connector, which inherits
  `include_views`, `statement_timeout_ms` and `schemas` from `SqlConnector`
- **Steps:** read the derived field names
- **Expected:** all three present
- **Why:** a deriver that saw only the leaf class omits every setting the shared
  base reads — named in the docstring as the failure this walk prevents

### CON-047 · A subclass's default wins over its base's
- **Area:** `connect/config_schema.py::ConfigSchemaDeriver.derive`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a base reading `self.config.get("k", 1)` and a subclass
  reading `self.config.get("k", 2)`
- **Steps:** derive the subclass
- **Expected:** default `2`
- **Why:** most-derived-first plus `setdefault` is the mechanism; reversing it
  shows the base's default in a form that the subclass ignores

### CON-048 · A read with no default is required
- **Area:** `connect/config_schema.py::ConfigSchemaDeriver._literal_default`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `FilesystemConnector`, which reads `root_path` with no
  default
- **Steps:** inspect `required` on that field
- **Expected:** `True`
- **Why:** "required" is not curated — it is derived from the absence of a
  second argument, which is what keeps it true after an edit

### CON-049 · A computed default is real but not rendered
- **Area:** `connect/config_schema.py::ConfigSchemaDeriver._literal_default`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a connector reading `self.config.get("k", SOME_CONSTANT)`
- **Steps:** derive
- **Expected:** the field exists, `required=False`, `default=None`
- **Why:** `ast.literal_eval` cannot evaluate a name; reporting `required=True`
  would make a form demand a value the code already supplies

### CON-050 · The deriver is deliberately syntactic
- **Area:** `connect/config_schema.py::ConfigSchemaDeriver._is_config_get`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a connector reading `self.config.get(key_variable)` and one
  reading `self.config.get(self.credential_field)`
- **Steps:** derive
- **Expected:** neither field is derived; no exception
- **Why:** "a deriver that tried to follow indirection would sometimes be right
  and sometimes silently wrong". `RestConnector` reads the literal `"token"`
  rather than `self.credential_field` for exactly this reason, and that comment
  is the test case

### CON-051 · `audit()` reports an overlay key the code never reads
- **Area:** `connect/config_schema.py::ConnectorConfigSchema.audit`,
  `connect/registry.py::ConnectorRegistry.audit`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a registry with an overlay naming a field the connector does
  not read
- **Steps:** `registry.audit()`
- **Expected:** one finding naming the key and saying the connector never reads
  it
- **Why:** the drift this whole design exists to prevent; it runs in CI and
  fails the build rather than appearing as a subtly wrong input six months later

### CON-052 · The shipped overlays are clean
- **Area:** `connect/builtin.py`, all nine overlays
- **Type:** regression
- **Priority:** P1
- **Precondition:** `register_builtin(ConnectorRegistry())`
- **Steps:** `registry.audit()`
- **Expected:** `[]`
- **Why:** the counterfactual for CON-051, and the assertion that no shipped form
  has drifted. `JDBC_OVERLAY` describes `fetch_size`, which `JdbcConnector`
  reads and never uses — the audit cannot see that, which is CON-093

### CON-053 · An overlay may annotate but not invent
- **Area:** `connect/config_schema.py::ConnectorConfigSchema.build`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an overlay with a key not in the derived set
- **Steps:** build the schema and render `to_form()`
- **Expected:** the invented key appears in `unknown_overlay_keys` and in **no**
  form group
- **Why:** "the overlay may annotate a derived field; it cannot invent one" — a
  rendered field nobody reads is an input that does nothing

### CON-054 · A secret's default is never emitted
- **Area:** `connect/config_schema.py::FieldSpec.to_dict`
- **Type:** security
- **Priority:** P1
- **Precondition:** a field marked `secret=True` whose code default is non-empty
- **Steps:** `to_dict()`
- **Expected:** `"default": None`, `"secret": true`, `"input": "password"`
- **Why:** a form is served to a browser; a default password in it is a
  credential in a page source

### CON-055 · `validate` refuses a supplied secret outright
- **Area:** `connect/config_schema.py::ConnectorConfigSchema.validate`
- **Type:** security
- **Priority:** P1
- **Precondition:** the `postgresql` schema, whose `password` and `dsn` are both
  marked secret
- **Steps:** `registry.create("postgresql", {"host":"h","database":"d","password":"literal"})`
- **Expected:** `ValidationError` naming `password`, remedy "Reference a vault
  entry with credential_ref instead. Connection configuration is exported to Git
  and shown in the UI."
- **Why:** connection configuration is exported; this refusal is what keeps a
  literal out of a repository

### CON-056 · `validate` refuses a missing required field with the field named
- **Area:** `connect/config_schema.py::ConnectorConfigSchema.validate`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `registry.create("filesystem", {})`;
  `registry.create("filesystem", {"root_path": ""})`;
  `registry.create("filesystem", {"root_path": None})`
- **Expected:** `ValidationError` in all three, context listing `root_path`,
  remedy "Fill in the highlighted fields; the connector reads them with no
  default."
- **Why:** "a missing field should be a message beside the input, not a driver
  error twenty seconds into a connection attempt"

### CON-057 · A missing *secret* field is not reported as missing
- **Area:** `connect/config_schema.py::ConnectorConfigSchema.validate`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a schema whose required field is also secret
- **Steps:** validate a config omitting it
- **Expected:** no `ValidationError` for that field
- **Why:** `and not f.secret` is deliberate — the value arrives from the vault at
  connect time, not from the form — but it means a genuinely missing credential
  surfaces as an authentication failure rather than a form error

### CON-058 · `create` validates before constructing
- **Area:** `connect/registry.py::ConnectorRegistry.create`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an invalid config for a connector whose `__init__` would also
  raise
- **Steps:** `registry.create(key, bad_config)`
- **Expected:** the `ValidationError` from the schema, not the connector's own
  `__init__` error
- **Why:** validation first, always; the order is the contract

### CON-059 · An unknown connector key lists the available ones
- **Area:** `connect/registry.py::ConnectorRegistry.get`
- **Type:** negative
- **Priority:** P2
- **Precondition:** the built-in registry
- **Steps:** `registry.get("snowfalke")`
- **Expected:** an error naming the available keys
- **Why:** a typo in a connection record must not become "unknown connector" with
  no list; `capabilities()` calls `get` first for this reason

### CON-060 · `capabilities` on an unknown key raises rather than returning empty
- **Area:** `connect/registry.py::ConnectorRegistry.capabilities`
- **Type:** negative
- **Priority:** P2
- **Precondition:** the built-in registry
- **Steps:** `registry.capabilities("nope")`
- **Expected:** the same registry error as CON-059, not `CapabilityMatrix()`
- **Why:** an empty matrix means "declares nothing", which is a legal answer; a
  typo returning it would silently disable pushdown for a real source

### CON-061 · `register(replace=False)` refuses a duplicate key
- **Area:** `connect/registry.py::ConnectorRegistry.register`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a registry already holding `sqlite`
- **Steps:** register a different class under the same manifest key without
  `replace=True`
- **Expected:** a registry error; the original class is still returned by `get`
- **Why:** a third-party entry point silently shadowing a first-party connector
  is a supply-chain problem, not a configuration one

### CON-062 · `register_builtin` is idempotent
- **Area:** `connect/builtin.py::register_builtin`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a fresh registry
- **Steps:** call it three times; check `len(registry)` and `keys()`
- **Expected:** nine keys each time, no error
- **Why:** the docstring says idempotent, and it is reached from the CLI, the
  console and the API bootstrap independently

### CON-063 · A re-registration invalidates the cached schema
- **Area:** `connect/registry.py::ConnectorRegistry.register` / `.schema`
- **Type:** regression
- **Priority:** P2
- **Precondition:** a registry where `schema(key)` has already been built
- **Steps:** re-register the key with a class reading a different field, then
  read `schema(key)` again
- **Expected:** the new field is present
- **Why:** `self._schemas.pop(key, None)` is the line that makes this true; a
  stale cache serves the previous connector's form for the life of the process

### CON-064 · `of_kind` partitions the registry
- **Area:** `connect/registry.py::ConnectorRegistry.of_kind`
- **Type:** functional
- **Priority:** P3
- **Precondition:** the built-in registry
- **Steps:** call for every `SourceKind`
- **Expected:** `RELATIONAL` → sqlite, postgresql, jdbc, clickhouse, snowflake;
  `FILESYSTEM` → filesystem; `OBJECT_STORE` → objectstore; `API` → rest;
  `DOCUMENT` → mongodb; every other kind empty; the union is all nine with no
  duplicates
- **Why:** the source picker groups by kind, and a connector whose
  `source_kind` was never set lands in `RELATIONAL` by inheritance rather than
  by decision

## `connect/cost.py` and `connect/pacing.py`

### CON-065 · An estimate makes no round trip
- **Area:** `connect/cost.py::CostEstimator.estimate`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a connector instrumented to count queries
- **Steps:** estimate from a `DiscoveredObject` already in hand
- **Expected:** zero queries issued
- **Why:** "an estimate that requires a scan to produce is not a preview" — the
  module's first principle, and it is the whole reason discovery carries sizes

### CON-066 · Unknown is a valid answer and renders as one
- **Area:** `connect/cost.py::CostEstimator._rows` / `_bytes` / `_duration`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** no discovered object, no schema, no throughput
- **Steps:** `estimate(path=("t",))` and `render()`
- **Expected:** `rows is None`, `byte_count is None`,
  `duration_seconds is None`, all three bases `UNKNOWN`, and the sentence ends
  "— duration unknown, nothing has been read through this connection yet."
- **Why:** "a duration invented from a default throughput constant is a
  fabrication, and a confident wrong number is worse for trust than an admitted
  absence"

### CON-067 · A derived byte count says it was derived
- **Area:** `connect/cost.py::CostEstimator._bytes`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a `DiscoveredObject` with `estimated_rows=1000` and no bytes
- **Steps:** estimate
- **Expected:** `byte_count == 128_000`, `bytes_basis is DERIVED`, and a warning
  reading "the source reports rows but not size; volume assumes 128 bytes per
  row"
- **Why:** a preview that presented this as a catalogue figure would be lying
  about a number somebody is using to decide whether to run the scan

### CON-068 · Duration comes from rows, not from bytes, when both are available
- **Area:** `connect/cost.py::CostEstimator._duration`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a catalogue object with rows and bytes, and a `Throughput`
  with both rates set
- **Steps:** estimate
- **Expected:** `duration_seconds == rows / throughput.rows_per_second`,
  `duration_basis is MEASURED`
- **Why:** the catalogue's byte figure is size *on disk* — indexes, TOAST, page
  padding — and measured throughput is bytes *delivered*; dividing one by the
  other is a unit error that overstates duration severalfold on an index-heavy
  table

### CON-069 · Duration from bytes alone is marked derived
- **Area:** `connect/cost.py::CostEstimator._duration`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an object with bytes and no rows, and a throughput
- **Steps:** estimate
- **Expected:** a duration, with `duration_basis is DERIVED` rather than
  `MEASURED`
- **Why:** the two byte figures are not the same measurement, and the basis is
  the only place that is said

### CON-070 · A zero throughput does not divide by zero
- **Area:** `connect/cost.py::CostEstimator._duration`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `Throughput(bytes_per_second=0, rows_per_second=0, …)`
- **Steps:** estimate with rows and bytes known
- **Expected:** `duration_seconds is None`, basis `UNKNOWN`; no
  `ZeroDivisionError`
- **Why:** both guards are `> 0`, and a throughput of zero is what a stalled
  connection records

### CON-071 · A budget breach is named, not merely flagged
- **Area:** `connect/cost.py::CostEstimator._exceeds`, `ScanEstimate.render`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `ReadPolicy(max_rows_read=1000, max_bytes_scanned=1<<20)`
  and an object of 5,000 rows / 10 MB
- **Steps:** estimate and render
- **Expected:** `within_budget is False`; `exceeds` names both limits with the
  numbers formatted (`1,000 rows`, `1.0 MB`); the sentence ends "This exceeds
  …"
- **Why:** "you cannot do that" without the number is a dead end for whoever has
  to decide whether to raise the limit

### CON-072 · At exactly the limit nothing is exceeded
- **Area:** `connect/cost.py::CostEstimator._exceeds`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `max_rows_read=1000` and an estimate of exactly 1,000 rows
- **Steps:** estimate
- **Expected:** `exceeds == ()`, `within_budget is True`
- **Why:** the comparison is `>`, and a limit that refused its own value would
  make every configured ceiling one lower than it reads

### CON-073 · `plan_that_fits` offers a plan rather than a refusal
- **Area:** `connect/cost.py::CostEstimator.plan_that_fits`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an over-budget estimate of 5,000 rows against
  `max_rows_read=1000`
- **Steps:** `plan_that_fits(estimate)`
- **Expected:** `SamplePlan(strategy=SYSTEMATIC, rows=1000, fraction=0.2)`
- **Why:** "'you cannot do that' is a dead end and 'you cannot do that, but this
  would work' is an answer"

### CON-074 · `plan_that_fits` returns None when it cannot help
- **Area:** `connect/cost.py::CostEstimator.plan_that_fits`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** (a) an estimate within budget; (b) an over-budget estimate
  with `rows is None`; (c) an over-budget estimate with no row limit, no byte
  limit
- **Steps:** call for each
- **Expected:** `None` in all three
- **Why:** a fabricated plan against an unknown row count is a sample fraction
  computed from nothing

### CON-075 · `plan_that_fits` derives a row cap from a byte budget
- **Area:** `connect/cost.py::CostEstimator.plan_that_fits`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `ReadPolicy(max_bytes_scanned=1_000_000)` and an estimate of
  10,000 rows / 10,000,000 bytes
- **Steps:** call
- **Expected:** `rows == 1000`, `fraction == 0.1`
- **Why:** `max(1, …)` is the floor; a byte budget smaller than one row must not
  produce a plan of zero rows

### CON-076 · A short read accumulates instead of being discarded
- **Area:** `connect/cost.py::ThroughputRegistry.observe`
- **Type:** regression
- **Priority:** P2
- **Precondition:** a fresh registry
- **Steps:** `observe("c", rows=10, byte_count=1000, seconds=0.01)` five times;
  then `of("c")`
- **Expected:** `None` for the first four; after the fifth (0.05s total, the
  `MINIMUM_TIMED_SECONDS` floor) a `Throughput` of 1,000 rows/s and
  100,000 bytes/s
- **Why:** the docstring records the measured failure — "an estate of a thousand
  small tables consists entirely of such reads, and every one of the thousand
  was discarded and the estimator learned nothing at all"

### CON-077 · A read of zero rows teaches nothing
- **Area:** `connect/cost.py::ThroughputRegistry.observe`,
  `Throughput.from_read`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a fresh registry
- **Steps:** `observe("c", rows=0, byte_count=0, seconds=10)`; and
  `Throughput.from_read(rows=0, byte_count=0, seconds=10)`
- **Expected:** nothing recorded, nothing pending; `from_read` returns `None`
- **Why:** an empty table read in ten seconds is a fact about the table, not the
  connection; averaging it in makes every later estimate slower

### CON-078 · Merged throughput is weighted by sample count
- **Area:** `connect/cost.py::Throughput.merged_with`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a 100-sample throughput of 1,000 rows/s and a 1-sample one
  of 1 row/s
- **Steps:** merge
- **Expected:** ≈ 990 rows/s, `samples == 101`, `measured_at` the later of the
  two
- **Why:** "one slow morning does not dominate"; a plain average would move the
  estimate by half

### CON-079 · `_render_bytes` and `_render_duration` at the boundaries
- **Area:** `connect/cost.py::_render_bytes` / `_render_duration`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** render `0`, `1023`, `1024`, `1024**5`; and `0.4`, `1`, `89`, `90`,
  `5399`, `5400`
- **Expected:** `0 B`, `1,023 B`, `1.0 KB`, a TB figure (never a PB);
  `under a second`, `1 seconds`, `89 seconds`, `2 minutes`, `90 minutes`,
  `1.5 hours`
- **Why:** these strings are the preview a data architect reads; `1 seconds` is
  the kind of wrongness that makes the whole sentence look generated

### CON-080 · `LoadPacer.pause_after` implements the duty cycle
- **Area:** `connect/pacing.py::LoadPacer.pause_after`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `LoadPacer(0.05)`
- **Steps:** `pause_after(0.1)`
- **Expected:** ≈ 1.9 s — `work * (1/c - 1)`, so a 100 ms batch is followed by
  waiting until roughly two seconds have passed
- **Why:** the module docstring's worked example, and the arithmetic every other
  property here rests on

### CON-081 · Pacing is inactive at a ceiling of 0 or 1
- **Area:** `connect/pacing.py::LoadPacer.is_active` / `.pause_after`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** pacers at `0.0`, `1.0`, `1.5`, `-0.1`, `0.999`
- **Steps:** read `is_active` and `pause_after(1.0)`
- **Expected:** inactive with a pause of 0.0 for all but `0.999`, which is active
- **Why:** `0 < c < 1`; a negative or >1 ceiling must read as "no pacing" rather
  than produce a negative sleep

### CON-082 · A capped pause is counted and logged
- **Area:** `connect/pacing.py::LoadPacer._wait`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `LoadPacer(0.01, max_pause_seconds=30.0)` and a batch taking
  10 s (implied pause 990 s)
- **Steps:** pace one batch
- **Expected:** the actual wait is 30 s, `report.capped_pauses == 1`, and the
  debug log says the read will exceed its share
- **Why:** "a read that never finishes is not a polite read — it is a connection
  held open against a production database all night", and the overshoot has to
  be visible rather than silent

## `connect/sources/sql/` — the shared base and the dialects

`SqlConnector` owns health, discovery, description, snapshot and paged reading;
a dialect owns quoting, the catalogue queries, the row estimate, the sampling
clause and the session setup. Four dialects have been run against a live
database (PostgreSQL, MySQL, ClickHouse, and PostgreSQL over JDBC); eight say in
their own docstring that nothing has answered them.

### CON-083 · Reading cannot write, and the server enforces it
- **Area:** `connect/sources/sql/postgres.py::PostgresDialect.session_setup_sql`
- **Type:** security
- **Priority:** P1
- **Precondition:** a live PostgreSQL
- **Steps:** open the connector, then issue `DELETE FROM positions` on an
  acquired connection
- **Expected:** the server refuses — `default_transaction_read_only = on` is set
  in the pool's `setup`
- **Why:** "our own care about not writing is not the guarantee a customer
  should have to rely on"; the equivalent SQLite assertion exists in the
  conformance suite and the PostgreSQL one is the harder and more important half

### CON-084 · Every statement carries a timeout
- **Area:** `connect/sources/sql/postgres.py::PostgresDialect.session_setup_sql`
- **Type:** security
- **Priority:** P1
- **Precondition:** a live PostgreSQL and a connector with
  `statement_timeout_ms=500`
- **Steps:** run `SELECT pg_sleep(5)` through `_fetch`
- **Expected:** the server cancels it; `classify_failure` reports `DEGRADED`
  with "the source did not respond in time"
- **Why:** "Prama reading a table must never be able to pin the database the
  business is using" — and the four settings (`statement_timeout`,
  `lock_timeout`, `idle_in_transaction_session_timeout`, read-only) are the
  connector's whole safety claim

### CON-085 · The connection identifies itself
- **Area:** `connect/sources/sql/postgres.py::PostgresConnector._connection_arguments`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a live PostgreSQL
- **Steps:** open, then read `application_name` from `pg_stat_activity`
- **Expected:** `prama`, or whatever was configured
- **Why:** "a DBA who finds an unfamiliar query eating a production box at 3am
  should be able to see whose it is without asking anyone"

### CON-086 · A DSN and explicit fields are alternatives, not a merge
- **Area:** `connect/sources/sql/postgres.py::PostgresConnector._connection_arguments`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a config with both `dsn` and `host`/`port`/`database`
- **Steps:** inspect the arguments
- **Expected:** only `dsn`, `timeout` and `server_settings` — the explicit fields
  are silently ignored
- **Why:** a form that accepts both and honours one is a configuration whose
  effective value nobody can read off the page; record whether this silent
  precedence is stated anywhere a user sees

### CON-087 · `ssl_mode` of `disable` means no TLS argument at all
- **Area:** `connect/sources/sql/postgres.py::PostgresConnector._connection_arguments`
- **Type:** security
- **Priority:** P2
- **Precondition:** configs with `ssl_mode` of `disable`, `""`, `prefer`,
  `verify-full`, and an invented `verify-nothing`
- **Steps:** inspect the `ssl` argument
- **Expected:** `None` for the first two, the literal string for the rest — and
  the invented value reaches asyncpg unvalidated
- **Why:** the overlay's help lists five legal modes and nothing enforces them;
  a typo silently becomes whatever the driver does with an unknown mode

### CON-088 · Health separates "cannot connect" from "cannot read the catalogue"
- **Area:** `connect/sources/sql/base.py::SqlConnector.health`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a source where `SELECT 1` succeeds and `discover()` raises
  (a) a permission error, (b) a type error from the driver
- **Steps:** `await c.health()`
- **Expected:** (a) `UNAUTHORISED` with `missing_permissions=("catalogue read",)`;
  (b) `DEGRADED` with "This is not a permissions failure — the connection and
  the credential both worked."
- **Why:** the comment records the real cost: "a driver returning a type this
  code cannot use failed here as UNAUTHORISED, which cost real time". Assuming a
  grant sends somebody to ask for one they already have

### CON-089 · `classify_failure` keys off words in the driver's message
- **Area:** `connect/sources/sql/base.py::SqlConnector.classify_failure`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** exceptions whose text contains `password`, `authentication`,
  `permission`, `denied`, `timeout`, `timed out`, and one containing none
- **Steps:** classify each; and classify an exception reading
  `relation "permissions" does not exist`
- **Expected:** UNAUTHORISED, UNAUTHORISED, UNAUTHORISED, UNAUTHORISED,
  DEGRADED, DEGRADED, UNREACHABLE — and record that the last case is
  misclassified as UNAUTHORISED because a *table named* `permissions` contains
  the substring
- **Why:** substring matching on a driver's prose is the mechanism; the failure
  mode is a table name that happens to contain one of the six words

### CON-090 · `_split` defaults an unqualified path to the `public` schema
- **Area:** `connect/sources/sql/base.py::SqlConnector._split`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** paths `("t",)`, `("s","t")`, `("c","s","t")`
- **Steps:** split each
- **Expected:** `("public","t")`, `("s","t")`, `("s","t")` — the catalogue
  segment of a three-part Databricks or BigQuery name is dropped
- **Why:** `DatabricksDialect`'s docstring says "the connector's path carries
  it, and a dialect that assumed two would address the wrong table in the
  default catalogue rather than failing". `_split` takes the last two, so the
  catalogue is silently dropped before the dialect ever sees it

### CON-091 · A row estimate is never bought with a scan
- **Area:** `connect/sources/sql/base.py::SqlConnector._estimate_rows`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a dialect whose `estimate_rows_sql()` returns `None`
  (Databricks, Trino)
- **Steps:** `describe(path)`
- **Expected:** `estimated_rows is None`; no `count(*)` issued
- **Why:** "a `count(*)` against a billion-row production table, issued because
  somebody opened a dataset page, is not something a business tool should ever
  do"

### CON-092 · A failed row estimate is a debug line, not an error
- **Area:** `connect/sources/sql/base.py::SqlConnector._estimate_rows`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a source whose estimate query raises
- **Steps:** `describe(path)`
- **Expected:** the schema is still returned with `estimated_rows is None`
- **Why:** a missing statistic must not take a description down; the columns are
  the answer the caller asked for

### CON-093 · A negative catalogue estimate becomes unknown
- **Area:** `connect/sources/sql/base.py::SqlConnector._estimate_rows`,
  `dialects.py::Db2Dialect.estimate_rows_sql`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a dialect returning `-1` (DB2's CARD before RUNSTATS)
- **Steps:** describe
- **Expected:** `None`, not `-1` and not `0`
- **Why:** "'nobody has run RUNSTATS on this table' and 'this table is empty' are
  different facts, and the second is a finding". The base clamps with
  `estimate if estimate >= 0 else None`; DB2 also clamps in SQL, so both halves
  need a case

### CON-094 · A row budget caps exactly; a byte budget overshoots by one batch
- **Area:** `connect/sources/sql/base.py::_Budget`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a table of 25,000 rows; policies of
  `max_rows_read=10_000` and `max_bytes_scanned=1`
- **Steps:** read fully under each and count rows
- **Expected:** exactly 10,000 under the row cap; under the byte cap, exactly one
  batch and then a stop
- **Why:** the class docstring states the asymmetry as a real limit — "a byte
  ceiling may be overshot by at most one batch … a caller who needs a hard byte
  cap sets a row cap too" — and that sentence is a test

### CON-095 · `batch_rows` never fetches more than the read will keep
- **Area:** `connect/sources/sql/base.py::_Budget.batch_rows`
- **Type:** performance
- **Priority:** P2
- **Precondition:** budgets with no row limit; with `plan.rows=25`; with
  `plan.rows=1_000_000`; with `plan.rows=0`
- **Steps:** read `batch_rows`
- **Expected:** 10,000; 25; 10,000; 1
- **Why:** "fetching ten thousand rows across the network to discard all but
  twenty-five is work a production database does on the customer's behalf for no
  reason" — and `max(1, …)` is what stops a zero-row plan asking for zero rows
  for ever

### CON-096 · A truncated read says so in the log and in `last_read`
- **Area:** `connect/sources/sql/base.py::_Budget.report`,
  `SqlConnector._record_read`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a read that hits a ceiling
- **Steps:** read to completion; inspect the log and `connector.last_read`
- **Expected:** an INFO line naming the object, the row count and the byte
  count; `last_read` carries `rows`, `bytes`, `seconds` and a `pacing` report
- **Why:** a silently truncated read produces a violation count that is a floor
  presented as a count; and `last_read` is what feeds the next cost preview

### CON-097 · Pacing time is excluded from the recorded read duration
- **Area:** `connect/sources/sql/base.py::SqlConnector._record_read`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a read paced at `load_ceiling=0.05`
- **Steps:** read and inspect `last_read["seconds"]` against the wall clock
- **Expected:** the recorded seconds are the *working* time only, roughly a
  twentieth of the elapsed
- **Why:** "folding it into a throughput measurement would make every subsequent
  estimate progressively slower for no reason"

### CON-098 · `run_metric_query` refuses rows with no column names
- **Area:** `connect/sources/sql/base.py::SqlConnector.run_metric_query`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a connector whose `_column_names()` returns `()` after a
  fetch
- **Steps:** run a metric query
- **Expected:** `ConnectorError` saying "the source returned rows without column
  names", remedy attributing it to the driver rather than the control
- **Why:** "a metric dictionary with invented keys would be judged against the
  wrong thresholds" — a wrong verdict rather than a failure

### CON-099 · `_column_names` is stale between a `_fetch` and a `_stream`
- **Area:** `connect/sources/sql/base.py::SqlConnector.run_metric_query`,
  `postgres.py::PostgresConnector._stream` / `_column_names`
- **Type:** regression
- **Priority:** P1
- **Precondition:** the PostgreSQL connector
- **Steps:** `read()` a table with columns A,B; then `run_metric_query` returning
  columns C,D; inspect the returned dictionaries' keys
- **Expected:** keys C,D
- **Why:** `_stream_columns` is set only by `_stream`, and `run_metric_query`
  calls `_fetch` and then reads `_column_names()`. On PostgreSQL that returns
  the *previous stream's* names — and `zip(..., strict=False)` silently
  truncates or drops rather than raising. Pin what the keys actually are

### CON-100 · Every identifier from a catalogue is quoted
- **Area:** `connect/sources/sql/dialect.py::SqlDialect.quote`, and each override
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** quote `x"; DROP TABLE y --` on the base, Snowflake and Oracle;
  `x]; DROP --` on SQL Server; `` x`; DROP -- `` on MySQL and Databricks;
  `` a\ `` and `` a`b `` on ClickHouse and BigQuery
- **Expected:** the embedded delimiter is doubled (or backslash-escaped for
  ClickHouse/BigQuery, backslash first); the result is a single identifier and
  delimiter parity holds for the rest of the statement
- **Why:** "object names arrive from a catalogue that a customer controls, and
  they reach a query string". Finding S5 was exactly the ClickHouse/BigQuery
  case: escaping the backtick and not the backslash leaves `` `a\` `` an
  identifier that never closes

### CON-101 · The placeholder style belongs to the driver, not the database
- **Area:** `connect/sources/sql/jdbc.py::_as_jdbc`,
  `dialect.py::SqlDialect.placeholder`
- **Type:** regression
- **Priority:** P1
- **Precondition:** the same `PostgresDialect` instance shared by the native
  connector
- **Steps:** build a JDBC connector with `dialect: postgresql`; then check the
  native `PostgresConnector.dialect.placeholder(1)`
- **Expected:** the JDBC copy yields `?`; the native one still yields `$1`
- **Why:** `_as_jdbc` copies rather than mutating precisely because the dialect
  instances are shared; mutating in place changes how the native connector binds
  and the symptom is "column index out of range" a long way from the cause

### CON-102 · A JDBC source refuses to open without a dialect
- **Area:** `connect/sources/sql/jdbc.py::JdbcConnector.open`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a config with a URL, driver class and jar but no `dialect`
- **Steps:** `await c.open()`
- **Expected:** `ConnectorError`, code `CONNECT.NO_DIALECT`, remedy listing
  `DIALECTS` and explaining that guessing would send one database's SQL to
  another
- **Why:** "JDBC is a transport, not a dialect" — and the consequence of
  guessing is a control that compiles and then fails at the source

### CON-103 · An unknown dialect name lists the known ones at construction
- **Area:** `connect/sources/sql/jdbc.py::JdbcConnector._resolve_dialect`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `dialect: "oracel"`
- **Steps:** construct the connector
- **Expected:** `ConnectorError`, code `CONNECT.UNKNOWN_DIALECT`, remedy listing
  all twelve; raised from `__init__`, before any connection attempt
- **Why:** `DIALECTS` is built from the dialect classes rather than typed a
  second time, so the list in the message cannot name a renamed dialect

### CON-104 · Each of the three JDBC connection fields is refused by name
- **Area:** `connect/sources/sql/jdbc.py::JdbcConnector.open`
- **Type:** negative
- **Priority:** P2
- **Precondition:** configs each missing one of `jdbc_url`, `driver_class`,
  `driver_path`
- **Steps:** open
- **Expected:** `ConnectorError` code `CONNECT.INCOMPLETE` naming the missing
  field, remedy "Prama does not ship drivers and will not fetch one"
- **Why:** the driver is somebody else's code running in our process; the
  deployment chooses it and the refusal has to say which part is missing

### CON-105 · `fetch_size` is read, offered in the form, and never used
- **Area:** `connect/sources/sql/jdbc.py::JdbcConnector.__init__` /
  `._stream`, `connect/builtin.py::JDBC_OVERLAY`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** none
- **Steps:** grep `_fetch_size` in `jdbc.py`; then read `_stream`'s docstring
- **Expected:** the docstring says "`fetchmany` rather than `fetchall`, **and the
  JDBC fetch size set on the statement**: without both, the driver materialises
  the whole result set in the JVM heap and a table read fails on memory". No
  code sets it — `self._fetch_size` has exactly one reference, its assignment
- **Why:** the overlay renders the field with help text explaining why it
  matters; a setting the form offers, the docstring depends on, and the code
  ignores is the exact drift `audit()` was built to catch and cannot see

### CON-106 · A JDBC decimal arrives as a `Decimal`
- **Area:** `connect/sources/sql/jdbc.py::_exact_decimal_converter`,
  `_use_exact_decimals`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a live JDBC source with a `numeric(38,12)` column holding
  `1953193.464900000000`
- **Steps:** read it
- **Expected:** a `decimal.Decimal` with every digit intact — never a float
- **Why:** "it is the same double-rounding that once reported 131 rows of a clean
  blotter as a cent out"; JayDeBeApi's own converter calls
  `BigDecimal.doubleValue()`

### CON-107 · Converters are replaced in both tables the bridge keeps
- **Area:** `connect/sources/sql/jdbc.py::_use_exact_decimals`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** a process where something else started the JVM first, so the
  bridge has already snapshotted `_DEFAULT_CONVERTERS` into `_converters`
- **Steps:** open a JDBC connector and read a decimal
- **Expected:** still a `Decimal`
- **Why:** the docstring names the symptom — "money arriving as a float on some
  runs and not others, which is close to undebuggable"; replacing only the
  defaults works when Prama opens first and silently does nothing when it does
  not

### CON-108 · A `BigInteger` row count does not break discovery
- **Area:** `connect/sources/sql/jdbc.py::_exact_integer_converter`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a live MySQL over Connector/J
- **Steps:** `discover()`
- **Expected:** every table listed with an int row estimate
- **Why:** "MySQL answers TABLE_ROWS as a BigInteger, and `int(that)` raises —
  which surfaced as *discovery failing on every MySQL table* rather than as
  anything about types"

### CON-109 · A failed `open` leaks neither a thread nor a JVM attachment
- **Area:** `connect/sources/sql/jdbc.py::JdbcConnector.open`,
  `snowflake.py::SnowflakeConnector.open`,
  `clickhouse.py::ClickHouseConnector.open`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** bad credentials for each
- **Steps:** attempt `async with connector:` three times, then let the
  interpreter exit
- **Expected:** the error propagates each time, the worker thread count returns
  to its baseline, and the interpreter exits promptly
- **Why:** "Python does not call `__aexit__` when `__aenter__` raises, so nothing
  else ever closes this … JPype's shutdown waits for attached threads, which
  hangs the interpreter at exit, a long way from anything explanatory. Bad
  credentials are an ordinary failure; three of them should not stop the process
  exiting."

### CON-110 · `close` detaches the JDBC thread from the JVM
- **Area:** `connect/sources/sql/jdbc.py::_detach_from_jvm`
- **Type:** concurrency
- **Priority:** P2
- **Precondition:** the `jdbc` extra and a JRE
- **Steps:** open and close a JDBC connector, then exit
- **Expected:** the interpreter exits without hanging; `_detach_from_jvm` runs
  *on the worker thread*, not the caller's
- **Why:** detaching from the wrong thread is a no-op that looks like a fix

### CON-111 · ClickHouse binds `?` as a String, whatever the value is
- **Area:** `connect/sources/sql/clickhouse.py::_bind`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** the ClickHouse connector
- **Steps:** bind a query with an integer parameter; and bind a query whose SQL
  contains a literal `'?'` inside a string
- **Expected:** the integer arrives as `{p0:String}`; the literal question mark
  is consumed as a placeholder and the parameter indices shift
- **Why:** the converter walks characters with no awareness of string literals.
  Every current call site passes two strings (schema and table), which is why
  this has never bitten — record it as the constraint it is

### CON-112 · ClickHouse pages a stream with LIMIT/OFFSET
- **Area:** `connect/sources/sql/clickhouse.py::ClickHouseConnector._stream`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a live ClickHouse table of 25,000 rows
- **Steps:** read fully; then read with a predicate
- **Expected:** every row exactly once, no duplicates across page boundaries,
  and the predicate's `WHERE` sits before the appended `LIMIT … OFFSET …`
- **Why:** `_stream` appends its paging clause to whatever `stream_sql` built; an
  unordered `OFFSET` on a merging column store can repeat or skip rows between
  pages, and nothing here orders

### CON-113 · A dialect with no snapshot marker says wall-clock and admits it
- **Area:** `connect/sources/sql/base.py::SqlConnector.snapshot`
- **Type:** functional
- **Priority:** P1
- **Precondition:** ClickHouse (`snapshot_sql()` returns `None`)
- **Steps:** `await c.snapshot(("db","t"))`
- **Expected:** `kind is WALL_CLOCK`, `exact is False`, and `detail["note"]`
  reading "<dialect> offers no point-in-time marker; this snapshot cannot be
  replayed exactly"
- **Why:** "evidence recorded against it cannot claim to be replayable"; the note
  is what an auditor reads

### CON-114 · PostgreSQL's snapshot follows recovery state
- **Area:** `connect/sources/sql/postgres.py::PostgresDialect.snapshot_sql`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a live primary and a live standby
- **Steps:** snapshot both twice with a write in between
- **Expected:** the primary's identifier advances via `pg_current_wal_lsn`; the
  standby's via `pg_last_wal_replay_lsn` and also advances
- **Why:** "on a standby the write position does not advance, so every snapshot
  taken against a read replica would be identical, and evidence would silently
  stop being replayable"

### CON-115 · `sample_from` is BERNOULLI, not SYSTEM
- **Area:** `connect/sources/sql/postgres.py::PostgresDialect.sample_from`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a live PostgreSQL table whose rows were inserted in date
  order
- **Steps:** take a 1% sample twice with the same seed, and compare the date
  distribution against the table's
- **Expected:** `TABLESAMPLE BERNOULLI (1)` in the SQL; the sample's date
  distribution matches the table's; the two samples are identical
- **Why:** "system sampling picks whole pages, so rows that were inserted
  together are selected together, and any column correlated with insertion order
  — a date, a branch, a batch id — comes back badly skewed"

### CON-116 · A fraction is clamped into a legal percentage
- **Area:** `connect/sources/sql/postgres.py::PostgresDialect.sample_from`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** plans with `fraction` of `0`, `1e-12`, `1.0`, `2.0`, `None`
- **Steps:** render `sample_from`
- **Expected:** percentages of `1e-06`, `1e-06`, `100`, `100`, and `1` (the
  0.01 default); never `0` and never above `100`
- **Why:** `TABLESAMPLE (0)` returns nothing and would be reported as a clean
  empty table; above 100 is a syntax error

### CON-117 · Stratified sampling is refused rather than quietly unstratified
- **Area:** `connect/sources/sql/postgres.py::sample_plan_is_supported`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `SamplePlan(strategy=STRATIFIED, stratify_by=("region",))`
- **Steps:** `sample_plan_is_supported(plan)`; then grep for callers
- **Expected:** `False` — and **no caller in `src/`**, so a stratified plan
  reaches `sample_from` and returns an unstratified sample
- **Why:** the docstring names it exactly: "the kind of quiet substitution that
  makes a profile untrustworthy without making it look wrong". A guard nothing
  calls is not a guard

### CON-118 · The base `select_sql` drops a predicate
- **Area:** `connect/sources/sql/dialect.py::SqlDialect.select_sql` vs
  `.stream_sql`
- **Type:** regression
- **Priority:** P1
- **Precondition:** `SamplePlan(predicate="booked = DATE '2026-04-01'")`
- **Steps:** render both `select_sql(path, plan, 100, 0)` and
  `stream_sql(path, plan)` on the base dialect and on Oracle, SQL Server, DB2,
  Teradata, MySQL, Redshift
- **Expected:** the predicate appears in both
- **Why:** `stream_sql` appends `WHERE {plan.predicate}`; `select_sql` and every
  override ignore `plan.predicate` entirely. `SqlConnector.read` uses
  `stream_sql`, so this is latent — but a connector reaching for `select_sql`
  would read the whole object and label it one segment, which is the exact
  failure `require_predicate_support` exists to prevent

### CON-119 · `stream_sql` with a sample and a predicate composes legally
- **Area:** `connect/sources/sql/dialect.py::SqlDialect.stream_sql`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a sampled plan with a predicate, on PostgreSQL, Snowflake,
  Oracle, SQL Server, Trino, BigQuery and Databricks
- **Steps:** render and parse the SQL against each dialect's grammar
- **Expected:** valid SQL in every case
- **Why:** `stream_sql` appends `WHERE …` after `sample_from(...)`, and several
  dialects' sampling clauses are table-level suffixes; `SELECT * FROM t
  TABLESAMPLE BERNOULLI (1) WHERE x` is legal on PostgreSQL and needs checking
  everywhere else

### CON-120 · Every "never run" dialect still says so
- **Area:** `connect/sources/sql/dialects.py`, `snowflake.py`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** for each of Oracle, SQL Server, DB2, Teradata, Redshift,
  Databricks, Synapse, Trino, BigQuery and Snowflake, assert the class or module
  docstring still carries its "never run against a …" sentence, and that
  `SnowflakeConnector.manifest().verification == "code_complete"`
- **Expected:** every warning is still present, and every one of the ten
  connectors or dialects reachable from `DIALECTS` that no live database has
  answered is `code_complete` rather than `verified`
- **Why:** "a test asserts this paragraph is still here, so it cannot quietly
  become a claim" — the connector picker shows the description, and a warning
  that stays in the source is not a warning

### CON-121 · `_as_bool` reads nullability in all three shapes
- **Area:** `connect/sources/sql/base.py::_as_bool`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** evaluate for `True`, `False`, `"YES"`, `"no"`, `" y "`, `"T"`,
  `"1"`, `1`, `0`, `None`, `""`, `"MAYBE"`
- **Expected:** `True, False, True, False, True, True, True, True, False, False,
  False, False`
- **Why:** MySQL's `describe_sql` returns a comparison, Oracle returns a CASE of
  1/0, and `information_schema` returns `YES`/`NO`; getting one wrong inverts a
  whole table's nullability and every completeness control derived from it

## `connect/sources/sqlite.py`

### CON-122 · The file is opened read-only by the driver
- **Area:** `connect/sources/sqlite.py::SqliteConnector._connect`
- **Type:** security
- **Priority:** P1
- **Precondition:** a writable SQLite file
- **Steps:** attempt `DELETE FROM positions` on a connection from `_connect`
- **Expected:** `sqlite3.OperationalError` matching "readonly"
- **Why:** `file:…?mode=ro` means the guarantee is enforced by the driver rather
  than by our discipline; pointing Prama at a production extract cannot alter it

### CON-123 · `snapshot` is size, mtime and page count — not `data_version`
- **Area:** `connect/sources/sqlite.py::SqliteConnector.snapshot`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a SQLite file
- **Steps:** snapshot; insert a row through a second connection; snapshot again
  from a *fresh* connector
- **Expected:** the two identifiers differ
- **Why:** the docstring names the trap: `PRAGMA data_version` "reports changes
  made by *other* connections during the life of the current one, so a fresh
  connection always reads 1 no matter what has happened to the file … anything
  built on it — incremental profiling above all — would trust a stale profile
  for ever while believing it had checked"

### CON-124 · An unchanged file snapshots identically
- **Area:** `connect/sources/sqlite.py::SqliteConnector._file_identity`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an untouched SQLite file
- **Steps:** snapshot twice
- **Expected:** the same identifier, and `exact is True`
- **Why:** the counterfactual for CON-123, and the property replay depends on

### CON-125 · A change that preserves size and mtime is not detected
- **Area:** `connect/sources/sqlite.py::SqliteConnector._file_identity`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a file edited in place to the same byte length, with mtime
  restored and page count unchanged
- **Steps:** snapshot before and after
- **Expected:** the identifiers match — record this as the stated limit
- **Why:** "a change that preserved all three is not something that happens by
  accident" is the claim; nanosecond mtime is what makes it hold, and a
  filesystem with coarse mtime granularity weakens it

### CON-126 · A view that cannot be evaluated still appears in discovery
- **Area:** `connect/sources/sqlite.py::SqliteConnector._list_objects`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a view over a dropped table
- **Steps:** `discover()`
- **Expected:** the view is listed with `estimated_rows is None`; no exception
- **Why:** a broken view is a finding about the estate; failing discovery on it
  hides every healthy object beside it

### CON-127 · `sqlite_%` internal tables are excluded
- **Area:** `connect/sources/sqlite.py::_list_objects`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a file with an `AUTOINCREMENT` table, so `sqlite_sequence`
  exists
- **Steps:** `discover()`
- **Expected:** `sqlite_sequence` absent
- **Why:** surfacing server-owned objects buries the customer's own tables in
  catalogue noise

### CON-128 · A read with no object named is refused
- **Area:** `connect/sources/sqlite.py::SqliteConnector._check_permitted`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `describe(())`, `snapshot(())`, `read(())`
- **Expected:** `ConnectorError` code `CONNECT.OBJECT_MISSING`, remedy "Give the
  table or view name."
- **Why:** an empty path would index `path[0]` and raise `IndexError`; the guard
  is what turns it into a message

### CON-129 · A non-FULL, non-HEAD plan produces a deterministic ordering
- **Area:** `connect/sources/sqlite.py::SqliteConnector._select`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a table of 1,000 rows and
  `SamplePlan(strategy=SYSTEMATIC, rows=100, seed=42)`
- **Steps:** read twice, compare the row ids; then read with `seed=43`
- **Expected:** identical both times at seed 42; a different set at 43
- **Why:** "a seeded ordering is deterministic and honest about being a sample
  rather than pretending to be a scan"; a sampled verdict can only carry an
  honest confidence if it is reproducible

### CON-130 · A seed of 0 does not collapse the ordering
- **Area:** `connect/sources/sqlite.py::SqliteConnector._select`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `SamplePlan(strategy=SYSTEMATIC, rows=100, seed=0)`
- **Steps:** render the SQL
- **Expected:** `ORDER BY (rowid * 1 % 1000003)` — the `or 1` fallback — which is
  rowid order for any table under a million rows, i.e. effectively HEAD
- **Why:** the default `SamplePlan.seed` is 0, so an unseeded systematic sample
  is the first n rows wearing a representative label. `is_representative`
  returns `True` for `SYSTEMATIC`, so a rate measured here would be extrapolated

### CON-131 · Paging a systematic sample repeats the ORDER BY per batch
- **Area:** `connect/sources/sqlite.py::SqliteConnector.read` / `._read_batch`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a 25,000-row table read with a systematic plan
- **Steps:** read fully and count distinct row ids
- **Expected:** 25,000 distinct ids, none repeated across the three batches
- **Why:** each batch is a separate connection and a separate `ORDER BY … LIMIT …
  OFFSET`; the expression must be a total order or a row can appear twice

## `connect/sources/filesystem.py`

### CON-132 · A path outside the root is refused
- **Area:** `connect/sources/filesystem.py::FilesystemConnector._resolve`
- **Type:** security
- **Priority:** P1
- **Precondition:** a root directory with a sibling file outside it
- **Steps:** `describe(("..", "secret.csv"))` and
  `read(("..", "..", "etc", "passwd"))`
- **Expected:** refused — record whether the refusal comes from the read policy,
  from `is_file()`, or not at all
- **Why:** `_resolve` does `self._root.joinpath(*path)` with no containment
  check, and `permits_path` returns `True` for an empty allow-list. A dataset
  path comes from a stored declaration, but the object-store connector's
  equivalent is reached from a URL

### CON-133 · A filename containing a quote does not break the reader expression
- **Area:** `connect/sources/filesystem.py::FilesystemConnector._reader`
- **Type:** security
- **Priority:** P1
- **Precondition:** a file named `it's_data.csv` in the root
- **Steps:** discover it, then describe and read it
- **Expected:** both succeed; the DuckDB expression has the quote doubled
- **Why:** the filename is under a data supplier's control and reaches a SQL
  string; `_escape`-style doubling is the only thing between that and a
  syntax error at best

### CON-134 · An unsupported extension is refused with the supported list
- **Area:** `connect/sources/filesystem.py::FilesystemConnector._reader`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `data.xyz` and a file with no extension in the root
- **Steps:** `describe(("data.xyz",))` and `describe(("README",))`
- **Expected:** `ConnectorError` code `CONNECT.FORMAT_UNSUPPORTED`; the second
  message reads "cannot read a file with no extension"; both remedies list the
  eight supported extensions
- **Why:** a landing zone contains checksums, manifests and notes; the refusal
  has to say what *is* readable

### CON-135 · Non-data files are invisible to discovery
- **Area:** `connect/sources/filesystem.py::FilesystemConnector._candidates`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a root with one CSV and one `.md`
- **Steps:** `discover()`
- **Expected:** only the CSV
- **Why:** the extension filter is what stops a landing zone's README appearing
  as a dataset

### CON-136 · The digest ceiling bounds the hashing
- **Area:** `connect/sources/filesystem.py::FilesystemConnector.snapshot`
- **Type:** performance
- **Priority:** P2
- **Precondition:** a 200 MB file and `max_file_bytes` unset, then set to 1 MB
- **Steps:** snapshot under each
- **Expected:** unset hashes 64 MB (the default) and reports
  `detail["hashed_bytes"] == 67_108_864`; at 1 MB it hashes 1 MB and says so
- **Why:** "an exact identifier for a 40 GB extract is not worth 40 GB of
  reading"; the reported `hashed_bytes` is how a reader knows how much of the
  file the identifier covers

### CON-137 · Two files with the same prefix and different tails snapshot differently
- **Area:** `connect/sources/filesystem.py::FilesystemConnector.snapshot`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two files identical for their first 1 MB, differing after,
  with `max_file_bytes=1048576`, and different sizes
- **Steps:** snapshot both
- **Expected:** different identifiers — size and mtime are folded in after the
  truncated content hash
- **Why:** "the size and modification time recorded alongside make a collision
  implausible" is the claim that makes the ceiling safe; two files of the *same*
  size differing only past the ceiling is the case that breaks it, and it should
  be recorded rather than asserted away

### CON-138 · `snapshot` reports `hashed_bytes` no larger than the file
- **Area:** `connect/sources/filesystem.py::FilesystemConnector.snapshot`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a 10-byte file
- **Steps:** snapshot
- **Expected:** `detail["hashed_bytes"] == 10`, not the 1 MB chunk size
- **Why:** `min(read, stat.st_size)` is the clamp; without it a small file
  reports more bytes hashed than it holds

### CON-139 · An empty file is readable, not an error
- **Area:** `connect/sources/filesystem.py::FilesystemConnector.describe` /
  `.read` / `.snapshot`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a zero-byte `.csv` and a header-only `.csv`
- **Steps:** describe, snapshot and read both
- **Expected:** the header-only file describes its columns with
  `estimated_rows == 0` and reads zero batches; the zero-byte file's behaviour is
  recorded (DuckDB's `read_csv_auto` on an empty file)
- **Why:** "an empty table reports pass" is open finding Q-09; the read path has
  to make the emptiness visible for the judgement path to have anything to act on

### CON-140 · Concurrent reads do not close each other's streams
- **Area:** `connect/sources/filesystem.py::FilesystemConnector.read`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** one connector and two large files
- **Steps:** start two `read` iterations concurrently and interleave their
  `anext` calls
- **Expected:** both complete with every row
- **Why:** "a DuckDB connection carries a single result stream, so two
  concurrent reads close each other's — and segmented profiling reads its
  segments concurrently". The `cursor()` per read is what makes this hold

### CON-141 · A read does not block the event loop
- **Area:** `connect/sources/filesystem.py::FilesystemConnector.read`
- **Type:** performance
- **Priority:** P2
- **Precondition:** a large Parquet file and a concurrent task ticking a counter
  every millisecond
- **Steps:** read the file while the ticker runs
- **Expected:** the ticker keeps ticking throughout
- **Why:** "blocking the event loop to read a file stalls every other control in
  the process, appearing as unexplained latency somewhere else entirely"; every
  DuckDB call here is wrapped in `asyncio.to_thread` for that reason

### CON-142 · The filesystem connector ignores the read policy's budgets
- **Area:** `connect/sources/filesystem.py::FilesystemConnector.read`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `ReadPolicy(max_rows_read=100, max_bytes_scanned=1024)` and a
  100,000-row Parquet file
- **Steps:** read fully and count rows
- **Expected:** record the actual count
- **Why:** `SqlConnector.read` builds a `_Budget` from the policy and the SQL
  base docstring states "a read has a ceiling … exceeding one truncates the read
  and says so". The filesystem, object-store, REST and Mongo connectors build no
  budget at all, so the policy's ceilings apply to some sources and not others —
  and the policy is the promise a source owner was shown

## `connect/sources/objectstore.py`

### CON-143 · A prefix of daily partitions is one dataset
- **Area:** `connect/sources/objectstore.py::_group` / `_partition_depth`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `s3://lake/risk/positions/booked=2026-04-01/part-0.parquet`
  and 899 siblings across dates
- **Steps:** `discover()`
- **Expected:** exactly one `DiscoveredObject` whose `tags == ("booked",)` and
  whose comment names the partition column
- **Why:** "the mistake is to treat every object as a dataset, which turns one
  table with four years of daily partitions into fourteen hundred 'tables' and
  makes the catalogue useless the moment it is built"

### CON-144 · Only *trailing* directories are partitions
- **Area:** `connect/sources/objectstore.py::_partition_depth`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** keys under `risk/2026/positions/part-0.parquet` and under
  `risk/positions/2026-04-01/part-0.parquet`
- **Steps:** group both
- **Expected:** the first is one dataset at `risk/2026/positions` with depth 0;
  the second is one dataset at `risk/positions` with depth 1 and **no** named
  column
- **Why:** "the year is not the last thing before the file and a directory in
  the middle is part of the dataset's identity rather than a slice of it"; and a
  bare date carries a value with no column name, so Prama must not invent one

### CON-145 · A bare-partition pattern does not swallow an ordinary name
- **Area:** `connect/sources/objectstore.py::_BARE_PARTITION`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** directories named `2026`, `202604`, `20260401`, `7`, `1234`,
  `12345`, `v2`, `part`, `2026-4-1`
- **Steps:** match each
- **Expected:** the first six match (`\d{1,4}` catches `7` and `1234`), the last
  three do not
- **Why:** `\d{1,4}` means a directory named `1234` — a book id, a desk code, an
  entity number — is read as a partition and folded into its parent, silently
  merging datasets that are not the same table

### CON-146 · More objects than the ceiling is a refusal, not a truncation
- **Area:** `connect/sources/objectstore.py::ObjectStoreConnector._glob`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a prefix holding `max_objects + 1` objects
- **Steps:** `discover()`
- **Expected:** `ConnectorError` code `CONNECT.TOO_MANY_OBJECTS`, remedy naming
  a narrower prefix or a higher ceiling and explaining that a partial listing
  would profile part of the data as though it were all of it
- **Why:** the whole design principle of this connector; the `+1` in the LIMIT
  is what makes "more than" detectable

### CON-147 · Exactly the ceiling is allowed
- **Area:** `connect/sources/objectstore.py::ObjectStoreConnector._glob`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a prefix holding exactly `max_objects` objects
- **Steps:** discover
- **Expected:** every object listed, no refusal
- **Why:** an off-by-one here makes a correctly sized estate unreadable

### CON-148 · A rewritten object changes the snapshot only when rows are known
- **Area:** `connect/sources/objectstore.py::ObjectStoreConnector.snapshot`,
  `_Dataset.is_measured`
- **Type:** contract
- **Priority:** P1
- **Precondition:** (a) a Parquet dataset whose footers give sizes and row
  counts; (b) a CSV dataset where neither is known
- **Steps:** snapshot each; rewrite one object in place to a different size;
  snapshot again
- **Expected:** (a) `kind is FILE_DIGEST`, `exact is True`, identifier changes;
  (b) `kind is OBJECT_LISTING`, `exact is False`
- **Why:** "an object rewritten in place under the same name leaves a key-only
  digest untouched, and calling that exact would let incremental profiling skip
  data that changed underneath it"

### CON-149 · The object listing is cached for the life of the connector
- **Area:** `connect/sources/objectstore.py::ObjectStoreConnector._list`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an open connector that has already discovered
- **Steps:** add an object to the prefix; then `discover()` and `snapshot()`
  again on the same connector
- **Expected:** record whether the new object appears
- **Why:** `self._listing` is set once and cleared only by `close()`. A
  long-lived connector serving a scheduled run would report an unchanged
  snapshot across a delivery, and `IncrementalPlanner` would mark every segment
  `SETTLED` on the strength of it

### CON-150 · A dataset mixing formats uses the first object's reader
- **Area:** `connect/sources/objectstore.py::_Dataset.reader` / `.kind`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a prefix holding both `part-0.csv` and `part-1.parquet`
- **Steps:** describe and read the dataset
- **Expected:** record what happens — objects are sorted by key, so the reader is
  chosen by whichever name sorts first, and the glob passes both to it
- **Why:** a landing zone that changed format mid-year is an ordinary estate
  fact; reading a Parquet file with `read_csv_auto` fails loudly, which is the
  good case, but a CSV read with `read_parquet` and `union_by_name` may not

### CON-151 · Credentials never reach a stored string
- **Area:** `connect/sources/objectstore.py::_secret_statement`
- **Type:** security
- **Priority:** P1
- **Precondition:** a config with a secret access key
- **Steps:** build the statement; then serialise the connector's `config`
  through the connection record path
- **Expected:** the secret appears only in the transient DuckDB statement, with
  its quotes doubled; the schema refuses to store it (CON-055)
- **Why:** "built here rather than stored, because the connection record holds a
  vault reference and the value only exists for the life of the process"

### CON-152 · No access key means the instance's own role
- **Area:** `connect/sources/objectstore.py::_secret_statement`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a config with `region` and `endpoint` and no key
- **Steps:** build the statement
- **Expected:** `PROVIDER credential_chain` present as the second clause; no
  `KEY_ID`, `SECRET` or `SESSION_TOKEN` clause even if a session token was
  supplied
- **Why:** "the normal arrangement in a cloud estate, and better than a key in a
  config"; a session token left behind without a key id is a half-configured
  credential that fails obscurely

### CON-153 · A URI that is not an object store is MISCONFIGURED, not UNREACHABLE
- **Area:** `connect/sources/objectstore.py::ObjectStoreConnector.health`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `uri` of `/mnt/lake/positions`, `http://x/y`, `` and
  `s3://bucket/prefix`
- **Steps:** `health()`
- **Expected:** MISCONFIGURED for the first three, listing the six accepted
  schemes; HEALTHY or a network state for the last
- **Why:** a mistyped bucket and a firewall produce the same driver error and
  send the reader to entirely different people

### CON-154 · Access denied is UNAUTHORISED and names the permission
- **Area:** `connect/sources/objectstore.py::_classify` / `_is_denied`
- **Type:** functional
- **Priority:** P2
- **Precondition:** exceptions containing `Access Denied`, `403`, `SignatureDoesNotMatch`,
  `No such bucket`, `connection refused`
- **Steps:** `health()` for each
- **Expected:** UNAUTHORISED with `missing_permissions=("s3:ListBucket",)` for
  the first three; MISCONFIGURED for the fourth; UNREACHABLE for the last
- **Why:** the remedy for each is a different person; and record that an object
  key containing the word `signature` would be classified as denied

### CON-155 · Health truncates the driver's message
- **Area:** `connect/sources/objectstore.py::ObjectStoreConnector.health`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** an exception with a 5,000-character multi-line message
- **Steps:** `health()`
- **Expected:** `detail` is the first line, capped at 300 characters
- **Why:** `HealthReport.detail` is "written for a data architect, not an
  engineer"; a driver stack trace rendered into a status field is the thing that
  claim forbids

## `connect/sources/rest.py`

### CON-156 · Pagination is followed to the end
- **Area:** `connect/sources/rest.py::RestConnector._collect`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a test server serving 40,000 records across 400 pages via a
  `links.next` field
- **Steps:** read the endpoint and count rows
- **Expected:** 40,000; `last_read_pages == 400`; `last_read_truncated is False`
- **Why:** "a page is not a population … a completeness control over the first
  hundred rows of forty thousand passes, and means nothing"

### CON-157 · A `next` link pointing at a page already read stops the read
- **Area:** `connect/sources/rest.py::RestConnector._collect`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a server whose page 3 links back to page 1
- **Steps:** read
- **Expected:** the read stops; pages 1–3 appear once each; no duplicates
- **Why:** the first URL is seeded into `seen_urls` precisely so "a 'next'
  pointing back at page one is detected *before* page one has been read a second
  time" — otherwise the read returns duplicates and calls itself complete

### CON-158 · A page cap stops the read and says so
- **Area:** `connect/sources/rest.py::RestConnector._collect`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `page_limit=10` and a server with 50 pages
- **Steps:** read
- **Expected:** 10 pages read, `last_read_truncated is True`
- **Why:** "an endpoint whose next link cycles would otherwise read forever", and
  a truncated read that does not say so is a completeness control on a fraction
  of the data

### CON-159 · A row limit reached before the cap is not truncation
- **Area:** `connect/sources/rest.py::RestConnector._collect`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `SamplePlan(rows=50)` and a server with 50 pages of 100
- **Steps:** read
- **Expected:** exactly 50 records and `last_read_truncated is False`
- **Why:** the caller asked for 50; conflating "you asked for fewer" with "we
  could not get them all" would make every sampled read look incomplete

### CON-160 · A page parameter is not replaced by an empty dict
- **Area:** `connect/sources/rest.py::RestConnector._collect`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a server paging by `?page=n` with a `links.next` absolute URL
- **Steps:** read and record the URLs requested
- **Expected:** each `next` URL is fetched with `params=None`, so its own query
  string survives
- **Why:** "httpx treats an empty params dict as 'replace the query string',
  which silently strips `?page=2` off a next link and refetches page one forever.
  The read looks successful and returns the first page repeated, which is the
  worst shape a truncation can take"

### CON-161 · 429 is honoured, not treated as a failure
- **Area:** `connect/sources/rest.py::RestConnector._get`, `_retry_after`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a server answering 429 with `Retry-After` of `2`, of
  `Wed, 21 Oct 2026 07:28:00 GMT`, of `999`, and absent
- **Steps:** read
- **Expected:** waits 2 s, 1 s (the unparseable fallback), 60 s (the clamp), 1 s;
  `last_read_waited_seconds` records the total
- **Why:** "an API saying 'slow down' is working correctly … so a read that took
  eleven minutes is explained rather than mysterious". Note that an HTTP-date
  `Retry-After` is legal and falls through to the 1 s fallback

### CON-162 · Five consecutive 429s is a refusal naming the total wait
- **Area:** `connect/sources/rest.py::RestConnector._get`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a server answering 429 for ever
- **Steps:** read
- **Expected:** `UnreachableError` "asked us to slow down five times running",
  remedy quoting the accumulated seconds and suggesting reading less or less
  often
- **Why:** a loop with no bound against a rate limiter is a hung read nobody can
  see; five is the bound and the message is what makes the stop actionable

### CON-163 · 401 and 403 are UNAUTHORISED, 5xx is DEGRADED
- **Area:** `connect/sources/rest.py::RestConnector.health` / `._get`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a server answering 200, 401, 403, 404, 500, 503
- **Steps:** `health()` for each; then `read()` for 401 and 404
- **Expected:** HEALTHY, UNAUTHORISED, UNAUTHORISED, HEALTHY (health treats
  anything under 500 that is not 401/403 as healthy), DEGRADED, DEGRADED; read
  raises `UnauthorisedError` for 401 and `UnreachableError` for 404
- **Why:** health's 404 case is worth pinning: a base URL with a typo answers 404
  and reports HEALTHY, which is the state that stops somebody checking the URL

### CON-164 · The credential goes in a header, never a query string
- **Area:** `connect/sources/rest.py::RestConnector._headers`
- **Type:** security
- **Priority:** P1
- **Precondition:** a token, and configs varying `auth_header` and `auth_scheme`
- **Steps:** inspect the client's headers and every requested URL
- **Expected:** `Authorization: Bearer <token>` by default; a custom header and
  scheme honoured; an empty scheme produces no leading space; the token appears
  in no URL
- **Why:** "a token in a URL is a token in every access log, proxy log and
  browser history between here and the server"

### CON-165 · A predicate is refused rather than ignored
- **Area:** `connect/sources/rest.py::RestConnector.read`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `SamplePlan(predicate="booked = '2026-04-01'")`
- **Steps:** read
- **Expected:** `ConnectorError` code `CONNECT.NO_PREDICATE` before any HTTP call
- **Why:** "reading everything and calling it a segment would state one slice's
  rates as the dataset's". This connector refuses explicitly rather than through
  `require_predicate_support`, which is the same guarantee by a second route

### CON-166 · The schema is inferred across the sample and disagreements land on the column
- **Area:** `connect/sources/rest.py::_infer`, `RestConnector.describe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 200 records where `amount` is a number in 199 and a string in
  one, and `settled_at` is absent from 50
- **Steps:** `describe()`
- **Expected:** `amount`'s comment reads "arrives as double and as string across
  the sample"; `settled_at` is `nullable`; the columns come from the whole
  sample, not record one
- **Why:** "a schema taken from record one is a type nobody checked"; and a
  summary saying "three columns have mixed types" sends somebody to find which
  three

### CON-167 · A mixed-type column can still be read as Arrow
- **Area:** `connect/sources/rest.py::RestConnector.read`
- **Type:** regression
- **Priority:** P1
- **Precondition:** the CON-166 records
- **Steps:** read the endpoint
- **Expected:** a batch is produced; the `amount` column holds both values
- **Why:** `read` builds the batch with `pa.RecordBatch.from_pydict`, which uses
  Arrow's own inference and raises `ArrowInvalid` on a mixed column — while
  `describe` on the same records reports the disagreement as a finding. The
  module docstring calls mixed types the normal state of an API; `to_array`
  exists for exactly this and is not used here

### CON-168 · A nested value becomes JSON text, deterministically
- **Area:** `connect/sources/rest.py::_scalar`
- **Type:** functional
- **Priority:** P2
- **Precondition:** records whose `legs` field is a list of dicts, with the keys
  in different orders across records
- **Steps:** read
- **Expected:** one string column; two structurally identical values render
  identically (`sort_keys=True`)
- **Why:** "flattening would invent columns the API never promised, and dropping
  it would lose a field a control might be about" — and an unsorted dump would
  make a distinct count of a JSON column depend on Python's dict ordering

### CON-169 · A response that is not JSON is refused by name
- **Area:** `connect/sources/rest.py::_json`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a server returning HTML with a 200
- **Steps:** read
- **Expected:** `ConnectorError` code `CONNECT.NOT_JSON` naming the URL
- **Why:** an HTML error page behind a 200 is the commonest API failure there is,
  and a JSON decode error with no URL in it is unactionable

### CON-170 · `_records` and `_next_link` survive a missing path
- **Area:** `connect/sources/rest.py::_records` / `_next_link`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** bodies: a bare list; a bare dict; `{"data": {"items": [...]}}`
  with `records_path="data.items"`; the same with `records_path="data.missing"`;
  a list of non-dicts; `null`
- **Steps:** extract records and the next link
- **Expected:** the list; a one-element list holding the dict; the items; **the
  whole body** (a missing path falls back to `node = body`); an empty list;
  an empty list
- **Why:** the fallback is the dangerous one — a mistyped `records_path` silently
  returns the envelope as a single record rather than reporting that the path
  was not found

### CON-171 · An endpoint's whole result set is held in memory
- **Area:** `connect/sources/rest.py::RestConnector._collect`
- **Type:** performance
- **Priority:** P3
- **Precondition:** a server with 1,000 pages of 1,000 records
- **Steps:** read and watch resident memory
- **Expected:** record the peak
- **Why:** `_collect` returns a list and `read` batches it afterwards, so the
  page cap of 1,000 is also the memory bound — the docstring's streaming claim
  applies to the batches handed out, not to what is held

## `connect/sources/mongo.py`

### CON-172 · A declared predicate is applied to the query
- **Area:** `connect/sources/mongo.py::MongoConnector.read` / `._sample`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a collection with documents across five business dates, and
  `SamplePlan(predicate="<one date>")`
- **Steps:** read and count documents
- **Expected:** only that date's documents
- **Why:** `CAPABILITIES` declares `PushdownFeature.PREDICATE_PUSHDOWN`, so
  `require_predicate_support` passes — and `_sample` issues `collection.find({})`
  and never looks at `plan.predicate`. This is precisely the outcome the SPI
  calls "the quiet disaster": the whole collection read and recorded as one
  segment, every rate wrong, nothing looking broken

### CON-173 · A read with no row limit materialises the collection
- **Area:** `connect/sources/mongo.py::MongoConnector._sample`
- **Type:** performance
- **Priority:** P1
- **Precondition:** a collection of 5,000,000 documents and `SamplePlan()`
- **Steps:** read
- **Expected:** record peak memory
- **Why:** `[document async for document in cursor]` with `limit == 0` collects
  every document before the first batch is yielded; the SPI's `read` contract is
  "stream the object as Arrow record batches"

### CON-174 · A `Decimal128` stays exact
- **Area:** `connect/sources/mongo.py::_scalar`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a document with `Decimal128("1953193.464900000000")`
- **Steps:** read it
- **Expected:** a `decimal.Decimal` with every digit; never a float
- **Why:** "the obvious conversion is through float, and that is the one that
  loses money — same trap as JDBC, different library"

### CON-175 · A type disagreement is reported on the field it is about
- **Area:** `connect/sources/mongo.py::_infer`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 200 documents where `notional` is a number in 199 and a
  string in one, and `settled_at` is absent from 50
- **Steps:** `describe()`
- **Expected:** `notional`'s comment reads "arrives as double and as string
  across 200 sampled document(s)"; `settled_at`'s reads "absent from 50 of 200
  sampled" and it is nullable
- **Why:** "in a collection nobody has declared, that is the finding rather than
  the noise"

### CON-176 · A sampled schema carries its sample size
- **Area:** `connect/sources/mongo.py::MongoConnector.describe`,
  `.last_schema_sample`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a collection of 10,000 documents, `schema_sample_documents=200`
- **Steps:** describe, then read `last_schema_sample`
- **Expected:** `200`
- **Why:** "'no document has a settled_at' and 'none of the two hundred I looked
  at has one' are different claims and only one of them is true"

### CON-177 · A nested document becomes JSON text, not columns
- **Area:** `connect/sources/mongo.py::_scalar`, `_type_of`
- **Type:** functional
- **Priority:** P2
- **Precondition:** documents with an embedded sub-document and an array
- **Steps:** describe and read
- **Expected:** type `json`; the value is sorted JSON text; a `datetime` inside
  it is stringified rather than raising
- **Why:** "flattening invents columns the collection never promised and changes
  shape as soon as a document nests one level deeper"; `default=str` is what
  keeps a BSON value from breaking the dump

### CON-178 · An `ObjectId` renders as its hex string
- **Area:** `connect/sources/mongo.py::_scalar`, `_type_of`
- **Type:** functional
- **Priority:** P2
- **Precondition:** documents with `_id`
- **Steps:** describe and read
- **Expected:** type name `objectid`; the Arrow value is the 24-character hex
  string
- **Why:** `_id` is the natural key candidate in every Mongo collection; leaving
  it as a BSON object makes the distinct count and the key-candidate inference
  operate on `repr()`

### CON-179 · A Mongo source refuses to open without a database
- **Area:** `connect/sources/mongo.py::MongoConnector.open`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a config with a host and no `database`
- **Steps:** open
- **Expected:** `ConnectorError` code `CONNECT.INCOMPLETE`, remedy "an estate
  declared against the wrong database is worse than one that failed to connect"
- **Why:** a deployment holds several and picking one silently is an estate
  pointed at the wrong data

### CON-180 · A catalogue read failure is distinguished from a connection failure
- **Area:** `connect/sources/mongo.py::MongoConnector.health` / `.discover`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a role that can read documents but not `listCollections`
- **Steps:** `health()` then `discover()`
- **Expected:** health HEALTHY (ping succeeds); discover raises
  `UnreachableError` whose remedy names `listCollections`
- **Why:** the remedy is right and the *state* is worth recording: a source that
  is healthy and undiscoverable reports healthy, which is a different answer from
  the SQL base's DEGRADED for the same condition

### CON-181 · Credentials in a built URI are percent-encoded
- **Area:** `connect/sources/mongo.py::MongoConnector._connection_uri`
- **Type:** security
- **Priority:** P1
- **Precondition:** a password containing `@`, `:` and `/`
- **Steps:** build the URI
- **Expected:** the password is escaped so the host is parsed correctly
- **Why:** `f"mongodb://{user}:{password}@{host}:{port}/…"` interpolates raw; a
  password containing `@` splits the authority and the driver connects
  somewhere else — or reports an unparseable URI containing the credential

## `connect/sources/query.py` — the executor seam

### CON-182 · A write statement is refused
- **Area:** `connect/sources/query.py::sole_read_statement`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** pass `DELETE FROM positions`, `UPDATE t SET x=1`,
  `DROP TABLE t`, `INSERT INTO t VALUES (1)`, `CREATE TABLE t (a int)`,
  ` \n SELECT 1 `, `WITH x AS (SELECT 1) SELECT * FROM x`
- **Expected:** `ConnectorError` "a control may only run a read-only query" for
  the first five, listing SELECT and WITH as permitted; the last two return the
  stripped statement
- **Why:** "a control is a check. It has no business writing, and refusing
  anything that is not a SELECT or a WITH means a defect in the compiler cannot
  damage the data it was meant to examine"

### CON-183 · Two statements are refused
- **Area:** `connect/sources/query.py::sole_read_statement`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** pass `SELECT 1; DROP TABLE t`, `SELECT 1;`, `SELECT 1;;`,
  `SELECT ';' FROM t`
- **Expected:** refusal for the first; the second and third are accepted (the
  trailing semicolons are stripped); the fourth is **refused** because the
  semicolon is inside a string literal
- **Why:** "a trailing semicolon and a second statement is the shape of every SQL
  injection there has ever been" — and the false positive on a quoted semicolon
  is the cost of a lexical check, worth recording

### CON-184 · An empty query is refused as a compiler defect
- **Area:** `connect/sources/query.py::sole_read_statement`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** pass `""`, `"   "`, `";"`
- **Expected:** `ConnectorError` "an empty query cannot be run", remedy "This is
  a compiler defect; the control produced no SQL."
- **Why:** the remedy points at the right owner; an empty string reaching a
  driver produces a message about syntax

### CON-185 · A refusal truncates the SQL it quotes
- **Area:** `connect/sources/query.py::sole_read_statement`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a 10,000-character offending statement
- **Steps:** trigger both refusals
- **Expected:** `context["sql"]` is 120 characters
- **Why:** an error context is logged and rendered; an unbounded generated query
  in it is a log line nobody can read

### CON-186 · SQLite's REGEXP is registered on every connection Prama opens
- **Area:** `connect/sources/query.py::register_regexp`,
  `sqlite.py::SqliteConnector._query`, `query.py::_sqlite`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a SQLite source
- **Steps:** run a compiled validity control through both paths
- **Expected:** no "no such function: REGEXP"
- **Why:** "Prama's SQLite dialect declares the capability on the strength of
  this function, so every SQLite connection Prama opens must call it" — and
  there are two such paths

### CON-187 · REGEXP on a NULL yields NULL, not False
- **Area:** `connect/sources/query.py::register_regexp`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a SQLite table with nulls in the checked column, and a
  control declaring `TREAT UNKNOWN AS PASS`
- **Steps:** run the control on SQLite and on DuckDB and compare violation counts
- **Expected:** identical; the nulls are unknown, and the control's policy — not
  this function — decides what that means
- **Why:** QA finding Q-12. The docstring already said this and the code returned
  `False`, "a definite *non-match* and not an unknown … 11 violations on SQLite
  against 4 on DuckDB, for the same control over the same rows"

### CON-188 · REGEXP takes the pattern first
- **Area:** `connect/sources/query.py::register_regexp`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a SQLite table whose column holds `GB0002634946` and `xxx`
- **Steps:** run `SELECT count(*) FROM t WHERE isin REGEXP '^[A-Z]{2}'`
- **Expected:** 1
- **Why:** "SQLite calls REGEXP with the pattern first: `x REGEXP y` is
  `regexp(y, x)`. Getting this backwards matches nothing, silently, and every
  validity control passes" — the counterfactual is a control that cannot fail

### CON-189 · `executor_for` refuses a missing file and an unknown engine
- **Area:** `connect/sources/query.py::executor_for`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `executor_for("/no/such.db", "sqlite")`;
  `executor_for(existing, "oracle")`; `executor_for(a_directory, "sqlite")`
- **Expected:** `ValidationError` "there is no file at …"; `ValidationError`
  listing `duckdb, sqlite` and explaining that a caller may supply its own
  executor; record what the directory case does
- **Why:** "22 tracebacks reach the terminal from the CLI, mostly 'directory
  where a file is expected'" — open finding Q-28, and this is one of the places
  a directory can be passed

### CON-190 · `executor_from` refuses a source with no query engine up front
- **Area:** `connect/sources/query.py::executor_from`
- **Type:** negative
- **Priority:** P1
- **Precondition:** the filesystem, REST and Mongo connectors
- **Steps:** `executor_from(connector)` for each
- **Expected:** `ConnectorError` before any control runs, remedy explaining local
  evaluation
- **Why:** "discovering that halfway through a run would leave a partial ledger
  and an error record that blames the source for something Prama should have
  known before it started". Note `FilesystemConnector` declares
  `PushdownFeature.SQL` and does **not** override `can_run_controls`, so it
  refuses here while claiming SQL pushdown — record which of the two is intended

## `connect/feed/` — arrival, filename patterns, trailers

The controls that catch what nothing else catches: a file that arrives late,
twice, out of order, truncated or not at all passes every content-level check,
because the rows that did arrive are perfectly valid.

### CON-191 · Every documented token parses and renders
- **Area:** `connect/feed/pattern.py::FilenamePattern`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** for each of the three documented examples —
  `POS_EXTRACT_{YYYYMMDD}_{SEQ}.csv`, `positions.{YYYY}-{MM}-{DD}.parquet`,
  `trades_{YYYYMMDD}_{HH}{mm}.json.gz` — parse a matching name and render the
  date back
- **Expected:** the business date, delivery time and sequence are read; `render`
  reproduces the name (with `??` for `{HH}`/`{mm}`)
- **Why:** these are the examples in the module docstring and in the remedy text;
  an example the code rejects is finding H7's shape

### CON-192 · An unrecognised token is refused, not left as a literal
- **Area:** `connect/feed/pattern.py::_reject_unknown_tokens`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** construct with `POS_{YYYYMDD}.csv` and with `POS_{DATE}.csv`
- **Expected:** `ValidationError` naming the token, listing the eleven legal
  ones plus `{ANY}`, and saying that left as literal text it "would match no file
  at all and the feed would report a missing delivery every day"
- **Why:** the failure is silent and daily; a misspelled token is invisible in a
  glob

### CON-193 · A day token with no month token is refused
- **Area:** `connect/feed/pattern.py::_reject_incoherent_date`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** construct `f_{YYYY}{DD}.csv`; then `f_{YYYY}{MM}.csv`
- **Expected:** the first raises; the second is accepted and reads as the first
  of the month
- **Why:** "every file in the year would land on the same handful of dates, and
  the arrival judge would report them as duplicates"

### CON-194 · An empty pattern is refused with an example
- **Area:** `connect/feed/pattern.py::FilenamePattern.__init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** construct with `""` and with `"   "`
- **Expected:** `ValidationError` whose remedy shows
  `POS_EXTRACT_{YYYYMMDD}_{SEQ}.csv`
- **Why:** a feed with no pattern matches everything or nothing, and neither is
  a feed

### CON-195 · A padded sequence renders padded
- **Area:** `connect/feed/pattern.py::_PADDED_SEQ`, `.render`,
  `._sequence_width`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `POS_{YYYYMMDD}_{SEQ:3}.csv`
- **Steps:** parse `POS_20260331_007.csv`; render for sequence 7 and 1
- **Expected:** sequence 7 parsed; `POS_20260331_007.csv` and
  `POS_20260331_001.csv` rendered
- **Why:** "an alert that names the missing file as `..._1.csv` when it should be
  `..._001.csv` sends the reader looking for the wrong thing"

### CON-196 · A padded sequence does not match the wrong width
- **Area:** `connect/feed/pattern.py::_build`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `POS_{YYYYMMDD}_{SEQ:3}.csv`
- **Steps:** `parse("POS_20260331_7.csv")` and `parse("POS_20260331_0007.csv")`
- **Expected:** `None` for both — `\d{3}` is exact
- **Why:** a sender who drops the padding has changed the convention, and that is
  an `UNREADABLE_NAME` finding rather than a silent match

### CON-197 · `*` and `?` remain wildcards; everything else is escaped
- **Area:** `connect/feed/pattern.py::_escape_literal`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `POS_*_{YYYYMMDD}.csv` and `a.b_{YYYYMMDD}.csv`
- **Steps:** match `POS_EOD_20260331.csv`, `POS_A/B_20260331.csv`,
  `axb_20260331.csv`
- **Expected:** first matches; second does not (`*` is `[^/]*`); third does not
  (the dot is escaped)
- **Why:** "refusing that would make the pattern language a worse version of the
  glob they already know" — while an unescaped dot would make `a.b` match `axb`

### CON-198 · Matching is case-insensitive
- **Area:** `connect/feed/pattern.py::FilenamePattern.__init__`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `POS_{YYYYMMDD}.CSV`
- **Steps:** `matches("pos_20260331.csv")`
- **Expected:** `True`
- **Why:** `re.IGNORECASE` is applied to the whole pattern and is not documented
  anywhere; on a case-sensitive filesystem a sender who changed the case has
  changed the convention, and this silently accepts it

### CON-199 · A shaped-but-impossible date is read as no date
- **Area:** `connect/feed/pattern.py::_date_from`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `POS_{YYYYMMDD}.csv`
- **Steps:** parse `POS_20261332.csv`, `POS_20260229.csv` (2026 is not a leap
  year), `POS_00000000.csv`
- **Expected:** a `ParsedName` in each case with `business_date is None`
- **Why:** `ValueError` is caught deliberately — "not this feed's file, or a
  genuinely malformed one — either way, not a date" — and the judge turns that
  into `UNREADABLE_NAME`

### CON-200 · `{DDMMYYYY}` and `{YYYYMMDD}` are not confused
- **Area:** `connect/feed/pattern.py::_date_from`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** two patterns differing only in the token
- **Steps:** parse `31032026` under `{DDMMYYYY}` and `20260331` under
  `{YYYYMMDD}`
- **Expected:** both yield 2026-03-31; and `31032026` under `{YYYYMMDD}` yields
  `None` rather than a plausible wrong date
- **Why:** both are eight digits; a feed declared with the wrong token would
  otherwise report every file as being for a date four thousand years away

### CON-201 · A two-digit year uses the declared century
- **Area:** `connect/feed/pattern.py::_date_from`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `POS_{YY}{MM}{DD}.csv` with `century=2000` and `century=1900`
- **Steps:** parse `POS_260331.csv`
- **Expected:** 2026-03-31 and 1926-03-31
- **Why:** the century is a constructor argument with a default and is not
  reachable from `FeedDefinition.from_dict`; a feed built from a document always
  gets 2000

### CON-202 · A feed expecting more than one file a day needs a sequence token
- **Area:** `connect/feed/definition.py::FeedDefinition.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `files_per_day=3` with a pattern carrying no `{SEQ}`
- **Steps:** construct
- **Expected:** `ValidationError` whose remedy names `{SEQ}` and `{SEQ:3}` and
  explains that the deliveries could not otherwise be told apart
- **Why:** without it, three files a day are three duplicates and a missing one
  cannot be identified

### CON-203 · `files_per_day` below one is refused
- **Area:** `connect/feed/definition.py::FeedDefinition.__post_init__`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `files_per_day` of `0` and `-1`
- **Steps:** construct
- **Expected:** `ValidationError` "A feed that never delivers is not a feed"
- **Why:** zero would make `expected_filenames` empty and the missing-file
  index in `_for_date` an `IndexError`

### CON-204 · An earliest time with no due time is refused
- **Area:** `connect/feed/definition.py::FeedDefinition.__post_init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `earliest=time(5,0)`, `due_by=None`
- **Steps:** construct
- **Expected:** `ValidationError` "an open-ended window cannot be late"
- **Why:** an EARLY finding against no deadline is a window with one edge

### CON-205 · `can_detect_missing` needs both a deadline and a readable date
- **Area:** `connect/feed/definition.py::FeedDefinition.can_detect_missing`
- **Type:** contract
- **Priority:** P1
- **Precondition:** four feeds — both, deadline only, date only, neither
- **Steps:** read the property; then judge an empty landing zone past the
  deadline for each
- **Expected:** `True` only for the first; a `MISSING` finding only for the first
- **Why:** "'the file has not arrived' cannot be distinguished from 'the file
  arrived and we could not tell which day it was for'" — and a feed that cannot
  report an absence should not look like one that can

### CON-206 · `from_dict` loses half the definition
- **Area:** `connect/feed/definition.py::FeedDefinition.to_dict` / `.from_dict`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a feed declaring `manifest_pattern`, `earliest`, and a
  trailer with `total_field`, `amount_field`, `header_lines` and
  `total_tolerance`
- **Steps:** round-trip through `to_dict` then `from_dict`
- **Expected:** an equal definition
- **Why:** `to_dict` emits neither `earliest` nor the trailer's fields, and
  `from_dict` reads neither `manifest_pattern`, `amount_field`, `header_lines`
  nor `total_tolerance`. A feed exported and re-imported loses its header
  exclusion — and `header_lines`'s own comment says that without it "a headed CSV
  reports a one-row shortfall on every single delivery, and the check gets muted"

### CON-207 · A file arriving after the deadline is LATE, measured from the due time
- **Area:** `connect/feed/arrival.py::ArrivalJudge._timeliness`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `due_by=06:30`, `lateness_grace=15 minutes`, a file at 06:40
  and one at 06:50
- **Steps:** judge
- **Expected:** 06:40 is ON_TIME (inside the grace); 06:50 is LATE with
  `lateness_seconds == 1200` — twenty minutes from **06:30**, not five from 06:45
- **Why:** "grace decides whether to raise the finding; it is an alerting
  tolerance, not a renegotiated promise. Measuring from the deadline would
  understate every breach and make the lateness trend shift retroactively
  whenever someone tuned the grace period"

### CON-208 · Nothing is MISSING before the deadline passes
- **Area:** `connect/feed/arrival.py::ArrivalJudge._for_date`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a feed due at 06:30 with 15 minutes' grace, an empty landing
  zone, and a frozen clock at 06:00, 06:45 and 06:46
- **Steps:** judge each
- **Expected:** no finding, no finding, `MISSING`
- **Why:** "reporting a file missing at 06:00 when it is due at 06:30 is how a
  feed monitor teaches people to ignore it"; the comparison is `>` the deadline,
  so exactly 06:45 is not yet missing

### CON-209 · A missing file is named
- **Area:** `connect/feed/arrival.py::ArrivalJudge._for_date`,
  `FeedDefinition.expected_filenames`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a three-file feed where only the first has arrived, past the
  deadline
- **Steps:** judge
- **Expected:** one `MISSING` finding whose `expected_filename` is the *second*
  expected name, and whose detail reads "2 of 3 deliveries have not arrived"
- **Why:** "'positions_20260331.csv has not arrived' is actionable; 'a file is
  missing' is not"

### CON-210 · Arrivals are ordered by arrival, not by sequence
- **Area:** `connect/feed/arrival.py::ArrivalJudge._for_date`
- **Type:** contract
- **Priority:** P1
- **Precondition:** sequences 1, 2, 3 whose modification times are 3, 1, 2
- **Steps:** judge with `duplicates=ACCUMULATE`
- **Expected:** an `OUT_OF_SEQUENCE` finding
- **Why:** "sorting by sequence would put the deliveries back into the order the
  sender intended and make the out-of-sequence check below unable to ever fire —
  which is the one thing it exists to catch"

### CON-211 · A resend is told from a restatement by digest
- **Area:** `connect/feed/arrival.py::ArrivalJudge._duplicate`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `duplicates=REJECT`, a second file for the same date, and
  `previously_seen` mapping the filename to (a) the same digest, (b) a different
  digest, (c) nothing
- **Steps:** judge
- **Expected:** DUPLICATE in all three, with details "identical bytes … a resend,
  not a restatement", "same name, different content: this is a restatement, not
  a resend", and "a second delivery for <date>"
- **Why:** the operational response differs: a resend is noise, a restatement is
  a reprocessing decision

### CON-212 · Under LATEST_WINS a second delivery produces no duplicate finding
- **Area:** `connect/feed/arrival.py::ArrivalJudge._for_date`,
  `DuplicatePolicy.permits_second_delivery`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `files_per_day=1`, `duplicates=LATEST_WINS`, two files for
  the same date
- **Steps:** judge
- **Expected:** record what is emitted — both files are judged for timeliness and
  neither is flagged
- **Why:** the enum says "a resend supersedes", which is a decision about which
  file to process; whether the *supersession* itself is worth reporting is a
  separate question, and at present nothing says a second file arrived

### CON-213 · A file for a non-business day is UNEXPECTED_DAY, not MISSING
- **Area:** `connect/feed/arrival.py::ArrivalJudge.judge` / `._unexpected`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a TARGET2 feed and a file dated Good Friday
- **Steps:** judge a range spanning it
- **Expected:** an `UNEXPECTED_DAY` finding naming the calendar, severity
  `minor`, next action "confirm the calendar: either the feed now runs on this
  day, or the sender used the wrong date"
- **Why:** the two readings lead to two different conversations, and severity
  `minor` is right for both

### CON-214 · A file too small is TRUNCATED before it is judged for timeliness
- **Area:** `connect/feed/arrival.py::ArrivalJudge._timeliness`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `minimum_bytes=1024` and files of 0, 1023 and 1024 bytes,
  all arriving late
- **Steps:** judge
- **Expected:** TRUNCATED, TRUNCATED, LATE
- **Why:** a truncated file needs a re-send and a late one needs chasing; the
  size check comes first because an incomplete file's arrival time is not the
  finding

### CON-215 · Every status carries a severity and a next action
- **Area:** `connect/feed/arrival.py::ArrivalStatus.severity` / `.next_action`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** evaluate both for all nine statuses
- **Expected:** no `KeyError`; MISSING and TRUNCATED are `critical`; ON_TIME and
  EARLY are `info`; every action is a sentence a person can act on
- **Why:** "every alert carries one"; a dict lookup by member means a new status
  raises rather than silently rendering blank

### CON-216 · `summarise` reports the worst severity across unhealthy findings
- **Area:** `connect/feed/arrival.py::summarise`, `_worst`
- **Type:** functional
- **Priority:** P2
- **Precondition:** findings of ON_TIME, UNREADABLE_NAME and MISSING; and a list
  of only ON_TIME
- **Steps:** summarise both
- **Expected:** `worst_severity == "critical"` and only the two unhealthy
  findings listed; `worst_severity is None` for the second
- **Why:** a scorecard that averaged severities would let one critical absence
  disappear into a month of clean days

### CON-217 · A trailer count mismatch is a count mismatch, with the shortfall
- **Area:** `connect/feed/integrity.py::TrailerChecker.check`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a file whose trailer declares 1,000 and which holds 997 data
  rows
- **Steps:** check
- **Expected:** `COUNT_MISMATCH`, `shortfall == 3`, and a rendered message
  "trailer declares 1,000 records, 997 arrived (-3)"
- **Why:** "the cheapest genuine integrity check there is … every row that *did*
  arrive is perfectly valid, so nothing else would notice"

### CON-218 · Headers and blank lines are excluded from the count
- **Area:** `connect/feed/integrity.py::TrailerChecker._data_row_count`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a headed CSV with a trailing blank line, `header_lines=1`,
  and a trailer declaring the correct data row count; then the same with
  `counts_itself=True` and a count one higher
- **Steps:** check both
- **Expected:** `MATCHED` both times
- **Why:** "a trailing newline is not a record, and counting it turns every
  delivery into a false mismatch" — which is how a check gets muted

### CON-219 · The reported `observed_count` on a total mismatch is the line index
- **Area:** `connect/feed/integrity.py::TrailerChecker._check_total`
- **Type:** regression
- **Priority:** P2
- **Precondition:** a file with `header_lines=2`, 100 data rows, a blank line, a
  trailer whose count matches and whose total does not
- **Steps:** check and read `observed_count`
- **Expected:** the number of data rows counted (100)
- **Why:** `_check_total` passes `observed_count=trailer_index`, which is the
  *line* index — 103 here — while `check` above it passes
  `self._data_row_count(...)`. The same field means two different things in two
  branches of one method, and the mismatch report quotes the wrong one

### CON-220 · A total is compared as Decimal, within the declared tolerance
- **Area:** `connect/feed/integrity.py::TrailerChecker._check_total`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a million rows of `0.1`, a trailer total of `100000.00`, and
  tolerances of `"0"` and `"0.01"`
- **Steps:** check under each
- **Expected:** exact Decimal arithmetic; the `"0"` case reflects the true
  difference rather than a floating-point artefact
- **Why:** "summing a million amounts in binary floating point manufactures
  exactly the kind of small discrepancy it is looking for, and the resulting
  mismatch is indistinguishable from a real one"

### CON-221 · `amount_field` and `total_field` are separate settings
- **Area:** `connect/feed/definition.py::TrailerSpec.sum_column`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a trailer `TRLR,100,5000.00` where the data rows carry the
  amount in column 9
- **Steps:** check with `total_field=2` and `amount_field=9`; then with
  `amount_field` unset
- **Expected:** the first sums column 9; the second sums column 2
- **Why:** "the two coincide only by accident"; defaulting to `total_field` is
  right for fixed-layout feeds and wrong for a delimited one, and both need
  pinning

### CON-222 · A malformed trailer is unreadable, not a mismatch
- **Area:** `connect/feed/integrity.py::TrailerChecker.check` / `._check_total`
- **Type:** negative
- **Priority:** P2
- **Precondition:** trailers `TRLR,abc`, `TRLR` (too few fields),
  `TRLR,100,not-a-number` with `total_field=2`
- **Steps:** check each
- **Expected:** `TRAILER_UNREADABLE` in all three, naming the field number and
  quoting up to 80 characters of the line; next action "confirm the trailer
  layout with the sender, or correct the declaration"
- **Why:** "the file is short" and "we cannot read the trailer" send the reader
  to different people

### CON-223 · A malformed tolerance is not swallowed
- **Area:** `connect/feed/integrity.py::TrailerChecker._check_total`
- **Type:** negative
- **Priority:** P3
- **Precondition:** `TrailerSpec(total_tolerance="a bit")`
- **Steps:** check a file with a total
- **Expected:** record what happens — `Decimal("a bit")` raises
  `InvalidOperation`, which is caught only around the *declared* total
- **Why:** a declaration error should be refused when the feed is declared, not
  raised from inside a nightly check; `TrailerSpec` validates nothing

### CON-224 · No declared trailer is MATCHED, and says why
- **Area:** `connect/feed/integrity.py::TrailerChecker.check`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `TrailerSpec()` with no marker
- **Steps:** check any file
- **Expected:** `MATCHED` with detail "no trailer declared for this feed"
- **Why:** the detail is what stops a green result being read as a passed
  integrity check; a feed with no trailer has had nothing checked

### CON-225 · A missing trailer is TRAILER_MISSING
- **Area:** `connect/feed/integrity.py::_find_trailer`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a declared marker `TRLR` and a file whose last line is a data
  row; and a file where a *data* row begins with `TRLR`
- **Steps:** check both
- **Expected:** `TRAILER_MISSING` "no line beginning 'TRLR' was found" for the
  first; the second finds the last such line and counts everything above it
- **Why:** "the transfer probably truncated; request a re-send" is the whole
  point of the check — and the scan is from the end, so a data row with the
  marker prefix is only a hazard when the real trailer is absent

### CON-226 · A manifest naming a file that has not landed is incomplete
- **Area:** `connect/feed/integrity.py::ManifestChecker.check`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a manifest of five files, four present; then five present;
  then five present plus an extra
- **Steps:** check each
- **Expected:** `MANIFEST_INCOMPLETE` naming the missing file, with
  `declared_count=5` and `observed_count=4`; then `MATCHED`; then `MATCHED`
  (an extra file is not reported)
- **Why:** "a multi-file batch is atomic in the sender's mind and is not atomic
  on the wire. Processing four of five files produces numbers that are wrong and
  look right"

## `profile/sketches.py` — HyperLogLog, TDigest, CountMin, TopK

Each sketch states its error bound, "because an approximation whose error nobody
knows is not a measurement". Three of those bounds were wrong — findings C6, C7
and C8 — and the cases below pin them as bounds rather than as behaviour.

### PRO-001 · The hash is stable across processes and runs
- **Area:** `profile/sketches.py::_hash64`
- **Type:** contract
- **Priority:** P1
- **Precondition:** two separate Python processes
- **Steps:** hash the same value in each, with `row=0` and `row=3`
- **Expected:** identical digests
- **Why:** "`hash()` is salted per process, so two workers would disagree and a
  merged sketch would be silently wrong"; mergeability is the property the whole
  parallel and incremental design rests on

### PRO-002 · Each row hashes independently
- **Area:** `profile/sketches.py::_hash64`, `CountMin.add`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a `CountMin(width=2048, depth=5)`
- **Steps:** `add(151, 1_000_000)`; then `estimate(154)`
- **Expected:** `1` — not `1_000_001`
- **Why:** finding C6, and the exact measured case. "If two values collide in one
  row they collide in *every* row, because adding the same constant to both
  cannot separate them. `min()` over the rows then eliminated nothing and the
  sketch was depth-1 with five times the memory … out by a factor of 753"

### PRO-003 · The CountMin error bound holds
- **Area:** `profile/sketches.py::CountMin.error_bound`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a `CountMin(2048, 5)` fed 100,000 values from a Zipf
  distribution
- **Steps:** for every distinct value, assert
  `estimate(v) - true_count(v) <= error_bound` and `estimate(v) >= true_count(v)`
- **Expected:** the over-count bound `e · total / width` holds for all but at
  most a `2^-5` share; no estimate is ever below the truth
- **Why:** the docstring states it as a guarantee with probability `1 - 2^-depth`,
  and "a top-K list that might *miss* a frequent value is useless for finding a
  dominant default, while one that might slightly over-count a rare one is
  harmless"

### PRO-004 · CountMin never underestimates
- **Area:** `profile/sketches.py::CountMin.estimate`
- **Type:** contract
- **Priority:** P1
- **Precondition:** any populated sketch
- **Steps:** compare every estimate against the true count
- **Expected:** `estimate >= true` always
- **Why:** the one-sided error is the whole reason this structure was chosen; a
  single underestimate breaks the property the class is named for

### PRO-005 · CountMin ignores nulls
- **Area:** `profile/sketches.py::CountMin.add` / `.estimate`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a fresh sketch
- **Steps:** `add(None, 5)`; `estimate(None)`; read `total`
- **Expected:** `0`, `0`, `0`
- **Why:** "nulls are counted separately; they are not a distinct value" — a null
  folded into a frequency sketch makes the dominant-value share wrong

### PRO-006 · CountMin merges only sketches of the same shape
- **Area:** `profile/sketches.py::CountMin.merge`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `CountMin(2048, 5)` and `CountMin(1024, 5)`
- **Steps:** merge
- **Expected:** `ValueError` "cannot merge CountMin sketches of different shape"
- **Why:** merging different widths would add counters that index different
  values, producing a sketch whose error bound is meaningless

### PRO-007 · A merged CountMin equals the sketch of the concatenation
- **Area:** `profile/sketches.py::CountMin.merge`
- **Type:** contract
- **Priority:** P1
- **Precondition:** two disjoint halves of a value stream
- **Steps:** sketch each half, merge; sketch the whole; compare every cell and
  `total`
- **Expected:** identical
- **Why:** "partial sketches from parallel workers combine into the sketch of the
  whole" — the claim that makes parallel and incremental profiling exact

### PRO-008 · The HyperLogLog standard error is `1.04 / sqrt(2^p)`
- **Area:** `profile/sketches.py::HyperLogLog.standard_error`
- **Type:** contract
- **Priority:** P1
- **Precondition:** precisions 4, 14 and 18
- **Steps:** read the property; then feed 1,000,000 distinct values at p=14 and
  compare the estimate against the truth
- **Expected:** ≈ 0.26, ≈ 0.0163 ("about 1.6% at the default"), ≈ 0.002; the
  measured relative error is within three standard errors
- **Why:** `ColumnProfile.is_key_candidate` multiplies this number by 3 to decide
  whether a column is a key; a wrong bound is a missed grain declaration, "the
  single most generative thing a business owner can state"

### PRO-009 · Small cardinalities use linear counting and are near-exact
- **Area:** `profile/sketches.py::HyperLogLog.estimate`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** p=14
- **Steps:** add 1, 2, 10, 100 and 1,000 distinct values; estimate each
- **Expected:** exact or within one at the low end
- **Why:** "exact for small cardinalities, where linear counting takes over and
  the error would otherwise be worst exactly where it matters most" — a
  five-value code list must not be reported as four

### PRO-010 · An empty HyperLogLog estimates zero
- **Area:** `profile/sketches.py::HyperLogLog.estimate`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a fresh sketch
- **Steps:** `estimate()` and `len()`
- **Expected:** `0` both times; no `ZeroDivisionError` and no `math.log(inf)`
- **Why:** every register is zero, so `raw` divides by `m` and the linear-counting
  branch computes `m · log(m/m) == 0`; an all-null column reaches here

### PRO-011 · A null is not a distinct value
- **Area:** `profile/sketches.py::HyperLogLog.add`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a fresh sketch
- **Steps:** add `None` a thousand times; estimate
- **Expected:** `0`
- **Why:** counting nulls as a distinct value makes an all-null column look like
  a one-value constant and defeats the empty-column finding

### PRO-012 · Precision is bounded at construction
- **Area:** `profile/sketches.py::HyperLogLog.__init__`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** construct at 3, 4, 18, 19
- **Expected:** `ValueError` at 3 and 19; success at 4 and 18
- **Why:** below 4 the alpha correction is undefined and above 18 the register
  array is 256 KB per column, which stops being a bounded-memory sketch

### PRO-013 · HyperLogLogs of different precision do not merge
- **Area:** `profile/sketches.py::HyperLogLog.merge`
- **Type:** negative
- **Priority:** P2
- **Precondition:** sketches at p=12 and p=14
- **Steps:** merge
- **Expected:** `ValueError`
- **Why:** `zip(..., strict=True)` would raise anyway; the explicit check is what
  names the reason

### PRO-014 · A merged HyperLogLog is the register-wise maximum
- **Area:** `profile/sketches.py::HyperLogLog.merge`
- **Type:** contract
- **Priority:** P1
- **Precondition:** two overlapping value sets
- **Steps:** sketch each, merge, estimate; compare against sketching the union
- **Expected:** identical estimates; neither input is mutated
- **Why:** the merge returns a new sketch rather than modifying in place, and an
  in-place merge would corrupt a segment's own accumulator when it is folded

### PRO-015 · Distinct counting treats `1` and `1.0` as different values
- **Area:** `profile/sketches.py::_hash64`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a fresh HyperLogLog and a fresh TopK
- **Steps:** add `1`, `1.0`, `Decimal("1")`, `"1"`, `True`
- **Expected:** record the distinct count
- **Why:** the hash is over `repr(value)`, so `1` → `"1"`, `1.0` → `"1.0"` and
  `Decimal("1")` → `"Decimal('1')"` are three values. A column read as int
  through one connector and as Decimal through another profiles to different
  distinct counts, and the distinct ratio decides key candidacy

### PRO-016 · A weighted TDigest point is mass, not a count
- **Area:** `profile/sketches.py::TDigest.add`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a fresh digest
- **Steps:** add each of 0…9 with `weight=100`; then `quantile(0.5)`
- **Expected:** ≈ 4.5 — not 9.0
- **Why:** finding C7, and the exact measured case. "The centroids held
  `n_points` of mass and `quantile()` looked for `q * count` — a target it could
  never reach. Every quantile fell through to the maximum"

### PRO-017 · The digest is accurate at the tails
- **Area:** `profile/sketches.py::TDigest._flush`, the `capacity` scale function
- **Type:** contract
- **Priority:** P1
- **Precondition:** 200,000 lognormal samples at `compression=100`
- **Steps:** measure the relative error at p50, p99 and p999 against the exact
  quantiles
- **Expected:** the tail errors are **no worse than** the median's — that is the
  relationship, not a fixed number
- **Why:** finding C8. "Every centroid got the same mass cap, which is the
  uniform accuracy an equi-width histogram already gives" — p99 was out by 12.7%
  and p999 by 17.2% against a docstring saying "a structure that is accurate in
  the middle and vague at the edges is precisely wrong for this job". A fixed
  threshold passes on a lucky seed and proves nothing

### PRO-018 · Quantiles of an empty digest are None
- **Area:** `profile/sketches.py::TDigest.quantile` / `.minimum` / `.maximum`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a fresh digest
- **Steps:** `quantile(0.5)`, `minimum`, `maximum`
- **Expected:** `None` for all three — never `inf` or `-inf`
- **Why:** `_min` and `_max` are seeded with `±inf`; a numeric summary reporting
  `inf` as a column minimum is a range control with an impossible bound

### PRO-019 · A quantile outside [0,1] is refused
- **Area:** `profile/sketches.py::TDigest.quantile`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a populated digest
- **Steps:** `quantile(-0.1)`, `quantile(1.1)`, `quantile(0.0)`, `quantile(1.0)`
- **Expected:** `ValueError` for the first two; the minimum and the maximum for
  the last two
- **Why:** `QUANTILES` is a module constant, but a monitor's baseline can ask for
  an arbitrary one

### PRO-020 · Non-finite and non-positive-weight values are ignored
- **Area:** `profile/sketches.py::TDigest.add`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a fresh digest
- **Steps:** add `nan`, `inf`, `-inf`, `None`, and `1.0` with `weight=0` and
  `weight=-5`; then add `1.0` and `2.0` normally
- **Expected:** `count == 2`, `minimum == 1.0`, `maximum == 2.0`
- **Why:** a `nan` in `_min`/`_max` poisons every subsequent comparison, and an
  `inf` becomes a column maximum that no range control can be written against

### PRO-021 · A merged TDigest answers like the digest of the whole
- **Area:** `profile/sketches.py::TDigest.merge`
- **Type:** contract
- **Priority:** P1
- **Precondition:** two halves of 100,000 samples
- **Steps:** digest each, merge, and compare p1/p50/p99 against a digest of all
  100,000
- **Expected:** within the structure's own stated accuracy; `count` is the sum;
  `minimum`/`maximum` are the extremes of both
- **Why:** this is what lets a year of segment profiles be folded without
  re-reading; and `merge` flushes both inputs, so the inputs' own buffers must
  survive the call

### PRO-022 · TopK is exact for its capacity
- **Area:** `profile/sketches.py::TopK.most_common`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `TopK(k=20)` and 500 distinct values with known counts
- **Steps:** `most_common()`
- **Expected:** the true top 20, in descending count, with exact counts
- **Why:** "'97% of this column is the single value N' is a finding, and a
  finding that might be wrong is worse than no finding"

### PRO-023 · TopK ordering is deterministic on a tie
- **Area:** `profile/sketches.py::TopK.most_common`
- **Type:** functional
- **Priority:** P2
- **Precondition:** five values each with count 10
- **Steps:** build the same TopK twice from different insertion orders and
  compare
- **Expected:** identical lists — the secondary key is `repr(value)`
- **Why:** `top_values` is serialised into a profile document that is hashed;
  an insertion-order-dependent list makes the same data profile two ways

### PRO-024 · Eviction bounds the map on a high-cardinality column
- **Area:** `profile/sketches.py::TopK._evict`
- **Type:** performance
- **Priority:** P1
- **Precondition:** `TopK(k=20, capacity_multiple=50)` — capacity 1,000
- **Steps:** add 1,000,000 distinct values, then check `tracked` and peak memory
- **Expected:** `tracked` never exceeds 1,000
- **Why:** "a high-cardinality column would otherwise turn a bounded sketch into
  an unbounded dictionary — the exact leak this module exists to prevent"

### PRO-025 · Eviction can lose a value that later becomes dominant
- **Area:** `profile/sketches.py::TopK._evict`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a stream where a value appears once early, then 999,000 times
  after 5,000 distinct values have passed through
- **Steps:** profile and read `most_common`
- **Expected:** the value is present with a count that under-reports by one
- **Why:** the class docstring says "the most frequent values, **exactly**"; the
  eviction makes that true only within a window, and the understatement is the
  cost. Pin how large it can be

### PRO-026 · A merged TopK keeps the capacity bound
- **Area:** `profile/sketches.py::TopK.merge`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two `TopK(k=20, capacity_multiple=50)` each tracking 1,000
  distinct values with no overlap
- **Steps:** merge; check `tracked` and the merged capacity
- **Expected:** `tracked <= 1000`
- **Why:** `merge` constructs `TopK(self._k)` and so takes the *default*
  `capacity_multiple` rather than the operand's; a sketch built with a smaller
  multiple silently widens on merge

### PRO-027 · An unhashable value is tracked by its repr
- **Area:** `profile/sketches.py::TopK.add`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** values that are lists and dicts
- **Steps:** add them
- **Expected:** no `TypeError`; they appear keyed by `repr`
- **Why:** a JSON column reaches here through `_scalar`, and a dict slipping
  through unstringified would take down the whole profile

## `profile/statistics.py` — accumulating a column

### PRO-028 · Every statistic on an empty column
- **Area:** `profile/statistics.py::ColumnAccumulator.profile`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an accumulator that has seen no values
- **Steps:** `profile()` and serialise
- **Expected:** `rows == 0`, `nulls == 0`, `null_rate == 0.0`,
  `distinct_estimate == 0`, `distinct_ratio == 0.0`,
  `is_key_candidate is False`, `is_constant is False`,
  `dominant_value is None`, `numeric is None`, `strings is None`
- **Why:** every derived property guards on `rows == 0`; one missed guard is a
  `ZeroDivisionError` inside a nightly profile of an empty landing table

### PRO-029 · Every statistic on an all-null column
- **Area:** `profile/statistics.py::ColumnAccumulator`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 1,000 values, all `None`
- **Steps:** profile
- **Expected:** `rows == 1000`, `nulls == 1000`, `null_rate == 1.0`,
  `distinct_estimate == 0` (the `rows > nulls` guard), `is_key_candidate is
  False`, `numeric is None`, `strings is None`; the column appears in
  `DatasetProfile.empty_columns`
- **Why:** "usually a field the source stopped populating" — and a distinct
  estimate of 1 here would make an empty column look constant rather than empty

### PRO-030 · A one-row column
- **Area:** `profile/statistics.py::ColumnAccumulator`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a single value `42`
- **Steps:** profile
- **Expected:** `distinct_ratio == 1.0`; `is_key_candidate is True`;
  `is_constant is True`; `numeric.stddev == 0.0`; every quantile is `42.0`;
  `dominant_value == (42, 1.0)`
- **Why:** key candidacy and constancy are both true of one row, which is
  correct and worth pinning — a proposal to verify, never a declared key

### PRO-031 · An all-identical column is constant, not a key
- **Area:** `profile/statistics.py::ColumnProfile.is_constant` /
  `.is_key_candidate` / `.dominant_value`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 1,000 rows all holding `"N"`
- **Steps:** profile
- **Expected:** `is_constant is True`, `is_key_candidate is False`,
  `dominant_value == ("N", 1.0)`
- **Why:** a dominant value is "usually an unfilled default" and is the finding;
  proposing it as a key would be the opposite reading of the same number

### PRO-032 · `dominant_value` has a 90% floor
- **Area:** `profile/statistics.py::ColumnProfile.dominant_value`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** columns where the top value covers 89.9%, exactly 90% and
  90.1% of rows
- **Steps:** read the property
- **Expected:** `None`, a tuple, a tuple
- **Why:** below the floor the top value is just the most common one; a
  dominant-default finding on a 50/50 flag column is noise

### PRO-033 · Key candidacy allows three standard errors of slack
- **Area:** `profile/statistics.py::ColumnProfile.is_key_candidate`,
  `KEY_CANDIDATE_SIGMA`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a genuinely unique 100,000-row column, profiled 50 times with
  different value sets
- **Steps:** count how often `is_key_candidate` is True
- **Expected:** all 50
- **Why:** "at one sigma a genuinely unique column is rejected roughly a third of
  the time, purely because the distinct sketch under-counted — and a missed key
  costs the grain declaration … A false candidate costs one verification query.
  The errors are not remotely equal, so the threshold should not be symmetric"

### PRO-034 · A nullable column is never a key candidate
- **Area:** `profile/statistics.py::ColumnProfile.is_key_candidate`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 1,000 distinct values plus one null
- **Steps:** profile
- **Expected:** `False`
- **Why:** "distinct in every row, **and never null**"; a single null is enough,
  and the check is `if self.rows == 0 or self.nulls`

### PRO-035 · NaN counts as a null
- **Area:** `profile/statistics.py::ColumnAccumulator.add_values`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** values `[1.0, float("nan"), 3.0]`
- **Steps:** profile
- **Expected:** `nulls == 1`, `numeric.mean == 2.0`, no `nan` in any quantile
- **Why:** a `nan` reaching the sum poisons the mean, the stddev and every
  quantile; Parquet and DuckDB both deliver `nan` for a missing float

### PRO-036 · A bool is not averaged
- **Area:** `profile/statistics.py::ColumnAccumulator.add_values`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** 1,000 booleans
- **Steps:** profile
- **Expected:** `numeric is None`, `strings is None`; the distinct estimate is 2;
  `top_values` holds `True` and `False`
- **Why:** "a bool is not a number here; averaging one is nonsense" — and `bool`
  is a subclass of `int`, so the check has to come first

### PRO-037 · A datetime is summarised as a number
- **Area:** `profile/statistics.py::ColumnAccumulator.add_values`
- **Type:** functional
- **Priority:** P2
- **Precondition:** 100 aware datetimes across a month, and 100 *naive* ones
- **Steps:** profile both
- **Expected:** numeric summaries with sensible min/max; record what
  `datetime.timestamp()` does with the naive values (it applies the host's local
  time zone)
- **Why:** a min/max range control on a date column is derived from these
  numbers; a host-dependent offset makes the same data profile differently on
  two machines

### PRO-038 · A `Decimal` is neither numeric nor string
- **Area:** `profile/statistics.py::ColumnAccumulator.add_values`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 1,000 `Decimal` values
- **Steps:** profile
- **Expected:** record the result — `Decimal` is not `int`, `float`, `str` or
  `datetime`, so neither `_add_numeric` nor `_add_string` runs and both summaries
  are `None`
- **Why:** JDBC and Mongo both deliver exact decimals deliberately, and money is
  the column a range control is most likely to be written against. A profile
  with no min, no max and no quantiles for every monetary column is a large
  silent gap

### PRO-039 · A string mask is bounded
- **Area:** `profile/statistics.py::_add_string`, `MAX_MASK_LENGTH`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** strings of length 0, 1, 64, 65 and 10,000
- **Steps:** profile and read `strings.top_masks`
- **Expected:** masks for lengths 1 and 64 only; the empty string and the two
  long ones contribute none
- **Why:** "beyond this, a mask is a fingerprint of one value rather than of a
  format" — and an unbounded mask on a free-text column fills the TopK with
  unique keys

### PRO-040 · Masks generalise the right character classes
- **Area:** `profile/statistics.py::_MASK_TRANSLATION`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `GB0002634946`, `abc-123`, `ÄÖÜ`, `£1.50`
- **Steps:** profile and read the masks
- **Expected:** `AA9999999999`, `aaa-999`, `ÄÖÜ` unchanged (non-ASCII letters are
  not in the table), `£9.99`
- **Why:** "a single dominant mask is a format control waiting to be written";
  non-ASCII passing through unmasked means a unicode column produces one mask per
  value and no format finding

### PRO-041 · Blank strings are counted separately from nulls
- **Area:** `profile/statistics.py::_add_string`, `StringSummary.blank_count`
- **Type:** functional
- **Priority:** P1
- **Precondition:** values `["a", "", "   ", "\t", None]`
- **Steps:** profile
- **Expected:** `nulls == 1`, `blank_count == 3`, `min_length == 0`
- **Why:** an empty string is a different defect from a null — it passes
  `IS NOT NULL` — and the two being conflated is why a completeness control can
  pass on an empty column

### PRO-042 · `is_fixed_length` requires a positive common length
- **Area:** `profile/statistics.py::StringSummary.is_fixed_length`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** summaries with min=max=12; min=max=0; min=2,max=12; min=None
- **Steps:** read the property
- **Expected:** `True`, `False`, `False`, `False`
- **Why:** an all-empty string column is fixed-length in arithmetic and not in
  any useful sense; a format control derived from it would assert length zero

### PRO-043 · The variance is clamped at zero
- **Area:** `profile/statistics.py::_numeric_summary`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a column of 1,000,000 copies of `1e8` plus one `1e8 + 1`
- **Steps:** profile and read `stddev`
- **Expected:** a real number, never `nan`
- **Why:** the sum-of-squares formula is numerically unstable at large means;
  `max(0.0, …)` is what stops `math.sqrt` of a small negative, and this is the
  case that produces one

### PRO-044 · Merging refuses a column-name mismatch
- **Area:** `profile/statistics.py::ColumnAccumulator.merge`
- **Type:** negative
- **Priority:** P1
- **Precondition:** accumulators for `notional` and `quantity`
- **Steps:** merge
- **Expected:** `ValidationError` naming both, remedy "Merge accumulators column
  by column, matching on name."
- **Why:** a mis-paired merge silently combines two columns' distributions into
  one, and nothing downstream could detect it

### PRO-045 · Merging columns of different types records both
- **Area:** `profile/statistics.py::ColumnAccumulator.merge`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** the same column profiled as `VARCHAR` in one segment and
  `TEXT` in another
- **Steps:** merge and read `type_name`
- **Expected:** `TEXT|VARCHAR` — sorted and joined, not one of the two
- **Why:** "a segment written before a type change holds real data and excluding
  it would understate the table. But the merged profile must not claim a single
  type the column no longer has"

### PRO-046 · A merged accumulator's counts are exact
- **Area:** `profile/statistics.py::ColumnAccumulator.merge`
- **Type:** contract
- **Priority:** P1
- **Precondition:** two halves of a column
- **Steps:** merge and compare against accumulating the whole
- **Expected:** `rows`, `nulls`, `blank_count`, `min_length`, `max_length`,
  `mean_length`, `mean` and `stddev` identical; the sketched quantities within
  their own declared error
- **Why:** "exact for the counted quantities; the estimated ones inherit each
  sketch's own declared error and gain none from the merge itself" — which is
  what makes a folded profile the profile a single scan would have produced

### PRO-047 · The CountMin a profile builds is never read
- **Area:** `profile/statistics.py::ColumnAccumulator._frequency`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** grep `_frequency` in `statistics.py`
- **Expected:** three references — construction, `add`, and the merge; none in
  `profile()`
- **Why:** every value in every column is hashed five times and written into a
  2,048×5 table whose output reaches no profile, no metric point and no finding.
  Either the frequency estimate belongs in `ColumnProfile` or the sketch belongs
  out of the accumulator

### PRO-048 · `character_classes` reports every family present
- **Area:** `profile/statistics.py::character_classes`
- **Type:** functional
- **Priority:** P3
- **Precondition:** none
- **Steps:** classify `GB00`, `abc`, `a-b`, `naïve`, `""`, `"  "`
- **Expected:** `{upper,digit}`; `{lower}`; `{lower,punctuation}`;
  `{lower,non_ascii}`; `set()`; `{punctuation}`
- **Why:** this is the input to semantic typing; a space counting as punctuation
  and an empty string classifying as nothing are both worth pinning

## `profile/profiler.py` — profiling an object end to end

### PRO-049 · A profile records how it was produced
- **Area:** `profile/profiler.py::Profiler.profile`, `ProfileProvenance`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a SQLite source
- **Steps:** profile with a sampled plan and serialise `provenance`
- **Expected:** `computed_at`, `snapshot` (with its `exact` flag), `sampling`,
  `representative`, `rows_examined`, `complete`, `duration_seconds` and
  `confidence` all present
- **Why:** "a statistic without that provenance cannot be replayed, and a
  threshold derived from one cannot be defended"

### PRO-050 · The confidence note matches the plan
- **Area:** `profile/profiler.py::ProfileProvenance.confidence_note`
- **Type:** functional
- **Priority:** P1
- **Precondition:** four provenances — full and untruncated; full but truncated;
  HEAD; systematic at 1%
- **Steps:** read the note
- **Expected:** "measured over all 1,000 rows"; an estimated-from note (because
  `is_complete` is False); "read the first 1,000 rows only — indicative of shape,
  not of any rate"; "estimated from 1,000 sampled rows (systematic sample at 1%)"
- **Why:** "rendered next to every derived threshold, so nobody mistakes a
  sampled estimate for a measured fact"

### PRO-051 · A truncated profile is not complete
- **Area:** `profile/profiler.py::ProfileProvenance.is_complete`,
  `Profiler.accumulate`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `Profiler(max_rows=1000)` and a 25,000-row table
- **Steps:** profile
- **Expected:** `truncated is True`, `is_complete is False`, an INFO log naming
  the budget, and `rows_examined` recorded as what was actually read
- **Why:** "stopping is honest and recorded; silently reading 40 GB because
  nobody set a limit is not"

### PRO-052 · The row budget is a floor, not a ceiling
- **Area:** `profile/profiler.py::Profiler.accumulate`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `Profiler(max_rows=1000)` and a source whose batches are
  10,000 rows
- **Steps:** profile and read `rows_examined`
- **Expected:** 10,000 — the check is after the batch is consumed
- **Why:** a "1,000-row budget" that reads ten thousand is a promise a source
  owner was shown and that is not kept; whether that is acceptable is a decision,
  but it must be a stated one

### PRO-053 · Columns are ordered by the schema, with extras appended
- **Area:** `profile/profiler.py::Profiler.assemble`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a batch whose columns are in a different order from
  `describe()`, plus one column the schema does not declare
- **Steps:** assemble
- **Expected:** the schema's order first, then the extra
- **Why:** a profile rendered in Arrow's order changes when a connector changes
  its projection; and a column present in the data and not in the catalogue is a
  finding that must not be dropped

### PRO-054 · A column's declared type is preferred over Arrow's
- **Area:** `profile/profiler.py::Profiler.accumulate`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a `NUMERIC(38,12)` column arriving as an Arrow string
- **Steps:** profile and read `type_name`
- **Expected:** the source's declared type, not `string`
- **Why:** the type name reaches a control proposal; proposing a text-format
  control on a decimal column is a proposal nobody will accept

### PRO-055 · `capture_snapshot=False` takes no snapshot
- **Area:** `profile/profiler.py::Profiler.accumulate`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a connector counting `snapshot` calls
- **Steps:** accumulate with the flag false
- **Expected:** zero calls; `provenance.snapshot is None`
- **Why:** segmented profiling takes one snapshot for the object and reuses it
  for every segment; per-segment snapshots would be N round trips and N different
  identifiers for one read

### PRO-056 · A profile of an unreadable object does not stop a source sweep
- **Area:** `profile/profiler.py::Profiler.profile_source`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a source of five objects where the second raises on read
- **Steps:** `profile_source(connector)`
- **Expected:** four profiles returned and a WARNING naming the failed object
- **Why:** a sweep that stopped on the first unreadable table leaves the rest of
  the estate unexamined for a reason nobody can see

### PRO-057 · A source sweep profiles the largest first
- **Area:** `profile/profiler.py::Profiler.profile_source`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a source of ten objects of differing size, `limit=3`
- **Steps:** sweep
- **Expected:** the three largest, in size order
- **Why:** "a budget will eventually bind, and the objects a person cares about
  are almost never the small ones" — the ordering comes from `discover()`, so
  this also pins that the sweep does not re-sort

### PRO-058 · `suggest_sample_plan` reads everything below the ceiling
- **Area:** `profile/profiler.py::suggest_sample_plan`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** suggest for `None`, `0`, `5_000_000`, `5_000_001`, `100_000_000`
- **Expected:** FULL for the first four; for the last, SYSTEMATIC at
  `fraction == 0.01` with `seed=1`
- **Why:** "below the ceiling, read everything: an exact rate is worth more than
  the compute saved"; and an unknown row count must default to the complete read
  rather than to a guess

### PRO-059 · A suggested sample carries a non-zero seed
- **Area:** `profile/profiler.py::suggest_sample_plan`
- **Type:** regression
- **Priority:** P1
- **Precondition:** an estimate above the ceiling
- **Steps:** read `plan.seed`
- **Expected:** `1`
- **Why:** `SamplePlan.seed` defaults to 0, and on SQLite a seed of 0 collapses
  the systematic ordering to rowid order (CON-130) — an unseeded "systematic"
  sample is HEAD wearing a representative label

### PRO-060 · `detectable_rate` is the rule of three
- **Area:** `profile/profiler.py::detectable_rate`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** evaluate for 0, -1, 1, 3, 10_000, 1_000_000; and at
  `confidence=0.9`
- **Expected:** `1.0`, `1.0`, `1.0` (clamped), `1.0`, `0.0003`, `0.000003`;
  the 0.9 case uses 2.3 as the multiplier
- **Why:** "this is the number that turns 'we sampled 1%' into a sentence a
  business owner can act on — 'we would have caught anything above 0.03%'"; a
  rate above 1.0 would be a nonsense a screen would render

### PRO-061 · `from_rows` requires a plan
- **Area:** `profile/profiler.py::from_rows`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** call without `plan`
- **Expected:** `TypeError` — it is keyword-only with no default
- **Why:** "a caller who has not thought about how these rows were obtained has
  not earned a profile that claims they are representative"

### PRO-062 · A column absent from a row is absent, not null
- **Area:** `profile/profiler.py::from_rows`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** rows `[{"a":1,"b":2}, {"a":3}]`
- **Steps:** profile
- **Expected:** `a.rows == 2`, `b.rows == 1`, `b.nulls == 0`,
  `b.null_rate == 0.0`, and `provenance.rows_examined == 2`
- **Why:** "a row that did not carry the key is a row the query did not return it
  for, and counting it as a null would invent a completeness defect out of a
  projection" — and the consequence is that two columns in one profile have
  different denominators

### PRO-063 · `from_rows` is not exported
- **Area:** `profile/__init__.py::__all__`
- **Type:** documentation
- **Priority:** P3
- **Precondition:** none
- **Steps:** `from prama.profile import from_rows`
- **Expected:** it resolves — but the name is absent from `__all__` while
  `points_from_profile`, `detectable_rate` and `suggest_sample_plan` are present
- **Why:** the console reaches for it by module path; a public function the
  package does not advertise is one a second implementation gets written beside

## `profile/segments.py`, `segmented.py`, `incremental.py`

### PRO-064 · A daily segmentation covers the range inclusively
- **Area:** `profile/segments.py::Segmentation.over_dates` / `._daily`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `Segmentation("booked", DAY)`
- **Steps:** `over_dates(2026-03-30, 2026-04-01)`; then a single-day range
- **Expected:** three segments keyed `2026-03-30`…`2026-04-01`, each with
  `lower` the day and `upper` the next; one segment for the single day
- **Why:** the bounds are inclusive-lower, exclusive-upper, and an off-by-one
  either double-counts a day's rows or drops them

### PRO-065 · A monthly segmentation crosses a year boundary
- **Area:** `profile/segments.py::Segmentation._monthly`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `Segmentation("booked", MONTH)`
- **Steps:** `over_dates(2026-11-15, 2027-02-03)`
- **Expected:** four segments `2026-11`, `2026-12`, `2027-01`, `2027-02`; the
  December segment's `upper` is 2027-01-01
- **Why:** the `(year+1, 1) if month == 12` rollover is the only place a year
  boundary is handled, and a wrong one silently loses December

### PRO-066 · A reversed range is refused
- **Area:** `profile/segments.py::Segmentation.over_dates`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `over_dates(2026-04-01, 2026-03-01)`
- **Expected:** `ValidationError` "the segmentation range ends before it begins",
  remedy "Give the earlier date first."
- **Why:** the `while` loops would return an empty list, and an empty
  segmentation is reported by `IncrementalPlan.render` as "Nothing to examine"

### PRO-067 · Too many segments is a refusal, not a truncation
- **Area:** `profile/segments.py::Segmentation._check_count`, `MAX_SEGMENTS`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a daily segmentation over 2,000 and over 2,001 days; and
  `over_values` of 2,001 distinct values
- **Steps:** build each
- **Expected:** 2,000 succeeds; both 2,001 cases raise `ValidationError` naming
  the count and the maximum
- **Why:** "a silently truncated segmentation reports 'all segments healthy'
  while never having looked at most of them"

### PRO-068 · A non-temporal grain cannot be built from dates
- **Area:** `profile/segments.py::Segmentation.over_dates`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `Segmentation("region", VALUE)` and `Segmentation("", NONE)`
- **Steps:** `over_dates(...)` on each
- **Expected:** `ValidationError` pointing at `over_values()`
- **Why:** a categorical segmentation silently producing date segments would
  filter on a column that holds region codes and return nothing for every day

### PRO-069 · A segmentation with no column is refused
- **Area:** `profile/segments.py::Segmentation.__post_init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `Segmentation("", DAY)`; then `Segmentation("", NONE)`
- **Expected:** the first raises with a remedy naming the business date; the
  second is allowed
- **Why:** `NONE` is the "do not segment" case and legitimately has no column

### PRO-070 · `over_values` deduplicates, sorts and drops nulls
- **Area:** `profile/segments.py::Segmentation.over_values`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** values `["EMEA", None, "APAC", "EMEA", 3, "3"]`
- **Steps:** build
- **Expected:** four segments, ordered by `str(value)`, no null segment; `3` and
  `"3"` are distinct segments whose keys are both `"3"`
- **Why:** a null segment would render as `column = NULL`, which matches nothing
  in SQL; and two segments with the same key collide in
  `SegmentedProfile._segments`, which is keyed by `segment.key`

### PRO-071 · A segment predicate quotes the column and escapes the value
- **Area:** `profile/segments.py::Segment.predicate`, `_literal`
- **Type:** security
- **Priority:** P1
- **Precondition:** a VALUE segment for `O'Brien Desk` on a column named
  `desk"name`
- **Steps:** render the predicate with the default quoter
- **Expected:** the column double-quoted with its quote doubled; the value
  single-quoted with its quote doubled
- **Why:** "segment columns come from a customer's catalogue and end up in a
  query string", and a distinct-value list is a customer's data

### PRO-072 · `_literal` renders each type as legal SQL
- **Area:** `profile/segments.py::_literal`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** render `None`, `True`, `False`, `7`, `7.5`, `float("nan")`,
  `float("inf")`, `date(2026,4,1)`, `datetime(2026,4,1,6,30)`, `"x"`
- **Expected:** `NULL`, `1`, `0`, `7`, `7.5`, **`nan`**, **`inf`** — neither is
  valid SQL — then `'2026-04-01'`, `'2026-04-01T06:30:00'`, `'x'`
- **Why:** a `nan` reaches here through `over_values` on a float column with a
  missing value that survived as `nan` rather than `None`, and the resulting
  predicate is a syntax error attributed to the source

### PRO-073 · A `NONE`-grain segment's predicate matches nothing
- **Area:** `profile/segments.py::Segment.predicate`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `Segment(key="all", column="c", grain=SegmentGrain.NONE)`
- **Steps:** render the predicate
- **Expected:** `"c" >= NULL AND "c" < NULL` — which matches no row
- **Why:** the method branches only on `VALUE` and falls through to the range
  form for everything else; a `NONE` segment profiles zero rows and reports
  them as the dataset's

### PRO-074 · A segmented refresh refuses a connector that cannot filter
- **Area:** `profile/segmented.py::SegmentedProfiler.refresh`
- **Type:** negative
- **Priority:** P1
- **Precondition:** the REST connector
- **Steps:** `refresh(connector, path, segments)`
- **Expected:** `ConnectorError` code `CONNECT.NO_PREDICATE` before any read
- **Why:** the probe `require_predicate_support(SamplePlan(predicate="x"))` is
  the one line standing between a non-filtering source and a whole object's data
  attributed to one segment

### PRO-075 · A refresh with no segments is refused
- **Area:** `profile/segmented.py::SegmentedProfiler.refresh`
- **Type:** negative
- **Priority:** P2
- **Precondition:** an empty segment list
- **Steps:** refresh
- **Expected:** `ValidationError` naming the object, remedy "Declare the
  segmentation — usually by business date — or profile the dataset whole."
- **Why:** an empty refresh would return an empty `SegmentedProfile` whose
  `folded()` is `None` and whose `to_dict` reports zero rows — indistinguishable
  from a dataset that is empty

### PRO-076 · Segment reads are bounded by the declared concurrency
- **Area:** `profile/segmented.py::SegmentedProfiler.refresh`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** 400 segments, `concurrency=4`, an instrumented connector
- **Steps:** refresh and record the maximum simultaneous reads
- **Expected:** never more than 4
- **Why:** "the point of reading less is to be gentler on the source, and firing
  four hundred partition queries at once would undo that entirely"

### PRO-077 · One failing segment fails the refresh
- **Area:** `profile/segmented.py::SegmentedProfiler.refresh`
- **Type:** negative
- **Priority:** P1
- **Precondition:** 10 segments where the fourth raises on read
- **Steps:** refresh
- **Expected:** record what happens — `asyncio.gather` with no
  `return_exceptions` propagates the first exception, the other nine reads are
  cancelled mid-flight, and nothing is recorded in the ledger
- **Why:** `Profiler.profile_source` handles the equivalent case by logging and
  continuing. A partial refresh that recorded nine segments and named the tenth
  would be a finding; an exception loses the nine that worked

### PRO-078 · A folded profile is as current as its oldest part
- **Area:** `profile/segmented.py::SegmentedProfile.folded`
- **Type:** contract
- **Priority:** P1
- **Precondition:** segments profiled a month apart
- **Steps:** fold and read `provenance.computed_at`
- **Expected:** the *oldest* segment's time
- **Why:** "a folded profile stamped with the newest segment's time would make a
  segment that has not been looked at for a month appear fresh"

### PRO-079 · A folded profile drops the segment predicate
- **Area:** `profile/segmented.py::SegmentedProfile.folded`
- **Type:** functional
- **Priority:** P1
- **Precondition:** segments read with per-segment predicates
- **Steps:** fold and read `provenance.plan`
- **Expected:** `predicate == ""`, so `is_complete` reflects the strategy alone
- **Why:** the fold covers every segment, so the whole is complete even though
  each part was not — and `SamplePlan.is_complete` is what a threshold's
  confidence note reads

### PRO-080 · A folded profile equals a single scan
- **Area:** `profile/segmented.py::SegmentedProfile.folded`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a dataset profiled whole, and the same dataset profiled in
  five segments
- **Steps:** compare every counted statistic and every sketched one
- **Expected:** counts identical; sketched values within their declared error
- **Why:** "this is the profile a single scan would have produced, which is the
  property the whole design rests on"

### PRO-081 · A column present in only some segments folds with a short denominator
- **Area:** `profile/segmented.py::SegmentedProfile.folded`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a dataset that gained a column mid-year, profiled by month
- **Steps:** fold and read that column's `rows` and `null_rate`
- **Expected:** record both
- **Why:** the fold merges accumulators by name, so a column absent from earlier
  segments has only the later segments' row count as its denominator, while every
  other column in the same profile has the full one. A null rate computed over a
  different denominator from its neighbours is the shape of finding PRO-062 at
  dataset scale

### PRO-082 · `divergent` compares against the median
- **Area:** `profile/segmented.py::SegmentedProfiler.divergent`
- **Type:** functional
- **Priority:** P1
- **Precondition:** rates of 0.0 across nine segments and 1.0 in the tenth
- **Steps:** `divergent(rates, tolerance=0.2)`
- **Expected:** exactly the tenth
- **Why:** "one catastrophic segment drags a mean far enough to make itself look
  ordinary, which is exactly the segment worth finding"

### PRO-083 · Fewer than three segments cannot diverge
- **Area:** `profile/segmented.py::SegmentedProfiler.divergent`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** rate lists of length 0, 1, 2 and 3
- **Steps:** call for each
- **Expected:** `[]`, `[]`, `[]`, a result
- **Why:** "two segments cannot tell which of them is the odd one out"; a
  two-segment divergence report is a coin flip presented as a finding

### PRO-084 · `compare` returns None for a column a segment does not have
- **Area:** `profile/segmented.py::SegmentedProfiler.compare`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a column absent from one segment
- **Steps:** compare
- **Expected:** `(key, None)` for that segment, and `divergent` excludes it
- **Why:** "no rate" and "a rate of zero" are different; the second would look
  like a perfectly clean month

### PRO-085 · A never-profiled segment is NEW
- **Area:** `profile/incremental.py::IncrementalPlanner._state`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an empty ledger
- **Steps:** plan five segments
- **Expected:** all five `NEW`, all `needs_read`, `saved_fraction == 0.0`, and
  `render()` reads "Reading all 5 segments — never profiled."
- **Why:** the first run has to read everything, and the reason is what an
  auditor reads

### PRO-086 · An inexact snapshot makes every segment UNVERIFIABLE
- **Area:** `profile/incremental.py::IncrementalPlanner._state`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a ledger with records, and a `WALL_CLOCK` snapshot (or none)
- **Steps:** plan
- **Expected:** every segment `UNVERIFIABLE` and read again, with the reason
  "this source offers no exact snapshot, so no segment can be assumed unchanged"
- **Why:** "a tool that assumes immutability it cannot verify will be wrong
  silently, and the failure surfaces months later as a number nobody can
  reproduce"

### PRO-087 · A settled segment is reused
- **Area:** `profile/incremental.py::IncrementalPlanner._state`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a ledger recording an exact snapshot identifier, a frozen
  clock, segments older than the mutable window, and the same snapshot now
- **Steps:** plan
- **Expected:** `SETTLED`, not read, `saved_fraction` reflecting them
- **Why:** this is the whole economic claim — "a nightly refresh costs the part
  that changed rather than the whole table"

### PRO-088 · One changed row re-reads every segment
- **Area:** `profile/incremental.py::IncrementalPlanner._state`,
  `SegmentLedger.record`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 400 daily segments all recorded against object snapshot `A`;
  the object's snapshot is now `B` because today's partition gained a row
- **Steps:** plan
- **Expected:** record how many segments are `CHANGED`
- **Why:** the ledger stores the *object-level* snapshot against each segment, so
  any write anywhere in the table invalidates every segment. On an append-only
  ledger — the motivating case — nothing is ever reused, and the module's claim
  that "a settled segment never needs reading again" holds only for a table that
  has stopped changing entirely

### PRO-089 · The mutable window is inclusive of its boundary day
- **Area:** `profile/incremental.py::IncrementalPlanner._is_mutable`,
  `DEFAULT_MUTABLE_DAYS`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `mutable_days=3`, a clock at 2026-04-10, daily segments for
  2026-04-06 through 2026-04-10
- **Steps:** plan (with the ledger current and the snapshot exact)
- **Expected:** the cutoff is 2026-04-07; a segment is mutable when its *upper*
  bound is after it, so 2026-04-06 (upper 04-07) is `SETTLED` and 2026-04-07
  (upper 04-08) is `MUTABLE`
- **Why:** "three days rather than one, because a Friday's late correction lands
  on Monday and a window of one day would miss it every weekend"; the exclusive
  upper bound is what makes the arithmetic off by one from the obvious reading

### PRO-090 · A categorical segment never settles
- **Area:** `profile/incremental.py::IncrementalPlanner._is_mutable`
- **Type:** functional
- **Priority:** P1
- **Precondition:** VALUE segments with a current ledger and an exact snapshot
- **Steps:** plan
- **Expected:** every segment `MUTABLE`
- **Why:** "a categorical one — by entity, by product — has no age, so nothing
  about it can be called old enough to stop checking"

### PRO-091 · A segment recorded against an inexact snapshot is CHANGED
- **Area:** `profile/incremental.py::IncrementalPlanner._state`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a ledger entry with `snapshot_exact=False` and a *now* exact
  snapshot with a matching identifier
- **Steps:** plan
- **Expected:** `CHANGED`, not `SETTLED`
- **Why:** the earlier record's identifier cannot be compared meaningfully, so
  the source having become exact does not retroactively validate it

### PRO-092 · `forget` forces a full re-read of one dataset only
- **Area:** `profile/incremental.py::SegmentLedger.forget`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a ledger holding records for two datasets
- **Steps:** `forget("a")`, then plan both
- **Expected:** every `a` segment `NEW`; every `b` segment unchanged
- **Why:** "needed after a declaration changes in a way that invalidates earlier
  profiles — a column reinterpreted, a segmentation redrawn"

### PRO-093 · `render` generalises one segment's reason to all of them
- **Area:** `profile/incremental.py::IncrementalPlan.render`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a plan where segment 1 is `NEW` and segments 2–5 are
  `MUTABLE`, so every segment is read
- **Steps:** `render()`
- **Expected:** record the sentence — it reads `Reading all 5 segments —
  <decisions[0].state.reason>`, i.e. "never profiled", which is true of one
- **Why:** the summary is what an operator reads to understand why a refresh
  cost what it did; attributing four segments' reason to a fifth's is a wrong
  explanation of a correct decision

### PRO-094 · `saved_fraction` of an empty plan is zero, not one
- **Area:** `profile/incremental.py::IncrementalPlan.saved_fraction`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `IncrementalPlan(decisions=())`
- **Steps:** read the property and `render()`
- **Expected:** `0.0`; "Nothing to examine: the segmentation produced no
  segments."
- **Why:** a saved fraction of 1.0 on an empty plan would report a perfect
  reuse rate for a refresh that did nothing

## `profile/recording.py`

### PRO-095 · Every recorded point carries the profile's provenance
- **Area:** `profile/recording.py::points_from_profile`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a sampled profile with a snapshot
- **Steps:** build the points and inspect one
- **Expected:** `snapshot_id`, `snapshot_exact`, `sampling`, `representative`
  and `rows_examined` on every point
- **Why:** "a baseline that silently mixed full scans with 1% samples would be
  wrong in a way nobody could detect afterwards"

### PRO-096 · Only the statistics a monitor tracks become series
- **Area:** `profile/recording.py::COLUMN_METRICS`, `NUMERIC_METRICS`,
  `STRING_METRICS`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a profile of one numeric and one string column
- **Steps:** build the points and list the metric names
- **Expected:** `row_count`, `duration_seconds`, the four column metrics per
  column, the four numeric ones, seven quantiles, and the four string ones; **no**
  `top_values` and **no** `top_masks`
- **Why:** "recording the former as time series would fill the store with rows
  nothing ever queries"

### PRO-097 · A None statistic is skipped, not recorded as zero
- **Area:** `profile/recording.py::points_from_profile`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a numeric summary whose `stddev` is `None`, and a string
  summary whose `min_length` is `None`
- **Steps:** build the points
- **Expected:** neither metric appears
- **Why:** a stddev of 0.0 recorded for a column that has none is a baseline a
  monitor would learn from and then alert against

### PRO-098 · A column with no values produces its four column metrics anyway
- **Area:** `profile/recording.py::COLUMN_METRICS`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an all-null column
- **Steps:** build the points
- **Expected:** `null_count == rows`, `null_rate == 1.0`,
  `distinct_count == 0`, `distinct_ratio == 0.0`
- **Why:** these four are unconditional, which is right — a column that went
  entirely null is the series that should have a point on the day it happened

## `discover/relationships.py`

### PRO-099 · A generic column name never proposes a relationship
- **Area:** `discover/relationships.py::_is_generic`, `GENERIC_NAMES`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two samples sharing only `id`, `status` and `created_at`
- **Steps:** `discover(left, right)`
- **Expected:** no candidates; `suppressed == {"generic_name": 3}`
- **Why:** "matching on column name proposes a relationship between every pair of
  tables in the estate, which is a report nobody can read and which discredits
  the ones that were real"

### PRO-100 · The suppressed count is reported rather than the pairs
- **Area:** `discover/relationships.py::DiscoveryReport.suppressed`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a sweep producing 412 generic-name matches
- **Steps:** read `suppressed`
- **Expected:** `{"generic_name": 412}`
- **Why:** "'412 pairs matched on id' tells somebody why the report is short,
  where 412 entries would tell them nothing and bury the four that mattered"

### PRO-101 · `_is_generic` strips punctuation before matching
- **Area:** `discover/relationships.py::_is_generic`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** test `id`, `ID`, `Id`, `i-d`, `account_id`, `id2`, `_id`
- **Expected:** the first four generic (the regex strips `-`); `account_id`,
  `id2` and `_id` not generic (`_` is kept, so `_id` is `_id`)
- **Why:** `account_id` is the single most useful join key in a banking estate
  and must survive; `_id` is Mongo's primary key and its treatment is worth
  pinning

### PRO-102 · Confidence combines signals rather than averaging them
- **Area:** `discover/relationships.py::CandidateRelationship.confidence`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a candidate with one signal at 0.8; one with two at 0.35;
  one with 0.8 and 0.35
- **Steps:** read `confidence`
- **Expected:** 0.80; 0.5775; 0.87
- **Why:** "two weak agreeing signals beat one strong one, which is the whole
  reason to gather five of them — averaging would let a single naming match drag
  a well-corroborated candidate down to its level"

### PRO-103 · A strength of 1.0 does not produce certainty
- **Area:** `discover/relationships.py::CandidateRelationship.confidence`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an evidence item with `strength=1.0`, one with `2.0`, one
  with `-1.0`
- **Steps:** read `confidence`
- **Expected:** 0.95 for the first two (clamped), 0.0 for the third
- **Why:** `min(0.95, max(0.0, …))` is what stops a proposal reading as a
  conclusion; nothing here is ever certain, and a 1.0 on a screen is a
  declaration

### PRO-104 · A single-signal candidate says it is a question
- **Area:** `discover/relationships.py::CandidateRelationship.describe` /
  `.is_corroborated`, `CORROBORATING_SIGNALS`
- **Type:** functional
- **Priority:** P1
- **Precondition:** candidates with one and with two pieces of evidence
- **Steps:** `describe()`
- **Expected:** the first ends "This rests on a single signal — … — which is a
  question rather than a finding"; the second does not
- **Why:** "a reviewer looking at 'the names match, the values are contained, and
  they are joined together in forty queries a week' approves in a second; the
  same candidate showing only the first is a question rather than a finding, and
  should look like one"

### PRO-105 · The kind's prompt is quoted, not slotted into a sentence
- **Area:** `discover/relationships.py::CandidateRelationship.describe`
- **Type:** regression
- **Priority:** P2
- **Precondition:** a `REFERENCES` candidate between `positions` and `accounts`
- **Steps:** `describe()`
- **Expected:** "positions → accounts may be references: records here point at
  records there, matched on …" — not "positions may records here point at
  records there accounts"
- **Why:** the comment records the exact wrong sentence this produced; the prompt
  is written for a screen that already names both datasets

### PRO-106 · Schema signature needs three distinctive columns on each side
- **Area:** `discover/relationships.py::RelationshipDiscoverer._signature`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** pairs with 2 and with 3 distinctive columns each, at 59% and
  61% overlap
- **Steps:** discover
- **Expected:** `None` below three columns and below 60% overlap; an `Evidence`
  at three columns and 61%, with strength `0.5 + 0.3 × overlap`
- **Why:** "finds copies, replicas and migrations that nothing else finds, and
  genuinely cannot distinguish them from two tables built from the same template
  — which is why it contributes a signal rather than a verdict"

### PRO-107 · Co-access is passed in, never read here
- **Area:** `discover/relationships.py::RelationshipDiscoverer.discover`
- **Type:** contract
- **Priority:** P2
- **Precondition:** `co_access=40, co_access_total=200`; and
  `co_access=0, co_access_total=200`; and `co_access=40, co_access_total=0`
- **Steps:** discover
- **Expected:** strength `min(0.9, 0.4 + 0.2) == 0.6` in the first; no co-access
  evidence in the other two
- **Why:** "the query log is a connector's concern and is frequently unavailable
  — a discoverer that needed it would be a discoverer that does not run"

### PRO-108 · `KEY_OVERLAP` is declared and never emitted
- **Area:** `discover/relationships.py::Signal.KEY_OVERLAP`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** grep `KEY_OVERLAP` in `src/`
- **Expected:** one reference — its declaration
- **Why:** the module docstring opens "`FR-MET-065`: key overlap, containment,
  naming, schema signature, query-log co-access. **Five signals**". Four are
  produced. A reviewer reading "this rests on a single signal" has no way to know
  one of the five never fires

### PRO-109 · Ranking is stable and deterministic
- **Area:** `discover/relationships.py::rank`,
  `RelationshipDiscoverer.discover`'s sort
- **Type:** functional
- **Priority:** P3
- **Precondition:** several reports with tied confidences
- **Steps:** rank twice from differently ordered inputs
- **Expected:** identical order — ties break on `left` then `right`, and within
  a report on `match_keys[0].left`
- **Why:** a candidate list rendered in a different order on each refresh is one
  a reviewer cannot work through

## `execute/run.py` — the control run

### EXE-001 · The run marker survives the process dying
- **Area:** `execute/run.py::ControlRun.execute_all`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a tenant with live controls
- **Steps:** start `execute_all`, kill the process after the marker is written
  and before any control finishes, then reopen the database and call
  `unfinished()`
- **Expected:** one run row with status `running`
- **Why:** finding X5. "A run is opened before it does anything. If the process
  dies mid-run the row stays `running`, and `unfinished()` surfaces it" was the
  module docstring; the class docstring promised one transaction, the transaction
  won, and the operations screen rendered "0 unfinished runs" to an operator

### EXE-002 · The marker is committed on the same session
- **Area:** `execute/run.py::ControlRun.execute_all`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** SQLite
- **Steps:** run `execute_all` with a caller that has pending uncommitted work
  on the same unit of work
- **Expected:** no deadlock; the caller's pending work is committed too
- **Why:** "the first attempt opened an independent transaction and deadlocked on
  SQLite, which permits a single writer. The cost — a caller with pending work of
  its own has it committed too — is why this is the first thing `execute_all`
  does"

### EXE-003 · A run that finishes is closed in its own transaction
- **Area:** `execute/run.py::ControlRun.execute_all`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a tenant with one passing control
- **Steps:** run, then read the run row
- **Expected:** status `complete`, `finished_at` set, `detail` equal to
  `report.describe()`
- **Why:** "a run marked complete inside a transaction that then fails to commit
  is a run that looks finished and wrote nothing"

### EXE-004 · `complete` means finished, not passed
- **Area:** `execute/run.py::ControlRun.execute_all`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a tenant where every control errors
- **Steps:** run and read the run row
- **Expected:** status `complete`; `detail` naming the error count
- **Why:** "conflating the two would hide a total outage behind a green run"

### EXE-005 · A run that raises mid-flight leaves the marker open
- **Area:** `execute/run.py::ControlRun.execute_all`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a unit of work whose `evidence.append` raises on the third
  control
- **Steps:** run; then call `unfinished()`
- **Expected:** the exception propagates and the run row is still `running`
- **Why:** there is no `try/finally` around the control loop, which is the
  *correct* behaviour for X5 — but it means a ledger failure produces a run that
  is permanently `running` rather than one marked failed, and an operator needs
  to know which of the two states means what

### EXE-006 · Only `active` controls run
- **Area:** `execute/run.py::ControlRun.execute_all`, `uow.controls.live`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a tenant with active, proposed and suppressed controls
- **Steps:** run
- **Expected:** only the active ones produce outcomes
- **Why:** "a coverage figure cannot count protection the estate has not agreed
  to"

### EXE-007 · A control that will not compile is a finding, not a crash
- **Area:** `execute/run.py::ControlRun._run_one`
- **Type:** negative
- **Priority:** P1
- **Precondition:** five live controls where the second holds unparseable PQL
- **Steps:** run
- **Expected:** five outcomes; the second has verdict `error` with a detail
  beginning "could not be compiled:"; the other four ran
- **Why:** "raising would take every control after it down with it", and the
  estate would go unchecked for a reason nobody can see

### EXE-008 · A source that will not answer is a finding, not a crash
- **Area:** `execute/run.py::ControlRun._run_one`
- **Type:** negative
- **Priority:** P1
- **Precondition:** an executor raising on the second control
- **Steps:** run
- **Expected:** an `error` record naming the exception type and message; the rest
  of the estate runs
- **Why:** the same rule applied to the source rather than the control; both
  produce an `error` record rather than a gap

### EXE-009 · A run over a segmented control judges every segment
- **Area:** `execute/run.py::ControlRun._run_one`, `_segments_from`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a `FOR EACH region` control returning five rows where only
  the fourth violates
- **Steps:** run
- **Expected:** verdict `fail`; the record's metrics are the judged result's, not
  row zero's
- **Why:** QA finding Q-11. "`rows[0]` was all `_metrics_from` ever looked at, so
  1 segment of 5 decided the verdict, the totals came from that segment alone,
  and the samples in the same record contradicted its own metrics"

### EXE-010 · A numeric segment key becomes a metric
- **Area:** `execute/run.py::_segments_from`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a `FOR EACH booking_year` control whose grouped query returns
  `{"booking_year": 2026, "scanned_rows": 100, "violating_rows": 3}`
- **Steps:** run and inspect the recorded metrics
- **Expected:** record whether `booking_year` appears as a metric
- **Why:** `_segments_from` keeps every numeric column as a metric, including the
  segment key itself. A threshold evaluated against a metric set containing
  `booking_year: 2026.0` is judging on a value that is not a measurement, and a
  string segment key would silently not do this — so the behaviour depends on the
  segment column's type

### EXE-011 · A segmented control returning one row falls through to the flat path
- **Area:** `execute/run.py::ControlRun._run_one`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a `FOR EACH` control over a dataset with exactly one segment
- **Steps:** run
- **Expected:** record which judgement path is used — the guard is
  `segment_by and len(rows) > 1`
- **Why:** a one-segment estate is judged by `judge` rather than
  `judge_segments`, so the two paths' enrichment of `result.metrics` must agree,
  or the same control produces differently shaped evidence on the day a second
  segment appears

### EXE-012 · The derived metrics reach the ledger
- **Area:** `execute/run.py::ControlRun._run_one`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a uniqueness control
- **Steps:** run and read the record's metrics
- **Expected:** `violating_rows` present
- **Why:** QA finding Q-13. "`judge` enriches a copy, so `violating_rows` for a
  uniqueness or functional-dependency control — which no engine returns and Prama
  computes from the two counts — existed only inside the result and never reached
  the ledger. The verdict was right and the evidence supporting it was missing
  the number it was based on"

### EXE-013 · An empty metric result is not judged as a pass
- **Area:** `execute/run.py::_metrics_from`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an executor returning `[]`
- **Steps:** run and read the verdict
- **Expected:** an empty metric set reaching `judge` — record the verdict
- **Why:** "an empty result is an empty metric set rather than zeros. Zeros would
  be judged — as a pass, since nothing violated — and 'the query returned no rows'
  is not a measurement of anything". Open finding Q-09 says the absolute-threshold
  path has no empty-scope guard, so this is where the two meet

### EXE-014 · Booleans are excluded from metrics
- **Area:** `execute/run.py::_metrics_from`, `_segments_from`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a metric row containing `{"passed": True, "scanned_rows": 10}`
- **Steps:** run
- **Expected:** `passed` absent from the metrics
- **Why:** `bool` is a subclass of `int`; a boolean column silently becoming the
  metric `1.0` would be compared against a numeric threshold

### EXE-015 · An incomplete screen cannot report a pass
- **Area:** `execute/run.py::ControlRun._run_one`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an `IS VALID` control whose compiled screen is a necessary
  condition, returning zero violations
- **Steps:** run
- **Expected:** verdict `indeterminate`, with a detail naming the unrun residual
  validators and saying a pass cannot be reported from a screen alone
- **Why:** "a lower bound of zero is not 'clean' — it is 'not established' — and
  reporting it as a pass is a false assurance about exactly the columns whose
  validation SQL cannot express"

### EXE-016 · A failing screen also carries the lower-bound caveat
- **Area:** `execute/run.py::ControlRun._run_one`
- **Type:** regression
- **Priority:** P1
- **Precondition:** the same control returning 11 violations of 23 rows
- **Steps:** run and read the detail
- **Expected:** a detail saying "11 is a LOWER BOUND on the violations; the
  residual (…) has not been run and the true count may be higher"
- **Why:** QA finding Q-10. "This caveat used to be attached only when the
  verdict would have been a pass — so 11-of-23 and 3-of-9 were recorded as
  completed measurements with nothing said. Disclosed exactly when the
  understatement was zero, and silent whenever it was not"

### EXE-017 · The threshold travels with the record
- **Area:** `execute/run.py::ControlRun._run_one`
- **Type:** regression
- **Priority:** P1
- **Precondition:** two controls with identical metrics and different thresholds
- **Steps:** run both and read `parameters["threshold"]`
- **Expected:** the two records' threshold strings differ and each names the
  values
- **Why:** QA finding Q-15. "Four records can carry identical metrics and
  opposite verdicts, distinguishable only by `plan_id` — a hash, so answering
  'why did this fail?' means resolving the plan." It sits inside `content()`, so
  the record hash covers it

### EXE-018 · The recorded snapshot is always wall-clock
- **Area:** `execute/run.py::ControlRun._run_one`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a run against a source that can produce an exact snapshot —
  PostgreSQL's LSN, SQLite's file digest, Snowflake's query id
- **Steps:** run and read `record.snapshot`
- **Expected:** record the kind
- **Why:** `_run_one` constructs
  `SnapshotRef(kind="wall_clock", identifier=started.isoformat())`
  unconditionally and never calls `connector.snapshot`. Every claim the SPI makes
  about exact snapshots — `SnapshotKind.is_exact`, `EXACT_SNAPSHOT`, the
  PostgreSQL recovery-aware LSN, Snowflake's Time Travel — terminates before the
  evidence record, so deterministic replay has nothing exact to replay against

### EXE-019 · Coverage is recorded as `full` whatever was read
- **Area:** `execute/run.py::ControlRun._run_one`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a control run against a sampled or watermark-narrowed scope
- **Steps:** run and read `record.coverage`
- **Expected:** record the value
- **Why:** `coverage="full"` is a literal. `execute/watermark.py::Coverage`
  exists precisely because "'positions_eod passed' after a full scan means the
  whole table is sound. The same words after an incremental run mean *today's
  rows* are sound" — and nothing connects the two

### EXE-020 · Samples are collected only for a non-passing control
- **Area:** `execute/run.py::ControlRun._store_samples`
- **Type:** security
- **Priority:** P1
- **Precondition:** a sampler, and controls that pass, fail and error
- **Steps:** run
- **Expected:** the sampler is called only for the failing one; the passing
  record carries `samples_digest == ""` and `sample_count == 0`
- **Why:** "sampling a passing control reads rows nobody needs and puts personal
  data on a retention clock for no reason"

### EXE-021 · A deployment with no sampler still gets verdicts
- **Area:** `execute/run.py::ControlRun._store_samples`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `ControlRun(..., sample=None)` and a failing control
- **Steps:** run
- **Expected:** the verdict is recorded; no samples
- **Why:** "sampling is a privacy decision: a deployment that must not move rows
  supplies no sampler and still gets verdicts"

### EXE-022 · A sampling failure does not become an error verdict
- **Area:** `execute/run.py::ControlRun._store_samples`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a sampler that raises, and a failing control
- **Steps:** run
- **Expected:** verdict `fail` recorded with no samples; a WARNING logged
- **Why:** "the verdict was established by the metric query; what is lost is the
  ability to show which rows, and that is a smaller loss than discarding the
  finding"

### EXE-023 · Records and samples are one transaction
- **Area:** `execute/run.py::ControlRun` (the unit of work)
- **Type:** contract
- **Priority:** P1
- **Precondition:** a unit of work whose `samples.put` raises
- **Steps:** run one failing control
- **Expected:** neither the record nor the samples are visible after the failure
- **Why:** "a control result recorded without its samples cannot happen"

### EXE-024 · Controls for another source are counted, not dropped
- **Area:** `execute/run.py::ControlRun.execute_all`, `_Elsewhere`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 40 live controls across four datasets, `datasets={"a"}`
- **Steps:** run
- **Expected:** outcomes only for `a`'s controls; the other 28 appear in
  `report.skipped` as `_Elsewhere` with `reason == "another_source"`;
  `is_a_defect is False`; `describe()` counts them as "not due"
- **Why:** "a run that reported 12 controls and said nothing about the other 28
  reads as an estate of 12"

### EXE-025 · `datasets=None` means everything
- **Area:** `execute/run.py::ControlRun.execute_all`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** 40 live controls, `datasets=None` and `datasets=set()`
- **Steps:** run each
- **Expected:** all 40 run under `None`; none run and all 40 are `_Elsewhere`
  under the empty set
- **Why:** `None` and an empty set mean opposite things and are one keystroke
  apart

### EXE-026 · An unreadable schedule is the one skip that is a defect
- **Area:** `execute/run.py::RunReport.unschedulable`, `_select`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `respect_schedule=True` and a control whose schedule is
  `"nightly-ish"`
- **Steps:** run and read `report.unschedulable` and `describe()`
- **Expected:** one entry; the sentence ends "1 with a schedule that cannot be
  read, which will never run until it is fixed"
- **Why:** "they will never run again and have no verdict to say so, which is the
  one skip reason that is a defect rather than the scheduler working"

### EXE-027 · By default a run means now
- **Area:** `execute/run.py::ControlRun._select`
- **Type:** functional
- **Priority:** P1
- **Precondition:** live controls all scheduled daily and all run an hour ago
- **Steps:** run with `respect_schedule=False`, then with `True`
- **Expected:** everything runs in the first case with nothing skipped; nothing
  runs in the second
- **Why:** "`prama control run` means 'run them now' — which is what somebody
  typing it at a terminal means. A timer sets it, and then only what is due runs"

### EXE-028 · A naive ledger timestamp does not break the scheduler
- **Area:** `execute/run.py::_parse_instant`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** ledger stamps of `2026-04-01T06:30:00Z`,
  `2026-04-01T06:30:00+00:00`, `2026-04-01T06:30:00` and
  `2026-04-01T06:30:00+02:00`
- **Steps:** parse each and compare against an aware `now`
- **Expected:** all four are aware; the naive one is assumed UTC; no `TypeError`
- **Why:** "a naive one compared against an aware `now` raises, and it would raise
  inside the scheduler — where the failure is a run that does nothing rather than
  an obvious error"

### EXE-029 · `describe` names what did not happen
- **Area:** `execute/run.py::RunReport.describe`
- **Type:** functional
- **Priority:** P2
- **Precondition:** four reports — no outcomes and no skips; no outcomes with
  skips; outcomes with failures; outcomes with an unschedulable skip
- **Steps:** describe each
- **Expected:** "no controls were live, so nothing ran"; "nothing was due, N not
  due"; a verdict breakdown plus "N could not be executed at all"; plus the
  unschedulable sentence
- **Why:** "a run summary that reports only verdicts reads as complete whatever
  proportion of the estate refused to execute — or was never asked"

## `execute/claim.py` and `execute/worker.py` — claims, leases, fencing

### EXE-030 · Exactly one worker claims a unit
- **Area:** `execute/claim.py::claim_unit`, `core/concurrency/leases.py`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** one queue, one unit, ten workers
- **Steps:** race all ten
- **Expected:** exactly one non-None claim; nine `None`
- **Why:** "the obvious failure is two workers running the same control at the
  same moment and writing two evidence records for one run"

### EXE-031 · Losing a race is not an error
- **Area:** `execute/claim.py::claim_unit`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a held resource
- **Steps:** claim it from a second worker
- **Expected:** `None`, no exception, nothing logged at warning or above
- **Why:** "another worker holding the work is the ordinary case in a fleet, not
  an error, and a worker that logged an exception every time it lost a race would
  drown its own useful output"

### EXE-032 · A short TTL is refused rather than silently unrenewable
- **Area:** `execute/claim.py::claim_unit`,
  `core/concurrency/leases.py::LeaseSettings.validate`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** `claim_unit(provider, unit, worker_id="w", ttl_seconds=t)` for
  `t` in `0.5`, `1.0`, `1.5`, `3.0`, `60.0`
- **Expected:** `ValueError` for 0.5 and 1.0 (the renew interval is floored at
  1.0 and must be shorter than the TTL); a log warning at 1.5 (renew × 2 > ttl);
  clean at 3.0 and 60.0
- **Why:** `renew_interval_seconds=max(1.0, ttl/3)` means the "renewed three
  times within the TTL" claim only holds above three seconds — and a bare
  `ValueError` rather than a `PramaError` escapes the error taxonomy

### EXE-033 · The fencing token is strictly increasing per resource
- **Area:** `execute/claim.py::Claim.fencing_token`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** a resource acquired, released and re-acquired five times
- **Steps:** record each token
- **Expected:** strictly increasing
- **Why:** it is "the number a writer compares"; equal or decreasing tokens make
  `FencedWriter` unable to tell a late holder from a current one

### EXE-034 · A stale write is refused
- **Area:** `execute/claim.py::FencedWriter.accept`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** a writer that has accepted token 7 for a resource
- **Steps:** `accept` a claim with token 6
- **Expected:** `StaleWriteError` code `CONCURRENCY.STALE_WRITE`, naming both
  tokens and the worker, remedy "Discard the result…"
- **Why:** the whole reason fencing tokens exist — "a long garbage collection, a
  stalled disk, a hypervisor pausing the VM for eleven seconds … nothing has
  failed, no error is raised, and the ledger now holds a record whose verdict is
  stale and whose timestamp says otherwise"

### EXE-035 · The same token may write twice
- **Area:** `execute/claim.py::FencedWriter.accept`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a writer that has accepted token 7
- **Steps:** `accept` the same claim again
- **Expected:** accepted (the comparison is `<`, not `<=`)
- **Why:** a retry by the current holder is legitimate, but so is a duplicated
  record; record which of the two this permits, because the class docstring's
  guarantee is "accepts a result only from the newest holder", not "only once"

### EXE-036 · Token zero is accepted
- **Area:** `execute/claim.py::FencedWriter.accept` / `.highest`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a fresh writer
- **Steps:** `highest("r")`, then accept a claim with token 0
- **Expected:** `0`, then accepted
- **Why:** the default is 0, so the first acquisition of a resource must produce
  a token of at least 0 — a provider starting at 0 makes the first write
  indistinguishable from no write

### EXE-037 · `would_accept` agrees with `accept`
- **Area:** `execute/claim.py::FencedWriter.would_accept`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a writer at token 7 and claims at 6, 7, 8
- **Steps:** call both
- **Expected:** `False/raise`, `True/accept`, `True/accept`
- **Why:** a predicate that disagrees with the action it predicts is worse than
  no predicate

### EXE-038 · `claim.check()` raises when the lease has been lost
- **Area:** `execute/claim.py::Claim.check`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** a claim whose lease has expired and been taken by another
  worker
- **Steps:** `claim.check()`
- **Expected:** `LeaseLostError`
- **Why:** "it cannot make a lost lease safe — the work is already done against
  data the claim no longer covers — but it turns a silent stale write into an
  exception at the moment the decision is made, which is where somebody can act
  on it"

### EXE-039 · A claim with no holder checks clean
- **Area:** `execute/claim.py::Claim.check`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `Claim(unit, "w", 1, holder=None)`
- **Steps:** `check()`
- **Expected:** returns `None`
- **Why:** a test double constructs claims without a holder; a guard that raised
  would make the fencing path untestable without a lease provider

### EXE-040 · The claim is checked before anything is written
- **Area:** `execute/worker.py::Worker._run`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** a runner that completes, then a lease lost before recording
- **Steps:** take the unit
- **Expected:** `status == "lost"`, no records written, an ERROR log saying the
  result is discarded
- **Why:** "recording first and checking after would put a stale verdict on the
  ledger and then discover it"

### EXE-041 · A lost claim requeues; a failed one does not
- **Area:** `execute/worker.py::WorkOutcome.should_requeue`
- **Type:** contract
- **Priority:** P1
- **Precondition:** outcomes of each of the five statuses
- **Steps:** read `should_requeue`
- **Expected:** `True` for `lost` and `stranded`; `False` for `done`, `skipped`
  and `failed`
- **Why:** "a lost claim requeues: the work was not recorded, so somebody must do
  it. A failure does not: it produced an error verdict, which is a finding, and
  rerunning it immediately would produce the same one"

### EXE-042 · A ledger failure strands the unit rather than losing it
- **Area:** `execute/worker.py::Worker.take_one`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a recorder that raises
- **Steps:** `take_one()`, then inspect the queue, the claim map and the lease
- **Expected:** `status == "stranded"`; the unit is back in `_pending`; the
  resource is no longer claimed; the lease is released
- **Why:** finding X4. "The unit had already left `_pending` and was never
  returned, `queue.release` never ran so it stayed claimed, and `release_claim`
  never ran so the lease holder renewed the lease indefinitely. The unit was
  invisible to every worker in the fleet, nobody could claim its resource again,
  and the report did not mention it: not lost, not failed, absent"

### EXE-043 · `drain` does not spin on a permanently failing recorder
- **Area:** `execute/worker.py::Worker.drain` / `.take_one`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** one unit and a recorder that always raises
- **Steps:** `await worker.drain()` with the default `limit=0`
- **Expected:** the call terminates
- **Why:** `take_one` returns a `stranded` outcome (not `None`) and requeues the
  unit, so `drain`'s `while limit <= 0` loop re-takes the same unit for ever. A
  transiently unreachable ledger is the ordinary case X4 was written about; a
  permanently unreachable one turns the fix into a hot loop

### EXE-044 · `drain` honours a positive limit
- **Area:** `execute/worker.py::Worker.drain`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** ten queued units
- **Steps:** `drain(limit=3)`, then `drain(limit=0)`
- **Expected:** three outcomes, then seven
- **Why:** the limit is the only backstop against EXE-043 and against a worker
  monopolising a queue a fleet is sharing

### EXE-045 · A worker only takes work in its own zone
- **Area:** `execute/worker.py::Worker.take_one`, `WorkQueue.pending`
- **Type:** functional
- **Priority:** P1
- **Precondition:** units in zones `""`, `"eu"` and `"us"`; workers in `""`,
  `"eu"`
- **Steps:** drain each
- **Expected:** the zoneless worker takes everything; the `eu` worker takes only
  `eu` units
- **Why:** a zone is a data-residency boundary; a worker reaching into another
  zone's work is a source read from the wrong jurisdiction

### EXE-046 · Releasing a superseded claim does not evict the current holder
- **Area:** `execute/claim.py::WorkQueue.release`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** a resource claimed at token 7, then re-claimed at token 8
- **Steps:** release the token-7 claim
- **Expected:** the token-8 claim remains in `_claimed`
- **Why:** the token comparison in `release` is what stops a stalled worker's
  late cleanup unclaiming the resource out from under whoever took it over

### EXE-047 · Requeuing is the caller's decision
- **Area:** `execute/claim.py::WorkQueue.release`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a claimed unit
- **Steps:** release with `requeue=False` and with `True`
- **Expected:** the unit is absent from `pending()` in the first case and present
  in the second
- **Why:** "a queue that requeued on every release would rerun everything; one
  that never did would lose whatever a crashing worker was holding"

### EXE-048 · A requeued unit is not duplicated
- **Area:** `execute/claim.py::WorkQueue.take` / `.release`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** one unit, taken and requeued three times
- **Steps:** read `len(queue)` after each cycle
- **Expected:** `1` each time
- **Why:** `take` removes with `if unit in self._pending`, which is an equality
  test on a frozen dataclass — two structurally identical units are the same
  entry, so offering the same unit twice and requeuing once loses one

### EXE-049 · `_as_triples` accepts both runner shapes
- **Area:** `execute/worker.py::_as_triples`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a runner returning 2-tuples, one returning 3-tuples, and one
  returning a 4-tuple
- **Steps:** normalise each
- **Expected:** the first two work; record what the 4-tuple does (the `len == 3`
  branch is not taken, so it is read as a 2-tuple and the extra elements are
  dropped silently)
- **Why:** "a worker that branched on the shape of what it was handed would
  encode every runner's quirks into the loop that is supposed to be independent
  of them" — but silently discarding a snapshot from a 4-element entry is a quirk
  of its own

### EXE-050 · A stranded unit is invisible in the fleet report
- **Area:** `execute/worker.py::FleetReport`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a fleet where one unit strands
- **Steps:** `run_fleet(...)` and read `render()` and `to_dict()`
- **Expected:** record whether the stranded unit appears
- **Why:** `FleetReport` exposes `done`, `lost` and `failed`, and `render` names
  the last two. `stranded` is in neither, so a ledger failure produces a report
  reading "0 units completed, 0 records written, 1 still queued" with no mention
  of why — which is the same invisibility X4 was fixed to remove, one layer out

### EXE-051 · `run_fleet` reports what is left
- **Area:** `execute/worker.py::run_fleet`
- **Type:** functional
- **Priority:** P2
- **Precondition:** twenty units, four workers, and a lease provider that holds
  two resources against everyone
- **Steps:** run the fleet
- **Expected:** eighteen outcomes and `remaining == 2`
- **Why:** a fleet report that did not say what it could not reach reads as a
  completed sweep

### EXE-052 · Two workers racing one queue produce one outcome per unit
- **Area:** `execute/worker.py::run_fleet`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** 100 units, eight workers
- **Steps:** run the fleet and count outcomes per resource
- **Expected:** exactly one `done` per unit; no resource appears twice
- **Why:** "the point of a fleet is that two workers racing for the same unit is
  the normal case and exactly one of them wins it"

### EXE-053 · A worker holds nothing between units
- **Area:** `execute/worker.py::Worker`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a worker that has drained ten units
- **Steps:** inspect its attributes
- **Expected:** no per-unit state; the only mutable member is the shared
  `FencedWriter`
- **Why:** "adding one is a deployment and losing one is a lease expiring. There
  is no worker identity that matters beyond the life of a claim, no state to
  migrate, and nothing to drain before a restart"

### EXE-054 · Two workers sharing a `FencedWriter` see each other's tokens
- **Area:** `execute/worker.py::Worker.__init__`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** two workers constructed with `writer=None`, and two sharing
  one writer
- **Steps:** have the first worker write at token 8, then the second attempt
  token 7
- **Expected:** with a shared writer, refused; with separate writers, accepted
- **Why:** `FencedWriter() if writer is None else writer` means the default is
  *per worker*, and a per-worker fence enforces nothing across a fleet — which
  is the only place the failure it prevents can happen

## `core/concurrency/bounded_queue.py`

The one queue the architecture guard permits, and the one every bounded producer
in the data plane is required to use.

### EXE-055 · An unbounded queue cannot be built
- **Area:** `core/concurrency/bounded_queue.py::BoundedQueue.__init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** construct with `max_bytes` of `0` and `-1`
- **Expected:** `ValueError` "an unbounded queue is not permitted"
- **Why:** "a queue of 100,000 'records' is 10 MB of telemetry or 40 GB of wide
  rows depending on the day, and the day it becomes the latter is the day the
  process dies with a bound configured and honoured"

### EXE-056 · The budget is bytes, with items as a secondary guard
- **Area:** `core/concurrency/bounded_queue.py::_would_fit`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `BoundedQueue(max_bytes=10_000, max_items=3)`
- **Steps:** put four small items; then fill to just under 10,000 bytes with two
  items and offer a third
- **Expected:** the fourth item blocks on the item guard; the third blocks on the
  byte guard
- **Why:** either bound alone is the wrong bound; the item count is what stops a
  flood of tiny items, and `ITEM_OVERHEAD_BYTES` is what stops them appearing free

### EXE-057 · An oversized item is accepted onto an empty queue
- **Area:** `core/concurrency/bounded_queue.py::put`, `_would_fit`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `BoundedQueue(max_bytes=100)` and a 10 KB item
- **Steps:** put it on an empty queue; then put a second one
- **Expected:** the first is accepted; the second blocks and then raises
  `BackPressureError`
- **Why:** "refusing it would strand the pipeline on one oversized record, which
  is a worse failure than a temporary overshoot that is visible in the stats"

### EXE-058 · An oversized item is still refused at the item ceiling
- **Area:** `core/concurrency/bounded_queue.py::_would_fit`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `BoundedQueue(max_bytes=100, max_items=1)` holding one item
- **Steps:** `try_put` an oversized item
- **Expected:** `False`
- **Why:** the empty-queue escape hatch applies to bytes and not to items; both
  halves of `_would_fit` need pinning because they are one boolean expression

### EXE-059 · Back-pressure is a typed refusal with a remedy
- **Area:** `core/concurrency/bounded_queue.py::put`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a full queue with `offer_timeout=0.05`
- **Steps:** `put(item)`
- **Expected:** `BackPressureError` after ~50 ms, message naming the byte and
  item counts, context carrying all four numbers, remedy noting that "widening
  the queue postpones the same problem with more memory held"; `stats().rejected`
  incremented
- **Why:** the error "propagates back to the scheduler as reduced admission
  rather than as an out-of-memory kill", and a remedy that only said "make it
  bigger" would be advice to defer the problem

### EXE-060 · `try_put` wakes a consumer
- **Area:** `core/concurrency/bounded_queue.py::try_put`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a consumer parked in `get()` with no timeout
- **Steps:** `await queue.try_put(item)`
- **Expected:** the consumer returns the item promptly
- **Why:** finding X6. "`try_put` enqueued and notified nobody, so a consumer in
  `get()` or `drain()` waited indefinitely while the item sat in the deque …
  `put()` two methods above notifies on exactly the same line; this one returned
  `True` and told nobody"

### EXE-061 · `resize` wakes blocked producers
- **Area:** `core/concurrency/bounded_queue.py::resize`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a full queue with two producers parked in `put` on a 30-second
  timeout
- **Steps:** `await queue.resize(max_bytes=<much larger>)`
- **Expected:** both producers complete promptly
- **Why:** finding X6's other half. "Producers already blocked sat out their full
  `offer_timeout` and took a `BackPressureError` against a queue with room —
  against a method whose reason to exist is 'an operator can widen a queue under
  load without a restart'"

### EXE-062 · Shrinking never discards queued items
- **Area:** `core/concurrency/bounded_queue.py::resize`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a queue holding 10 KB
- **Steps:** `resize(max_bytes=1000)`; read `len`, `byte_size` and
  `stats().utilisation`
- **Expected:** every item still present; `byte_size == 10_000`;
  `utilisation == 1.0` (clamped)
- **Why:** discarding on shrink would make a capacity change a data-loss event;
  and the clamp is why an over-full queue reports 100% rather than 1000%

### EXE-063 · `resize` refuses a non-positive byte budget
- **Area:** `core/concurrency/bounded_queue.py::resize`
- **Type:** negative
- **Priority:** P2
- **Precondition:** any queue
- **Steps:** `resize(max_bytes=0)`; then `resize(max_items=0)`
- **Expected:** `ValueError` for the first; the second is accepted and means "no
  item ceiling"
- **Why:** zero means two different things for the two parameters, and only one
  of them is a mistake

### EXE-064 · `close` wakes every waiter
- **Area:** `core/concurrency/bounded_queue.py::close`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** one producer parked in `put` on a full queue and one consumer
  parked in `get` on an empty one
- **Steps:** `await queue.close()`
- **Expected:** both return promptly; the producer gets `BackPressureError`
  "queue is closed", the consumer gets `BackPressureError` "closed and drained"
- **Why:** a close that left a waiter parked is a shutdown that never completes

### EXE-065 · A closed queue drains before it refuses
- **Area:** `core/concurrency/bounded_queue.py::get` / `.drain`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a queue holding three items, then closed
- **Steps:** `get()` four times; separately, `drain()` twice
- **Expected:** three items then `BackPressureError`; then the three items and
  then `[]`
- **Why:** closing is "closed for production", not "discard what is queued"; and
  the asymmetry between `get` raising and `drain` returning empty is a contract a
  consumer has to know

### EXE-066 · `drain` has no timeout
- **Area:** `core/concurrency/bounded_queue.py::drain`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an empty, open queue
- **Steps:** `await queue.drain()` with no producer
- **Expected:** it waits indefinitely
- **Why:** `get` takes a `timeout` and `drain` does not; a batch consumer with no
  way to time out cannot participate in a supervised shutdown unless something
  closes the queue for it

### EXE-067 · `drain` respects `max_items`
- **Area:** `core/concurrency/bounded_queue.py::drain`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a queue holding ten items
- **Steps:** `drain(max_items=3)`, then `drain(max_items=0)`
- **Expected:** three, then seven; `byte_size` drops by exactly the drained
  items' sizes each time
- **Why:** "a metric writer or an evidence appender wants a page, not a record";
  the byte accounting must follow the partial drain or the queue leaks capacity

### EXE-068 · `default_sizer` charges the overhead and walks one level
- **Area:** `core/concurrency/bounded_queue.py::default_sizer`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** size `b""`, `"x"*1000`, `{"a": "x"*1000}`, `[1,2,3]`,
  a deeply nested dict, and an object whose `__sizeof__` raises
- **Expected:** every result at least `ITEM_OVERHEAD_BYTES`; the dict's size
  reflects its value; the nested dict is *not* walked past one level; the raising
  object returns exactly the overhead
- **Why:** "exactness is not the goal: the budget exists to prevent an
  order-of-magnitude surprise, and an estimate that costs a deep traversal per
  item would cost more than the leak it prevents" — the nested case is where the
  estimate is knowingly wrong

### EXE-069 · Stats are a snapshot, not a live view
- **Area:** `core/concurrency/bounded_queue.py::stats`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a queue under load
- **Steps:** take a `stats()`, put more items, and re-read the first snapshot
- **Expected:** the first snapshot is unchanged; high-water marks never decrease
- **Why:** these are exported to Prometheus; a mutable object handed to a scraper
  produces a sample that changed while it was being serialised

## `execute/inflight.py`, `transport.py`, `kafka.py`

### EXE-070 · A quarantining pipeline with no dead letter is refused at construction
- **Area:** `execute/inflight.py::Pipeline.__init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** construct with `Action.QUARANTINE` and with `Action.BLOCK`, both
  with `dead_letter=None`; then with `Action.ALERT` and `Action.TAG`
- **Expected:** `PramaError` code `STREAM.NO_DEAD_LETTER` for the first two;
  the last two construct
- **Why:** "a quarantining pipeline with nowhere to put anything is a deleting
  pipeline, and discovering that at runtime means it has already deleted
  something"

### EXE-071 · A rejected message is written away before it is removed
- **Area:** `execute/inflight.py::Pipeline._judge`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a quarantining pipeline and a violating message
- **Steps:** judge it, recording the order of the dead-letter call and the
  outcome
- **Expected:** the dead letter receives the payload *before* the `quarantined`
  outcome is produced
- **Why:** "a pipeline that drops and *then* fails to record has destroyed data
  to enforce a rule about data quality, which is the worst trade in the product"

### EXE-072 · A full dead letter halts the pass rather than dropping
- **Area:** `execute/inflight.py::Pipeline.run`, `_to_dead_letter`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a dead letter returning `False` on the fourth message, and a
  stream of ten
- **Steps:** `run(messages)`
- **Expected:** three outcomes; `halted_because` set; `completed is False`;
  `describe()` begins "HALTED after 3 message(s)" and says the rest of the stream
  was not examined
- **Why:** "a full dead letter that silently falls back to dropping converts a
  storage problem into permanent loss, and the storage problem is the one
  somebody can fix"

### EXE-073 · `DeadLetterFull` is an exception, not a return value
- **Area:** `execute/inflight.py::DeadLetterFull`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** inspect the type and the raise site
- **Expected:** a `PramaError` subclass raised from `_to_dead_letter`
- **Why:** "a caller that could ignore this would ignore it under load, which is
  exactly when the dead letter fills up"

### EXE-074 · An unreadable message with no dead letter is silently dropped
- **Area:** `execute/inflight.py::Pipeline._judge` / `._to_dead_letter`,
  `Outcome.was_kept`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a `TAG` pipeline with `dead_letter=None` and a message whose
  payload is not a dict
- **Steps:** run
- **Expected:** record what happens — `_to_dead_letter` returns silently, the
  outcome is `unreadable`, and `was_kept` reports `True`
- **Why:** the module's first rule is "nothing is dropped without being kept",
  and the constructor guard covers only QUARANTINE and BLOCK. For an ALERT or TAG
  pipeline the unreadable path keeps nothing while `was_kept` says it did —
  "discarding it removes the only evidence of what they sent"

### EXE-075 · ALERT lets a violating message through
- **Area:** `execute/inflight.py::Pipeline._judge`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an alerting pipeline and a violating message
- **Steps:** judge
- **Expected:** disposition `passed`, `violated` naming the plan ids,
  `reaches_the_consumer is True`, payload unmodified
- **Why:** "anything else would make ALERT a different action from the one the
  estate approved"

### EXE-076 · TAG marks and delivers
- **Area:** `execute/inflight.py::Pipeline._judge`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a tagging pipeline with `tag_field="_prama"`, a message that
  violates two controls and has one unknown
- **Steps:** judge
- **Expected:** disposition `tagged`; the payload gains
  `{"_prama": {"violated": [...], "unknown": [...]}}`; the original dict is not
  mutated; `reaches_the_consumer is True`
- **Why:** "the consumer decides, and a control that silently removed them would
  be making a business decision on a data quality signal"

### EXE-077 · A message whose payload already has the tag field
- **Area:** `execute/inflight.py::Pipeline._judge`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a payload already containing `_prama`
- **Steps:** judge a violating message
- **Expected:** the existing value is overwritten
- **Why:** a producer that already uses the field, or a message replayed through
  two pipelines, silently loses the earlier annotation

### EXE-078 · Violated controls are named, not counted
- **Area:** `execute/inflight.py::Outcome.violated`
- **Type:** functional
- **Priority:** P1
- **Precondition:** forty assertions where one fires
- **Steps:** judge
- **Expected:** `violated` holds that assertion's `plan.plan_id`
- **Why:** "a message quarantined by one control out of forty needs to say which"

### EXE-079 · An assertion with no plan contributes an empty identity
- **Area:** `execute/inflight.py::Pipeline._judge`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an assertion object with no `plan` attribute
- **Steps:** judge a violating message
- **Expected:** `violated == ("",)` — record it
- **Why:** `getattr(getattr(assertion, "plan", None), "plan_id", "") or ""` never
  raises, which is right for a test double and means a real assertion with an
  unset plan id produces an unattributable quarantine

### EXE-080 · Latency is measured per message and reported as a percentile
- **Area:** `execute/inflight.py::Throughput.percentile` / `.p99_ms` /
  `.within`
- **Type:** performance
- **Priority:** P1
- **Precondition:** a pass over 100,000 messages with five assertions
- **Steps:** run and read `p99_ms` and `within(5.0)`
- **Expected:** a real p99; `within` returns a bool
- **Why:** "docs/15 §7 sets a budget of five milliseconds added at p99, and a
  pipeline that cannot say what it costs is one nobody will put in front of a
  payment system"

### EXE-081 · Nothing measured is None, not zero
- **Area:** `execute/inflight.py::Throughput.percentile` / `.within` /
  `.per_second`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an empty pass
- **Steps:** read `p99_ms`, `within(5.0)`, `per_second`, `describe()`
- **Expected:** `None`, `None`, `None`, "no messages passed through, so nothing
  was measured"
- **Why:** "a pass over no messages has not demonstrated a fast pipeline, and
  reporting 0 ms would say it had"

### EXE-082 · The percentile index is in range at the boundaries
- **Area:** `execute/inflight.py::Throughput.percentile`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** latency tuples of length 1, 2 and 100
- **Steps:** `percentile(0.0)`, `percentile(0.99)`, `percentile(1.0)`
- **Expected:** no `IndexError`; `percentile(1.0)` returns the maximum
- **Why:** `int(share * len)` is `len` at share 1.0, and the `min(len-1, …)` is
  the only thing preventing an off-the-end read

### EXE-083 · Commit happens after enforcement, never before
- **Area:** `execute/transport.py::StreamRunner.poll_once`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a `MemoryTransport` recording call order
- **Steps:** `poll_once()`
- **Expected:** poll, then the pipeline, then commit
- **Why:** "a consumer that commits an offset and then enforces has promised the
  broker it is finished with a message it has not finished with. Crash in between
  and the message is never redelivered and never dead-lettered: it is simply
  gone, and nothing anywhere records that it existed"

### EXE-084 · A halted batch commits through the last enforced message
- **Area:** `execute/transport.py::StreamRunner.poll_once`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a batch of ten where the pipeline halts after four
- **Steps:** `poll_once()` and read `committed` and `uncommitted`
- **Expected:** commits through message four only; six positions uncommitted;
  `describe()` says they will be redelivered
- **Why:** "committing the batch's last offset would skip every message after the
  halt; committing nothing replays the ones already dead-lettered. Committing
  through the last *enforced* message is the only choice that loses nothing"

### EXE-085 · Offsets are committed per partition
- **Area:** `execute/transport.py::_highest_per_partition`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a batch spanning `t[0]` offsets 1–5 and `t[1]` offsets 10–12
- **Steps:** `poll_once()` and read the committed positions
- **Expected:** two positions — `t[0]@5` and `t[1]@12` — sorted deterministically
- **Why:** "committing one partition's offset against another's is how a consumer
  group silently skips a partition's worth of data"

### EXE-086 · A poll failure commits nothing
- **Area:** `execute/transport.py::StreamRunner.poll_once`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a transport whose `poll` raises
- **Steps:** `poll_once()`
- **Expected:** `TransportError` code `STREAM.TRANSPORT`, remedy "Nothing was
  enforced and nothing was committed, so no message was lost"; no commit call
- **Why:** the safe direction on a polling failure is to do nothing at all

### EXE-087 · A commit failure says the batch will be reprocessed
- **Area:** `execute/transport.py::StreamRunner.poll_once`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a transport whose `commit` raises, after a successful
  enforcement pass
- **Steps:** `poll_once()`
- **Expected:** `TransportError` whose remedy says the messages will be
  redelivered and dead-lettered again, and whose context carries the enforced
  count
- **Why:** "duplicate evidence is a reconciliation problem; losing it is not one
  anybody can solve afterwards" — at-least-once, said out loud

### EXE-088 · An empty poll is not an error and commits nothing
- **Area:** `execute/transport.py::StreamRunner.poll_once`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a drained transport
- **Steps:** `poll_once()`
- **Expected:** `polled == 0`, `committed == ()`, `describe() == "nothing to
  read"`, and the pipeline was still run over an empty iterable
- **Why:** an idle consumer must not commit a stale position or report a pass
  over nothing

### EXE-089 · `run_until_idle` stops on a halt rather than spinning
- **Area:** `execute/transport.py::StreamRunner.run_until_idle`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** a full dead letter and a transport with a thousand messages
- **Steps:** `run_until_idle()`
- **Expected:** exactly one report, halted
- **Why:** "the next batch would halt on its first bad message, and the loop would
  spin against a broker for as long as the condition lasts"

### EXE-090 · `max_batches` bounds a transport that never empties
- **Area:** `execute/transport.py::StreamRunner.run_until_idle`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a transport that always returns a batch
- **Steps:** `run_until_idle(max_batches=5)`
- **Expected:** exactly five reports
- **Why:** "a backstop, not a tuning knob: a transport that keeps returning
  messages forever is a bug, and a loop with no bound turns it into a hang nobody
  can interrupt"

### EXE-091 · A batch size below one is refused
- **Area:** `execute/transport.py::StreamRunner.__init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** construct with 0 and -1
- **Expected:** `PramaError` code `STREAM.BATCH_SIZE`
- **Why:** a batch of zero polls nothing for ever, which looks like an idle
  broker

### EXE-092 · A `MemoryTransport` commit never moves an offset backwards
- **Area:** `execute/transport.py::MemoryTransport.commit`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a committed offset of 10
- **Steps:** commit offset 5 for the same partition
- **Expected:** `committed` stays at 10
- **Why:** "a commit that moved an offset backwards would replay messages already
  dealt with, which is not wrong but is a surprise nobody asked for" — and the
  reference transport is what a real one is checked against

### EXE-093 · Auto-commit is refused, not overridden
- **Area:** `execute/kafka.py::KafkaTransport.__init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `config={"enable.auto.commit": True}`, then `"true"`, then
  `"1"`, then `"false"`, then absent
- **Steps:** construct
- **Expected:** `PramaError` code `STREAM.AUTO_COMMIT` for the first three;
  construction for the last two, with the setting forced to `False`
- **Why:** "an operator who set it deliberately needs to know it cannot mean what
  they wanted" — auto-commit "commits on a timer, in a background thread, with no
  idea whether enforcement happened"

### EXE-094 · Kafka commits `offset + 1`
- **Area:** `execute/kafka.py::KafkaTransport.commit`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a live broker
- **Steps:** consume one message, commit, reconnect with the same group id, poll
- **Expected:** the message does not come back
- **Why:** "a committed offset in Kafka is the *next* one to read … This is the
  single most common Kafka bug and it is invisible in a test that only ever
  consumes once"

### EXE-095 · A broker error aborts the batch without enforcing
- **Area:** `execute/kafka.py::KafkaTransport.poll`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a record carrying an error
- **Steps:** `poll(100)`
- **Expected:** `TransportError` naming the broker error; the messages already
  accumulated in the batch are discarded and never committed
- **Why:** nothing was enforced, so nothing is lost — and a partially enforced
  batch with a committed prefix would be

### EXE-096 · An undeserialisable message is not dead-lettered as unreadable
- **Area:** `execute/kafka.py::KafkaTransport._message`,
  `execute/inflight.py::Pipeline._judge`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a Kafka message whose body is not JSON, and a pipeline with a
  dead letter
- **Steps:** poll and run
- **Expected:** record the disposition
- **Why:** the Kafka module says "it arrives with its raw bytes and a note, and
  the pipeline dead-letters it like any other unreadable message". `_message`
  wraps it as `{"_unreadable": True, "_raw": …}`, which *is* a dict — so
  `Pipeline._judge`'s `isinstance(payload, dict)` check passes, every assertion
  is evaluated against the note rather than the message, and it is delivered as
  `passed` unless one of them happens to fire

### EXE-097 · A JSON body that is not an object is wrapped
- **Area:** `execute/kafka.py::KafkaTransport._message`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** message bodies of `[1,2,3]`, `"text"`, `42`, `null`, and
  empty bytes
- **Steps:** poll
- **Expected:** the first four become `{"_raw": …}`; the empty body becomes `{}`
- **Why:** a bare array is a legal JSON document and a common shape; wrapping
  keeps the payload a dict without inventing field names

### EXE-098 · Headers and keys survive invalid UTF-8
- **Area:** `execute/kafka.py::_text`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a message with a key and a header value containing invalid
  UTF-8 bytes, and a `None` key
- **Steps:** poll
- **Expected:** replacement characters rather than a `UnicodeDecodeError`; the
  `None` key becomes `""`
- **Why:** a single undecodable key must not take down a whole poll; the message
  is the evidence of what the sender sent

### EXE-099 · `close` is idempotent
- **Area:** `execute/kafka.py::KafkaTransport.close`,
  `transport.py::MemoryTransport.close`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an open transport
- **Steps:** `close()` twice
- **Expected:** the underlying consumer is closed once; no exception
- **Why:** the ABC's docstring says "safe to call twice", and a
  double-close on a Kafka consumer raises

## `execute/stream.py` and `execute/watermark.py`

### EXE-100 · A message is judged by the same semantics as a batch row
- **Area:** `execute/stream.py::StreamAssertion.judge`
- **Type:** contract
- **Priority:** P1
- **Precondition:** one control, a hundred messages, and the same hundred rows in
  a table
- **Steps:** run the control in flight and in a nightly batch; compare violation
  counts
- **Expected:** identical
- **Why:** "a control that means one thing in a nightly batch cannot mean
  something else in flight" — the expression semantics are the reference
  interpreter's, imported rather than reimplemented

### EXE-101 · The second stage decides in flight too
- **Area:** `execute/stream.py::StreamAssertion.judge` / `.offer`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a two-stage `IS VALID` control and a message carrying a
  fabricated identifier with valid shape and a wrong check digit
- **Steps:** judge it
- **Expected:** `passed is False`
- **Why:** "omitting this is how the same control caught a fabricated identifier
  overnight and passed it in flight"; the docstring "imported rather than
  reimplemented" was there while the method reimplemented them and dropped the
  residual check

### EXE-102 · An unknown is counted and the policy decides
- **Area:** `execute/stream.py::StreamAssertion.judge` / `.offer`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a message whose field is null, under
  `TREAT UNKNOWN AS PASS` and `AS FAIL`
- **Steps:** judge and offer
- **Expected:** `judge` returns `unknown=True` with `passed` following the
  policy; `offer` increments `_unknowns` always and `_violations` only under
  FAIL; the two paths agree
- **Why:** "a source that starts sending a field as null shows up here before it
  shows up anywhere else" — and `judge` and `offer` are two implementations of
  one rule

### EXE-103 · A control with no predicate passes everything
- **Area:** `execute/stream.py::StreamAssertion.judge`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a plan whose `predicate is None`
- **Steps:** judge any message
- **Expected:** `passed is True`, `unknown is False`
- **Why:** an aggregate-only control has no row predicate; judging it per message
  as a violation would quarantine a whole stream

### EXE-104 · A count window closes at its size
- **Area:** `execute/stream.py::StreamAssertion._should_close`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `Window(kind=COUNT, size=100)`
- **Steps:** offer 99, 100 and 101 messages
- **Expected:** no verdict at 99; a verdict on the 100th; the 101st opens a new
  window with `_messages == 1`
- **Why:** "for a source whose rate varies so much that a time window is empty
  half the day and unmanageable the rest"; an off-by-one makes every window
  report one message short

### EXE-105 · A tumbling window never closes without a timestamp
- **Area:** `execute/stream.py::StreamAssertion.offer` / `._should_close`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `Window(kind=TUMBLING, duration=60s)`
- **Steps:** offer a million messages with `at=None`
- **Expected:** no verdict ever; the counters grow without bound
- **Why:** the tumbling branch returns `False` when `at is None`, so a caller
  that does not supply an event time gets a control that accumulates silently and
  reports nothing — which is indistinguishable from a stream with no violations

### EXE-106 · A window is cut by arrival, not by event time
- **Area:** `execute/stream.py::StreamAssertion.offer` / `._should_close`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a tumbling minute window, and messages whose `at` values
  arrive out of order — 12:00:10, 12:00:50, 12:00:20, 12:01:05
- **Steps:** offer each and record when the window closes and which messages it
  counted
- **Expected:** the window opens at the *first* message's `at` and closes when
  some message's `at` is a minute past it; a late message is counted into
  whichever window is open when it arrives, and a message earlier than
  `_opened_at` produces a negative delta that cannot close the window
- **Why:** there is no watermark, no allowed lateness and no reassignment by
  event time. "A count reconcilable with a batch run over the same period" is the
  stated property of a tumbling window, and out-of-order delivery breaks it —
  record the actual behaviour so the claim can be narrowed or the code changed

### EXE-107 · An empty window is indeterminate, not a pass
- **Area:** `execute/stream.py::StreamAssertion.close`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an assertion that has seen no messages
- **Steps:** `close()`
- **Expected:** `Verdict.INDETERMINATE`, `messages == 0`,
  `violation_rate == 0.0`
- **Why:** the same rule as the batch path: "a control that could not establish a
  pass" is not a quiet one, and a minute with no traffic is not a minute with no
  defects

### EXE-108 · Closing resets every counter
- **Area:** `execute/stream.py::StreamAssertion.close`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a closed window with violations and unknowns
- **Steps:** offer more messages and close again
- **Expected:** the second verdict counts only the second window's messages;
  `opened_at` is the second window's first timestamp
- **Why:** a counter that carried over would make every window's violation rate
  the cumulative one, and a stream would look worse every hour

### EXE-109 · `offer` allocates nothing per message
- **Area:** `execute/stream.py::StreamAssertion.offer`
- **Type:** performance
- **Priority:** P2
- **Precondition:** five assertions and a million messages
- **Steps:** measure per-message cost and allocation count
- **Expected:** no `MessageVerdict` allocated; the cost is the evaluation
- **Why:** "allocating a MessageVerdict per message per assertion cost twice as
  much as the evaluation it described — measured at 7.07 µs for five controls, of
  which 4.7 µs was bookkeeping. On a hot path the object that reports the work is
  not allowed to outweigh the work"

### EXE-110 · A window is judged by the plan's own threshold
- **Area:** `execute/stream.py::StreamAssertion.close`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a control failing at 0.1%, with 1,000 messages and 1 then 2
  violations
- **Steps:** close each window
- **Expected:** pass then fail — the same boundary the nightly run applies
- **Why:** "a control that fails at 0.1% in a nightly run fails at 0.1% in
  flight — which is the whole reason both go through the IR"

### EXE-111 · A window's duration and size are validated
- **Area:** `execute/stream.py::Window.__post_init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** construct tumbling windows of 0 and -1 seconds; count windows of
  size 0 and -1; and a count window with a zero duration
- **Expected:** `ValidationError` for the first four; the last constructs (the
  duration is not checked for a count window)
- **Why:** a zero-duration tumbling window closes on every message and a
  zero-size count window closes on none

### EXE-112 · A suite evaluates one deserialised message once
- **Area:** `execute/stream.py::StreamSuite.offer`
- **Type:** performance
- **Priority:** P1
- **Precondition:** forty assertions
- **Steps:** offer one message and count deserialisations and copies
- **Expected:** one object, seen by all forty
- **Why:** "the streaming equivalent of fusion … evaluating each control against
  its own copy would multiply the only cost that matters here"

### EXE-113 · `close_all` skips an assertion with no open messages
- **Area:** `execute/stream.py::StreamSuite.close_all`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** three assertions where one has seen nothing
- **Steps:** `close_all()`
- **Expected:** two verdicts; the third silently produces none
- **Why:** the alternative is an `INDETERMINATE` verdict per empty window per
  shutdown, and the choice between "say nothing" and "say we established nothing"
  is a reporting decision worth pinning — a control that stops receiving messages
  entirely reports nothing at all here

### EXE-114 · Lag is reported, never absorbed
- **Area:** `execute/stream.py::StreamSuite.lag`, `Lag.is_falling_behind`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a suite that has seen 1,000 of 20,000 produced, threshold
  10,000
- **Steps:** `lag(20_000)` and `render()`
- **Expected:** `messages_behind == 19_000`, `is_falling_behind is True`, and a
  sentence saying "Messages are not being dropped; the assertion is asking the
  caller to shed load or add capacity"
- **Why:** "a streaming quality check that drops messages under load is worse
  than none: it reports green because it stopped looking, exactly when the volume
  that broke it is the thing worth looking at"

### EXE-115 · Lag is never negative
- **Area:** `execute/stream.py::Lag`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a suite that has seen more than the reported production
- **Steps:** `lag(500)` after seeing 1,000
- **Expected:** `0`
- **Why:** a negative backlog on a dashboard is a number nobody can interpret

### EXE-116 · Coverage qualifies a verdict at the width it was established
- **Area:** `execute/watermark.py::Coverage.qualify` /
  `.supports_a_claim_about_the_whole_dataset` / `.sees_restatements`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** `qualify("passed")` for all three coverages; read both properties
- **Expected:** `"passed"` for FULL and `"passed over the rows examined"` for the
  other two; only FULL supports a whole-dataset claim; only FORWARD_ONLY fails
  `sees_restatements`
- **Why:** "'positions_eod passed' after a full scan means the whole table is
  sound. The same words after an incremental run mean *today's rows* are sound
  and nothing was said about the rest"

### EXE-117 · A dataset never examined reads everything, and says why
- **Area:** `execute/watermark.py::WatermarkPlanner.scope`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an unset watermark
- **Steps:** `scope(watermark, now=…)`
- **Expected:** `Coverage.FULL`, `reason == "nothing has been examined before"`,
  and `describe()` reading "the whole dataset — nothing has been examined before"
- **Why:** the first run has no lower bound to narrow to, and the evidence should
  explain why it was wide

### EXE-118 · A due full sweep reads everything and says when the last one was
- **Area:** `execute/watermark.py::WatermarkPlanner.scope` / `._sweep_is_due`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `full_sweep_every=7 days`; last sweeps of exactly 7 days ago,
  6 days ago, and never
- **Steps:** scope each
- **Expected:** FULL, INCREMENTAL, FULL — and the FULL reasons name the last
  sweep's date or "never run"
- **Why:** "the evidence should be able to explain why last Tuesday's run took an
  hour when the others took a second"; the comparison is `>=`, so exactly the
  period is due

### EXE-119 · A policy with no sweep and no change column is a stated gap
- **Area:** `execute/watermark.py::LatenessPolicy.covers_the_past` / `.gap`,
  `WatermarkPlanner.audit`
- **Type:** contract
- **Priority:** P1
- **Precondition:** `LatenessPolicy(full_sweep_every=None, change_column="")`
- **Steps:** read `gap` and `audit()`
- **Expected:** a sentence naming the lookback and saying a correction booked
  before it would never be seen, with a remedy
- **Why:** "reported rather than left to be discovered when a restatement from
  three months ago turns up in a regulatory return"

### EXE-120 · A change column widens the predicate with OR
- **Area:** `execute/watermark.py::WatermarkPlanner.scope`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a watermark on `booked` at 2026-04-10, lookback 3 days,
  `change_column="updated_at"`
- **Steps:** scope and read `predicate`
- **Expected:** `booked >= '2026-04-07' OR updated_at >= '2026-04-07'`
- **Why:** "an old row that moved is found by its change column rather than by
  its business date, which is the only way a restatement outside the lookback is
  visible without reading everything"

### EXE-121 · A zero lookback with no change column is FORWARD_ONLY
- **Area:** `execute/watermark.py::WatermarkPlanner.scope`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `LatenessPolicy(lookback=timedelta(0), full_sweep_every=None,
  change_column="")` and a set watermark
- **Steps:** scope and read `coverage`
- **Expected:** `FORWARD_ONLY`, whose `sees_restatements` is False
- **Why:** "a correction booked to last Tuesday sits below the high-water mark
  and is invisible for ever. This is not a corner case: in a bank, late
  corrections *are* the workload"

### EXE-122 · A negative lookback is refused
- **Area:** `execute/watermark.py::LatenessPolicy.__post_init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** construct with `lookback=timedelta(days=-1)`
- **Expected:** `ValidationError` "a lookback cannot be negative"
- **Why:** a negative lookback would shift the lower bound *forward* and skip
  rows that were never examined

### EXE-123 · A watermark never moves backwards
- **Area:** `execute/watermark.py::Watermark.advanced_to`, `_before`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a watermark at 2026-04-10
- **Steps:** advance to 2026-04-09, to 2026-04-10, to 2026-04-11, and to a value
  that cannot be compared with a date
- **Expected:** unchanged, advanced (equal is not "before"), advanced, unchanged
- **Why:** "a watermark that could move back would silently re-admit rows already
  judged, and the same failing row would be reported every night until somebody
  noticed the count was wrong rather than the data"; and "two values that cannot
  be ordered are not evidence that the mark should move back … at worst a row is
  examined twice"

### EXE-124 · `rows_seen` accumulates across advances
- **Area:** `execute/watermark.py::Watermark.advanced_to`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a watermark advanced three times with 100, 200 and 300 rows,
  including one refused backward advance
- **Steps:** read `rows_seen`
- **Expected:** the refused advance contributes nothing
- **Why:** `advanced_to` returns `self` unchanged on a refusal, so the rows from
  a rejected batch are not counted — which is right, and worth pinning because
  the counter otherwise looks like a simple running total

### EXE-125 · `_shift` applies the lookback only where it means something
- **Area:** `execute/watermark.py::_shift`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** watermark values of a `date`, a `datetime`, an ISO string,
  a non-ISO string, an `int` sequence number, and `None`
- **Steps:** shift each by −3 days
- **Expected:** shifted, shifted, shifted as an ISO string, returned unchanged,
  returned unchanged, returned unchanged
- **Why:** "a numeric watermark — a sequence, an offset — has no notion of days,
  so the lookback cannot be applied and the mark itself is the bound" — which
  silently makes an integer-watermarked dataset FORWARD_ONLY in effect while the
  coverage still reads INCREMENTAL

### EXE-126 · `_literal` quotes a watermark bound safely
- **Area:** `execute/watermark.py::_literal`
- **Type:** security
- **Priority:** P2
- **Precondition:** values `None`, `7`, `7.5`, `True`, a date, and the string
  `it's`
- **Steps:** render each
- **Expected:** `NULL`, `7`, `7.5`, `'True'` (bool is excluded from the numeric
  branch), `'2026-04-07'`, `'it''s'`
- **Why:** a watermark value is a column value from a customer's table and reaches
  a predicate string

### EXE-127 · `_period` renders every magnitude
- **Area:** `execute/watermark.py::_period`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** render 1 day, 3 days, 1 hour, 5 hours, 30 minutes, 0
- **Expected:** `day`, `3 days`, `hour`, `5 hours`, `30 minutes`, `0 minutes`
- **Why:** this appears inside the gap sentence an auditor reads; "1 days" is the
  kind of wrongness that makes the whole finding look generated

## `execute/actions.py` and `execute/preview.py`

### EXE-128 · Only a failure acts
- **Area:** `execute/actions.py::Enforcer.enforce`
- **Type:** contract
- **Priority:** P1
- **Precondition:** verdicts PASS, FAIL, INDETERMINATE and ERROR
- **Steps:** enforce each with `Action.BLOCK`
- **Expected:** a `Consequence` only for FAIL; `None` otherwise
- **Why:** "an *indeterminate* verdict deliberately does not: it means the
  control demonstrated nothing, and blocking a pipeline because a scope was empty
  would be acting on the absence of evidence rather than on evidence"

### EXE-129 · A quarantine sets rows aside and records a reference, not the rows
- **Area:** `execute/actions.py::Enforcer.enforce`, `Consequence.quarantine_ref`
- **Type:** security
- **Priority:** P1
- **Precondition:** a failing control with 900 offending rows
- **Steps:** enforce with `Action.QUARANTINE`
- **Expected:** `quarantined_rows == 900`; a reference string; the rows are in
  the `Quarantine` and **not** in the `Consequence`
- **Why:** "copying them here would double the exposure of exactly the data
  somebody decided to isolate"

### EXE-130 · A quarantine with no rows quarantines nothing
- **Area:** `execute/actions.py::Enforcer.enforce`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a failing control, `Action.QUARANTINE`, `rows=None` and
  `rows=[]`
- **Steps:** enforce
- **Expected:** a `Consequence` whose action is quarantine, `quarantine_ref ==
  ""` and `quarantined_rows == 0`
- **Why:** the consequence still says "quarantine" while nothing was set aside —
  a caller reading `action` alone would believe the rows were isolated, and this
  is the shape a pipeline takes when the sampler is absent

### EXE-131 · A blocking consequence is in force until it is dealt with
- **Area:** `execute/actions.py::Consequence.is_blocking`, `Enforcer.blocking` /
  `._in_force` / `.is_blocked`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a BLOCK consequence, then overridden, resolved, and released
- **Steps:** read `blocking()` and `is_blocked(dataset)` after each
- **Expected:** blocking; not blocking; not blocking; not blocking
- **Why:** "the list somebody looks at when a batch has not run"

### EXE-132 · An expired override restores the block
- **Area:** `execute/actions.py::Enforcer._in_force`,
  `Override.is_effective_at`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a BLOCK overridden `until` T, with a clock at T−1s, T and
  T+1s
- **Steps:** read `blocking()` at each
- **Expected:** not blocking, blocking, blocking (`moment < until` is strict)
- **Why:** "an override that has run out restores the block rather than lapsing
  into permission. An override with no expiry is a control quietly switched off,
  and this is where that shows"

### EXE-133 · An override with no expiry never restores the block
- **Area:** `execute/actions.py::Override.is_effective_at`,
  `Consequence.render`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a BLOCK overridden with `until=None`
- **Steps:** read `blocking()` a year later, and `render()`
- **Expected:** not blocking; the rendered line says "overridden by <name> **with
  no expiry**"
- **Why:** "an override with no expiry is a control that has been quietly
  switched off, and six months later nobody remembers it was ever on" — the
  wording is the only thing making that visible

### EXE-134 · A non-blocking action is never in force
- **Area:** `execute/actions.py::Enforcer._in_force`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** open TAG and QUARANTINE consequences
- **Steps:** read `blocking()`
- **Expected:** empty
- **Why:** only BLOCK stops a pipeline; a quarantine listed as blocking would
  send an operator to release rows that were never holding anything up

### EXE-135 · A second failure on the same plan overwrites the first
- **Area:** `execute/actions.py::Enforcer._open`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a plan blocked, then overridden, then failing again
- **Steps:** enforce the second failure and read `blocking()` and `report()`
- **Expected:** record what happens — `self._open[plan_id] = consequence`
  replaces the overridden entry with a fresh OPEN one
- **Why:** the override is silently discarded, so "proceed anyway" lasts only
  until the next run of the same control. Whether an override should survive a
  re-fail is a decision, and at present it is made by a dict assignment

### EXE-136 · Overriding, releasing or resolving an unknown plan returns None
- **Area:** `execute/actions.py::Enforcer.override` / `.release` / `.resolve`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an enforcer with nothing open
- **Steps:** call all three with an unknown plan id; then `release` on a plan
  whose action is BLOCK rather than QUARANTINE
- **Expected:** `None` in all four
- **Why:** a silent `None` is right for an idempotent retry and wrong for a
  console button that reports success; record which callers check the return

### EXE-137 · Releasing an unknown reference still records a release
- **Area:** `execute/actions.py::Quarantine.release` / `.was_released`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a fresh quarantine
- **Steps:** `release("nothing")` then `was_released("nothing")`
- **Expected:** `[]` and `True`
- **Why:** "released rather than deleted: the rows rejoin the flow and the fact
  that they were once quarantined stays visible" — a release recorded for a batch
  that never existed makes that record untrustworthy

### EXE-138 · Quarantined rows are copied, not referenced
- **Area:** `execute/actions.py::Quarantine.put` / `.get`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a list of dicts
- **Steps:** put them, mutate the originals, then `get`
- **Expected:** the stored rows are unchanged; `get` returns a new list each time
- **Why:** the quarantine is the only surviving copy of the offending data; a
  caller mutating its own list afterwards must not change what is held

### EXE-139 · A trial is not an evidence record
- **Area:** `execute/preview.py::Trial`, `Preview`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** confirm `Preview` holds no unit of work; confirm `Trial` carries no
  `plan_id`, snapshot or chain position; attempt to pass a `Trial` to
  `evidence.append`
- **Expected:** refused by type
- **Why:** "a preview runs against a control that has not been approved, often
  against a bounded sample, and frequently while the author is still editing it;
  evidence that a regulator may later read must be the record of a control the
  estate agreed to, run in full. Making the two convertible would be one refactor
  away from a ledger nobody can vouch for"

### EXE-140 · An empty period is `no_data`, not a pass
- **Area:** `execute/preview.py::Preview._trial`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a period with no rows in scope
- **Steps:** run one trial
- **Expected:** `verdict == "no_data"`, `has_data is False`, detail "no rows were
  in scope, so the control tested nothing"
- **Why:** "ten empty days quietly cut the expected alert rate by a third — and
  the ten empty days are usually a retention window, meaning the backtest is most
  wrong exactly where the author trusts it most"

### EXE-141 · Empty periods are excluded from the rate and counted
- **Area:** `execute/preview.py::Backtest.evaluated` / `.empty` / `.alert_rate` /
  `.describe`
- **Type:** contract
- **Priority:** P1
- **Precondition:** 30 periods, 10 of them empty, 4 of the other 20 alerting
- **Steps:** backtest
- **Expected:** `alert_rate == 0.2` (4 of 20, not 4 of 30); `describe()` names the
  10 as "excluded from the rate rather than counted as quiet"
- **Why:** the whole reason the distinction exists

### EXE-142 · A backtest that could read nothing reports None, not zero
- **Area:** `execute/preview.py::Backtest.alert_rate` / `.per_period`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 30 periods, all errored
- **Steps:** backtest
- **Expected:** `alert_rate is None`, `per_period(30) is None`, and `describe()`
  reading "none of the 30 period(s) could be evaluated"
- **Why:** "that is the number that gets a control approved on the strength of an
  outage"

### EXE-143 · An indeterminate period counts as an alert
- **Area:** `execute/preview.py::Trial.would_alert`
- **Type:** contract
- **Priority:** P1
- **Precondition:** trials with verdicts `pass`, `fail`, `indeterminate`,
  `error`, `no_data`
- **Steps:** read `would_alert`
- **Expected:** `False, True, True, False, False`
- **Why:** "a control that could not establish a pass is one somebody has to look
  at, and a backtest that treated it as quiet would understate the workload the
  author is signing up for"

### EXE-144 · Fewer than five evaluated periods is not a rate worth quoting
- **Area:** `execute/preview.py::Backtest.is_trustworthy` / `.describe`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** backtests with 4 and 5 evaluated periods
- **Steps:** read `is_trustworthy` and `describe()`
- **Expected:** `False` then `True`; the first's sentence ends "4 period(s) is
  too few to quote a rate from"
- **Why:** "quoting '20% of days' from one alert in five is how a control gets
  approved on a coin flip"

### EXE-145 · A bounded scan makes the counts a floor and says so
- **Area:** `execute/preview.py::Preview._trial`, `Trial.was_bounded` /
  `.describe`, `Backtest.is_a_lower_bound`
- **Type:** contract
- **Priority:** P1
- **Precondition:** `Preview(max_rows=10_000)` and a period scanning exactly
  10,000 rows
- **Steps:** run
- **Expected:** `was_bounded is True`; the detail says the scan stopped at the
  cap and the counts are a floor; `describe()` renders "at least N of M rows";
  the backtest's `is_a_lower_bound` is True and `describe()` says "at least"
- **Why:** "a row cap that silently truncated the scan produces a violation count
  that is a floor, and a floor presented as a count is the single most dangerous
  number this system can emit"

### EXE-146 · A bounded scan does not downgrade the verdict
- **Area:** `execute/preview.py::Preview._trial`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a bounded scan returning zero violations
- **Steps:** run
- **Expected:** `verdict == "pass"` with a bounding detail — record it
- **Why:** the incomplete-screen path downgrades a pass to `indeterminate` for
  exactly the same reason (the count is a lower bound), and the bounded-scan path
  does not. Two floors, two different verdicts

### EXE-147 · The scan limit is applied by the compiler, not as a query LIMIT
- **Area:** `execute/preview.py::Preview._trial`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `max_rows=1000` and a large table
- **Steps:** read the emitted `query`
- **Expected:** the limit wraps the source relation, not the aggregate
- **Why:** "the metric query aggregates, so a LIMIT on the query would bound the
  one row of output and leave the scan exactly as expensive"

### EXE-148 · A period restriction is built as an AST node
- **Area:** `execute/preview.py::_restricted`
- **Type:** security
- **Priority:** P1
- **Precondition:** a period string containing `'` and `; DROP TABLE t --`
- **Steps:** build the restricted control and compile it
- **Expected:** the period reaches the compiler as a `Literal` and is escaped by
  the dialect; the trial finds nothing rather than doing something
- **Why:** "nothing here concatenates a caller's text into a statement"

### EXE-149 · A period column must be a plain identifier
- **Area:** `execute/preview.py::plain_identifier`, `IDENTIFIER`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** validate `as_of_date`, `_x9`, `9x`, `a.b`, `"a"`, `a b`,
  `as_of_date; DROP TABLE positions --`, `""`, `  a  `
- **Expected:** accepted, accepted, then `ValidationError` for the next six
  except the last, which is trimmed and accepted
- **Why:** "the dialect quotes every identifier, so `as_of_date; DROP TABLE
  positions --` compiles to a column of that name and finds nothing. This is the
  second line, and its job is the error message"

### EXE-150 · An existing WHERE is combined, not replaced
- **Area:** `execute/preview.py::_restricted`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a control that already has a `WHERE`
- **Steps:** restrict it to a period
- **Expected:** `AND` of the original and the period predicate; the original
  control object is not mutated
- **Why:** dropping the author's own filter would backtest a different control
  from the one they wrote

### EXE-151 · `over` is a generator and yields as it goes
- **Area:** `execute/preview.py::Preview.over`
- **Type:** performance
- **Priority:** P2
- **Precondition:** 30 periods against a slow executor
- **Steps:** iterate and record when each trial arrives
- **Expected:** the first arrives after one round trip, not after thirty
- **Why:** "a thirty-day backtest is thirty round trips to a warehouse and a
  screen that shows nothing until the last one lands is a screen people stop
  using"

### EXE-152 · A parse failure yields one errored trial per period
- **Area:** `execute/preview.py::Preview.over` / `.once`
- **Type:** negative
- **Priority:** P2
- **Precondition:** unparseable PQL and 30 periods
- **Steps:** `backtest(...)`
- **Expected:** 30 trials, each with the same error and `ran is False`; no
  exception; `evaluated` is empty and `alert_rate is None`
- **Why:** the backtest shape is preserved so a screen renders 30 rows of "could
  not be evaluated" rather than a stack trace

### EXE-153 · `business_dates` excludes weekends and ends inclusively
- **Area:** `execute/preview.py::business_dates`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an `end` that is a Sunday, and one that is a Wednesday
- **Steps:** `business_dates(end, days=5)` for each, and with
  `weekdays_only=False`; then `days=0`
- **Expected:** five weekdays ending on the Friday before for the Sunday case;
  five consecutive days including the weekend when the flag is off; `[]` for
  `days=0`; results are in ascending date order
- **Why:** "a backtest that includes weekends on a feed that does not deliver at
  weekends reports two empty periods in every seven … they still cost two queries
  each week and clutter the answer"

## `schedule/spec.py`, `trigger.py`, `due.py`

### SCH-001 · Every documented schedule form parses
- **Area:** `schedule/spec.py::parse`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the banking calendars installed
- **Steps:** parse `every 15 minutes`, `every 4 hours`, `daily`, `06:30`,
  `06:30 TARGET2`, `on arrival`, `manual`
- **Expected:** an `IntervalTrigger(15)`, `IntervalTrigger(240)`,
  `IntervalTrigger(1440)`, a `CalendarTrigger` on `ALWAYS_OPEN`, a
  `CalendarTrigger` on TARGET2, an `ArrivalTrigger`, a `ManualTrigger`
- **Why:** these seven are the module docstring's list *and* the remedy's list.
  Finding H7 was exactly this: the remedy told the reader to use
  `'06:30 TARGET2'` and `parse()` refused it, because nothing installed the
  calendar — "the test and the remedy asserted opposite things about the same
  value"

### SCH-002 · Every alias parses to the same trigger
- **Area:** `schedule/spec.py::parse`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `manual`, `never`, `on demand`; `on arrival`, `arrival`,
  `on-arrival`; `daily`, `every day`, `every 1 day`, `every 1 d`; `hourly`,
  `every hour`, `every 60 minutes`
- **Expected:** each group yields equal triggers
- **Why:** a generated control renders one spelling and a person types another;
  a spelling that parses to a *different* cadence is worse than one that fails

### SCH-003 · Parsing is case- and whitespace-insensitive
- **Area:** `schedule/spec.py::parse`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `  DAILY  `, `Every 15 Minutes`, `06:30 target2`, `""`, `None`
- **Expected:** all succeed; the empty string and `None` yield `DEFAULT`
  (`daily`)
- **Why:** the calendar registry lowercases its keys, so `TARGET2` and `target2`
  must both resolve; and an unset schedule must not be a refusal

### SCH-004 · An unstated schedule is daily, not hourly
- **Area:** `schedule/spec.py::DEFAULT`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** `parse("")` and read the interval
- **Expected:** 1,440 minutes
- **Why:** "an unstated cadence is an unconsidered one, and the cost of guessing
  too often is a bill and a load the owner never agreed to"

### SCH-005 · A cadence below the floor is refused, not clamped
- **Area:** `schedule/spec.py::MINIMUM_MINUTES`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `every 4 minutes`, `every 5 minutes`, `every 0 minutes`
- **Expected:** `ValidationError` naming the 5-minute floor for the first and
  third; success for the second
- **Why:** "silently running something five times less often than it says is
  worse than saying no", and a zero-minute interval would fire continuously

### SCH-006 · An impossible time of day is refused
- **Area:** `schedule/spec.py::parse`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `24:00`, `23:60`, `00:00`, `23:59`, `6:30`
- **Expected:** `ValidationError` for the first two; success for the rest —
  `6:30` is legal because the hour group is `\d{1,2}`
- **Why:** `time(24, 0)` raises a bare `ValueError` inside the scheduler; the
  guard is what turns it into a message naming the schedule

### SCH-007 · An unknown calendar is refused, not treated as weekdays
- **Area:** `schedule/spec.py::parse`,
  `core/calendars.py::CalendarRegistry.get`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a registry with only `always` and `weekdays`
- **Steps:** parse `06:30 TARGET2`
- **Expected:** `ValidationError` listing the loaded calendars and saying that
  treating it as weekdays "would produce controls that fire on the wrong days"
- **Why:** "a control declared against a calendar nobody loaded would look right
  and fire on the wrong days"

### SCH-008 · Cron is refused by name
- **Area:** `schedule/spec.py::parse`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `30 6 * * 1-5`, `@daily`, `0 0 1 * *`
- **Expected:** `ValidationError` listing the seven accepted forms and saying
  "Cron is deliberately not accepted — it cannot express a business calendar, and
  a schedule that is wrong on a holiday is a morning of false alarms"
- **Why:** a refusal that did not explain *why* would read as a missing feature
  rather than a decision

### SCH-009 · `describe` never raises
- **Area:** `schedule/spec.py::describe`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a registry without TARGET2
- **Steps:** describe `daily`, `nightly-ish`, `06:30 TARGET2`, `24:00`, `""`,
  `None`
- **Expected:** a sentence for the valid ones; "unreadable schedule: …" for the
  rest; no exception in any case
- **Why:** "this is what a list of controls prints beside each row, and one
  unparseable schedule must not take the page down — it has to be *visible* as
  broken instead". `describe` catches `ValidationError` only, and the calendar
  registry's refusal is one — so this case is also the guard on that remaining
  true

### SCH-010 · A dependency trigger cannot be declared
- **Area:** `schedule/spec.py::parse`, `schedule/trigger.py::DependencyTrigger`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** attempt to parse a schedule producing a `DependencyTrigger`
- **Expected:** no accepted form produces one
- **Why:** `trigger.py` opens "**Five kinds**, because data arrives in five ways"
  and describes dependency as "after another dataset's controls have run. So a
  reconciliation does not fire against half a ledger". Four are reachable from a
  schedule string; the fifth has no syntax, so a reconciliation control declared
  today fires on a timer

### SCH-011 · An interval trigger's next fire is aligned to an anchor
- **Area:** `schedule/trigger.py::IntervalTrigger.next_after`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `IntervalTrigger(minutes=60, offset_minutes=0)`
- **Steps:** `next_after` at 09:00:00, 09:00:01 and 09:59:59
- **Expected:** 10:00, 10:00, 10:00 — strictly after the moment, on the hour
- **Why:** `steps = int(elapsed // minutes) + 1` means the boundary itself is not
  the answer; a control run at exactly 09:00 must not be due again at 09:00

### SCH-012 · The offset staggers an interval
- **Area:** `schedule/trigger.py::IntervalTrigger.next_after`,
  `schedule/due.py::_stagger`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `offset_minutes=17`, hourly
- **Steps:** `next_after` at 09:00 and at 09:20
- **Expected:** 09:17 and 10:17
- **Why:** "without it, every hourly control in the estate fires at the top of
  the hour and lands on the source together"

### SCH-013 · The stagger is stable across nodes and restarts
- **Area:** `schedule/due.py::_stagger`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a set of control ids
- **Steps:** compute in two processes; compute again after a restart
- **Expected:** identical; every value in 0…59
- **Why:** "a random offset would re-stagger the estate on every deploy and make
  load unpredictable"

### SCH-014 · A calendar schedule is not staggered
- **Area:** `schedule/due.py::Schedule.plan`, `schedule/spec.py::parse`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** forty controls all scheduled `06:30 TARGET2`
- **Steps:** plan and inspect each trigger's next fire
- **Expected:** all forty at exactly 06:30
- **Why:** `offset_minutes` is passed into `parse` for every control but only
  `IntervalTrigger` consumes it. The stagger exists because "every hourly control
  in the estate fires at the top of the hour and lands on the source together" —
  which is exactly what every 06:30 control does, and those are the ones that
  fire right after a feed lands

### SCH-015 · A calendar trigger skips a holiday
- **Area:** `schedule/trigger.py::CalendarTrigger.next_after`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a TARGET2 calendar and a moment on the Thursday before Good
  Friday, after 06:30
- **Steps:** `next_after`
- **Expected:** the following Tuesday at 06:30 (Good Friday and Easter Monday
  closed, and the weekend)
- **Why:** "`30 6 * * 1-5` is wrong on Good Friday" — the whole reason this is
  not cron

### SCH-016 · A calendar trigger at exactly the due time moves to the next day
- **Area:** `schedule/trigger.py::CalendarTrigger.next_after`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a weekday calendar at 06:30
- **Steps:** `next_after` at 06:29:59, 06:30:00 and 06:30:01 on a business day
- **Expected:** today, tomorrow, tomorrow — the comparison is `due > moment`
- **Why:** `Schedule.plan` calls `next_after(previous_run)`, so a control that
  ran at exactly its due time must not be immediately due again

### SCH-017 · A calendar with no business day in a year is refused
- **Area:** `schedule/trigger.py::CalendarTrigger.next_after`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a calendar whose `weekend_days` covers all seven
- **Steps:** `next_after`
- **Expected:** `ValidationError` naming the calendar, remedy "Check the
  calendar's weekend days and holidays."
- **Why:** the 400-iteration bound is what stops an unbounded loop; without the
  refusal the scheduler would return `None` and the control would silently never
  run

### SCH-018 · A calendar due time is computed in the calendar's own zone
- **Area:** `core/calendars.py::BusinessCalendar.expected_at`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a calendar in `Europe/London`, due at 06:30, on a date in
  January and one in July
- **Steps:** compute the due instant
- **Expected:** 06:30 UTC in January and 05:30 UTC in July
- **Why:** "an arrival window written as 06:30 by a person in London must not
  drift by an hour twice a year"

### SCH-019 · A due time that does not exist on a spring-forward day
- **Area:** `core/calendars.py::BusinessCalendar.expected_at`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a `Europe/London` calendar due at 01:30 on 2026-03-29, when
  the clocks jump from 01:00 to 02:00
- **Steps:** compute the due instant, and `CalendarTrigger.next_after` across it
- **Expected:** record the instant chosen, and that `next_after` still advances
  strictly
- **Why:** `datetime.combine(date, time, tzinfo=zone)` constructs a local time
  that never occurs; the resulting UTC instant is an implementation choice, and a
  feed's deadline on that morning depends on it

### SCH-020 · A due time that happens twice on an autumn-back day
- **Area:** `core/calendars.py::BusinessCalendar.expected_at`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a `Europe/London` calendar due at 01:30 on 2026-10-25, when
  01:00–02:00 occurs twice
- **Steps:** compute the due instant
- **Expected:** the earlier of the two (`fold=0`), and the choice recorded
- **Why:** the difference is an hour of grace on one morning a year, and a feed
  judged LATE against the wrong one of the two is a false alarm that teaches
  somebody to stop reading them

### SCH-021 · An interval trigger's anchor drifts across a DST boundary
- **Area:** `schedule/trigger.py::IntervalTrigger.next_after`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a daily interval trigger and a `moment` that is tz-aware in a
  zone observing DST, on the day of a transition
- **Steps:** `next_after`
- **Expected:** record the result
- **Why:** `moment.replace(hour=0, …)` produces a local midnight and the interval
  is then added as an absolute `timedelta`, so a "daily" control shifts by an
  hour twice a year relative to local time — which is one of the three failures
  the module docstring says cron has

### SCH-022 · An arrival trigger has no clock time of its own
- **Area:** `schedule/trigger.py::ArrivalTrigger.next_after`
- **Type:** functional
- **Priority:** P1
- **Precondition:** arrival triggers with and without `due_by`
- **Steps:** `next_after`
- **Expected:** `None` without a deadline; the next calendar occurrence of the
  deadline with one
- **Why:** "a trigger that only fires on arrival can never report that nothing
  arrived — and a feed that silently stops is the failure this platform exists to
  catch"

### SCH-023 · A manual trigger is never due
- **Area:** `schedule/trigger.py::ManualTrigger.next_after`,
  `schedule/due.py::Schedule.plan`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a control scheduled `manual`, never run
- **Steps:** plan
- **Expected:** skipped with reason `manual`, **not** due — the manual check
  comes before the never-run check
- **Why:** a manual control being due on its first plan because it has no history
  would make "only when somebody asks" mean "once, immediately"

### SCH-024 · An arrival-triggered control is left alone by a timer pass
- **Area:** `schedule/due.py::Schedule.plan`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a control scheduled `on arrival`, never run
- **Steps:** plan
- **Expected:** skipped with reason `waits_for_arrival`; not due
- **Why:** "arrival triggers fire on a feed landing, not on a clock. A
  timer-driven pass must leave them alone rather than guess a cadence for them"

### SCH-025 · A control that has never run is due immediately
- **Area:** `schedule/due.py::Schedule.plan`, `NEVER`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a daily control accepted this afternoon, with no history
- **Steps:** plan at any time
- **Expected:** due, with `has_never_run is True` and `due_at is None`
- **Why:** "a control accepted this afternoon is checked tonight rather than at
  whatever boundary its cadence would next reach"

### SCH-026 · Due-ness is decided at the boundary, inclusively
- **Area:** `schedule/due.py::Schedule.plan`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an hourly control last run at 09:00 with a stagger of 0
- **Steps:** plan at 09:59:59, 10:00:00 and 10:00:01
- **Expected:** skipped, due, due — the comparison is `next_at <= now`
- **Why:** an exclusive comparison makes a control due one tick after its
  boundary for ever, which compounds into a visible drift on a short cadence

### SCH-027 · An unreadable schedule is skipped, never defaulted
- **Area:** `schedule/due.py::Schedule.plan`, `Skipped.is_a_defect`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a control whose schedule is `nightly-ish`
- **Steps:** plan
- **Expected:** skipped with reason `unreadable`, `detail` carrying the
  validation message, `is_a_defect is True`, a WARNING logged; it appears in
  `plan.defects`
- **Why:** "quietly running it on a cadence nobody chose would hide that for as
  long as it kept passing"

### SCH-028 · `not_due` and `manual` are the scheduler working
- **Area:** `schedule/due.py::Skipped.is_a_defect`
- **Type:** contract
- **Priority:** P1
- **Precondition:** skips of each reason — `not_due`, `manual`,
  `waits_for_arrival`, `unreadable`
- **Steps:** read `is_a_defect`
- **Expected:** `False, False, False, True`
- **Why:** "'not due until 06:30' and 'its schedule does not parse' are the same
  absence from a run and completely different facts, and a scheduler that
  reported only the first list would let the second hide for months"

### SCH-029 · A `not_due` skip says when it will next run
- **Area:** `schedule/due.py::Schedule.plan`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a daily control run an hour ago
- **Steps:** plan
- **Expected:** `detail` reading "next at <ISO-8601>"
- **Why:** an operator asking "why did this not run" needs the answer in the
  skip, not in a second query

### SCH-030 · `Plan.describe` names the defects separately and last
- **Area:** `schedule/due.py::Plan.describe`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a plan with 3 due, 5 skipped of which 1 unreadable
- **Steps:** describe
- **Expected:** "3 due, 5 not due, 1 with a schedule that cannot be read, which
  will never run until it is fixed"
- **Why:** "a control whose schedule cannot be read will never run again, and
  nothing else in the system will say so"

### SCH-031 · The plan is a pure function of controls, history and now
- **Area:** `schedule/due.py::Schedule.plan`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a fixed control list, history and moment
- **Steps:** plan twice
- **Expected:** identical results; no database access; no clock read
- **Why:** "takes the last-run times rather than reading them, so the decision is
  a pure function … and can be tested without a database or a clock"

### SCH-032 · A control with an empty schedule string is daily
- **Area:** `schedule/due.py::Schedule.plan`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a control whose `schedule` is `None` and one whose is `""`
- **Steps:** plan
- **Expected:** both treated as daily; neither skipped as unreadable
- **Why:** `control.schedule or ""` then `parse("")` reaches `DEFAULT`; a control
  that predates the schedule column must not become an unreadable defect

## `schedule/cadence.py` and `schedule/budget.py`

### SCH-033 · Nothing observed yields the declared starting cadence
- **Area:** `schedule/cadence.py::AdaptiveCadence.decide`, `CadenceBounds.start`
- **Type:** functional
- **Priority:** P1
- **Precondition:** bounds of floor 15, ceiling 1440, initial 0 and initial 60
- **Steps:** decide with an empty `Observation`
- **Expected:** 15 and 60; the reason says nothing has been observed yet
- **Why:** `initial_minutes or floor_minutes` means an unset initial falls back
  to the floor, which is the tightest cadence — worth pinning as the deliberate
  default

### SCH-034 · A single failure returns to the floor immediately
- **Area:** `schedule/cadence.py::AdaptiveCadence.decide`
- **Type:** contract
- **Priority:** P1
- **Precondition:** bounds floor 15, ceiling 1440; a current cadence of 480; a
  history of forty passes then one `fail`
- **Steps:** decide
- **Expected:** 15, with a reason saying it returns to its floor "rather than
  easing back"; the same for a trailing `error`
- **Why:** "the period just after a break is when the next one is most likely and
  when somebody is most likely to be watching"

### SCH-035 · Backoff needs a sample, and is slow
- **Area:** `schedule/cadence.py::AdaptiveCadence.decide`, `BACKOFF_FACTOR`,
  `PASSES_BEFORE_BACKOFF`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** floor 60, ceiling 10080, current 60
- **Steps:** decide after 9 consecutive passes, then after 10
- **Expected:** unchanged at 9 with a reason naming the sample size; widened at
  10 to 90 (60 × 1.5, rounded to the 15-minute grid)
- **Why:** "below this, a quiet patch is not evidence of stability — it is a
  small sample"; and "doubling would take a daily check to fortnightly in four
  quiet weeks, which is a different control from the one somebody approved"

### SCH-036 · The cadence never leaves its declared bounds
- **Area:** `schedule/cadence.py::CadenceBounds.clamp`,
  `AdaptiveCadence.decide`
- **Type:** contract
- **Priority:** P1
- **Precondition:** floor 60, ceiling 240, current 240, fifty consecutive passes
- **Steps:** decide repeatedly
- **Expected:** never above 240; the reason says the cadence is already at its
  declared ceiling
- **Why:** "a tier-one dataset carrying a CDE has a floor that no amount of quiet
  can widen, because the cost of finding out late is not paid by the scheduler"

### SCH-037 · Impossible bounds are refused
- **Area:** `schedule/cadence.py::CadenceBounds.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** construct with floor 0; floor −5; floor 60 and ceiling 15; floor 60
  and ceiling 60
- **Expected:** `ValidationError` for the first three; the fourth is legal (a
  fixed cadence)
- **Why:** "both bounds are required rather than defaulted. A floor invented by
  the platform would be the platform deciding how late a bank may learn about a
  break, which is not the platform's decision to make"

### SCH-038 · Three indeterminates hold the cadence rather than widening it
- **Area:** `schedule/cadence.py::AdaptiveCadence.decide`,
  `Observation.indeterminate_streak`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a history ending in two, then three, indeterminates
- **Steps:** decide
- **Expected:** at two, the consecutive-passes branch (an indeterminate is not a
  pass, so the streak is 0 and the cadence holds with a sample reason); at three,
  a hold whose reason says looking more often would not make an empty scope
  informative
- **Why:** "repeated indeterminates mean we are not learning anything by looking.
  Widening would be the wrong lesson: the answer is that somebody should fix the
  scope, and checking harder will not"

### SCH-039 · `consecutive_passes` counts backwards from the most recent
- **Area:** `schedule/cadence.py::Observation.consecutive_passes` /
  `.last_failed` / `.recent_failures`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** histories `()`, `("pass",)*10`,
  `("fail",) + ("pass",)*10`, `("pass",)*10 + ("fail",)`
- **Steps:** read all three properties
- **Expected:** 0/False/0; 10/False/0; 10/False/1; 0/True/1
- **Why:** "most recent last, so a reader of a stored history sees it in time
  order" — reading the tuple the other way round would reset the cadence on a
  failure from a month ago

### SCH-040 · `recent_failures` looks at a bounded window
- **Area:** `schedule/cadence.py::WINDOW`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a history of 100 verdicts where the first 50 are failures
- **Steps:** read `recent_failures`
- **Expected:** 0
- **Why:** "short enough that a dataset which has changed character is not judged
  on how it behaved last quarter"

### SCH-041 · Rounded intervals sit on a legible grid
- **Area:** `schedule/cadence.py::_round_interval`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** round 1, 7, 59, 60, 202, 1439, 1440, 5000
- **Expected:** 5, 5, 60, 60, 210, 1440, 1440, 5040 — never below the step
- **Why:** "202 becomes 303 becomes 454, and none of those numbers means
  anything. Rounding to a sensible step keeps the schedule legible and stops the
  interval moving on every run"

### SCH-042 · `Decision.direction` and `.changed` describe the move
- **Area:** `schedule/cadence.py::Decision`
- **Type:** functional
- **Priority:** P2
- **Precondition:** decisions with `previous_minutes` of 0, of the same value,
  of a smaller and of a larger value
- **Steps:** read `changed`, `direction`, `render()`
- **Expected:** `False/unchanged`; `False/unchanged`; `True/widened`;
  `True/narrowed`; the rendered sentence names both intervals only when changed
- **Why:** "an adaptive system that cannot say why it now checks something every
  four hours instead of every one is a system nobody trusts, and the first time
  it is blamed for a late detection it will be turned off"

### SCH-043 · `_period` renders a cadence a person would say
- **Area:** `schedule/cadence.py::_period`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** render 5, 60, 90, 120, 1440, 2880, 1500
- **Expected:** `5 minutes`, `hour`, `hour 30 minutes`, `2 hours`, `day`,
  `2 days`, `25 hours`
- **Why:** every cadence reason quotes this; `1 days` or `1 hours` in an
  explanation makes the whole sentence look machine-written

### SCH-044 · Critical work is never shed
- **Area:** `schedule/budget.py::Priority.may_be_shed`,
  `BudgetPolicy.allocate`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a budget of 10 and three critical candidates costing 20 in
  total
- **Steps:** allocate
- **Expected:** all three admitted; `over_committed is True`; `spent == 20`;
  `render()` says the critical work alone exceeds the budget, that it has been
  run anyway, and that somebody has to change one of the two
- **Why:** "a scheduler that quietly dropped it would be answering a question
  about money with a decision about risk"

### SCH-045 · Nothing is dropped silently
- **Area:** `schedule/budget.py::Allocation.render` / `.to_dict`
- **Type:** contract
- **Priority:** P1
- **Precondition:** twelve deferred candidates
- **Steps:** render
- **Expected:** each named on its own line with its dataset, priority, reason and
  next attempt — never only a count
- **Why:** "the dashboard is green because a third of the estate did not run, and
  nobody can tell the difference between a control that passed and one that never
  happened"

### SCH-046 · Shedding order contradicts its own docstring
- **Area:** `schedule/budget.py::BudgetPolicy.allocate`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** two NORMAL candidates at the same priority — A costing 1 with
  0 deferrals, B costing 100 with 3 deferrals — and a budget of 100
- **Steps:** allocate
- **Expected:** record which is admitted
- **Why:** the docstring says "then by priority, and within a priority **by cost
  ascending** — cheapest first, so the estate keeps the most controls for the
  budget it has. **Within equal cost**, whatever has been deferred longest goes
  first". The sort key is `(priority.rank, -deferrals, cost, identifier)`, so
  deferrals outrank cost: B is admitted, A is deferred, and the estate keeps one
  control instead of one hundred. Either the anti-starvation rule or the
  cheapest-first rule is the intended one, and the code and the prose disagree
  about which

### SCH-047 · A starving candidate is named as starving
- **Area:** `schedule/budget.py::Candidate.is_starving`,
  `Allocation.starving`, `Deferral.render`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** candidates with 2 and 3 prior deferrals, both deferred
- **Steps:** allocate and render
- **Expected:** only the second is starving; its line reads "This is deferral 4
  in a row for this control"; the allocation's closing paragraph says a control
  deferred every night is one that does not exist
- **Why:** "priority scheduling starves the bottom of the queue by construction.
  Noticing is not optional"

### SCH-048 · Exactly-fitting work is admitted
- **Area:** `schedule/budget.py::BudgetPolicy.allocate`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a budget of 10 and candidates costing 6 and 4
- **Steps:** allocate
- **Expected:** both admitted; `spent == 10`; `headroom == 0.0`;
  `over_committed is False`
- **Why:** the comparison is `spent + cost <= budget`; an off-by-one here leaves
  a permanent sliver of unusable budget

### SCH-049 · A zero budget defers everything sheddable
- **Area:** `schedule/budget.py::BudgetPolicy.__init__` / `.allocate`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `BudgetPolicy(0)` and `BudgetPolicy(-5)`, with one critical
  and three normal candidates
- **Steps:** allocate
- **Expected:** the budget is clamped to 0; the critical candidate runs and
  `over_committed is True`; the three normal ones are deferred by name
- **Why:** a negative budget is a configuration error that must not become
  negative headroom on a dashboard

### SCH-050 · A zero-cost candidate is always admitted
- **Area:** `schedule/budget.py::BudgetPolicy.allocate`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a budget of 0 and a NORMAL candidate costing 0; and one
  costing −5
- **Steps:** allocate
- **Expected:** both admitted; the negative one *reduces* `spent`
- **Why:** cost is caller-supplied and unvalidated; a negative estimate from a
  cost model returning a signed delta would admit unlimited work behind it

### SCH-051 · The deferral reason quotes the numbers
- **Area:** `schedule/budget.py::BudgetPolicy.allocate`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a budget of 10, spent 8, a candidate costing 5
- **Steps:** allocate and read the deferral's reason
- **Expected:** "the budget has 2 left and this would cost 5"
- **Why:** an operator deciding whether to raise the budget needs both numbers,
  and `:g` formatting is what keeps `2` from rendering as `2.0`

### SCH-052 · Every deferral carries a next attempt
- **Area:** `schedule/budget.py::BudgetPolicy.allocate`, `Deferral.render`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `retry_after_minutes=60` and `now`
- **Steps:** allocate with deferrals
- **Expected:** every `next_attempt` is `now + 60 minutes` and appears in the
  rendered line to the minute
- **Why:** "a deferred control is on the report, by name, with the reason **and
  when it will run instead**"

