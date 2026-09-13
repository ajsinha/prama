# -*- coding: utf-8 -*-
import re

SP = "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/plat1"

rows = []
for line in open(f"{SP}/consolidated.tsv", encoding="utf-8"):
    id_, result, obs = line.rstrip("\n").split("\t", 2)
    rows.append((id_, result, obs))

def sortkey(row):
    area, num = row[0].split("-")
    return (area, int(num))
rows.sort(key=sortkey)

total = len(rows)
counts = {"PASS": 0, "FAIL": 0, "BLOCKED": 0}
for _, r, _ in rows:
    counts[r] += 1

# ---------------------------------------------------------------------------
# Failure details: Expected / Reproduce / Severity / Assessment
# ---------------------------------------------------------------------------
# severity: P1/P2/P3 (taken from the catalogue, occasionally elevated/lowered
# when the assessment changes the practical impact)
F = {}  # id -> dict(expected, reproduce, severity, assessment, note)

F["CFG-008"] = dict(
    expected="A named refusal with a remedy listing the accepted logging levels.",
    reproduce="python -c \"import sys; sys.path.insert(0,'src'); from prama.core.log import LoggingConfigurator; LoggingConfigurator(level='VERBOSE').apply()\"",
    severity="P2", assessment="defect",
    note="`LoggingConfigurator.apply()` calls `root.setLevel(self._level)` with no validation. An unknown level raises the stdlib's bare `ValueError: Unknown level: 'VERBOSE'` — not a `PramaError` subclass, no code, no remedy.")

F["CFG-014"] = dict(
    expected="The shipped comment describes the value; since the value is `True`, a comment saying it is 'off' is wrong and must be corrected.",
    reproduce="grep -A2 'session_secret' src/prama/core/config/defaults.py  # the comment above cookies_https_only says 'Off in development' while the value is True",
    severity="P2", assessment="defect",
    note="Documentation-only. `defaults.py`'s comment block describes `cookies_https_only` as off in development, but the shipped default is `True` (on). The behaviour is fine; the comment is backwards.")

F["CFG-020"] = dict(
    expected="A refusal, not a preview that silently returns nothing.",
    reproduce="python -c \"import sys; sys.path.insert(0,'src'); import duckdb; from prama.execute.preview import Preview\n"
              "con=duckdb.connect(':memory:'); con.execute('CREATE TABLE t(a INTEGER)'); con.execute('INSERT INTO t VALUES (1),(2),(3)')\n"
              "def execute(sql):\n cur=con.execute(sql); names=[c[0] for c in cur.description or ()]; return [dict(zip(names,r)) for r in cur.fetchall()]\n"
              "p=Preview(execute=execute, engine='duckdb', max_rows=0)\n"
              "t=p.once(\\\"CHECK t.a IS NOT NULL SEVERITY critical DIMENSION completeness BECAUSE 'x'\\\"); print(t.verdict, t.scanned_rows)\"",
    severity="P2", assessment="not-a-defect",
    note="`max_rows=0` is not refused, but it is not silently empty either: the code and `config/application.yaml`'s own comment ('Zero is unbounded') define 0 as *unbounded*, and `Preview._trial` separately guards the specific danger the case is worried about — it reports `no_data` (not `pass`) whenever `scanned_rows<=0`, regardless of `max_rows`. The catalogue assumed 0 meant 'cap of zero rows, so empty', which is not how the code works; the actual behaviour (scan everything) is safe and documented.")

F["CFG-021"] = dict(
    expected="Default `30`; `-1` refused with a remedy.",
    reproduce="grep -n 'backtest_days' src/prama/web/routes/preview_routes.py  # config.get_int(..., 30) is used directly with no negative guard",
    severity="P3", assessment="defect",
    note="The default (30) is correct. No negative-value guard was found anywhere `backtest_days` is read (`preview_routes.py` reads it straight into `_preview`'s `requested` count with no validation), so a negative value would reach date arithmetic unchecked. Verified by source inspection of every read site, not by driving the web route end-to-end.")

F["CFG-036"] = dict(
    expected="Either `disabled: []` is added to `DEFAULTS`, or its absence is deliberate and documented.",
    reproduce="python -c \"import sys; sys.path.insert(0,'src'); from prama.core.config.defaults import DEFAULTS; print('disabled' in DEFAULTS['plugins'])\"  # False, yet config/application.yaml line 106 ships 'disabled: []'",
    severity="P2", assessment="defect",
    note="`defaults.py`'s own docstring says 'this mapping is the authority and the file is documentation. Where the two could drift, a test compares them' — but `plugins.disabled` exists only in the tracked YAML, not in `DEFAULTS`, and nothing enforces agreement between them.")

F["CFG-040"] = dict(
    expected="A named refusal.",
    reproduce="python -c \"import sys; sys.path.insert(0,'src'); from prama.db.settings import DbSettings, PoolSettings\nprint(PoolSettings(max_overflow=-5))\"  # constructs cleanly; DbSettings.from_config likewise accepts it",
    severity="P2", assessment="defect",
    note="`PoolSettings.validate()` only checks `size <= 0`; `max_overflow` is never validated. SQLAlchemy treats a negative `max_overflow` as unbounded, silently defeating the cap an operator believed they set.")

F["CFG-048"] = dict(
    expected="`MemoryLeaseProvider` and `DatabaseLeaseProvider` respectively; an unknown value refused by name.",
    reproduce="grep -rn 'lease.provider\\|LeaseProvider(' src/prama/db/__init__.py  # Database.lease_provider() unconditionally returns DatabaseLeaseProvider(...); concurrency.lease.provider is never read",
    severity="P1", assessment="defect",
    note="No code anywhere in `src/prama` reads `concurrency.lease.provider`. `Database.lease_provider()` always builds a `DatabaseLeaseProvider`, so setting `provider: memory` has no effect at all, and an invalid value is not refused either — the key is entirely decorative.")

F["CFG-062"] = dict(
    expected="`CONFIG.FILE_UNREADABLE` — the decode failure is caught and translated rather than escaping as a traceback.",
    reproduce="python -c \"import sys; sys.path.insert(0,'src'); open('/tmp/latin1.yaml','wb').write('app:\\n  name: caf\\xe9\\n'.encode('latin-1'))\nfrom prama.core.config import load_configuration; load_configuration('/tmp/latin1.yaml', use_environment=False)\"",
    severity="P3", assessment="defect",
    note="Confirms the catalogue's own flagged concern exactly: `FileSource.load` only catches `except OSError`, and `UnicodeDecodeError` is a `ValueError`, not an `OSError`. A non-UTF-8 config file crashes with a raw traceback instead of `CONFIG.FILE_UNREADABLE`.")

F["CFG-082"] = dict(
    expected="The nested passwords are masked, or the gap is documented.",
    reproduce="python -c \"import sys; sys.path.insert(0,'src'); from prama.core.log import redact_mapping; print(redact_mapping({'connections':[{'password':'p1'},{'password':'p2'}]}))\"",
    severity="P2", assessment="defect",
    note="`redact_mapping` recurses into `dict` only; a `list` of mappings (the natural shape for a multi-connection config) passes through unmasked, and the gap is not documented anywhere (the function's docstring makes no mention of lists).")

F["CFG-088"] = dict(
    expected="The password is masked, or the limitation is documented.",
    reproduce="python -c \"import sys, logging; sys.path.insert(0,'src'); from prama.core.log import RedactionFilter\nr=logging.LogRecord('t',logging.INFO,'f',1,'connecting to postgresql://prama:hunter2@host/db',None,None)\nRedactionFilter().filter(r); print(r.msg)\"",
    severity="P2", assessment="defect",
    note="`_SENSITIVE_TEXT` only matches `key: value` / `key=value` forms; a DSN embeds the password after a colon inside a URL and is not matched. The gap is not documented, and a connection string is the single most likely thing to end up in a log line.")

F["CFG-094"] = dict(
    expected="`YYYY-MM-DDTHH:MM:SS.mmmZ`, i.e. a genuine UTC timestamp.",
    reproduce="TZ=America/New_York python -c \"import sys, logging, io; sys.path.insert(0,'src'); from prama.core.log import JsonFormatter, ContextFilter\nimport datetime; s=io.StringIO(); h=logging.StreamHandler(s); h.setFormatter(JsonFormatter()); h.addFilter(ContextFilter())\nroot=logging.getLogger('x'); root.handlers=[h]; root.setLevel(logging.INFO); root.propagate=False\nroot.info('hi'); print(s.getvalue()); print('actual utc:', datetime.datetime.now(datetime.UTC))\"",
    severity="P2", assessment="defect",
    note="`JsonFormatter.format` builds `ts` from `self.formatTime(record, ...)`, which uses `time.localtime` by default (`logging.Formatter.converter`) and is never overridden to `time.gmtime`. On a machine set to a non-UTC zone (confirmed on this host, EDT, UTC-4) the emitted `ts` is local wall-clock time with a trailing `Z` falsely claiming UTC — a 4-hour error in every structured log line, exactly the scenario the docstring says the module protects against.")

F["CFG-112"] = dict(
    expected="Refused at coercion or refused by the consumer; never applied.",
    reproduce="python -c \"import sys; sys.path.insert(0,'src'); from prama.core.config.coercion import Coercer; print(Coercer('x').to_duration_seconds(-5))\"  # -5.0, no exception",
    severity="P2", assessment="defect",
    note="The string form `'-5s'` is correctly refused (the regex has no sign), but the numeric form `-5` passes straight through the `isinstance(int|float)` branch and returns `-5.0`. The two representations of the same value disagree about validity, exactly as the catalogue's own 'Why' predicts.")

F["CFG-118"] = dict(
    expected="The value is masked in the raised error.",
    reproduce="python -c \"import sys; sys.path.insert(0,'src'); from prama.core.config.coercion import Coercer\ntry:\n Coercer('security.session_secret').to_int('supersecretvalue123')\nexcept Exception as e:\n print(e)\"",
    severity="P1", assessment="defect",
    note="`Coercer._fail` puts `context={'value': repr(value), ...}` into the raised `ConfigTypeError` unconditionally — it does not consult `SENSITIVE_KEYS` for the key it was constructed with. A coercion failure on `security.session_secret` (or any secret key) prints the raw value in the exception, which is exactly the kind of value that ends up in a log or an API problem document.")

F["CFG-162"] = dict(
    expected="No bare `datetime.now()` outside `core/clock.py`.",
    reproduce="grep -n 'datetime.now(' src/prama/cli/apikey.py",
    severity="P2", assessment="defect",
    note="`cli/apikey.py:98` calls `datetime.now(UTC)` directly to compute an API key's `expires_at`, instead of going through `utc_now()` or an injected `Clock`. Low real-world severity (it is UTC-aware, so not wrong data, just outside the deterministic-replay discipline the rest of the codebase follows) but a literal violation of the stated rule.")

F["CFG-169"] = dict(
    expected="The second id still sorts after the first.",
    reproduce="python -c \"import sys; sys.path.insert(0,'src'); from prama.core.ids import UlidFactory, ulid_timestamp_millis\nfrom prama.core.clock import ManualClock\nfrom datetime import datetime, timezone\nf=UlidFactory(clock=ManualClock(datetime(2026,1,1,0,0,1,tzinfo=timezone.utc)))\nfirst=f.new()\nf._clock=ManualClock(datetime(2026,1,1,0,0,0,tzinfo=timezone.utc))\nsecond=f.new()\nprint(first, second, second>first)\"",
    severity="P2", assessment="defect",
    note="Confirms the catalogue's flagged concern exactly. `UlidFactory.new`'s `else` branch (taken whenever `ms != self._last_ms`, which includes a *backwards* step) resets `_last_ms` to whatever the clock now says, so an NTP step backwards produces an id that sorts *before* the previous one — breaking the append-only, page-by-id-order guarantee several stores rely on.")

F["CFG-205"] = dict(
    expected="It runs repeatedly, incrementing `restarts`.",
    reproduce="python -c \"import sys, asyncio, time; sys.path.insert(0,'src'); from prama.core.concurrency.supervisor import TaskSupervisor, RestartPolicy\n"
              "async def main():\n"
              " sup=TaskSupervisor(base_backoff=0.2, max_backoff=30)\n"
              " calls=[]\n"
              " async def poller():\n  calls.append(time.monotonic())\n"
              " h=sup.spawn('poll', poller, policy=RestartPolicy.ALWAYS)\n"
              " await asyncio.sleep(3.0)\n"
              " await sup.shutdown()\n"
              " print(len(calls), h.restarts)\n"
              "asyncio.run(main())\"  # 5 calls in 3 seconds, not ~unlimited",
    severity="P2", assessment="defect",
    note="Bonus finding (not in the catalogue's pre-flagged list). `TaskSupervisor._run`'s restart-counting/backoff code sits *after* the try/except and runs unconditionally whenever the loop does not `return` — which for `RestartPolicy.ALWAYS` is every iteration, success or failure. A poller that succeeds every time is therefore throttled with the same exponential backoff as a crash loop: 5 calls in 3 seconds instead of ~unlimited, and the gap between polls keeps growing toward `max_backoff` (30s) the longer the poller runs successfully.")

F["CFG-256"] = dict(
    expected="Either the plugin is disabled, or the configuration key is removed from the tracked file.",
    reproduce="grep -rn '\\.disable(' src/prama --include='*.py'  # zero results anywhere in the codebase",
    severity="P2", assessment="defect",
    note="No call to `Registry.disable(...)` exists anywhere in `src/prama`. `config/application.yaml` ships `plugins.disabled: []` (CFG-036) but nothing ever reads that key into a `disable()` call — the configuration key does nothing.")

F["CFG-260"] = dict(
    expected="The failure is reported somewhere an operator sees it.",
    reproduce="grep -n 'health' src/prama/api/routes/meta.py  # /health reports only database.health(); no registry/plugin state anywhere",
    severity="P2", assessment="defect",
    note="`Registry.discover()`'s docstring claims a broken plugin's failure 'is visible in health output', but `Registry` exposes no failure-tracking attribute at all (confirmed: no `_failed`/`failures`/`discovery_errors`), and the only `/health` endpoint in the codebase reports database state exclusively. The only trace of a broken plugin is a `_log.warning(...)` call.")

F["CFG-262"] = dict(
    expected="The failure to enumerate is reported, not silently turned into 'no plugins found'.",
    reproduce="python -c \"import sys; sys.path.insert(0,'src'); import importlib.metadata as im\n"
              "class Broken:\n def __call__(self,*a,**kw): raise OSError('corrupted metadata')\n"
              "im.entry_points=Broken()\n"
              "from prama.core.registry import _entry_points_for; print(_entry_points_for('prama.connectors'))\"",
    severity="P2", assessment="defect",
    note="Confirms the flagged concern exactly. `_entry_points_for`'s `except Exception: return []` makes a corrupted or unreadable distribution-metadata directory indistinguishable from an install with no plugins at all — CLAUDE.md's 'no exception is swallowed' rule, violated.")

F["CFG-292"] = dict(
    expected="A bounded refusal, not an infinite loop.",
    reproduce="timeout 10 python -c \"import sys; sys.path.insert(0,'src'); from prama.core.calendars import BusinessCalendar\nfrom datetime import date\nc=BusinessCalendar(name='never', weekend_days=frozenset(range(7)))\nprint(c.next_business_day(date(2026,1,1)))\"",
    severity="P2", assessment="defect",
    note="Not a literal infinite loop — `date` has an internal maximum, so the `while not self.is_business_day(candidate): candidate += timedelta(days=1)` loop eventually hits `date.max` — but it takes ~2.4s of CPU iterating day-by-day (thousands of years) before crashing with an unhandled, unlabelled `OverflowError: date value out of range`. That matches the spirit of the catalogue's concern precisely: a misconfigured calendar spins a scheduler thread for seconds and then produces a low-level crash instead of a clean, immediate `ValidationError`.")

F["CFG-305"] = dict(
    expected="Found (case-insensitive lookup succeeds) — the catalogue also asks to confirm whether `names()` returning lower-cased forms is intended.",
    reproduce="python -c \"import sys; sys.path.insert(0,'src'); from prama.core.calendars import CalendarRegistry, BusinessCalendar\nr=CalendarRegistry(); r.register(BusinessCalendar(name='TARGET2'))\nprint(r.get('target2').name, r.names())\"",
    severity="P2", assessment="defect",
    note="`get()` correctly finds `TARGET2` case-insensitively. But `register()` stores the dict key lower-cased while the `BusinessCalendar` object itself keeps its original-case `name`, and `names()` returns the lower-cased dict keys — so a caller who registered `TARGET2` sees `'target2'` in any listing, never the name they registered. The catalogue explicitly asks to confirm which behaviour is intended; nothing in the code or its docstring says the case-folding is deliberate.")

F["DB-025"] = dict(
    expected="(Catalogue's literal Steps say to scan both `ev_*` and `att_*` tables.) No FK out of the ledger, and no `ON DELETE CASCADE` anywhere in it.",
    reproduce="grep -n 'REFERENCES tenant' schema/sqlite.sql | grep att_attestation  # -- att_attestation.tenant_id REFERENCES tenant(id) ON DELETE CASCADE",
    severity="P1", assessment="not-a-defect",
    note="The true evidence ledger — `ev_run`/`ev_record`/`ev_sample`, the only tables under `EvidenceBase` (confirmed via ORM metadata) — has zero FKs to platform tables and zero `ON DELETE CASCADE`, exactly as required. `att_attestation` does carry `REFERENCES tenant (id) ON DELETE CASCADE`, but its own module docstring explicitly documents it as living under `Base`, not `EvidenceBase`, 'because it is a governance artefact about evidence' made by a person — a deliberate architectural decision, not an oversight. The catalogue's Steps ('scan the ev_* and att_* tables') conflates the governance table with the ledger proper.")

F["DB-028"] = dict(
    expected="34 tables.",
    reproduce="grep -c '^CREATE TABLE IF NOT EXISTS' schema/sqlite.sql  # 35",
    severity="P1", assessment="not-a-defect",
    note="The schema genuinely declares 35 tables, including `schema_state` (the bootstrap/drift-tracking table itself). Every column-level assertion in this case (e.g. `tenant.slug` parsed as `VARCHAR(128) NOT NULL`) is correct. This is a consistent off-by-one in the catalogue's own counting, repeated identically in DB-004, DB-008, DB-035 and DB-054 — most plausibly the author did not count `schema_state` as a 'declared' table. Not a product defect.")

F["DB-031"] = dict(
    expected="One statement, applied correctly — or a loud refusal.",
    reproduce="python3 - <<'PY'\nimport sys; sys.path.insert(0,'src')\nfrom pathlib import Path\nfrom prama.db.schema.loader import SchemaLoader\ntext = Path('schema/sqlite.sql').read_text().replace(\n    \"display_name   VARCHAR(255)  NOT NULL,\",\n    \"display_name   VARCHAR(255)  NOT NULL DEFAULT 'a;b',\", 1)\nPath('/tmp/sqlite_semicolon.sql').write_text(text)\nsf = SchemaLoader().load(Path('/tmp/sqlite_semicolon.sql'))\nstmt = next(s for s in sf.statements if 'CREATE TABLE IF NOT EXISTS tenant' in s)\nprint(repr(stmt[:250]))\nPY",
    severity="P1", assessment="defect",
    note="Confirms the loader's own documented failure mode. `SchemaLoader._split` splits on every `;` after stripping comments, with no string-literal awareness, so a `DEFAULT 'a;b'` breaks one `CREATE TABLE` into two truncated, unbalanced fragments — neither a working statement nor a refusal. The schema files do not currently contain such a value (which is why this has never fired in production), but the splitter provides no protection if one is ever added, exactly as the module's own docstring warns.")

F["DB-035"] = dict(
    expected="`tables_present=34`.",
    reproduce="see DB-028's reproduction — the same schema file, the same count",
    severity="P1", assessment="not-a-defect",
    note="Same finding as DB-028: `tables_present=35` is correct given the schema genuinely declares 35 tables. `created=True` and `statements_executed=99` (matching the parsed statement count) are both correct.")

F["DB-047"] = dict(
    expected="Drift reported, blocking.",
    reproduce="python3 - <<'PY'\nimport sys; sys.path.insert(0,'src')\n# bootstrap a db, then rebuild `role` with `name TEXT` instead of `VARCHAR(128)`, then:\nfrom prama.db.schema.verifier import SchemaVerifier\n# verify() against the retyped table -> no drift mentioning role.name\nPY  # (full script: /tmp/.../db_046_058.py in this run's scratch directory)",
    severity="P1", assessment="defect",
    note="Confirms the catalogue's flagged concern by direct execution: a live `role.name` column retyped from `VARCHAR(128)` to `TEXT` (via table rebuild) produces zero drift from `SchemaVerifier.verify()`. The verifier's own source only ever compares column *presence* and *nullability* (`live is None`, `live['nullable']`) — `ColumnSpec.type`, parsed by the loader, is never read by the verifier at all.")

F["DB-048"] = dict(
    expected="Verification reports it; otherwise the first write fails.",
    reproduce="Same mechanism as DB-047, with `role.name` rebuilt as `VARCHAR(8)` instead of `VARCHAR(128)`.",
    severity="P2", assessment="defect",
    note="Same root cause as DB-047 (the verifier never compares `ColumnSpec.type`, which carries the width for `VARCHAR(n)`). A shrunk column verifies clean; the first oversized write then fails at runtime with no prior warning.")

F["DB-050"] = dict(
    expected="Either the extra column is reported informationally, or the insert fails with nothing having warned.",
    reproduce="Add a `NOT NULL` column with no default to a live `tenant` table (table rebuild), then `SchemaVerifier.verify()`, then insert a tenant omitting that column.",
    severity="P2", assessment="defect",
    note="`SchemaVerifier.verify` iterates `for column in table.columns` — the *declared* columns only — so it can never discover a column present in the live table but absent from the schema file. Confirmed: the extra `NOT NULL` column is not mentioned in any drift, `report.ok` is `True`, and an insert omitting the column then fails at the database. This is the weaker half of the Expected ('the insert fails') without the honest half ('nothing having warned') — the verifier says the database is clean.")

F["DB-052"] = dict(
    expected="Blocking, or a documented decision that it is not.",
    reproduce="Bootstrap a database, `DROP INDEX uq_ev_record_sequence`, then `SchemaVerifier.verify()`.",
    severity="P1", assessment="defect",
    note="Confirmed: `DriftKind.MISSING_INDEX` is a single kind covering both `ix_` and `uq_` prefixed indexes, and only `MISSING_TABLE`, `MISSING_COLUMN`, `NULLABILITY` and `VERSION` are in `BLOCKING`. Dropping `uq_ev_record_sequence` — the exact constraint DB-015 proves prevents a forked evidence chain — verifies clean (`report.ok=True`), informational only. No code comment or docstring documents this as a deliberate choice.")

F["DB-055"] = dict(
    expected="A connection failure is reported, not turned into 'no recorded state'.",
    reproduce="python3 - <<'PY'\nimport sys; sys.path.insert(0,'src')\nfrom sqlalchemy import create_engine\nfrom prama.db.schema.verifier import SchemaVerifier\n# any working SchemaVerifier instance:\n# sv._recorded_state(create_engine('sqlite:////nonexistent/deep/path/x.db'))\nPY  # returns (None, None) instead of raising",
    severity="P2", assessment="defect",
    note="Confirms the flagged concern: `_recorded_state`'s `except SQLAlchemyError: return None, None` was written to handle 'table absent' (an unbootstrapped database) but also silently catches a genuine inability to connect at all, making an unreachable database indistinguishable from a merely-unbootstrapped one.")

F["DB-065"] = dict(
    expected="`DatabaseError` `DB.ENGINE_CREATE_FAILED` whose remedy is `pip install 'prama[postgres]'`.",
    reproduce="python3 - <<'PY'\nimport sys, builtins; sys.path.insert(0,'src')\norig=builtins.__import__\ndef fake(name,*a,**kw):\n    if name.startswith('asyncpg'): raise ModuleNotFoundError(\"No module named 'asyncpg'\")\n    return orig(name,*a,**kw)\nbuiltins.__import__=fake\nfrom prama.db import Database\nfrom prama.db.settings import DbSettings\nfrom prama.core.config import DEFAULTS\nfrom prama.core.config.configuration import Configuration\nfrom prama.core.config.sources import deep_merge\ns=DbSettings.from_config(Configuration(deep_merge(DEFAULTS, {'database':{'dialect':'postgres'}})))\nDatabase(s)._engines.async_engine()\nPY  # raises ModuleNotFoundError, uncaught",
    severity="P1", assessment="defect",
    note="`EngineFactory.async_engine()` wraps `create_async_engine(...)` in `except SQLAlchemyError`, but a missing driver raises `ModuleNotFoundError` (a plain `ImportError`, not a `SQLAlchemyError`), which propagates as a raw, untranslated Python exception rather than the documented `DatabaseError`. In this environment `asyncpg` happens to be installed, so this path is not normally hit — but the failure mode was reproduced directly by simulating the missing driver.")

F["DB-068"] = dict(
    expected="The tables are there.",
    reproduce="python3 - <<'PY'\nimport sys, asyncio; sys.path.insert(0,'src')\nfrom prama.db import Database\nfrom prama.db.settings import DbSettings\nfrom prama.core.config import DEFAULTS\nfrom prama.core.config.configuration import Configuration\nfrom prama.core.config.sources import deep_merge\nasync def main():\n    s=DbSettings.from_config(Configuration(deep_merge(DEFAULTS, {'database':{'sqlite':{'path':':memory:'}}})))\n    db=Database(s); db.initialise(applied_by='qa'); await db.start()\n    async with db.unit_of_work() as uow:\n        uow.tenants.create(slug='x', display_name='X')\nasyncio.run(main())\nPY  # sqlite3.OperationalError: no such table: tenant",
    severity="P1", assessment="defect",
    note="`database.sqlite.path: ':memory:'` is documented as 'honoured, for tests' (CFG-026), and the normal lifecycle is `initialise()` (sync engine) then `start()` (async engine). But `SqliteDialect.engine_kwargs` gives each engine its own `StaticPool`, and plain `:memory:` is not a shared-cache URI, so the sync engine's in-memory database and the async engine's in-memory database are two entirely separate SQLite databases — the schema created by `initialise()` is invisible to anything done through `start()`+`unit_of_work()`. `tests/conftest.py::sqlite_config`'s own docstring names exactly this failure mode as the reason the test suite uses a file instead, but no equivalent warning exists for a real deployment that sets `database.sqlite.path: ':memory:'`.")

F["DB-070"] = dict(
    expected="The configured values (application_name, statement_timeout, search_path); the timeout in milliseconds.",
    reproduce="python3 - <<'PY'\nimport sys; sys.path.insert(0,'src')\nfrom sqlalchemy.ext.asyncio import create_async_engine\nfrom prama.db.dialects import PostgresDialect\nfrom prama.db.settings import DbSettings, PostgresSettings\ns=DbSettings(dialect='postgres', postgres=PostgresSettings())\nd=PostgresDialect(s)\ncreate_async_engine(d.async_url(), **d.engine_kwargs(is_async=True))\nPY  # sqlalchemy.exc.ArgumentError: Pool class QueuePool cannot be used with asyncio engine",
    severity="P1", assessment="defect",
    note="ROOT CAUSE shared with DB-072, DB-148 and DB-279. `PostgresDialect.engine_kwargs` sets `poolclass=QueuePool` unconditionally at the top of the method, and the `is_async` branch never overrides it to an async-compatible pool class (SQLAlchemy 2.x requires `AsyncAdaptedQueuePool` for an async engine). The kwarg *values* (application_name, statement_timeout, search_path) are all correct when inspected directly, but `create_async_engine(...)` itself raises immediately — the async PostgreSQL engine, the path the module's own docstring says handles 'everything else', cannot be constructed at all on this SQLAlchemy version (2.0.52). No test in `tests/` exercises it: `tests/conftest.py::postgres_config` is defined but never used by any test in the repository.")

F["DB-072"] = dict(
    expected="Either refused, or the configuration is refused at start-up with an explanation.",
    reproduce="Same as DB-070, with `sslmode='require'` set — the async engine still fails to construct before `sslmode` is ever consulted.",
    severity="P1", assessment="defect",
    note="Two independent findings. (1) `engine_kwargs(is_async=True)` never places `sslmode` anywhere in the async connect args (confirmed: absent from the whole kwargs dict), matching the code comment 'the driver negotiates TLS itself' — but that is not the same as honouring `require`, and nothing refuses the configuration at start-up either. (2) Separately, the async engine cannot be constructed at all (the DB-070 QueuePool defect), which means today `sslmode=require` against PostgreSQL is neither honoured nor cleanly refused — it simply cannot connect, for an unrelated reason that masks the real gap.")

F["DB-074"] = dict(
    expected="Not `0` — a zero statement timeout means unlimited in PostgreSQL.",
    reproduce="python -c \"import sys; sys.path.insert(0,'src'); from prama.db.dialects import PostgresDialect\nfrom prama.db.settings import DbSettings, PostgresSettings\ns=DbSettings(dialect='postgres', postgres=PostgresSettings(statement_timeout_seconds=0.0005))\nprint(PostgresDialect(s).engine_kwargs(is_async=False)['connect_args']['options'])\"",
    severity="P2", assessment="defect",
    note="Confirms the flagged concern exactly: `int(0.0005 * 1000)` truncates to `0`, and `-c statement_timeout=0` in the connect options means *unlimited* in PostgreSQL — the precise opposite of what `statement_timeout: 500us` asked for.")

F["DB-076"] = dict(
    expected="Either a valid `DO NOTHING`, or a refusal — never `DO UPDATE SET` with an empty assignment list.",
    reproduce="python -c \"import sys, sqlite3; sys.path.insert(0,'src'); from prama.db.dialects import SqliteDialect\nfrom prama.db.settings import DbSettings\nstmt = SqliteDialect(DbSettings()).upsert('t', ['a','b'], ['a','b'])\nprint(repr(stmt))\nc = sqlite3.connect(':memory:'); c.execute('CREATE TABLE t (a TEXT, b TEXT, PRIMARY KEY(a,b))')\nc.execute(stmt, {'a':'1','b':'2'})\"",
    severity="P2", assessment="defect",
    note="When every column is part of the conflict key, the list comprehension building `assignments` (`c for c in columns if c not in conflict`) is empty, producing `... ON CONFLICT (a, b) DO UPDATE SET ` with nothing after `SET` — confirmed to raise `sqlite3.OperationalError: incomplete input` when executed. All three real call sites (`bootstrap.py`, `RoleDao.grant`, `SettingDao.put`) happen to always include a non-key column, so this has never fired in production, but the function itself provides no protection.")

F["DB-086"] = dict(
    expected="A named refusal rather than a raw SQLAlchemy 'session is closed'.",
    reproduce="python3 - <<'PY'\nimport sys, asyncio; sys.path.insert(0,'src')\nfrom prama.db import Database\nfrom prama.db.settings import DbSettings\nfrom prama.core.config import DEFAULTS\nfrom prama.core.config.configuration import Configuration\nfrom prama.core.config.sources import deep_merge\nasync def main():\n    s=DbSettings.from_config(Configuration(deep_merge(DEFAULTS, {'database':{'sqlite':{'path':'/tmp/x086.db'}}})))\n    db=Database(s); db.initialise(applied_by='qa'); await db.start()\n    uow=db.unit_of_work(); await uow.close()\n    await uow.tenants.by_slug('x')\nasyncio.run(main())\nPY",
    severity="P2", assessment="defect",
    note="`UnitOfWork.close()` closes the underlying `AsyncSession` but nothing checks `self._closed` before a DAO call proceeds to use `self._session`. The raw SQLAlchemy error (`StatementError`/`ResourceClosedError`, depending on driver) reaches the caller directly — the layering claim that 'nothing above `prama.db` ever sees SQLAlchemy, including in its exceptions' does not hold here.")

F["DB-089"] = dict(
    expected="Each of the 23 DAO properties returns an instance of the type in its annotation.",
    reproduce="grep -c '    @property' src/prama/db/session.py; grep -c 'def .*Dao:' src/prama/db/session.py  # 22 DAO properties, not 23",
    severity="P2", assessment="not-a-defect",
    note="Every one of the 22 DAO properties `UnitOfWork` actually declares returns an instance exactly matching its own property return annotation — verified via `inspect.signature`, not the weaker `typing.get_type_hints()` approach (which does not see property return types at all and would report nothing to check). The catalogue's count of 23 is off by one; direct enumeration of every `@property` in `db/session.py` finds 22.")

F["DB-098"] = dict(
    expected="A clear failure naming the column, not a `ValueError` from `fromisoformat` with no context.",
    reproduce="python3 - <<'PY'\nimport sys; sys.path.insert(0,'src')\nfrom sqlalchemy import create_engine, MetaData, Table, Column, Integer, text\nfrom prama.db.types import UtcDateTime\ne=create_engine('sqlite:///:memory:'); m=MetaData()\nt=Table('t',m,Column('id',Integer,primary_key=True),Column('ts',UtcDateTime)); m.create_all(e)\nwith e.begin() as c:\n    c.execute(text(\"INSERT INTO t (id, ts) VALUES (1, 'not-a-date')\"))\n    c.execute(t.select())\nPY",
    severity="P2", assessment="defect",
    note="`UtcDateTime.process_result_value` calls `datetime.fromisoformat(text)` with no try/except. A malformed stored value raises the stdlib's raw `ValueError: Invalid isoformat string: 'not-a-date'` — no table or column name anywhere in the message.")

F["DB-125"] = dict(
    expected="A named refusal, not an engine error.",
    reproduce="python3 - <<'PY'\nimport sys, asyncio; sys.path.insert(0,'src')\n# build a unit of work against a bootstrapped db with rows, then:\n# await uow.principals.list_for_tenant(tenant_id, limit=-1)\nPY  # returns every row in the tenant, unfiltered -- neither a refusal nor an engine error",
    severity="P2", assessment="defect",
    note="`TenantScopedDao.list_for_tenant` passes `limit`/`offset` straight to SQLAlchemy's `.limit()`/`.offset()` with no validation. On SQLite, `LIMIT -1` means 'no limit', so a negative value silently returns the entire unfiltered result set — not the engine error the catalogue anticipated, and not the named refusal it expected either; the worst of both, since it looks like a normal (if oversized) response.")

F["DB-142"] = dict(
    expected="Either a tenant argument is required, or the pair is proven globally unique by a constraint.",
    reproduce="Two principals in different tenants sharing `(external_idp, external_id)` (no DB constraint prevents this — grep schema/sqlite.sql for external_id shows no UNIQUE), then `await uow.principals.by_external_id('okta', 'collide-123')`.",
    severity="P1", assessment="defect",
    note="Worse than the catalogue anticipated. `by_external_id` takes no tenant parameter at all, and the schema has no uniqueness constraint on `(external_idp, external_id)` either. When two tenants collide on the pair, the method does not merely return the wrong tenant's principal — its `_one_or_none()` call raises a raw, untranslated `sqlalchemy.exc.MultipleResultsFound`, crashing the SSO sign-in path outright.")

F["DB-148"] = dict(
    expected="Identical outcome on both engines.",
    reproduce="See DB-070's reproduction — the PostgreSQL async engine cannot be constructed at all.",
    severity="P1", assessment="defect",
    note="SQLite side fully proven (DB-146/147: grant then re-grant is idempotent, concurrent grants produce one row, no `ConflictError` escapes). PostgreSQL side is blocked by the same root-cause QueuePool defect as DB-070/072/279 — `RoleDao.grant` needs an `AsyncSession` bound to a working async engine, and that engine cannot be built for `dialect: postgres` in this environment.")

F["DB-155"] = dict(
    expected="The listing's meaning of 'active' is documented, and authentication refuses the expired key.",
    reproduce="python -c \"import sys, inspect; sys.path.insert(0,'src'); from prama.db.dao.platform import ApiKeyDao; print(inspect.getdoc(ApiKeyDao.active_for_principal))\"  # None",
    severity="P2", assessment="defect",
    note="Split result. The security-relevant half is correct: `api/deps.py`'s authentication path separately checks `record.expires_at <= utc_now()` and refuses an expired key even though `active_for_principal` itself only filters on `revoked_at`. But `active_for_principal` carries no docstring at all — the catalogue's documentation requirement is not met, even though the dangerous behaviour it worried about (an expired key treated as usable) does not actually happen at the point that matters.")

F["DB-179"] = dict(
    expected="One succeeds; the other gets a `ConflictError`.",
    reproduce="Two `UnitOfWork`s racing `domains.amend(same_entity_id, ...)` via `asyncio.gather` (needs a real interleaving; sequential awaits will not reproduce it — see the note).",
    severity="P1", assessment="defect",
    note="Data integrity holds: exactly one current version exists after the race, confirmed by a raw-SQL count against the database independent of either coroutine's own return value — the partial unique index does its job. But the losing side's error is a raw, untranslated `sqlite3.IntegrityError`, not the documented `ConflictError`. `VersionedDao.amend`/`correct` call `self._session.flush()` directly rather than through `UnitOfWork._guarded()`, so the error-taxonomy translation is bypassed at exactly the concurrency-conflict path this case exists to test.")

F["DB-201"] = dict(
    expected="Either a tenant argument is required, or the method is proven unreachable from any caller-supplied input.",
    reproduce="python -c \"import sys, inspect; sys.path.insert(0,'src'); from prama.db.dao.semantic import AttributeDao; print(list(inspect.signature(AttributeDao.mapped_to_property).parameters))\"  # ['self', 'property_id'] -- no tenant_id",
    severity="P1", assessment="defect",
    note="Confirmed by execution: with two tenants' attributes both pointing at the same `concept_property_id`, calling `mapped_to_property(property_id)` with no tenant context returns the other tenant's attribute. This is the fifth by-parent read on `AttributeDao`/`ConceptPropertyDao`/`BindingDao` and the only one of the five that was not fixed after finding F-02 — its docstring is the generic one, without the tenant-required rationale the other four carry verbatim.")

F["DB-208"] = dict(
    expected="Found, or a documented ceiling.",
    reproduce="Monkeypatch `VersionedDao.list_current` to cap at N (simulating the real hardcoded 10,000), create N+2 journeys where the matching one is beyond the cap, call `journeys.containing(tenant_id, dataset_id)`.",
    severity="P2", assessment="defect",
    note="Executed at reduced scale rather than at the real 10,000-row threshold (impractical to build 10,001 rows through the ORM in this pass), but the mechanism is exact: `containing()` calls `self.list_current(tenant_id, limit=10_000)` and filters in Python, with no pagination beyond that call and no ceiling surfaced anywhere the caller can see. At the reduced cap, the match beyond the limit is silently missed, exactly as `list_current(limit=10_000)`'s hardcoding in the source predicts.")

F["DB-209"] = dict(
    expected="A complete answer or a stated limit.",
    reproduce="Same mechanism as DB-208, against `ConnectionDao.unhealthy`.",
    severity="P3", assessment="defect",
    note="Same root cause and same executed-at-reduced-scale confirmation as DB-208: `unhealthy()` also calls `list_current(tenant_id, limit=10_000)` with no ceiling surfaced to the operator.")

F["DB-239"] = dict(
    expected="The hashes are still protected.",
    reproduce="python -O -c \"assert False\"  # exits 0 -- proves this interpreter strips asserts under -O",
    severity="P1", assessment="defect",
    note="Confirms the flagged concern. `EvidenceDao.erase`'s only protection for `content_hash`/`record_hash` — the two invariants that keep an erased record's place in the hash chain verifiable — is `assert row.content_hash == erased.content_hash` and `assert row.record_hash == erased.record_hash`, with no accompanying runtime check. Confirmed directly that this interpreter strips `assert` under `python -O` / `PYTHONOPTIMIZE=1`, which a container base image or deployment flag could trigger, silently removing the guard.")

F["DB-244"] = dict(
    expected="Either a tenant argument is required, or control ids are proven globally unique and unguessable.",
    reproduce="python -c \"import sys, inspect; sys.path.insert(0,'src'); from prama.db.dao.evidence import EvidenceDao; print(list(inspect.signature(EvidenceDao.for_control).parameters))\"  # ['self', 'control_id', 'limit'] -- no tenant_id",
    severity="P1", assessment="defect",
    note="Confirmed by execution: with an evidence record in tenant A carrying a confidential `detail`, calling `for_control(control_id)` from a context holding only that control id (no tenant) returns tenant A's record in full, including `detail`. Same shape as F-02, on the same class.")

F["DB-245"] = dict(
    expected="As DB-244.",
    reproduce="Same mechanism, against `for_run(run_id)`.",
    severity="P1", assessment="defect",
    note="Same finding as DB-244, confirmed on `for_run`: no tenant parameter, and a caller holding only a run id sees that run's full evidence records.")

F["DB-279"] = dict(
    expected="Identical behaviour on both engines.",
    reproduce="See DB-070's reproduction.",
    severity="P1", assessment="defect",
    note="SQLite side fully exercised and correct (DB-278, DB-280–288 all pass: exactly-one-grant under real `asyncio.gather` contention, strictly increasing fencing tokens, lost-race/renewal/release/inspect/purge semantics all confirmed). PostgreSQL side cannot be exercised at all: `DatabaseLeaseProvider` requires a working `AsyncEngine`, and constructing one for `dialect: postgres` fails immediately with the same QueuePool defect as DB-070/072/148 — confirmed directly against the live PostgreSQL server used for this pass. The database-backed lease provider, the mechanism CLAUDE.md's structured-concurrency rules rely on for fleet-wide coordination, cannot function on PostgreSQL in this build at all.")

# ---------------------------------------------------------------------------
# Build the document
# ---------------------------------------------------------------------------
lines = []
lines.append("<img src=\"../../../assets/prama-lockup.svg\" alt=\"Prama — Declare it. Prove it. Trust it.\" width=\"330\"/>")
lines.append("")
lines.append("*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*")
lines.append("")
lines.append("---")
lines.append("")
lines.append("# Platform & core — execution log")
lines.append("")
lines.append("Executed against `docs/qa/catalogue/platform.md`, CFG-001 through CFG-320 and")
lines.append("DB-001 through DB-295 (615 cases): configuration, core services, the schema files,")
lines.append("loader/bootstrap/verifier, engines, session and unit of work, types and security,")
lines.append("every DAO, leases and metrics. MON-, INC-, RPT-, BCH- and OPS- are out of scope for")
lines.append("this log (covered elsewhere).")
lines.append("")
pass_rate = counts["PASS"] / total * 100
lines.append(f"**Total: {total} · Passed: {counts['PASS']} · Failed: {counts['FAIL']} · Blocked: {counts['BLOCKED']} · Pass rate: {pass_rate:.1f}%**")
lines.append("")
lines.append("PostgreSQL cases ran against a live `postgres:16-alpine` server "
             "(`postgresql://prama:prama@127.0.0.1:55433/prama`), reachable via Docker in this "
             "environment; none are BLOCKED on that account. A handful of PostgreSQL-async cases "
             "(DB-070, DB-072, DB-148, DB-279) are executed and FAIL rather than BLOCKED: they were "
             "run, and what running them found is that the async PostgreSQL engine cannot be built "
             "at all in this environment (see DB-070's writeup) — a real, reproduced defect, not an "
             "absent test.")
lines.append("")
lines.append("## Failures ranked by severity")
lines.append("")
sev_order = {"P1": 0, "P2": 1, "P3": 2}
fail_ids_sorted = sorted(
    [id_ for id_, r, _ in rows if r == "FAIL"],
    key=lambda i: (sev_order.get(F[i]["severity"], 9), F[i]["assessment"] != "defect", sortkey((i, "", "")))
)
for id_ in fail_ids_sorted:
    d = F[id_]
    tag = {"defect": "DEFECT", "not-a-defect": "not-a-defect", "working-as-designed": "working-as-designed"}[d["assessment"]]
    lines.append(f"- **{id_}** ({d['severity']}, {tag}) — {d['expected'][:110]}")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Per-case results")
lines.append("")
lines.append("| Id | Result | Observed |")
lines.append("|---|---|---|")
for id_, result, obs in rows:
    obs_md = obs.replace("|", "\\|").replace("\n", " ")
    if len(obs_md) > 400:
        obs_md = obs_md[:400] + "…"
    lines.append(f"| `{id_}` | {result} | {obs_md} |")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Failures")
lines.append("")
for id_ in sorted([i for i, r, _ in rows if r == "FAIL"], key=lambda i: sortkey((i, "", ""))):
    d = F[id_]
    # find the title from the catalogue for a heading
    lines.append(f"### {id_}")
    lines.append(f"- **Expected:** {d['expected']}")
    obs_row = next(o for i, r, o in rows if i == id_)
    lines.append(f"- **Observed:** {obs_row}")
    lines.append(f"- **Reproduce:**")
    lines.append("  ```")
    for rl in d["reproduce"].splitlines():
        lines.append(f"  {rl}")
    lines.append("  ```")
    lines.append(f"- **Severity:** {d['severity']}")
    lines.append(f"- **Assessment:** {d['assessment']}")
    lines.append(f"- **Note:** {d['note']}")
    lines.append("")

lines.append("---")
lines.append("")
lines.append("Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.")
lines.append("")

open("/home/ashutosh/PycharmProjects/prama/docs/qa/logs/platform-core.md", "w", encoding="utf-8").write("\n".join(lines))
print("WROTE", len(lines), "lines")
print("counts", counts, "total", total)
