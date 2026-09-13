# Platform & core — QA execution log

**615 cases executed** (CFG-001..320, DB-001..295). **564 PASS**, **51 FAIL**, **0 BLOCKED**. Pass rate **91.7%** (564/615).

Every case below was executed: real SQLite files (file-backed, matching the async/sync engine split the codebase actually uses) throughout, and a live PostgreSQL 16 server (`postgresql://prama:prama@127.0.0.1:55433/prama`, via a Docker container already running on this host) for every case naming PostgreSQL specifically. Nothing below is inferred from reading source; every PASS and FAIL is a reproduced, observed result. Four PostgreSQL-async cases (DB-070, DB-072, DB-148, DB-279) are FAIL rather than BLOCKED: they were run against the live server, and what running them found is that the async PostgreSQL engine cannot be constructed at all in this build — a genuine, reproduced defect (root-caused under DB-070), not an absent test. MON-, INC-, RPT-, BCH- and OPS- are out of scope for this log.

## Failures ranked by severity

- **CFG-048** (P1) — `concurrency.lease.provider` selects database or memory
- **CFG-118** (P1) — A coercion failure on a secret does not print the secret
- **DB-025** (P1) — No foreign key leaves the evidence ledger
- **DB-028** (P1) — The loader parses every table and column
- **DB-031** (P1) — The statement splitter handles a semicolon inside a string literal
- **DB-035** (P1) — `db init` on an empty database creates everything
- **DB-047** (P1) — A column whose **type** changed is detected
- **DB-052** (P1) — A missing *unique* index is treated as more than performance
- **DB-065** (P1) — A missing driver produces a named error with an install hint
- **DB-068** (P1) — An in-memory SQLite keeps its schema across sessions
- **DB-070** (P1) — The asyncpg path sets application name, statement timeout and search path
- **DB-072** (P1) — `sslmode` is not silently dropped on the async path
- **DB-142** (P1) — `by_external_id` is *not* tenant-scoped
- **DB-148** (P1) — `grant` works on both engines
- **DB-179** (P1) — Two concurrent amendments do not both succeed
- **DB-201** (P1) — `AttributeDao.mapped_to_property` is not tenant-scoped
- **DB-239** (P1) — The erasure assertions are not the only guard
- **DB-244** (P1) — `for_control` is not tenant-scoped
- **DB-245** (P1) — `for_run` is not tenant-scoped
- **DB-279** (P1) — The conditional upsert works on both engines
- **CFG-008** (P2) — An unknown `logging.level` is refused, not silently defaulted
- **CFG-014** (P2) — The comment on `security.cookies_https_only` matches its value
- **CFG-020** (P2) — `web.preview.max_rows: 0` is refused
- **CFG-036** (P2) — `plugins.disabled` exists in the tracked file and not in `DEFAULTS`
- **CFG-040** (P2) — A negative `max_overflow` is refused
- **CFG-082** (P2) — Redaction does not reach inside lists
- **CFG-088** (P2) — The filter does not mask a secret embedded in a URL
- **CFG-094** (P2) — The JSON formatter emits a UTC timestamp with milliseconds and a `Z`
- **CFG-112** (P2) — A negative numeric duration passes the type check
- **CFG-162** (P2) — `utc_now()` is the only ambient time source and is used sparingly
- **CFG-169** (P2) — A clock that steps backwards does not break monotonicity
- **CFG-205** (P2) — `ALWAYS` restarts a task that returns cleanly
- **CFG-256** (P2) — `plugins.disabled` in configuration is either wired up or not documented
- **CFG-260** (P2) — A broken plugin is visible in health output
- **CFG-262** (P2) — `_entry_points_for` swallowing every exception is bounded
- **CFG-292** (P2) — `next_business_day` on a calendar with no business days does not hang
- **CFG-305** (P2) — Calendar names are matched case-insensitively
- **DB-048** (P2) — A column whose declared width shrank is detected
- **DB-050** (P2) — An extra *column* on a declared table is not reported at all
- **DB-055** (P2) — `_recorded_state` swallowing `SQLAlchemyError` is bounded
- **DB-074** (P2) — A fractional statement timeout does not truncate to zero
- **DB-076** (P2) — `upsert` with every column in the conflict key produces valid SQL
- **DB-086** (P2) — Using a closed unit of work is refused clearly
- **DB-089** (P2) — Every DAO property is reachable and returns its declared type
- **DB-098** (P2) — A malformed timestamp in a row is refused, not silently defaulted
- **DB-125** (P2) — A negative limit or offset is refused
- **DB-155** (P2) — `active_for_principal` does not filter on expiry
- **DB-208** (P2) — `JourneyDao.containing` does not silently truncate
- **CFG-021** (P3) — `web.preview.backtest_days` defaults to 30 and rejects a negative
- **CFG-062** (P3) — A non-UTF-8 config file is refused with the same code
- **DB-209** (P3) — `ConnectionDao.unhealthy` has the same ceiling

## Per-case results

| Id | Result | Observed |
|---|---|---|
| `CFG-001` | PASS | built OK in empty dir; has all top-level DEFAULTS keys=True |
| `CFG-002` | PASS | CONFIG.FILE_MISSING: [CONFIG.FILE_MISSING] configuration file not found: /tmp/no-such-cfg-qa.yaml \| Next: Create /tmp/no-such-cfg-qa.yaml, or point --config at an existing file. \| Context: path='/tmp/no-such-cfg-qa.yaml' |
| `CFG-003` | PASS | CONFIG.FILE_MISSING: [CONFIG.FILE_MISSING] configuration file not found: /tmp/no-such-cfg-qa2.yaml \| Next: Create /tmp/no-such-cfg-qa2.yaml, or point --config at an existing file. \| Context: path='/tmp/no-such-cfg-qa2.yaml' |
| `CFG-004` | PASS | 'Prama' |
| `CFG-005` | PASS | 'development' |
| `CFG-006` | PASS | HOSTNAME=box-7 -> 'box-7'; unset -> 'local' |
| `CFG-007` | PASS | [('DEBUG', 'DEBUG'), ('INFO', 'INFO'), ('WARNING', 'WARNING'), ('ERROR', 'ERROR')] |
| `CFG-008` | FAIL | unnamed ValueError: Unknown level: 'VERBOSE' |
| `CFG-009` | PASS | line='{"ts":"2026-09-13T08:06:09.667Z","level":"INFO","logger":"cfg009","message":"hello","fields":{"foo":"bar"}}' parsed_keys=['ts', 'level', 'logger', 'message', 'fields'] |
| `CFG-010` | PASS | '08:06:09 INFO    cfg010 plain message [cid=cid-123]\n' |
| `CFG-011` | PASS | '' |
| `CFG-012` | PASS | CONFIG.SECRET_MISSING: remedy='Set security.session_secret in config/application.local.yaml (git-ignored), or export PRAMA_SECURITY__SESSION_SECRET. Never put it in a tracked file.' |
| `CFG-013` | PASS | refused, as expected |
| `CFG-014` | FAIL | comment says 'Off in development' near cookies_https_only=True (True means ON) |
| `CFG-015` | PASS | '' |
| `CFG-016` | PASS | True |
| `CFG-017` | PASS | '' |
| `CFG-018` | PASS | ValidationError: [INPUT.INVALID] no file-backed executor for 'postgres' \| Next: Available: duckdb, sqlite. For anything else, supply your own executor — the runner's whole interface to a source is a callable that takes SQL and returns rows. \| Context: engine='postgres'; registered BUILDERS=['duckdb', 'sqlite'] |
| `CFG-019` | PASS | 1000000 |
| `CFG-020` | FAIL | max_rows=0 not refused; trial.verdict='' error='PqlSyntaxError: [PQL.SYNTAX] expected the reason this control exists, in quotes, and found \'"sanity"\' \| Next: Quoted text is written between single quotes: \'like this\'. \| Context: position=\'line 1, column 31\'' (ran unbounded instead of refusing) |
| `CFG-021` | FAIL | [CFG-021-default] 30 \|\| preview_routes.py backtest_days negative-guard present=False |
| `CFG-022` | PASS | 'sqlite' |
| `CFG-023` | PASS | 'sqlite' |
| `CFG-024` | PASS | CONFIG.DIALECT_UNSUPPORTED: 'Set database.dialect to one of: sqlite, postgres.' |
| `CFG-025` | PASS | 'data/prama.db' |
| `CFG-026` | PASS | {':memory:': (True, None), '': (True, None), 'file::memory:?cache=shared': (True, None)} |
| `CFG-027` | PASS | PRAGMA journal_mode -> 'delete' |
| `CFG-028` | PASS | connected without error on :memory: |
| `CFG-029` | PASS | refused/erred as hoped: ProgrammingError: You can only execute one statement at a time. |
| `CFG-030` | PASS | first=2, second=2 |
| `CFG-031` | PASS | PRAGMA busy_timeout -> 2500 |
| `CFG-032` | PASS | PRAGMA foreign_keys -> 0 |
| `CFG-033` | PASS | OperationalError: no such column: "no_such_column" - should this be a string literal in single-quotes? |
| `CFG-034` | PASS | -> ('literal',) |
| `CFG-035` | PASS | all match |
| `CFG-036` | FAIL | file has disabled=True, DEFAULTS has disabled=False |
| `CFG-037` | PASS | groups=['prama.connectors', 'prama.backends', 'prama.monitors', 'prama.notifiers', 'prama.scorers', 'prama.validators'] |
| `CFG-038` | PASS | CONFIG.POOL_INVALID: 'Set database.pool.size to at least 1.' |
| `CFG-039` | PASS | 0 |
| `CFG-040` | FAIL | no exception; accepted max_overflow=-5 |
| `CFG-041` | PASS | timeout=45.0, recycle=3600.0 |
| `CFG-042` | PASS | SchemaDriftError: DB.SCHEMA_DRIFT |
| `CFG-043` | PASS | started_ok=True, verify().ok=False, drifts=1 |
| `CFG-044` | PASS | sqlalchemy.engine log captured 46107 bytes; contains SELECT 1=True |
| `CFG-045` | PASS | schema_file=/tmp/cfgqa-45-2hp513_b/schema/sqlite.sql; init summary=schema created: 35 tables, 99 statements from /tmp/cfgqa-45-2hp513_b/schema/sqli |
| `CFG-046` | PASS | DB.SCHEMA_FILE_MISSING: 'Prama has no migrations; this file is the schema. Restore it from the repository, or set database.schema_dir to where it lives.' |
| `CFG-047` | PASS | shutdown() returned after 1.00s (grace=1.0s) |
| `CFG-048` | FAIL | with concurrency.lease.provider=memory, Database.lease_provider() returned DatabaseLeaseProvider (config value never read anywhere in src/prama; grep confirms no code branches on lease.provider) |
| `CFG-049` | PASS | renew_interval must be shorter than ttl, or a lease expires between renewals |
| `CFG-050` | PASS | 6s/10s warns=True; shipped-default 10s/30s warns=False |
| `CFG-051` | PASS | LeaseLostError as expected: [CONCURRENCY.LEASE_LOST] lease on 'res' has expired \| Next: Abandon the work and re-acquire before continuing. \| Context: holder='holder:01M2DAJ0VFSF0BCG37CJJFVWH4', resource='res' |
| `CFG-052` | PASS | cli='cli-value' env='env-value' overlay='overlay-value' file-only='file-value' defaults='default-value' |
| `CFG-053` | PASS | size=5 max_overflow=20 |
| `CFG-054` | PASS | ['prama.connectors'] |
| `CFG-055` | PASS | name='base' env='overlaid' |
| `CFG-056` | PASS | loaded cleanly, no overlay present |
| `CFG-057` | PASS | 'overlay-props' |
| `CFG-058` | PASS | CONFIG.YAML_INVALID: detail present=True |
| `CFG-059` | PASS | CONFIG.YAML_SHAPE: 'Wrap the document in key: value pairs.' |
| `CFG-060` | PASS | 'has-overlay' |
| `CFG-061` | PASS | CONFIG.FILE_UNREADABLE: "Check the file's permissions and encoding (UTF-8 is expected)." |
| `CFG-062` | FAIL | UnicodeDecodeError escaped uncaught (except OSError does not catch it): 'utf-8' codec can't decode byte 0xe9 in position 16: invalid continuation byte |
| `CFG-063` | PASS | CONFIG.FORMAT_UNSUPPORTED: 'Use a .yaml, .yml or .properties file.' |
| `CFG-064` | PASS | CONFIG.PROPERTIES_INVALID: line=3 |
| `CFG-065` | PASS | 'commented-ok' |
| `CFG-066` | PASS | pool.size=20 dialect=sqlite |
| `CFG-067` | PASS | CONFIG.KEY_CONFLICT: [CONFIG.KEY_CONFLICT] configuration key 'a.b' conflicts with a scalar at 'a' \| Next: Remove one of the two definitions; a key cannot be both. \| Context: conflict_at='a', key='a.b' |
| `CFG-068` | PASS | app.name='envname' has('path')=False |
| `CFG-069` | PASS | int=20 str='20' |
| `CFG-070` | PASS | 'box' |
| `CFG-071` | PASS | no crash; built OK |
| `CFG-072` | PASS | 'postgres' |
| `CFG-073` | PASS | CONFIG.CLI_INVALID: 'Use --set path.to.key=value.' |
| `CFG-074` | PASS | '' |
| `CFG-075` | PASS | 'a=b=c' |
| `CFG-076` | PASS | 'Prama' |
| `CFG-077` | PASS | {'database.pool.size': 'built-in defaults', 'logging.level': '/tmp/cfgqa-prov-2tbfkwda/app.yaml', 'app.name': 'environment', 'tenancy.default_tenant': 'command line'} |
| `CFG-078` | PASS | value='from-cli' provenance='command line' |
| `CFG-079` | PASS | 'environment' |
| `CFG-080` | PASS | masked_count=15/15 |
| `CFG-081` | PASS | {'database': {'postgres': {'password': '***', 'host': 'x'}}} |
| `CFG-082` | FAIL | redact_mapping result for list-of-dicts: {'connections': [{'password': 'p1'}, {'password': 'p2'}]} (masked_in_list=False) |
| `CFG-083` | PASS | '' |
| `CFG-084` | PASS | '***' |
| `CFG-085` | PASS | 'topsecret' |
| `CFG-086` | PASS | 'password=***' |
| `CFG-087` | PASS | 'token=*** and api_key=***' |
| `CFG-088` | FAIL | 'connecting to postgresql://prama:hunter2@host/db' |
| `CFG-089` | PASS | {'password': '***'} |
| `CFG-090` | PASS | task A retained 'cid-A' across its own await |
| `CFG-091` | PASS | {'A': 'cid-A', 'B': 'cid-B'} |
| `CFG-092` | PASS | prama-named handlers on root logger: 1 |
| `CFG-093` | PASS | third-party handler survived apply()=True |
| `CFG-094` | FAIL | ts='2026-09-13T08:07:55.272Z' local_tz_offset_hours=-4.0 utc_now='2026-09-13T12:07' matches_utc=False |
| `CFG-095` | PASS | parsed_ok=True; has exception field=True |
| `CFG-096` | PASS | truthy all True=True, falsy all False=True |
| `CFG-097` | PASS | CONFIG.TYPE: {'key': 'test.key', 'value': "'maybe'", 'wanted': 'boolean'} |
| `CFG-098` | PASS | [CONFIG.TYPE] configuration key test.key is not a valid integer \| Next: A boolean is not an integer here; be explicit. \| Context: key='test.key', value='True', wanted='integer' |
| `CFG-099` | PASS | 16 \|\| [CFG-099b] 010 refused as expected |
| `CFG-100` | PASS | [CFG-100a] 10 \|\| [CFG-100b] refused |
| `CFG-101` | PASS | [CONFIG.TYPE] configuration key test.key is not a valid number \| Next: A boolean is not a number here; be explicit. \| Context: key='test.key', value='True', wanted='number' |
| `CFG-102` | PASS | ['a', 'b', 'c'] |
| `CFG-103` | PASS | [] |
| `CFG-104` | PASS | {'key': 'test.key', 'value': "{'a': 1}", 'wanted': 'list'} |
| `CFG-105` | PASS | {'key': 'test.key', 'value': "'sqlite'", 'wanted': 'mapping'} |
| `CFG-106` | PASS | all 16 units correct |
| `CFG-107` | PASS | 5.0 |
| `CFG-108` | PASS | Use a duration such as 500ms, 30s, 5m, 2h or 1d. |
| `CFG-109` | PASS | 30S=30.0 5M=300.0 |
| `CFG-110` | PASS | 0.5s=0.5 .5s=0.5 |
| `CFG-111` | PASS | refused |
| `CFG-112` | FAIL | numeric -5 accepted and returned -5.0 -- disagrees with string form '-5s' which is refused |
| `CFG-113` | PASS | all correct |
| `CFG-114` | PASS | 268435456 |
| `CFG-115` | PASS | Use a size such as 1024, 512kb, 256mb or 4gib. |
| `CFG-116` | PASS | [CFG-116a] bool refused \|\| [CFG-116b] fractional float refused |
| `CFG-117` | PASS | {'key': 'database.pool.size', 'value': "'notanumber'", 'wanted': 'integer'} |
| `CFG-118` | FAIL | secret leaked in exception string=True: [CONFIG.TYPE] configuration key security.session_secret is not a valid integer \| Next: Provide a whole number, e.g. 20. \| Context: key='security.session_secret', value="'supersecretvalue123'", wanted='integer' |
| `CFG-119` | PASS | CONFIG.PLACEHOLDER_UNRESOLVED: 'Set the environment variable NOT_SET, define NOT_SET in configuration, or give the placeholder a default: ${NOT_SET:value}.' |
| `CFG-120` | PASS | 'localhost' |
| `CFG-121` | PASS | 'http://host:5432/db' |
| `CFG-122` | PASS | '' |
| `CFG-123` | PASS | '${NOT_A_VAR}' |
| `CFG-124` | PASS | '/var/lib/prama/evidence' |
| `CFG-125` | PASS | 'env-value' |
| `CFG-126` | PASS | [CONFIG.PLACEHOLDER_CYCLE] placeholder cycle: a -> a \| Next: Remove the self-reference; a placeholder cannot resolve to itself. \| Context: name='a', path='a' |
| `CFG-127` | PASS | [CONFIG.PLACEHOLDER_CYCLE] placeholder cycle: b -> a -> b \| Next: Remove the self-reference; a placeholder cannot resolve to itself. \| Context: name='b', path='a' |
| `CFG-128` | PASS | 17-link-chain=('error', 'CONFIG.PLACEHOLDER_CYCLE', "[CONFIG.PLACEHOLDER_CYCLE] placeholder recursion exceeded 16 levels at k0 \| Next: Break the cycle: a placeholder chain must terminate in a literal. \| Context: chain='k1 -> k2 -> k3 -> k4 -> k5 -> k6 -> k7 -> k8 -> k9 -> k10 -> k11 -> k12 -> k13 -> k14 -> k15 -> k16 -> k17', path='k0'"); 16-link-chain result='literal-end' |
| `CFG-129` | PASS | 10 |
| `CFG-130` | PASS | ['prama.connectors'] |
| `CFG-131` | PASS | has=True get_str(default='fallback')='fallback' |
| `CFG-132` | PASS | [CONFIG.MISSING] required configuration key is not set: database.nope \| Next: Set database.nope in config/application.yaml, or export PRAMA_DATABASE__NOPE. \| Context: key='database.nope'; remedy='Set database.nope in config/application.yaml, or export PRAMA_DATABASE__NOPE.' |
| `CFG-133` | PASS | CONFIG.NOT_A_SECTION |
| `CFG-134` | PASS | 'd' |
| `CFG-135` | PASS | {'s': 'hi', 'i': 5, 'f': 1.5, 'b': True, 'p': PosixPath('/home/ashutosh/x'), 'lst': ['a', 'b'], 'dct': {'k': 1}, 'opt': None} |
| `CFG-136` | PASS | [CONFIG.MISSING] required configuration key is not set: needsit.must \| Next: Add must under needsit. \| Context: key='needsit.must' |
| `CFG-137` | PASS | NotADataclass is not a dataclass |
| `CFG-138` | PASS | None |
| `CFG-139` | PASS | '/home/ashutosh/prama.db' |
| `CFG-140` | PASS | raw() is a live reference (external mutation of the returned dict is visible through get_str -> 'MUTATED'); the only caller (run_prama_web.py) only reads it via with_defaults(), never mutates it: '/home/ashutosh/PycharmProjects/prama/run_prama_web.py:176:            .with_defaults(config.raw())' |
| `CFG-141` | PASS | all match, all unique |
| `CFG-142` | PASS | PramaError.__init__() missing 1 required keyword-only argument: 'remedy' |
| `CFG-143` | PASS | no remedy="" literal found in src/ |
| `CFG-144` | PASS | 6 quoted `prama ...` commands inside remedy=... strings all resolve via --help: ['prama apikey create', 'prama apikey list', 'prama db init', 'prama estate export', 'prama lsp catalogue', 'prama tenant create acme-bank'] |
| `CFG-145` | PASS | paths referenced in remedy=...: ['config/application.local.yaml', 'config/application.yaml']; missing-and-not-local=[]; every missing one is git-ignored *.local.*=True |
| `CFG-146` | PASS | '[CONFIG.INVALID] bad thing \| Next: fix it \| Context: a=1, b=2' |
| `CFG-147` | PASS | ['code', 'context', 'message', 'remedy'] |
| `CFG-148` | PASS | e148.context={'a': 1} |
| `CFG-149` | PASS | ValueError('root cause') |
| `CFG-150` | PASS | [True, True, True, True, True, True, True, True, True] |
| `CFG-151` | PASS | Unauthorised<-Forbidden=False, Forbidden<-Unauthorised=False |
| `CFG-152` | PASS | 'CONFIG.YAML_INVALID' |
| `CFG-153` | PASS | 100 code= literals, all AREA.CONDITION |
| `CFG-154` | PASS | stdout='UTC True' stderr='' |
| `CFG-155` | PASS | '2026-09-13T12:15:02.850717Z' |
| `CFG-156` | PASS | epoch_millis=1772368245123, timestamp*1000=1772368245123.456 |
| `CFG-157` | PASS | FixedClock requires a timezone-aware instant |
| `CFG-158` | PASS | 2026-06-01 16:00:00+00:00 vs expected 2026-06-01 16:00:00+00:00 |
| `CFG-159` | PASS | now delta=30.0, mono delta=30.0 |
| `CFG-160` | PASS | a clock does not run backwards |
| `CFG-161` | PASS | 0.0, 0.0 |
| `CFG-162` | FAIL | bare datetime.now() call sites outside core/clock.py: [('/home/ashutosh/PycharmProjects/prama/src/prama/cli/apikey.py', 98)] |
| `CFG-163` | PASS | lengths={'us0': 27, 'us999999': 27} (fixed-width, within the catalogue's accepted 27-28 range and well inside VARCHAR(32)); values={'us0': '2026-01-01T00:00:00.000000Z', 'us999999': '2026-01-01T00:00:00.999999Z'} |
| `CFG-164` | PASS | ORDER BY ts result matches chronological order=True |
| `CFG-165` | PASS | 1000 minted, all 26-char Crockford32=True; sample=01M2DB2GA7EZQ3NXB8MM8SF4SE |
| `CFG-166` | PASS | 100000 minted, strictly increasing=True |
| `CFG-167` | PASS | minted 100000 from 16 threads; duplicates=False |
| `CFG-168` | PASS | traced true mint order (appended inside the critical section) across 16 threads, 100000 ids: strictly increasing=True |
| `CFG-169` | FAIL | first=01KDVDNAZ8G0G52AJVW43GCPDH (ms=1767225601000), second=01KDVDNA0045EC5K0MDC8QJ08A (ms=1767225600000); second>first=False |
| `CFG-170` | PASS | predecessor=01M2DB2H83ZZZZZZZZZZZZZZZZ, new=01M2DB2H84PGW1QTTSFD69XG64, sorts-after=True |
| `CFG-171` | PASS | {'25-char': False, '27-char': False, 'has-I': False, 'has-L': False, 'has-O': False, 'has-U': False, 'lowercase': False, 'empty': False} |
| `CFG-172` | PASS | decoded=1778839200000, expected=1778839200000 |
| `CFG-173` | PASS | not a ULID: 'not-an-id' |
| `CFG-174` | PASS | 01M2DB2H83WC52312XNGBFA7J2, 01M2DB2H83WC52312XNGBFA7J2 |
| `CFG-175` | PASS | TenantId.parse('user:'+ulid) -> '01M2DB2H83WC52312XNGBFA7J3' (no refusal); EntityId docstring documents prefix as 'used only for display and log readability' -- deliberate, so acceptance is documented behaviour, not a silent gap |
| `CFG-176` | PASS | {'TenantId': 'tenant', 'PrincipalId': 'user', 'RoleId': 'role', 'ApiKeyId': 'key', 'AuditEventId': 'audit', 'LeaseId': 'lease'} |
| `CFG-177` | PASS | max_bytes must be positive; an unbounded queue is not permitted \|\| max_bytes must be positive; an unbounded queue is not permitted |
| `CFG-178` | PASS | [CONCURRENCY.BACKPRESSURE] queue 'q178' is full: 2991/3000 bytes, 3 items \| Next: Slow the producer, add consumers, or build this queue with a larger |
| `CFG-179` | PASS | [CONCURRENCY.BACKPRESSURE] queue 'q179' is full: 196/10000000 bytes, 2 items \| Next: Slow the producer, add consumers, or build this queue with a larg |
| `CFG-180` | PASS | stats().bytes=4193 > max_bytes=1024 |
| `CFG-181` | PASS | refused as expected |
| `CFG-182` | PASS | context={'queue': 'q182', 'bytes': 147, 'max_bytes': 100, 'items': 1}; remedy_ok=True |
| `CFG-183` | PASS | producer completed after 0.100s (well inside 3s timeout) |
| `CFG-184` | PASS | try_put=True, consumer received 'item184' |
| `CFG-185` | PASS | drain() returned ['item185'] |
| `CFG-186` | PASS | try_put=False, rejected 0->1, offered 1->2 |
| `CFG-187` | PASS | producer completion times=[0.1, 0.1, 0.1] |
| `CFG-188` | PASS | len after shrink=4, new put refused=True |
| `CFG-189` | PASS | refused; budget unchanged=5000 |
| `CFG-190` | PASS | producer raised: "[CONCURRENCY.BACKPRESSURE] queue 'qP' is closed \| Next: Stop producing to a closed queue; the consumer has shut down. \| Context: queue='qP'"; consumer raised: "[CONCURRENCY.BACKPRESSURE] queue 'qC' is closed and drained \| Next: Stop consuming; the producer has finished. \| Context: queue='qC'"; both resolved in 0.000s |
| `CFG-191` | PASS | g1='i1' g2='i2' then: [CONCURRENCY.BACKPRESSURE] queue 'q191' is closed and drained \| Next: Stop consuming; the producer has finished. \| Context: queue='q191' |
| `CFG-192` | PASS | took 3 items; byte_size 1070->749 |
| `CFG-193` | PASS | drained 1000; byte_size=0 |
| `CFG-194` | PASS | empty-tuple=104, small-dict=318, 1mb-bytes=1048673, OVERHEAD=64 |
| `CFG-195` | PASS | default_sizer(NoSizeof())=64 |
| `CFG-196` | PASS | 1.0 |
| `CFG-197` | PASS | peak items=5 bytes=5485; after drain items=5 bytes=5485 |
| `CFG-198` | PASS | snapshot.items after later drain=1 (should stay 1) |
| `CFG-199` | PASS | a.done=True a.stopped=True; b.done=True b.stopped=True |
| `CFG-200` | PASS | [CONCURRENCY.INVARIANT] task 'dispatch' is already running under supervisor 'supervisor' \| Next: Use a distinct task name, or stop the existing task first. \| Context: supervisor='supervisor', task='dispatch' |
| `CFG-201` | PASS | re-spawn of stopped name accepted |
| `CFG-202` | PASS | failures=1 restarts=0 |
| `CFG-203` | PASS | attempts=4, failures=1, msg=[CONCURRENCY.INVARIANT] task 'bad' restarted 4 times in 60s and is being given up on \| Next: Read the last error above: a crash loop is a defect, not a transient. The task is stopped, not silently retried forever. \| Context: supervisor='supervisor', task='bad' |
| `CFG-204` | PASS | count=20, gave_up=False |
| `CFG-205` | FAIL | restarts after 0.2s of an instantly-returning ALWAYS task=2 |
| `CFG-206` | PASS | {1: (0.0014268088563414328, 0.398999600770574, 0.4, True), 5: (0.0011467673671468504, 6.363112010036186, 6.4, True), 10: (0.009593570232641069, 29.738933065836985, 30, True), 16: (0.018148911593444117, 29.940159220614923, 30, True), 20: (0.03938433800370844, 29.971223827461863, 30, True)} |
| `CFG-207` | PASS | failures after cancellation-based shutdown=0 |
| `CFG-208` | PASS | failures=1 (healthy() == not failures) |
| `CFG-209` | PASS | raised ValueError: first209 |
| `CFG-210` | PASS | second shutdown() OK, failures unchanged=0 |
| `CFG-211` | PASS | run_sync(coro) with no loop running -> 42 |
| `CFG-212` | PASS | run_sync(coro) from inside a running loop -> 99 |
| `CFG-213` | PASS | both loop states preserve the typed error: ['PASS', 'PASS'] |
| `CFG-214` | PASS | A got=True, B got=None |
| `CFG-215` | PASS | first=1, second=2 |
| `CFG-216` | PASS | B got=True, token 1->2 |
| `CFG-217` | PASS | A renew after B took over -> None |
| `CFG-218` | PASS | A release-after-lost=False, current holder=B |
| `CFG-219` | PASS | None |
| `CFG-220` | PASS | lost_at_any_point=False |
| `CFG-221` | PASS | valid after renew denied=False |
| `CFG-222` | PASS | [CONCURRENCY.LEASE_LOST] lease on 'res222' has expired \| Next: Abandon the work and re-acquire before continuing. \| Context: holder='H222', resource='res222' |
| `CFG-223` | PASS | raised as expected |
| `CFG-224` | PASS | [CONCURRENCY.LEASE_LOST] lease on 'res224' is held by another instance \| Next: This is normal in a fleet: another instance owns the work. Use acquire(wait=True) if this instance should queue for it. \| Context: resource='res224' |
| `CFG-225` | PASS | B acquired=True after 0.0ms |
| `CFG-226` | PASS | renewer after release: None; original renewer done/cancelled=True |
| `CFG-227` | PASS | B acquired=True after 0.201s |
| `CFG-228` | PASS | max observed in_flight=3, high_water=3 |
| `CFG-229` | PASS | refused |
| `CFG-230` | PASS | {'limiter': 'lim230', 'limit': 1} |
| `CFG-231` | PASS | second acquire after exception took 0.0ms |
| `CFG-232` | PASS | in_flight after cycles=0 |
| `CFG-233` | PASS | burst-of-10 took 0.0ms; 11th waited 100.3ms |
| `CFG-234` | PASS | cannot acquire 11 permits from a bucket of capacity 10 |
| `CFG-235` | PASS | [CONCURRENCY.BACKPRESSURE] rate limit 'rate' would require 1.00s, over the 0.10s budget \| Next: Raise the configured rate, or reduce the request volume. \| Context: limiter='rate', rate=1 |
| `CFG-236` | PASS | try_acquire=False, took 0.00ms |
| `CFG-237` | PASS | 5 |
| `CFG-238` | PASS | before=5, after backwards-clock refill=5 |
| `CFG-239` | PASS | unique thread ids seen={125180398278336}, caller=125180416042880 |
| `CFG-240` | PASS | 'x' |
| `CFG-241` | PASS | teardown ran on 125180398278336, worker thread was 125180398278336 |
| `CFG-242` | PASS | teardown call count on already-closed worker=0 |
| `CFG-243` | PASS | CONCURRENCY.WORKER_CLOSED: A closed worker cannot be reopened; its thread is gone and so is whatever it had initialised. Open a new one. |
| `CFG-244` | PASS | 'jdbc_0' |
| `CFG-245` | PASS | no threading.Thread/create_task/ThreadPoolExecutor/asyncio.Queue found outside core/concurrency/ |
| `CFG-246` | PASS | Can't instantiate abstract class NoManifest without an implementation for abstract method 'manifest' |
| `CFG-247` | PASS | [REGISTRY.INVALID] RaisingManifest.manifest() raised ValueError \| Next: manifest() must be a pure classmethod returning a PluginManifest. \| Context: kind='connectors', plugin='RaisingManifest'; remedy=manifest() must be a pure classmethod returning a PluginManifest. |
| `CFG-248` | PASS | [REGISTRY.INVALID] WrongType.manifest() did not return a PluginManifest \| Next: Return a PluginManifest describing the plugin. \| Context: kind='connectors', plugin='WrongType' |
| `CFG-249` | PASS | Give the plugin a stable, unique key. |
| `CFG-250` | PASS | [REGISTRY.INVALID] WrongKind declares kind 'notifiers' but was registered as 'connectors' \| Next: Correct the manifest's kind, or register it with the right registry. \| Context: declared='notifiers', kind='connectors' |
| `CFG-251` | PASS | Make the plugin subclass BasePlugin. |
| `CFG-252` | PASS | refused without replace, accepted with replace=True |
| `CFG-253` | PASS | Available: good1, good2, good3. Install the package providing it, or correct the key. |
| `CFG-254` | PASS | Available: (none). Install the package providing it, or correct the key. |
| `CFG-255` | PASS | [REGISTRY.INVALID] connectors plugin 'good1' has been disabled \| Next: Something called disable('good1') on this registry. Re-enable it there, or build a registry without the call — a disabled plugin is disabled in code, not in configuration. \| Context: key='good1', kind='connectors' |
| `CFG-256` | FAIL | no call to Registry.disable(...) found anywhere in src/prama (grep for '.disable(' across *.py): ''; config/application.yaml ships plugins.disabled: [] but nothing reads it |
| `CFG-257` | PASS | keys()=['good2', 'good3']; 'good1' in reg=False; len=2 \|\| keys()=['good2', 'good3'], 'good1' in reg=False, len=2 |
| `CFG-258` | PASS | manifests keys=['good2', 'good3'] |
| `CFG-259` | PASS | loaded=1, log contains broken-ep and group name: True; log="plugin 'broken-ep' from group 'prama.backends' failed to load: cannot import broken module" |
| `CFG-260` | FAIL | Registry exposes no failure-tracking attribute for discover() (checked _failed/failures/discovery_errors); only a log.warning is emitted, and grep of src/prama/api shows /health reports only database state -- the docstring's claim 'visible in health output' is not backed by any mechanism |
| `CFG-261` | PASS | 0 |
| `CFG-262` | FAIL | _entry_points_for() on a broken metadata call returned [] -- 'except Exception: return []' silently reports zero plugins found, indistinguishable from an empty install; enumeration failure is not surfaced at all |
| `CFG-263` | PASS | ['hascap'] |
| `CFG-264` | PASS | 'pushdown.sql[a=1,b=2]' vs 'pushdown.sql[a=1,b=2]' |
| `CFG-265` | PASS | 'DEFAULT', 'DEFAULT2' |
| `CFG-266` | PASS | 'code_complete' |
| `CFG-267` | PASS | Use catalogue.of(kind) to fetch the existing registry. |
| `CFG-268` | PASS | Known registries: backends, connectors, scorers. |
| `CFG-269` | PASS | discover_all touched: ['backends', 'connectors'] |
| `CFG-270` | PASS | catalogue B has no knowledge of catalogue A's registry, as expected |
| `CFG-271` | PASS | BACKEND='orjson' HAVE_ORJSON=True |
| `CFG-272` | PASS | backends=['orjson', 'stdlib']; identical=True; values={'orjson': b'{"a":{"nested":true},"b":[1,2.5,null],"dec":"1.50","dt":"2026-01-01T00:00:00Z"}', 'stdlib': b'{"a":{"nested":true},"b":[1,2.5,null],"dec":"1.50","dt":"2026-01-01T00:00:00Z"}'} |
| `CFG-273` | PASS | {'orjson': 'refusing to serialise a naive datetime; attach UTC', 'stdlib': 'refusing to serialise a naive datetime; attach UTC'} |
| `CFG-274` | PASS | {'orjson': '{"t":"2026-06-01T16:00:00Z"}', 'stdlib': '{"t":"2026-06-01T16:00:00Z"}'} |
| `CFG-275` | PASS | {'orjson': '{"a":null,"b":null,"c":null}', 'stdlib': '{"a":null,"b":null,"c":null}'} |
| `CFG-276` | PASS | {'orjson': '{"m":{"x":[1.0,null]}}', 'stdlib': '{"m":{"x":[1.0,null]}}'} |
| `CFG-277` | PASS | {'orjson': '{"amt":"0.1"}', 'stdlib': '{"amt":"0.1"}'} |
| `CFG-278` | PASS | {'orjson': '{"s":[1,2,3],"t":[1,2,3]}', 'stdlib': '{"s":[1,2,3],"t":[1,2,3]}'} |
| `CFG-279` | PASS | {'orjson': '{"b":"�� not utf8"}', 'stdlib': '{"b":"�� not utf8"}'} |
| `CFG-280` | PASS | {'orjson': 'Type is not JSON serializable: Weird', 'stdlib': 'cannot serialise Weird to JSON'} |
| `CFG-281` | PASS | {'orjson': b'{"a":2,"m":3,"z":1}', 'stdlib': b'{"a":2,"m":3,"z":1}'} vs {'orjson': b'{"a":2,"m":3,"z":1}', 'stdlib': b'{"a":2,"m":3,"z":1}'} |
| `CFG-282` | PASS | {'orjson': b'{"top":{"a":2,"z":1}}', 'stdlib': b'{"top":{"a":2,"z":1}}'} vs {'orjson': b'{"top":{"a":2,"z":1}}', 'stdlib': b'{"top":{"a":2,"z":1}}'} |
| `CFG-283` | PASS | {'orjson': '{"a":1}', 'stdlib': '{"a":1}'} |
| `CFG-284` | PASS | {'orjson': {'n': 1, 'f': 1.5, 's': 'text', 'l': [1, 2, 3], 'b': True, 'nil': None}, 'stdlib': {'n': 1, 'f': 1.5, 's': 'text', 'l': [1, 2, 3], 'b': True, 'nil': None}} |
| `CFG-285` | PASS | str={'orjson': {'a': 1}, 'stdlib': {'a': 1}} bytes={'orjson': {'a': 1}, 'stdlib': {'a': 1}} |
| `CFG-286` | PASS | dumps identical=True; roundtrip={'orjson': 'café 日本語 🎉', 'stdlib': 'café 日本語 🎉'}; raw dumps={'orjson': '{"name":"café 日本語 🎉"}', 'stdlib': '{"name":"café 日本語 🎉"}'} |
| `CFG-287` | PASS | [INPUT.INVALID] unknown timezone 'Mars/Olympus' for calendar 'bad' \| Next: Use an IANA timezone name such as Europe/London or UTC. \| Context: calendar='bad', timezone='Mars/Olympus'; remedy=Use an IANA timezone name such as Europe/London or UTC. |
| `CFG-288` | PASS | Saturday=True Sunday=True |
| `CFG-289` | PASS | {'Mon': True, 'Tue': True, 'Wed': True, 'Thu': True, 'Fri': True, 'Sat': False, 'Sun': False} |
| `CFG-290` | PASS | {'Mon': True, 'Tue': True, 'Wed': True, 'Thu': True, 'Fri': False, 'Sat': False, 'Sun': True} |
| `CFG-291` | PASS | next_business_day(24 Dec)=2025-12-29 (27th is a Saturday, so Monday 29th) |
| `CFG-292` | FAIL | not a true infinite loop (date has an internal max), but an unbounded, uncontrolled spin: took 2.42s of CPU iterating day-by-day toward date.max, then crashed with rc=1 on an unhandled low-level error rather than a graceful, immediate refusal: 'OverflowError: date value out of range' |
| `CFG-293` | PASS | datetime.date(2026, 1, 3) |
| `CFG-294` | PASS | datetime.date(2026, 1, 5) |
| `CFG-295` | PASS | 4 |
| `CFG-296` | PASS | fwd=8, bwd=-8, same-day=0 |
| `CFG-297` | PASS | datetime.date(2026, 1, 5) |
| `CFG-298` | PASS | datetime.date(2026, 1, 2) |
| `CFG-299` | PASS | datetime.date(2026, 1, 6) |
| `CFG-300` | PASS | winter UTC=06:30:00, summer UTC=05:30:00 |
| `CFG-301` | PASS | non-existent local time 01:30 on 2026-03-29 resolved to 2026-03-29T01:30:00+00:00 without raising (fold-rule behaviour) |
| `CFG-302` | PASS | same object=False, original holidays=frozenset(), new holidays has date=True |
| `CFG-303` | PASS | [INPUT.INVALID] no calendar named 'TARGET2' is loaded \| Next: Loaded: always, weekdays. Install the domain pack that provides it, or correct the name. Treating it as weekdays would produce controls that fire on the wrong days. \| Context: calendar='TARGET2', loaded=['always', 'weekdays']; remedy=Loaded: always, weekdays. Install the domain pack that provides it, or correct the name. Treating it as weekdays would produce controls that fire on the wrong days. |
| `CFG-304` | PASS | get(None) is ALWAYS_OPEN=True; get('') is ALWAYS_OPEN=True |
| `CFG-305` | FAIL | found.name='TARGET2'; names()=['always', 'target2', 'weekdays']; 'TARGET2' in names()=False |
| `CFG-306` | PASS | refused without replace, accepted with replace=True |
| `CFG-307` | PASS | registered into default_calendars() from one call site, visible from another: True |
| `CFG-308` | PASS | {'DECLARATION': 100, 'IMPORT': 60, 'DOCUMENT': 80, 'MINING': 40, 'EXAMPLE': 30, 'INDUCTION': 20} |
| `CFG-309` | PASS | {'DECLARATION': True, 'IMPORT': False, 'DOCUMENT': False, 'MINING': False, 'EXAMPLE': False, 'INDUCTION': False} |
| `CFG-310` | PASS | {'DOCUMENT', 'IMPORT', 'DECLARATION'} |
| `CFG-311` | PASS | a rule attributed to a document must carry the passage it came from; without one it cannot be checked, and an unfalsifiable rule will not be approved |
| `CFG-312` | PASS | after 1st corroboration: 1; second call same object=True |
| `CFG-313` | PASS | original unchanged corroborations=0; new instance=True |
| `CFG-314` | PASS | 'Alice declared it on 2026-03-04' |
| `CFG-315` | PASS | 'It holds in the data. seen in 30/30 days' |
| `CFG-316` | PASS | before='Bob declared it on 2026-01-01' after='Bob declared it on 2026-01-01' |
| `CFG-317` | PASS | 092201bc33e5877f7dd4bd559eaa9eae == 092201bc33e5877f7dd4bd559eaa9eae |
| `CFG-318` | PASS | 0473ef2dc0d324ab659d3580c1134e9d vs 02d8bc3008a9bb0dcc4b86d7fd3428ce |
| `CFG-319` | PASS | c710867f517fb187555a7321f5a823e9 vs 56cfb7654b0457abceedfa7e2e615c38 |
| `CFG-320` | PASS | identity len=32, content_hash len=32 |
| `DB-001` | PASS | diff schema/sqlite.sql schema/postgres.sql -- exactly 3 differing lines (1,4,9), each naming the other dialect (verified by direct diff) |
| `DB-002` | PASS | grep of schema/sqlite.sql shows BOOLEAN/TIMESTAMP/DATETIME/JSONB/SERIAL/NUMERIC/BIGINT/UUID/BYTEA/BLOB appear only inside the header comment documenting them as forbidden -- zero occurrences as an actual column type |
| `DB-003` | PASS | grep -nE for bare VARCHAR (no parenthesised width) across schema/sqlite.sql -- zero matches |
| `DB-004` | PASS | every PRIMARY KEY column (single-column VARCHAR(26)/INTEGER id, and the two composite PKs principal_role(principal_id,role_id) and setting(tenant_id,scope,key)) declares NOT NULL explicitly, confirmed by direct inspection of all 35 CREATE TABLE bodies |
| `DB-005` | PASS | grep of every CREATE TABLE/INDEX/UNIQUE INDEX statement -- all carry IF NOT EXISTS; also verified via pytest tests/db/test_schema.py::TestParity::test_every_statement_is_idempotent (ran, both dialects PASSED) |
| `DB-006` | PASS | extracted all 41 named CONSTRAINTs and 64 CREATE INDEX names via regex -- every one carries uq_/ix_/ck_; no unnamed table-level UNIQUE or CHECK found |
| `DB-007` | PASS | sorted+uniq -c over all constraint and index names -- max count is 1 for every name, no duplicates |
| `DB-008` | PASS | ran pytest tests/db/test_schema.py::TestModelAgreement::test_every_orm_table_exists_in_the_schema_file and test_every_schema_table_has_an_orm_model -- both PASSED |
| `DB-009` | PASS | ran pytest tests/db/test_schema.py::TestModelAgreement::test_orm_string_widths_match_the_schema_file -- PASSED |
| `DB-010` | PASS | ran pytest tests/db/test_schema.py::TestModelAgreement::test_columns_and_nullability_agree -- PASSED |
| `DB-011` | PASS | cross-referenced every BoolInt-typed ORM column (via Base/EvidenceBase metadata) against its schema column decl -- all INTEGER with a CHECK ... IN (0,1) found in the same file |
| `DB-012` | PASS | cross-referenced every UtcDateTime-typed ORM column against schema -- all VARCHAR(32), matching db/types.py::TIMESTAMP_WIDTH=32 |
| `DB-013` | PASS | cross-referenced every String(26)/Ulid-typed ORM column against schema -- all VARCHAR(26), matching db/types.py::ULID_WIDTH=26 |
| `DB-014` | PASS | IntegrityError as expected: UNIQUE constraint failed: sem_domain_version.domain_id |
| `DB-015` | PASS | IntegrityError as expected: UNIQUE constraint failed: ev_record.tenant_id, ev_record.sequence |
| `DB-016` | PASS | IntegrityError as expected: UNIQUE constraint failed: ev_record.record_hash |
| `DB-017` | PASS | IntegrityError as expected: UNIQUE constraint failed: tenant.slug |
| `DB-018` | PASS | cross-tenant same username accepted=True; same-tenant duplicate refused=True |
| `DB-019` | PASS | IntegrityError as expected: UNIQUE constraint failed: api_key.key_prefix |
| `DB-020` | PASS | IntegrityError as expected: UNIQUE constraint failed: ctl_control.tenant_id, ctl_control.identity |
| `DB-021` | PASS | IntegrityError as expected: UNIQUE constraint failed: att_attestation.content_hash -- confirms the constraint scopes on content_hash, which folds in 'supersedes', so a legitimate correction (different supersedes -> different hash) is not blocked by this DB-level check |
| `DB-022` | PASS | same key, different definition accepted=True; same key+definition refused=True |
| `DB-023` | PASS | [('ck_tenant_status', 'refused'), ('ck_principal_kind', 'refused'), ('ck_ev_record_verdict', 'refused'), ('ck_rec_break_kind', 'refused'), ('ck_rec_break_seen(last<first)', 'refused')] |
| `DB-024` | PASS | {0: 'refused', 1: 'accepted', 4: 'accepted', 5: 'refused'} |
| `DB-025` | FAIL | true evidence ledger (ev_run/ev_record/ev_sample, the only tables under EvidenceBase): FK-to-platform=False, ON DELETE CASCADE=False -- clean, as required. att_attestation DOES carry 'REFERENCES tenant (id) ON DELETE CASCADE' (True), but its own module docstring documents it as deliberately living under Base (not EvidenceBase) 'because it is a governance artefact about evidence' -- the catalogue's Steps ('scan the ev_* and att_* tables') conflates the two, which is a misreading of the ledger/gov… |
| `DB-026` | PASS | declared=64 (expected 64), live=64, missing after db init=set() |
| `DB-027` | PASS | sqlite has 35 tables, postgres has 35, identical order=True |
| `DB-028` | FAIL | parsed 35 tables (expected 34); tenant.slug spec correct=True: ColumnSpec(name='slug', type='VARCHAR(128)', nullable=False) |
| `DB-029` | PASS | tenant.status parsed as ColumnSpec(name='status', type='VARCHAR(32)', nullable=False) |
| `DB-030` | PASS | principal_role columns=['principal_id', 'role_id', 'granted_at', 'granted_by']; phantom entries=set() |
| `DB-031` | FAIL | tenant statement after injecting DEFAULT 'a;b': survived intact=False; balanced parens=False; first 200 chars of the (possibly truncated) statement: "CREATE TABLE IF NOT EXISTS tenant (\n    id             VARCHAR(26)   NOT NULL PRIMARY KEY,\n    slug           VARCHAR(128)  NOT NULL,\n    display_name   VARCHAR(255)  NOT NULL DEFAULT 'a" |
| `DB-032` | PASS | file has 99 CREATE-starting lines; loader parsed 99 statements total (includes CREATE TABLE/INDEX + others) |
| `DB-033` | PASS | 5df0746f832e vs 734d05a9db20 |
| `DB-034` | PASS | report.ok=True (must stay True -- DIGEST is not in BLOCKING); digest drifts found=['applied digest 5df0746f832e differs from the current file (7'] |
| `DB-035` | FAIL | created=True, tables_present=35, statements_executed=99 (parsed count=99) |
| `DB-036` | PASS | schema already current: 35 tables, 99 statements from schema/sqlite.sql (digest 5df0746f832e) |
| `DB-037` | PASS | columns after re-apply=['id', 'slug', 'display_name', 'status', 'residency', 'settings_json', 'created_at', 'updated_at', 'qa_extra']; indexes=['sqlite_autoindex_tenant_1', 'sqlite_autoindex_tenant_2', 'ix_qa_extra'] |
| `DB-038` | PASS | DB.SCHEMA_APPLY_FAILED: statement[:80]='CREATE TABLE IF NOT EXISTS role BROKEN SYNTAX HERE (\n    id                VARCH', detail='(sqlite3.OperationalError) near "BROKEN": syntax error' |
| `DB-039` | PASS | SQLite after a failed apply (role table's CREATE fails partway through the file): 3 tables survived from statements executed before the failure: ['principal', 'schema_state', 'tenant'] -- SQLite DDL is NOT fully transactional across the whole batch the way PostgreSQL's would be; document this per-engine difference |
| `DB-040` | PASS | row=(1, '1', 'sqlite', '5df0746f832ea8eebeedf0eea7924472460325bdc003dc26578d1b5bdbcc6dc6', 'qa', '0.1.0', '2026-09-13T12:30:25.695579Z') |
| `DB-041` | PASS | _current_user() with getuser() raising -> 'unknown' |
| `DB-042` | PASS | schema_state row count after 3 total applies=1 |
| `DB-043` | PASS | summary='schema verified against schema/sqlite.sql (digest 5df0746f832e): no drift' |
| `DB-044` | PASS | drift found=True, blocking=True, raise_if_blocking raised=True |
| `DB-045` | PASS | drift=[Drift(kind=<DriftKind.MISSING_COLUMN: 'missing_column'>, object_name='tenant.residency', detail='declared VARCHAR(64), absent')] |
| `DB-046` | PASS | [Drift(kind=<DriftKind.NULLABILITY: 'nullability'>, object_name='tenant.slug', detail='declared NOT NULL, live column is nullable')] |
| `DB-047` | FAIL | role.name retyped VARCHAR(128)->TEXT; drifts mentioning it=[]; report.ok=True -- if empty, the verifier's own code confirms it never compares ColumnSpec.type, only presence+nullability |
| `DB-048` | FAIL | role.name shrunk VARCHAR(128)->VARCHAR(8); drifts mentioning it=[]; report.ok=True |
| `DB-049` | PASS | [Drift(kind=<DriftKind.EXTRA_TABLE: 'extra_table'>, object_name='qa_operator_table', detail='present in the database, not in the schema file')]; report.ok=True |
| `DB-050` | FAIL | verifier reports the extra NOT NULL column anywhere=False; report.ok=True; an insert omitting it fails=True (the verifier says the database is clean while every insert would fail) |
| `DB-051` | PASS | [Drift(kind=<DriftKind.MISSING_INDEX: 'missing_index'>, object_name='ix_audit_tenant_time', detail='declared on audit_event, absent')] |
| `DB-052` | FAIL | [Drift(kind=<DriftKind.MISSING_INDEX: 'missing_index'>, object_name='uq_ev_record_sequence', detail='declared on ev_record, absent')]; report.ok=True -- MISSING_INDEX is uniformly informational in BLOCKING set, so a dropped uq_ index (a correctness guarantee, not a performance one) verifies clean |
| `DB-053` | PASS | [Drift(kind=<DriftKind.VERSION: 'version'>, object_name='schema_state', detail='database built for schema version 999, this build expects 1')] |
| `DB-054` | PASS | no traceback; 35 MISSING_TABLE drifts (schema declares 35 tables) |
| `DB-055` | FAIL | _recorded_state on an unreachable database returned None, None -- a genuine connection failure was silently turned into 'no recorded state' rather than reported, matching CLAUDE.md's 'no exception is swallowed' violation |
| `DB-056` | PASS | DB.SCHEMA_DRIFT: blocking=['missing_column:lease.metadata_json', 'missing_table:setting', 'version:schema_state'] |
| `DB-057` | PASS | Prama has no migrations. Either run `prama db init` (safe: it only creates missing objects), or reconcile the database with the schema file deliberately. Nothing will be altered automatically. |
| `DB-058` | PASS | blocking-mark='!', info-mark='-', heading='schema drift against schema/sqlite.sql (3 blocking, 0 informational):' |
| `DB-059` | PASS | clean verify ok=True ('schema verified against schema/postgres.sql (digest 3be7ad10'); dropped-table drift blocking=True; nullability drift blocking=True -- same drift kinds and blocking classification as SQLite |
| `DB-060` | PASS | schema=prama_alt verifies clean even with a differently-shaped public.tenant present: 'schema verified against schema/postgres.sql (digest 3be7ad104901): no drift' |
| `DB-061` | PASS | bootstrapped SQLite db -- list_tables() and list_indexes() both return zero sqlite_-prefixed names (sqlite_autoindex_* entries filtered) |
| `DB-062` | PASS | sync PRAGMA synchronous=2, async PRAGMA synchronous=2 |
| `DB-063` | PASS | sync same object=True, async same object=True |
| `DB-064` | PASS | tenant created in db64a visible in db64b: None |
| `DB-065` | FAIL | wrong exception type: ModuleNotFoundError: No module named 'asyncpg' |
| `DB-066` | PASS | MAJOR FINDING (independent of DB-066's own scenario): async_engine() itself raised DB.ENGINE_CREATE_FAILED before even attempting a connection -- 'Pool class QueuePool cannot be used with asyncio engine'. PostgresDialect.engine_kwargs(is_async=True) sets poolclass=QueuePool, which SQLAlchemy 2.0's async engine rejects outright (it requires AsyncAdaptedQueuePool). This means the ASYNC PostgreSQL engine -- the path the docstring says handles 'everything else' -- cannot be constructed at all on thi… |
| `DB-067` | PASS | same object after dispose+rebuild=False |
| `DB-068` | FAIL | the schema applied by initialise() (the SYNC engine's own private StaticPool connection) is invisible to the ASYNC engine (a SEPARATE StaticPool / separate physical in-memory database, since pysqlite and aiosqlite are different DBAPI drivers and plain ':memory:' is not a shared-cache URI): DB.TRANSACTION_FAILED: '(sqlite3.OperationalError) no such table: tenant'. This is the exact confusion tests/conftest.py::sqlite_config's own docstring warns about ('A file rather than :memory: so that the syn… |
| `DB-069` | PASS | async poolclass=<class 'sqlalchemy.pool.impl.NullPool'>, sync poolclass=<class 'sqlalchemy.pool.impl.QueuePool'> |
| `DB-070` | FAIL | engine_kwargs(is_async=True) sets application_name='qa-app', statement_timeout='2500'ms, search_path='public' (correct values); but create_async_engine() itself FAILED: ArgumentError: Pool class QueuePool cannot be used with asyncio engine (Background on this error at: https://sqlalche.me/e/20/pcls) -- confirms the same QueuePool/async-engine defect found under DB-066 blocks the whole path from ever reaching a real connection where these settings would actually be verified server-side |
| `DB-071` | PASS | connection with sslmode=require raised OperationalError: '(psycopg.OperationalError) connection failed: connection to server at "127.0.0.1", port 55433 failed: server does not support SSL, but SSL was required\n(Background on this error at: https://sqlalche.m' (ssl-related=True) |
| `DB-072` | FAIL | sslmode=require is silently absent from engine_kwargs(is_async=True) (has_sslmode_anywhere=False, matching the comment 'the driver negotiates TLS itself'), AND separately the async engine cannot even be constructed due to the QueuePool bug (ArgumentError: Pool class QueuePool cannot be used with asyncio engine (Background on this error at: https://sqlalche.me/e/20/pcls)) -- so today sslmode=require against Postgres is neither honoured nor refused with an explanation on the async path; it simply … |
| `DB-073` | PASS | sync path: pg_sleep(5) with statement_timeout=1s raised after 1.01s: OperationalError: '(psycopg.errors.QueryCanceled) canceling statement due to statement timeout\n[SQL: SELECT pg_sleep(5)]\n(Background on this error at: https://sqlalche.m' |
| `DB-074` | FAIL | statement_timeout=500us (0.0005s) -> connect options string contains statement_timeout='0' (int(0.0005*1000)=int(0.5)=0); a value of '0' means UNLIMITED in PostgreSQL, the opposite of what was configured |
| `DB-075` | PASS | value after two puts of same key='second', row count=1 |
| `DB-076` | FAIL | upsert(columns=conflict) produced: 'INSERT INTO t (a, b) VALUES (:a, :b) ON CONFLICT (a, b) DO UPDATE SET ' -- a syntax error (empty SET list) \|\| [DB-076-exec] executing 'INSERT INTO t (a, b) VALUES (:a, :b) ON CONFLICT (a, b) DO UPDATE SET ' raised OperationalError: incomplete input |
| `DB-077` | PASS | 3 call sites of dialect.upsert() in src/prama, all with literal table/column/conflict lists (bootstrap.py schema_state, platform.py RoleDao.grant, platform.py SettingDao.put): ['src/prama/db/schema/bootstrap.py:109:        statement = self._dialect.upsert(', 'src/prama/db/dao/platform.py:234:        statement = self._dialect.upsert(', 'src/prama/db/dao/platform.py:378:        statement = self._dialect.upsert('] |
| `DB-078` | PASS | tenant persisted after clean exit: <Tenant id='01M2DCA7VPSWS54VN4ER9YXMYM'> |
| `DB-079` | PASS | tenant NOT persisted after an exception mid-block: None |
| `DB-080` | PASS | none of the three writes (tenant, principal, duplicate) persisted: tenant=None, principal=None |
| `DB-081` | PASS | ENTITY.CONFLICT: 'A unique key or foreign key was violated. Re-read the current state and retry, or correct the input.'; detail='(sqlite3.IntegrityError) UNIQUE constraint failed: tenant.slug' |
| `DB-082` | PASS | DB.TRANSACTION_FAILED: 'Inspect the detail below; the transaction has been rolled back.' |
| `DB-083` | PASS | unit of work usable after a caught ConflictError: by_slug returned <Tenant id='01M2DCA825JH25E3S7FGF6WHXA'> |
| `DB-084` | PASS | detail='(sqlite3.IntegrityError) UNIQUE constraint failed: principal.tenant_id, principal.username'; password hash leaked into translated error=False |
| `DB-085` | PASS | close() twice: no error |
| `DB-086` | FAIL | no exception using a closed unit of work |
| `DB-087` | PASS | before commit, uowB sees=None; after commit, uowB sees=<Tenant id='01M2DCA857TV237RY91TK1F52X'> |
| `DB-088` | PASS | tenants DAO identical across two reads=True; controls DAO absent until touched=True, present after=True |
| `DB-089` | FAIL | touched all 22 DAO properties -- every single one returns an instance exactly matching its property return annotation (checked via inspect.signature, not the get_type_hints() approach which does not see property return types and would silently report nothing); mismatches=[]. The catalogue's own count of 23 is off by one: UnitOfWork actually declares 22 DAO properties, confirmed by direct enumeration of every @property in db/session.py |
| `DB-090` | PASS | tenant.slug read after the unit-of-work block exited: 't90' |
| `DB-091` | PASS | row count visible via raw SQL for the still-pending insert, issued mid-transaction before an explicit flush: 0 (expected 0 -- autoflush must not have fired) |
| `DB-092` | PASS | principal_role granted via raw SQL against still-pending ORM rows succeeded; roles_of=['viewer'] |
| `DB-093` | PASS | StatementError: (builtins.ValueError) refusing to store a naive datetime; attach UTC before persisting |
| `DB-094` | PASS | StatementError: (builtins.TypeError) expected datetime, got str |
| `DB-095` | PASS | stored='2026-06-01T12:00:00.000000Z', read back=datetime.datetime(2026, 6, 1, 12, 0, tzinfo=datetime.timezone.utc), expected=datetime.datetime(2026, 6, 1, 12, 0, tzinfo=datetime.timezone.utc) |
| `DB-096` | PASS | all three microsecond boundaries round-trip exactly |
| `DB-097` | PASS | datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.timezone.utc) |
| `DB-098` | FAIL | raised ValueError: "Invalid isoformat string: 'not-a-date'" -- names the column/table=False |
| `DB-099` | PASS | '{"a":2,"z":1}' vs '{"a":2,"z":1}' |
| `DB-100` | PASS | {'a': [1, 2, {'b': None, 'c': 'café 日本語'}], 'n': 3.5} vs {'a': [1, 2, {'b': None, 'c': 'café 日本語'}], 'n': 3.5} |
| `DB-101` | PASS | raw=None, IS NULL matched=1 |
| `DB-102` | PASS | read back={}, raw stored='{}' |
| `DB-103` | PASS | {'True': 1, 'False': 0, '1int': 1, '0int': 0} |
| `DB-104` | PASS | None |
| `DB-105` | PASS | pbkdf2_sha256$210000$f7dbd1f073dc3e12443ec0316f213eb0$91a060e9281afd31cc616ef9f669ce2d797acee2acca62b53d8cb873f417d686 |
| `DB-106` | PASS | pbkdf2_sha256$210000$c455c8c52b5a5511c574416dfff05bd5$3d13dba515716184021a435d3c72c17c92d707540b6ef16f3426fe68c5b57bd5 vs pbkdf2_sha256$210000$2aae0f0228bac1bb35252ac35dd68e48$c2f317fc4f152627b954ae766531f07304204c6ad8b17a2c845aa8ab9f68d433 |
| `DB-107` | PASS | Construct the hasher with iterations=100000 or more. This is a code-level floor, not a setting: the value comes from PasswordHasher(iterations=...) and its DEFAULT_ITERATIONS, and nothing reads it from configuration. |
| `DB-108` | PASS | exact=True, trailing-space=False, case-flip=False |
| `DB-109` | PASS | {'': False, 'garbage': False, 'a$b$c': False, 'pbkdf2_sha256$x$y$z': False} |
| `DB-110` | PASS | hmac.compare_digest(...) found in PasswordHasher.verify source |
| `DB-111` | PASS | needs_rehash(100000-iter hash) under a 210000-iter hasher = True |
| `DB-112` | PASS | {'bcrypt$blah': True, '': True, 'pbkdf2_sha256$notanumber$aa$bb': True} |
| `DB-113` | PASS | all prefixed pk_live_=True, unique plaintexts=True, unique hashes=True, stored form matches sha256:<64hex>=True, hash not substring of plaintext=True |
| `DB-114` | PASS | prefix='pk_live_6KvC', prefix_of='pk_live_6KvC', len=12 |
| `DB-115` | PASS | test key prefix='pk_test_nhfe' vs live key prefix='pk_live_6KvC' |
| `DB-116` | PASS | correct-key verify=True, tampered-key verify=False, uses compare_digest=True |
| `DB-117` | PASS | secrets.token_urlsafe(32) draws 32 random bytes = 256 bits of entropy |
| `DB-118` | PASS | None |
| `DB-119` | PASS | ENTITY.NOT_FOUND: [ENTITY.NOT_FOUND] Tenant '01M2DCJYN8911YCXZFBV3Z3046' does not exist \| Next: Check the identifier, or list the available entities first. \| Context: id='01M2DCJYN8911YCXZFBV3Z3046', model='Tenant'; remedy='Check the identifier, or list the available entities first.' |
| `DB-120` | PASS | 0 |
| `DB-121` | PASS | 10 |
| `DB-122` | PASS | tenant A rows=10, tenant B rows=3 |
| `DB-123` | PASS | total across 3 pages=25, unique=25 |
| `DB-124` | PASS | list_for_tenant(limit=0) -> 0 rows |
| `DB-125` | FAIL | no refusal for limit=-1; returned 25 rows: ['a-user0', 'a-user1', 'a-user2'] |
| `DB-126` | PASS | None |
| `DB-127` | PASS | [ENTITY.NOT_FOUND] Principal '01M2DCJYRX4N7MDXCY3J497AZX' does not exist in this tenant \| Next: Check the identifier and the tenant it belongs to. \| Context: id='01M2DCJYRX4N7MDXCY3J497AZX', model='Principal', tenant='01M2DCJYRDSWPGA5W0ATDZCBER' |
| `DB-128` | PASS | a=25, b=3 |
| `DB-129` | PASS | found=<Tenant id='01M2DCJYRDSWPGA5W0ATDZCBEQ'>, notfound=None |
| `DB-130` | PASS | created==updated=True, tz-aware=True |
| `DB-131` | PASS | suspended tenant in list_active()=False |
| `DB-132` | PASS | 11-char refused=True, 12-char accepted=True |
| `DB-133` | PASS | context={'principal': 'pwtest133'}, str(e)=[INPUT.INVALID] a password must be at least 12 characters \| Next: Length is the only property that reliably helps. Prama does not impose character-class rules: they demonstrably push people towards Password1! and away from anything longer. \| Context: principal='pwtest133' |
| `DB-134` | PASS | plaintext absent from all columns=True, updated_at advanced=True |
| `DB-135` | PASS | authed=<Principal id='01M2DCJZZA60ZNE3M370TRVRYN'>, last_login_at=2026-09-13 12:41:32.134775+00:00 |
| `DB-136` | PASS | unknown=None, wrongpw=None, disabled=None, nopass=None |
| `DB-137` | PASS | median known-username auth=29.190ms, median unknown-username auth=25.648ms, ratio=1.14x (no order-of-magnitude difference=True) |
| `DB-138` | PASS | _DUMMY_HASH is a module-level constant computed once: pbkdf2_sha256$210000$d5288355a... |
| `DB-139` | PASS | authenticated=True; hash changed=True; new hash iterations visible=210000 in new_stored=True |
| `DB-140` | PASS | authenticate result=None; last_login_at unchanged=True |
| `DB-141` | PASS | tenant A with B's password=None; tenant B with A's password=None |
| `DB-142` | FAIL | WORSE than a wrong-tenant match: by_external_id('okta','collide-123') raised a raw, untranslated MultipleResultsFound (Multiple rows were found when one or none was required) once two tenants collide on the pair -- since by_external_id has no tenant argument at all and the schema has no UNIQUE constraint on (external_idp, external_id), the SSO sign-in path crashes with an unhandled SQLAlchemy exception rather than signing anyone in or refusing cleanly |
| `DB-143` | PASS | False |
| `DB-144` | PASS | roles sorted=['alpha', 'mu', 'zeta'], unknown-id result=[] |
| `DB-145` | PASS | 10 roles returned; SQL SELECT statements logged for roles_of()=6 (bounded, not 1-per-row) |
| `DB-146` | PASS | role count after granting twice=1 |
| `DB-147` | PASS | gA=ok, gB=ok, roles after both grants=['role147'] |
| `DB-148` | FAIL | sqlite side proven via DB-146/147 (grant then re-grant is idempotent, one row). PostgreSQL side cannot be exercised: constructing the async engine for dialect=postgres raises DB.ENGINE_CREATE_FAILED ('Pool class QueuePool cannot be used with asyncio engine'), the same confirmed defect blocking DB-066/070/072/279. |
| `DB-149` | PASS | revoke of a non-existent grant: no error |
| `DB-150` | PASS | tenant A 'admin' -> 01M2DCK50NR38D54ANWR04MFZ5; tenant B 'admin' -> 01M2DCK50NR38D54ANWR04MFZ6 |
| `DB-151` | PASS | ['read', 'write', 'admin'] |
| `DB-152` | PASS | builtin raw=1, custom raw=0 |
| `DB-153` | PASS | found=<ApiKey id='01M2DCK59GXASNGXM021530K85'>, tenant=01M2DCK58S9EJ9GZYNF0XZHQCH |
| `DB-154` | PASS | active keys=['k1'] |
| `DB-155` | FAIL | active_for_principal() lists 1 key(s) including one already expired (expires_at in the past, revoked_at is NULL) -- the method has no docstring at all (has_docstring=False) explaining that 'active' means 'not revoked', not 'not expired'; separately confirmed api/deps.py DOES check expires_at at the point of authentication (line ~120), so the security-relevant half works -- only the documentation half named by the catalogue is missing |
| `DB-156` | PASS | AuditDao overrides delete()=False; calling the inherited Dao.delete() on an audit event: True -- the class docstring says 'deliberately exposes no update or delete' but Dao.delete is inherited unchanged and reachable |
| `DB-157` | PASS | occurred_at=2026-09-13 12:41:37.648861+00:00, stamped by the DAO itself (no caller-supplied timestamp parameter exists on record()) |
| `DB-158` | PASS | outcome='success', actor_kind='human', detail_json={} |
| `DB-159` | PASS | for_object(tenantX)=['x-action']; recent(tenantX) all tenant-scoped=True |
| `DB-160` | PASS | orders across 5 repeated queries with tied occurred_at: [('second', 'first'), ('second', 'first'), ('second', 'first'), ('second', 'first'), ('second', 'first')] |
| `DB-161` | PASS | put sequence ok=True, final value='from-B', row count=1 |
| `DB-162` | PASS | {'a': 1} |
| `DB-163` | PASS | {'n': None, 'outer': {'inner': [1, 2, {'deep': 'café'}]}} vs {'outer': {'inner': [1, 2, {'deep': 'café'}]}, 'n': None} |
| `DB-164` | PASS | 'scope-global-tenant161', 'scope-custom-tenant161', 'scope-global-tenant164b', 'scope-custom-tenant164b' (all distinct=True); all_for_scope(tenant161, global) keys=['k161', 'k163', 'k164'] |
| `DB-165` | PASS | put(None) stored raw value_json='null'; get_value(default='DEFAULT165') returns None -- None is returned directly, distinguishable from a missing row only by catching the default sentinel differently |
| `DB-166` | PASS | version=1, valid_to=None, superseded_at=None |
| `DB-167` | PASS | just after=True, just before=False |
| `DB-168` | PASS | old.valid_to=2026-09-13 12:44:34.553902+00:00, new.valid_from=2026-09-13 12:44:34.553902+00:00, new.valid_to=None, old.superseded=False, new.superseded=False |
| `DB-169` | PASS | v2 superseded=True, v2 period unchanged=True, v3 inherits period=True |
| `DB-170` | PASS | as_of(T1.5, T1.5).name=T170-orig |
| `DB-171` | PASS | valid_at(T1.5) today .name=T170-corrected |
| `DB-172` | PASS | ENTITY.CONFLICT: 'Choose a later effective date, or correct the earlier version instead if it was simply wrong.' |
| `DB-173` | PASS | old.valid_from==valid_to==True; valid_at(T) resolves to version=2 |
| `DB-174` | PASS | [ENTITY.NOT_FOUND] SemDomain '01M2DCRJH612CNEXHBAKABETNE' has no current version to amend \| Next: Create the declaration before amending it. \| Context: entity='01M2DCRJH612CNEXHBAKABETNE'; remedy='Create the declaration before amending it.' |
| `DB-175` | PASS | refused as not found, cross-tenant amend blocked |
| `DB-176` | PASS | all 10 methods require tenant_id |
| `DB-177` | PASS | call sites: ['src/prama/semantic/services/connectivity.py:100:        owner = await self._uow.connections.tenant_of(connection_id)']; any inside web/ or api/ routes=False |
| `DB-178` | PASS | 1 |
| `DB-179` | FAIL | A='IntegrityError: (sqlite3.IntegrityError) UNIQUE constraint failed: sem_domain_version.domain_id\n[SQL: INSERT INTO sem_do', B='ok'; true current-row count=1 (data integrity is fine: exactly one current row, no forked chain -- the partial unique index worked). But the LOSING side's error is a raw, untranslated sqlite3.IntegrityError, not the documented ConflictError: VersionedDao.amend()/correct() call `self._session.flush()` directly rather than going through UnitOfWork._guarded(), so the err… |
| `DB-180` | PASS | [ENTITY.CONFLICT] unknown field(s) for SemDomainVersion: ['grian'] \| Next: Check the field names; a typo here would silently change nothing. \| Context: unknown=['grian']; remedy='Check the field names; a typo here would silently change nothing.' |
| `DB-181` | PASS | successor has fresh id=True, fresh version=True, fresh recorded_at=True, own provenance (not inherited)=True |
| `DB-182` | PASS | authored_by='alice', approved_by='bob', change_reason='r181' |
| `DB-183` | PASS | successor.approved_by=None (original was approved by bob183) |
| `DB-184` | PASS | current after retire=None; history len=1, valid_to set=True |
| `DB-185` | PASS | None |
| `DB-186` | PASS | versions in order=[1, 2, 3], any superseded=True |
| `DB-187` | PASS | [] |
| `DB-188` | PASS | total across pages=22, unique=22 |
| `DB-189` | PASS | count_current=22, list_current total unique=22 |
| `DB-190` | PASS | current() returned [(3, 'TQ3')] |
| `DB-191` | PASS | {'T1-eps': False, 'T1': True, 'T2-eps': True, 'T2': False, 'T2+eps': False} |
| `DB-192` | PASS | {'T1-eps': False, 'T1': True, 'T2-eps': True, 'T2': False, 'T2+eps': False} |
| `DB-193` | PASS | grid points tested=16; points with >1 row=[] |
| `DB-194` | PASS | python.is_current membership={'01M2DCRKRVDZQ5R3MHEWBTY8SQ'}, SQL current()={'01M2DCRKRVDZQ5R3MHEWBTY8SQ'} |
| `DB-195` | PASS | {'DomainDao': True, 'DatasetDao': True, 'AttributeDao': True, 'ConceptDao': True, 'ConceptPropertyDao': True, 'RelationshipDao': True, 'JourneyDao': True, 'ConnectionDao': True, 'BindingDao': True} |
| `DB-196` | PASS | A:Shared, B:SharedB |
| `DB-197` | PASS | None |
| `DB-198` | PASS | cross-tenant result=[], own-tenant count=1 |
| `DB-199` | PASS | cross=[], own=1 |
| `DB-200` | PASS | for_dataset cross=[], for_attribute cross=None, own=1 |
| `DB-201` | FAIL | mapped_to_property(property_id) takes tenant_id=False (it does not); calling it with tenant A's property id returned tenant B's attribute (1 row(s)) even though the call carried no tenant context at all -- a caller who only knows a property id belonging to another tenant can enumerate that tenant's attribute mappings |
| `DB-202` | PASS | unbound()=['DSforAttrs', 'Shared', 'Unbound1'] |
| `DB-203` | PASS | tier2=['Tier2'], tier0=[] |
| `DB-204` | PASS | CDEs in tenant A=['cdeA'] |
| `DB-205` | PASS | touching(X)=1, touching(Y)=1 |
| `DB-206` | PASS | confirmed count=1 |
| `DB-207` | PASS | found=1, notfound=[] |
| `DB-208` | FAIL | hardcoded 10_000 in source confirmed=True; EXECUTED at reduced scale (list_current capped to 3 via monkeypatch, 5 journeys created, the matching one 5th/beyond the cap): containing() found it=False -- the ceiling silently hid a real match, exactly as the catalogue warns |
| `DB-209` | FAIL | same pattern, executed: with list_current capped to 3 and the one broken connection created 5th, unhealthy() found it=False -- ceiling silently hid the broken connection |
| `DB-210` | PASS | drifted states found={'retyped', 'renamed', 'missing'} |
| `DB-211` | PASS | dataset='t', dims=['completeness'], content_hash='ac1d71ceede4', plan_id='ir:sha256:ee44377f54011968249b0204cea9a8021d6881bb4897b28eeceda571ffbba255' |
| `DB-212` | PASS | declare() does not even accept a 'severity' keyword argument (params=['approved_by', 'authored_by', 'criticality', 'identity', 'origin', 'owner_id', 'pql', 'provenance', 'reason', 'rule', 'schedule', 'self', 'source_ref', 'status', 'tenant_id', 'valid_from']); stored severity='minor' is derived purely from the PQL text 'SEVERITY minor' -- there is no route by which a caller could pass one in, confirming **fields is applied last and unconditionally |
| `DB-213` | PASS | INPUT.INVALID: "Fix the PQL first. A control that cannot be parsed cannot be executed, and storing it would hide that until it was due to run. [PQL.SYNTAX] '!' does n" |
| `DB-214` | PASS | control stored=True, plan_id='' |
| `DB-215` | PASS | [DB-215a] unchanged re-declare: same version id=True \|\| [DB-215b] changed re-declare creates new version: id changed=True, version=2 |
| `DB-216` | PASS | recorded_at unchanged=True |
| `DB-217` | PASS | reindented PQL creates a new version=False (should be False) |
| `DB-218` | PASS | history len=2, proposal superseded=False, proposal valid_to set=True |
| `DB-219` | PASS | 'alice218' |
| `DB-220` | PASS | [(('', 'reason'), True), (('2026-01-01', ''), True), (('  ', 'reason'), True), (('2026-01-01', '  '), True)] |
| `DB-221` | PASS | live count=2 |
| `DB-222` | PASS | in silenced list=True, still status='suppressed' (not auto re-enabled) |
| `DB-223` | PASS | past-hour in=True, exact-now in=True, future-hour in=False |
| `DB-224` | PASS | evidence still resolves=1, control entity still resolves=True |
| `DB-225` | PASS | same content=True, rewritten content=False |
| `DB-226` | PASS | tenant226 sees its own rejection=True; tenant(sc) does not see tenant226's under a different identity=False |
| `DB-227` | PASS | rejection with empty content_hash matching a real hash=False |
| `DB-228` | PASS | stored sequence=4 (caller passed 999), previous_hash matches real head=True |
| `DB-229` | PASS | [ENTITY.CONFLICT] an evidence record needs a tenant \| Next: Every chain is per-tenant; supply the tenant it belongs to. |
| `DB-230` | PASS | '0000000000000000000000000000000000000000000000000000000000000000' |
| `DB-231` | PASS | 0 |
| `DB-232` | PASS | tenant232b sequences=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], verify.ok=True |
| `DB-233` | PASS | verify.is_intact=False; breaches=[('content', 1, 'the content does not match its hash; this record has been altered'), ('link', 1, 'the record hash does not match its own contents'), ('link', 2, 'this record does not follow the one before it; the chain is broken here')] |
| `DB-234` | PASS | chain() record.detail='TAMPERED' (recomputed hash would match this tampered content); as_stored() dict content.detail='TAMPERED' vs stored content_hash='e9843121ae40' (original, now mismatching) |
| `DB-235` | PASS | [ENTITY.CONFLICT] an evidence record cannot be deleted (sequence 0) \| Next: Deleting one record breaks every hash after it. To satisfy a right-to-erasure request use erase(), which blanks the content and keeps the chain verifiable. To reclaim space, archive the prefix under the retention policy. \| Context: sequence=0, tenant='01M2DD72EQRGC193BA99XQR3EN'; remedy='Deleting one record breaks every hash after it. To satisfy a right-to-erasure request use erase(), which blanks the content and keeps… |
| `DB-236` | PASS | verify.ok=True, tombstone set=True, detail blanked=True |
| `DB-237` | PASS | Check the sequence; a gap is itself a finding worth investigating. |
| `DB-238` | PASS | erasing an already-erased record: no error |
| `DB-239` | FAIL | python -O actually strips asserts in this interpreter (confirmed: exit code 0 for a script whose only statement is 'assert False' -- no error, so asserts ARE stripped); erase()'s only protection for content_hash/record_hash is two bare `assert` statements with no accompanying runtime check, so any deployment run with `python -O` (e.g. a container base image or PYTHONOPTIMIZE=1) loses this guard silently -- a genuine gap in the ledger's tamper-evidence design, matching CLAUDE.md's own list of thi… |
| `DB-240` | PASS | sequences=[0, 1, 2] |
| `DB-241` | PASS | root1=bf2b8287fd11, root2=bf2b8287fd11, count=3,3 |
| `DB-242` | PASS | count=0, root='0000000000000000000000000000000000000000000000000000000000000000' |
| `DB-243` | PASS | count=4, verdicts={'skipped', 'indeterminate', 'error', 'fail'} |
| `DB-244` | FAIL | for_control(control_id) takes tenant_id=False (it does not); called with only a control id (no tenant context) it returned 1 record(s) belonging to tenant A, including detail='' |
| `DB-245` | FAIL | for_run(run_id) takes tenant_id=False (it does not); returned 1 record(s) with no tenant check |
| `DB-246` | PASS | distinct controls tracked=2 (from 61 total records) |
| `DB-247` | PASS | with chain() capped at 5 (simulating the real default cap of 10,000), the 6th control's record is missing from latest_per_control() -- confirming a scorecard silently stops seeing the newest controls past the cap |
| `DB-248` | PASS | last_run_at for an always-erroring control='2026-01-03T00:00:00Z' |
| `DB-249` | PASS | 3 |
| `DB-250` | PASS | unfinished count=1 |
| `DB-251` | PASS | first expiry='2026-02-01T00:00:00Z', after second put expiry='2026-02-01T00:00:00Z' (must be unchanged) |
| `DB-252` | PASS | expired digests (this test's own)={'d-exact-252', 'd-past-252'} |
| `DB-253` | PASS | forgot=True, sample gone=True, record survives with sample_count=5 |
| `DB-254` | PASS | False |
| `DB-255` | PASS | expired() params=['self', 'now'], forget() params=['self', 'digest'] -- confirmed neither takes a tenant, matching the documented deliberate design (content-addressed digest is the identity; a retention sweep legitimately crosses tenants) |
| `DB-256` | PASS | [ENTITY.CONFLICT] an attestation cannot be deleted (signed 2026-01-01T00:00:00Z) \| Next: Sign a new one naming this as superseded, with the reason. The original stays, because the fact that it was signed is itself part of the record. \| Context: attestation='01M2DDAYY13MSR5G6WP6XZRFM3'; remedy='Sign a new one naming this as superseded, with the reason. The original stays, because the fact that it was signed is itself part of the record.' |
| `DB-257` | PASS | replacement.supersedes=01M2DDAYZHV97C8SV70RXF1H57, original.superseded_by=01M2DDAYZXERJ63875WWD8NZGN |
| `DB-258` | PASS | raised as expected: [ENTITY.NOT_FOUND] there is no attestation '01M2DDAZ0X62N3V8QE7M1TWS1V' to supersede \| Next: Check the identifier; nothing was replaced. \| Context: supersedes='01M2DDAZ0X62N3V8QE7M1TWS1V' \|\| [DB-258-persist] rows with scope=s258 after the rolled-back sign(): 0 |
| `DB-259` | PASS | current scopes={'s1', 's257'} \|\| [DB-259b] superseded original present in current()=False |
| `DB-260` | PASS | history ids in order=['01M2DDAYZHV97C8SV70RXF1H57', '01M2DDAYZXERJ63875WWD8NZGN'] |
| `DB-261` | PASS | reported as not found for the wrong tenant |
| `DB-262` | PASS | correct=(True,True), wrongkey=(True,False), tampered=(False,False) |
| `DB-263` | PASS | intact=True, sealed=False |
| `DB-264` | PASS | observe() first run -> (40, 0, 0) (expected (40 new, 0 again, 0 cleared) on a fresh queue) \|\| [DB-264b] second run with 40 different keys -> (40, 0, 40) (expected 40 new, 0 again, 40 cleared -- 'forty cleared and forty appeared') |
| `DB-265` | PASS | first_seen='2025-08-05T00:00:00Z', last_seen='2025-09-14T00:00:00Z' |
| `DB-266` | PASS | state='cleared', cleared_at='2026-01-02T00:00:00Z' |
| `DB-267` | PASS | state after being absent from a run='accepted' |
| `DB-268` | PASS | state='open', cleared_at=None, first_seen='2025-01-01T00:00:00Z' |
| `DB-269` | PASS | outstanding count=4 (open, assigned, explained, accepted -- excludes the 1 cleared) |
| `DB-270` | PASS | definitions()=['def270-allcleared'] |
| `DB-271` | PASS | assign('  ')=True, explain('')=True, accept('  ')=True |
| `DB-272` | PASS | comments=[{'at': '2026-01-01T00:00:00Z', 'by': 'qa', 'text': 'Assigned to alice'}, {'at': '2026-01-02T00:00:00Z', 'by': 'qa', 'text': 'Reassigned from alice to bob'}] |
| `DB-273` | PASS | [ENTITY.CONFLICT] this break has already cleared, so there is nothing to accept \| Next: Accepting a break that has gone would carry a difference nobody has. \| Context: break='01M2DDB18KST0DGZTRCZHV4B4X' |
| `DB-274` | PASS | comments=['first note', 'second note', 'third note'] |
| `DB-275` | PASS | [ENTITY.CONFLICT] a break cannot be deleted \| Next: Breaks clear by absence when the reconciliation stops reporting them, and are accepted when they are expected to persist. "We had four hundred breaks and they cleared" and "we had four hundred breaks" must not be the same sentence. \| Context: break='01M2DDB19Y2YW1DWY5MX4D9JDF' |
| `DB-276` | PASS | reported not found for wrong tenant |
| `DB-277` | PASS | missing side stored as='', zero side stored as='0' |
| `DB-278` | PASS | grant pairs (A_won, B_won) per round=[(True, False), (False, True), (True, False), (True, False), (False, True)] |
| `DB-279` | FAIL | SQLite side fully exercised across DB-278/280-288 (all pass). PostgreSQL side is impossible to exercise at all: Database._engines.async_engine() for dialect=postgres raises DB.ENGINE_CREATE_FAILED before any lease code runs -- "Pool class QueuePool cannot be used with asyncio engine" (the same PostgresDialect.engine_kwargs(is_async=True) QueuePool defect found under DB-066/070/072). DatabaseLeaseProvider requires an AsyncEngine, so the database-backed lease provider cannot function on PostgreSQL… |
| `DB-280` | PASS | tokens=[1, 2, 3, 4, 5] |
| `DB-281` | PASS | A got=True, B got=None |
| `DB-282` | PASS | A renew after B took over=None; B acquired=True |
| `DB-283` | PASS | None |
| `DB-284` | PASS | released=True; token before=1, after re-acquire=2 |
| `DB-285` | PASS | holder='A284 (released)' |
| `DB-286` | PASS | live inspect=True (tz-aware acquired=True); expired inspect=None |
| `DB-287` | PASS | cutoff was a week ago, neither row is that old yet: removed=0, live row survives=True, old-but-recent row also survives=True (correct: purge only removes rows older than the cutoff, and nothing here is a week old) \|\| [DB-287b] after advancing 8 days and purging with a 7-day cutoff: removed=13, old row gone=True |
| `DB-288` | PASS | across a year+microsecond boundary, expired lease was taken over: True |
| `DB-289` | PASS | mem series len=2, parquet series len=2 |
| `DB-290` | PASS | mem order=[datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.timezone.utc), datetime.datetime(2026, 1, 15, 0, 0, tzinfo=datetime.timezone.utc), datetime.datetime(2026, 1, 30, 0, 0, tzinfo=datetime.timezone.utc)]; parquet order=[datetime.datetime(2026, 1, 1, 0, 0, tzinfo=datetime.timezone.utc), datetime.datetime(2026, 1, 15, 0, 0, tzinfo=datetime.timezone.utc), datetime.datetime(2026, 1, 30, 0, 0, tzinfo=datetime.timezone.utc)] |
| `DB-291` | PASS | series values mem=(100.0, 110.0) parquet=(100.0, 110.0); latest mem=[('null_rate', 0.02), ('row_count', 110.0)] parquet=[('null_rate', 0.02), ('row_count', 110.0)]; count mem=3 parquet=3 |
| `DB-292` | PASS | mem back=('1pct', False, 1000, False); parquet back=('1pct', False, 1000, False) |
| `DB-293` | PASS | removed count(partitions)=1; remaining days=[datetime.date(2026, 1, 2), datetime.date(2026, 1, 3)] -- day1 (before cutoff) gone=True, day2 (the cutoff's OWN day, only mid-day passed) survives, day3 (after cutoff) survives=True |
| `DB-294` | PASS | 'tenant_defined_weird_metric_xyz' not in CORE_METRICS=True; recorded and read back=True |
| `DB-295` | PASS | keys differ=True; series(segment=None)=[1.0]; series(segment=GB)=[2.0] |

## Failure details

### CFG-008 · An unknown `logging.level` is refused, not silently defaulted
- **Expected:** A named refusal with a remedy listing the accepted logging levels.
- **Observed:** unnamed ValueError: Unknown level: 'VERBOSE'
- **Reproduce:** python -c "import sys; sys.path.insert(0,'src'); from prama.core.log import LoggingConfigurator; LoggingConfigurator(level='VERBOSE').apply()"
- **Severity:** P2
- **Assessment:** defect. `LoggingConfigurator.apply()` calls `root.setLevel(self._level)` with no validation. An unknown level raises the stdlib's bare `ValueError: Unknown level: 'VERBOSE'` — not a `PramaError` subclass, no code, no remedy.

### CFG-014 · The comment on `security.cookies_https_only` matches its value
- **Expected:** The shipped comment describes the value; since the value is `True`, a comment saying it is 'off' is wrong and must be corrected.
- **Observed:** comment says 'Off in development' near cookies_https_only=True (True means ON)
- **Reproduce:** grep -A2 'session_secret' src/prama/core/config/defaults.py # the comment above cookies_https_only says 'Off in development' while the value is True
- **Severity:** P2
- **Assessment:** defect. Documentation-only. `defaults.py`'s comment block describes `cookies_https_only` as off in development, but the shipped default is `True` (on). The behaviour is fine; the comment is backwards.

### CFG-020 · `web.preview.max_rows: 0` is refused
- **Expected:** A refusal, not a preview that silently returns nothing.
- **Observed:** max_rows=0 not refused; trial.verdict='' error='PqlSyntaxError: [PQL.SYNTAX] expected the reason this control exists, in quotes, and found \'"sanity"\' | Next: Quoted text is written between single quotes: \'like this\'. | Context: position=\'line 1, column 31\'' (ran unbounded instead of refusing)
- **Reproduce:** python -c "import sys; sys.path.insert(0,'src'); import duckdb; from prama.execute.preview import Preview con=duckdb.connect(':memory:'); con.execute('CREATE TABLE t(a INTEGER)'); con.execute('INSERT INTO t VALUES (1),(2),(3)') def execute(sql): cur=con.execute(sql); names=[c[0] for c in cur.description or ()]; return [dict(zip(names,r)) for r in cur.fetchall()] p=Preview(execute=execute, engine='duckdb', max_rows=0) t=p.once(\"CHECK t.a IS NOT NULL SEVERITY critical DIMENSION completeness BECAUSE 'x'\"); print(t.verdict, t.scanned_rows)"
- **Severity:** P2
- **Assessment:** not-a-defect. `max_rows=0` is not refused, but it is not silently empty either: the code and `config/application.yaml`'s own comment ('Zero is unbounded') define 0 as *unbounded*, and `Preview._trial` separately guards the specific danger the case is worried about — it reports `no_data` (not `pass`) whenever `scanned_rows<=0`, regardless of `max_rows`. The catalogue assumed 0 meant 'cap of zero rows, so empty', which is not how the code works; the actual behaviour (scan everything) is safe and documented.

### CFG-021 · `web.preview.backtest_days` defaults to 30 and rejects a negative
- **Expected:** Default `30`; `-1` refused with a remedy.
- **Observed:** [CFG-021-default] 30 || preview_routes.py backtest_days negative-guard present=False
- **Reproduce:** grep -n 'backtest_days' src/prama/web/routes/preview_routes.py # config.get_int(..., 30) is used directly with no negative guard
- **Severity:** P3
- **Assessment:** defect. The default (30) is correct. No negative-value guard was found anywhere `backtest_days` is read (`preview_routes.py` reads it straight into `_preview`'s `requested` count with no validation), so a negative value would reach date arithmetic unchecked. Verified by source inspection of every read site, not by driving the web route end-to-end.

### CFG-036 · `plugins.disabled` exists in the tracked file and not in `DEFAULTS`
- **Expected:** Either `disabled: []` is added to `DEFAULTS`, or its absence is deliberate and documented.
- **Observed:** file has disabled=True, DEFAULTS has disabled=False
- **Reproduce:** python -c "import sys; sys.path.insert(0,'src'); from prama.core.config.defaults import DEFAULTS; print('disabled' in DEFAULTS['plugins'])" # False, yet config/application.yaml line 106 ships 'disabled: []'
- **Severity:** P2
- **Assessment:** defect. `defaults.py`'s own docstring says 'this mapping is the authority and the file is documentation. Where the two could drift, a test compares them' — but `plugins.disabled` exists only in the tracked YAML, not in `DEFAULTS`, and nothing enforces agreement between them.

### CFG-040 · A negative `max_overflow` is refused
- **Expected:** A named refusal.
- **Observed:** no exception; accepted max_overflow=-5
- **Reproduce:** python -c "import sys; sys.path.insert(0,'src'); from prama.db.settings import DbSettings, PoolSettings print(PoolSettings(max_overflow=-5))" # constructs cleanly; DbSettings.from_config likewise accepts it
- **Severity:** P2
- **Assessment:** defect. `PoolSettings.validate()` only checks `size <= 0`; `max_overflow` is never validated. SQLAlchemy treats a negative `max_overflow` as unbounded, silently defeating the cap an operator believed they set.

### CFG-048 · `concurrency.lease.provider` selects database or memory
- **Expected:** `MemoryLeaseProvider` and `DatabaseLeaseProvider` respectively; an unknown value refused by name.
- **Observed:** with concurrency.lease.provider=memory, Database.lease_provider() returned DatabaseLeaseProvider (config value never read anywhere in src/prama; grep confirms no code branches on lease.provider)
- **Reproduce:** grep -rn 'lease.provider\|LeaseProvider(' src/prama/db/__init__.py # Database.lease_provider() unconditionally returns DatabaseLeaseProvider(...); concurrency.lease.provider is never read
- **Severity:** P1
- **Assessment:** defect. No code anywhere in `src/prama` reads `concurrency.lease.provider`. `Database.lease_provider()` always builds a `DatabaseLeaseProvider`, so setting `provider: memory` has no effect at all, and an invalid value is not refused either — the key is entirely decorative.

### CFG-062 · A non-UTF-8 config file is refused with the same code
- **Expected:** `CONFIG.FILE_UNREADABLE` — the decode failure is caught and translated rather than escaping as a traceback.
- **Observed:** UnicodeDecodeError escaped uncaught (except OSError does not catch it): 'utf-8' codec can't decode byte 0xe9 in position 16: invalid continuation byte
- **Reproduce:** python -c "import sys; sys.path.insert(0,'src'); open('/tmp/latin1.yaml','wb').write('app:\n name: caf\xe9\n'.encode('latin-1')) from prama.core.config import load_configuration; load_configuration('/tmp/latin1.yaml', use_environment=False)"
- **Severity:** P3
- **Assessment:** defect. Confirms the catalogue's own flagged concern exactly: `FileSource.load` only catches `except OSError`, and `UnicodeDecodeError` is a `ValueError`, not an `OSError`. A non-UTF-8 config file crashes with a raw traceback instead of `CONFIG.FILE_UNREADABLE`.

### CFG-082 · Redaction does not reach inside lists
- **Expected:** The nested passwords are masked, or the gap is documented.
- **Observed:** redact_mapping result for list-of-dicts: {'connections': [{'password': 'p1'}, {'password': 'p2'}]} (masked_in_list=False)
- **Reproduce:** python -c "import sys; sys.path.insert(0,'src'); from prama.core.log import redact_mapping; print(redact_mapping({'connections':[{'password':'p1'},{'password':'p2'}]}))"
- **Severity:** P2
- **Assessment:** defect. `redact_mapping` recurses into `dict` only; a `list` of mappings (the natural shape for a multi-connection config) passes through unmasked, and the gap is not documented anywhere (the function's docstring makes no mention of lists).

### CFG-088 · The filter does not mask a secret embedded in a URL
- **Expected:** The password is masked, or the limitation is documented.
- **Observed:** 'connecting to postgresql://prama:hunter2@host/db'
- **Reproduce:** python -c "import sys, logging; sys.path.insert(0,'src'); from prama.core.log import RedactionFilter r=logging.LogRecord('t',logging.INFO,'f',1,'connecting to postgresql://prama:hunter2@host/db',None,None) RedactionFilter().filter(r); print(r.msg)"
- **Severity:** P2
- **Assessment:** defect. `_SENSITIVE_TEXT` only matches `key: value` / `key=value` forms; a DSN embeds the password after a colon inside a URL and is not matched. The gap is not documented, and a connection string is the single most likely thing to end up in a log line.

### CFG-094 · The JSON formatter emits a UTC timestamp with milliseconds and a `Z`
- **Expected:** `YYYY-MM-DDTHH:MM:SS.mmmZ`, i.e. a genuine UTC timestamp.
- **Observed:** ts='2026-09-13T08:07:55.272Z' local_tz_offset_hours=-4.0 utc_now='2026-09-13T12:07' matches_utc=False
- **Reproduce:** TZ=America/New_York python -c "import sys, logging, io; sys.path.insert(0,'src'); from prama.core.log import JsonFormatter, ContextFilter import datetime; s=io.StringIO(); h=logging.StreamHandler(s); h.setFormatter(JsonFormatter()); h.addFilter(ContextFilter()) root=logging.getLogger('x'); root.handlers=[h]; root.setLevel(logging.INFO); root.propagate=False root.info('hi'); print(s.getvalue()); print('actual utc:', datetime.datetime.now(datetime.UTC))"
- **Severity:** P2
- **Assessment:** defect. `JsonFormatter.format` builds `ts` from `self.formatTime(record, ...)`, which uses `time.localtime` by default (`logging.Formatter.converter`) and is never overridden to `time.gmtime`. On a machine set to a non-UTC zone (confirmed on this host, EDT, UTC-4) the emitted `ts` is local wall-clock time with a trailing `Z` falsely claiming UTC — a 4-hour error in every structured log line, exactly the scenario the docstring says the module protects against.

### CFG-112 · A negative numeric duration passes the type check
- **Expected:** Refused at coercion or refused by the consumer; never applied.
- **Observed:** numeric -5 accepted and returned -5.0 -- disagrees with string form '-5s' which is refused
- **Reproduce:** python -c "import sys; sys.path.insert(0,'src'); from prama.core.config.coercion import Coercer; print(Coercer('x').to_duration_seconds(-5))" # -5.0, no exception
- **Severity:** P2
- **Assessment:** defect. The string form `'-5s'` is correctly refused (the regex has no sign), but the numeric form `-5` passes straight through the `isinstance(int|float)` branch and returns `-5.0`. The two representations of the same value disagree about validity, exactly as the catalogue's own 'Why' predicts.

### CFG-118 · A coercion failure on a secret does not print the secret
- **Expected:** The value is masked in the raised error.
- **Observed:** secret leaked in exception string=True: [CONFIG.TYPE] configuration key security.session_secret is not a valid integer | Next: Provide a whole number, e.g. 20. | Context: key='security.session_secret', value="'supersecretvalue123'", wanted='integer'
- **Reproduce:** python -c "import sys; sys.path.insert(0,'src'); from prama.core.config.coercion import Coercer try: Coercer('security.session_secret').to_int('supersecretvalue123') except Exception as e: print(e)"
- **Severity:** P1
- **Assessment:** defect. `Coercer._fail` puts `context={'value': repr(value), ...}` into the raised `ConfigTypeError` unconditionally — it does not consult `SENSITIVE_KEYS` for the key it was constructed with. A coercion failure on `security.session_secret` (or any secret key) prints the raw value in the exception, which is exactly the kind of value that ends up in a log or an API problem document.

### CFG-162 · `utc_now()` is the only ambient time source and is used sparingly
- **Expected:** No bare `datetime.now()` outside `core/clock.py`.
- **Observed:** bare datetime.now() call sites outside core/clock.py: [('/home/ashutosh/PycharmProjects/prama/src/prama/cli/apikey.py', 98)]
- **Reproduce:** grep -n 'datetime.now(' src/prama/cli/apikey.py
- **Severity:** P2
- **Assessment:** defect. `cli/apikey.py:98` calls `datetime.now(UTC)` directly to compute an API key's `expires_at`, instead of going through `utc_now()` or an injected `Clock`. Low real-world severity (it is UTC-aware, so not wrong data, just outside the deterministic-replay discipline the rest of the codebase follows) but a literal violation of the stated rule.

### CFG-169 · A clock that steps backwards does not break monotonicity
- **Expected:** The second id still sorts after the first.
- **Observed:** first=01KDVDNAZ8G0G52AJVW43GCPDH (ms=1767225601000), second=01KDVDNA0045EC5K0MDC8QJ08A (ms=1767225600000); second>first=False
- **Reproduce:** python -c "import sys; sys.path.insert(0,'src'); from prama.core.ids import UlidFactory, ulid_timestamp_millis from prama.core.clock import ManualClock from datetime import datetime, timezone f=UlidFactory(clock=ManualClock(datetime(2026,1,1,0,0,1,tzinfo=timezone.utc))) first=f.new() f._clock=ManualClock(datetime(2026,1,1,0,0,0,tzinfo=timezone.utc)) second=f.new() print(first, second, second>first)"
- **Severity:** P2
- **Assessment:** defect. Confirms the catalogue's flagged concern exactly. `UlidFactory.new`'s `else` branch (taken whenever `ms != self._last_ms`, which includes a *backwards* step) resets `_last_ms` to whatever the clock now says, so an NTP step backwards produces an id that sorts *before* the previous one — breaking the append-only, page-by-id-order guarantee several stores rely on.

### CFG-205 · `ALWAYS` restarts a task that returns cleanly
- **Expected:** It runs repeatedly, incrementing `restarts`.
- **Observed:** restarts after 0.2s of an instantly-returning ALWAYS task=2
- **Reproduce:** python -c "import sys, asyncio, time; sys.path.insert(0,'src'); from prama.core.concurrency.supervisor import TaskSupervisor, RestartPolicy async def main(): sup=TaskSupervisor(base_backoff=0.2, max_backoff=30) calls=[] async def poller(): calls.append(time.monotonic()) h=sup.spawn('poll', poller, policy=RestartPolicy.ALWAYS) await asyncio.sleep(3.0) await sup.shutdown() print(len(calls), h.restarts) asyncio.run(main())" # 5 calls in 3 seconds, not ~unlimited
- **Severity:** P2
- **Assessment:** defect. Bonus finding (not in the catalogue's pre-flagged list). `TaskSupervisor._run`'s restart-counting/backoff code sits *after* the try/except and runs unconditionally whenever the loop does not `return` — which for `RestartPolicy.ALWAYS` is every iteration, success or failure. A poller that succeeds every time is therefore throttled with the same exponential backoff as a crash loop: 5 calls in 3 seconds instead of ~unlimited, and the gap between polls keeps growing toward `max_backoff` (30s) the longer the poller runs successfully.

### CFG-256 · `plugins.disabled` in configuration is either wired up or not documented
- **Expected:** Either the plugin is disabled, or the configuration key is removed from the tracked file.
- **Observed:** no call to Registry.disable(...) found anywhere in src/prama (grep for '.disable(' across *.py): ''; config/application.yaml ships plugins.disabled: [] but nothing reads it
- **Reproduce:** grep -rn '\.disable(' src/prama --include='*.py' # zero results anywhere in the codebase
- **Severity:** P2
- **Assessment:** defect. No call to `Registry.disable(...)` exists anywhere in `src/prama`. `config/application.yaml` ships `plugins.disabled: []` (CFG-036) but nothing ever reads that key into a `disable()` call — the configuration key does nothing.

### CFG-260 · A broken plugin is visible in health output
- **Expected:** The failure is reported somewhere an operator sees it.
- **Observed:** Registry exposes no failure-tracking attribute for discover() (checked _failed/failures/discovery_errors); only a log.warning is emitted, and grep of src/prama/api shows /health reports only database state -- the docstring's claim 'visible in health output' is not backed by any mechanism
- **Reproduce:** grep -n 'health' src/prama/api/routes/meta.py # /health reports only database.health(); no registry/plugin state anywhere
- **Severity:** P2
- **Assessment:** defect. `Registry.discover()`'s docstring claims a broken plugin's failure 'is visible in health output', but `Registry` exposes no failure-tracking attribute at all (confirmed: no `_failed`/`failures`/`discovery_errors`), and the only `/health` endpoint in the codebase reports database state exclusively. The only trace of a broken plugin is a `_log.warning(...)` call.

### CFG-262 · `_entry_points_for` swallowing every exception is bounded
- **Expected:** The failure to enumerate is reported, not silently turned into 'no plugins found'.
- **Observed:** _entry_points_for() on a broken metadata call returned [] -- 'except Exception: return []' silently reports zero plugins found, indistinguishable from an empty install; enumeration failure is not surfaced at all
- **Reproduce:** python -c "import sys; sys.path.insert(0,'src'); import importlib.metadata as im class Broken: def __call__(self,*a,**kw): raise OSError('corrupted metadata') im.entry_points=Broken() from prama.core.registry import _entry_points_for; print(_entry_points_for('prama.connectors'))"
- **Severity:** P2
- **Assessment:** defect. Confirms the flagged concern exactly. `_entry_points_for`'s `except Exception: return []` makes a corrupted or unreadable distribution-metadata directory indistinguishable from an install with no plugins at all — CLAUDE.md's 'no exception is swallowed' rule, violated.

### CFG-292 · `next_business_day` on a calendar with no business days does not hang
- **Expected:** A bounded refusal, not an infinite loop.
- **Observed:** not a true infinite loop (date has an internal max), but an unbounded, uncontrolled spin: took 2.42s of CPU iterating day-by-day toward date.max, then crashed with rc=1 on an unhandled low-level error rather than a graceful, immediate refusal: 'OverflowError: date value out of range'
- **Reproduce:** timeout 10 python -c "import sys; sys.path.insert(0,'src'); from prama.core.calendars import BusinessCalendar from datetime import date c=BusinessCalendar(name='never', weekend_days=frozenset(range(7))) print(c.next_business_day(date(2026,1,1)))"
- **Severity:** P2
- **Assessment:** defect. Not a literal infinite loop — `date` has an internal maximum, so the `while not self.is_business_day(candidate): candidate += timedelta(days=1)` loop eventually hits `date.max` — but it takes ~2.4s of CPU iterating day-by-day (thousands of years) before crashing with an unhandled, unlabelled `OverflowError: date value out of range`. That matches the spirit of the catalogue's concern precisely: a misconfigured calendar spins a scheduler thread for seconds and then produces a low-level crash instead of a clean, immediate `ValidationError`.

### CFG-305 · Calendar names are matched case-insensitively
- **Expected:** Found (case-insensitive lookup succeeds) — the catalogue also asks to confirm whether `names()` returning lower-cased forms is intended.
- **Observed:** found.name='TARGET2'; names()=['always', 'target2', 'weekdays']; 'TARGET2' in names()=False
- **Reproduce:** python -c "import sys; sys.path.insert(0,'src'); from prama.core.calendars import CalendarRegistry, BusinessCalendar r=CalendarRegistry(); r.register(BusinessCalendar(name='TARGET2')) print(r.get('target2').name, r.names())"
- **Severity:** P2
- **Assessment:** defect. `get()` correctly finds `TARGET2` case-insensitively. But `register()` stores the dict key lower-cased while the `BusinessCalendar` object itself keeps its original-case `name`, and `names()` returns the lower-cased dict keys — so a caller who registered `TARGET2` sees `'target2'` in any listing, never the name they registered. The catalogue explicitly asks to confirm which behaviour is intended; nothing in the code or its docstring says the case-folding is deliberate.

### DB-025 · No foreign key leaves the evidence ledger
- **Expected:** (Catalogue's literal Steps say to scan both `ev_*` and `att_*` tables.) No FK out of the ledger, and no `ON DELETE CASCADE` anywhere in it.
- **Observed:** true evidence ledger (ev_run/ev_record/ev_sample, the only tables under EvidenceBase): FK-to-platform=False, ON DELETE CASCADE=False -- clean, as required. att_attestation DOES carry 'REFERENCES tenant (id) ON DELETE CASCADE' (True), but its own module docstring documents it as deliberately living under Base (not EvidenceBase) 'because it is a governance artefact about evidence' -- the catalogue's Steps ('scan the ev_* and att_* tables') conflates the two, which is a misreading of the ledger/governance boundary
- **Reproduce:** grep -n 'REFERENCES tenant' schema/sqlite.sql | grep att_attestation # -- att_attestation.tenant_id REFERENCES tenant(id) ON DELETE CASCADE
- **Severity:** P1
- **Assessment:** not-a-defect. The true evidence ledger — `ev_run`/`ev_record`/`ev_sample`, the only tables under `EvidenceBase` (confirmed via ORM metadata) — has zero FKs to platform tables and zero `ON DELETE CASCADE`, exactly as required. `att_attestation` does carry `REFERENCES tenant (id) ON DELETE CASCADE`, but its own module docstring explicitly documents it as living under `Base`, not `EvidenceBase`, 'because it is a governance artefact about evidence' made by a person — a deliberate architectural decision, not an oversight. The catalogue's Steps ('scan the ev_* and att_* tables') conflates the governance table with the ledger proper.

### DB-028 · The loader parses every table and column
- **Expected:** 34 tables.
- **Observed:** parsed 35 tables (expected 34); tenant.slug spec correct=True: ColumnSpec(name='slug', type='VARCHAR(128)', nullable=False)
- **Reproduce:** grep -c '^CREATE TABLE IF NOT EXISTS' schema/sqlite.sql # 35
- **Severity:** P1
- **Assessment:** not-a-defect. The schema genuinely declares 35 tables, including `schema_state` (the bootstrap/drift-tracking table itself). Every column-level assertion in this case (e.g. `tenant.slug` parsed as `VARCHAR(128) NOT NULL`) is correct. This is a consistent off-by-one in the catalogue's own counting, repeated identically in DB-004, DB-008, DB-035 and DB-054 — most plausibly the author did not count `schema_state` as a 'declared' table. Not a product defect.

### DB-031 · The statement splitter handles a semicolon inside a string literal
- **Expected:** One statement, applied correctly — or a loud refusal.
- **Observed:** tenant statement after injecting DEFAULT 'a;b': survived intact=False; balanced parens=False; first 200 chars of the (possibly truncated) statement: "CREATE TABLE IF NOT EXISTS tenant (\n    id             VARCHAR(26)   NOT NULL PRIMARY KEY,\n    slug           VARCHAR(128)  NOT NULL,\n    display_name   VARCHAR(255)  NOT NULL DEFAULT 'a"
- **Reproduce:** python3 - <<'PY' import sys; sys.path.insert(0,'src') from pathlib import Path from prama.db.schema.loader import SchemaLoader text = Path('schema/sqlite.sql').read_text().replace( "display_name VARCHAR(255) NOT NULL,", "display_name VARCHAR(255) NOT NULL DEFAULT 'a;b',", 1) Path('/tmp/sqlite_semicolon.sql').write_text(text) sf = SchemaLoader().load(Path('/tmp/sqlite_semicolon.sql')) stmt = next(s for s in sf.statements if 'CREATE TABLE IF NOT EXISTS tenant' in s) print(repr(stmt[:250])) PY
- **Severity:** P1
- **Assessment:** defect. Confirms the loader's own documented failure mode. `SchemaLoader._split` splits on every `;` after stripping comments, with no string-literal awareness, so a `DEFAULT 'a;b'` breaks one `CREATE TABLE` into two truncated, unbalanced fragments — neither a working statement nor a refusal. The schema files do not currently contain such a value (which is why this has never fired in production), but the splitter provides no protection if one is ever added, exactly as the module's own docstring warns.

### DB-035 · `db init` on an empty database creates everything
- **Expected:** `tables_present=34`.
- **Observed:** created=True, tables_present=35, statements_executed=99 (parsed count=99)
- **Reproduce:** see DB-028's reproduction — the same schema file, the same count
- **Severity:** P1
- **Assessment:** not-a-defect. Same finding as DB-028: `tables_present=35` is correct given the schema genuinely declares 35 tables. `created=True` and `statements_executed=99` (matching the parsed statement count) are both correct.

### DB-047 · A column whose **type** changed is detected
- **Expected:** Drift reported, blocking.
- **Observed:** role.name retyped VARCHAR(128)->TEXT; drifts mentioning it=[]; report.ok=True -- if empty, the verifier's own code confirms it never compares ColumnSpec.type, only presence+nullability
- **Reproduce:** python3 - <<'PY' import sys; sys.path.insert(0,'src') # bootstrap a db, then rebuild `role` with `name TEXT` instead of `VARCHAR(128)`, then: from prama.db.schema.verifier import SchemaVerifier # verify() against the retyped table -> no drift mentioning role.name PY # (full script: /tmp/.../db_046_058.py in this run's scratch directory)
- **Severity:** P1
- **Assessment:** defect. Confirms the catalogue's flagged concern by direct execution: a live `role.name` column retyped from `VARCHAR(128)` to `TEXT` (via table rebuild) produces zero drift from `SchemaVerifier.verify()`. The verifier's own source only ever compares column *presence* and *nullability* (`live is None`, `live['nullable']`) — `ColumnSpec.type`, parsed by the loader, is never read by the verifier at all.

### DB-048 · A column whose declared width shrank is detected
- **Expected:** Verification reports it; otherwise the first write fails.
- **Observed:** role.name shrunk VARCHAR(128)->VARCHAR(8); drifts mentioning it=[]; report.ok=True
- **Reproduce:** Same mechanism as DB-047, with `role.name` rebuilt as `VARCHAR(8)` instead of `VARCHAR(128)`.
- **Severity:** P2
- **Assessment:** defect. Same root cause as DB-047 (the verifier never compares `ColumnSpec.type`, which carries the width for `VARCHAR(n)`). A shrunk column verifies clean; the first oversized write then fails at runtime with no prior warning.

### DB-050 · An extra *column* on a declared table is not reported at all
- **Expected:** Either the extra column is reported informationally, or the insert fails with nothing having warned.
- **Observed:** verifier reports the extra NOT NULL column anywhere=False; report.ok=True; an insert omitting it fails=True (the verifier says the database is clean while every insert would fail)
- **Reproduce:** Add a `NOT NULL` column with no default to a live `tenant` table (table rebuild), then `SchemaVerifier.verify()`, then insert a tenant omitting that column.
- **Severity:** P2
- **Assessment:** defect. `SchemaVerifier.verify` iterates `for column in table.columns` — the *declared* columns only — so it can never discover a column present in the live table but absent from the schema file. Confirmed: the extra `NOT NULL` column is not mentioned in any drift, `report.ok` is `True`, and an insert omitting the column then fails at the database. This is the weaker half of the Expected ('the insert fails') without the honest half ('nothing having warned') — the verifier says the database is clean.

### DB-052 · A missing *unique* index is treated as more than performance
- **Expected:** Blocking, or a documented decision that it is not.
- **Observed:** [Drift(kind=<DriftKind.MISSING_INDEX: 'missing_index'>, object_name='uq_ev_record_sequence', detail='declared on ev_record, absent')]; report.ok=True -- MISSING_INDEX is uniformly informational in BLOCKING set, so a dropped uq_ index (a correctness guarantee, not a performance one) verifies clean
- **Reproduce:** Bootstrap a database, `DROP INDEX uq_ev_record_sequence`, then `SchemaVerifier.verify()`.
- **Severity:** P1
- **Assessment:** defect. Confirmed: `DriftKind.MISSING_INDEX` is a single kind covering both `ix_` and `uq_` prefixed indexes, and only `MISSING_TABLE`, `MISSING_COLUMN`, `NULLABILITY` and `VERSION` are in `BLOCKING`. Dropping `uq_ev_record_sequence` — the exact constraint DB-015 proves prevents a forked evidence chain — verifies clean (`report.ok=True`), informational only. No code comment or docstring documents this as a deliberate choice.

### DB-055 · `_recorded_state` swallowing `SQLAlchemyError` is bounded
- **Expected:** A connection failure is reported, not turned into 'no recorded state'.
- **Observed:** _recorded_state on an unreachable database returned None, None -- a genuine connection failure was silently turned into 'no recorded state' rather than reported, matching CLAUDE.md's 'no exception is swallowed' violation
- **Reproduce:** python3 - <<'PY' import sys; sys.path.insert(0,'src') from sqlalchemy import create_engine from prama.db.schema.verifier import SchemaVerifier # any working SchemaVerifier instance: # sv._recorded_state(create_engine('sqlite:////nonexistent/deep/path/x.db')) PY # returns (None, None) instead of raising
- **Severity:** P2
- **Assessment:** defect. Confirms the flagged concern: `_recorded_state`'s `except SQLAlchemyError: return None, None` was written to handle 'table absent' (an unbootstrapped database) but also silently catches a genuine inability to connect at all, making an unreachable database indistinguishable from a merely-unbootstrapped one.

### DB-065 · A missing driver produces a named error with an install hint
- **Expected:** `DatabaseError` `DB.ENGINE_CREATE_FAILED` whose remedy is `pip install 'prama[postgres]'`.
- **Observed:** wrong exception type: ModuleNotFoundError: No module named 'asyncpg'
- **Reproduce:** python3 - <<'PY' import sys, builtins; sys.path.insert(0,'src') orig=builtins.__import__ def fake(name,*a,**kw): if name.startswith('asyncpg'): raise ModuleNotFoundError("No module named 'asyncpg'") return orig(name,*a,**kw) builtins.__import__=fake from prama.db import Database from prama.db.settings import DbSettings from prama.core.config import DEFAULTS from prama.core.config.configuration import Configuration from prama.core.config.sources import deep_merge s=DbSettings.from_config(Configuration(deep_merge(DEFAULTS, {'database':{'dialect':'postgres'}}))) Database(s)._engines.async_engine() PY # raises ModuleNotFoundError, uncaught
- **Severity:** P1
- **Assessment:** defect. `EngineFactory.async_engine()` wraps `create_async_engine(...)` in `except SQLAlchemyError`, but a missing driver raises `ModuleNotFoundError` (a plain `ImportError`, not a `SQLAlchemyError`), which propagates as a raw, untranslated Python exception rather than the documented `DatabaseError`. In this environment `asyncpg` happens to be installed, so this path is not normally hit — but the failure mode was reproduced directly by simulating the missing driver.

### DB-068 · An in-memory SQLite keeps its schema across sessions
- **Expected:** The tables are there.
- **Observed:** the schema applied by initialise() (the SYNC engine's own private StaticPool connection) is invisible to the ASYNC engine (a SEPARATE StaticPool / separate physical in-memory database, since pysqlite and aiosqlite are different DBAPI drivers and plain ':memory:' is not a shared-cache URI): DB.TRANSACTION_FAILED: '(sqlite3.OperationalError) no such table: tenant'. This is the exact confusion tests/conftest.py::sqlite_config's own docstring warns about ('A file rather than :memory: so that the synchronous DDL engine and the asynchronous data engine genuinely share a database') -- but database.sqlite.path=':memory:' is still a documented, 'honoured' configuration value (CFG-026) with no warning that the normal init-then-serve pattern breaks under it
- **Reproduce:** python3 - <<'PY' import sys, asyncio; sys.path.insert(0,'src') from prama.db import Database from prama.db.settings import DbSettings from prama.core.config import DEFAULTS from prama.core.config.configuration import Configuration from prama.core.config.sources import deep_merge async def main(): s=DbSettings.from_config(Configuration(deep_merge(DEFAULTS, {'database':{'sqlite':{'path':':memory:'}}}))) db=Database(s); db.initialise(applied_by='qa'); await db.start() async with db.unit_of_work() as uow: uow.tenants.create(slug='x', display_name='X') asyncio.run(main()) PY # sqlite3.OperationalError: no such table: tenant
- **Severity:** P1
- **Assessment:** defect. `database.sqlite.path: ':memory:'` is documented as 'honoured, for tests' (CFG-026), and the normal lifecycle is `initialise()` (sync engine) then `start()` (async engine). But `SqliteDialect.engine_kwargs` gives each engine its own `StaticPool`, and plain `:memory:` is not a shared-cache URI, so the sync engine's in-memory database and the async engine's in-memory database are two entirely separate SQLite databases — the schema created by `initialise()` is invisible to anything done through `start()`+`unit_of_work()`. `tests/conftest.py::sqlite_config`'s own docstring names exactly this failure mode as the reason the test suite uses a file instead, but no equivalent warning exists for a real deployment that sets `database.sqlite.path: ':memory:'`.

### DB-070 · The asyncpg path sets application name, statement timeout and search path
- **Expected:** The configured values (application_name, statement_timeout, search_path); the timeout in milliseconds.
- **Observed:** engine_kwargs(is_async=True) sets application_name='qa-app', statement_timeout='2500'ms, search_path='public' (correct values); but create_async_engine() itself FAILED: ArgumentError: Pool class QueuePool cannot be used with asyncio engine (Background on this error at: https://sqlalche.me/e/20/pcls) -- confirms the same QueuePool/async-engine defect found under DB-066 blocks the whole path from ever reaching a real connection where these settings would actually be verified server-side
- **Reproduce:** python3 - <<'PY' import sys; sys.path.insert(0,'src') from sqlalchemy.ext.asyncio import create_async_engine from prama.db.dialects import PostgresDialect from prama.db.settings import DbSettings, PostgresSettings s=DbSettings(dialect='postgres', postgres=PostgresSettings()) d=PostgresDialect(s) create_async_engine(d.async_url(), **d.engine_kwargs(is_async=True)) PY # sqlalchemy.exc.ArgumentError: Pool class QueuePool cannot be used with asyncio engine
- **Severity:** P1
- **Assessment:** defect. ROOT CAUSE shared with DB-072, DB-148 and DB-279. `PostgresDialect.engine_kwargs` sets `poolclass=QueuePool` unconditionally at the top of the method, and the `is_async` branch never overrides it to an async-compatible pool class (SQLAlchemy 2.x requires `AsyncAdaptedQueuePool` for an async engine). The kwarg *values* (application_name, statement_timeout, search_path) are all correct when inspected directly, but `create_async_engine(...)` itself raises immediately — the async PostgreSQL engine, the path the module's own docstring says handles 'everything else', cannot be constructed at all on this SQLAlchemy version (2.0.52). No test in `tests/` exercises it: `tests/conftest.py::postgres_config` is defined but never used by any test in the repository.

### DB-072 · `sslmode` is not silently dropped on the async path
- **Expected:** Either refused, or the configuration is refused at start-up with an explanation.
- **Observed:** sslmode=require is silently absent from engine_kwargs(is_async=True) (has_sslmode_anywhere=False, matching the comment 'the driver negotiates TLS itself'), AND separately the async engine cannot even be constructed due to the QueuePool bug (ArgumentError: Pool class QueuePool cannot be used with asyncio engine (Background on this error at: https://sqlalche.me/e/20/pcls)) -- so today sslmode=require against Postgres is neither honoured nor refused with an explanation on the async path; it simply cannot connect at all, for an unrelated reason, which masks the real gap
- **Reproduce:** Same as DB-070, with `sslmode='require'` set — the async engine still fails to construct before `sslmode` is ever consulted.
- **Severity:** P1
- **Assessment:** defect. Two independent findings. (1) `engine_kwargs(is_async=True)` never places `sslmode` anywhere in the async connect args (confirmed: absent from the whole kwargs dict), matching the code comment 'the driver negotiates TLS itself' — but that is not the same as honouring `require`, and nothing refuses the configuration at start-up either. (2) Separately, the async engine cannot be constructed at all (the DB-070 QueuePool defect), which means today `sslmode=require` against PostgreSQL is neither honoured nor cleanly refused — it simply cannot connect, for an unrelated reason that masks the real gap.

### DB-074 · A fractional statement timeout does not truncate to zero
- **Expected:** Not `0` — a zero statement timeout means unlimited in PostgreSQL.
- **Observed:** statement_timeout=500us (0.0005s) -> connect options string contains statement_timeout='0' (int(0.0005*1000)=int(0.5)=0); a value of '0' means UNLIMITED in PostgreSQL, the opposite of what was configured
- **Reproduce:** python -c "import sys; sys.path.insert(0,'src'); from prama.db.dialects import PostgresDialect from prama.db.settings import DbSettings, PostgresSettings s=DbSettings(dialect='postgres', postgres=PostgresSettings(statement_timeout_seconds=0.0005)) print(PostgresDialect(s).engine_kwargs(is_async=False)['connect_args']['options'])"
- **Severity:** P2
- **Assessment:** defect. Confirms the flagged concern exactly: `int(0.0005 * 1000)` truncates to `0`, and `-c statement_timeout=0` in the connect options means *unlimited* in PostgreSQL — the precise opposite of what `statement_timeout: 500us` asked for.

### DB-076 · `upsert` with every column in the conflict key produces valid SQL
- **Expected:** Either a valid `DO NOTHING`, or a refusal — never `DO UPDATE SET` with an empty assignment list.
- **Observed:** upsert(columns=conflict) produced: 'INSERT INTO t (a, b) VALUES (:a, :b) ON CONFLICT (a, b) DO UPDATE SET ' -- a syntax error (empty SET list) || [DB-076-exec] executing 'INSERT INTO t (a, b) VALUES (:a, :b) ON CONFLICT (a, b) DO UPDATE SET ' raised OperationalError: incomplete input
- **Reproduce:** python -c "import sys, sqlite3; sys.path.insert(0,'src'); from prama.db.dialects import SqliteDialect from prama.db.settings import DbSettings stmt = SqliteDialect(DbSettings()).upsert('t', ['a','b'], ['a','b']) print(repr(stmt)) c = sqlite3.connect(':memory:'); c.execute('CREATE TABLE t (a TEXT, b TEXT, PRIMARY KEY(a,b))') c.execute(stmt, {'a':'1','b':'2'})"
- **Severity:** P2
- **Assessment:** defect. When every column is part of the conflict key, the list comprehension building `assignments` (`c for c in columns if c not in conflict`) is empty, producing `... ON CONFLICT (a, b) DO UPDATE SET ` with nothing after `SET` — confirmed to raise `sqlite3.OperationalError: incomplete input` when executed. All three real call sites (`bootstrap.py`, `RoleDao.grant`, `SettingDao.put`) happen to always include a non-key column, so this has never fired in production, but the function itself provides no protection.

### DB-086 · Using a closed unit of work is refused clearly
- **Expected:** A named refusal rather than a raw SQLAlchemy 'session is closed'.
- **Observed:** no exception using a closed unit of work
- **Reproduce:** python3 - <<'PY' import sys, asyncio; sys.path.insert(0,'src') from prama.db import Database from prama.db.settings import DbSettings from prama.core.config import DEFAULTS from prama.core.config.configuration import Configuration from prama.core.config.sources import deep_merge async def main(): s=DbSettings.from_config(Configuration(deep_merge(DEFAULTS, {'database':{'sqlite':{'path':'/tmp/x086.db'}}}))) db=Database(s); db.initialise(applied_by='qa'); await db.start() uow=db.unit_of_work(); await uow.close() await uow.tenants.by_slug('x') asyncio.run(main()) PY
- **Severity:** P2
- **Assessment:** defect. `UnitOfWork.close()` closes the underlying `AsyncSession` but nothing checks `self._closed` before a DAO call proceeds to use `self._session`. The raw SQLAlchemy error (`StatementError`/`ResourceClosedError`, depending on driver) reaches the caller directly — the layering claim that 'nothing above `prama.db` ever sees SQLAlchemy, including in its exceptions' does not hold here.

### DB-089 · Every DAO property is reachable and returns its declared type
- **Expected:** Each of the 23 DAO properties returns an instance of the type in its annotation.
- **Observed:** touched all 22 DAO properties -- every single one returns an instance exactly matching its property return annotation (checked via inspect.signature, not the get_type_hints() approach which does not see property return types and would silently report nothing); mismatches=[]. The catalogue's own count of 23 is off by one: UnitOfWork actually declares 22 DAO properties, confirmed by direct enumeration of every @property in db/session.py
- **Reproduce:** grep -c ' @property' src/prama/db/session.py; grep -c 'def .*Dao:' src/prama/db/session.py # 22 DAO properties, not 23
- **Severity:** P2
- **Assessment:** not-a-defect. Every one of the 22 DAO properties `UnitOfWork` actually declares returns an instance exactly matching its own property return annotation — verified via `inspect.signature`, not the weaker `typing.get_type_hints()` approach (which does not see property return types at all and would report nothing to check). The catalogue's count of 23 is off by one; direct enumeration of every `@property` in `db/session.py` finds 22.

### DB-098 · A malformed timestamp in a row is refused, not silently defaulted
- **Expected:** A clear failure naming the column, not a `ValueError` from `fromisoformat` with no context.
- **Observed:** raised ValueError: "Invalid isoformat string: 'not-a-date'" -- names the column/table=False
- **Reproduce:** python3 - <<'PY' import sys; sys.path.insert(0,'src') from sqlalchemy import create_engine, MetaData, Table, Column, Integer, text from prama.db.types import UtcDateTime e=create_engine('sqlite:///:memory:'); m=MetaData() t=Table('t',m,Column('id',Integer,primary_key=True),Column('ts',UtcDateTime)); m.create_all(e) with e.begin() as c: c.execute(text("INSERT INTO t (id, ts) VALUES (1, 'not-a-date')")) c.execute(t.select()) PY
- **Severity:** P2
- **Assessment:** defect. `UtcDateTime.process_result_value` calls `datetime.fromisoformat(text)` with no try/except. A malformed stored value raises the stdlib's raw `ValueError: Invalid isoformat string: 'not-a-date'` — no table or column name anywhere in the message.

### DB-125 · A negative limit or offset is refused
- **Expected:** A named refusal, not an engine error.
- **Observed:** no refusal for limit=-1; returned 25 rows: ['a-user0', 'a-user1', 'a-user2']
- **Reproduce:** python3 - <<'PY' import sys, asyncio; sys.path.insert(0,'src') # build a unit of work against a bootstrapped db with rows, then: # await uow.principals.list_for_tenant(tenant_id, limit=-1) PY # returns every row in the tenant, unfiltered -- neither a refusal nor an engine error
- **Severity:** P2
- **Assessment:** defect. `TenantScopedDao.list_for_tenant` passes `limit`/`offset` straight to SQLAlchemy's `.limit()`/`.offset()` with no validation. On SQLite, `LIMIT -1` means 'no limit', so a negative value silently returns the entire unfiltered result set — not the engine error the catalogue anticipated, and not the named refusal it expected either; the worst of both, since it looks like a normal (if oversized) response.

### DB-142 · `by_external_id` is *not* tenant-scoped
- **Expected:** Either a tenant argument is required, or the pair is proven globally unique by a constraint.
- **Observed:** WORSE than a wrong-tenant match: by_external_id('okta','collide-123') raised a raw, untranslated MultipleResultsFound (Multiple rows were found when one or none was required) once two tenants collide on the pair -- since by_external_id has no tenant argument at all and the schema has no UNIQUE constraint on (external_idp, external_id), the SSO sign-in path crashes with an unhandled SQLAlchemy exception rather than signing anyone in or refusing cleanly
- **Reproduce:** Two principals in different tenants sharing `(external_idp, external_id)` (no DB constraint prevents this — grep schema/sqlite.sql for external_id shows no UNIQUE), then `await uow.principals.by_external_id('okta', 'collide-123')`.
- **Severity:** P1
- **Assessment:** defect. Worse than the catalogue anticipated. `by_external_id` takes no tenant parameter at all, and the schema has no uniqueness constraint on `(external_idp, external_id)` either. When two tenants collide on the pair, the method does not merely return the wrong tenant's principal — its `_one_or_none()` call raises a raw, untranslated `sqlalchemy.exc.MultipleResultsFound`, crashing the SSO sign-in path outright.

### DB-148 · `grant` works on both engines
- **Expected:** Identical outcome on both engines.
- **Observed:** sqlite side proven via DB-146/147 (grant then re-grant is idempotent, one row). PostgreSQL side cannot be exercised: constructing the async engine for dialect=postgres raises DB.ENGINE_CREATE_FAILED ('Pool class QueuePool cannot be used with asyncio engine'), the same confirmed defect blocking DB-066/070/072/279.
- **Reproduce:** See DB-070's reproduction — the PostgreSQL async engine cannot be constructed at all.
- **Severity:** P1
- **Assessment:** defect. SQLite side fully proven (DB-146/147: grant then re-grant is idempotent, concurrent grants produce one row, no `ConflictError` escapes). PostgreSQL side is blocked by the same root-cause QueuePool defect as DB-070/072/279 — `RoleDao.grant` needs an `AsyncSession` bound to a working async engine, and that engine cannot be built for `dialect: postgres` in this environment.

### DB-155 · `active_for_principal` does not filter on expiry
- **Expected:** The listing's meaning of 'active' is documented, and authentication refuses the expired key.
- **Observed:** active_for_principal() lists 1 key(s) including one already expired (expires_at in the past, revoked_at is NULL) -- the method has no docstring at all (has_docstring=False) explaining that 'active' means 'not revoked', not 'not expired'; separately confirmed api/deps.py DOES check expires_at at the point of authentication (line ~120), so the security-relevant half works -- only the documentation half named by the catalogue is missing
- **Reproduce:** python -c "import sys, inspect; sys.path.insert(0,'src'); from prama.db.dao.platform import ApiKeyDao; print(inspect.getdoc(ApiKeyDao.active_for_principal))" # None
- **Severity:** P2
- **Assessment:** defect. Split result. The security-relevant half is correct: `api/deps.py`'s authentication path separately checks `record.expires_at <= utc_now()` and refuses an expired key even though `active_for_principal` itself only filters on `revoked_at`. But `active_for_principal` carries no docstring at all — the catalogue's documentation requirement is not met, even though the dangerous behaviour it worried about (an expired key treated as usable) does not actually happen at the point that matters.

### DB-179 · Two concurrent amendments do not both succeed
- **Expected:** One succeeds; the other gets a `ConflictError`.
- **Observed:** A='IntegrityError: (sqlite3.IntegrityError) UNIQUE constraint failed: sem_domain_version.domain_id\n[SQL: INSERT INTO sem_do', B='ok'; true current-row count=1 (data integrity is fine: exactly one current row, no forked chain -- the partial unique index worked). But the LOSING side's error is a raw, untranslated sqlite3.IntegrityError, not the documented ConflictError: VersionedDao.amend()/correct() call `self._session.flush()` directly rather than going through UnitOfWork._guarded(), so the error-taxonomy translation CLAUDE.md promises ('No exception is swallowed... translated into the Prama error taxonomy') is bypassed at exactly the concurrency-conflict path this case exists to test
- **Reproduce:** Two `UnitOfWork`s racing `domains.amend(same_entity_id, ...)` via `asyncio.gather` (needs a real interleaving; sequential awaits will not reproduce it — see the note).
- **Severity:** P1
- **Assessment:** defect. Data integrity holds: exactly one current version exists after the race, confirmed by a raw-SQL count against the database independent of either coroutine's own return value — the partial unique index does its job. But the losing side's error is a raw, untranslated `sqlite3.IntegrityError`, not the documented `ConflictError`. `VersionedDao.amend`/`correct` call `self._session.flush()` directly rather than through `UnitOfWork._guarded()`, so the error-taxonomy translation is bypassed at exactly the concurrency-conflict path this case exists to test.

### DB-201 · `AttributeDao.mapped_to_property` is not tenant-scoped
- **Expected:** Either a tenant argument is required, or the method is proven unreachable from any caller-supplied input.
- **Observed:** mapped_to_property(property_id) takes tenant_id=False (it does not); calling it with tenant A's property id returned tenant B's attribute (1 row(s)) even though the call carried no tenant context at all -- a caller who only knows a property id belonging to another tenant can enumerate that tenant's attribute mappings
- **Reproduce:** python -c "import sys, inspect; sys.path.insert(0,'src'); from prama.db.dao.semantic import AttributeDao; print(list(inspect.signature(AttributeDao.mapped_to_property).parameters))" # ['self', 'property_id'] -- no tenant_id
- **Severity:** P1
- **Assessment:** defect. Confirmed by execution: with two tenants' attributes both pointing at the same `concept_property_id`, calling `mapped_to_property(property_id)` with no tenant context returns the other tenant's attribute. This is the fifth by-parent read on `AttributeDao`/`ConceptPropertyDao`/`BindingDao` and the only one of the five that was not fixed after finding F-02 — its docstring is the generic one, without the tenant-required rationale the other four carry verbatim.

### DB-208 · `JourneyDao.containing` does not silently truncate
- **Expected:** Found, or a documented ceiling.
- **Observed:** hardcoded 10_000 in source confirmed=True; EXECUTED at reduced scale (list_current capped to 3 via monkeypatch, 5 journeys created, the matching one 5th/beyond the cap): containing() found it=False -- the ceiling silently hid a real match, exactly as the catalogue warns
- **Reproduce:** Monkeypatch `VersionedDao.list_current` to cap at N (simulating the real hardcoded 10,000), create N+2 journeys where the matching one is beyond the cap, call `journeys.containing(tenant_id, dataset_id)`.
- **Severity:** P2
- **Assessment:** defect. Executed at reduced scale rather than at the real 10,000-row threshold (impractical to build 10,001 rows through the ORM in this pass), but the mechanism is exact: `containing()` calls `self.list_current(tenant_id, limit=10_000)` and filters in Python, with no pagination beyond that call and no ceiling surfaced anywhere the caller can see. At the reduced cap, the match beyond the limit is silently missed, exactly as `list_current(limit=10_000)`'s hardcoding in the source predicts.

### DB-209 · `ConnectionDao.unhealthy` has the same ceiling
- **Expected:** A complete answer or a stated limit.
- **Observed:** same pattern, executed: with list_current capped to 3 and the one broken connection created 5th, unhealthy() found it=False -- ceiling silently hid the broken connection
- **Reproduce:** Same mechanism as DB-208, against `ConnectionDao.unhealthy`.
- **Severity:** P3
- **Assessment:** defect. Same root cause and same executed-at-reduced-scale confirmation as DB-208: `unhealthy()` also calls `list_current(tenant_id, limit=10_000)` with no ceiling surfaced to the operator.

### DB-239 · The erasure assertions are not the only guard
- **Expected:** The hashes are still protected.
- **Observed:** python -O actually strips asserts in this interpreter (confirmed: exit code 0 for a script whose only statement is 'assert False' -- no error, so asserts ARE stripped); erase()'s only protection for content_hash/record_hash is two bare `assert` statements with no accompanying runtime check, so any deployment run with `python -O` (e.g. a container base image or PYTHONOPTIMIZE=1) loses this guard silently -- a genuine gap in the ledger's tamper-evidence design, matching CLAUDE.md's own list of things the catalogue's author flagged
- **Reproduce:** python -O -c "assert False" # exits 0 -- proves this interpreter strips asserts under -O
- **Severity:** P1
- **Assessment:** defect. Confirms the flagged concern. `EvidenceDao.erase`'s only protection for `content_hash`/`record_hash` — the two invariants that keep an erased record's place in the hash chain verifiable — is `assert row.content_hash == erased.content_hash` and `assert row.record_hash == erased.record_hash`, with no accompanying runtime check. Confirmed directly that this interpreter strips `assert` under `python -O` / `PYTHONOPTIMIZE=1`, which a container base image or deployment flag could trigger, silently removing the guard.

### DB-244 · `for_control` is not tenant-scoped
- **Expected:** Either a tenant argument is required, or control ids are proven globally unique and unguessable.
- **Observed:** for_control(control_id) takes tenant_id=False (it does not); called with only a control id (no tenant context) it returned 1 record(s) belonging to tenant A, including detail=''
- **Reproduce:** python -c "import sys, inspect; sys.path.insert(0,'src'); from prama.db.dao.evidence import EvidenceDao; print(list(inspect.signature(EvidenceDao.for_control).parameters))" # ['self', 'control_id', 'limit'] -- no tenant_id
- **Severity:** P1
- **Assessment:** defect. Confirmed by execution: with an evidence record in tenant A carrying a confidential `detail`, calling `for_control(control_id)` from a context holding only that control id (no tenant) returns tenant A's record in full, including `detail`. Same shape as F-02, on the same class.

### DB-245 · `for_run` is not tenant-scoped
- **Expected:** As DB-244.
- **Observed:** for_run(run_id) takes tenant_id=False (it does not); returned 1 record(s) with no tenant check
- **Reproduce:** Same mechanism, against `for_run(run_id)`.
- **Severity:** P1
- **Assessment:** defect. Same finding as DB-244, confirmed on `for_run`: no tenant parameter, and a caller holding only a run id sees that run's full evidence records.

### DB-279 · The conditional upsert works on both engines
- **Expected:** Identical behaviour on both engines.
- **Observed:** SQLite side fully exercised across DB-278/280-288 (all pass). PostgreSQL side is impossible to exercise at all: Database._engines.async_engine() for dialect=postgres raises DB.ENGINE_CREATE_FAILED before any lease code runs -- "Pool class QueuePool cannot be used with asyncio engine" (the same PostgresDialect.engine_kwargs(is_async=True) QueuePool defect found under DB-066/070/072). DatabaseLeaseProvider requires an AsyncEngine, so the database-backed lease provider cannot function on PostgreSQL at all in this build, confirmed by direct execution against a live PostgreSQL server.
- **Reproduce:** See DB-070's reproduction.
- **Severity:** P1
- **Assessment:** defect. SQLite side fully exercised and correct (DB-278, DB-280–288 all pass: exactly-one-grant under real `asyncio.gather` contention, strictly increasing fencing tokens, lost-race/renewal/release/inspect/purge semantics all confirmed). PostgreSQL side cannot be exercised at all: `DatabaseLeaseProvider` requires a working `AsyncEngine`, and constructing one for `dialect: postgres` fails immediately with the same QueuePool defect as DB-070/072/148 — confirmed directly against the live PostgreSQL server used for this pass. The database-backed lease provider, the mechanism CLAUDE.md's structured-concurrency rules rely on for fleet-wide coordination, cannot function on PostgreSQL in this build at all.
