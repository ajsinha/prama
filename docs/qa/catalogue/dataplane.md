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
| `connect/spi.py` — the connector contract | 24 | 11 | 10 | 3 |
| `connect/capability.py` — the pushdown matrix | 9 | 4 | 4 | 1 |
| `connect/arrow.py` — `to_array` | 11 | 6 | 4 | 1 |
| `connect/config_schema.py`, `registry.py`, `builtin.py` | 19 | 7 | 9 | 3 |
| `connect/cost.py` and `connect/pacing.py` | 18 | 4 | 11 | 3 |
| `connect/sources/sql/` — base and dialects | 23 | 10 | 11 | 2 |
| `connect/sources/sqlite.py` | 10 | 5 | 4 | 1 |
| `connect/sources/filesystem.py` | 11 | 5 | 5 | 1 |
| `connect/sources/objectstore.py` | 11 | 4 | 6 | 1 |
| `connect/sources/rest.py` | 11 | 5 | 5 | 1 |
| `connect/sources/mongo.py` | 9 | 4 | 4 | 1 |
| `connect/sources/query.py` | 9 | 5 | 3 | 1 |
| `connect/feed/` — arrival, trailers, patterns | 22 | 7 | 12 | 3 |
| `profile/sketches.py` — HLL, TDigest, CountMin, TopK | 22 | 8 | 11 | 3 |
| `profile/statistics.py` — column accumulation | 15 | 5 | 8 | 2 |
| `profile/profiler.py` — profiling end to end | 13 | 5 | 6 | 2 |
| `profile/segments.py`, `segmented.py`, `incremental.py` | 19 | 6 | 11 | 2 |
| `profile/recording.py` | 4 | 1 | 3 | 0 |
| `discover/relationships.py` | 10 | 2 | 6 | 2 |
| `execute/run.py` — the control run | 19 | 10 | 8 | 1 |
| `execute/claim.py`, `worker.py` — claims, leases, fencing | 20 | 9 | 10 | 1 |
| `core/concurrency/bounded_queue.py` | 13 | 4 | 7 | 2 |
| `execute/inflight.py`, `transport.py`, `kafka.py` | 22 | 10 | 10 | 2 |
| `execute/stream.py`, `watermark.py` | 18 | 6 | 10 | 2 |
| `execute/actions.py`, `preview.py` | 16 | 5 | 9 | 2 |
| `schedule/spec.py`, `trigger.py`, `due.py` | 24 | 10 | 11 | 3 |
| `schedule/cadence.py`, `budget.py` | 16 | 4 | 10 | 2 |
| **Total** | **418** | **172** | **208** | **48** |

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

