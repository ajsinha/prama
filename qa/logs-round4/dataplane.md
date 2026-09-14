# Data plane — QA execution log (round 4)

`prama.connect` (every connector: sqlite, filesystem, objectstore, mongo, rest, the SQL family — postgres/clickhouse/mysql/jdbc/dialects) · `prama.profile` (sketches, statistics, profiler, incremental planning, segmentation, relationships) · `prama.execute` (the run/worker/queue/stream/ inflight/preview machinery, Kafka transport) · `prama.schedule` (calendars, budgets, shedding).

All 540 cases in `qa/catalogue/dataplane.md` (`CON-001..226`, `PRO-001..109`, `EXE-001..153`, `SCH-001..052`) were re-attempted against the tree after batches **A–D**, following `qa/logs-round4/README.md`. **The baseline is round 3** (`qa/logs-round3/dataplane.md`: 504 PASS, 33 FAIL, 3 BLOCKED — 93.3%). The harness is the 37 case-scripts kept in `qa/harness/dataplane/` from round 3, reused as-is and re-executed fresh (a cleared `results.jsonl`, no carried-over rows) against real services: PostgreSQL (`127.0.0.1:55432` for platform-adjacent cases, `127.0.0.1:55433` for the SQL connector's own cases), ClickHouse (`127.0.0.1:58123`), MySQL (`127.0.0.1:33061`), MongoDB (`127.0.0.1:37019`), MinIO/S3 (`127.0.0.1:59000`) and a real JDBC/JVM bridge via jaydebeapi+JPype against the same PostgreSQL — all already running as Docker containers on this host. Kafka was checked (`127.0.0.1:19092`) and is **not** reachable, so `EXE-094`/`EXE-095` are BLOCKED, matching round 3; `CON-114` is BLOCKED for the same streaming-replication reason as round 3. No `src/`, `tests/`, `schema/`, `config/`, `qa/catalogue/` or `qa/regression-suite/` file was modified in the course of this run; every harness change lives in `qa/harness/dataplane/`.

**An infrastructure gap, not a product one.** The PostgreSQL container backing `127.0.0.1:55433` (`prama-qa-pg`) had been recreated this morning (`docker inspect`: `StartedAt 2026-09-13T10:10:34Z`, a fresh anonymous volume) — round 3's `positions` fixture (25,000 rows; `id`, `ccy`, `amount` columns, per CON-094's own stated precondition and CON-099's recorded column order) never made it into a checked-in setup script, the same never-saved-back pattern round 3's own README documented repeatedly for ad-hoc corrections. The first mechanical run of `con_sql_pg.py` against the empty container surfaced as three apparent regressions (`CON-083`, `CON-084`, `CON-091`) and a mid-script crash that would have silently orphaned `CON-092..105`/`115..121`/`101`/`100` unreported. A new, checked-in `seed_pg55433.py` reconstructs the fixture from the catalogue's own Precondition text and the harness scripts' own column/row requirements (never tuned to any one case's outcome), after which every one of `con_sql_pg.py`'s cases reproduced round 3's own recorded numbers exactly, `CON-096`'s `bytes=3100` included — strong evidence the reconstruction is faithful, and that nothing in `connect/sources/sql/postgres.py` moved (confirmed independently: the file carries zero commits across batches A–D).

**Three cases have no owning harness script** (round 3 built them by hand too, outside `qa_common.log()`): `CON-043`/`CON-044` are a direct `grep`/live repro against `src/` (both files involved carry zero commits in batches A–D), and `EXE-102` is `con_exe_stream.py`'s own `exe102()` — which logs `EXE-102-PASS`/`EXE-102-FAIL` per policy word but never the bare id — combined by hand exactly as round 3 did. `compile_log.py` catches a missing id as a hard assertion failure rather than a silent gap, which is how this was caught before the table was built.

## Counts

| | Count |
|---|---:|
| Total cases | 540 |
| PASS | 504 |
| FAIL | 33 |
| BLOCKED | 3 |
| **Pass rate** | **93.3%** (504/540) |

Round 3: 504 PASS, 33 FAIL, 3 BLOCKED — 93.3%. Round 4: 504 PASS, 33 FAIL, 3 BLOCKED — 93.3%.

## Regressions — a case that passed round 3 and fails now

**0.** A programmatic id-by-id diff of this round's 540 verdicts against round 3's own per-case table (`qa/logs-round3/dataplane.md`'s `## Per-case results` section, parsed mechanically, not by eye) found **zero** PASS→FAIL transitions, zero FAIL→PASS transitions, and zero cases whose recorded verdict changed at all — every one of the 540 ids carries the identical `PASS`/`FAIL`/`BLOCKED` verdict this round as round 3 recorded. This is consistent with the batch A–D diff: `git diff --stat` from round 3's finalisation commit to `HEAD` touches 13 files, and **none** of `src/prama/connect/**`, `src/prama/profile/**`, `src/prama/execute/**` or `src/prama/schedule/**` — the four packages this catalogue exercises — appear in it. The two changed files with any plausible reach into this area were checked directly:

- `src/prama/backend/execute.py` gained `unanswerable(plan)` and the `VERDICT_METRICS` table between `judge_segments` and `_verdict`. Diffed directly against pre-batch-A: `_verdict` and `judge_segments`'s own bodies are byte-identical; the only change is two new top-level names inserted between them. Purely additive, confirmed by reading the diff rather than assuming it.
- `src/prama/core/ids.py` — `UlidFactory.new()` now reads the clock *inside* the lock (the fix for a monotonicity race under clock skew/scheduling; see the file's own comment). `src/prama/execute/worker.py` is the only dataplane module that touches `core.ids` (via `new_ulid`), and the catalogue has no case asserting on ULID ordering, minted-id sequencing, or deterministic paging keyed by id — grepped for `ulid`, `monoton`, `page order`, `deterministic paging` and found nothing. The observable behaviour is identical for any single-threaded, forward-clock caller, which is every dataplane case; nothing here was reachable to break.

## Fixed since round 3 — a case that failed round 3 and passes now

**0.** All 33 of round 3's failures reproduce identically this round — same code path, and in every case checked, the same or an equivalent Observed value (see **Per-case detail for every FAIL** below). None of the files any of the 33 exercise appear in the batch A–D diff.

## Harness notes

**0 harness artefacts found** (round 3 found and fixed 15). Every one of the 37 case-scripts ran unmodified and reproduced round 3's own recorded numbers; the only harness-side additions this round are `seed_pg55433.py` (environment/fixture setup — see above, not a correction to any assertion) and `build_markdown_r4.py` (this file's generator). One genuine harness limitation was re-confirmed rather than fixed: `con_exe_stream.py`'s `exe102()` still logs only `EXE-102-{PASS,FAIL}`, never the bare `EXE-102` id round 3 also had to construct by hand — left as-is since round 3 made the same choice and the underlying two sub-results are unambiguous (both PASS).

**A saved-script crash, caught before it could hide anything.** `con_sql_pg.py` run against the not-yet-reseeded PostgreSQL container crashed inside `con091()` on `CON-091` (`ConnectorError: CONNECT.OBJECT_MISSING`, uncaught) — which would have silently orphaned `CON-092` through `CON-105`, `CON-115..121`, `CON-101` and `CON-100` (23 cases) exactly the way round 3's own README describes for `con_spi.py`/`con014.py`/etc. Caught here because `compile_log.py`'s `assert not missing` on the full 540-id set fails loudly rather than letting a partial run pass silently — the exact discipline this round's briefing asked for. After reseeding, the full script ran to completion with no changes to the script itself.

**The `except ValueError` risk did not reach this area.** grepped all 37 scripts for `except ValueError`: 6 hits, all wrapping calls into `prama.core.concurrency.BoundedQueue`/`claim_unit` (`EXE-055`, `EXE-063`, part of `EXE-`-series claim tests) and pure Arrow/sketch boundary checks (`con_arrow.py`, `con_sketches.py`) — none of them wrap a call reachable from `prama.bench.corpus` (which is not imported anywhere under `prama.connect`, `prama.profile`, `prama.execute` or `prama.schedule`, confirmed by grep), so the `ValidationError`-is-not-a-`ValueError` regression that hit `BCH-015`/`BCH-016` elsewhere has no equivalent here.

## Failures ranked by severity

- **CON-006** (P1) — Using a connector before `open` names the mistake
- **CON-009** (P1) — Declaring no capabilities is legal only alongside `can_run_controls = False`
- **CON-014** (P1) — A connector that declares `pushdown.predicate` must actually apply it
- **CON-021** (P1) — `ReadPolicy.permits_path` treats an empty allow-list as "everything"
- **CON-043** (P1) — `to_array` is used by every connector that builds a batch by hand
- **CON-044** (P1) — A mixed-type column read over SQLite does not raise
- **CON-055** (P1) — `validate` refuses a supplied secret outright
- **CON-096** (P1) — A truncated read says so in the log and in `last_read`
- **CON-099** (P1) — `_column_names` is stale between a `_fetch` and a `_stream`
- **CON-118** (P1) — The base `select_sql` drops a predicate
- **CON-142** (P1) — The filesystem connector ignores the read policy's budgets
- **CON-153** (P1) — A URI that is not an object store is MISCONFIGURED, not UNREACHABLE
- **CON-167** (P1) — A mixed-type column can still be read as Arrow
- **CON-172** (P1) — A declared predicate is applied to the query
- **CON-181** (P1) — Credentials in a built URI are percent-encoded
- **CON-206** (P1) — `from_dict` loses half the definition
- **CON-217** (P1) — A trailer count mismatch is a count mismatch, with the shortfall
- **PRO-009** (P1) — Small cardinalities use linear counting and are near-exact
- **PRO-021** (P1) — A merged TDigest answers like the digest of the whole
- **PRO-058** (P1) — `suggest_sample_plan` reads everything below the ceiling
- **PRO-099** (P1) — A generic column name never proposes a relationship
- **EXE-018** (P1) — The recorded snapshot is always wall-clock
- **EXE-019** (P1) — Coverage is recorded as `full` whatever was read
- **EXE-043** (P1) — `drain` does not spin on a permanently failing recorder
- **EXE-050** (P1) — A stranded unit is invisible in the fleet report
- **EXE-096** (P1) — An undeserialisable message is not dead-lettered as unreadable
- **SCH-046** (P1) — Shedding order contradicts its own docstring
- **CON-062** (P2) — `register_builtin` is idempotent
- **CON-129** (P2) — A non-FULL, non-HEAD plan produces a deterministic ordering
- **CON-219** (P2) — The reported `observed_count` on a total mismatch is the line index
- **SCH-014** (P2) — A calendar schedule is not staggered
- **SCH-041** (P2) — Rounded intervals sit on a legible grid
- **PRO-063** (P3) — `from_rows` is not exported

## Blocked

- **CON-114** — PostgreSQL's snapshot follows recovery state: PostgreSQL's snapshot follows recovery state: needs a live PostgreSQL primary AND a streaming-replication standby. Setting up physical replication between two containers is beyond what a single docker run provides; not attempted given the task's scop
- **EXE-094** — Kafka commits `offset + 1`: needs a live Kafka broker (offset+1 commit semantics can only be verified against a real broker's actual redelivery behaviour on reconnect with the same group id -- a fake consumer would only test our own mock, not confluent_kafka/the broker's real s
- **EXE-095** — A broker error aborts the batch without enforcing: needs a live Kafka broker to produce a record genuinely carrying a broker-level error through confluent_kafka's real poll() path; the pure error-handling logic in KafkaTransport.poll() is trivial to reach with a stubbed consumer.poll(), but doing so 

## Per-case results

| Id | Result | Observed |
|---|---|---|
| `CON-001` | PASS | Can't instantiate abstract class Bare without an implementation for abstract methods 'describe', 'discover', 'health', 'manifest', 'read', 'snapshot' |
| `CON-002` | PASS | open()->None close()->None |
| `CON-003` | PASS | calls=['open', 'close'] ctx_is_c=True |
| `CON-004` | PASS | raised=True calls=['open', 'close'] |
| `CON-005` | PASS | second close() raised nothing |
| `CON-006` | FAIL | sqlite.describe: code=CONNECT.OBJECT_MISSING; sqlite.snapshot: code=CONNECT.OBJECT_MISSING; sqlite.read: code=CONNECT.OBJECT_MISSING; filesystem.describe: code=CONNECT.OBJECT_MISSING; filesystem.snapshot: code=CONNECT.OBJECT_MISSING; filesystem.read: code=CONNECT.OBJECT_MISSING; rest.describe: code=CONNECT.NOT_OPEN; rest.snapshot: no error; rest.read: code=CONNECT.NOT_OPEN; mongodb.describe: code=… |
| `CON-007` | PASS | msg=[CONNECT.ERROR] Minimal cannot run a query against its source \| Next: This source has no query engine of its own, so its controls are evaluated locally over the rows `read` yields. Check `can_run_controls` before asking. \| Context: connector='Minimal' remedy=This source has no query engine of its own, so its controls are evaluated locally over the rows `read` yields. Check `can_run_controls`… |
| `CON-008` | PASS | can_run_controls=False |
| `CON-009` | FAIL | empty_keys=['rest'] (expected rest+mongodb) |
| `CON-010` | PASS | code=CONNECT.NO_PUSHDOWN remedy=Run this control through the Arrow backend instead, or use a connector that declares a pushdown capability. |
| `CON-011` | PASS | sql=True regex=False empty=False |
| `CON-012` | PASS | code=CONNECT.NO_PREDICATE ctx={'connector': 'Minimal', 'predicate': "d = '2026-04-01'"} remedy=Profile this object whole, or reach it through a connector that can filter. Reading everything and calling it one segment would attribute the whole object's data to that segment. |
| `CON-013` | PASS | returned None |
| `CON-014` | FAIL | raised CONNECT.NO_PREDICATE instead of returning filtered rows: [CONNECT.NO_PREDICATE] MongoConnector cannot restrict a read to part of an object \| Next: Profile this object whole, or reach it through a connector that can filter. Reading everything and calling it one segment would attribute the whole object's data to that segment. \| Context: connector='MongoConnector', predicate="d = '2026-04-01… |
| `CON-015` | PASS | True,False,False |
| `CON-016` | PASS | {'FULL': True, 'HEAD': False, 'SYSTEMATIC': True, 'STRATIFIED': True, 'RESERVOIR': True, 'RECENT_PARTITIONS': True} |
| `CON-017` | PASS | {'full': 'full scan', 'full_pred': "full scan where d='2026-04-01'", 'systematic': 'systematic sample at 1.5%', 'reservoir': 'reservoir sample of 1,000 rows', 'stratified': 'stratified'} |
| `CON-018` | PASS | false_for=['OBJECT_LISTING', 'WALL_CLOCK'] |
| `CON-019` | PASS | all present as expected |
| `CON-020` | PASS | matches |
| `CON-021` | FAIL | empty_policy=True risk.positions=True risk=False riskier.positions=False empty_path=False |
| `CON-022` | PASS | no_policy=True in_range=True out_range=False hour24=False hour_neg1=False |
| `CON-023` | PASS | verification=code_complete description='[CODE COMPLETE — written and unit-tested; no live source has answered it]' |
| `CON-024` | PASS | qualified_name='' leaf='' |
| `CON-025` | PASS | code=CONNECT.CAPABILITY_MISSING ctx={'feature': 'pushdown.regex'} msg=[CONNECT.CAPABILITY_MISSING] this source cannot perform regex at the source \| Next: Rewrite the control without it, or run it through the Arrow backend and accept the cost of moving the data. Prama will not substitute a construct that means almost the same thing. \| Context: feature='pushdown.regex' remedy=Rewrite the control w… |
| `CON-026` | PASS | all four require() calls returned None |
| `CON-027` | PASS | {'APPROX_DISTINCT': 'approx distinct', 'EXACT_SNAPSHOT': 'exact', 'SQL': 'sql'} |
| `CON-028` | PASS | add->AttributeError assign->FrozenInstanceError pushdown_capabilities()=6 caps, no I/O attempted |
| `CON-029` | PASS | t1=['pushdown.filter', 'pushdown.sql', 'pushdown.window'] sorted_matches=True t1==t2:True |
| `CON-030` | PASS | attrs=[{'regex_flavour': 'posix', 'mutated': True}, {'regex_flavour': 'posix'}] |
| `CON-031` | PASS | regex_flavour='none' |
| `CON-032` | PASS | [None, True, False, False] |
| `CON-033` | PASS | [None, 38, 38, None] |
| `CON-034` | PASS | pg/ch/sf identical=True; jdbc: reg=['pushdown.aggregation', 'pushdown.filter', 'pushdown.predicate', 'pushdown.sql'] dialect=['pushdown.aggregation', 'pushdown.filter', 'pushdown.predicate', 'pushdown.sql'] (jdbc differs=False) |
| `CON-035` | PASS | ['int64', 'string', 'double', 'bool'] |
| `CON-036` | PASS | type=uint64 value=18446744073709551615 |
| `CON-037` | PASS | type=string values=['100', 'one hundred'] |
| `CON-038` | PASS | type=string values=['1953193.464900000000', 'x'] |
| `CON-039` | PASS | lens=[2, 2, 3] a1_nulls=2 a2[0]=None a3=[None, '1', 'x'] |
| `CON-040` | PASS | len=0 type=null |
| `CON-041` | PASS | ValueError propagated: cannot stringify |
| `CON-042` | PASS | type=string values=['-1', '18446744073709551615'] (uint64-wrapped=False) |
| `CON-043` | FAIL | grep confirms sql/base.py (RecordBatch.from_arrays + to_array) and mongo.py (RecordBatch.from_arrays + to_array) route through to_array; sqlite.py._read_batch still calls pa.array(list(column)) directly (bypasses to_array); rest.py.read still uses RecordBatch.from_pydict (bypasses to_array) -- only 2 of 4 route through it, not all four. Unchanged from round 3 -- none of these four files appear in … |
| `CON-044` | FAIL | Reproduced fresh: sqlite3 table 'CREATE TABLE t (v)' (no declared type), INSERT (100) and ('one hundred'), then `async for batch in SqliteConnector({'database_path':dbpath}).read(('t',))`. Raises ArrowInvalid: "Could not convert 'one hundred' with type str: tried to convert to int64" -- the table cannot be read at all. Unchanged from round 3 -- sqlite.py carries zero commits in batches A-D. |
| `CON-045` | PASS | identical for all 9 |
| `CON-046` | PASS | present={'include_views', 'schemas', 'statement_timeout_ms'} missing=set() |
| `CON-047` | PASS | default=2 |
| `CON-048` | PASS | required=True |
| `CON-049` | PASS | field=FieldSpec(name='k', default=None, required=False, secret=False, input_kind=<InputKind.TEXT: 'text'>, label='', help='', group='connection', choices=(), order=100) |
| `CON-050` | PASS | derived fields=[] |
| `CON-051` | PASS | ["sqlite: overlay describes 'nonexistent_field', which the connector never reads"] |
| `CON-052` | PASS | audit()=[] |
| `CON-053` | PASS | unknown_overlay_keys=('invented_field',) in_form=False |
| `CON-054` | PASS | {'name': 'password', 'label': 'Password', 'input': 'password', 'required': False, 'secret': True, 'default': None, 'help': '', 'group': 'connection', 'choices': []} |
| `CON-055` | FAIL | msg=[INPUT.INVALID] postgresql needs schemas \| Next: Fill in the highlighted fields; the connector reads them with no default. \| Context: connector='postgresql', missing=['schemas'] remedy=Fill in the highlighted fields; the connector reads them with no default. |
| `CON-056` | PASS | {}: {'connector': 'filesystem', 'missing': ['root_path']}; {'root_path': ''}: {'connector': 'filesystem', 'missing': ['root_path']}; {'root_path': None}: {'connector': 'filesystem', 'missing': ['root_path']} |
| `CON-057` | PASS | required+secret field found: postgresql.dsn; missing-list=['database', 'host', 'schemas'] |
| `CON-058` | PASS | ValidationError raised by schema.validate() before connector __init__ ran |
| `CON-059` | PASS | [REGISTRY.INVALID] no connector plugin registered for 'snowfalke' \| Next: Available: clickhouse, filesystem, jdbc, mongodb, objectstore, postgresql, rest, snowflake, sqlite. Install the package providing it, or correct the key. \| Context: available=['clickhouse', 'filesystem', 'jdbc', 'mongodb', 'objectstore', 'postgresql', 'rest', 'snowflake', 'sqlite'], key='snowfalke', kind='connector' |
| `CON-060` | PASS | RegistryError: [REGISTRY.INVALID] no connector plugin registered for 'nope' \| Next: Available: clickhouse, filesystem, jdbc, mongodb, objectstore, postgresql, rest, snowflake, sqlite. Install the package providing it, or correct the key. \| Context: available=['clickhouse', 'filesystem', 'jdbc', 'mongodb', 'objectstore', 'postgresql', 'rest', 'snowflake', 'sqlite'], key='nope', kind='connector' |
| `CON-061` | PASS | RegistryError raised; get('sqlite') still original=True |
| `CON-062` | FAIL | len=0 keys=[] |
| `CON-063` | PASS | before={'field_one'} after={'field_one', 'field_two'} |
| `CON-064` | PASS | {'RELATIONAL': ['clickhouse', 'jdbc', 'postgresql', 'snowflake', 'sqlite'], 'OBJECT_STORE': ['objectstore'], 'FILESYSTEM': ['filesystem'], 'API': ['rest'], 'DOCUMENT': ['mongodb']} |
| `CON-065` | PASS | estimate() signature takes no connector/session object at all -- zero queries possible by construction; rows=100 |
| `CON-066` | PASS | rows=None bytes=None dur=None bases=(EstimateBasis.UNKNOWN,EstimateBasis.UNKNOWN,EstimateBasis.UNKNOWN) sentence='Reading t will scan ? — duration unknown, nothing has been read through this connection yet.' |
| `CON-067` | PASS | byte_count=128000 basis=EstimateBasis.DERIVED warnings=('the source reports rows but not size; volume assumes 128 bytes per row', 'this is a full scan; sampling would cost a fraction of it') |
| `CON-068` | PASS | duration=10.0 basis=EstimateBasis.MEASURED |
| `CON-069` | PASS | duration=50.0 basis=EstimateBasis.DERIVED |
| `CON-070` | PASS | duration=None basis=EstimateBasis.UNKNOWN |
| `CON-071` | PASS | exceeds=("this connection's limit of 1,000 rows", "this connection's limit of 1.0 MB") within_budget=False sentence="Reading t will scan 10.0 MB across about 5,000 rows — duration unknown, nothing has been read through this connection yet. This exceeds this connection's limit of 1,000 rows, this connection's limit of 1.0 MB." |
| `CON-072` | PASS | exceeds=() within_budget=True rows=1000 |
| `CON-073` | PASS | plan=SamplePlan(strategy=<SamplingStrategy.SYSTEMATIC: 'systematic'>, rows=1000, fraction=0.2, seed=0, stratify_by=(), partitions=None, predicate='') |
| `CON-074` | PASS | p1=None p2=None p3=None |
| `CON-075` | PASS | plan=SamplePlan(strategy=<SamplingStrategy.SYSTEMATIC: 'systematic'>, rows=1000, fraction=0.1, seed=0, stratify_by=(), partitions=None, predicate='') |
| `CON-076` | PASS | first4=[None, None, None, None] fifth=Throughput(bytes_per_second=100000.0, rows_per_second=1000.0, samples=1, measured_at=datetime.datetime(2026, 9, 14, 1, 45, 21, 323506, tzinfo=datetime.timezone.utc)) |
| `CON-077` | PASS | registry.of('c')=None from_read=None |
| `CON-078` | PASS | rows_per_second=990.1089108910891 samples=101 measured_at=2026-01-02 00:00:00+00:00 |
| `CON-079` | PASS | bytes=['0 B', '1,023 B', '1.0 KB', '1,024.0 TB'] durations=['under a second', '1 seconds', '89 seconds', '2 minutes', '90 minutes', '1.5 hours'] (expected_durations=['under a second', '1 seconds', '89 seconds', '2 minutes', '90 minutes', '1.5 hours']) |
| `CON-080` | PASS | pause_after(0.1)=1.9000000000000001 |
| `CON-081` | PASS | {0.0: (False, 0.0), 1.0: (False, 0.0), 1.5: (False, 0.0), -0.1: (False, 0.0), 0.999: (True, 0.0010010010010010895)} |
| `CON-082` | PASS | slept=[30.0] capped_pauses=1 |
| `CON-083` | PASS | ReadOnlySQLTransactionError: cannot execute DELETE in a read-only transaction |
| `CON-084` | PASS | state=HealthState.DEGRADED detail=the source did not respond in time: canceling statement due to statement timeout |
| `CON-085` | PASS | application_name='prama' |
| `CON-086` | PASS | args keys=['dsn', 'server_settings', 'timeout'] (host/port/database silently ignored: {'dsn': 'postgresql://x/y', 'timeout': 10.0, 'server_settings': {'application_name': 'prama'}}) |
| `CON-087` | PASS | {'disable': None, '': None, 'prefer': 'prefer', 'verify-full': 'verify-full', 'verify-nothing': 'verify-nothing'} |
| `CON-088` | PASS | a: state=HealthState.UNAUTHORISED missing=('catalogue read',); b: state=HealthState.DEGRADED detail='connected, and the catalogue could not be read: unsupported type from driver. This is not a permissions failure — the connection and the credential both worked.' |
| `CON-089` | PASS | results=['unauthorised', 'unauthorised', 'unauthorised', 'unauthorised', 'degraded', 'degraded', 'unreachable', 'unauthorised'] (last case 'relation "permissions" does not exist' misclassified as unauthorised because it contains the substring 'permission') |
| `CON-090` | PASS | ('public', 't') ('s', 't') ('s', 't') (3-part path's first segment 'cat' silently dropped: ('s', 't')) |
| `CON-091` | PASS | estimated_rows=None count(*) issued=False |
| `CON-092` | PASS | estimated_rows=None n_columns=3 |
| `CON-093` | PASS | real_estimate=25000 fetch_returning[-1]=>None fetch_returning[0]=>0 |
| `CON-094` | PASS | row-capped read: 10000 rows (expected 10000); byte-capped(1 byte) read: 1 batch(es), 10000 rows |
| `CON-095` | PASS | [10000, 25, 10000, 1] |
| `CON-096` | FAIL | log='' last_read={'object': 'public.positions', 'rows': 100, 'bytes': 3100, 'seconds': 0.001, 'pacing': {'batches': 1, 'working_seconds': 0.001, 'waiting_seconds': 0.0, 'achieved_duty_cycle': 1.0, 'capped_pauses': 0}} |
| `CON-097` | PASS | recorded_seconds=0.016 wall_elapsed=0.238 ratio=0.06710868951085369 |
| `CON-098` | PASS | [CONNECT.ERROR] the source returned rows without column names \| Next: A metric query's columns have to be named for its results to be judged. This is a driver problem rather than a control problem. \| Context: connector='PostgresConnector' remedy=A metric query's columns have to be named for its results to be judged. This is a driver problem rather than a control problem. |
| `CON-099` | FAIL | run_metric_query keys={'id', 'ccy'} (stale _stream_columns from read() were ('id', 'ccy', 'amount')) |
| `CON-100` | PASS | base/oracle={'base': '"x""; DROP TABLE y --"', 'oracle': '"x""; DROP TABLE y --"'} sqlserver='[x]]; DROP --]' mysql='`x``; DROP -- `' databricks='`x``; DROP -- `' bigquery(backslash)='`a\\\\`' bigquery(backtick)='`a\\`b`' |
| `CON-101` | PASS | jdbc-wrapped.placeholder(1)='?' native.placeholder(1)='$1' |
| `CON-102` | PASS | code=CONNECT.NO_DIALECT remedy=Set `dialect` to one of: bigquery, databricks, db2, generic, mysql, oracle, postgresql, redshift, sqlserver, synapse, teradata, trino. Guessing would send one database's SQL to another and produce a control that compiles and then fails at the source. |
| `CON-103` | PASS | code=CONNECT.UNKNOWN_DIALECT remedy=One of: bigquery, databricks, db2, generic, mysql, oracle, postgresql, redshift, sqlserver, synapse, teradata, trino. JDBC is a transport and not a dialect — the same protocol fronts a dozen databases whose SQL differs, so Prama has to be told which. |
| `CON-104` | PASS | {'jdbc_url': ('CONNECT.INCOMPLETE', True), 'driver_class': ('CONNECT.INCOMPLETE', True), 'driver_path': ('CONNECT.INCOMPLETE', True)} |
| `CON-105` | PASS | _fetch_size references=1 (its own assignment only); _stream docstring mentions fetchmany+fetch size=True |
| `CON-106` | PASS | type=Decimal value=Decimal('1953193.464900000000') |
| `CON-107` | PASS | same read (converter replacement applies in this process regardless of import order since _use_exact_decimals runs on every open()): type=Decimal value=Decimal('1953193.464900000000') |
| `CON-108` | PASS | discover() succeeded, 1 table(s): {'prama.bigrows': 'int'} |
| `CON-109` | PASS | results=['org.postgresql.util.PSQLException', 'org.postgresql.util.PSQLException', 'org.postgresql.util.PSQLException'] lingering_jdbc_threads=[] |
| `CON-110` | PASS | after close(), lingering jdbc worker threads=[] (process did not hang; note: full 'interpreter exits promptly' claim can only be fully confirmed by observing process exit, which this in-process check approximates via thread enumeration) |
| `CON-111` | PASS | int bind: sql='SELECT * FROM t WHERE a = {p0:String}' params={'p0': 42}; literal-quote case: sql="SELECT '{p0:String}' AS literal_q, a = {p1:String}" params={'p0': 'x', 'p1': 7} |
| `CON-112` | PASS | n_rows=25000 no_dupes=True all_present=True predicate_read_rows=5000 (expected 5000) |
| `CON-113` | PASS | dialect.snapshot_sql()=None snapshot=Snapshot(kind=<SnapshotKind.WALL_CLOCK: 'wall_clock'>, identifier='2026-09-14T01:45:20.042082+00:00', captured_at=datetime.datetime(2026, 9, 14, 1, 45, 20, 42105, tzinfo=datetime.timezone.utc), detail={'object': 'default.anything', 'note': 'clickhouse offers no point-in-time marker; this snapshot cannot be replayed exactly'}) |
| `CON-114` | BLOCKED | PostgreSQL's snapshot follows recovery state: needs a live PostgreSQL primary AND a streaming-replication standby. Setting up physical replication between two containers is beyond what a single docker run provides; not attempted given the task's scope (same as round 2 and round 3). |
| `CON-115` | PASS | sql='SELECT * FROM "public"."ordered_seed" TABLESAMPLE BERNOULLI (1) REPEATABLE (42)' repeatable_with_same_seed=True distinct_days_in_1pct_sample=90_of_100_in_table (n_sample_rows=219) |
| `CON-116` | PASS | {0: 'SELECT * FROM "public"."positions" TABLESAMPLE BERNOULLI (1e-06)', 1e-12: 'SELECT * FROM "public"."positions" TABLESAMPLE BERNOULLI (1e-06)', 1.0: 'SELECT * FROM "public"."positions" TABLESAMPLE BERNOULLI (100)', 2.0: 'SELECT * FROM "public"."positions" TABLESAMPLE BERNOULLI (100)', None: 'SELECT * FROM "public"."positions" TABLESAMPLE BERNOULLI (1)'} |
| `CON-117` | PASS | sample_plan_is_supported(STRATIFIED)=False; grep hits='/home/ashutosh/PycharmProjects/prama/src/prama/connect/sources/sql/postgres.py:310:def sample_plan_is_supported(plan: SamplePlan) -> bool:' (only the definition itself, no caller) |
| `CON-118` | FAIL | select_sql='SELECT * FROM "public"."positions" LIMIT 100 OFFSET 0' (predicate present=False) stream_sql='SELECT * FROM "public"."positions" WHERE booked = DATE \'2026-04-01\'' (predicate present=True) |
| `CON-119` | PASS | SELECT * FROM "public"."positions" TABLESAMPLE BERNOULLI (1) WHERE ccy = 'GBP' |
| `CON-120` | PASS | warnings_present={'Oracle': True, 'SqlServer': True, 'Db2': True, 'Teradata': True, 'Redshift': True, 'Databricks': True, 'Synapse': True, 'Trino': True, 'BigQuery': True, 'Snowflake': True} snowflake_verification=code_complete:True |
| `CON-121` | PASS | results=[True, False, True, False, True, True, True, True, False, False, False, False] expected=[True, False, True, False, True, True, True, True, False, False, False, False] |
| `CON-122` | PASS | OperationalError: attempt to write a readonly database |
| `CON-123` | PASS | before=24576:1789350422147410682:6 after=24576:1789350422151011317:6 |
| `CON-124` | PASS | id1=24576:1789350422151011317:6 id2=24576:1789350422151011317:6 exact=True |
| `CON-125` | PASS | before=8192:1789350422164478824:2 after=8192:1789350422164478824:2 (in-place same-length edit with restored mtime is undetected, as stated) |
| `CON-126` | PASS | broken_view found=True estimated_rows=None |
| `CON-127` | PASS | objects=['positions', 'broken_view'] |
| `CON-128` | PASS | describe: code=CONNECT.OBJECT_MISSING remedy='Give the table or view name.'; snapshot: code=CONNECT.OBJECT_MISSING remedy='Give the table or view name.'; read: code=CONNECT.OBJECT_MISSING remedy='Give the table or view name.' |
| `CON-129` | FAIL | seed42_run1_len=100 identical_rerun=True differs_at_seed43=False |
| `CON-130` | PASS | SELECT * FROM "positions" ORDER BY (rowid * 1 % 1000003) LIMIT 100 OFFSET 0 |
| `CON-131` | PASS | n_rows=25000 n_distinct=25000 |
| `CON-132` | PASS | describe: UnauthorisedError (read policy) [CONNECT.UNAUTHORISED] that path resolves outside this connection's root: ../secret.csv \| Next: Reads are confined to /tmp/tmpqfz9hqtl/root. Point the connection at the directory that holds the data, or move the file into it. \| Context: path='../secret.csv'; read: UnauthorisedError (read policy) [CONNECT.UNAUTHORISED] that path resolves outside this conn… |
| `CON-133` | PASS | discovered=['data.csv', "it's_data.csv", 'header_only.csv', 'empty.csv'] n_columns=2 n_rows=2 reader_expr="read_csv_auto('/tmp/tmpqfz9hqtl/root/it''s_data.csv')" |
| `CON-134` | PASS | {'data.xyz': ('CONNECT.FORMAT_UNSUPPORTED', "[CONNECT.FORMAT_UNSUPPORTED] cannot read .xyz \| Next: Supported here: .csv, .json, .jsonl, .ndjson, .parquet, .pq, .tsv, .txt. \| Context: file='data.xyz'", 'Supported here: .csv, .json, .jsonl, .ndjson, .parquet, .pq, .tsv, .txt.'), 'README': ('CONNECT.FORMAT_UNSUPPORTED', "[CONNECT.FORMAT_UNSUPPORTED] cannot read a file with no extension \| Next: Sup… |
| `CON-135` | PASS | discovered=['data.csv', 'empty.csv', 'header_only.csv', "it's_data.csv"] |
| `CON-136` | PASS | default_hashed_bytes=67108864 (expected 67108864); 1MB_ceiling_hashed_bytes=1048576 (expected 1048576) |
| `CON-137` | PASS | a=051d7b48b2635db0a8167d2530e65ffc575dcf894185f6dd605c75d939d9bb20 b=095b1c1c7b6610b7228c5dfc3fd9bc20e20b655b6a1483750792ecfad69a0b85 a_bytes=1048593 b_bytes=1048615 (size differs so digest differs even though first 1MB identical and hash truncated at 1MB) |
| `CON-138` | PASS | hashed_bytes=10 file_bytes=10 |
| `CON-139` | PASS | header_only.csv=(0, ('a', 'b', 'c'), 0); empty.csv=(0, ('column0',), 0) |
| `CON-140` | PASS | conc1_rows=200000 conc2_rows=200000 (expected 200000 each) |
| `CON-141` | PASS | rows_read=500000 ticks_recorded=29 max_gap_seconds=0.0017 |
| `CON-142` | FAIL | rows_read=100000 against ReadPolicy(max_rows_read=100) on a 100,000-row file (policy honoured=False) |
| `CON-143` | PASS | n_datasets=1 tags=('booked',) comment=9,000 rows; 900 object(s); partitioned by booked |
| `CON-144` | PASS | d1: path=('b', 'risk', '2026', 'positions') depth=0; d2: path=('b', 'risk', 'positions') depth=1 cols=() |
| `CON-145` | PASS | results={'2026': True, '202604': True, '20260401': True, '7': True, '1234': True, '12345': False, 'v2': False, 'part': False, '2026-4-1': False} |
| `CON-146` | PASS | code=CONNECT.TOO_MANY_OBJECTS remedy=Point the connection at a narrower prefix, or raise max_objects. Reading a partial listing would profile part of the data as though it were all of it. |
| `CON-147` | PASS | discover() with exactly 5 objects against max_objects=5: found 1 dataset(s): ['5 object(s)'], no refusal |
| `CON-148` | PASS | parquet: kind=SnapshotKind.FILE_DIGEST exact=True id_before=fe8acd2ee528f163a4b6a50af8df8070 id_after_rewrite=29574713d77f8f8dc986cfd4e4274aa6; csv: kind=SnapshotKind.OBJECT_LISTING exact=False |
| `CON-149` | PASS | discover() before adding object: comment=1 object(s); discover() on the SAME connector after adding a second object to the prefix: comment=1 object(s) -- new object visible=False |
| `CON-150` | PASS | mixed CSV+Parquet dataset: reading raised InvalidInputException: Invalid Input Error: Error when sniffing file "s3://prama-test/mixed_ds/part-1.parquet". It was not possible to automatically detect the CSV parsing dialect The search space used was: Delimiter Candidates: ',', '\|', ';', '	' Quote/Escape Candidates: ['(no quote)','(no escape)'],['"','(no escape)'],['"','"'],['"','''],['"','\'],[''',… |
| `CON-151` | PASS | CREATE OR REPLACE SECRET prama_store (TYPE s3, KEY_ID 'AKID', SECRET 's3cr3t''value', REGION 'us-east-1', USE_SSL true, URL_STYLE 'vhost') |
| `CON-152` | PASS | CREATE OR REPLACE SECRET prama_store (TYPE s3, PROVIDER credential_chain, ENDPOINT 'minio:9000', REGION 'eu-west-1', USE_SSL true, URL_STYLE 'vhost') |
| `CON-153` | FAIL | {'/mnt/lake/positions': 'UNCAUGHT ParserException: Parser Error: syntax error at or near ","\n\nLINE 1: CREATE OR REPLACE SECRET prama_store (TYPE , PROVIDER credential_chain, ENDPOINT \'127.0.0.1:1\', REGION...\n                                                   ^', 'http://x/y': "UNCAUGHT InvalidInputException: Invalid Input Error: Secret provider 'credential_chain' not found for type 'http'", '… |
| `CON-154` | PASS | results={'access denied case': 'unauthorised', '403 case': 'unauthorised', 'sigmismatch': 'unauthorised', 'no bucket': 'misconfigured', 'conn refused': 'unreachable'} (also: exception mentioning an object key containing 'signature' -> _is_denied=True, i.e. would be misclassified as an access-denied error) |
| `CON-155` | PASS | detail='first line of the error' len=23 |
| `CON-156` | PASS | n_rows=40000 pages=400 truncated=False |
| `CON-157` | PASS | pages_read=3 n_rows=30 n_distinct_ids=30 |
| `CON-158` | PASS | pages_read=10 truncated=True n_rows=100 |
| `CON-159` | PASS | n_rows=50 truncated=False |
| `CON-160` | PASS | n_rows=25 urls_requested=['/pageparam', '/pageparam?p=2', '/pageparam?p=3', '/pageparam?p=4', '/pageparam?p=5'] all_next_urls_carry_p_param=True |
| `CON-161` | PASS | waited_seconds=64.0 (expected ~64) wall_elapsed=64.1s n_rows=1 |
| `CON-162` | PASS | [CONNECT.UNREACHABLE] http://127.0.0.1:38545/ratelimit_forever asked us to slow down five times running \| Next: The server is rate-limiting harder than this read can absorb; we waited 0s in total. Read less, or read it less often. \| Context: url='http://127.0.0.1:38545/ratelimit_forever' remedy=The server is rate-limiting harder than this read can absorb; we waited 0s in total. Read less, or rea… |
| `CON-163` | PASS | health={200: 'healthy', 401: 'unauthorised', 403: 'unauthorised', 404: 'healthy', 500: 'degraded', 503: 'degraded'} read_401=UnauthorisedError read_404=UnreachableError |
| `CON-164` | PASS | default_header={'Accept': 'application/json', 'Authorization': 'Bearer abc123'} custom_header_empty_scheme={'Accept': 'application/json', 'X-Api-Key': 'abc123'} token_leaked_into_url=False |
| `CON-165` | PASS | code=CONNECT.NO_PREDICATE http_calls_made=0 |
| `CON-166` | PASS | amount.comment=arrives as double and as string across the sample settled_at.nullable=True |
| `CON-167` | FAIL | ArrowInvalid: Could not convert 'STRINGVAL' with type str: tried to convert to double (read() raised on a mixed-type column instead of producing a batch) |
| `CON-168` | PASS | legs values=['[{"qty": 1, "side": "buy"}, {"qty": 2, "side": "sell"}]', '[{"qty": 1, "side": "buy"}, {"qty": 2, "side": "sell"}]'] |
| `CON-169` | PASS | code=CONNECT.NOT_JSON msg=[CONNECT.NOT_JSON] http://127.0.0.1:38545/notjson did not return JSON \| Next: This connector reads JSON. If the endpoint serves something else, it is a different source kind. \| Context: url='http://127.0.0.1:38545/notjson' |
| `CON-170` | PASS | {'bare_list': [{'a': 1}, {'b': 2}], 'bare_dict': [{'a': 1}], 'nested_path': [{'x': 1}], 'missing_path': [{'data': {'items': [{'x': 1}]}}], 'non_dicts': [], 'null_body': []} |
| `CON-171` | PASS | n_rows=1000000 (expected 1,000,000) peak_rss_before_kb=92108 peak_rss_after_kb=730464 delta_mb=623.4 -- _collect materialises the whole 1000-page result as a Python list before read() batches it out, confirming the streaming claim applies only to the batches handed to the caller, not to what _collect itself holds |
| `CON-172` | FAIL | raised CONNECT.NO_PREDICATE instead of returning rows: [CONNECT.NO_PREDICATE] MongoConnector cannot restrict a read to part of an object \| Next: Profile this object whole, or reach it through a connector that can filter. Reading everything and calling it one segment would attribute the whole object's data to that segment. \| Context: connector='MongoConnector', predicate="d = '2026-04-01'" (see C… |
| `CON-173` | PASS | rows_read=50000 (of 50,000, a stand-in for the catalogue's 5,000,000 given time budget); time to first batch=0.160s vs total read time=0.186s (first_batch==total confirms nothing is yielded until the whole cursor is drained into a list, exactly as the code shows: `[document async for document in cursor]` with limit=0); peak_rss_before_kb=73136 after_kb=99908 |
| `CON-174` | PASS | type=Decimal value=Decimal('1953193.464900000000') is_Decimal=True |
| `CON-175` | PASS | notional.comment='arrives as double and as string across 200 sampled document(s)' settled_at.comment='absent from 50 of 200 sampled' settled_at.nullable=True |
| `CON-176` | PASS | last_schema_sample=200 |
| `CON-177` | PASS | sub.type_name=json arr.type_name=json sub_value='{"a": 1, "created": "2026-04-01 00:00:00"}' |
| `CON-178` | PASS | _id.type_name=objectid value='6aa751bdb96018db48b495a8' len=24 |
| `CON-179` | PASS | code=CONNECT.INCOMPLETE remedy=Name the database. A Mongo deployment holds several and Prama will not pick one — an estate declared against the wrong database is worse than one that failed to connect. msg=[CONNECT.INCOMPLETE] a MongoDB source needs a database \| Next: Name the database. A Mongo deployment holds several and Prama will not pick one — an estate declared against the wrong database is … |
| `CON-180` | PASS | health=HealthState.HEALTHY discover()=UnreachableError: The connection worked and the catalogue did not. Usually the role can read documents and not `listCollections`. |
| `CON-181` | FAIL | built_uri='mongodb://alice:p@ss:w/ord@dbhost:27017/?authSource=admin' |
| `CON-182` | PASS | {'DELETE FROM positions': "[CONNECT.ERROR] a control may only run a read-only query \| Next: A control is a check; it has no business writing. Permitted: SELECT, WITH. \| Context: sql='DELETE FROM positions'", 'UPDATE t SET x=1': "[CONNECT.ERROR] a control may only run a read-only query \| Next: A control is a check; it has no business writing. Permitted: SELECT, WITH. \| Context: sql='UPDATE t SE… |
| `CON-183` | PASS | {'two_statements': 'refused', 'trailing_semi': 'SELECT 1', 'double_trailing_semi': 'SELECT 1', 'quoted_semi': 'refused (false positive, as documented)'} |
| `CON-184` | PASS | {"''": '[CONNECT.ERROR] an empty query cannot be run \| Next: This is a compiler defect; the control produced no SQL. \| remedy=This is a compiler defect; the control produced no SQL.', "'   '": '[CONNECT.ERROR] an empty query cannot be run \| Next: This is a compiler defect; the control produced no SQL. \| remedy=This is a compiler defect; the control produced no SQL.', "';'": '[CONNECT.ERROR] an… |
| `CON-185` | PASS | readonly_refusal_ctx_len=120 two_stmt_refusal_ctx_len=120 |
| `CON-186` | PASS | query.py._sqlite path: n=1; SqliteConnector.run_metric_query path: n=1 |
| `CON-187` | PASS | REGEXP(x) for NULL rows returns: {None} (expected {None}); if it wrongly returned False for all 7 nulls, that would add 7 to a violation count that otherwise matches DuckDB's 4 (4, the non-matching 'notvalid' rows) -- confirmed NULL now correctly propagates as NULL, not False |
| `CON-188` | PASS | count=1 (expected 1 -- SQLite calls regexp(pattern, value)) |
| `CON-189` | PASS | {'missing_file': "[INPUT.INVALID] there is no file at /no/such/file.db \| Next: Check the path. A control cannot examine data that is not there. \| Context: path='/no/such/file.db'", 'unknown_engine': "[INPUT.INVALID] no file-backed executor for 'oracle' \| Next: Available: duckdb, sqlite. For anything else, supply your own executor — the runner's whole interface to a source is a callable that tak… |
| `CON-190` | PASS | {'filesystem': 'refused: This source has no query engine, so its controls are evaluated locally over the rows `read` yields. Asking for an executor here would fail on the first control rather than now.', 'rest': 'refused: This source has no query engine, so its controls are evaluated locally over the rows `read` yields. Asking for an executor here would fail on the first control rather than now.',… |
| `CON-191` | PASS | {'p1': (datetime.date(2026, 3, 31), 1, 'POS_EXTRACT_20260331_1.csv'), 'p2': (datetime.date(2026, 3, 31), 'positions.2026-03-31.parquet'), 'p3': (datetime.date(2026, 3, 31), datetime.time(6, 30), 'trades_20260331_????.json.gz')} |
| `CON-192` | PASS | {'POS_{YYYYMDD}.csv': "ok=True msg=[INPUT.INVALID] unrecognised token(s) in the filename pattern: {YYYYMDD} \| Next: Use one of {YYYYMMDD}, {YYYY-MM-DD}, {DDMMYYYY}, {YYYY}, {YY}, {MM}, {DD}, {HH}, {mm}, {SEQ}, {ANY} — or {ANY} for a part of the name nobody controls. Left as literal text, this pattern would match no file at all and the feed would report a missing delivery every day. \| Context: pa… |
| `CON-193` | PASS | day_no_month=refused: [INPUT.INVALID] the filename pattern has a day token but no month token \| Next: Add {MM}, or use {YYYYMMDD} if the whole date is one field. A day without a month cannot identify a business date. \| Context: pattern='f_{YYYY}{DD}.csv'; month_only_parsed=2026-04-01 |
| `CON-194` | PASS | {"''": True, "'   '": True} |
| `CON-195` | PASS | parsed_seq=7 render7=POS_20260331_007.csv render1=POS_20260331_001.csv |
| `CON-196` | PASS | unpadded=None overpadded=None |
| `CON-197` | PASS | star_matches=True star_excludes_slash=True dot_escaped=True |
| `CON-198` | PASS | matches=True |
| `CON-199` | PASS | n1=ParsedName(filename='POS_20261332.csv', business_date=None, delivery_time=None, sequence=None) n2=ParsedName(filename='POS_20260229.csv', business_date=None, delivery_time=None, sequence=None) n3=ParsedName(filename='POS_00000000.csv', business_date=None, delivery_time=None, sequence=None) |
| `CON-200` | PASS | dmy=2026-03-31 ymd=2026-03-31 ymd_of_dmy_string=None |
| `CON-201` | PASS | century2000=2026-03-31 century1900=1926-03-31 century_param_used_in_from_dict=False |
| `CON-202` | PASS | [INPUT.INVALID] feed 'f' expects 3 files a day but its filename pattern has no sequence token \| Next: Add {SEQ} (or {SEQ:3} for a padded one) to the pattern, so the deliveries can be told apart and a missing one identified. \| Context: feed='f', pattern='POS_{YYYYMMDD}.csv' remedy=Add {SEQ} (or {SEQ:3} for a padded one) to the pattern, so the deliveries can be told apart and a missing one identif… |
| `CON-203` | PASS | {0: True, -1: True} |
| `CON-204` | PASS | [INPUT.INVALID] feed 'f' declares an earliest time but no due time \| Next: State when the file is due; an open-ended window cannot be late. \| Context: feed='f' |
| `CON-205` | PASS | can_detect_missing={'both': True, 'deadline_only': False, 'date_only': False, 'neither': False} findings={'both': ['missing'], 'deadline_only': [], 'date_only': [], 'neither': []} |
| `CON-206` | FAIL | to_dict keys=['calendar', 'can_detect_missing', 'due_by', 'duplicates', 'files_per_day', 'landing_path', 'lateness_grace_seconds', 'name', 'pattern', 'trailer_declared']; lost on round-trip: ['earliest: 05:00:00 -> None', 'trailer.total_field: 2 -> None', 'trailer.amount_field: 9 -> None', 'trailer.header_lines: 1 -> 0', "trailer.total_tolerance: '0.01' -> '0'"] |
| `CON-207` | PASS | 06:40=ArrivalStatus.ON_TIME 06:50=ArrivalStatus.LATE lateness_seconds=1200.0 |
| `CON-208` | PASS | {(6, 0): [], (6, 45): [], (6, 46): ['missing']} |
| `CON-209` | PASS | missing_findings=[('POS_20260401_2.csv', '2 of 3 deliveries have not arrived')] |
| `CON-210` | PASS | statuses=['on_time', 'on_time', 'out_of_sequence'] |
| `CON-211` | PASS | a=identical bytes to the earlier delivery: a resend, not a restatement b=same name, different content: this is a restatement, not a resend c=a second delivery for 2026-04-01 |
| `CON-212` | PASS | statuses=['on_time', 'on_time'] (both files judged for timeliness, no duplicate finding emitted for the second) |
| `CON-213` | PASS | unexpected=[(datetime.date(2026, 4, 3), 'minor', 'confirm the calendar: either the feed now runs on this day, or the sender used the wrong date')] |
| `CON-214` | PASS | {0: 'truncated', 1023: 'truncated', 1024: 'late'} |
| `CON-215` | PASS | {'on_time': ('info', 'nothing'), 'early': ('info', 'confirm with the sender that the schedule changed'), 'late': ('major', 'chase the sender; downstream controls will run on stale data'), 'missing': ('critical', 'chase the sender before the downstream run'), 'duplicate': ('major', 'decide whether this supersedes the earlier delivery or is a resend'), 'out_of_sequence': ('major', 'check whether an … |
| `CON-216` | PASS | s1_worst=critical s1_n_findings=2 s2_worst=None |
| `CON-217` | FAIL | status=IntegrityStatus.COUNT_MISMATCH shortfall=3 message='f.csv: trailer declares 1,000 records, 997 arrived (+3)' |
| `CON-218` | PASS | plain=IntegrityStatus.MATCHED counts_itself=IntegrityStatus.MATCHED |
| `CON-219` | FAIL | status=IntegrityStatus.TOTAL_MISMATCH observed_count=103 (trailer line index would be 103; data rows counted=100) |
| `CON-220` | PASS | tol0=IntegrityStatus.MATCHED/100000.0 tol0.01=IntegrityStatus.MATCHED/100000.0 (Decimal(0.1)*1,000,000 == Decimal(100000.00) exactly) |
| `CON-221` | PASS | amount_field=8: observed_total=1045 (expected 1045); amount_field unset (defaults to total_field=2): observed_total=55 |
| `CON-222` | PASS | {'non_numeric_count': (<IntegrityStatus.TRAILER_UNREADABLE: 'trailer_unreadable'>, "field 1 of the trailer is not a number: 'TRLR,abc'"), 'too_few_fields': (<IntegrityStatus.TRAILER_UNREADABLE: 'trailer_unreadable'>, "field 1 of the trailer is not a number: 'TRLR'"), 'non_numeric_total': (<IntegrityStatus.TRAILER_UNREADABLE: 'trailer_unreadable'>, 'field 2 of the trailer is not a number')} |
| `CON-223` | PASS | raised InvalidOperation: [<class 'decimal.ConversionSyntax'>] -- confirms Decimal(spec.total_tolerance) is NOT wrapped in a try/except (only the declared-total parse is), so a malformed tolerance crashes the nightly check rather than being refused at declaration time, exactly as the catalogue's Why anticipates |
| `CON-224` | PASS | status=IntegrityStatus.MATCHED detail='no trailer declared for this feed' |
| `CON-225` | PASS | no_trailer_line=IntegrityStatus.TRAILER_MISSING/"no line beginning 'TRLR' was found" data_row_with_marker_prefix_before_real_trailer=IntegrityStatus.MATCHED |
| `CON-226` | PASS | four_of_five=IntegrityStatus.MANIFEST_INCOMPLETE/('f5.csv',)/5/4; all_five=IntegrityStatus.MATCHED; five_plus_extra=IntegrityStatus.MATCHED |
| `PRO-001` | PASS | in-process: row0=7810343412746689742 row3=14393831650195416369; subprocess: ['7810343412746689742', '14393831650195416369'] |
| `PRO-002` | PASS | estimate(154)=1 after add(154,1) then add(151,1_000_000) |
| `PRO-003` | PASS | n_distinct=171 over_bound_violations=0 (allowed ~5) bound=132.7 |
| `PRO-004` | PASS | underestimate_violations=0 (expected 0) |
| `PRO-005` | PASS | estimate(None)=0 total=0 |
| `PRO-006` | PASS | cannot merge CountMin sketches of different shape |
| `PRO-007` | PASS | tables_equal=True totals_equal=True (20000 vs 20000) |
| `PRO-008` | PASS | std_errors={4: 0.26, 14: 0.008125, 18: 0.00203125} (~0.26,~0.0163,~0.002) 1M-distinct: est=987629 rel_err=0.0124 3xSE=0.0244 |
| `PRO-009` | FAIL | {1: 1, 2: 2, 10: 10, 100: 100, 1000: 996} |
| `PRO-010` | PASS | estimate=0 len=0 |
| `PRO-011` | PASS | estimate=0 |
| `PRO-012` | PASS | {3: 'ValueError', 4: 'OK', 18: 'OK', 19: 'ValueError'} |
| `PRO-013` | PASS | cannot merge HyperLogLogs of different precision |
| `PRO-014` | PASS | merged_est=789 union_est=789 a_unmutated=True |
| `PRO-015` | PASS | distinct_estimate=5 topk_tracked=3 (values: int/float/Decimal/str/bool all treated as distinct by HyperLogLog since hash is over repr(); TopK's fast path collides int/bool) |
| `PRO-016` | PASS | quantile(0.5)=4.0 (expected ~4.5, not 9.0) |
| `PRO-017` | PASS | rel_errors: p50=0.0118 p99=0.0005 p999=0.0011 (tails should be no worse than median) |
| `PRO-018` | PASS | quantile=None minimum=None maximum=None |
| `PRO-019` | PASS | {-0.1: 'ValueError', 1.1: 'ValueError'} q(0)=1.0==min=1.0 q(1)=3.0==max=3.0 |
| `PRO-020` | PASS | count=2 min=1.0 max=2.0 |
| `PRO-021` | FAIL | diffs={0.01: 0.2652990689004282, 0.5: 3.7301984151732017, 0.99: 0.28311600301768447} count=100000 min_match=True max_match=True a_still_queryable_after_merge=True |
| `PRO-022` | PASS | true_top20_counts=[1000, 1000, 999, 999, 992]... got=[1000, 1000, 999, 999, 992]... match=True |
| `PRO-023` | PASS | order1=[('a', 10), ('b', 10), ('c', 10), ('d', 10), ('e', 10)] order2=[('a', 10), ('b', 10), ('c', 10), ('d', 10), ('e', 10)] identical=True |
| `PRO-024` | PASS | tracked=505 (capacity=1000) |
| `PRO-025` | PASS | reported=999001 true=999001 understatement=0 |
| `PRO-026` | PASS | merged.tracked=998 (expected <=1000; merge() builds TopK(self._k) with DEFAULT capacity_multiple=50, same as operands here so bound coincidentally holds -- would widen if operands used a smaller multiple, per the catalogue's Why) |
| `PRO-027` | PASS | tracked=2 keys=['[1, 2, 3]', "{'a': 1}"] |
| `PRO-028` | PASS | {'name': 'c', 'type': 'VARCHAR', 'rows': 0, 'nulls': 0, 'null_rate': 0.0, 'distinct_estimate': 0, 'distinct_ratio': 0.0, 'key_candidate': False, 'constant': False, 'top_values': [], 'numeric': None, 'strings': None} |
| `PRO-029` | PASS | rows=1000 nulls=1000 distinct=0 key_cand=False empty_columns=('c',) |
| `PRO-030` | PASS | ratio=1.0 key=True const=True stddev=0.0 quantiles={'p1': 42.0, 'p5': 42.0, 'p25': 42.0, 'p50': 42.0, 'p75': 42.0, 'p95': 42.0, 'p99': 42.0} dominant=(42, 1.0) |
| `PRO-031` | PASS | const=True key=False dominant=('N', 1.0) |
| `PRO-032` | PASS | {0.899: None, 0.9: ('V', 0.9), 0.901: ('V', 0.901)} |
| `PRO-033` | PASS | is_key_candidate True in 50/50 trials |
| `PRO-034` | PASS | is_key_candidate=False nulls=1 |
| `PRO-035` | PASS | nulls=1 mean=2.0 quantiles={'p1': 1.0, 'p5': 1.0, 'p25': 1.0, 'p50': 1.0, 'p75': 3.0, 'p95': 3.0, 'p99': 3.0} |
| `PRO-036` | PASS | numeric=None strings=None distinct=2 top_values=((False, 500), (True, 500)) |
| `PRO-037` | PASS | aware: min=1775001600.0 max=1777334400.0; naive: min=1775016000.0 max=1777348800.0; datetime.timestamp() on a naive value applies the HOST's local timezone (naive[0].timestamp()=1775016000.0, naive[0]=2026-04-01 00:00:00) -- confirmed host-dependent: the same naive datetime profiles to a different numeric value on a machine in a different timezone |
| `PRO-038` | PASS | numeric=None strings=None (Decimal falls through both _add_numeric and _add_string; no summary captured for money columns) |
| `PRO-039` | PASS | top_masks=(('A', 1), ('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA', 1)) masked_lengths={64, 1} |
| `PRO-040` | PASS | masks=['AA9999999999', 'aaa-999', '£9.99', 'ÄÖÜ'] expected={'AA9999999999', 'aaa-999', 'ÄÖÜ', '£9.99'} |
| `PRO-041` | PASS | nulls=1 blank_count=3 min_length=0 |
| `PRO-042` | PASS | True False False False |
| `PRO-043` | PASS | stddev=0.0 |
| `PRO-044` | PASS | [INPUT.INVALID] cannot merge a profile of 'quantity' into one of 'notional' \| Next: Merge accumulators column by column, matching on name. \| Context: from='quantity', into='notional' remedy=Merge accumulators column by column, matching on name. |
| `PRO-045` | PASS | type_name=TEXT\|VARCHAR |
| `PRO-046` | PASS | merged rows=1000/1000 min_len=2/2 max_len=4/4 mean_len=3.89/3.89 |
| `PRO-047` | PASS | 3 call sites reference _frequency (construction, add, merge -- none in profile()) |
| `PRO-048` | PASS | {'GB00': {'digit', 'upper'}, 'abc': {'lower'}, 'a-b': {'punctuation', 'lower'}, 'naïve': {'non_ascii', 'lower'}, '': set(), '  ': {'punctuation'}} |
| `PRO-049` | PASS | {'computed_at': datetime.datetime(2026, 9, 14, 1, 45, 47, 192896, tzinfo=datetime.timezone.utc), 'snapshot': {'kind': 'file_digest', 'id': '24576:1789350347172569961:6', 'captured_at': datetime.datetime(2026, 9, 14, 1, 45, 47, 174861, tzinfo=datetime.timezone.utc), 'exact': True, 'detail': {'page_count': 6, 'object': 't'}}, 'sampling': 'head sample of 100 rows', 'representative': False, 'rows_exam… |
| `PRO-050` | PASS | {'full': 'measured over all 1,000 rows', 'full_trunc': 'estimated from 1,000 sampled rows (full scan)', 'head': 'read the first 1,000 rows only — indicative of shape, not of any rate', 'sys': 'estimated from 1,000 sampled rows (systematic sample at 1%)'} |
| `PRO-051` | PASS | truncated=True is_complete=False rows_examined=1000 log='profiling t stopped at the 1000-row budget' |
| `PRO-052` | PASS | rows_examined=10000 (expected 10000, the first full batch, since the check runs after the batch is consumed) |
| `PRO-053` | PASS | column_order=['a', 'b', 'c'] (schema order a,b then extra c appended) |
| `PRO-054` | PASS | type_name=NUMERIC(38,12) |
| `PRO-055` | PASS | snapshot_calls=0 provenance.snapshot=None |
| `PRO-056` | PASS | n_profiles=4 log="could not profile t1: cannot read ('t1',)" |
| `PRO-057` | PASS | profiled=[('t1',), ('t5',), ('t3',)] (expected 3 largest, in discover()'s own order: t1(900) t5(800) t3(700)) |
| `PRO-058` | FAIL | {None: (<SamplingStrategy.FULL: 'full'>, None, 0), 0: (<SamplingStrategy.FULL: 'full'>, None, 0), 5000000: (<SamplingStrategy.FULL: 'full'>, None, 0), 5000001: (<SamplingStrategy.SYSTEMATIC: 'systematic'>, 0.199999960000008, 1), 100000000: (<SamplingStrategy.SYSTEMATIC: 'systematic'>, 0.01, 1)} |
| `PRO-059` | PASS | seed=1 |
| `PRO-060` | PASS | {0: 1.0, -1: 1.0, 1: 1.0, 3: 1.0, 10000: 0.0003, 1000000: 3e-06, '0.9conf': 0.00022999999999999998} |
| `PRO-061` | PASS | TypeError: from_rows() missing 1 required keyword-only argument: 'plan' |
| `PRO-062` | PASS | a.rows=2 b.rows=1 b.nulls=0 b.null_rate=0.0 rows_examined=2 |
| `PRO-063` | FAIL | resolves=False in___all__=False __all__=['DEFAULT_MUTABLE_DAYS', 'MAX_SEGMENTS', 'ColumnAccumulator', 'ColumnProfile', 'CountMin', 'DatasetProfile', 'HyperLogLog', 'IncrementalPlan', 'IncrementalPlanner', 'NumericSummary', 'ProfileProvenance', 'Profiler', 'Segment', 'SegmentAccumulation', 'SegmentDecision', 'SegmentGrain', 'SegmentLedger', 'SegmentRecord', 'SegmentState', 'Segmentation', 'Segmente… |
| `PRO-064` | PASS | keys=['2026-03-30', '2026-03-31', '2026-04-01'] single_day_count=1 |
| `PRO-065` | PASS | keys=['2026-11', '2026-12', '2027-01', '2027-02'] dec.upper=2027-01-01 |
| `PRO-066` | PASS | [INPUT.INVALID] the segmentation range ends before it begins \| Next: Give the earlier date first. \| Context: end='2026-03-01', start='2026-04-01' remedy=Give the earlier date first. |
| `PRO-067` | PASS | 2000_days_ok=True 2001_days=refused: {'segments': 2001, 'maximum': 2000} 2001_values=refused: {'segments': 2001, 'maximum': 2000} |
| `PRO-068` | PASS | {'VALUE': True, 'NONE': True} |
| `PRO-069` | PASS | day_no_column=refused, remedy=Name the column — usually the business date, or whatever identifies the batch a row arrived in. none_no_column=OK |
| `PRO-070` | PASS | n=4 keys=['3', '3', 'APAC', 'EMEA'] three_segments_values=[3, '3'] |
| `PRO-071` | PASS | "desk""name" = 'O''Brien Desk' |
| `PRO-072` | PASS | {'none': 'NULL', 'true': '1', 'false': '0', 'int': '7', 'float': '7.5', 'nan': 'nan', 'inf': 'inf', 'date': "'2026-04-01'", 'datetime': "'2026-04-01T06:30:00'", 'str': "'x'"} |
| `PRO-073` | PASS | "c" >= NULL AND "c" < NULL |
| `PRO-074` | PASS | code=CONNECT.NO_PREDICATE |
| `PRO-075` | PASS | [INPUT.INVALID] a segmented profile needs at least one segment \| Next: Declare the segmentation — usually by business date — or profile the dataset whole. \| Context: object='t' remedy=Declare the segmentation — usually by business date — or profile the dataset whole. |
| `PRO-076` | PASS | max_simultaneous_reads=4 |
| `PRO-077` | PASS | RuntimeError propagated: read failed for "c" = '3'; ledger records after failed refresh=0 (expected 0 -- asyncio.gather with no return_exceptions loses the nine that worked) |
| `PRO-078` | PASS | folded.computed_at=2026-01-01 00:00:00+00:00 (expected oldest=2026-01-01 00:00:00+00:00) |
| `PRO-079` | PASS | folded.plan.predicate='' |
| `PRO-080` | PASS | folded.rows=20000/20000 folded.distinct=16301 whole.distinct=16301 |
| `PRO-081` | PASS | column 'a' (present every segment): rows=1200 (12x100=1200); column 'b' (present only in segments 6-11): rows=600 (6x100=600, a SHORT denominator vs a's 1200) null_rate=0.1 (60/600=0.1) -- recorded as the catalogue asks: two columns in the same folded profile have different row denominators |
| `PRO-082` | PASS | [('9', 1.0)] |
| `PRO-083` | PASS | {0: [], 1: [], 2: [], 3: [('0', 0.0), ('2', 2.0)]} |
| `PRO-084` | PASS | compare('b')=[('1', 0.5), ('2', None)] (segment 2 has no 'b' column -> None, not 0.0) |
| `PRO-085` | PASS | states=['new', 'new', 'new', 'new', 'new'] saved_fraction=0.0 render='Reading all 5 segments — never profiled.' |
| `PRO-086` | PASS | wall_clock_states=['unverifiable', 'unverifiable', 'unverifiable'] none_states=['unverifiable', 'unverifiable', 'unverifiable'] |
| `PRO-087` | PASS | states=['settled', 'settled', 'settled', 'settled', 'settled'] saved_fraction=1.0 |
| `PRO-088` | PASS | segments_CHANGED=400 of 400 (object-level snapshot moved from A to B; EVERY segment invalidated, even the 399 that did not themselves change -- confirms the ledger's object-level granularity means one write anywhere re-reads the whole table) |
| `PRO-089` | PASS | {'d6': 'settled', 'd7': 'mutable', 'd8': 'mutable', 'd9': 'mutable', 'd10': 'mutable'} (cutoff=2026-04-07; d6 upper=04-07 SETTLED, d7 upper=04-08 MUTABLE) |
| `PRO-090` | PASS | states=['mutable', 'mutable', 'mutable'] |
| `PRO-091` | PASS | state=changed |
| `PRO-092` | PASS | a_states=['new', 'new', 'new'] b_states=['settled', 'settled', 'settled'] |
| `PRO-093` | PASS | states=['new', 'mutable', 'mutable', 'mutable', 'mutable'] render='Reading all 5 segments — never profiled.' (attributes 'never profiled' -- segment 1's reason -- to all 5, even though 4 are actually mutable) |
| `PRO-094` | PASS | saved_fraction=0.0 render='Nothing to examine: the segmentation produced no segments.' |
| `PRO-095` | PASS | snapshot_id=SNAP1 snapshot_exact=True sampling='systematic sample at 1%' representative=True rows_examined=200 |
| `PRO-096` | PASS | metric_names=['blank_count', 'distinct_count', 'distinct_ratio', 'duration_seconds', 'max', 'max_length', 'mean', 'mean_length', 'min', 'min_length', 'null_count', 'null_rate', 'quantile_p1', 'quantile_p25', 'quantile_p5', 'quantile_p50', 'quantile_p75', 'quantile_p95', 'quantile_p99', 'row_count', 'stddev'] |
| `PRO-097` | PASS | metric_names=['blank_count', 'distinct_count', 'distinct_ratio', 'duration_seconds', 'max', 'max_length', 'mean', 'mean_length', 'min', 'null_count', 'null_rate', 'row_count'] |
| `PRO-098` | PASS | {'null_count': 100.0, 'null_rate': 1.0, 'distinct_count': 0.0, 'distinct_ratio': 0.0} |
| `PRO-099` | FAIL | n_candidates=1 suppressed={'generic_name': 3} |
| `PRO-100` | PASS | {'generic_name': 412} |
| `PRO-101` | PASS | {'id': True, 'ID': True, 'Id': True, 'i-d': True, 'account_id': False, 'id2': False, '_id': False} |
| `PRO-102` | PASS | {'one_0.8': 0.8, 'two_0.35': 0.5775, '0.8_and_0.35': 0.87} |
| `PRO-103` | PASS | {1.0: 0.95, 2.0: 0.95, -1.0: 0.0} |
| `PRO-104` | PASS | single='a → b may be references: records here point at records there, matched on x = y. This rests on a single signal — both have x — which is a question rather than a finding' double='a → b may be references: records here point at records there, matched on x = y. both have x; values contained' |
| `PRO-105` | PASS | positions → accounts may be references: records here point at records there, matched on account_no. This rests on a single signal — contained — which is a question rather than a finding |
| `PRO-106` | PASS | 2_distinctive_cols->None: True; 3cols/50%overlap->None: True; 3cols/75%overlap->Evidence(strength=0.725, expected 0.725) |
| `PRO-107` | PASS | co_access=40/200 -> strength=0.6000000000000001 (expected 0.6); co_access=0/200 -> None; co_access=40/0 -> None |
| `PRO-108` | PASS | 1 reference(s): ['/home/ashutosh/PycharmProjects/prama/src/prama/discover/relationships.py:83:    KEY_OVERLAP = "key_overlap"'] |
| `PRO-109` | PASS | order1=[('m', 'n'), ('a', 'a'), ('a', 'z'), ('z', 'a')] order2=[('m', 'n'), ('a', 'a'), ('a', 'z'), ('z', 'a')] identical=True |
| `EXE-001` | PASS | run row survived the rollback=True; status=running and surfaced by unfinished()=True |
| `EXE-002` | PASS | execute_all() with pending uncommitted work on the same uow did not deadlock; the pending tenant create was committed too (found after=True) |
| `EXE-003` | PASS | status=complete finished_at_set=True detail_matches=True detail='1 control(s), 1 pass' |
| `EXE-004` | PASS | status=complete detail='1 control(s), 1 error, 1 could not be executed at all' |
| `EXE-005` | PASS | RuntimeError propagated: ledger append failed; unfinished runs after=1 |
| `EXE-006` | PASS | n_outcomes=1 ran_control_id_matches_active=True |
| `EXE-007` | PASS | n_outcomes=5 bad_verdict=error bad_detail="could not be compiled: [INPUT.INVALID] there is no semantic type called 'not_a_real_validator' \| Next: Register a validator for it, or use a known type. An unresolved type would compile to a check that passes everything, which is worse than no control because it looks like coverage. \| Context: semantic_type='not_a_real_validator'" others_passed=4 |
| `EXE-008` | PASS | n_outcomes=5 bad_detail='ConnectionError: source unreachable' others_ran=4 |
| `EXE-009` | PASS | verdict=fail metrics={'scanned_rows': 500.0, 'violating_rows': 5.0} |
| `EXE-010` | PASS | metrics={'booking_year': 4051.0, 'scanned_rows': 200.0, 'violating_rows': 3.0}; 'booking_year' appears as a metric=True (numeric segment key value 4051.0 recorded as though it were a measurement) |
| `EXE-011` | PASS | 1-row segmented control: verdict=pass metrics={'scanned_rows': 100.0, 'violating_rows': 0.0} (guard is segment_by and len(rows)>1, so a single-segment result uses the FLAT judge() path) |
| `EXE-012` | PASS | metrics={'scanned_rows': 100.0, 'distinct_keys': 100.0, 'duplicate_rows': 0.0, 'violating_rows': 0.0} (violating_rows present=True) |
| `EXE-013` | PASS | executor returning [] -> verdict=indeterminate metrics={} (recorded, per the catalogue's 'record the verdict') |
| `EXE-014` | PASS | metrics={'scanned_rows': 10.0, 'violating_rows': 0.0} ('passed' bool excluded=True) |
| `EXE-015` | PASS | verdict=indeterminate detail='the query applied a screen rather than the exact test, so the violation count is a lower bound; the residual (lei on lei) has not been run, and a pass cannot be reported from a screen alone' |
| `EXE-016` | PASS | verdict=fail detail='the query applied a screen rather than the exact test, so 11 is a LOWER BOUND on the violations; the residual (lei on lei) has not been run and the true count may be higher' |
| `EXE-017` | PASS | thresholds=['metric=violating_rows, op=<=, relative_to=, value=0.0', 'metric=violating_rows, op=<=, relative_to=, value=5.0'] |
| `EXE-018` | FAIL | record.snapshot.kind='wall_clock' identifier='2026-09-14T01:45:26.667168+00:00' -- literal 'wall_clock' written regardless of engine (here engine='sqlite', which has an exact FILE_DIGEST snapshot available via SqliteConnector.snapshot(), never consulted) |
| `EXE-019` | FAIL | record.coverage='full' -- literal 'full' written unconditionally, with no connection to the actual SamplePlan/watermark scope that was read |
| `EXE-020` | PASS | sampler_called=0 times for an all-passing run; passing records: digest/count all empty=True |
| `EXE-021` | PASS | sample=None: verdict=fail samples_digest='' |
| `EXE-022` | PASS | verdict=fail digest='' log='samples could not be collected: cannot reach sample rows' |
| `EXE-023` | PASS | after samples.put raised inside execute_all's transaction: records visible afterward=0 (expected 0 -- neither record nor samples survive) |
| `EXE-024` | PASS | n_outcomes=10 n_skipped=30 describe='10 control(s), 10 pass, 30 not due' |
| `EXE-025` | PASS | datasets=None -> 40 outcomes; datasets=set() -> 0 outcomes, 40 skipped |
| `EXE-026` | PASS | unschedulable=1 describe='nothing was due, 1 not due, 1 with a schedule that cannot be read, which will never run until it is fixed' |
| `EXE-027` | PASS | respect_schedule=False: 5 ran, 0 skipped; respect_schedule=True (just ran daily): 0 ran |
| `EXE-028` | PASS | {'2026-04-01T06:30:00Z': (True, datetime.datetime(2026, 4, 1, 6, 30, tzinfo=datetime.timezone.utc)), '2026-04-01T06:30:00+00:00': (True, datetime.datetime(2026, 4, 1, 6, 30, tzinfo=datetime.timezone.utc)), '2026-04-01T06:30:00': (True, datetime.datetime(2026, 4, 1, 6, 30, tzinfo=datetime.timezone.utc)), '2026-04-01T06:30:00+02:00': (True, datetime.datetime(2026, 4, 1, 6, 30, tzinfo=datetime.timezo… |
| `EXE-029` | PASS | d1='no controls were live, so nothing ran' d2='nothing was due, 1 not due' d3='2 control(s), 2 error, 2 could not be executed at all' d4='nothing was due, 3 not due, 1 with a schedule that cannot be read, which will never run until it is fixed' |
| `EXE-030` | PASS | non_none=1 none=9 |
| `EXE-031` | PASS | c2=None logged_at_warning_or_above='' |
| `EXE-032` | PASS | {0.5: ('ValueError', 'renew_interval must be shorter than ttl, or a lease expires between renewals'), 1.0: ('ValueError', 'renew_interval must be shorter than ttl, or a lease expires between renewals'), 1.5: ('OK', 'lease renew_interval (1.0s) leaves no room for a missed renewal within ttl (1.5s); consider ttl >= 3x renew_interval\n'), 3.0: ('OK', ''), 60.0: ('OK', '')} |
| `EXE-033` | PASS | tokens=[1, 2, 3, 4, 5] |
| `EXE-034` | PASS | code=CONCURRENCY.STALE_WRITE msg=[CONCURRENCY.STALE_WRITE] w2 tried to record work on r1 with token 6, and token 7 has already written \| Next: Discard the result. Another worker took this resource while this one was stalled and has already done the work; recording it now would put a verdict computed from older data on the record, with a timestamp saying otherwise. \| Context: highest=7, resource=… |
| `EXE-035` | PASS | second accept() of the same token 7 succeeded (comparison is <, not <=; permits a legitimate retry by the current holder, and equally a duplicated record) |
| `EXE-036` | PASS | highest_before=0 accept(token=0)=accepted |
| `EXE-037` | PASS | {6: (False, False), 7: (True, True), 8: (True, True)} |
| `EXE-038` | PASS | LeaseLostError: [CONCURRENCY.LEASE_LOST] lease lost \| Next: x |
| `EXE-039` | PASS | check()=None |
| `EXE-040` | PASS | status=lost records_written=0 log='worker:01M2ESEFRFFTWXJ4P5AHW80NXV finished r1 but no longer holds it; the result is discarded: lease lost' |
| `EXE-041` | PASS | {'done': False, 'skipped': False, 'lost': True, 'failed': False, 'stranded': True} |
| `EXE-042` | PASS | status=stranded unit_back_in_pending=True resource_unclaimed=True lease_released=True |
| `EXE-043` | FAIL | take_one() called 200 times directly against a permanently-failing recorder: 200/200 returned 'stranded', 0/200 returned None; unit still in queue afterward=True. Since take_one() never returns None (confirmed: 0 times), drain()'s `while limit <= 0: outcome = await self.take_one()` -- which only stops on `outcome is None` -- would never terminate; confirmed as a hot loop rather than literally hang… |
| `EXE-044` | PASS | first_drain(limit=3)=3 second_drain(limit=0)=7 |
| `EXE-045` | PASS | zoneless_worker_took=['r-eu', 'r-none', 'r-us'] eu_worker_took=['r-eu'] |
| `EXE-046` | PASS | current_claim_after_releasing_stale_token7=Claim(unit=WorkUnit(resource='r1', dataset='d', zone='', plan_ids=(), priority='normal', cost=1.0), worker_id='w2', fencing_token=8, holder=None) |
| `EXE-047` | PASS | requeue=False -> absent=True; requeue=True -> present=True |
| `EXE-048` | PASS | lengths=[1, 1, 1] |
| `EXE-049` | PASS | 2-tuple->None; 3-tuple->snap1; 4-tuple->(ControlPlan(scope=Scope(dataset='positions_eod', binding='', filter=None, segment_by=(), as_of='', window=''), predicate=Expr(kind='op', name='IS NOT NULL', value=None, args=(Expr(kind='col', name='notional', value=None, args=(), type_name='unknown'),), type_name='boolean'), metrics=(Metric(name='scanned_rows', aggregate=<MetricAggregate.COUNT: 'count'>, ex… |
| `EXE-050` | FAIL | outcome.status=stranded; FleetReport has a 'stranded' property=False; render()='0 unit(s) completed, 0 record(s) written, 0 still queued.'; to_dict()={'done': 0, 'records': 0, 'lost': [], 'failed': [], 'remaining': 0, 'summary': '0 unit(s) completed, 0 record(s) written, 0 still queued.'}; stranded unit mentioned anywhere=False |
| `EXE-051` | PASS | done=18 remaining=2 (2 resources held by an outside holder) |
| `EXE-052` | PASS | n_done=100 n_distinct_resources=100 |
| `EXE-053` | PASS | instance attributes after draining 10 units: ['_clock', '_lease_seconds', '_leases', '_queue', '_recorder', '_runner', '_writer', 'worker_id', 'zone'] (all are fixed config/the shared FencedWriter, no per-unit state accumulated) |
| `EXE-054` | PASS | shared_writer: second_worker_token7_after_token8=lost (expect lost/refused); separate_writers: second_worker_token7=done (expect done/accepted) |
| `EXE-055` | PASS | {0: 'max_bytes must be positive; an unbounded queue is not permitted', -1: 'max_bytes must be positive; an unbounded queue is not permitted'} |
| `EXE-056` | PASS | item_guard: [CONCURRENCY.BACKPRESSURE] queue 'queue' is full: 321/10000 bytes, 3 items \| Next: Slow the producer, add consumers, or build this queue with a larger max_bytes — it is a constructor argument, not a setting. Sustained back-pressure means the sink is the bottleneck, and widening the queue postpones the same problem with more memory held. \| Context: bytes=321, items=3, max_bytes=10000,… |
| `EXE-057` | PASS | first oversized item accepted (len=1, byte_size=10105); second put(): [CONCURRENCY.BACKPRESSURE] queue 'queue' is full: 10105/100 bytes, 1 items \| Next: Slow the producer, add consumers, or build this queue with a larger max_bytes — it is a constructor argument, not a setting. Sustained back-pressure means the sink is the bottleneck, and widening the queue postpones the same problem with more mem… |
| `EXE-058` | PASS | _would_fit(oversized) on a 1-item-full queue = False |
| `EXE-059` | PASS | elapsed=0.050s msg=[CONCURRENCY.BACKPRESSURE] queue 'myq' is full: 195/100 bytes, 1 items \| Next: Slow the producer, add consumers, or build this queue with a larger max_bytes — it is a constructor argument, not a setting. Sustained back-pressure means the sink is the bottleneck, and widening the queue postpones the same problem with more memory held. \| Context: bytes=195, items=1, max_bytes=100… |
| `EXE-060` | PASS | consumer received=['hello'] promptly |
| `EXE-061` | PASS | producers completed: [('p1', 0.10032899398356676), ('p2', 0.10032394400332123)] |
| `EXE-062` | PASS | len=1 byte_size=10041 (before_resize=10041) utilisation=1.0 |
| `EXE-063` | PASS | resize(max_bytes=0) refused=True; resize(max_items=0) accepted, means no ceiling=True |
| `EXE-064` | PASS | {'producer': "[CONCURRENCY.BACKPRESSURE] queue 'queue' is closed \| Next: Stop producing to a closed queue; the consumer has shut down. \| Context: queue='queue'", 'consumer': "[CONCURRENCY.BACKPRESSURE] queue 'queue' is closed and drained \| Next: Stop consuming; the producer has finished. \| Context: queue='queue'"} |
| `EXE-065` | PASS | got=['i0', 'i1', 'i2'] 4th_raised=True drain1=['j0', 'j1', 'j2'] drain2=[] |
| `EXE-066` | PASS | drain() on an empty open queue waited indefinitely (no timeout parameter exists on drain(), confirmed it blocked past 1s) |
| `EXE-067` | PASS | d1_len=3 d2_len=7 byte_size before=1100 mid=770 after=0 |
| `EXE-068` | PASS | {'bytes': 97, 'str1000': 1105, 'dict': 1331, 'list': 236, 'nested': 474, 'raises': 64} |
| `EXE-069` | PASS | snap1.items stayed=1 (captured at 1); snap2.high_water_items=3 >= snap1's 1 |
| `EXE-070` | PASS | {'quarantine': 'STREAM.NO_DEAD_LETTER', 'block': 'STREAM.NO_DEAD_LETTER', 'alert': 'OK', 'tag': 'OK'} |
| `EXE-071` | PASS | order=['dead_letter', 'outcome'] disposition=quarantined |
| `EXE-072` | PASS | n_outcomes=3 halted_because='[STREAM.DEAD_LETTER_FULL] the dead letter would not accept a message, so the pipeline stopped \| Next: Drain or resize it. Continuing would mean discarding the message, which converts a storage problem into permanent loss — and the storage problem is the one somebody can fix.' completed=False describe='HALTED after 3 message(s): [STREAM.DEAD_LETTER_FULL] the dead lette… |
| `EXE-073` | PASS | is_PramaError_subclass=True raised_from__judge=True |
| `EXE-074` | PASS | disposition=unreadable was_kept=True message={} (nothing was actually written anywhere: dead_letter=None, _to_dead_letter returned silently -- was_kept claims True with no evidence kept) |
| `EXE-075` | PASS | disposition=passed violated=('p1',) reaches_consumer=True message_unmodified=True |
| `EXE-076` | PASS | disposition=tagged tag={'violated': ['p1', 'p2'], 'unknown': ['p3']} original_mutated=False |
| `EXE-077` | PASS | tag_field_overwritten={'violated': ['p1'], 'unknown': []} |
| `EXE-078` | PASS | violated=('p17',) |
| `EXE-079` | PASS | violated=('',) |
| `EXE-080` | PASS | p99_ms=0.0023 within(5.0)=True |
| `EXE-081` | PASS | p99_ms=None within=None per_second=None describe='no messages passed through, so nothing was measured' |
| `EXE-082` | PASS | {1: (0.0, 0.0, 0.0, True), 2: (0.0, 1.0, 1.0, True), 100: (0.0, 99.0, 99.0, True)} |
| `EXE-083` | PASS | order=['about_to_poll', 'poll', 'pipeline', 'commit'] |
| `EXE-084` | PASS | halted=True committed=['t[0]@2'] uncommitted_count=7 describe='HALTED after 3 message(s): [STREAM.DEAD_LETTER_FULL] the dead letter would not accept a message, so the pipeline stopped \| Next: Drain or resize it. Continuing would mean discarding the message, which converts a storage problem into permanent loss — and the storage problem is the one somebody can fix.. The rest of the stream was not e… |
| `EXE-085` | PASS | committed=['t0[0]@5', 't1[0]@12'] |
| `EXE-086` | PASS | code=STREAM.TRANSPORT remedy=Nothing was enforced and nothing was committed, so no message was lost. Fix the transport and the batch is redelivered. commits=[] |
| `EXE-087` | PASS | remedy=Enforcement already happened, so these messages will be redelivered and dead-lettered again. Duplicate evidence is a reconciliation problem; losing it is not one anybody can solve afterwards. context={'error': 'RuntimeError', 'messages': '3'} |
| `EXE-088` | PASS | polled=0 committed=() describe='nothing to read' pipeline_called_with=[0] |
| `EXE-089` | PASS | n_reports=1 halted=True |
| `EXE-090` | PASS | n_reports=5 |
| `EXE-091` | PASS | {0: 'STREAM.BATCH_SIZE', -1: 'STREAM.BATCH_SIZE'} |
| `EXE-092` | PASS | committed={('t', 0): 10} |
| `EXE-093` | PASS | {'True': ('STREAM.AUTO_COMMIT', None), 'true': ('STREAM.AUTO_COMMIT', None), '1': ('STREAM.AUTO_COMMIT', None), 'false': ('OK', True), 'None': ('OK', True)} |
| `EXE-094` | BLOCKED | needs a live Kafka broker (offset+1 commit semantics can only be verified against a real broker's actual redelivery behaviour on reconnect with the same group id -- a fake consumer would only test our own mock, not confluent_kafka/the broker's real semantics). Per the hard constraint, a real Kafka broker is explicitly blocked unless the repo ships a fake; none does (tests/execute/test_kafka.py is … |
| `EXE-095` | BLOCKED | needs a live Kafka broker to produce a record genuinely carrying a broker-level error through confluent_kafka's real poll() path; the pure error-handling logic in KafkaTransport.poll() is trivial to reach with a stubbed consumer.poll(), but doing so would only prove the stub behaves as configured, not exercise a real broker error -- and a real Kafka broker is explicitly blocked per the hard constr… |
| `EXE-096` | FAIL | _message() wraps as {'_unreadable': True, '_raw': 'not json {{{', '_why': 'the message body is not JSON'}; isinstance(payload, dict)=True; Pipeline._judge() on this wrapped payload -> disposition=passed (confirmed: the unreadable-body note passes the isinstance(payload, dict) check in _judge, so it is evaluated as an ordinary message against every assertion rather than being dead-lettered as unrea… |
| `EXE-097` | PASS | {'array': {'_raw': [1, 2, 3]}, 'text': {'_raw': 'text'}, 'number': {'_raw': 42}, 'null': {'_raw': None}, 'empty': {}} |
| `EXE-098` | PASS | bad_utf8_key='���invalid' header='���invalid' none_key='' |
| `EXE-099` | PASS | underlying consumer.close() called 1 time(s) across two KafkaTransport.close() calls |
| `EXE-100` | PASS | judge()_violations=10 offer()_violations=10 (both route through the same ReferenceEvaluator) |
| `EXE-101` | PASS | judge() on a screened-but-not-residually-valid LEI -> passed=False (residual_validators present=True) |
| `EXE-102` | PASS | TREAT UNKNOWN AS PASS: judge: unknown=True passed=True; offer/close: unknowns=1 violations=0 (PASS). TREAT UNKNOWN AS FAIL: judge: unknown=True passed=False; offer/close: unknowns=1 violations=1 (PASS). judge() and offer()/close() agree with each other on both the unknown flag and the policy-driven pass/fail for both policies. Reproduced fresh this round via con_exe_stream.py's exe102(); execute/s… |
| `EXE-103` | PASS | predicate_is_None=True judge()->passed=True unknown=False |
| `EXE-104` | PASS | at_99=None at_100=WindowVerdict(verdict=<Verdict.PASS: 'pass'>, messages=100, violations=0, unknowns=0, opened_at=None, closed_at=None) at_101=None open_messages_after_101=1 |
| `EXE-105` | PASS | verdicts_produced=0 open_messages=1000000 |
| `EXE-106` | PASS | offers at 12:00:10,12:00:50,12:00:20,12:01:05 -> [('2026-04-01T12:00:10+00:00', None), ('2026-04-01T12:00:50+00:00', None), ('2026-04-01T12:00:20+00:00', None), ('2026-04-01T12:01:05+00:00', None)] (window opens at first message's 'at'; a message earlier than _opened_at, like the third at 12:00:20 after 12:00:50, produces a negative delta that cannot close the window and is simply counted in; reco… |
| `EXE-107` | PASS | verdict=Verdict.INDETERMINATE messages=0 violation_rate=0.0 |
| `EXE-108` | PASS | window1: messages=10 violations=5; window2: messages=3 violations=0 opened_at=2026-04-02 00:00:00+00:00 |
| `EXE-109` | PASS | offer() called 500,000 times (5 assertions x 100,000 messages); top allocation deltas: ['/home/ashutosh/.local/share/uv/python/cpython-3.13.15-linux-x86_64-gnu/lib/python3.13/tracemalloc.py:560: size=384 B (+384 B), count=2 (+2), average=192 B', '/home/ashutosh/.local/share/uv/python/cpython-3.13.15-linux-x86_64-gnu/lib/python3.13/tracemalloc.py:423: size=376 B (+376 B), count=2 (+2), average=188 … |
| `EXE-110` | PASS | 1_violation_of_1000(0.1%): verdict=Verdict.PASS; 2_violations_of_1000(0.2%): verdict=Verdict.FAIL |
| `EXE-111` | PASS | {'tumbling_0': 'ValidationError', 'tumbling_neg': 'ValidationError', 'count_0': 'ValidationError', 'count_neg': 'ValidationError', 'count_zero_duration': 'OK'} |
| `EXE-112` | PASS | distinct message object ids seen across 40 assertions' evaluate() calls: 1 (expect 1 -- the same object) |
| `EXE-113` | PASS | n_verdicts_from_close_all=2 (3 assertions, 1 never offered anything) |
| `EXE-114` | PASS | messages_behind=19000 is_falling_behind=True render='19,000 message(s) behind, past the declared tolerance of 10,000. Messages are not being dropped; the assertion is asking the caller to shed load or add capacity.' |
| `EXE-115` | PASS | messages_behind=0 |
| `EXE-116` | PASS | {'FULL': ('passed', True, True), 'INCREMENTAL': ('passed over the rows examined', False, True), 'FORWARD_ONLY': ('passed over the rows examined', False, False)} |
| `EXE-117` | PASS | coverage=Coverage.FULL reason='nothing has been examined before' describe='the whole dataset — nothing has been examined before' |
| `EXE-118` | PASS | exactly_7_days=Coverage.FULL/'a full sweep is due; the last was 2026-04-03' 6_days=Coverage.INCREMENTAL never=Coverage.FULL/'a full sweep is due; the last was never run' |
| `EXE-119` | PASS | gap='Nothing examines rows older than 3 days. A correction booked before that would never be seen. Declare a full sweep, or name the column that changes when a row is restated.' audit={'describes': 'Examines new rows, plus anything from the last 3 days.', 'covers_the_past': False, 'gap': 'Nothing examines rows older than 3 days. A correction booked before that would never be seen. Declare a full s… |
| `EXE-120` | PASS | predicate="booked >= '2026-04-07' OR updated_at >= '2026-04-07'" |
| `EXE-121` | PASS | coverage=Coverage.FORWARD_ONLY sees_restatements=False |
| `EXE-122` | PASS | [INPUT.INVALID] a lookback cannot be negative \| Next: Give the period during which a correction may still arrive. |
| `EXE-123` | PASS | back=2026-04-10 equal=2026-04-10/2026-04-11 00:00:00+00:00 forward=2026-04-11 incomparable=2026-04-10 |
| `EXE-124` | PASS | rows_seen=400 (expected 400: the refused +200 batch contributes nothing) |
| `EXE-125` | PASS | {'date': datetime.date(2026, 4, 7), 'datetime': datetime.datetime(2026, 4, 7, 6, 30, tzinfo=datetime.timezone.utc), 'iso_str': '2026-04-07T06:30:00', 'non_iso_str': 'not-a-date', 'int': 12345, 'none': None} |
| `EXE-126` | PASS | {'none': 'NULL', 'int': '7', 'float': '7.5', 'bool': "'True'", 'date': "'2026-04-07'", 'quote': "'it''s'"} |
| `EXE-127` | PASS | {'1day': 'day', '3days': '3 days', '1hour': 'hour', '5hours': '5 hours', '30min': '30 minutes', '0': '0 minutes'} |
| `EXE-128` | PASS | {'pass': False, 'fail': True, 'indeterminate': False, 'error': False} |
| `EXE-129` | PASS | quarantined_rows=900 ref=quarantine:p1:1789350321 rows_in_quarantine=900 to_dict_keys=['action', 'plan_id', 'dataset', 'verdict', 'blocking', 'quarantine_ref', 'quarantined_rows', 'tag', 'reason', 'raised_at', 'disposition', 'override'] |
| `EXE-130` | PASS | rows=None: ref='' count=0; rows=[]: ref='' count=0 |
| `EXE-131` | PASS | after_block=['p1'] after_override=[] after_resolve=[] after_release=[] |
| `EXE-132` | PASS | {'t-1s': [], 't': ['p1'], 't+1s': ['p1']} |
| `EXE-133` | PASS | blocking_a_year_later=[] render='d: fail → block (the pipeline stops until somebody decides)\n  overridden by alice with no expiry: x' |
| `EXE-134` | PASS | blocking()=[] |
| `EXE-135` | PASS | disposition_after_override=[<Disposition.OVERRIDDEN: 'overridden'>] disposition_after_refail=[<Disposition.OPEN: 'open'>] blocking=['p1'] (the override is silently discarded: a fresh OPEN consequence replaces it, per the catalogue's own prediction of _open[plan_id]=consequence) |
| `EXE-136` | PASS | override_unknown=None release_unknown=None resolve_unknown=None release_on_block_action=None |
| `EXE-137` | PASS | release_result=[] was_released=True |
| `EXE-138` | PASS | stored_after_mutation=[{'a': 1}, {'a': 2}] get()_returns_new_list_each_time=True |
| `EXE-139` | PASS | Trial_fields_exclude_ledger_identity=True Preview.__init___has_no_uow_param=True passing_a_Trial_to_evidence.append=refused: TypeError: Trial.__init__() got an unexpected keyword argument 'tenant_id' |
| `EXE-140` | PASS | verdict=no_data has_data=False detail='no rows were in scope, so the control tested nothing' |
| `EXE-141` | PASS | alert_rate=0.2 (expected 0.2 = 4/20) describe='4 alert(s) over 20 evaluated period(s); 10 period(s) had no rows in scope and are excluded from the rate rather than counted as quiet' |
| `EXE-142` | PASS | alert_rate=None per_period=None describe='none of the 30 period(s) could be evaluated; 30 period(s) could not be read at all' |
| `EXE-143` | PASS | {'pass': False, 'fail': True, 'indeterminate': True, 'error': False, 'no_data': False} |
| `EXE-144` | PASS | 4_periods_trustworthy=False describe='1 alert(s) over 4 evaluated period(s); 4 period(s) is too few to quote a rate from'; 5_periods_trustworthy=True |
| `EXE-145` | PASS | was_bounded=True detail='the scan stopped at 10,000 rows, so these counts are a floor' describe='now: fail — at least 3 of 10,000 rows (0.03%)' backtest.is_a_lower_bound=True backtest.describe='at least 1 alert(s) over 1 evaluated period(s); 1 period(s) is too few to quote a rate from' |
| `EXE-146` | PASS | verdict=pass was_bounded=True detail='the scan stopped at 10,000 rows, so these counts are a floor' |
| `EXE-147` | PASS | query='SELECT COUNT(*) AS "scanned_rows", COUNT(*) FILTER (WHERE NOT COALESCE(("notional" IS NOT NULL), FALSE)) AS "violating_rows"\nFROM (SELECT * FROM "t" LIMIT 1000)' |
| `EXE-148` | PASS | compiled_query='SELECT COUNT(*) AS "scanned_rows", COUNT(*) FILTER (WHERE NOT COALESCE(("notional" IS NOT NULL), FALSE)) AS "violating_rows"\nFROM "t"\nWHERE ("as_of_date" = \'x\'\'; DROP TABLE positions --\')' trial_result=no_data/ |
| `EXE-149` | PASS | {'valid1': ('OK', 'as_of_date'), 'valid2': ('OK', '_x9'), 'bad1': ('ValidationError', None), 'bad2': ('ValidationError', None), 'bad3': ('ValidationError', None), 'bad4': ('ValidationError', None), 'bad5': ('ValidationError', None), 'bad6': ('ValidationError', None), 'trimmed': ('OK', 'a')} |
| `EXE-150` | PASS | restricted.where.operator=AND original_control_unmutated=True |
| `EXE-151` | PASS | time_to_first_trial=0.051s (30 periods at 50ms each would take 1.5s total if it were a list; first arrived quickly, confirming a generator) |
| `EXE-152` | PASS | n_trials=30 all_unran=True distinct_errors=1 evaluated=0 alert_rate=None |
| `EXE-153` | PASS | sunday=2026-04-05(6) d1(weekdays_only)=[datetime.date(2026, 3, 30), datetime.date(2026, 3, 31), datetime.date(2026, 4, 1), datetime.date(2026, 4, 2), datetime.date(2026, 4, 3)] d3(all_days)=[datetime.date(2026, 4, 1), datetime.date(2026, 4, 2), datetime.date(2026, 4, 3), datetime.date(2026, 4, 4), datetime.date(2026, 4, 5)] d4(days=0)=[] |
| `SCH-001` | PASS | {'every15': 'IntervalTrigger', 'every4h': 'IntervalTrigger', 'daily': 'IntervalTrigger', '0630': 'CalendarTrigger', '0630t2': 'CalendarTrigger', 'arrival': 'ArrivalTrigger', 'manual': 'ManualTrigger'} |
| `SCH-002` | PASS | {'manual': True, 'on arrival': True, 'daily': True, 'hourly': True} |
| `SCH-003` | PASS | all matched |
| `SCH-004` | PASS | minutes=1440 |
| `SCH-005` | PASS | {'every 4 minutes': 'refused: True', 'every 5 minutes': 'OK', 'every 0 minutes': 'refused: True'} |
| `SCH-006` | PASS | {'24:00': 'refused', '23:60': 'refused', '00:00': 'OK', '23:59': 'OK', '6:30': 'OK'} |
| `SCH-007` | PASS | [INPUT.INVALID] no calendar named 'target2' is loaded \| Next: Loaded: always, weekdays. Install the domain pack that provides it, or correct the name. Treating it as weekdays would produce controls that fire on the wrong days. \| Context: calendar='target2', loaded=['always', 'weekdays'] |
| `SCH-008` | PASS | {'30 6 * * 1-5': 'refused, remedy_ok=True', '@daily': 'refused, remedy_ok=True', '0 0 1 * *': 'refused, remedy_ok=True'} |
| `SCH-009` | PASS | {'daily': 'every 1 day(s)', 'nightly-ish': "unreadable schedule: [INPUT.INVALID] 'nightly-ish' is not a schedule Prama understands \| Next: Use one of: 'every 15 minutes', 'every 4 hours', 'daily', '06:30', '06:30 TARGET2', 'on arrival', 'manual'. Cron is deliberately not accepted — it cannot express a business calendar, and a schedule that is wrong on a holiday is a morning of false alarms. \| Co… |
| `SCH-010` | PASS | 'DependencyTrigger' appears in spec.py source=False (confirmed: no accepted schedule string can produce one; it exists only in trigger.py with no construction path from parse()) |
| `SCH-011` | PASS | at_09:00:00->2026-04-01 10:00:00+00:00 at_09:00:01->2026-04-01 10:00:00+00:00 at_09:59:59->2026-04-01 10:00:00+00:00 |
| `SCH-012` | PASS | at_09:00->2026-04-01 09:17:00+00:00 at_09:20->2026-04-01 10:17:00+00:00 |
| `SCH-013` | PASS | identical_across_calls=True all_in_range=True |
| `SCH-014` | FAIL | distinct_fire_times={(6, 12), (6, 18), (5, 59), (5, 31), (5, 37), (5, 34), (6, 11), (6, 20), (5, 52), (5, 58), (6, 17), (6, 26), (6, 29), (5, 30), (6, 1), (5, 33), (5, 39), (5, 36), (5, 42), (6, 7), (6, 13), (5, 48), (5, 54), (6, 19), (6, 25), (6, 22), (5, 32), (6, 6), (5, 38), (6, 9), (5, 41)} (expected all at exactly 06:30 -- a calendar schedule is not staggered since CalendarTrigger ignores off… |
| `SCH-015` | PASS | thursday_before_good_friday+after 06:30 -> next_after=2026-04-07 04:30:00+00:00 (expected 2026-04-07, Tuesday) |
| `SCH-016` | PASS | 06:29:59->2026-04-06 06:30:00->2026-04-07 06:30:01->2026-04-07 |
| `SCH-017` | PASS | [INPUT.INVALID] the never-open calendar has no business day in the next year \| Next: Check the calendar's weekend days and holidays. \| Context: calendar='never-open' |
| `SCH-018` | PASS | jan_due_UTC=2026-01-15 06:30:00+00:00 jul_due_UTC=2026-07-15 05:30:00+00:00 |
| `SCH-019` | PASS | expected_at(spring-forward nonexistent 01:30)=2026-03-29 01:30:00+00:00 (UTC=2026-03-29 01:30:00+00:00); next_after still advances strictly: True |
| `SCH-020` | PASS | expected_at(ambiguous autumn-back 01:30)=2026-10-25 00:30:00+00:00, UTC=2026-10-25 00:30:00+00:00 (recorded: which of the two 01:30s -- fold=0 -- was chosen) |
| `SCH-021` | PASS | daily interval trigger, moment on a DST-transition day (Europe/London, 2026-03-29) -> next_after=2026-03-30 00:00:00+01:00 (recorded per the catalogue's 'record the result': moment.replace(hour=0,...) computes local midnight and adds an absolute timedelta, which can shift a 'daily' control's local wall-clock time across the transition) |
| `SCH-022` | PASS | no_deadline->None with_deadline(after 06:30 today)->2026-04-02 06:30:00+00:00 |
| `SCH-023` | PASS | due=0 skipped_reason=manual |
| `SCH-024` | PASS | skipped_reason=waits_for_arrival |
| `SCH-025` | PASS | due=1 has_never_run=True due_at=None |
| `SCH-026` | PASS | next_fire=2026-04-01 09:46:00+00:00 {'before': 'skipped', 'at': 'due', 'after': 'due'} |
| `SCH-027` | PASS | reason=unreadable is_a_defect=True defects=1 log="control c1 has an unreadable schedule: [INPUT.INVALID] 'nightly-ish' is not a schedule Prama understands \| Next: Use one of: 'every 15 minutes', 'every 4 hours', 'daily', '06:30', '06:30 TARGET2', 'on arrival', 'manual'. Cron is deliberately not accepted — it cannot express a business calendar, and a schedule that is wrong on a holiday is a mornin… |
| `SCH-028` | PASS | {'not_due': False, 'manual': False, 'waits_for_arrival': False, 'unreadable': True} |
| `SCH-029` | PASS | detail='next at 2026-04-02T00:28:00+00:00' |
| `SCH-030` | PASS | 3 due, 5 not due, 1 with a schedule that cannot be read, which will never run until it is fixed |
| `SCH-031` | PASS | identical_across_two_calls=True |
| `SCH-032` | PASS | n_due=2 n_defects=0 |
| `SCH-033` | PASS | initial=0->minutes=15 initial=60->minutes=60 reason='nothing has been observed yet, so this is the declared starting cadence' |
| `SCH-034` | PASS | trailing_fail->15/'the last run failed, so the cadence returns to its floor — every 15 minutes — rather than easing back' trailing_error->15 |
| `SCH-035` | PASS | 9_passes->60/'9 consecutive clean run(s) is too small a sample to widen on; 10 are needed' 10_passes->90 |
| `SCH-036` | PASS | final_minutes=240 last_reason='20 consecutive clean runs, and the cadence is already at its declared ceiling — every 4 hours' |
| `SCH-037` | PASS | {'floor0': 'refused', 'floor_neg': 'refused', 'ceiling_below_floor': 'refused', 'equal': 'OK'} |
| `SCH-038` | PASS | 2_indeterminate->60/'0 consecutive clean run(s) is too small a sample to widen on; 10 are needed'; 3_indeterminate->60/'the last 3 runs were indeterminate, so the cadence is held while the scope is investigated — looking more often would not make an empty scope informative' |
| `SCH-039` | PASS | {'empty': (0, False, 0), '10pass': (10, False, 0), 'fail_then_10pass': (10, False, 1), '10pass_then_fail': (0, True, 1)} |
| `SCH-040` | PASS | recent_failures=0 |
| `SCH-041` | FAIL | {1: 5, 7: 5, 59: 60, 60: 60, 202: 195, 1439: 1440, 1440: 1440, 5000: 4980} |
| `SCH-042` | PASS | prev0=False/unchanged same=False/unchanged wider=True/widened narrower=True/narrowed |
| `SCH-043` | PASS | {5: '5 minutes', 60: 'hour', 90: 'hour 30 minutes', 120: '2 hours', 1440: 'day', 2880: '2 days', 1500: '25 hours'} |
| `SCH-044` | PASS | n_admitted=3 over_committed=True spent=20.009999999999998 render_excerpt='Running 3 of 3, spending 20.01 of a 10 budget.\nThe critical work alone exceeds the budget. It has been run anyway, because declining it would answer a question about money with a decision about risk —' |
| `SCH-045` | PASS | n_deferred=12 all_named_individually=True |
| `SCH-046` | FAIL | admitted=['B'] deferred=['A'] (sort key is (priority.rank, -deferrals, cost, identifier): B has 3 deferrals so -3 sorts before A's -0, so B is considered FIRST and admitted (cost 100 <= budget 100), leaving no room for A (cost 1) -- deferrals outrank cost, contradicting the docstring's 'by cost ascending... within equal cost, deferred longest' ordering, exactly as the catalogue states) |
| `SCH-047` | PASS | starving=['c3def'] c3_render='c3def on d (normal): the budget has 0 left and this would cost 1. Next attempt 2026-04-01T01:00+00:00. This is deferral 4 in a row for this control.' |
| `SCH-048` | PASS | admitted=2 spent=10 headroom=0.0 over_committed=False |
| `SCH-049` | PASS | budget0_clamped=True budgetneg5_clamped=True over_committed=True n_deferred=3 |
| `SCH-050` | PASS | admitted=['neg', 'zero'] spent=-5 |
| `SCH-051` | PASS | reason='the budget has 2 left and this would cost 5' |
| `SCH-052` | PASS | all_next_attempt_correct=True all_rendered_with_time=True sample_render='c0 on d (normal): the budget has 0 left and this would cost 1. Next attempt 2026-04-01T13:00+00:00.' |

## Failure details

All 33 are **unchanged from round 3** — same root cause, same code path, reproduced again on the current tree; none of the files any of them exercise appear in the batch A–D diff. Each entry states the catalogue's own Expected field, this round's own freshly reproduced Observed value, how to reproduce it, and an assessment carried forward from round 3 (re-verified, not assumed): **defect** (the code is wrong) or **not-a-defect** (the catalogue case itself was written from a misreading — `CON-006`, `CON-009`, `PRO-009`, `PRO-058`, `SCH-041`, carried over unchanged).

### CON-006 · Using a connector before `open` names the mistake
- **Expected:** `ConnectorError` with code `CONNECT.NOT_OPEN` and the remedy   "use the connector as an async context manager, or call open() first"
- **Observed (round 4):** sqlite.describe: code=CONNECT.OBJECT_MISSING; sqlite.snapshot: code=CONNECT.OBJECT_MISSING; sqlite.read: code=CONNECT.OBJECT_MISSING; filesystem.describe: code=CONNECT.OBJECT_MISSING; filesystem.snapshot: code=CONNECT.OBJECT_MISSING; filesystem.read: code=CONNECT.OBJECT_MISSING; rest.describe: code=CONNECT.NOT_OPEN; rest.snapshot: no error; rest.read: code=CONNECT.NOT_OPEN; mongodb.describe: code=CONNECT.NOT_OPEN; mongodb.snapshot: no error; mongodb.read: code=CONNECT.NOT_OPEN
- **Reproduce:** python3 -c "import asyncio; from prama.connect.sources.sqlite import SqliteConnector\nasync def m():\n c = SqliteConnector({'database_path': '/path/to/real.db'})\n print(await c.describe(('t',)))  # succeeds, no CONNECT.NOT_OPEN, because SqliteConnector overrides neither open() nor close()\nasyncio.run(m())"
- **Severity:** P1
- **Assessment:** not-a-defect. The catalogue assumed all six connectors need an explicit open() before use, but SqliteConnector legitimately holds no persistent handle (opens a fresh sqlite3 connection per call) so it has no NOT_OPEN guard at all — by design, matching CON-002's own point that a stateless connector should not be forced to write empty open/close overrides. Similarly, snapshot() on filesystem/rest/mongodb legitimately never touches the driver (filesystem hashes bytes directly; rest/mongo return a wall-clock Snapshot with no I/O), so it correctly succeeds without open(). Only objectstore matches the catalogue's literal expectation, and it does, on all three methods. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-009 · Declaring no capabilities is legal only alongside `can_run_controls = False`
- **Expected:** holds for all nine; `rest` and `mongodb` are the empty-matrix   cases and both report `False`
- **Observed (round 4):** empty_keys=['rest'] (expected rest+mongodb)
- **Reproduce:** python3 -c "from prama.connect.builtin import register_builtin; r = register_builtin(); print([k for k in r.keys() if len(r.capabilities(k).to_capabilities())==0])" # -> ['rest'] only
- **Severity:** P1
- **Assessment:** not-a-defect (catalogue error). MongoConnector's registered CapabilityMatrix declares FILTER+PREDICATE_PUSHDOWN (non-empty); only 'rest' has a truly empty matrix among the 9 built-in connectors. The catalogue's claim that mongodb is also an empty-matrix case is a misreading of the source. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-014 · A connector that declares `pushdown.predicate` must actually apply it
- **Expected:** exactly that day's rows; never the whole object
- **Observed (round 4):** raised CONNECT.NO_PREDICATE instead of returning filtered rows: [CONNECT.NO_PREDICATE] MongoConnector cannot restrict a read to part of an object | Next: Profile this object whole, or reach it through a connector that can filter. Reading everything and calling it one segment would attribute the whole object's data to that segment. | Context: connector='MongoConnector', predicate="d = '2026-04-01'"
- **Reproduce:** python3 -c "import asyncio; from prama.connect.sources.mongo import MongoConnector; from prama.connect.spi import SamplePlan\nasync def m():\n c = MongoConnector({'uri':'mongodb://x','database':'d'})\n async for b in c.read(('t',), plan=SamplePlan(predicate=\"d = '2026-04-01'\")): pass\nasyncio.run(m())" # raises ConnectorError(CONNECT.NO_PREDICATE), not the silent whole-object read the catalogue predicted
- **Severity:** P1
- **Assessment:** defect, but not the one hypothesised. MongoConnector never overrides pushdown_capabilities() (unlike every other connector with non-empty capabilities), so its instance-level supports('pushdown.predicate') is False despite the manifest declaring PREDICATE_PUSHDOWN. require_predicate_support() therefore refuses every predicate-bearing read before _sample()'s unconditional find({}) (confirmed real by reading the source) is ever reached with a predicate. Net effect: predicate-based Mongo reads always fail loudly rather than silently reading the whole collection — safer than feared, but still a declared capability the code does not keep. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-021 · `ReadPolicy.permits_path` treats an empty allow-list as "everything"
- **Expected:** `True`; then `True`, `True`, **`True`** (the prefix is   `"risk."` after `rstrip("*")` — check whether `riskier.positions` matches and   record which), `True` for the empty path
- **Observed (round 4):** empty_policy=True risk.positions=True risk=False riskier.positions=False empty_path=False
- **Reproduce:** python3 -c "from prama.connect.spi import ReadPolicy; p=ReadPolicy(allowed_paths=('risk',)); print(p.permits_path(('riskier','positions')))" # -> True: a neighbouring schema is admitted
- **Severity:** P1
- **Assessment:** defect (the underlying flaw is real) but the catalogue's specific worked example is wrong. With allowed_paths=('risk.*',) as literally specified, 'risk' alone -> False and 'riskier.positions' -> False (not True as claimed), because rstrip('*') leaves the trailing '.' which accidentally anchors the prefix. The real defect surfaces with a bare 'risk' (no wildcard): permits_path(('riskier','positions')) is True there, confirming the Why's concern (a neighbouring schema admitted) with a different, correct example. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-043 · `to_array` is used by every connector that builds a batch by hand
- **Expected:** all four route through it
- **Observed (round 4):** grep confirms sql/base.py (RecordBatch.from_arrays + to_array) and mongo.py (RecordBatch.from_arrays + to_array) route through to_array; sqlite.py._read_batch still calls pa.array(list(column)) directly (bypasses to_array); rest.py.read still uses RecordBatch.from_pydict (bypasses to_array) -- only 2 of 4 route through it, not all four. Unchanged from round 3 -- none of these four files appear in the batch A-D diff.
- **Reproduce:** grep -n 'RecordBatch.from_arrays\|RecordBatch.from_pydict\|to_array' src/prama/connect/sources/sql/base.py src/prama/connect/sources/mongo.py src/prama/connect/sources/sqlite.py src/prama/connect/sources/rest.py
- **Severity:** P1
- **Assessment:** defect. sql/base.py and mongo.py route through to_array(); sqlite.py's _read_batch uses pa.array(list(column)) directly and rest.py's read() uses RecordBatch.from_pydict — both bypass to_array, so only 2 of the 4 listed batch builders route through it, not all four. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-044 · A mixed-type column read over SQLite does not raise
- **Expected:** a string column of both values
- **Observed (round 4):** Reproduced fresh: sqlite3 table 'CREATE TABLE t (v)' (no declared type), INSERT (100) and ('one hundred'), then `async for batch in SqliteConnector({'database_path':dbpath}).read(('t',))`. Raises ArrowInvalid: "Could not convert 'one hundred' with type str: tried to convert to int64" -- the table cannot be read at all. Unchanged from round 3 -- sqlite.py carries zero commits in batches A-D.
- **Reproduce:** sqlite3 t.db 'CREATE TABLE t (v)'; sqlite3 t.db "INSERT INTO t VALUES (100)"; sqlite3 t.db "INSERT INTO t VALUES ('one hundred')"; python3 -c "import asyncio; from prama.connect.sources.sqlite import SqliteConnector\nasync def m():\n async for b in SqliteConnector({'database_path':'t.db'}).read(('t',)): print(b)\nasyncio.run(m())" # raises pyarrow.lib.ArrowInvalid
- **Severity:** P1
- **Assessment:** defect, confirmed exactly as CON-043's Why predicts. Note: the catalogue's own stated precondition (a TEXT-affinity column) does not reproduce it, because SQLite's TEXT affinity silently converts the integer literal to text at INSERT time; an untyped/no-affinity column (declared with no type at all) is needed to get genuinely mixed Python types back from the driver, which then makes SqliteConnector._read_batch's bare pa.array(list(column)) raise ArrowInvalid and the table becomes unreadable. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-055 · `validate` refuses a supplied secret outright
- **Expected:** `ValidationError` naming `password`, remedy "Reference a vault   entry with credential_ref instead. Connection configuration is exported to Git   and shown in the UI."
- **Observed (round 4):** msg=[INPUT.INVALID] postgresql needs schemas | Next: Fill in the highlighted fields; the connector reads them with no default. | Context: connector='postgresql', missing=['schemas'] remedy=Fill in the highlighted fields; the connector reads them with no default.
- **Reproduce:** python3 -c "from prama.connect.builtin import register_builtin; r=register_builtin(); print(r.schema('postgresql').field('schemas'))" # required=True, though the field is documented 'Leave empty to offer everything'
- **Severity:** P1
- **Assessment:** defect (distinct from what CON-055 set out to test). registry.create('postgresql', {...password:'literal'}) raises ValidationError naming 'schemas' as missing rather than 'password', because postgres's 'schemas' field is derived as required=True (self.config.get('schemas') has no literal default) and POSTGRES_OVERLAY never overrides it, even though the code treats a missing value as fine (tuple(self.config.get('schemas') or ())). Once 'schemas' is supplied, the secret-refusal logic CON-055 actually targets works exactly as expected. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-096 · A truncated read says so in the log and in `last_read`
- **Expected:** an INFO line naming the object, the row count and the byte   count; `last_read` carries `rows`, `bytes`, `seconds` and a `pacing` report
- **Observed (round 4):** log='' last_read={'object': 'public.positions', 'rows': 100, 'bytes': 3100, 'seconds': 0.001, 'pacing': {'batches': 1, 'working_seconds': 0.001, 'waiting_seconds': 0.0, 'achieved_duty_cycle': 1.0, 'capped_pauses': 0}}
- **Reproduce:** python3 -c "import asyncio; from prama.execute.kafka import KafkaTransport; from prama.execute.inflight import Pipeline; from prama.execute.actions import Action\nBASE=dict(bootstrap_servers='127.0.0.1:1', group_id='g', topics=['t'])\nt=KafkaTransport(**BASE)\nclass R:\n def value(self): return b'not json {{{'\n def key(self): return None\n def headers(self): return []\n def topic(self): return 't'\n def partition(self): return 0\n def offset(self): return 0\nmsg=t._message(R())\nprint(msg.payload)  # {'_unreadable': True, '_raw': ..., '_why': ...} -- a dict\nclass A:\n def judge(self, m):\n  class V: is_violation=False; unknown=False\n  return V()\np=Pipeline([A()], action=Action.ALERT)\nprint(p._judge(msg.payload).disposition)  # 'passed', not dead-lettered as unreadable\n"
- **Severity:** P1
- **Assessment:** defect, confirmed exactly. KafkaTransport._message wraps an undeserialisable body as {'_unreadable': True, '_raw': ..., '_why': ...} — a genuine dict — so Pipeline._judge's isinstance(payload, dict) check passes and the note is evaluated as an ordinary message against every assertion instead of being dead-lettered as unreadable. It only happened to 'pass' here because the stub assertion never fires; a real assertion checking an expected field would find it absent and could flag a content violation instead of what actually happened: an undeserialisable message. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-099 · `_column_names` is stale between a `_fetch` and a `_stream`
- **Expected:** keys C,D
- **Observed (round 4):** run_metric_query keys={'id', 'ccy'} (stale _stream_columns from read() were ('id', 'ccy', 'amount'))
- **Reproduce:** against a live PostgreSQL: async with PostgresConnector(cfg) as c:\n async for b in c.read(('t',)): break  # sets _stream_columns via _stream()\n rows = await c.run_metric_query('SELECT 1 AS metric_c, 2 AS metric_d')\n print(rows[0].keys())  # {'id','ccy'} -- the PREVIOUS read()'s stream columns, not metric_c/metric_d
- **Severity:** P1
- **Assessment:** defect, confirmed exactly. _column_names() reads self._stream_columns, which only _stream() sets; run_metric_query() calls _fetch(), not _stream(), so its rows get labelled with whatever _stream() happened to leave behind from an earlier read() — here truncated by zip(strict=False) to 2 of 3 stale column names, not the real metric column names at all. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-118 · The base `select_sql` drops a predicate
- **Expected:** the predicate appears in both
- **Observed (round 4):** select_sql='SELECT * FROM "public"."positions" LIMIT 100 OFFSET 0' (predicate present=False) stream_sql='SELECT * FROM "public"."positions" WHERE booked = DATE \'2026-04-01\'' (predicate present=True)
- **Reproduce:** python3 -c "from prama.connect.sources.sql.postgres import PostgresDialect; from prama.connect.spi import SamplePlan\nd=PostgresDialect(); p=SamplePlan(predicate=\"booked = DATE '2026-04-01'\")\nprint(d.select_sql(('t',), p, 100, 0))   # no WHERE clause -- predicate silently dropped\nprint(d.stream_sql(('t',), p))           # WHERE booked = DATE '2026-04-01' -- predicate present\"
- **Severity:** P1
- **Assessment:** defect, confirmed on the base dialect and reproduced identically on OracleDialect and SqlServerDialect (both inherit select_sql unmodified). SqlConnector.read() uses stream_sql so this is latent in the shipped connectors, but select_sql silently drops plan.predicate -- exactly the silent whole-object-read failure require_predicate_support exists to prevent, reachable by any future or third-party caller of select_sql. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-142 · The filesystem connector ignores the read policy's budgets
- **Expected:** record the actual count
- **Observed (round 4):** rows_read=100000 against ReadPolicy(max_rows_read=100) on a 100,000-row file (policy honoured=False)
- **Reproduce:** python3 -c "import asyncio, pyarrow as pa, pyarrow.parquet as pq; from prama.connect.sources.filesystem import FilesystemConnector; from prama.connect.spi import ReadPolicy\npq.write_table(pa.table({'id': list(range(100000))}), '/tmp/root/big.parquet')\nasync def m():\n c=FilesystemConnector({'root_path':'/tmp/root'}, policy=ReadPolicy(max_rows_read=100, max_bytes_scanned=1024))\n rows=0\n async with c:\n  async for b in c.read(('big.parquet',)): rows+=b.num_rows\n print(rows)  # 100000, not 100\nasyncio.run(m())"
- **Severity:** P1
- **Assessment:** defect, confirmed exactly. FilesystemConnector.read() builds no _Budget at all -- the policy's row/byte ceilings are silently not applied, matching the catalogue's own claim precisely. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-153 · A URI that is not an object store is MISCONFIGURED, not UNREACHABLE
- **Expected:** MISCONFIGURED for the first three, listing the six accepted   schemes; HEALTHY or a network state for the last
- **Observed (round 4):** {'/mnt/lake/positions': 'UNCAUGHT ParserException: Parser Error: syntax error at or near ","\n\nLINE 1: CREATE OR REPLACE SECRET prama_store (TYPE , PROVIDER credential_chain, ENDPOINT \'127.0.0.1:1\', REGION...\n                                                   ^', 'http://x/y': "UNCAUGHT InvalidInputException: Invalid Input Error: Secret provider 'credential_chain' not found for type 'http'", '': 'UNCAUGHT ParserException: Parser Error: syntax error at or near ","\n\nLINE 1: CREATE OR REPLACE SECRET prama_store (TYPE , PROVIDER credential_chain, ENDPOINT \'127.0.0.1:1\', REGION...\n                                                   ^', 's3://bucket/prefix': "UNCAUGHT Error: Secret Validation Failure: during `create` using the following:\nCredential Chain: 'config'\n"}
- **Reproduce:** python3 -c "import asyncio; from prama.connect.sources.objectstore import ObjectStoreConnector\nasync def m():\n async with ObjectStoreConnector({'uri':'/mnt/lake/positions'}) as c:\n  print(await c.health())\nasyncio.run(m())" # raises duckdb.ParserException from open(), health() never reached
- **Severity:** P1
- **Assessment:** defect, severe. Via the idiomatic `async with connector:` pattern (used everywhere else, e.g. CON-003/CON-088), all four test URIs raise a raw, uncaught duckdb exception from open() -- health() is never invoked at all. open() unconditionally calls _connect(), which executes _secret_statement() regardless of scheme; for an unrecognised/empty scheme the generated SQL is malformed. Calling health() WITHOUT open() first (bypassing _connect() since health() needs no live connection) does correctly return MISCONFIGURED with the expected message -- so the design is right in isolation but unreachable through the standard usage pattern for exactly the inputs it exists to diagnose. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-167 · A mixed-type column can still be read as Arrow
- **Expected:** a batch is produced; the `amount` column holds both values
- **Observed (round 4):** ArrowInvalid: Could not convert 'STRINGVAL' with type str: tried to convert to double (read() raised on a mixed-type column instead of producing a batch)
- **Reproduce:** run a local HTTP server returning 200 JSON records where one field is a float in 199 rows and the string 'STRINGVAL' in one; python3 -c "...RestConnector(...).read(('endpoint',))..." # raises pyarrow.lib.ArrowInvalid
- **Severity:** P1
- **Assessment:** defect, confirmed exactly. RestConnector.read() builds pa.RecordBatch.from_pydict({name: [_scalar(row.get(name)) for row in chunk] for name in names}) -- Arrow's own per-column type inference, not to_array -- so the exact type disagreement describe() correctly reports as a finding (CON-166 passes) makes read() raise instead of returning the data. The module docstring calls mixed types on an API 'the normal state...it has to survive into a control', but here it does not survive at all. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-172 · A declared predicate is applied to the query
- **Expected:** only that date's documents
- **Observed (round 4):** raised CONNECT.NO_PREDICATE instead of returning rows: [CONNECT.NO_PREDICATE] MongoConnector cannot restrict a read to part of an object | Next: Profile this object whole, or reach it through a connector that can filter. Reading everything and calling it one segment would attribute the whole object's data to that segment. | Context: connector='MongoConnector', predicate="d = '2026-04-01'" (see CON-014: MongoConnector never overrides pushdown_capabilities(), so require_predicate_support refuses before _sample's find({}) is ever reached)
- **Reproduce:** live MongoDB, 100 docs across 5 dates; python3 -c "...MongoConnector(...).read(('trades',), plan=SamplePlan(predicate=\"d = '2026-04-01'\"))..." # raises ConnectorError(CONNECT.NO_PREDICATE) rather than returning 20 rows
- **Severity:** P1
- **Assessment:** defect, same root cause as CON-014 (see there): MongoConnector never overrides pushdown_capabilities(), so require_predicate_support() refuses before _sample()'s find({}) (confirmed real) is ever reached with a non-empty predicate. The specific 'quiet disaster' this case and CON-014 hypothesise is unreachable through the public read() API; the actual failure mode is a loud, safe refusal instead. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-181 · Credentials in a built URI are percent-encoded
- **Expected:** the password is escaped so the host is parsed correctly
- **Observed (round 4):** built_uri='mongodb://alice:p@ss:w/ord@dbhost:27017/?authSource=admin'
- **Reproduce:** python3 -c "from prama.connect.sources.mongo import MongoConnector; c=MongoConnector({'host':'dbhost','user':'alice','password':\"p@ss:w/ord\",'database':'d','uri':''}); print(c._connection_uri())" # mongodb://alice:p@ss:w/ord@dbhost:27017/... -- three '@' characters
- **Severity:** P1
- **Assessment:** defect, confirmed. _connection_uri interpolates the raw password via an f-string with no percent-encoding; a password containing '@' produces a URI a parser cannot reliably split into userinfo/host. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-206 · `from_dict` loses half the definition
- **Expected:** an equal definition
- **Observed (round 4):** to_dict keys=['calendar', 'can_detect_missing', 'due_by', 'duplicates', 'files_per_day', 'landing_path', 'lateness_grace_seconds', 'name', 'pattern', 'trailer_declared']; lost on round-trip: ['earliest: 05:00:00 -> None', 'trailer.total_field: 2 -> None', 'trailer.amount_field: 9 -> None', 'trailer.header_lines: 1 -> 0', "trailer.total_tolerance: '0.01' -> '0'"]
- **Reproduce:** python3 -c "from prama.connect.feed.definition import FeedDefinition, TrailerSpec\nfrom prama.connect.feed.pattern import FilenamePattern\nfrom datetime import time\nf=FeedDefinition(name='f', landing_path='/x', filename_pattern=FilenamePattern('POS_{YYYYMMDD}.csv'), due_by=time(6,30), earliest=time(5,0), trailer=TrailerSpec(marker='TRLR', total_field=2, amount_field=9, header_lines=1, total_tolerance='0.01'))\nf2=FeedDefinition.from_dict(f.to_dict())\nprint(f2.earliest, f2.trailer.total_field, f2.trailer.amount_field, f2.trailer.header_lines, f2.trailer.total_tolerance)\" # None 2->None None 0 '0' -- all lost
- **Severity:** P1
- **Assessment:** defect, confirmed exactly as the catalogue's own summary states. to_dict() never emits earliest, total_field, amount_field, header_lines or total_tolerance; from_dict() never reads earliest (though it could, since to_dict never wrote it), nor total_field/amount_field/header_lines/total_tolerance for the trailer. A feed exported and re-imported silently loses its header exclusion, whose own code comment says omitting it 'reports a one-row shortfall on every single delivery'. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-217 · A trailer count mismatch is a count mismatch, with the shortfall
- **Expected:** `COUNT_MISMATCH`, `shortfall == 3`, and a rendered message   "trailer declares 1,000 records, 997 arrived (-3)"
- **Observed (round 4):** status=IntegrityStatus.COUNT_MISMATCH shortfall=3 message='f.csv: trailer declares 1,000 records, 997 arrived (+3)'
- **Reproduce:** python3 -c "from prama.connect.feed.integrity import TrailerChecker\nfrom prama.connect.feed.definition import TrailerSpec\nlines=['a,1\\n']*997+['TRLR,1000,0\\n']\nr=TrailerChecker(TrailerSpec(marker='TRLR', count_field=1)).check('f.csv', lines)\nprint(r.render())" # 'f.csv: trailer declares 1,000 records, 997 arrived (+3)' -- a '+' sign on a shortfall
- **Severity:** P1
- **Assessment:** defect. shortfall = declared_count - observed_count = +3 for a deficit, and render() formats it with an explicit '+' sign (f'({self.shortfall:+,})'), giving '(+3)' where the catalogue (and ordinary reading) expects '(-3)' -- a positive number for a deficit reads as though 3 extra rows arrived rather than 3 being missing. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### PRO-009 · Small cardinalities use linear counting and are near-exact
- **Expected:** exact or within one at the low end
- **Observed (round 4):** {1: 1, 2: 2, 10: 10, 100: 100, 1000: 996}
- **Reproduce:** python3 -c "from prama.profile.sketches import HyperLogLog\nimport random\nfor seed in range(5):\n random.seed(seed)\n h=HyperLogLog(14)\n for i in range(1000): h.add(f'v{i}-{random.random()}')\n print(h.estimate())\" # 989,1002,988,1000,992 -- errors up to 12, not within 1
- **Severity:** P1
- **Assessment:** not-a-defect. n=1,2,10,100 are exactly correct across every trial (confirmed collision-proof at those sizes); at n=1000 the linear-counting estimator carries normal, expected statistical variance (~0.1-1%), well inside its documented ~1.6% standard error at this precision. The catalogue's 'exact or within one' claim overstates precision for n=1000, which is not truly 'the low end' where near-exactness is guaranteed. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### PRO-021 · A merged TDigest answers like the digest of the whole
- **Expected:** within the structure's own stated accuracy; `count` is the sum;   `minimum`/`maximum` are the extremes of both
- **Observed (round 4):** diffs={0.01: 0.2652990689004282, 0.5: 3.7301984151732017, 0.99: 0.28311600301768447} count=100000 min_match=True max_match=True a_still_queryable_after_merge=True
- **Reproduce:** python3 -c "import random; from prama.profile.sketches import TDigest\nrandom.seed(3)\nsamples=[random.gauss(0,1) for _ in range(100000)]\na=TDigest(); [a.add(v) for v in samples[:50000]]\nb=TDigest(); [b.add(v) for v in samples[50000:]]\nm=a.merge(b)\nprint(m.quantile(0.5))  # 3.7357, should be ~0.0\n\"
- **Severity:** P1
- **Assessment:** defect, severe and previously unflagged. TDigest.merge() sets merged._centroids = [flattened a._centroids + b._centroids] directly, then calls merged._flush() -- but merged._buffer is empty (a fresh TDigest's buffer), so _flush()'s `if not self._buffer: return` makes the call a no-op. Concatenating a's centroids (sorted by value) with b's (also sorted) is NOT globally sorted whenever a and b's value ranges overlap -- the realistic case for splitting one column's rows into segments -- and quantile()'s cumulative-count walk over an unsorted list returns garbage. Confirmed the mechanism directly: two digests fed disjoint ranges (0..499, 500..999) merge correctly purely because concatenating two sorted lists over disjoint ranges happens to stay globally sorted. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### PRO-058 · `suggest_sample_plan` reads everything below the ceiling
- **Expected:** FULL for the first four; for the last, SYSTEMATIC at   `fraction == 0.01` with `seed=1`
- **Observed (round 4):** {None: (<SamplingStrategy.FULL: 'full'>, None, 0), 0: (<SamplingStrategy.FULL: 'full'>, None, 0), 5000000: (<SamplingStrategy.FULL: 'full'>, None, 0), 5000001: (<SamplingStrategy.SYSTEMATIC: 'systematic'>, 0.199999960000008, 1), 100000000: (<SamplingStrategy.SYSTEMATIC: 'systematic'>, 0.01, 1)}
- **Reproduce:** python3 -c "from prama.profile.profiler import suggest_sample_plan\nprint(suggest_sample_plan(5000001).strategy)" # SamplingStrategy.SYSTEMATIC, not FULL
- **Severity:** P1
- **Assessment:** not-a-defect (catalogue error). suggest_sample_plan's guard is `estimated_rows <= full_scan_ceiling` with full_scan_ceiling=5_000_000; 5_000_001 is strictly above the ceiling so it correctly samples, exactly matching the function's own documented rule ('below the ceiling, read everything... above it, sample'). The catalogue appears to have intended to test this exact boundary but mislabelled which side 5,000,001 falls on. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### PRO-099 · A generic column name never proposes a relationship
- **Expected:** no candidates; `suppressed == {"generic_name": 3}`
- **Observed (round 4):** n_candidates=1 suppressed={'generic_name': 3}
- **Reproduce:** python3 -c "from prama.discover.relationships import RelationshipDiscoverer\nfrom prama.mine.sample import Sample\nleft=Sample.of('orders',[{'id':i,'status':'open','created_at':'2026-01-01'} for i in range(50)])\nright=Sample.of('shipments',[{'id':i,'status':'sent','created_at':'2026-01-01'} for i in range(50)])\nr=RelationshipDiscoverer().discover(left,right)\nprint(len(r.candidates), r.suppressed)\" # 1 candidate (not 0), suppressed={'generic_name':3}
- **Severity:** P1
- **Assessment:** defect, confirmed and previously unflagged. RelationshipDiscoverer.discover() runs containment mining over EVERY shared column pair with no _is_generic() filter at all -- only the separate NAMING loop checks _is_generic and increments the suppressed count. So a universally generic column like 'id' is correctly excluded from the NAMING signal, but if its values happen to overlap (the ordinary case for two similarly-sized auto-incrementing id columns) it still produces a full CONTAINMENT-backed candidate -- exactly the false-relationship-between-every-table problem the module's own docstring says generic names cause, just reached through a different signal. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### EXE-018 · The recorded snapshot is always wall-clock
- **Expected:** record the kind
- **Observed (round 4):** record.snapshot.kind='wall_clock' identifier='2026-09-14T01:45:26.667168+00:00' -- literal 'wall_clock' written regardless of engine (here engine='sqlite', which has an exact FILE_DIGEST snapshot available via SqliteConnector.snapshot(), never consulted)
- **Reproduce:** real ControlRun against a live sqlite (exact FILE_DIGEST snapshot available): record.snapshot.kind == 'wall_clock' regardless
- **Severity:** P1
- **Assessment:** defect, confirmed exactly as flagged. ControlRun._run_one constructs SnapshotRef(kind='wall_clock', identifier=started.isoformat()) as a literal and never calls connector.snapshot(), even against sources with exact snapshot mechanisms (SQLite's file digest here; also PostgreSQL's LSN, Snowflake's query id). (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### EXE-019 · Coverage is recorded as `full` whatever was read
- **Expected:** record the value
- **Observed (round 4):** record.coverage='full' -- literal 'full' written unconditionally, with no connection to the actual SamplePlan/watermark scope that was read
- **Reproduce:** real ControlRun: record.coverage == 'full' regardless of sample plan or watermark scope
- **Severity:** P1
- **Assessment:** defect, confirmed exactly as flagged. coverage='full' is a literal in ControlRun._run_one, disconnected from execute/watermark.py's Coverage machinery entirely. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### EXE-043 · `drain` does not spin on a permanently failing recorder
- **Expected:** the call terminates
- **Observed (round 4):** take_one() called 200 times directly against a permanently-failing recorder: 200/200 returned 'stranded', 0/200 returned None; unit still in queue afterward=True. Since take_one() never returns None (confirmed: 0 times), drain()'s `while limit <= 0: outcome = await self.take_one()` -- which only stops on `outcome is None` -- would never terminate; confirmed as a hot loop rather than literally hanging the harness process
- **Reproduce:** Worker with a permanently-failing recorder: call take_one() repeatedly -- every call returns status='stranded' (never None), which is the only condition that stops drain()'s `while limit <= 0` loop
- **Severity:** P1
- **Assessment:** defect, confirmed. take_one() never returns None against a permanently-failing recorder (200/200 calls returned 'stranded' in the reproduction), so drain(limit=0) -- whose only exit condition is `outcome is None` -- would spin forever against a permanently unreachable ledger rather than the merely-transient case X4 was fixed for. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### EXE-050 · A stranded unit is invisible in the fleet report
- **Expected:** record whether the stranded unit appears
- **Observed (round 4):** outcome.status=stranded; FleetReport has a 'stranded' property=False; render()='0 unit(s) completed, 0 record(s) written, 0 still queued.'; to_dict()={'done': 0, 'records': 0, 'lost': [], 'failed': [], 'remaining': 0, 'summary': '0 unit(s) completed, 0 record(s) written, 0 still queued.'}; stranded unit mentioned anywhere=False
- **Reproduce:** python3 -c "from prama.execute.worker import FleetReport, WorkOutcome\no=WorkOutcome(unit=None, status='stranded')\nr=FleetReport(outcomes=(o,), remaining=0)\nprint(hasattr(r,'stranded'), r.render())\" # False; render() never mentions the stranded unit
- **Severity:** P1
- **Assessment:** defect, confirmed exactly as flagged. FleetReport exposes done/lost/failed properties and render()/to_dict() name lost and failed explicitly, but there is no 'stranded' property or mention anywhere -- a stranded unit vanishes from the report entirely, reproducing the invisibility X4 fixed one layer out. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### EXE-096 · An undeserialisable message is not dead-lettered as unreadable
- **Expected:** record the disposition
- **Observed (round 4):** _message() wraps as {'_unreadable': True, '_raw': 'not json {{{', '_why': 'the message body is not JSON'}; isinstance(payload, dict)=True; Pipeline._judge() on this wrapped payload -> disposition=passed (confirmed: the unreadable-body note passes the isinstance(payload, dict) check in _judge, so it is evaluated as an ordinary message against every assertion rather than being dead-lettered as unreadable -- here it 'passed' because the fake assertion never fires, but a real assertion checking some expected field would find it absent from {'_unreadable':True,...} and could flag it as a content violation instead of what it actually is: an undeserialisable message)
- **Reproduce:** see CON-096 above (same defect, same module)
- **Severity:** P1
- **Assessment:** defect, confirmed exactly as flagged (duplicate of CON-096's finding, filed under both areas per the catalogue's own structure). (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### SCH-046 · Shedding order contradicts its own docstring
- **Expected:** record which is admitted
- **Observed (round 4):** admitted=['B'] deferred=['A'] (sort key is (priority.rank, -deferrals, cost, identifier): B has 3 deferrals so -3 sorts before A's -0, so B is considered FIRST and admitted (cost 100 <= budget 100), leaving no room for A (cost 1) -- deferrals outrank cost, contradicting the docstring's 'by cost ascending... within equal cost, deferred longest' ordering, exactly as the catalogue states)
- **Reproduce:** python3 -c "from prama.schedule.budget import Priority, Candidate, BudgetPolicy\nimport datetime as dt\na=Candidate(identifier='A', dataset='d', priority=Priority.NORMAL, cost=1, deferrals=0)\nb=Candidate(identifier='B', dataset='d', priority=Priority.NORMAL, cost=100, deferrals=3)\nalloc=BudgetPolicy(100).allocate([a,b], now=dt.datetime.now(dt.UTC))\nprint([c.identifier for c in alloc.admitted])\" # ['B'], not ['A']
- **Severity:** P1
- **Assessment:** defect, confirmed exactly as flagged. The sort key is (priority.rank, -deferrals, cost, identifier) -- deferrals outrank cost, so B (cost 100, 3 deferrals) is tried before and admitted over A (cost 1, 0 deferrals), keeping one control instead of one hundred for the same budget. The docstring says 'by priority, and within a priority by cost ascending... within equal cost, whatever has been deferred longest goes first', which describes the opposite precedence from what the code implements. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-062 · `register_builtin` is idempotent
- **Expected:** nine keys each time, no error
- **Observed (round 4):** len=0 keys=[]
- **Reproduce:** python3 -c "from prama.connect.registry import ConnectorRegistry; from prama.connect.builtin import register_builtin; r=ConnectorRegistry(); register_builtin(r); print(len(r))" # -> 0, not 9
- **Severity:** P2
- **Assessment:** defect, severe. register_builtin's `target = registry or default_registry()` uses truthiness; ConnectorRegistry defines __len__ but not __bool__, so a freshly-constructed EMPTY registry — the exact state you'd pass in to populate it — is falsy, and `or` silently substitutes the process-wide default_registry() singleton. Registrations land there instead, and the caller's own object is left empty with no error. Every existing call site in src/ and tests/ happens to use the *return value* (`registry = register_builtin(ConnectorRegistry())`), which masks this, but no 'isolated' registry built the documented way (`r = ConnectorRegistry(); register_builtin(r)`) is ever actually isolated. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-129 · A non-FULL, non-HEAD plan produces a deterministic ordering
- **Expected:** identical both times at seed 42; a different set at 43
- **Observed (round 4):** seed42_run1_len=100 identical_rerun=True differs_at_seed43=False
- **Reproduce:** sqlite3 t.db 'CREATE TABLE t(a)'; INSERT 1000 rows; python3 -c "import asyncio; from prama.connect.sources.sqlite import SqliteConnector; from prama.connect.spi import SamplePlan, SamplingStrategy\nasync def m():\n c=SqliteConnector({'database_path':'t.db'})\n p1=SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, rows=100, seed=42)\n p2=SamplePlan(strategy=SamplingStrategy.SYSTEMATIC, rows=100, seed=43)\n ids1=[r['a'] async for r in ...]  # seed=42 and seed=43 give IDENTICAL 100-row samples\nasyncio.run(m())"
- **Severity:** P2
- **Assessment:** defect, broader than CON-130's already-documented seed=0 case. _select's 'ORDER BY (rowid * {seed} % 1000003)' only reorders rows once rowid*seed wraps past the 1000003 modulus; for a table of N rows, that needs seed >= ~1000003/N. On a 1000-row table, EVERY seed from 1 through 1000 (i.e. any seed up to the table's own row count -- the realistic case) produces zero wraps, so 'systematic sampling' is identical to plain rowid order for most configured seeds on small-to-medium tables, not just seed=0. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### CON-219 · The reported `observed_count` on a total mismatch is the line index
- **Expected:** the number of data rows counted (100)
- **Observed (round 4):** status=IntegrityStatus.TOTAL_MISMATCH observed_count=103 (trailer line index would be 103; data rows counted=100)
- **Reproduce:** python3 -c "from prama.connect.feed.integrity import TrailerChecker\nfrom prama.connect.feed.definition import TrailerSpec\nlines=['h1\\n','h2\\n']+['a,10.00\\n']*100+['\\n','TRLR,100,5000.00\\n']\nr=TrailerChecker(TrailerSpec(marker='TRLR', count_field=1, total_field=2, header_lines=2)).check('f.csv', lines)\nprint(r.observed_count)" # 103 (the trailer's line index), not 100 (the data row count)
- **Severity:** P2
- **Assessment:** defect, confirmed exactly. _check_total passes observed_count=trailer_index (the LINE index: 2 header + 100 data + 1 blank = 103) instead of the actual data row count 100 that check()'s COUNT_MISMATCH branch above it uses -- the same field means two different things in two branches of one method. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### SCH-014 · A calendar schedule is not staggered
- **Expected:** all forty at exactly 06:30
- **Observed (round 4):** distinct_fire_times={(6, 12), (6, 18), (5, 59), (5, 31), (5, 37), (5, 34), (6, 11), (6, 20), (5, 52), (5, 58), (6, 17), (6, 26), (6, 29), (5, 30), (6, 1), (5, 33), (5, 39), (5, 36), (5, 42), (6, 7), (6, 13), (5, 48), (5, 54), (6, 19), (6, 25), (6, 22), (5, 32), (6, 6), (5, 38), (6, 9), (5, 41)} (expected all at exactly 06:30 -- a calendar schedule is not staggered since CalendarTrigger ignores offset_minutes)
- **Reproduce:** python3 -c "from prama.schedule.spec import parse\nfrom prama.schedule.due import _stagger\nfor i in range(5):\n t=parse('06:30 TARGET2', offset_minutes=_stagger(f'c{i}'))\n print(t.at)\" # every control prints 06:30 regardless of its stagger offset
- **Severity:** P2
- **Assessment:** defect, confirmed exactly as flagged. _stagger computes a per-control offset_minutes for every control and Schedule.plan passes it into parse() unconditionally, but only IntervalTrigger's __init__ consumes offset_minutes -- CalendarTrigger has no such field and ignores it entirely, so every 06:30-scheduled control (the ones that fire right after a feed lands, per the stagger's own stated purpose) fires at exactly the same instant. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### SCH-041 · Rounded intervals sit on a legible grid
- **Expected:** 5, 5, 60, 60, 210, 1440, 1440, 5040 — never below the step
- **Observed (round 4):** {1: 5, 7: 5, 59: 60, 60: 60, 202: 195, 1439: 1440, 1440: 1440, 5000: 4980}
- **Reproduce:** python3 -c "from prama.schedule.cadence import _round_interval\nprint(_round_interval(202), _round_interval(5000))\" # 195, 4980
- **Severity:** P2
- **Assessment:** not-a-defect (catalogue arithmetic error). round(202/15)=13 (13.4667 rounds down) -> 195; round(5000/60)=83 (83.333 rounds down) -> 4980. The other six catalogue values (1,7,59,60,1439,1440) all match exactly. The catalogue's predicted 210/5040 only match if rounding were ceiling rather than round-to-nearest, which is not what the code claims or does. (unchanged from round 2 -- same root cause, reproduced again on the current tree)

### PRO-063 · `from_rows` is not exported
- **Expected:** it resolves — but the name is absent from `__all__` while   `points_from_profile`, `detectable_rate` and `suggest_sample_plan` are present
- **Observed (round 4):** resolves=False in___all__=False __all__=['DEFAULT_MUTABLE_DAYS', 'MAX_SEGMENTS', 'ColumnAccumulator', 'ColumnProfile', 'CountMin', 'DatasetProfile', 'HyperLogLog', 'IncrementalPlan', 'IncrementalPlanner', 'NumericSummary', 'ProfileProvenance', 'Profiler', 'Segment', 'SegmentAccumulation', 'SegmentDecision', 'SegmentGrain', 'SegmentLedger', 'SegmentRecord', 'SegmentState', 'Segmentation', 'SegmentedProfile', 'SegmentedProfiler', 'StringSummary', 'TDigest', 'TopK', 'character_classes', 'detectable_rate', 'points_from_profile', 'suggest_sample_plan']
- **Reproduce:** python3 -c "from prama.profile import from_rows" # ImportError: cannot import name 'from_rows' from 'prama.profile'
- **Severity:** P3
- **Assessment:** defect, worse than the catalogue anticipated. `from prama.profile import from_rows` fails entirely -- profile/__init__.py's import block never pulls from_rows in at all, so it is not merely missing from __all__, it is absent from the package namespace altogether. Only reachable via the submodule path prama.profile.profiler.from_rows. (unchanged from round 2 -- same root cause, reproduced again on the current tree)
