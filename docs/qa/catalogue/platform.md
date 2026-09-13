<img src="../../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# The platform underneath, and running it in anger

**Packages:** `core`, `db`, `monitor`, `incident`, `alert`, `report`,
`telemetry`, `bench`, plus `schema/`, `deploy/`, `scripts/` and
`.github/workflows/`.

**Source under test:** ~19,200 lines of Python across 87 modules, two
authoritative schema files of 1,047 lines each, one Helm chart, one Dockerfile,
one CI workflow and five scripts.

**What this is not.** Round 1 tested installation and operation as a *surface*
([`cases-operate.md`](../cases-operate.md), [`log-operate.md`](../log-operate.md)):
somebody following the documentation, standing up a database, starting a server,
sealing a bundle. This asks the other question — *is there any part of this
nobody has looked at* — and the answer, for most of what is below, was no. The
DAOs, the monitors, the reports and the bench were barely touched. Where a case
here does restate a round-1 concern it is because the *counterfactual* was never
written: a guard nobody has seen fail is a guard nobody knows works.

**Nothing here was executed.** Every case was written from the code and its
docstrings. Several name a defect the code appears to contain; each of those
says so in its **Why**, and the execution pass is what settles it.

---

## Scope

| Area | Ids | Cases | P1 / P2 / P3 |
|---|---|---:|---|
| Configuration — the keys and their defaults | `CFG-001`–`CFG-051` | 51 | 14 / 28 / 9 |
| Configuration — sources, precedence and parsing | `CFG-052`–`CFG-095` | 44 | 13 / 23 / 8 |
| Configuration — coercion and placeholders | `CFG-096`–`CFG-140` | 45 | 13 / 21 / 11 |
| The error taxonomy | `CFG-141`–`CFG-153` | 13 | 6 / 6 / 1 |
| Clock and time | `CFG-154`–`CFG-164` | 11 | 5 / 4 / 2 |
| Identifiers | `CFG-165`–`CFG-176` | 12 | 3 / 6 / 3 |
| Structured concurrency | `CFG-177`–`CFG-245` | 69 | 31 / 28 / 10 |
| The plugin registry | `CFG-246`–`CFG-270` | 25 | 6 / 13 / 6 |
| pjson | `CFG-271`–`CFG-286` | 16 | 7 / 6 / 3 |
| Business calendars | `CFG-287`–`CFG-307` | 21 | 7 / 12 / 2 |
| Provenance | `CFG-308`–`CFG-320` | 13 | 5 / 7 / 1 |
| The schema files | `DB-001`–`DB-027` | 27 | 19 / 8 / 0 |
| The schema loader, bootstrapper and verifier | `DB-028`–`DB-061` | 34 | 22 / 10 / 2 |
| Engines, sessions and the unit of work | `DB-062`–`DB-092` | 31 | 17 / 13 / 1 |
| Portable types and credential handling | `DB-093`–`DB-117` | 25 | 13 / 12 / 0 |
| DAOs — the base, tenancy and identity | `DB-118`–`DB-165` | 48 | 28 / 15 / 5 |
| DAOs — the bitemporal protocol | `DB-166`–`DB-194` | 29 | 21 / 8 / 0 |
| DAOs — the semantic layer, controls, evidence and the rest | `DB-195`–`DB-277` | 83 | 60 / 22 / 1 |
| Leases in the database, and the metric store | `DB-278`–`DB-295` | 18 | 12 / 4 / 2 |
| Monitors — drift and accepting a new normal | `MON-001`–`MON-030` | 30 | 16 / 13 / 1 |
| Monitors — detectors | `MON-031`–`MON-055` | 25 | 11 / 12 / 2 |
| Monitors — seasonality | `MON-056`–`MON-074` | 19 | 11 / 7 / 1 |
| Monitors — the monitor, the fleet, cold start and the tournament | `MON-075`–`MON-140` | 66 | 37 / 25 / 4 |
| Incidents | `INC-001`–`INC-041` | 41 | 24 / 16 / 1 |
| Alerts and routing | `INC-042`–`INC-073` | 32 | 23 / 8 / 1 |
| Reports — attestations, packs and charts | `RPT-001`–`RPT-095` | 95 | 64 / 26 / 5 |
| The benchmark corpus and its baselines | `BCH-001`–`BCH-061` | 61 | 39 / 21 / 1 |
| Deployment, the gate, and telemetry | `OPS-001`–`OPS-074` | 74 | 52 / 20 / 2 |
| **Total** | | **1,058** | **579 / 394 / 85** |

By type: 372 boundary · 221 functional · 175 contract · 109 security · 105
negative · 33 documentation · 23 concurrency · 13 regression · 7 performance.

---

## What was hunted, and where

The docstrings in these packages make a great many absolute claims. Every
occurrence of *never*, *always*, *cannot*, *loudly*, *exactly* and *only* was
treated as a test case:

- **"No exception is swallowed"** (CLAUDE.md, `db/dao/base.py`) — three bare
  `except` clauses that return a benign value are enumerated: `CFG-262`,
  `DB-055`, and the `_entry_points_for` catch-all.
- **"Reported, never repaired"** (`db/schema/verifier.py`) — the verifier
  compares presence and nullability and never type or width: `DB-047`, `DB-048`,
  `DB-050`, `DB-052`.
- **"Tenant scoping is structural"** (`db/dao/base.py`) — four reads take a
  parent id and no tenant, in the exact shape of QA finding F-02: `DB-201`,
  `DB-244`, `DB-245`, `DB-142`.
- **"This mapping is the authority and the file is documentation"**
  (`core/config/defaults.py`) — the two disagree about `plugins.disabled` and
  about the PostgreSQL placeholders: `CFG-035`, `CFG-036`, and a comment that
  contradicts the value beside it, `CFG-014`.
- **"Every remedy names something real"** — `CFG-143` through `CFG-145` and
  `OPS-023`, `OPS-052`.
- **Claims about the *rendered* artefact rather than the intent** — `RPT-025`
  asserts an evidence root that the code assigns a tuple to, and `RPT-017` asks
  the printed pack, not the source, to say what the seal proves.

The five CLAUDE.md hard rules are each represented, and for the three that
`tests/architecture/` already enforces the case exists to write the
counterfactual: `OPS-070` (layering), `OPS-071` (no model verdict), `OPS-072`
(no second schema authority), `OPS-073` (no tracked secret), `OPS-074`
(authorship), `OPS-030` (the file-length ceiling), `DB-001` (the two schema
files).

---
## Configuration — the keys and their defaults

Every key in `core/config/defaults.py`, and the claim in its docstring that the
mapping "is the authority and the file is documentation".

### CFG-001 · The built-in defaults are a complete, bootable configuration
- **Area:** `core/config/__init__.py::load_configuration`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a directory with no `config/` at all
- **Steps:** `load_configuration()` with `use_environment=False`
- **Expected:** a `Configuration` whose every `DEFAULTS` key resolves, no exception
- **Why:** the docstring says a missing configuration file is not an error because
  "the built-in defaults are a complete, safe configuration". A fresh clone and a
  CI job both depend on it.

### CFG-002 · A configuration file named explicitly and absent is an error
- **Area:** `core/config/__init__.py::load_configuration`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `/tmp/no-such.yaml` does not exist
- **Steps:** `load_configuration("/tmp/no-such.yaml")`
- **Expected:** `ConfigError` code `CONFIG.FILE_MISSING`, remedy naming the path
- **Why:** the same docstring draws the line: absent-by-default is normal,
  absent-when-named "is always a mistake".

### CFG-003 · `PRAMA_CONFIG` makes the file required
- **Area:** `core/config/__init__.py::load_configuration`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `PRAMA_CONFIG=/tmp/no-such.yaml` in the environment passed in
- **Steps:** `load_configuration(environ={"PRAMA_CONFIG": "/tmp/no-such.yaml"})`
- **Expected:** `CONFIG.FILE_MISSING`, not a silent fall back to defaults
- **Why:** `explicit` is set by the env var as well as the argument; an operator
  who pointed the process at a file is entitled to be told it is not there.

### CFG-004 · `app.name` defaults to `Prama`
- **Area:** `core/config/defaults.py::DEFAULTS`
- **Type:** functional
- **Priority:** P3
- **Precondition:** none
- **Steps:** `config.get_str("app.name")`
- **Expected:** `"Prama"`
- **Why:** the product name appears on every printed artefact; a default it does
  not have is a pack with a blank masthead.

### CFG-005 · `app.environment` defaults to `development`
- **Area:** `core/config/defaults.py::DEFAULTS`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `config.get_str("app.environment")`
- **Expected:** `"development"`
- **Why:** shipping `production` as the default would make an unconfigured
  install claim a posture it has not been given.

### CFG-006 · `app.instance_id` resolves `${HOSTNAME:local}` against the environment
- **Area:** `core/config/resolver.py::PlaceholderResolver`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `HOSTNAME=box-7` in the passed environment
- **Steps:** read `app.instance_id`
- **Expected:** `"box-7"`; with `HOSTNAME` unset, `"local"`
- **Why:** the only shipped default that is a placeholder — it proves the
  resolver runs on the defaults source and not only on files.

### CFG-007 · `logging.level` accepts every documented value
- **Area:** `core/log.py::LoggingConfigurator`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** apply the configurator at `DEBUG`, `INFO`, `WARNING`, `ERROR`
- **Expected:** the root logger's level matches each in turn
- **Why:** `config/application.yaml` documents exactly those four; one that is
  accepted in the file and rejected by the configurator is doc rot with an
  outage attached.

### CFG-008 · An unknown `logging.level` is refused, not silently defaulted
- **Area:** `core/log.py::LoggingConfigurator.apply`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `logging.level: VERBOSE`
- **Steps:** apply the configurator
- **Expected:** a named refusal with a remedy listing the accepted levels
- **Why:** `root.setLevel("VERBOSE")` raises a bare `ValueError` from the standard
  library; the taxonomy promises a remedy on every deliberate failure.

### CFG-009 · `logging.format: json` produces one JSON object per line
- **Area:** `core/log.py::JsonFormatter`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a stream captured
- **Steps:** configure `fmt="json"`, log one record with `prama_fields`
- **Expected:** a single parseable JSON object with `ts`, `level`, `logger`,
  `message`, `fields`; no trailing text
- **Why:** "the format a log shipper wants" — a shipper rejects the whole line
  if anything precedes the brace.

### CFG-010 · `logging.format: text` is the default and is human-readable
- **Area:** `core/log.py::TextFormatter`
- **Type:** functional
- **Priority:** P3
- **Precondition:** none
- **Steps:** log a record with a correlation id set
- **Expected:** the `cid=` suffix appears; no JSON braces
- **Why:** the default must be the one a person reads on a terminal.

### CFG-011 · `security.session_secret` ships empty
- **Area:** `core/config/defaults.py::DEFAULTS`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** `DEFAULTS["security"]["session_secret"]`
- **Expected:** `""`
- **Why:** CLAUDE.md rule 5 — "a fresh clone is meant to refuse to boot". A
  non-empty default is a public signing key.

### CFG-012 · `require_secret` refuses an empty secret with an actionable remedy
- **Area:** `core/config/configuration.py::Configuration.require_secret`
- **Type:** security
- **Priority:** P1
- **Precondition:** defaults only
- **Steps:** `config.require_secret("security.session_secret")`
- **Expected:** `SecretMissingError` (`CONFIG.SECRET_MISSING`) whose remedy names
  `config/application.local.yaml` and `PRAMA_SECURITY__SESSION_SECRET`
- **Why:** the remedy must be followable literally — round 1 found three shipped
  remedies naming commands that did not exist.

### CFG-013 · A whitespace-only secret is treated as empty
- **Area:** `core/config/configuration.py::Configuration.require_secret`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `security.session_secret: "   "`
- **Steps:** `require_secret`
- **Expected:** refused
- **Why:** `str(value).strip()` is the guard; a space is the easiest way to
  defeat a naive emptiness check and it must not work.

### CFG-014 · The comment on `security.cookies_https_only` matches its value
- **Area:** `core/config/defaults.py::DEFAULTS["security"]`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** read the shipped comment ("Off in development only because a
  developer on http://localhost would otherwise never receive the cookie") and
  the value beside it
- **Expected:** the comment describes the value; the value is `True`, so the
  comment describing it as off is wrong and must be corrected
- **Why:** a comment that contradicts the value it annotates teaches the next
  reader something false about the security posture of a default.

### CFG-015 · `tenancy.default_tenant` defaults to empty and means multi-tenant
- **Area:** `core/config/defaults.py::DEFAULTS["tenancy"]`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** read `tenancy.default_tenant`
- **Expected:** `""`
- **Why:** the comment states that empty means an unauthenticated request is
  refused rather than guessed at; a default tenant would silently expose one.

### CFG-016 · `web.enabled` defaults to true
- **Area:** `core/config/defaults.py::DEFAULTS["web"]`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `config.get_bool("web.enabled")`
- **Expected:** `True`
- **Why:** `run_prama_web.py` branches on it to decide whether to print the
  console URL; a false default would make a first run look broken.

### CFG-017 · `web.preview.source` empty means check-and-compile but not run
- **Area:** `core/config/defaults.py::DEFAULTS["web"]["preview"]`
- **Type:** functional
- **Priority:** P2
- **Precondition:** defaults only
- **Steps:** read `web.preview.source`
- **Expected:** `""`, and the studio says so rather than showing an empty result
- **Why:** the comment promises it "says so rather than showing an empty result
  that reads as clean" — an empty clean result is the product's worst lie.

### CFG-018 · `web.preview.dialect` accepts only `duckdb` and `sqlite`
- **Area:** `core/config/defaults.py` and `config/application.yaml`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `web.preview.dialect: postgres`
- **Steps:** start the preview path
- **Expected:** a refusal naming the two supported values
- **Why:** the tracked file documents two; anything else is a configuration the
  code cannot honour and must not accept silently.

### CFG-019 · `web.preview.max_rows` at its default is 1,000,000
- **Area:** `core/config/defaults.py`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** `config.get_int("web.preview.max_rows")`
- **Expected:** `1000000`
- **Why:** the underscore literal `1_000_000` in Python and the plain `1000000`
  in the YAML must agree; a mismatch is exactly the drift the docstring warns of.

### CFG-020 · `web.preview.max_rows: 0` is refused
- **Area:** `core/config/coercion.py::Coercer.to_int` and its consumer
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `--set web.preview.max_rows=0`
- **Steps:** run a preview
- **Expected:** a refusal, not a preview that silently returns nothing
- **Why:** a zero row cap produces an empty result that reads as clean, which
  the neighbouring comment says must never happen.

### CFG-021 · `web.preview.backtest_days` defaults to 30 and rejects a negative
- **Area:** `core/config/defaults.py`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `--set web.preview.backtest_days=-1`
- **Steps:** read and use it
- **Expected:** default `30`; `-1` refused with a remedy
- **Why:** a negative backtest window is a query against the future presented as
  history.

### CFG-022 · `database.dialect` defaults to sqlite
- **Area:** `db/settings.py::DbSettings.from_config`
- **Type:** functional
- **Priority:** P1
- **Precondition:** defaults only
- **Steps:** `DbSettings.from_config(config).dialect`
- **Expected:** `"sqlite"`
- **Why:** the "no network, no external calls" property of the defaults depends
  on it.

### CFG-023 · `database.dialect` is lowercased before validation
- **Area:** `db/settings.py::DbSettings.from_config`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `--set database.dialect=SQLite`
- **Steps:** build settings
- **Expected:** accepted as `sqlite`
- **Why:** `.lower()` is applied; a case-sensitive refusal on a configuration
  value a person typed is friction with no safety benefit.

### CFG-024 · An unsupported dialect is refused by name
- **Area:** `db/settings.py::DbSettings.validate`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `--set database.dialect=mysql`
- **Steps:** build settings
- **Expected:** `ConfigError` `CONFIG.DIALECT_UNSUPPORTED`, remedy listing
  `sqlite, postgres`
- **Why:** the alternative is a `KeyError` from `_DIALECTS` at engine
  construction, which names nothing.

### CFG-025 · `database.sqlite.path` defaults to `data/prama.db`
- **Area:** `db/settings.py::SqliteSettings`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** read the setting
- **Expected:** `data/prama.db`, relative to the working directory
- **Why:** round 1 covered where the file lands; this case fixes the value the
  rest of the settings tests are written against.

### CFG-026 · `:memory:` and `""` are both recognised as in-memory
- **Area:** `db/settings.py::SqliteSettings.is_memory`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `database.sqlite.path` set to each of `:memory:`, `""`,
  `file::memory:?cache=shared`
- **Steps:** read `is_memory` and `resolved_path()`
- **Expected:** `True` and `None` for all three
- **Why:** an unrecognised in-memory form makes `prepare_filesystem` create a
  directory called `:memory:` on disk.

### CFG-027 · `database.sqlite.journal_mode` reaches the connection as a PRAGMA
- **Area:** `db/dialects.py::SqliteDialect.on_connect`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a file-backed SQLite database
- **Steps:** set `journal_mode: DELETE`, connect, `PRAGMA journal_mode`
- **Expected:** `delete`
- **Why:** a setting accepted and not applied is worse than one refused.

### CFG-028 · `journal_mode` is not applied to an in-memory database
- **Area:** `db/dialects.py::SqliteDialect.on_connect`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `path: ":memory:"`
- **Steps:** connect
- **Expected:** no `PRAGMA journal_mode` issued; no error
- **Why:** the code guards on `is_memory` because WAL is meaningless there.

### CFG-029 · `journal_mode` is interpolated into SQL without quoting
- **Area:** `db/dialects.py::SqliteDialect.on_connect`
- **Type:** security
- **Priority:** P2
- **Precondition:** `database.sqlite.journal_mode: "WAL; ATTACH DATABASE '/tmp/x' AS y"`
- **Steps:** connect
- **Expected:** refused, or the value validated against the known journal modes —
  never executed as typed
- **Why:** the pragma is built with an f-string. The value comes from
  configuration rather than from a user, which lowers the severity and does not
  make an unvalidated interpolation into DDL acceptable.

### CFG-030 · `database.sqlite.synchronous` is applied on every connection
- **Area:** `db/dialects.py::SqliteDialect.on_connect`
- **Type:** functional
- **Priority:** P3
- **Precondition:** `synchronous: FULL`
- **Steps:** connect twice, read `PRAGMA synchronous` on each
- **Expected:** `2` both times
- **Why:** the docstring on `EngineFactory` says the connect hook is shared so a
  pragma "cannot apply on one path and not the other".

### CFG-031 · `database.sqlite.busy_timeout` accepts a duration and reaches SQLite in ms
- **Area:** `db/settings.py::from_config` and `SqliteDialect.on_connect`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `busy_timeout: 2500ms`
- **Steps:** connect, `PRAGMA busy_timeout`
- **Expected:** `2500`
- **Why:** seconds-to-milliseconds conversion applied twice or not at all is the
  classic unit defect this suite exists to catch.

### CFG-032 · `database.sqlite.foreign_keys: false` disables the pragma
- **Area:** `db/dialects.py::SqliteDialect.on_connect`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `foreign_keys: false`
- **Steps:** connect, `PRAGMA foreign_keys`
- **Expected:** `0`
- **Why:** the default is on; an operator who turned it off must actually get
  what they asked for, including the consequences.

### CFG-033 · SQLite's double-quoted-string fallback is off
- **Area:** `db/dialects.py::_refuse_double_quoted_strings`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a bootstrapped SQLite database
- **Steps:** `SELECT "no_such_column" FROM tenant`
- **Expected:** `no such column`, not a column of the constant string
- **Why:** QA finding Q-08 — with the fallback on, a control on a mistyped column
  reports **pass over the whole table**. The counterfactual is that the same
  control errors on DuckDB.

### CFG-034 · A genuine single-quoted string literal still works
- **Area:** `db/dialects.py::_refuse_double_quoted_strings`
- **Type:** regression
- **Priority:** P2
- **Precondition:** as above
- **Steps:** `SELECT 'literal'`
- **Expected:** `literal`
- **Why:** the counterfactual to CFG-033: a fix that broke every string literal
  would pass the first test and fail the product.

### CFG-035 · `database.postgres.*` defaults match the shipped file
- **Area:** `core/config/defaults.py` vs `config/application.yaml`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** compare each of host, port, database, user, sslmode,
  application_name, schema, statement_timeout
- **Expected:** identical *effective* values; the file's `${PGHOST:localhost}`
  resolves to the mapping's `localhost` when `PGHOST` is unset
- **Why:** `defaults.py` says "this mapping is the authority and the file is
  documentation. Where the two could drift, a test compares them" — the file
  uses placeholders the mapping does not, and the comparison must account for
  that rather than fail or be skipped.

### CFG-036 · `plugins.disabled` exists in the tracked file and not in `DEFAULTS`
- **Area:** `core/config/defaults.py::DEFAULTS["plugins"]`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** compare the `plugins` section of both
- **Expected:** either `disabled: []` is added to `DEFAULTS`, or its absence is
  deliberate and documented
- **Why:** the same "authority versus documentation" claim. A key only the file
  declares is a key `has()` reports differently depending on whether a file was
  found.

### CFG-037 · `plugins.entry_point_groups` lists all six groups
- **Area:** `core/config/defaults.py::DEFAULTS["plugins"]`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** compare the list to the registries `RegistryCatalogue` creates
- **Expected:** connectors, backends, monitors, notifiers, scorers, validators —
  and every group named here is created somewhere
- **Why:** a group nobody registers is a configuration key that does nothing; a
  registry whose group is missing here is a plugin kind nobody can extend.

### CFG-038 · `database.pool.size` below 1 is refused
- **Area:** `db/settings.py::PoolSettings.validate`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `--set database.pool.size=0`
- **Steps:** build settings
- **Expected:** `ConfigError` `CONFIG.POOL_INVALID`, remedy "at least 1"
- **Why:** a zero pool deadlocks on first checkout with no message.

### CFG-039 · `database.pool.max_overflow` of 0 is accepted
- **Area:** `db/settings.py::PoolSettings`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `--set database.pool.max_overflow=0`
- **Steps:** build settings and an engine
- **Expected:** accepted — a hard cap at `size` is a legitimate choice
- **Why:** `validate()` deliberately checks only `size`; the boundary should be
  confirmed rather than assumed.

### CFG-040 · A negative `max_overflow` is refused
- **Area:** `db/settings.py::PoolSettings.validate`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `--set database.pool.max_overflow=-5`
- **Steps:** build settings
- **Expected:** a named refusal
- **Why:** SQLAlchemy treats a negative overflow as unbounded, which silently
  removes the cap an operator thought they were setting.

### CFG-041 · `database.pool.timeout` and `recycle` accept durations
- **Area:** `db/settings.py::from_config`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `timeout: 45s`, `recycle: 1h`
- **Steps:** build settings
- **Expected:** `45.0` and `3600.0` seconds; `recycle` reaches
  `create_engine` as the integer `3600`
- **Why:** `pool_recycle` is `int(...)`-cast at the dialect; a fractional
  duration must not be silently truncated to something surprising.

### CFG-042 · `database.verify_on_start` defaults to true
- **Area:** `db/settings.py::DbSettings`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a drifted database
- **Steps:** `await database.start()`
- **Expected:** `SchemaDriftError` before any work happens
- **Why:** `Database.start` says failing here "names the actual problem" instead
  of producing failures hours later in unrelated code.

### CFG-043 · `database.verify_on_start: false` skips verification and nothing else
- **Area:** `db/__init__.py::Database.start`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a drifted database, verification off
- **Steps:** `await database.start()`
- **Expected:** starts; the async engine is still built; `verify()` still reports
  the drift when called explicitly
- **Why:** an escape hatch that also disables the *reporting* would make the
  drift invisible rather than merely unenforced.

### CFG-044 · `database.echo: true` logs SQL
- **Area:** `db/dialects.py::engine_kwargs`
- **Type:** functional
- **Priority:** P3
- **Precondition:** `echo: true`
- **Steps:** run one query with SQLAlchemy's logger captured
- **Expected:** the statement appears
- **Why:** both dialects pass `echo` through; a flag documented and dropped on
  one engine is a debugging tool that works on a laptop and not in production.

### CFG-045 · `database.schema_dir` relocates the authoritative file
- **Area:** `db/settings.py::DbSettings.schema_file`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `schema/` copied to `/tmp/qa/schema`, `schema_dir` set to it
- **Steps:** `prama db init`
- **Expected:** applies `/tmp/qa/schema/sqlite.sql`
- **Why:** the Dockerfile sets `PRAMA_DATABASE__SCHEMA_DIR=/opt/prama/schema`;
  if this key does not work the image cannot bootstrap.

### CFG-046 · A missing schema file is a named packaging failure
- **Area:** `db/dialects.py::schema_file_for`, `db/schema/loader.py::SchemaLoader.load`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `schema_dir` points at an empty directory
- **Steps:** `prama db init`
- **Expected:** `DatabaseError` `DB.SCHEMA_FILE_MISSING`, remedy explaining there
  are no migrations and naming `database.schema_dir`
- **Why:** "Its absence is a packaging failure, not a condition to work around."

### CFG-047 · `concurrency.supervisor.shutdown_grace` is honoured
- **Area:** `core/concurrency/supervisor.py::TaskSupervisor.shutdown`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a supervised task that ignores cancellation, grace `1s`
- **Steps:** `await sup.shutdown()`, timed
- **Expected:** returns after about one second, logging that the task did not
  stop within the grace
- **Why:** a shutdown that waits for ever on one stuck task is an operator
  holding `kill -9`.

### CFG-048 · `concurrency.lease.provider` selects database or memory
- **Area:** `db/__init__.py::Database.lease_provider`, `core/concurrency/leases.py`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `provider: memory` and `provider: database` in turn
- **Steps:** resolve the provider
- **Expected:** `MemoryLeaseProvider` and `DatabaseLeaseProvider` respectively;
  an unknown value refused by name
- **Why:** the memory provider "is deliberately not the default: a provider that
  silently grants every request would make a two-node deployment duplicate all
  its work with no symptom".

### CFG-049 · `lease.renew_interval` at or above `lease.ttl` is refused
- **Area:** `core/concurrency/leases.py::LeaseSettings.validate`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `ttl: 10s`, `renew_interval: 10s`
- **Steps:** construct a `LeaseHolder`
- **Expected:** `ValueError` — "a lease expires between renewals"
- **Why:** the invariant is arithmetic; letting it through produces a lease that
  is lost on a healthy holder.

### CFG-050 · `renew_interval` over half the TTL warns but proceeds
- **Area:** `core/concurrency/leases.py::LeaseSettings.validate`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `ttl: 10s`, `renew_interval: 6s`
- **Steps:** construct a holder with logging captured
- **Expected:** a warning recommending `ttl >= 3x renew_interval`; no exception
- **Why:** the shipped default (30s/10s) sits exactly on the recommended ratio,
  so the warning must not fire for it — test both.

### CFG-051 · `lease.clock_skew_allowance` widens the validity check
- **Area:** `core/concurrency/leases.py::LeaseHolder.raise_if_lost`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a `ManualClock`, a lease expiring in 1s, allowance 2s
- **Steps:** `raise_if_lost()`
- **Expected:** `LeaseLostError` — the allowance makes the holder give up
  *earlier*, not later
- **Why:** skew handling that made a holder hold on longer would be the opposite
  of safe; the sign of this comparison is the whole value of the setting.

## Configuration — sources, precedence and parsing

### CFG-052 · Precedence runs defaults → file → local overlay → env → CLI
- **Area:** `core/config/configuration.py::ConfigurationBuilder.build`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the same key set in all five sources with distinct values
- **Steps:** build and read it
- **Expected:** the `--set` value wins; removing sources one at a time yields the
  next in order
- **Why:** the layering is stated in three docstrings; an operator debugging a
  production mystery relies on it being exactly this order.

### CFG-053 · An overlay overrides key by key, not wholesale
- **Area:** `core/config/sources.py::deep_merge`
- **Type:** functional
- **Priority:** P1
- **Precondition:** overlay sets only `database.pool.size`
- **Steps:** read `database.pool.max_overflow`
- **Expected:** still the default 20
- **Why:** "an operator can override `database.pool.size` without having to
  restate the rest of `database`".

### CFG-054 · Lists replace rather than concatenate
- **Area:** `core/config/sources.py::deep_merge`
- **Type:** functional
- **Priority:** P2
- **Precondition:** overlay sets `plugins.entry_point_groups: [prama.connectors]`
- **Steps:** read the list
- **Expected:** exactly one entry
- **Why:** the docstring explains concatenation "makes it impossible to *remove*
  a default entry, which is the operation operators actually need".

### CFG-055 · The local overlay is discovered from the base file's name
- **Area:** `core/config/sources.py::local_overlay_for`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `/tmp/qa/app.yaml` and `/tmp/qa/app.local.yaml`
- **Steps:** `load_configuration("/tmp/qa/app.yaml")`
- **Expected:** the overlay is merged without being named
- **Why:** "the mechanism that keeps secrets out of tracked configuration
  without any deployment having to know the overlay exists".

### CFG-056 · A missing local overlay is not an error
- **Area:** `core/config/sources.py::FileSource.load`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** base file present, overlay absent
- **Steps:** load
- **Expected:** loads cleanly
- **Why:** "forcing operators to create empty files is friction with no safety
  benefit".

### CFG-057 · A `.properties` overlay is discovered for a `.properties` base
- **Area:** `core/config/sources.py::local_overlay_for` + `source_for`
- **Type:** functional
- **Priority:** P3
- **Precondition:** `app.properties` and `app.local.properties`
- **Steps:** load
- **Expected:** both parsed, the overlay winning
- **Why:** `with_name(f"{stem}.local{suffix}")` is format-agnostic; the JVM
  migration path claimed in the docstring depends on it.

### CFG-058 · Malformed YAML is refused with the parser's detail
- **Area:** `core/config/sources.py::YamlFileSource._parse`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a file containing `a: [1, 2`
- **Steps:** load
- **Expected:** `CONFIG.YAML_INVALID` with the YAML error in `context["detail"]`
- **Why:** a config parse failure with no line number costs an hour.

### CFG-059 · A YAML document that is a list is refused
- **Area:** `core/config/sources.py::YamlFileSource._parse`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a file containing `- a\n- b`
- **Steps:** load
- **Expected:** `CONFIG.YAML_SHAPE`, remedy "wrap the document in key: value pairs"
- **Why:** a list merged as a mapping would raise somewhere unrelated.

### CFG-060 · An empty YAML file contributes nothing
- **Area:** `core/config/sources.py::YamlFileSource._parse`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a zero-byte `application.local.yaml`
- **Steps:** load
- **Expected:** `{}` — the defaults survive
- **Why:** `yaml.safe_load("")` is `None`; treating that as a mapping would wipe
  the merge.

### CFG-061 · An unreadable file is refused, not skipped
- **Area:** `core/config/sources.py::FileSource.load`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `chmod 000` on the base file
- **Steps:** load
- **Expected:** `CONFIG.FILE_UNREADABLE`, remedy naming permissions and UTF-8
- **Why:** a required file that exists and cannot be read must not degrade to
  defaults; that is how a production instance runs on a development secret.

### CFG-062 · A non-UTF-8 config file is refused with the same code
- **Area:** `core/config/sources.py::FileSource.load`
- **Type:** negative
- **Priority:** P3
- **Precondition:** a latin-1 encoded YAML file with an accented value
- **Steps:** load
- **Expected:** `CONFIG.FILE_UNREADABLE` — `UnicodeDecodeError` is a `ValueError`,
  not an `OSError`, so confirm it is caught and translated rather than escaping
  as a traceback
- **Why:** the `except OSError` clause does not cover decode failures.

### CFG-063 · An unsupported config extension is refused
- **Area:** `core/config/sources.py::source_for`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `--config app.toml`
- **Steps:** load
- **Expected:** `CONFIG.FORMAT_UNSUPPORTED`, remedy listing `.yaml`, `.yml`,
  `.properties`
- **Why:** TOML looks plausible enough that somebody will try it.

### CFG-064 · A properties line with neither `=` nor `:` is refused with its line number
- **Area:** `core/config/sources.py::PropertiesFileSource._parse`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a properties file whose third line is `database.pool.size`
- **Steps:** load
- **Expected:** `CONFIG.PROPERTIES_INVALID` naming line 3
- **Why:** "not a key/value line" without a line number is unactionable in a
  file with thousands of them.

### CFG-065 · Properties comments start with `#` or `!`
- **Area:** `core/config/sources.py::PropertiesFileSource._parse`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a file with both comment forms
- **Steps:** load
- **Expected:** both ignored, no refusal
- **Why:** `!` is the JVM convention; estates migrating from JVM tooling are the
  stated reason this source exists.

### CFG-066 · Properties dotted keys expand to the YAML shape
- **Area:** `core/config/sources.py::expand_dotted`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `database.pool.size = 20`
- **Steps:** load and read `database.pool.size`
- **Expected:** `20`, and `database.dialect` still `sqlite`
- **Why:** "nothing downstream can tell which format was used".

### CFG-067 · A scalar/section collision is reported, not resolved
- **Area:** `core/config/sources.py::expand_dotted`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `--set a=1 --set a.b=2`
- **Steps:** build
- **Expected:** `CONFIG.KEY_CONFLICT` naming the key and the conflict point
- **Why:** "either resolution silently discards something the operator wrote".

### CFG-068 · Only `PRAMA_`-prefixed environment variables contribute
- **Area:** `core/config/sources.py::EnvironmentSource.load`
- **Type:** security
- **Priority:** P1
- **Precondition:** `PATH`, `HOME`, `USER` set; `PRAMA_APP__NAME=x` set
- **Steps:** build
- **Expected:** only `app.name` changes; there is no `path` key
- **Why:** "an unrelated `PATH` or `HOME` can never silently become a setting".

### CFG-069 · `PRAMA_DATABASE__POOL__SIZE` maps to `database.pool.size`
- **Area:** `core/config/sources.py::EnvironmentSource.load`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the variable set to `20`
- **Steps:** `config.get_int("database.pool.size")`
- **Expected:** `20` as an int, `"20"` when read with `get_str`
- **Why:** "coercion happens at read time against the type the caller asks for".

### CFG-070 · A single underscore is not a separator
- **Area:** `core/config/sources.py::ENV_SEPARATOR`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `PRAMA_APP__INSTANCE_ID=box`
- **Steps:** read `app.instance_id`
- **Expected:** `box` — the inner underscore is part of the key segment
- **Why:** "a single one is legal inside a key segment"; a greedy split would
  produce `app.instance.id`, a key nothing reads.

### CFG-071 · A bare `PRAMA_` variable is ignored
- **Area:** `core/config/sources.py::EnvironmentSource.load`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `PRAMA_=x`
- **Steps:** build
- **Expected:** no empty-named key; no crash
- **Why:** the `if path:` guard exists for exactly this and must stay.

### CFG-072 · Environment keys are lowercased
- **Area:** `core/config/sources.py::EnvironmentSource.load`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `PRAMA_DATABASE__DIALECT=postgres`
- **Steps:** read `database.dialect`
- **Expected:** found under the lowercase path
- **Why:** the Helm chart and the Dockerfile both configure exclusively through
  upper-case environment variables.

### CFG-073 · `--set` without `=` is refused
- **Area:** `core/config/sources.py::CliSource.load`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `--set database.dialect`
- **Steps:** run any command
- **Expected:** `CONFIG.CLI_INVALID`, remedy showing `--set path.to.key=value`
- **Why:** a malformed override that was ignored would make the command do
  something other than what was typed.

### CFG-074 · `--set` with an empty value sets an empty string
- **Area:** `core/config/sources.py::CliSource.load`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `--set tenancy.default_tenant=`
- **Steps:** read it
- **Expected:** `""`, which is the documented "multi-tenant" value
- **Why:** clearing a key set in a file is a real operation and the only way to
  express it.

### CFG-075 · `--set` values containing `=` keep everything after the first one
- **Area:** `core/config/sources.py::CliSource.load`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `--set security.session_secret=a=b=c`
- **Steps:** read it
- **Expected:** `a=b=c`
- **Why:** `split("=", 1)`; base64 and URL values contain `=` constantly.

### CFG-076 · `--set` strips surrounding whitespace from key and value
- **Area:** `core/config/sources.py::CliSource.load`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `--set " app.name = Prama "`
- **Steps:** read `app.name`
- **Expected:** `Prama`
- **Why:** confirm the strip, and confirm it does not strip *inside* the value.

### CFG-077 · Provenance names the source of every key
- **Area:** `core/config/configuration.py::_record_provenance`
- **Type:** functional
- **Priority:** P2
- **Precondition:** one key from each source
- **Steps:** `config.provenance("database.pool.size")`
- **Expected:** `"command line"` when set by `--set`, `"environment"` when by env,
  the file's path when by file, `"built-in defaults"` otherwise
- **Why:** "the usual production mystery is not what a setting is but which of
  five files set it".

### CFG-078 · Provenance records the *winning* source, not the last recorded
- **Area:** `core/config/configuration.py::build`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `app.name` set in the file and overridden by `--set`
- **Steps:** read the provenance
- **Expected:** `"command line"`
- **Why:** provenance is recorded per source in order, so the strongest source
  overwrites — confirm that the value and its attribution cannot disagree.

### CFG-079 · A key set only in a section still reports provenance through `section()`
- **Area:** `core/config/configuration.py::Configuration.section`
- **Type:** functional
- **Priority:** P3
- **Precondition:** `database.pool.size` from the environment
- **Steps:** `config.section("database").provenance("pool.size")`
- **Expected:** `"environment"` — the prefix is applied before lookup
- **Why:** a section view that silently lost provenance would make
  `prama config show` wrong for every nested key.

### CFG-080 · `redacted()` masks every sensitive key
- **Area:** `core/log.py::redact_mapping`, `Configuration.redacted`
- **Type:** security
- **Priority:** P1
- **Precondition:** non-empty values on each of the sixteen `SENSITIVE_KEYS`
- **Steps:** `config.redacted()`
- **Expected:** every one is `***`; nothing else is
- **Why:** "`prama config show` is never a credential leak".

### CFG-081 · Redaction reaches nested mappings
- **Area:** `core/log.py::redact_mapping`
- **Type:** security
- **Priority:** P1
- **Precondition:** `database.postgres.password: hunter2`
- **Steps:** `redacted()`
- **Expected:** masked at depth
- **Why:** every real secret in this configuration is nested at least two levels.

### CFG-082 · Redaction does not reach inside lists
- **Area:** `core/log.py::redact_mapping`
- **Type:** security
- **Priority:** P2
- **Precondition:** a list of mappings each carrying a `password`
- **Steps:** `redacted()`
- **Expected:** the nested passwords are masked, or the gap is documented
- **Why:** the function recurses into `dict` only; a list of connection
  definitions is the shape a multi-source config would naturally take.

### CFG-083 · An empty sensitive value is left as it is
- **Area:** `core/log.py::redact_mapping`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `session_secret: ""`
- **Steps:** `redacted()`
- **Expected:** `""`, not `***`
- **Why:** deliberate — an operator must be able to see from `config show` that
  the secret is *not set*, which `***` would hide.

### CFG-084 · `flatten(redact=True)` masks by leaf name
- **Area:** `core/config/configuration.py::Configuration.flatten`
- **Type:** security
- **Priority:** P2
- **Precondition:** `security.session_secret` set
- **Steps:** `flatten()`
- **Expected:** `security.session_secret -> "***"`
- **Why:** `flatten` uses the last dotted segment; a key whose sensitive word is
  not the final segment (`password_file`) is not masked — confirm which is
  intended.

### CFG-085 · `flatten(redact=False)` returns the real values
- **Area:** `core/config/configuration.py::Configuration.flatten`
- **Type:** security
- **Priority:** P2
- **Precondition:** as above
- **Steps:** `flatten(redact=False)`
- **Expected:** the secret in clear
- **Why:** the unsafe mode exists; confirm that no caller in `src/` passes
  `redact=False` into anything that prints.

### CFG-086 · The log redaction filter masks secrets in the message text
- **Area:** `core/log.py::RedactionFilter`
- **Type:** security
- **Priority:** P1
- **Precondition:** a record logging `password=hunter2`
- **Steps:** emit through the configured handler
- **Expected:** `password=***`
- **Why:** "a filter on the handler rather than discipline at every call site".

### CFG-087 · The filter masks quoted values too
- **Area:** `core/log.py::_SENSITIVE_TEXT`
- **Type:** security
- **Priority:** P2
- **Precondition:** messages containing `token: "abc"` and `api_key='xyz'`
- **Steps:** emit
- **Expected:** both masked
- **Why:** the pattern covers double and single quotes; a connection string
  logged as a repr is the realistic case.

### CFG-088 · The filter does not mask a secret embedded in a URL
- **Area:** `core/log.py::_SENSITIVE_TEXT`
- **Type:** security
- **Priority:** P2
- **Precondition:** a message containing `postgresql://prama:hunter2@host/db`
- **Steps:** emit
- **Expected:** the password is masked, or the limitation is documented
- **Why:** the regex requires `key: value` or `key=value`; a DSN is the single
  most likely thing to be logged and does not match.

### CFG-089 · Structured fields are redacted as well as the message
- **Area:** `core/log.py::RedactionFilter.filter`
- **Type:** security
- **Priority:** P1
- **Precondition:** `log_fields(log, INFO, "x", password="hunter2")`
- **Steps:** emit through the handler
- **Expected:** `fields.password == "***"`
- **Why:** the JSON formatter writes `prama_fields` verbatim; unfiltered, the
  structured path is a bypass of the text path.

### CFG-090 · Correlation and tenant ids survive an async hop
- **Area:** `core/log.py::correlation_id`, `ContextFilter`
- **Type:** concurrency
- **Priority:** P2
- **Precondition:** a correlation id set, then `await` across a task boundary
- **Steps:** log on both sides
- **Expected:** the same id on both records
- **Why:** `ContextVar` is chosen so the id "survives async hops without being
  threaded through every signature".

### CFG-091 · Two tasks do not see each other's correlation id
- **Area:** `core/log.py::correlation_id`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** two concurrent tasks setting different ids
- **Steps:** log from both, repeatedly
- **Expected:** no crossover
- **Why:** a leaked correlation id attributes one tenant's failure to another's
  request, which is both a debugging and a disclosure problem.

### CFG-092 · Applying the logging configuration twice does not duplicate handlers
- **Area:** `core/log.py::LoggingConfigurator.apply`
- **Type:** regression
- **Priority:** P2
- **Precondition:** none
- **Steps:** `apply()` twice, log once
- **Expected:** one line
- **Why:** "Idempotent: calling it twice replaces the handler rather than adding
  a second one, which is the usual cause of duplicated log lines in a reloading
  dev server."

### CFG-093 · A pre-existing non-Prama handler is left alone
- **Area:** `core/log.py::LoggingConfigurator.apply`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a third-party handler on the root logger
- **Steps:** `apply()`
- **Expected:** it survives; only handlers named `prama` are removed
- **Why:** a library that removes everybody's handlers is a library nobody
  embeds.

### CFG-094 · The JSON formatter emits a UTC timestamp with milliseconds and a `Z`
- **Area:** `core/log.py::JsonFormatter.format`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** emit and parse `ts`
- **Expected:** `YYYY-MM-DDTHH:MM:SS.mmmZ`
- **Why:** `formatTime` uses local time by default; a `Z` on a local timestamp is
  a lie a shipper will believe.

### CFG-095 · The JSON formatter renders an exception
- **Area:** `core/log.py::JsonFormatter.format`
- **Type:** functional
- **Priority:** P3
- **Precondition:** `logger.exception(...)` inside an `except`
- **Steps:** emit
- **Expected:** an `exception` field carrying the traceback, and the line is
  still one parseable JSON object
- **Why:** a multi-line traceback outside the JSON object breaks every line-
  oriented shipper.

## Configuration — coercion and placeholders

### CFG-096 · `to_bool` accepts every documented truthy word
- **Area:** `core/config/coercion.py::Coercer.to_bool`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** coerce `1 true yes y on enabled` and `0 false no n off disabled`
- **Expected:** `True` and `False` respectively, case-insensitively, with
  surrounding whitespace tolerated
- **Why:** the module's stated purpose is that nobody ever gets "a silent
  `"false"` that is truthy, which is the classic configuration defect".

### CFG-097 · `to_bool` refuses a word it does not know
- **Area:** `core/config/coercion.py::Coercer.to_bool`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `PRAMA_WEB__ENABLED=maybe`
- **Steps:** `get_bool("web.enabled")`
- **Expected:** `ConfigTypeError` `CONFIG.TYPE` naming the key and listing the
  accepted forms
- **Why:** the alternative is `bool("maybe") is True`, which turns a typo into a
  feature nobody asked for.

### CFG-098 · `to_int` refuses a boolean
- **Area:** `core/config/coercion.py::Coercer.to_int`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `database.pool.size: true` in YAML
- **Steps:** `get_int`
- **Expected:** refused — "A boolean is not an integer here; be explicit."
- **Why:** `int(True)` is 1, and a pool of one that was meant to be enabled is a
  production incident that reads as a load problem.

### CFG-099 · `to_int` accepts a base prefix
- **Area:** `core/config/coercion.py::Coercer.to_int`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `--set database.pool.size=0x10`
- **Steps:** `get_int`
- **Expected:** `16` — `int(text, 0)` is deliberate
- **Why:** confirm the behaviour is intended rather than an accident, since it
  also means a leading zero is an error (`010` is refused).

### CFG-100 · `to_int` accepts a whole float and refuses a fractional one
- **Area:** `core/config/coercion.py::Coercer.to_int`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `pool.size: 10.0` and `pool.size: 10.5`
- **Steps:** `get_int`
- **Expected:** `10`, then a refusal
- **Why:** YAML produces a float for `10.0`; truncating `10.5` silently would be
  the flattering direction.

### CFG-101 · `to_float` refuses a boolean
- **Area:** `core/config/coercion.py::Coercer.to_float`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a boolean value
- **Steps:** `get_float`
- **Expected:** refused with the "be explicit" remedy
- **Why:** symmetry with `to_int`; a threshold of `1.0` meaning `true` is a
  silent monitor change.

### CFG-102 · `to_list` splits a comma-separated environment value
- **Area:** `core/config/coercion.py::Coercer.to_list`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `PRAMA_PLUGINS__ENTRY_POINT_GROUPS=a,b, c`
- **Steps:** `get_list`
- **Expected:** `["a", "b", "c"]`, empty segments dropped
- **Why:** "comma-separated is the only sane rendering of a list in an env var".

### CFG-103 · `to_list` of an empty string is an empty list
- **Area:** `core/config/coercion.py::Coercer.to_list`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `PRAMA_PLUGINS__DISABLED=`
- **Steps:** `get_list`
- **Expected:** `[]`
- **Why:** disabling nothing must be expressible; `[""]` would disable a plugin
  whose key is the empty string.

### CFG-104 · `to_list` refuses a mapping
- **Area:** `core/config/coercion.py::Coercer.to_list`
- **Type:** negative
- **Priority:** P3
- **Precondition:** a YAML mapping where a list is expected
- **Steps:** `get_list`
- **Expected:** `ConfigTypeError` naming the key
- **Why:** a mapping read as a list would iterate its keys and look almost right.

### CFG-105 · `to_dict` refuses a scalar
- **Area:** `core/config/coercion.py::Coercer.to_dict`
- **Type:** negative
- **Priority:** P3
- **Precondition:** `database: sqlite` (a scalar where a section belongs)
- **Steps:** `get_dict("database")`
- **Expected:** refused, naming the key
- **Why:** the shape mistake a person makes when flattening a config by hand.

### CFG-106 · Every duration unit converts correctly
- **Area:** `core/config/coercion.py::Coercer.to_duration_seconds`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** coerce `1ns 1us 1ms 1s 1sec 1secs 1m 1min 1mins 1h 1hr 1hrs 1d 1day
  1days 1w`
- **Expected:** 1e-9, 1e-6, 1e-3, 1, 1, 1, 60, 60, 60, 3600, 3600, 3600, 86400,
  86400, 86400, 604800
- **Why:** every one of these is accepted, so every one of these is a promise. A
  unit silently mapped wrong is a timeout an order of magnitude off.

### CFG-107 · A bare number is seconds
- **Area:** `core/config/coercion.py::Coercer.to_duration_seconds`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `busy_timeout: 5`
- **Steps:** coerce
- **Expected:** `5.0`
- **Why:** the documented fallback; treating it as milliseconds would make the
  same file mean different things on different keys.

### CFG-108 · An unknown duration unit is refused
- **Area:** `core/config/coercion.py::Coercer.to_duration_seconds`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `busy_timeout: 5 fortnights`
- **Steps:** coerce
- **Expected:** refused, remedy showing `500ms, 30s, 5m, 2h, 1d`
- **Why:** a partial match that took the number and dropped the unit would
  produce five seconds where five weeks was meant.

### CFG-109 · A duration is case-insensitive
- **Area:** `core/config/coercion.py::_DURATION`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `30S`, `5M`
- **Steps:** coerce
- **Expected:** 30 and 300
- **Why:** the pattern is `(?i)`; `5M` meaning megabytes-minutes confusion is
  worth pinning down explicitly.

### CFG-110 · A fractional duration is honoured
- **Area:** `core/config/coercion.py::to_duration_seconds`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `0.5s`, `.5s`
- **Steps:** coerce
- **Expected:** `0.5` for both
- **Why:** the regex allows a leading dot; a sub-second timeout is a legitimate
  thing to want.

### CFG-111 · A negative duration is refused
- **Area:** `core/config/coercion.py::to_duration_seconds`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `busy_timeout: -5s`
- **Steps:** coerce
- **Expected:** a refusal
- **Why:** the regex has no sign, so `-5s` does not match and falls to the
  refusal — confirm, because a numeric `-5` **does** pass through the
  `isinstance(int|float)` branch and would be accepted.

### CFG-112 · A negative numeric duration passes the type check
- **Area:** `core/config/coercion.py::to_duration_seconds`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `busy_timeout: -5`
- **Steps:** coerce, then apply as a PRAGMA
- **Expected:** refused at coercion or refused by the consumer; never applied
- **Why:** the string form and the numeric form of the same value must not
  disagree about validity.

### CFG-113 · Decimal and binary byte units differ as the standards intend
- **Area:** `core/config/coercion.py::Coercer.to_bytes`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** coerce `1kb 1kib 1mb 1mib 1gb 1gib 1tb 1tib`
- **Expected:** 1000/1024, 1e6/1048576, 1e9/1073741824, 1e12/1099511627776
- **Why:** the docstring: "Ambiguity here produces budgets that are 7% wrong,
  which is exactly wrong enough to be missed."

### CFG-114 · A bare number of bytes is bytes
- **Area:** `core/config/coercion.py::Coercer.to_bytes`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `268435456`
- **Steps:** coerce
- **Expected:** `268435456`
- **Why:** the documented fallback, and the form the module says an operator
  should never have to write.

### CFG-115 · An unknown size unit is refused
- **Area:** `core/config/coercion.py::Coercer.to_bytes`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `512megs`
- **Steps:** coerce
- **Expected:** refused, remedy showing `1024, 512kb, 256mb, 4gib`
- **Why:** `megs` is what somebody types; taking the 512 and dropping the unit
  would give half a kilobyte.

### CFG-116 · `to_bytes` refuses a boolean and a fractional float
- **Area:** `core/config/coercion.py::Coercer.to_bytes`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `true`, `1.5`
- **Steps:** coerce
- **Expected:** both refused
- **Why:** the float branch requires `is_integer()`; a fraction of a byte is not
  a budget.

### CFG-117 · A `ConfigTypeError` names the key, the value and the wanted type
- **Area:** `core/config/coercion.py::Coercer._fail`
- **Type:** contract
- **Priority:** P1
- **Precondition:** any coercion failure on a nested key
- **Steps:** read `exc.context`
- **Expected:** `key`, `value` (as a repr) and `wanted`
- **Why:** the key is the only thing that makes the error actionable in a
  hundred-key configuration.

### CFG-118 · A coercion failure on a secret does not print the secret
- **Area:** `core/config/coercion.py::Coercer._fail`
- **Type:** security
- **Priority:** P1
- **Precondition:** `security.session_secret` set to something that fails a
  coercion
- **Steps:** trigger the failure, read `str(exc)`
- **Expected:** the value is masked
- **Why:** `context={"value": repr(value)}` puts the raw value into an error that
  the API renders as a problem document and the logger writes out.

### CFG-119 · `${VAR}` with no value and no default is an error
- **Area:** `core/config/resolver.py::PlaceholderResolver.resolve_value`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `app.instance_id: ${NOT_SET}`
- **Steps:** build
- **Expected:** `CONFIG.PLACEHOLDER_UNRESOLVED`, remedy naming the variable and
  showing the `${NAME:value}` form
- **Why:** "a mistake fails loudly rather than producing a plausible-looking
  wrong value" — an empty instance id would be accepted everywhere and mean
  nothing.

### CFG-120 · `${VAR:default}` uses the default when unset
- **Area:** `core/config/resolver.py`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `PGHOST` unset
- **Steps:** read `database.postgres.host` from the tracked file
- **Expected:** `localhost`
- **Why:** every shipped placeholder in `application.yaml` carries a default;
  this is what makes the tracked file usable with no environment at all.

### CFG-121 · A default containing a colon is preserved
- **Area:** `core/config/resolver.py::_PLACEHOLDER`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `x: ${NOT_SET:http://host:5432/db}`
- **Steps:** resolve
- **Expected:** the whole URL
- **Why:** the pattern's default group is `[^}]*`, so a colon inside it is fine —
  confirm, because a DSN default is the obvious use.

### CFG-122 · An empty default resolves to an empty string
- **Area:** `core/config/resolver.py`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `x: ${NOT_SET:}`
- **Steps:** resolve
- **Expected:** `""`, not a refusal
- **Why:** `match.group("default")` is `""` rather than `None`; deliberately
  declaring a key empty must be possible.

### CFG-123 · `$${X}` escapes to a literal
- **Area:** `core/config/resolver.py::_PLACEHOLDER`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `x: $${NOT_A_VAR}`
- **Steps:** resolve
- **Expected:** `${NOT_A_VAR}`
- **Why:** a documented escape that does not work is a value nobody can express —
  a password containing `${` is the realistic case.

### CFG-124 · A placeholder can reference another configuration key
- **Area:** `core/config/resolver.py::_lookup`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `paths.data: /var/lib/prama` and `evidence.path: ${paths.data}/evidence`
- **Steps:** resolve
- **Expected:** `/var/lib/prama/evidence`
- **Why:** the docstring's own example; it is what makes a templating engine
  unnecessary.

### CFG-125 · The environment wins over a configuration key of the same name
- **Area:** `core/config/resolver.py::_lookup`
- **Type:** functional
- **Priority:** P2
- **Precondition:** both `PGHOST` in the environment and `pghost` in the config
- **Steps:** resolve `${PGHOST}`
- **Expected:** the environment value
- **Why:** "against the environment first and the merged configuration second" —
  the order is stated and must hold.

### CFG-126 · A self-referencing placeholder is refused with the chain
- **Area:** `core/config/resolver.py::resolve_value`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `a: ${a}`
- **Steps:** resolve
- **Expected:** `CONFIG.PLACEHOLDER_CYCLE`, message showing `a -> a`
- **Why:** "a cycle is reported with the chain that formed it" — without the
  chain an operator cannot find which of forty keys did it.

### CFG-127 · A two-step cycle is refused
- **Area:** `core/config/resolver.py::resolve_value`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `a: ${b}`, `b: ${a}`
- **Steps:** resolve
- **Expected:** `CONFIG.PLACEHOLDER_CYCLE` naming both
- **Why:** the `_seen` tuple is per-chain; confirm it catches an indirect loop
  and not only the trivial one.

### CFG-128 · Recursion deeper than sixteen levels is refused
- **Area:** `core/config/resolver.py::MAX_DEPTH`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a seventeen-link non-cyclic chain
- **Steps:** resolve
- **Expected:** `CONFIG.PLACEHOLDER_CYCLE` mentioning the depth
- **Why:** the bound exists so a pathological chain cannot exhaust the stack;
  check the sixteen-link chain still resolves.

### CFG-129 · Substitution applies to strings only
- **Area:** `core/config/resolver.py::_walk`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `database.pool.size: 10` (an int)
- **Steps:** resolve
- **Expected:** still the int `10`, not `"10"`
- **Why:** "numeric settings cannot be corrupted by a stray `$`" — and a
  stringified int would then fail `to_int`'s boolean guard in confusing ways.

### CFG-130 · Placeholders inside a list are resolved
- **Area:** `core/config/resolver.py::_walk`
- **Type:** functional
- **Priority:** P3
- **Precondition:** `plugins.entry_point_groups: ["${GROUP:prama.connectors}"]`
- **Steps:** resolve
- **Expected:** the resolved string, and the path in an error is `...[0]`
- **Why:** list indices are included in the reported path; a placeholder failure
  inside a list must still be locatable.

### CFG-131 · `has()` distinguishes absent from null
- **Area:** `core/config/configuration.py::Configuration.has`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `tenancy.default_tenant: null` in YAML
- **Steps:** `has("tenancy.default_tenant")` and `get_str(..., "")`
- **Expected:** `has` is `True`; `get_str` returns the supplied default because
  the value is `None`
- **Why:** an explicit null and an omitted key are different operator intents
  and the typed readers collapse them — confirm that is what is wanted.

### CFG-132 · `require()` names the key and both ways to set it
- **Area:** `core/config/configuration.py::Configuration.require`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a missing key inside a section view
- **Steps:** `config.section("database").require("nope")`
- **Expected:** `ConfigMissingError` whose message says `database.nope` and whose
  remedy names `PRAMA_DATABASE__NOPE`
- **Why:** the qualified key is what makes the remedy followable; a section view
  that dropped the prefix would send the operator to the wrong place.

### CFG-133 · `section()` on a scalar is refused
- **Area:** `core/config/configuration.py::Configuration.section`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `database: sqlite`
- **Steps:** `config.section("database")`
- **Expected:** `CONFIG.NOT_A_SECTION`
- **Why:** silently returning an empty section would make every database setting
  fall back to its default while the operator's file says otherwise.

### CFG-134 · `section()` on a missing path is an empty section
- **Area:** `core/config/configuration.py::Configuration.section`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** no `notifiers` key at all
- **Steps:** `config.section("notifiers").get_str("x", "d")`
- **Expected:** `"d"`
- **Why:** "a missing section is an empty one" — components must be constructible
  before anybody has configured them.

### CFG-135 · `bind()` coerces every field type
- **Area:** `core/config/configuration.py::Configuration.bind`, `_coerce_hint`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a dataclass with `str`, `int`, `float`, `bool`, `Path`,
  `list`, `dict` and optional fields, all supplied as strings
- **Steps:** `bind("section", cls)`
- **Expected:** every field arrives as its declared type; `Path` is
  `expanduser`-ed
- **Why:** "Validation happens once, at startup" — a field the binder passes
  through as a string defeats the entire mechanism.

### CFG-136 · `bind()` of a missing required field fails at boot
- **Area:** `core/config/configuration.py::Configuration.bind`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a dataclass field with no default and no configured value
- **Steps:** `bind`
- **Expected:** `ConfigMissingError` naming `section.field`
- **Why:** "a typo in a key name is a boot failure rather than a 3am `KeyError`".

### CFG-137 · `bind()` of a non-dataclass is a `TypeError`
- **Area:** `core/config/configuration.py::Configuration.bind`
- **Type:** negative
- **Priority:** P3
- **Precondition:** a plain class
- **Steps:** `bind`
- **Expected:** `TypeError` naming the class
- **Why:** it is a programming error rather than a configuration one, and the
  distinction should be visible in the type raised.

### CFG-138 · An optional field set to null binds to `None`
- **Area:** `core/config/configuration.py::_coerce_hint`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `field: null` with the hint `int | None`
- **Steps:** `bind`
- **Expected:** `None`, not `0`
- **Why:** the union branch checks for `None` before coercing; a null coerced to
  a zero is a threshold nobody set.

### CFG-139 · `get_path` expands `~`
- **Area:** `core/config/configuration.py::Configuration.get_path`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `database.sqlite.path: ~/prama.db`
- **Steps:** `get_path`
- **Expected:** an absolute path under the home directory
- **Why:** a literal `~` directory created in the working directory is the
  classic symptom of a missing `expanduser`.

### CFG-140 · `raw()` is not defensively copied
- **Area:** `core/config/configuration.py::Configuration.raw`
- **Type:** contract
- **Priority:** P3
- **Precondition:** a built configuration
- **Steps:** mutate the returned mapping, re-read the key
- **Expected:** the class documents that "callers must not mutate it"; confirm
  no caller in `src/` does
- **Why:** the class claims to be immutable and this is the one hole in the
  claim; `run_prama_web.py` passes `config.raw()` into a new builder.

## The error taxonomy

### CFG-141 · Every error class carries a distinct, stable code
- **Area:** `core/errors.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** enumerate every `PramaError` subclass and its `code`
- **Expected:** `PRAMA.ERROR`, `CONFIG.INVALID`, `CONFIG.MISSING`, `CONFIG.TYPE`,
  `CONFIG.SECRET_MISSING`, `REGISTRY.INVALID`, `DB.ERROR`, `DB.SCHEMA_DRIFT`,
  `CONCURRENCY.INVARIANT`, `CONCURRENCY.LEASE_LOST`, `CONCURRENCY.BACKPRESSURE`,
  `ENTITY.NOT_FOUND`, `ENTITY.CONFLICT`, `INPUT.INVALID`, `AUTH.UNAUTHORISED`,
  `AUTH.FORBIDDEN` — all unique, all `AREA.CONDITION`
- **Why:** "Codes are part of the public contract … they may not be renamed
  without a deprecation window."

### CFG-142 · `remedy` is a required keyword argument
- **Area:** `core/errors.py::PramaError.__init__`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** `PramaError("x")` with no remedy
- **Expected:** `TypeError`
- **Why:** "it is the constructor signature, so an error that omits the next
  action cannot be raised".

### CFG-143 · Every `raise` of a Prama error in `src/` passes a non-empty remedy
- **Area:** all of `src/prama/`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** scan every construction of a `PramaError` subclass
- **Expected:** none passes `remedy=""` or a remedy that is only a restatement of
  the message
- **Why:** the signature enforces presence, not usefulness; `tests/architecture/
  test_remedies.py` already checks that remedies do not name keys nothing reads,
  and emptiness is the gap beside it.

### CFG-144 · Every remedy naming a command names one that exists
- **Area:** all of `src/prama/`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** none
- **Steps:** extract every `prama ...` command quoted in a remedy and run it with
  `--help`
- **Expected:** every one resolves
- **Why:** the catalogue README records that three shipped remedies named
  commands that did not exist.

### CFG-145 · Every remedy naming a file names one the product would create or ship
- **Area:** all of `src/prama/`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** a fresh clone
- **Steps:** extract every path quoted in a remedy
- **Expected:** each exists, is git-ignored by design, or is described as one to
  create
- **Why:** `config/application.local.yaml` is named in several remedies and does
  not exist in a clone — that is correct, and it must be the *only* kind of
  absence.

### CFG-146 · `__str__` renders code, message, next action and context
- **Area:** `core/errors.py::PramaError.__str__`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an error with context
- **Steps:** `str(exc)`
- **Expected:** `[CODE] message | Next: remedy | Context: k='v', ...` with the
  context sorted
- **Why:** the CLI prints `str(exc)` directly; the sort makes the output stable
  enough to assert.

### CFG-147 · `to_dict` carries exactly four keys
- **Area:** `core/errors.py::PramaError.to_dict`
- **Type:** contract
- **Priority:** P2
- **Precondition:** any error
- **Steps:** `to_dict()`
- **Expected:** `code`, `message`, `remedy`, `context`; nothing else, and no
  traceback
- **Why:** it is the API problem document; a stack trace leaking into it is an
  information disclosure.

### CFG-148 · `context` is copied, not aliased
- **Area:** `core/errors.py::PramaError.__init__`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a mutable dict passed as context
- **Steps:** mutate the caller's dict after raising
- **Expected:** the error is unchanged
- **Why:** `dict(context or {})` is the copy; an error whose context changes
  after it was raised cannot be trusted in a log.

### CFG-149 · `cause` is wired to `__cause__`
- **Area:** `core/errors.py::PramaError.__init__`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an error constructed with `cause=ValueError("x")`
- **Steps:** raise and inspect the traceback
- **Expected:** the chained cause is shown
- **Why:** every translated database and YAML error passes one; losing it makes
  the underlying failure invisible.

### CFG-150 · The subclass hierarchy is the documented one
- **Area:** `core/errors.py`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** check `issubclass` for each pair
- **Expected:** `ConfigMissingError`, `ConfigTypeError`, `SecretMissingError` are
  `ConfigError`; `SchemaDriftError` is a `DatabaseError`; `LeaseLostError` and
  `BackPressureError` are `ConcurrencyError`; all are `PramaError`
- **Why:** an API handler catching `ConfigError` must catch the secret failure
  too, and a rehomed class would silently change the HTTP status.

### CFG-151 · `UnauthorisedError` and `ForbiddenError` are not interchangeable
- **Area:** `core/errors.py`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** confirm neither subclasses the other
- **Expected:** siblings
- **Why:** the docstring draws the distinction — "we do not know who you are"
  versus "we know, and no" — and collapsing it changes what a client should do.

### CFG-152 · A code passed to the constructor overrides the class code
- **Area:** `core/errors.py::PramaError.__init__`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `ConfigError(..., code="CONFIG.YAML_INVALID")`
- **Steps:** read `exc.code`
- **Expected:** the instance code
- **Why:** most of the configuration codes are instance-level; a class default
  that won would collapse six distinct conditions into `CONFIG.INVALID`.

### CFG-153 · Every instance-level code in `src/` follows `AREA.CONDITION`
- **Area:** all of `src/prama/`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** extract every `code="..."` literal
- **Expected:** upper-case, one dot, no spaces; the area is one a reader would
  recognise
- **Why:** codes appear in support conversations; an inconsistent one is a code
  nobody can search for.

## Clock and time

### CFG-154 · `SystemClock.now()` is timezone-aware UTC
- **Area:** `core/clock.py::SystemClock.now`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the process running under `TZ=Asia/Kolkata`
- **Steps:** `SystemClock().now()`
- **Expected:** `tzinfo` is UTC, and the instant matches `datetime.now(UTC)`
- **Why:** "Every timestamp Prama records is UTC"; a local-time clock under a
  non-UTC `TZ` is the defect that only appears off the developer's machine.

### CFG-155 · `isoformat()` ends in `Z`, never `+00:00`
- **Area:** `core/clock.py::Clock.isoformat`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** `SystemClock().isoformat()`
- **Expected:** a trailing `Z`
- **Why:** the schema stores timestamps as text that must sort chronologically;
  mixing `Z` and `+00:00` forms breaks the ordering at the character level.

### CFG-156 · `epoch_millis` matches `now()`
- **Area:** `core/clock.py::Clock.epoch_millis`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a `FixedClock` at a known instant
- **Steps:** compare `epoch_millis()` with the instant's timestamp
- **Expected:** equal to the millisecond, truncating rather than rounding
- **Why:** ULID time ordering is derived from this; a rounding difference makes
  two ids mint out of order across a millisecond boundary.

### CFG-157 · `FixedClock` refuses a naive instant
- **Area:** `core/clock.py::FixedClock.__init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `datetime(2026, 1, 1)` with no tzinfo
- **Steps:** construct
- **Expected:** `ValueError`
- **Why:** a test clock that silently assumed local time would make every
  temporal test pass on one machine and fail on another.

### CFG-158 · `FixedClock` converts a non-UTC aware instant to UTC
- **Area:** `core/clock.py::FixedClock.__init__`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** an instant in `America/New_York`
- **Steps:** `now()`
- **Expected:** the same moment expressed in UTC
- **Why:** `astimezone(UTC)` is applied; the class must never hand back a
  non-UTC datetime.

### CFG-159 · `ManualClock.advance` moves wall clock and monotonic together
- **Area:** `core/clock.py::ManualClock.advance`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a `ManualClock`
- **Steps:** `advance(30)`, read both
- **Expected:** `now()` is 30s later and `monotonic()` is 30.0 higher
- **Why:** lease expiry is measured on one and renewal intervals on the other; a
  clock where they diverge tests nothing real.

### CFG-160 · `ManualClock.advance` refuses to go backwards
- **Area:** `core/clock.py::ManualClock.advance`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `advance(-1)`
- **Expected:** `ValueError` — "a clock does not run backwards"
- **Why:** a test that could rewind time would let a bug that depends on
  monotonicity pass.

### CFG-161 · `FixedClock.monotonic` never moves
- **Area:** `core/clock.py::FixedClock.monotonic`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** read twice
- **Expected:** `0.0` both times
- **Why:** any code that measures a duration against a `FixedClock` gets zero,
  which is the intended and testable behaviour.

### CFG-162 · `utc_now()` is the only ambient time source and is used sparingly
- **Area:** `core/clock.py::utc_now`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** count the call sites of `utc_now` and of `datetime.now` in `src/`
- **Expected:** no bare `datetime.now()` outside `core/clock.py`; every
  `utc_now()` is in a place with no injected clock
- **Why:** "Every use of this function is a small obstacle to deterministic
  replay, so it is deliberately unattractive to reach for."

### CFG-163 · A stored timestamp is exactly 27 or 28 characters
- **Area:** `db/types.py::UtcDateTime.process_bind_param`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an instant at microsecond `0` and one at `999999`
- **Steps:** bind both
- **Expected:** `timespec="microseconds"` gives a fixed-width form in both cases,
  within the `VARCHAR(32)` declared in the schema
- **Why:** a variable-width timestamp does not sort correctly as text, and the
  whole no-TIMESTAMP-type decision rests on it sorting.

### CFG-164 · ISO-8601 UTC text sorts chronologically
- **Area:** `db/types.py::UtcDateTime`, `schema/*.sql`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a table of timestamps spanning a year, inserted out of order
- **Steps:** `ORDER BY` the column on both engines
- **Expected:** chronological, identical on both
- **Why:** the schema header states this as the reason timestamps are
  `VARCHAR(32)`; the evidence ledger's `in_period` depends on it.

## Identifiers

### CFG-165 · A ULID is 26 Crockford base32 characters
- **Area:** `core/ids.py::UlidFactory.new`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** mint 1,000
- **Expected:** every one is 26 characters from `0123456789ABCDEFGHJKMNPQRSTVWXYZ`
- **Why:** `String(26)` is the declared column width on every primary key; a
  27-character id is a write that fails on PostgreSQL and silently truncates
  nowhere.

### CFG-166 · Ids minted in a tight loop are strictly increasing
- **Area:** `core/ids.py::UlidFactory.new`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** mint 100,000 in a loop, compare each to the previous
- **Expected:** strictly increasing as strings
- **Why:** "several stores rely on id order to page deterministically" — the
  evidence ledger reads in creation order without a secondary sort.

### CFG-167 · Ids are unique under concurrency
- **Area:** `core/ids.py::UlidFactory` (the lock)
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** none
- **Steps:** mint 100,000 from sixteen threads through the process-wide factory
- **Expected:** no duplicates
- **Why:** the lock is the only thing between a shared `_last_rand` and two rows
  claiming the same primary key.

### CFG-168 · Ids from concurrent threads are still monotonic in aggregate
- **Area:** `core/ids.py::UlidFactory.new`
- **Type:** concurrency
- **Priority:** P2
- **Precondition:** as above
- **Steps:** collect and sort by mint order
- **Expected:** sorted order matches mint order within each millisecond
- **Why:** the increment-rather-than-redraw design claims this; without it the
  ordering guarantee is only single-threaded.

### CFG-169 · A clock that steps backwards does not break monotonicity
- **Area:** `core/ids.py::UlidFactory.new`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a `ManualClock`-backed factory; mint, then construct a clock
  reading an earlier millisecond
- **Steps:** mint again
- **Expected:** the second id still sorts after the first
- **Why:** the `else` branch resets `_last_ms` to whatever the clock said, so a
  backwards step produces a smaller id. NTP steps backwards.

### CFG-170 · The random-overflow path emits a larger id
- **Area:** `core/ids.py::UlidFactory.new`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `_last_rand` forced to `(1 << 80) - 1` within one millisecond
- **Steps:** mint
- **Expected:** the id sorts after its predecessor
- **Why:** the comment claims the platform would "wait for the next millisecond
  rather than emit a non-monotonic id"; the code advances `ms` and redraws the
  random part, which is a different mechanism and must be shown to work.

### CFG-171 · `is_ulid` rejects near-misses
- **Area:** `core/ids.py::is_ulid`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** test a 25-character id, a 27-character id, one containing `I`, `L`,
  `O` or `U`, one lower-cased, and the empty string
- **Expected:** `False` for all
- **Why:** the four excluded letters are the whole point of Crockford base32;
  accepting a lower-case id would let two spellings of one identifier exist.

### CFG-172 · `ulid_timestamp_millis` round-trips the mint time
- **Area:** `core/ids.py::ulid_timestamp_millis`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a factory on a `FixedClock`
- **Steps:** mint, decode
- **Expected:** the clock's `epoch_millis()`
- **Why:** the recovered timestamp is what makes a ULID self-describing; an
  off-by-one in the shift loop would be invisible in ordering and wrong here.

### CFG-173 · `ulid_timestamp_millis` refuses a non-ULID
- **Area:** `core/ids.py::ulid_timestamp_millis`
- **Type:** negative
- **Priority:** P3
- **Precondition:** `"not-an-id"`
- **Steps:** call
- **Expected:** `ValueError` quoting the input
- **Why:** decoding garbage into a plausible epoch would date a record to 1970 or
  to the year 12000.

### CFG-174 · `EntityId.parse` accepts both the bare and qualified forms
- **Area:** `core/ids.py::EntityId.parse`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a valid ULID
- **Steps:** `TenantId.parse(ulid)` and `TenantId.parse(f"tenant:{ulid}")`
- **Expected:** both give the bare ULID
- **Why:** "the stored value is the bare ULID, so a prefix rename is never a data
  migration" — URLs carry the qualified form.

### CFG-175 · `EntityId.parse` does not check the prefix
- **Area:** `core/ids.py::EntityId.parse`
- **Type:** security
- **Priority:** P2
- **Precondition:** a valid ULID
- **Steps:** `TenantId.parse(f"user:{ulid}")`
- **Expected:** either a refusal naming the mismatch, or documented as
  deliberate
- **Why:** the class exists so that "passing a control id where a dataset id
  belongs is a type error rather than a runtime mystery"; accepting another
  type's qualified form defeats that at the parsing boundary.

### CFG-176 · Every typed id declares a distinct prefix
- **Area:** `core/ids.py`
- **Type:** contract
- **Priority:** P3
- **Precondition:** none
- **Steps:** collect `prefix` from `TenantId`, `PrincipalId`, `RoleId`,
  `ApiKeyId`, `AuditEventId`, `LeaseId`
- **Expected:** `tenant`, `user`, `role`, `key`, `audit`, `lease` — all distinct
- **Why:** a shared prefix makes the qualified form ambiguous in a URL.

## Structured concurrency

### CFG-177 · A queue with `max_bytes <= 0` is refused
- **Area:** `core/concurrency/bounded_queue.py::BoundedQueue.__init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** construct with `max_bytes=0` and `-1`
- **Expected:** `ValueError` — "an unbounded queue is not permitted"
- **Why:** CLAUDE.md forbids unbounded queues; zero is how one would be spelled.

### CFG-178 · The byte budget, not the item count, is what fills the queue
- **Area:** `core/concurrency/bounded_queue.py::_would_fit`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `max_bytes` sized for about three large items, `max_items=0`
- **Steps:** put four large items with a short timeout
- **Expected:** the fourth raises `BackPressureError`
- **Why:** "an item-bounded 'bounded' queue behaves like a leak under a payload
  change".

### CFG-179 · The item count is a secondary guard
- **Area:** `core/concurrency/bounded_queue.py::_would_fit`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `max_items=2`, a generous byte budget
- **Steps:** put three tiny items
- **Expected:** the third is refused
- **Why:** both bounds are advertised; a secondary guard that never fires is not
  a guard.

### CFG-180 · An item larger than the whole budget is accepted into an empty queue
- **Area:** `core/concurrency/bounded_queue.py::put`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `max_bytes=1024`, an item sized 4096
- **Steps:** put into an empty queue
- **Expected:** accepted; `stats().bytes` shows the overshoot
- **Why:** the docstring: "refusing it would strand the pipeline on one oversized
  record, which is a worse failure than a temporary overshoot that is visible in
  the stats".

### CFG-181 · An oversized item is refused when the queue is not empty
- **Area:** `core/concurrency/bounded_queue.py::_would_fit`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** one small item already queued
- **Steps:** put an item larger than the budget with a short timeout
- **Expected:** `BackPressureError`
- **Why:** the `and self._items` clause is what limits the escape hatch to the
  case where waiting could never help.

### CFG-182 · Back-pressure carries the numbers and an honest remedy
- **Area:** `core/concurrency/bounded_queue.py::put`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a full queue
- **Steps:** read the raised error
- **Expected:** context with `queue`, `bytes`, `max_bytes`, `items`; the remedy
  says widening "postpones the same problem with more memory held"
- **Why:** a remedy that only said "make it bigger" would teach the wrong lesson
  about a sink that is the bottleneck.

### CFG-183 · A producer parked on a full queue wakes when a consumer takes an item
- **Area:** `core/concurrency/bounded_queue.py::get`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** a full queue and a producer awaiting `put`
- **Steps:** `get()` once
- **Expected:** the producer completes well inside its timeout
- **Why:** `get` notifies `_not_full` with `notify_all`; a missed wake is a
  pipeline that stalls under exactly the load it was built for.

### CFG-184 · `try_put` wakes a consumer parked in `get`
- **Area:** `core/concurrency/bounded_queue.py::try_put`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a consumer awaiting `get(timeout=None)`
- **Steps:** `await try_put(item)`
- **Expected:** the consumer receives the item
- **Why:** finding X6 — `try_put` returned `True` and told nobody, so a consumer
  waited for ever while the item sat in the deque. Confirm the new test fails
  against the old code.

### CFG-185 · `try_put` wakes a consumer parked in `drain`
- **Area:** `core/concurrency/bounded_queue.py::try_put`, `drain`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a consumer awaiting `drain()`
- **Steps:** `await try_put(item)`
- **Expected:** the drain returns with one item
- **Why:** the same finding; `drain` is the batch path and the one a metric
  writer actually uses.

### CFG-186 · `try_put` on a full queue returns False and counts a rejection
- **Area:** `core/concurrency/bounded_queue.py::try_put`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a full queue
- **Steps:** `try_put`
- **Expected:** `False`, `stats().rejected` incremented, `offered` incremented
- **Why:** "'Non-blocking' is about back-pressure: this never waits for capacity,
  it refuses."

### CFG-187 · `resize` wakes every blocked producer
- **Area:** `core/concurrency/bounded_queue.py::resize`
- **Type:** regression
- **Priority:** P1
- **Precondition:** three producers parked on a full queue with a long timeout
- **Steps:** `resize(max_bytes=<much larger>)`
- **Expected:** all three complete promptly
- **Why:** finding X6 again — "widening a queue that nobody is told about is not
  widening it", and the parked producers used to take a `BackPressureError`
  against a queue with room in it.

### CFG-188 · Shrinking never discards queued items
- **Area:** `core/concurrency/bounded_queue.py::resize`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a queue holding four items
- **Steps:** `resize(max_bytes=1)`
- **Expected:** `len()` is still four; new puts are refused
- **Why:** an operator narrowing a queue must not lose in-flight work.

### CFG-189 · `resize` to a non-positive budget is refused
- **Area:** `core/concurrency/bounded_queue.py::resize`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a live queue
- **Steps:** `resize(max_bytes=0)`
- **Expected:** `ValueError`; the existing budget is unchanged
- **Why:** the constructor's invariant must not be defeatable at runtime.

### CFG-190 · `close` wakes every waiter on both conditions
- **Area:** `core/concurrency/bounded_queue.py::close`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** one producer parked on full, one consumer parked on empty
- **Steps:** `close()`
- **Expected:** the producer raises "queue is closed", the consumer raises
  "closed and drained"; neither hangs
- **Why:** a shutdown that leaves a task parked for ever is what the supervisor's
  grace period then has to kill.

### CFG-191 · A consumer drains what is queued before seeing the close
- **Area:** `core/concurrency/bounded_queue.py::get`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** two items queued, then `close()`
- **Steps:** `get()` twice, then a third time
- **Expected:** both items, then the closed-and-drained refusal
- **Why:** the guard is `if not self._items and self._closed` — closing must not
  discard accepted work.

### CFG-192 · `drain(max_items=n)` takes at most n
- **Area:** `core/concurrency/bounded_queue.py::drain`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** ten items queued
- **Steps:** `drain(max_items=3)`
- **Expected:** three items; `byte_size` reduced by exactly their sizes
- **Why:** a byte accounting that drifts makes the budget meaningless after the
  first partial drain.

### CFG-193 · `drain()` with no limit takes everything in one wake-up
- **Area:** `core/concurrency/bounded_queue.py::drain`
- **Type:** performance
- **Priority:** P3
- **Precondition:** a thousand items
- **Steps:** `drain()`
- **Expected:** one call returns all thousand; `byte_size` is zero
- **Why:** "draining once per wake-up is far cheaper than a `get` per item".

### CFG-194 · `default_sizer` charges the per-item overhead
- **Area:** `core/concurrency/bounded_queue.py::default_sizer`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** size an empty tuple, a small dict, a 1 MB `bytes`
- **Expected:** every result is at least `ITEM_OVERHEAD_BYTES`; the 1 MB case is
  at least 1 MB
- **Why:** "Charging it stops a flood of tiny items from appearing free."

### CFG-195 · `default_sizer` survives an object `getsizeof` cannot measure
- **Area:** `core/concurrency/bounded_queue.py::default_sizer`
- **Type:** negative
- **Priority:** P3
- **Precondition:** an object whose `__sizeof__` raises `TypeError`
- **Steps:** size it
- **Expected:** `ITEM_OVERHEAD_BYTES`, no exception
- **Why:** a sizer that raised would take down the producer rather than the item.

### CFG-196 · `QueueStats.utilisation` is bounded to 1.0
- **Area:** `core/concurrency/bounded_queue.py::QueueStats.utilisation`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** an oversized item accepted into an empty queue
- **Steps:** read `utilisation`
- **Expected:** exactly `1.0`, never above
- **Why:** a gauge exported to Prometheus above 1.0 breaks every alert rule
  written against it as a fraction.

### CFG-197 · High-water marks never fall
- **Area:** `core/concurrency/bounded_queue.py`
- **Type:** functional
- **Priority:** P3
- **Precondition:** fill then drain a queue
- **Steps:** read `high_water_items` and `high_water_bytes`
- **Expected:** both retain the peak
- **Why:** they are the only evidence after the fact that the queue was ever
  near its bound.

### CFG-198 · `stats()` returns a snapshot, not a live view
- **Area:** `core/concurrency/bounded_queue.py::stats`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a queue with items
- **Steps:** take stats, drain, re-read the first snapshot
- **Expected:** unchanged
- **Why:** `dataclasses.replace` is the copy; a live view makes an exported
  metric race with the queue.

### CFG-199 · A supervisor cancels and awaits every child on exit
- **Area:** `core/concurrency/supervisor.py::TaskSupervisor.__aexit__`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** two long-running spawned tasks
- **Steps:** leave the `async with` block
- **Expected:** both tasks are done; `handle.stopped` is true for each
- **Why:** "a task cannot outlive the scope that created it".

### CFG-200 · Spawning a duplicate running name is refused
- **Area:** `core/concurrency/supervisor.py::TaskSupervisor.spawn`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a task named `dispatch` already running
- **Steps:** `spawn("dispatch", ...)`
- **Expected:** `ConcurrencyError` `CONCURRENCY.INVARIANT` naming the supervisor
  and the task
- **Why:** two dispatch loops under one name is exactly the duplicate-work
  failure the lease machinery exists to prevent, arriving from inside.

### CFG-201 · Re-spawning a *stopped* name is allowed
- **Area:** `core/concurrency/supervisor.py::TaskSupervisor.spawn`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a `NEVER` task that has completed
- **Steps:** spawn the same name again
- **Expected:** accepted
- **Why:** the guard is on `running`, not on presence; a restartable one-shot is
  a normal thing to want.

### CFG-202 · `RestartPolicy.NEVER` surfaces a failure rather than restarting
- **Area:** `core/concurrency/supervisor.py::_run`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a one-shot task that raises
- **Steps:** await it, then `failures()`
- **Expected:** one recorded failure, no restart, an error log naming the task
- **Why:** the alternative is the silent-failure mode the module opens by
  describing.

### CFG-203 · `ON_FAILURE` restarts with backoff and gives up after `max_restarts`
- **Area:** `core/concurrency/supervisor.py::_run`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a task that always raises, `max_restarts=3`,
  `restart_window=60`
- **Steps:** run
- **Expected:** exactly four attempts, then a `ConcurrencyError` recorded whose
  remedy says a crash loop is a defect, not a transient
- **Why:** "a crash loop is eventually reported rather than hidden by infinite
  retrying".

### CFG-204 · The restart window resets
- **Area:** `core/concurrency/supervisor.py::_run`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a `ManualClock`; failures spaced beyond `restart_window`
- **Steps:** advance the clock between failures
- **Expected:** the task is never given up on
- **Why:** an occasional transient over months must not accumulate into a
  permanent stop.

### CFG-205 · `ALWAYS` restarts a task that returns cleanly
- **Area:** `core/concurrency/supervisor.py::_run`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a poller that returns immediately
- **Steps:** spawn with `ALWAYS`, wait
- **Expected:** it runs repeatedly, incrementing `restarts`
- **Why:** "a poller that is expected to return" is the documented use; a clean
  return that stopped the loop would silently stop the polling.

### CFG-206 · Backoff is jittered and bounded
- **Area:** `core/concurrency/supervisor.py::_backoff`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `base_backoff=0.2`, `max_backoff=30`
- **Steps:** sample `_backoff(1..20)` many times
- **Expected:** every value in `[0, min(30, 0.2 * 2**min(n,16))]`; the
  distribution is not constant
- **Why:** "full jitter — avoids a synchronised retry storm"; a fixed backoff
  makes a fleet retry in lockstep.

### CFG-207 · Cancellation is not treated as a failure
- **Area:** `core/concurrency/supervisor.py::_run`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** an `ON_FAILURE` task cancelled during shutdown
- **Steps:** `shutdown()`, then `failures()`
- **Expected:** empty
- **Why:** `CancelledError` is re-raised before the `except Exception`; treating
  a clean shutdown as a crash would make `healthy()` false after every stop.

### CFG-208 · `healthy()` is false once anything has failed
- **Area:** `core/concurrency/supervisor.py::healthy`
- **Type:** functional
- **Priority:** P2
- **Precondition:** one `NEVER` task that raised
- **Steps:** `healthy()`
- **Expected:** `False`
- **Why:** it is what a health endpoint reads; a supervisor that reports healthy
  with a dead worker is the failure this package exists to prevent.

### CFG-209 · `raise_for_failures` re-raises the first failure
- **Area:** `core/concurrency/supervisor.py::raise_for_failures`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two recorded failures
- **Steps:** call
- **Expected:** the first is raised, with its original type and remedy
- **Why:** a wrapped or stringified failure loses the taxonomy at exactly the
  boundary that reports it.

### CFG-210 · `shutdown` is safe to call twice
- **Area:** `core/concurrency/supervisor.py::shutdown`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a supervisor already shut down
- **Steps:** `shutdown()` again
- **Expected:** returns immediately, no exception, no duplicate failures recorded
- **Why:** `__aexit__` calls it, and an explicit call in a `finally` is the
  natural thing for a caller to write as well.

### CFG-211 · `run_sync` works with no running loop
- **Area:** `core/concurrency/supervisor.py::run_sync`
- **Type:** functional
- **Priority:** P1
- **Precondition:** synchronous context
- **Steps:** `run_sync(coro)`
- **Expected:** the coroutine's result; no thread created
- **Why:** the CLI path.

### CFG-212 · `run_sync` works from inside a running loop
- **Area:** `core/concurrency/supervisor.py::run_sync`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** called from inside a coroutine
- **Steps:** `run_sync(coro)`
- **Expected:** the result, obtained on a worker thread; no "cannot be called
  from a running event loop"
- **Why:** the docstring: `asyncio.run` "is correct when nothing is running and
  fatal when something is … which is the worst place to find out".

### CFG-213 · `run_sync` propagates an exception rather than swallowing it
- **Area:** `core/concurrency/supervisor.py::run_sync`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a coroutine that raises a `PramaError`, both loop states
- **Steps:** call
- **Expected:** the same error, with its code and remedy, in both cases
- **Why:** a `concurrent.futures` wrapper is the classic place a typed error
  becomes a generic one.

### CFG-214 · `MemoryLeaseProvider` grants only one holder at a time
- **Area:** `core/concurrency/leases.py::MemoryLeaseProvider.acquire`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** a live lease held by A
- **Steps:** B acquires the same resource
- **Expected:** `None`
- **Why:** "Implementations must make `acquire` atomic with respect to other
  holders" — the whole contract.

### CFG-215 · The same holder re-acquiring gets a new fencing token
- **Area:** `core/concurrency/leases.py::MemoryLeaseProvider.acquire`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** A holds the lease
- **Steps:** A acquires again
- **Expected:** granted, `fencing_token` incremented
- **Why:** the token "increases strictly with every acquisition of the same
  resource across the fleet" — including reacquisition by the same holder.

### CFG-216 · An expired lease is takeable
- **Area:** `core/concurrency/leases.py::MemoryLeaseProvider.acquire`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a `ManualClock`, A's lease expired
- **Steps:** B acquires
- **Expected:** granted with a higher fencing token
- **Why:** "A holder that dies stops renewing and the lease expires. No operator
  has to clear a stale lock."

### CFG-217 · Renewing a lost lease returns None
- **Area:** `core/concurrency/leases.py::MemoryLeaseProvider.renew`
- **Type:** negative
- **Priority:** P1
- **Precondition:** A's lease taken over by B
- **Steps:** A renews
- **Expected:** `None`
- **Why:** the second half of the contract — "must reject `renew`/`release` from
  a holder that no longer owns the resource".

### CFG-218 · Releasing a lease somebody else holds returns False
- **Area:** `core/concurrency/leases.py::MemoryLeaseProvider.release`
- **Type:** negative
- **Priority:** P1
- **Precondition:** as above
- **Steps:** A releases
- **Expected:** `False`; B's lease is untouched
- **Why:** a release that matched on resource alone would let a stalled holder
  free a live lease.

### CFG-219 · `inspect` hides an expired lease
- **Area:** `core/concurrency/leases.py::MemoryLeaseProvider.inspect`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an expired lease still in the map
- **Steps:** `inspect`
- **Expected:** `None`
- **Why:** health output showing a holder that no longer holds anything sends an
  operator to the wrong process.

### CFG-220 · The renewer loop renews before the TTL elapses
- **Area:** `core/concurrency/leases.py::LeaseHolder._renew_loop`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** ttl 0.3s, renew interval 0.1s
- **Steps:** hold for a second, checking `valid` throughout
- **Expected:** never lost
- **Why:** a holder that loses its own lease while healthy is a scheduler that
  stops dispatching for no reason.

### CFG-221 · A lost lease sets `_lost`, logs, and stops renewing
- **Area:** `core/concurrency/leases.py::LeaseHolder._renew_loop`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** the provider made to return `None` from `renew`
- **Steps:** wait one interval
- **Expected:** `valid` is false, `wait_until_lost()` completes, an error log
  says work under it must stop
- **Why:** "so it can abandon work it can no longer claim to own".

### CFG-222 · `raise_if_lost` raises once the lease has expired by the clock
- **Area:** `core/concurrency/leases.py::LeaseHolder.raise_if_lost`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a `ManualClock` advanced past expiry, renewer suppressed
- **Steps:** `raise_if_lost()`
- **Expected:** `LeaseLostError` with the "abandon the work" remedy
- **Why:** a holder that only learns of loss from its renewer is blind during a
  GC pause, which is the case the design names.

### CFG-223 · `fencing_token` with no lease raises rather than returning zero
- **Area:** `core/concurrency/leases.py::LeaseHolder.fencing_token`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a holder that never acquired
- **Steps:** read the property
- **Expected:** `LeaseLostError`
- **Why:** a zero token presented to a downstream store would be accepted as
  older than everything and rejected, or worse, accepted as valid.

### CFG-224 · Entering the context manager when another holder owns it refuses
- **Area:** `core/concurrency/leases.py::LeaseHolder.__aenter__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** the lease held elsewhere
- **Steps:** `async with provider.hold(...)`
- **Expected:** `LeaseLostError` whose remedy says this is normal in a fleet and
  points at `acquire(wait=True)`
- **Why:** the remedy has to prevent an operator treating a normal condition as
  an incident.

### CFG-225 · Leaving the block releases immediately
- **Area:** `core/concurrency/leases.py::LeaseHolder.release`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a 30s TTL
- **Steps:** enter and leave the block, then have another holder acquire
- **Expected:** the second acquires in milliseconds, not after 30 seconds
- **Why:** "a graceful shutdown hands over in milliseconds instead of after a
  TTL".

### CFG-226 · `release` cancels the renewer and is idempotent
- **Area:** `core/concurrency/leases.py::LeaseHolder.release`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a held lease
- **Steps:** `release()` twice
- **Expected:** no exception; no orphaned renewer task remains
- **Why:** a surviving renewer task would keep a released lease alive and is
  exactly the fire-and-forget task the package forbids.

### CFG-227 · `acquire(wait=True)` queues for a busy lease
- **Area:** `core/concurrency/leases.py::LeaseHolder.acquire`
- **Type:** concurrency
- **Priority:** P2
- **Precondition:** the lease held and released after a moment
- **Steps:** `acquire(wait=True, poll_interval=0.05)`
- **Expected:** returns `True` shortly after the release
- **Why:** the documented alternative in the refusal remedy must work.

### CFG-228 · `ConcurrencyLimiter` admits at most `limit` at once
- **Area:** `core/concurrency/limits.py::ConcurrencyLimiter`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** `limit=3`, ten concurrent holders
- **Steps:** track `in_flight` throughout
- **Expected:** never above three; `high_water` is three
- **Why:** "NFR-PRF-013 caps Prama-attributable load at a configured fraction of
  source capacity".

### CFG-229 · A limiter with a non-positive limit is refused
- **Area:** `core/concurrency/limits.py::ConcurrencyLimiter.__init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** construct with 0
- **Expected:** `ValueError`
- **Why:** zero would deadlock the first caller for ever.

### CFG-230 · A limiter timeout raises back-pressure naming the limiter
- **Area:** `core/concurrency/limits.py::ConcurrencyLimiter._enter`
- **Type:** negative
- **Priority:** P2
- **Precondition:** the limit fully held
- **Steps:** `acquire(timeout=0.05)`
- **Expected:** `BackPressureError` with `limiter` and `limit` in the context
- **Why:** the remedy explains the limiter exists "to keep Prama inside its
  agreed share of the source", which is what stops an operator raising it
  reflexively.

### CFG-231 · A slot is released even when the body raises
- **Area:** `core/concurrency/limits.py::_LimiterContext.__aexit__`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `limit=1`
- **Steps:** raise inside the block, then acquire again
- **Expected:** the second acquire succeeds
- **Why:** a leaked slot narrows the limiter permanently and looks like a slow
  source.

### CFG-232 · `in_flight` returns to zero after every holder exits
- **Area:** `core/concurrency/limits.py::ConcurrencyLimiter._exit`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** many acquire/release cycles including failures
- **Steps:** read `in_flight`
- **Expected:** zero, never negative
- **Why:** the counter is decremented outside the semaphore; a double exit would
  drive it negative and misreport the cap.

### CFG-233 · `RateLimiter` bursts to capacity then paces at the rate
- **Area:** `core/concurrency/limits.py::RateLimiter`
- **Type:** performance
- **Priority:** P2
- **Precondition:** rate 10/s, capacity 10, a `ManualClock`
- **Steps:** acquire ten immediately, then an eleventh
- **Expected:** the first ten are instant; the eleventh waits about 0.1s
- **Why:** "a fixed window permits the whole quota in the first millisecond of
  every window — the pattern that trips a DBA's alerting".

### CFG-234 · Requesting more permits than the capacity is refused immediately
- **Area:** `core/concurrency/limits.py::RateLimiter.acquire`
- **Type:** negative
- **Priority:** P2
- **Precondition:** capacity 10
- **Steps:** `acquire(11)`
- **Expected:** `ValueError` naming both numbers
- **Why:** it would otherwise wait for ever for a bucket that can never hold
  enough.

### CFG-235 · A rate limiter timeout is back-pressure, not a silent wait
- **Area:** `core/concurrency/limits.py::RateLimiter.acquire`
- **Type:** negative
- **Priority:** P2
- **Precondition:** an empty bucket, rate 1/s
- **Steps:** `acquire(1, timeout=0.1)`
- **Expected:** `BackPressureError` stating the required and budgeted times
- **Why:** the caller needs to be able to shed load rather than queue for ever.

### CFG-236 · `try_acquire` never waits
- **Area:** `core/concurrency/limits.py::RateLimiter.try_acquire`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** an empty bucket
- **Steps:** `try_acquire()`
- **Expected:** `False` immediately; `available` unchanged
- **Why:** a non-blocking path that consumed a partial permit would leak the
  budget.

### CFG-237 · `available` never exceeds capacity however long the bucket idles
- **Area:** `core/concurrency/limits.py::_refill`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a `ManualClock` advanced by an hour
- **Steps:** read `available`
- **Expected:** exactly the capacity
- **Why:** an unbounded refill turns the limiter into a burst of thousands
  against a source that has just come back.

### CFG-238 · A backwards monotonic reading does not mint permits
- **Area:** `core/concurrency/limits.py::_refill`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a clock whose `monotonic` decreases
- **Steps:** refill
- **Expected:** no change — `max(0.0, now - updated)` is the guard
- **Why:** the guard exists; the test is what keeps it there.

### CFG-239 · `DedicatedThread` runs every call on one thread
- **Area:** `core/concurrency/affinity.py::DedicatedThread.call`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** a worker
- **Steps:** call `threading.get_ident` twenty times
- **Expected:** the same id every time, and not the caller's
- **Why:** the whole point — a thread-bound library "must be used from the thread
  that initialised it, and using them from another does not raise — it
  deadlocks".

### CFG-240 · `call` accepts keyword arguments
- **Area:** `core/concurrency/affinity.py::DedicatedThread.call`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a function taking `account=`
- **Steps:** `await worker.call(fn, account="x")`
- **Expected:** the keyword arrives
- **Why:** the docstring records the defect — Snowflake's `open()` raised
  "unexpected keyword argument 'account'", blaming the concurrency primitive for
  a connector bug.

### CFG-241 · `close` runs the teardown on the worker's own thread
- **Area:** `core/concurrency/affinity.py::DedicatedThread.close`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** a teardown that records `threading.get_ident`
- **Steps:** close with the teardown
- **Expected:** the recorded id is the worker's
- **Why:** "a library finalised from the wrong thread fails at interpreter exit,
  a long way from anything explanatory".

### CFG-242 · `close` is idempotent
- **Area:** `core/concurrency/affinity.py::DedicatedThread.close`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a closed worker
- **Steps:** `close()` again, with a teardown
- **Expected:** returns immediately; the teardown is not run a second time
- **Why:** the docstring says idempotent, and a double teardown on a JVM detach
  is a crash.

### CFG-243 · Calling a closed worker refuses with a code
- **Area:** `core/concurrency/affinity.py::DedicatedThread.call`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a closed worker
- **Steps:** `call(fn)`
- **Expected:** `PramaError` `CONCURRENCY.WORKER_CLOSED`, remedy saying a closed
  worker cannot be reopened
- **Why:** the alternative is `run_in_executor(None, ...)` on the default
  executor, which would silently run on the wrong thread.

### CFG-244 · The worker thread is named
- **Area:** `core/concurrency/affinity.py::DedicatedThread.__init__`
- **Type:** functional
- **Priority:** P3
- **Precondition:** a worker named `jdbc`
- **Steps:** inspect thread names
- **Expected:** the prefix appears
- **Why:** a stack dump with `ThreadPoolExecutor-3_0` in it tells an operator
  nothing about which resource is stuck.

### CFG-245 · No bare `threading.Thread` or `create_task` outside the package
- **Area:** all of `src/prama/`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** scan for `threading.Thread(`, `asyncio.create_task(`,
  `ThreadPoolExecutor(` and `asyncio.Queue(` outside `core/concurrency/`
- **Expected:** none, or each an explicitly documented exception
- **Why:** CLAUDE.md: "No bare `threading.Thread`, no unbounded queue, no
  fire-and-forget task." `tests/architecture/test_layering.py` does not check it.

## The plugin registry

### CFG-246 · A plugin without a manifest cannot be registered
- **Area:** `core/registry.py::Registry._validate`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a subclass that does not implement `manifest`
- **Steps:** `register`
- **Expected:** refused — the ABC makes it uninstantiable and the registry names
  the class
- **Why:** "A plugin that does not declare one is not loadable, because an
  undeclared capability is the thing the compiler would otherwise have to guess
  at."

### CFG-247 · A `manifest()` that raises is refused with the exception type named
- **Area:** `core/registry.py::Registry._validate`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a plugin whose `manifest` raises
- **Steps:** `register`
- **Expected:** `RegistryError` naming the class and the exception type, remedy
  "manifest() must be a pure classmethod returning a PluginManifest"
- **Why:** a manifest with side effects is a plugin that behaves differently
  depending on when it was first listed.

### CFG-248 · A `manifest()` returning the wrong type is refused
- **Area:** `core/registry.py::Registry._validate`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a plugin returning a dict
- **Steps:** `register`
- **Expected:** `RegistryError` naming the class
- **Why:** a duck-typed manifest would fail later inside the compiler with no
  attribution.

### CFG-249 · An empty plugin key is refused
- **Area:** `core/registry.py::Registry._validate`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `key=""`
- **Steps:** `register`
- **Expected:** refused — "Give the plugin a stable, unique key."
- **Why:** an empty key is unaddressable and would collide with the next one.

### CFG-250 · A manifest declaring the wrong kind is refused
- **Area:** `core/registry.py::Registry._validate`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a connector registered in the notifier registry
- **Steps:** `register`
- **Expected:** `RegistryError` naming both kinds
- **Why:** a plugin in the wrong registry is resolved by a caller expecting a
  different interface, which fails at first use deep inside an execution.

### CFG-251 · A class that does not subclass the base is refused
- **Area:** `core/registry.py::Registry._validate`
- **Type:** negative
- **Priority:** P1
- **Precondition:** an unrelated class
- **Steps:** `register`
- **Expected:** refused, remedy naming the base class
- **Why:** "Everything is a class with an interface" is a CLAUDE.md rule, and
  this is where it is enforced.

### CFG-252 · A duplicate key is refused unless `replace=True`
- **Area:** `core/registry.py::Registry.register`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a key already registered
- **Steps:** register again, with and without `replace`
- **Expected:** refused, then accepted
- **Why:** silent replacement means an installed package can shadow a
  first-party connector with nothing in the log.

### CFG-253 · `get` on an unknown key lists what is available
- **Area:** `core/registry.py::Registry.get`
- **Type:** negative
- **Priority:** P1
- **Precondition:** three registered plugins
- **Steps:** `get("nope")`
- **Expected:** `RegistryError` whose remedy lists the three sorted keys and says
  to install the package providing it
- **Why:** "Available: ..." is the only thing that turns a typo into a two-second
  fix.

### CFG-254 · `get` on an empty registry says `(none)`
- **Area:** `core/registry.py::Registry.get`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** nothing registered
- **Steps:** `get("x")`
- **Expected:** remedy containing `(none)`, not `Available: .`
- **Why:** an empty list rendered as nothing reads as a formatting bug and
  distracts from the real cause.

### CFG-255 · A disabled plugin is refused with a distinct message
- **Area:** `core/registry.py::Registry.get`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a registered plugin, then `disable([key])`
- **Steps:** `get(key)`
- **Expected:** the "has been disabled" refusal, not the "no plugin registered"
  one, and the remedy says disabling is in code rather than configuration
- **Why:** the two causes need different actions, and the remedy is honest that
  `plugins.disabled` in the YAML is not what did it.

### CFG-256 · `plugins.disabled` in configuration is either wired up or not documented
- **Area:** `config/application.yaml`, `core/registry.py::Registry.disable`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** `plugins.disabled: ["x"]`
- **Steps:** register `x`, build the catalogue as the application does, `get("x")`
- **Expected:** either the plugin is disabled, or the configuration key is
  removed from the tracked file
- **Why:** the refusal's own remedy says "a disabled plugin is disabled in code,
  not in configuration", while the shipped file offers a key that says otherwise.

### CFG-257 · A disabled plugin disappears from `keys`, `__contains__` and `__len__`
- **Area:** `core/registry.py`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two registered, one disabled
- **Steps:** read all three
- **Expected:** one key, `in` is false for the disabled one, length one
- **Why:** a listing that shows a plugin `get` will refuse is a listing that
  wastes somebody's afternoon.

### CFG-258 · `manifests()` on a registry with a disabled plugin does not raise
- **Area:** `core/registry.py::Registry.manifests`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** as above
- **Steps:** `manifests()`
- **Expected:** the enabled manifest only
- **Why:** it iterates `keys()` and indexes `_plugins` directly, so the disabled
  entry is skipped rather than raising — confirm.

### CFG-259 · A broken entry point is logged and skipped, not fatal
- **Area:** `core/registry.py::Registry.discover`
- **Type:** negative
- **Priority:** P1
- **Precondition:** an entry point whose module raises on import
- **Steps:** `discover()`
- **Expected:** a warning naming the entry point and the group; the process
  continues; other plugins still load
- **Why:** "one broken third-party connector must not prevent the platform from
  starting".

### CFG-260 · A broken plugin is visible in health output
- **Area:** `core/registry.py::Registry.discover`
- **Type:** functional
- **Priority:** P2
- **Precondition:** as above
- **Steps:** read the health endpoint
- **Expected:** the failure is reported somewhere an operator sees it
- **Why:** the docstring promises "the failure is visible in health output"; a
  warning in a log nobody reads is not that. Confirm the claim is kept.

### CFG-261 · `discover` on a registry with no group returns zero
- **Area:** `core/registry.py::Registry.discover`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a registry built without `entry_point_group`
- **Steps:** `discover()`
- **Expected:** `0`, no exception
- **Why:** first-party-only registries exist and must not fail at start-up.

### CFG-262 · `_entry_points_for` swallowing every exception is bounded
- **Area:** `core/registry.py::_entry_points_for`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a corrupted distribution metadata directory
- **Steps:** `discover()`
- **Expected:** the failure to *enumerate* is reported, not silently turned into
  "no plugins found"
- **Why:** CLAUDE.md: "No exception is swallowed." A bare `except Exception:
  return []` makes a broken installation indistinguishable from an empty one.

### CFG-263 · `with_capability` finds only declaring plugins
- **Area:** `core/registry.py::Registry.with_capability`
- **Type:** functional
- **Priority:** P2
- **Precondition:** one plugin declaring `pushdown.sql`, one not
- **Steps:** `with_capability("pushdown.sql")`
- **Expected:** exactly one manifest
- **Why:** "The compiler consults capabilities; it never guesses and never
  probes."

### CFG-264 · `Capability.__str__` renders attributes deterministically
- **Area:** `core/registry.py::Capability.__str__`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a capability with two attributes inserted in each order
- **Steps:** render both
- **Expected:** identical, sorted text
- **Why:** capability strings feed plan ids; an insertion-order-dependent
  rendering is a plan id that changes for no reason.

### CFG-265 · `manifest.attribute` falls back cleanly
- **Area:** `core/registry.py::PluginManifest.attribute`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a manifest without the capability, and one with the
  capability but not the attribute
- **Steps:** read with a default
- **Expected:** the default in both cases
- **Why:** the compiler reads these to decide pushdown; a `KeyError` here is a
  compile failure with no explanation.

### CFG-266 · `verification` defaults to the weaker claim
- **Area:** `core/registry.py::PluginManifest.verification`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a manifest that does not set it
- **Steps:** read it
- **Expected:** `"code_complete"`
- **Why:** "a plugin that does not say is treated as unproven, because the safe
  default is the weaker claim".

### CFG-267 · `RegistryCatalogue.create` refuses a duplicate kind
- **Area:** `core/registry.py::RegistryCatalogue.create`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a catalogue with `connectors`
- **Steps:** `create("connectors", ...)`
- **Expected:** refused, remedy pointing at `of(kind)`
- **Why:** a second registry for one kind means two sets of plugins and a
  coin-flip about which the resolver uses.

### CFG-268 · `of` on an unknown kind lists the known ones
- **Area:** `core/registry.py::RegistryCatalogue.of`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a catalogue with three kinds
- **Steps:** `of("nope")`
- **Expected:** `RegistryError` whose remedy names the three
- **Why:** the same "Available:" discipline as `get`.

### CFG-269 · `discover_all` filtered by group only touches matching registries
- **Area:** `core/registry.py::RegistryCatalogue.discover_all`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** three registries, two groups requested
- **Steps:** `discover_all(groups=[...])`
- **Expected:** counts for exactly the two; the third is untouched
- **Why:** it reaches into `registry._group`, a private attribute — confirm the
  filter is by group and not by kind, which is what a caller would assume.

### CFG-270 · Two catalogues are independent
- **Area:** `core/registry.py::RegistryCatalogue`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two catalogues, a plugin registered in one
- **Steps:** resolve it in the other
- **Expected:** refused
- **Why:** "Held as a single object rather than module globals so that a test can
  build an isolated catalogue" — module state would make tests order-dependent.

## pjson

### CFG-271 · The backend is chosen once at import
- **Area:** `core/pjson.py::HAVE_ORJSON`, `BACKEND`
- **Type:** contract
- **Priority:** P2
- **Precondition:** both with and without `orjson` installed
- **Steps:** read `BACKEND`
- **Expected:** `orjson` or `stdlib`, constant for the process
- **Why:** "chosen at import time, never at call time, so the decision does not
  cost anything per call and never varies within a process".

### CFG-272 · Both backends produce identical canonical bytes
- **Area:** `core/pjson.py::canonical`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a structure with nested dicts, lists, floats, datetimes and
  Decimals
- **Steps:** encode under each backend
- **Expected:** byte-identical
- **Why:** "the evidence ledger's hash chain depends on it" — a machine with
  orjson and one without must produce the same record hash.

### CFG-273 · A naive datetime is refused by both backends with the same message
- **Area:** `core/pjson.py::_sanitise`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a naive datetime nested two levels deep
- **Steps:** `dumps`
- **Expected:** `TypeError` saying "refusing to serialise a naive datetime;
  attach UTC" on both
- **Why:** the `_sanitise` pass exists because "orjson rewrites the message of
  any exception raised inside `default`", turning a precise complaint into a
  generic one on some machines.

### CFG-274 · An aware datetime serialises to a `Z` form on both backends
- **Area:** `core/pjson.py::_default`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an instant in `America/New_York`
- **Steps:** `dumps`
- **Expected:** the UTC instant with a trailing `Z`, not `+00:00`, on both
- **Why:** `OPT_PASSTHROUGH_DATETIME` is what forces orjson through `_default`;
  without it the two backends emit different text for the same instant.

### CFG-275 · Non-finite floats become null
- **Area:** `core/pjson.py::_sanitise`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `{"a": float("nan"), "b": float("inf"), "c": float("-inf")}`
- **Steps:** `dumps`
- **Expected:** all three `null`, on both backends
- **Why:** "emitting them produces documents that some parsers accept and others
  reject — the worst possible outcome for an evidence record".

### CFG-276 · A non-finite float inside a nested list is sanitised
- **Area:** `core/pjson.py::_sanitise`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `{"m": {"x": [1.0, float("nan")]}}`
- **Steps:** `dumps`
- **Expected:** `null` in place
- **Why:** a metrics document is exactly this shape and a NaN rate is exactly
  what a division by zero produces.

### CFG-277 · A `Decimal` serialises as a string, never a float
- **Area:** `core/pjson.py::_default`
- **Type:** contract
- **Priority:** P1
- **Precondition:** `Decimal("0.1")`
- **Steps:** `dumps`
- **Expected:** `"0.1"`
- **Why:** "never `float()`: Decimal exists precisely to avoid that" — a monetary
  amount rounded into binary floating point in an evidence record is
  unrecoverable.

### CFG-278 · Sets and tuples become lists
- **Area:** `core/pjson.py::_default`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a set and a tuple
- **Steps:** `dumps`
- **Expected:** JSON arrays; note that a set's order is not stable, so a set
  inside a canonical document is a hash that varies
- **Why:** `canonical` claims that equal structures produce identical bytes; a
  set defeats it, and whether that is acceptable must be decided rather than
  discovered.

### CFG-279 · Bytes decode with replacement rather than raising
- **Area:** `core/pjson.py::_default`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** invalid UTF-8 bytes
- **Steps:** `dumps`
- **Expected:** a string with replacement characters, no exception
- **Why:** an evidence record must be writable even when a source returned
  something undecodable; the replacement is visible and the crash is not.

### CFG-280 · An unserialisable type is refused by name
- **Area:** `core/pjson.py::_default`
- **Type:** negative
- **Priority:** P2
- **Precondition:** an arbitrary object
- **Steps:** `dumps`
- **Expected:** `TypeError` naming the type
- **Why:** "cannot serialise X to JSON" is actionable; orjson's own message is
  not.

### CFG-281 · `canonical` is order-independent
- **Area:** `core/pjson.py::canonical`
- **Type:** contract
- **Priority:** P1
- **Precondition:** two dicts with the same pairs inserted in different orders
- **Steps:** `canonical` both
- **Expected:** identical bytes
- **Why:** "a hash that depends on dict insertion order is not a hash of the
  content".

### CFG-282 · `canonical` sorts nested keys too
- **Area:** `core/pjson.py::canonical`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** differing insertion order three levels down
- **Steps:** compare
- **Expected:** identical
- **Why:** `OPT_SORT_KEYS` and `sort_keys=True` both recurse; the evidence
  content document is nested.

### CFG-283 · `dumps` without `indent` emits no insignificant whitespace
- **Area:** `core/pjson.py::dumpb`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a small mapping
- **Steps:** `dumps`
- **Expected:** `{"a":1}` on both backends — the stdlib path passes
  `separators=(",", ":")`
- **Why:** a space difference between backends is a hash difference.

### CFG-284 · `loads` round-trips what `dumps` wrote
- **Area:** `core/pjson.py::loads`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a nested structure of the supported types
- **Steps:** `loads(dumps(x))`
- **Expected:** equal, allowing for the documented coercions
- **Why:** `JsonText` in the ORM writes with one and reads with the other.

### CFG-285 · `loads` accepts both `str` and `bytes`
- **Area:** `core/pjson.py::loads`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** the same document in both forms
- **Steps:** `loads`
- **Expected:** equal results on both backends
- **Why:** the stdlib branch decodes manually; a missing decode would raise only
  on machines without orjson.

### CFG-286 · Non-ASCII survives a round trip
- **Area:** `core/pjson.py::dumpb`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a value containing `é`, `日本語` and an emoji
- **Steps:** `dumps` and `loads` on both backends
- **Expected:** identical bytes on both (`ensure_ascii=False` on the stdlib path)
  and the original string back
- **Why:** party names in the defect corpus are deliberately mojibake-prone; an
  escaped-vs-raw difference between backends is again a hash difference.

## Business calendars

### CFG-287 · An unknown timezone is refused at construction
- **Area:** `core/calendars.py::BusinessCalendar.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `timezone="Mars/Olympus"`
- **Steps:** construct
- **Expected:** `ValidationError` naming the calendar and the timezone, remedy
  showing an IANA name
- **Why:** a bad zone discovered at the first `business_date_of` would be a
  runtime failure in the scheduler rather than a configuration error.

### CFG-288 · `ALWAYS_OPEN` has no weekend
- **Area:** `core/calendars.py::ALWAYS_OPEN`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `is_business_day` for a Saturday and a Sunday
- **Expected:** `True`
- **Why:** "honest about knowing nothing rather than guessing a market's
  calendar" — the default must not invent a weekend.

### CFG-289 · `WEEKDAYS` excludes Saturday and Sunday and nothing else
- **Area:** `core/calendars.py::WEEKDAYS`, `WESTERN_WEEKEND`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `is_business_day` across a full week
- **Expected:** Monday–Friday true, Saturday and Sunday false
- **Why:** `weekday()` numbering off by one is the classic error and would move
  the whole week.

### CFG-290 · A non-western weekend is expressible
- **Area:** `core/calendars.py::BusinessCalendar.weekend_days`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `weekend_days={4, 5}` (Friday/Saturday)
- **Steps:** `is_business_day` across a week
- **Expected:** Sunday–Thursday true
- **Why:** "Not universal — Gulf markets rest Friday and Saturday — which is
  exactly why it is a parameter rather than an assumption."

### CFG-291 · `next_business_day` skips a holiday
- **Area:** `core/calendars.py::next_business_day`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a calendar with 25 and 26 December as holidays
- **Steps:** `next_business_day(24 December)`
- **Expected:** 27 December, or the following Monday if that is a weekend
- **Why:** the whole abstraction exists so "nothing downstream has to invent its
  own notion of 'next business day'".

### CFG-292 · `next_business_day` on a calendar with no business days does not hang
- **Area:** `core/calendars.py::next_business_day`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `weekend_days={0,1,2,3,4,5,6}`
- **Steps:** call
- **Expected:** a bounded refusal, not an infinite loop
- **Why:** the `while` has no ceiling; a misconfigured calendar would spin a
  scheduler thread for ever.

### CFG-293 · `shift` with zero returns the input unchanged
- **Area:** `core/calendars.py::shift`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a Saturday
- **Steps:** `shift(day, 0)`
- **Expected:** the same Saturday, even though it is not a business day
- **Why:** `range(0)` makes it a no-op — confirm, because "shift by zero" is what
  a settlement rule of T+0 compiles to.

### CFG-294 · `shift` is symmetric
- **Area:** `core/calendars.py::shift`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a business day, weekdays calendar
- **Steps:** `shift(shift(d, 5), -5)`
- **Expected:** `d`
- **Why:** T+2 and T-2 must agree, or a settlement reconciliation compares two
  different days.

### CFG-295 · `business_days_between` is half-open
- **Area:** `core/calendars.py::business_days_between`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** Monday to Friday, weekdays calendar
- **Steps:** count
- **Expected:** 4 — `[start, end)`
- **Why:** an inclusive count is off by one at every month end and the docstring
  states the convention.

### CFG-296 · `business_days_between` is antisymmetric
- **Area:** `core/calendars.py::business_days_between`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** two days
- **Steps:** count both ways
- **Expected:** exact negation
- **Why:** the recursive negative branch is easy to get wrong at equal dates,
  where both must be zero.

### CFG-297 · `business_date_of` rolls an early-morning instant to the previous day
- **Area:** `core/calendars.py::business_date_of`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `day_boundary=time(3, 0)`, an instant at 02:00 local
- **Steps:** call
- **Expected:** the previous calendar day's business date
- **Why:** "A cut-off after midnight is normal for overnight batch: 02:00 belongs
  to the day before."

### CFG-298 · A Saturday arrival belongs to Friday
- **Area:** `core/calendars.py::business_date_of`
- **Type:** functional
- **Priority:** P1
- **Precondition:** weekdays calendar, a Saturday 03:00 instant
- **Steps:** call
- **Expected:** the preceding Friday
- **Why:** "a file that lands at 03:00 on Saturday belongs to Friday's run, not
  to a Saturday that never existed".

### CFG-299 · `business_date_of` converts into the calendar's timezone first
- **Area:** `core/calendars.py::business_date_of`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a Tokyo calendar, an instant at 23:50 UTC
- **Steps:** call
- **Expected:** the *next* day in Tokyo
- **Why:** "A trade booked at 23:50 in New York is a different business date in
  Tokyo" — the timezone is not decoration.

### CFG-300 · `expected_at` survives a daylight-saving transition
- **Area:** `core/calendars.py::expected_at`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a `Europe/London` calendar, `at=time(6, 30)`, dates either
  side of the March and October transitions
- **Steps:** compute the UTC instants
- **Expected:** 06:30 UTC in winter and 05:30 UTC in summer — the *local* time is
  constant
- **Why:** "An arrival window written as 06:30 by a person in London must not
  drift by an hour twice a year."

### CFG-301 · `expected_at` on a non-existent local time is handled
- **Area:** `core/calendars.py::expected_at`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `at=time(1, 30)` on the spring-forward day in a zone where
  01:30 does not exist
- **Steps:** compute
- **Expected:** a defined, documented instant rather than a silent hour's drift
- **Why:** `datetime.combine(..., tzinfo=zone)` resolves the gap by fold rules
  the caller has not been told about.

### CFG-302 · `with_holidays` returns a new calendar
- **Area:** `core/calendars.py::with_holidays`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a calendar
- **Steps:** `with_holidays({...})`
- **Expected:** a new instance; the original is unchanged
- **Why:** the dataclass is frozen and shared, so an in-place mutation would
  change every user of `WEEKDAYS`.

### CFG-303 · An unknown calendar name is refused, never treated as weekdays
- **Area:** `core/calendars.py::CalendarRegistry.get`
- **Type:** negative
- **Priority:** P1
- **Precondition:** nothing named `TARGET2` loaded
- **Steps:** `get("TARGET2")`
- **Expected:** `ValidationError` listing what is loaded and saying treating it
  as weekdays "would produce controls that fire on the wrong days"
- **Why:** the single most important refusal in this module.

### CFG-304 · `get(None)` and `get("")` return `ALWAYS_OPEN`
- **Area:** `core/calendars.py::CalendarRegistry.get`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** both
- **Expected:** `ALWAYS_OPEN`
- **Why:** "not stated" and "stated wrongly" must behave differently, and the
  first is not an error.

### CFG-305 · Calendar names are matched case-insensitively
- **Area:** `core/calendars.py::CalendarRegistry`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a calendar registered as `TARGET2`
- **Steps:** `get("target2")`
- **Expected:** found
- **Why:** `register` lower-cases the key and `get` lower-cases the lookup — but
  `names()` then returns the lower-cased forms, so a listing does not match what
  was registered. Confirm which is intended.

### CFG-306 · Registering a duplicate name is refused unless replaced
- **Area:** `core/calendars.py::CalendarRegistry.register`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `always` already registered
- **Steps:** register another named `always`
- **Expected:** `ValidationError`; with `replace=True`, accepted
- **Why:** two calendars with one name means the controls bound to it fire on
  whichever was loaded last.

### CFG-307 · The default registry is process-wide and shared
- **Area:** `core/calendars.py::default_calendars`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** register into `default_calendars()` from one place, read from
  another
- **Expected:** visible — and note that this is module-level mutable state, which
  makes test order significant
- **Why:** the registry pattern elsewhere in the codebase is deliberately
  non-global (`RegistryCatalogue`); this one is not, and the inconsistency is
  worth pinning down.

## Provenance

### CFG-308 · Origins rank in the documented order
- **Area:** `core/provenance.py::Origin.authority`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** read the authority of each
- **Expected:** declaration 100 > document 80 > import 60 > mining 40 > example
  30 > induction 20
- **Why:** "The higher authority wins the control and the other becomes
  corroboration" — the ordering is the mechanism.

### CFG-309 · Only a declaration may auto-activate
- **Area:** `core/provenance.py::Origin.may_auto_activate`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** check all six
- **Expected:** true for `DECLARATION` only
- **Why:** "a column that happens to be unique in today's extract is not a
  declared key, and enforcing it turns the first legitimate duplicate into an
  incident".

### CFG-310 · `is_stated` is true for the three human origins
- **Area:** `core/provenance.py::Origin.is_stated`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** check all six
- **Expected:** declaration, import, document
- **Why:** the property separates "a person meant it" from "it is true today",
  which is what the review queue orders on.

### CFG-311 · A document-origin provenance without a citation is refused
- **Area:** `core/provenance.py::Provenance.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `Origin.DOCUMENT`, no citation
- **Steps:** construct
- **Expected:** `ValueError` explaining an unfalsifiable rule will not be approved
- **Why:** `FR-IND-012`; a citation-free document rule is indistinguishable from
  a model's invention.

### CFG-312 · Corroboration from a second origin is recorded once
- **Area:** `core/provenance.py::corroborated_by`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a declaration provenance
- **Steps:** corroborate with mining twice
- **Expected:** one corroboration; the second call returns the same object
- **Why:** a nightly miner runs every night and must not fill the record with
  identical corroborations.

### CFG-313 · `corroborated_by` does not mutate the original
- **Area:** `core/provenance.py::corroborated_by`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a frozen provenance
- **Steps:** corroborate, check the original
- **Expected:** unchanged; a new instance returned
- **Why:** frozen dataclasses are shared freely; in-place mutation would be
  impossible anyway and the replace path must be the one taken.

### CFG-314 · `sentence()` names the declarer and the date
- **Area:** `core/provenance.py::Provenance.sentence`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a declaration with `declared_by` and `declared_at`
- **Steps:** render
- **Expected:** "Alice declared it on 2026-03-04." — the date only, not the time
- **Why:** "read at three in the morning by somebody deciding whether an alert
  matters".

### CFG-315 · `sentence()` for a non-declaration uses the origin label
- **Area:** `core/provenance.py::Provenance.sentence`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a mining provenance with observations
- **Steps:** render
- **Expected:** "It holds in the data" capitalised, then the observations
- **Why:** every origin has a label; one that rendered as an enum name would
  reach a business owner's screen.

### CFG-316 · `sentence()` is assembled, never stored
- **Area:** `core/provenance.py::Provenance.sentence`, `to_dict`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a provenance round-tripped through `to_dict`/`from_dict`
- **Steps:** compare the sentence before and after
- **Expected:** identical, and `from_dict` ignores the stored `sentence` key
- **Why:** "a stored sentence drifts from the provenance it describes" — and
  `to_dict` writes one, so `from_dict` must not read it back as authoritative.

### CFG-317 · `identity()` is stable across a text edit
- **Area:** `core/provenance.py::identity`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the same parts
- **Steps:** compute twice, with differing control text
- **Expected:** identical
- **Why:** "Editing a threshold must update the existing control rather than
  orphan one and create another."

### CFG-318 · `identity()` is order-sensitive and part-sensitive
- **Area:** `core/provenance.py::identity`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `identity("a", "b")` and `identity("b", "a")`
- **Steps:** compare
- **Expected:** different
- **Why:** it hashes a list; two different subjects must not collide.

### CFG-319 · `content_hash` changes when the rendered text changes
- **Area:** `core/provenance.py::content_hash`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two renderings differing in one character
- **Steps:** hash both
- **Expected:** different 32-character hexes
- **Why:** `ControlDao.declare` uses it to decide whether to write a new version
  at all; a hash that missed a change would freeze the estate.

### CFG-320 · Both hashes are 32 characters
- **Area:** `core/provenance.py::identity`, `content_hash`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** measure
- **Expected:** 32 hex characters, matching the schema's declared width for
  `ctl_control.identity` and `ctl_control_version.content_hash`
- **Why:** a truncation width that disagrees with the column is a write that
  fails on PostgreSQL only.

## The schema files

### DB-001 · The two schema files are byte-identical apart from their headers
- **Area:** `schema/sqlite.sql`, `schema/postgres.sql`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** diff with the first lines of each header excluded
- **Expected:** exactly three differing lines, all of them naming the other
  dialect
- **Why:** CLAUDE.md rule 2 states it, and `tests/db/test_schema.py` enforces it;
  the case exists so the *counterfactual* is written — insert one extra index
  into one file and confirm the check fails.

### DB-002 · Only the four permitted column types appear
- **Area:** `schema/*.sql`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** extract every column type
- **Expected:** only `VARCHAR(n)`, `TEXT`, `INTEGER`, `REAL`
- **Why:** "only these mean the same thing in both engines". Confirm the check
  rejects `BOOLEAN`, `TIMESTAMP`, `DATETIME`, `JSONB`, `SERIAL`, `NUMERIC`,
  `BIGINT`, `UUID`, `BYTEA`, `BLOB` by planting each in a copy.

### DB-003 · Every `VARCHAR` declares a width
- **Area:** `schema/*.sql`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** scan for bare `VARCHAR`
- **Expected:** none
- **Why:** "a bare `VARCHAR` is unbounded in PostgreSQL and meaningless in
  SQLite" — the two engines would then disagree about what is storable.

### DB-004 · Every primary-key column declares `NOT NULL`
- **Area:** `schema/*.sql`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** for each of the 34 tables, check the primary-key column definitions
- **Expected:** all explicit
- **Why:** "SQLite does not [imply it] for a non-`INTEGER` primary key and would
  store a NULL id".

### DB-005 · Every statement is idempotent
- **Area:** `schema/*.sql`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** check every `CREATE` for `IF NOT EXISTS`
- **Expected:** every one has it
- **Why:** `prama db init` is applied twice in the normal upgrade path; a
  statement without the guard turns the second run into a failure.

### DB-006 · Constraint naming follows `uq_`, `ix_`, `ck_`
- **Area:** `schema/*.sql`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** extract every named constraint and index
- **Expected:** every name carries one of the three prefixes; no unnamed
  `UNIQUE` or `CHECK` at table level
- **Why:** CLAUDE.md names the convention; an unnamed constraint on PostgreSQL
  gets a generated name the verifier cannot match.

### DB-007 · Every constraint name is unique across the file
- **Area:** `schema/*.sql`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** count duplicates among the 64 index names and the check constraints
- **Expected:** none
- **Why:** PostgreSQL index names are schema-scoped, so a duplicate is an apply
  failure on one engine and silently accepted on the other.

### DB-008 · Every table the ORM declares exists in the schema file
- **Area:** `db/models/`, `schema/*.sql`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** compare the 34 schema tables with the mapped tables of `Base` and
  `EvidenceBase`
- **Expected:** exact correspondence in both directions
- **Why:** "The ORM models must agree with schema/*.sql, which is the authority."

### DB-009 · Every ORM string width matches the declared `VARCHAR(n)`
- **Area:** `db/models/`, `schema/*.sql`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** compare widths column by column
- **Expected:** identical
- **Why:** a model declaring 64 against a column of 32 writes a value that
  PostgreSQL refuses and SQLite accepts, which is the worst possible split.

### DB-010 · Nullability agrees between the ORM and the schema
- **Area:** `db/models/`, `schema/*.sql`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** compare
- **Expected:** identical
- **Why:** the verifier only reports a live column that is *more* permissive than
  declared; a model that is more permissive than the schema is caught nowhere
  else.

### DB-011 · Every boolean column is `INTEGER` with a 0/1 CHECK
- **Area:** `schema/*.sql`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** find every column mapped by `BoolInt` and check its constraint
- **Expected:** `INTEGER` with `CHECK (col IN (0,1))`
- **Why:** without the check, `2` is storable and `bool(2)` is `True`, so an
  impossible value reads as a legitimate one.

### DB-012 · Every timestamp column is `VARCHAR(32)`
- **Area:** `schema/*.sql`, `db/types.py::TIMESTAMP_WIDTH`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** find every column mapped by `UtcDateTime`
- **Expected:** `VARCHAR(32)` in both files
- **Why:** 28 characters plus room; a narrower column truncates the microseconds
  on PostgreSQL and breaks the ordering.

### DB-013 · Every identifier column is `VARCHAR(26)`
- **Area:** `schema/*.sql`, `db/types.py::ULID_WIDTH`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** find every id and foreign-key column
- **Expected:** `VARCHAR(26)`
- **Why:** a ULID is exactly 26; a wider column lets a non-ULID in and a narrower
  one refuses a valid id.

### DB-014 · Exactly one current version per entity is enforced by a partial index
- **Area:** `schema/*.sql`, the ten `uq_*_current` indexes
- **Type:** contract
- **Priority:** P1
- **Precondition:** a bootstrapped database on each engine
- **Steps:** insert two version rows for one entity with `valid_to IS NULL AND
  superseded_at IS NULL`
- **Expected:** an integrity error on both engines
- **Why:** `db/temporal.py` claims "A partial unique index in the schema enforces
  exactly one current version per entity, on both engines" — partial indexes
  behave differently enough between the two that this must be executed, not read.

### DB-015 · `uq_ev_record_sequence` prevents a forked chain
- **Area:** `schema/*.sql`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** a tenant with records up to sequence *n*
- **Steps:** two concurrent appends at *n+1*
- **Expected:** one succeeds, one raises; never two rows at *n+1*
- **Why:** "a forked chain is a condition no later verification can repair,
  because both branches are internally consistent".

### DB-016 · `uq_ev_record_hash` prevents a duplicated record hash
- **Area:** `schema/*.sql`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a stored record
- **Steps:** insert a second row with the same `record_hash`
- **Expected:** refused
- **Why:** two records with one hash makes the Merkle root ambiguous.

### DB-017 · `uq_tenant_slug` is global, not per-anything
- **Area:** `schema/*.sql`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** one tenant `acme-bank`
- **Steps:** create another with the same slug
- **Expected:** refused, surfaced as a `ConflictError`
- **Why:** `TenantDao.by_slug` returns `one_or_none`; a duplicate slug would
  raise a SQLAlchemy `MultipleResultsFound` from inside a DAO instead.

### DB-018 · `uq_principal_tenant_username` is per tenant
- **Area:** `schema/*.sql`
- **Type:** security
- **Priority:** P1
- **Precondition:** two tenants
- **Steps:** create `alice` in both
- **Expected:** accepted; a second `alice` in one tenant refused
- **Why:** a global username constraint would leak the existence of other
  tenants' accounts through a creation failure.

### DB-019 · `uq_api_key_prefix` is global
- **Area:** `schema/*.sql`, `db/dao/platform.py::ApiKeyDao.by_prefix`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** attempt two keys with the same prefix
- **Expected:** refused
- **Why:** `by_prefix` does an unscoped `one_or_none` lookup — a duplicate prefix
  would make authentication raise, and a colliding prefix across tenants is a
  cross-tenant lookup.

### DB-020 · `uq_ctl_control_identity` makes regeneration idempotent
- **Area:** `schema/*.sql`, `db/dao/control.py::declare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a control declared under an identity
- **Steps:** insert another control row with the same identity in the same tenant
- **Expected:** refused
- **Why:** the identity is what makes re-running a generator amend rather than
  duplicate.

### DB-021 · `uq_att_content` prevents double-signing identical content
- **Area:** `schema/*.sql`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a signed attestation
- **Steps:** sign an identical one
- **Expected:** refused, or the constraint's scope is documented — an attester
  legitimately re-signing the same period after a correction produces different
  content because `supersedes` is inside the hash
- **Why:** the constraint interacts with `Attestation.content()`; confirm a
  legitimate correction is not blocked.

### DB-022 · `uq_rec_break_key` is per tenant and definition
- **Area:** `schema/*.sql`, `db/dao/recon.py::observe`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two reconciliations producing the same break key
- **Steps:** observe both
- **Expected:** two rows, not a conflict
- **Why:** `observe` keys its `existing` map by `break_key` within one
  definition; a constraint narrower than that would make the second
  reconciliation fail.

### DB-023 · Every CHECK constraint refuses its out-of-domain value
- **Area:** `schema/*.sql` — 43 checks
- **Type:** negative
- **Priority:** P1
- **Precondition:** a bootstrapped database on each engine
- **Steps:** for each check, insert one violating row
- **Expected:** refused on both engines, with the same logical outcome
- **Why:** a check that binds on one engine and not the other is the exact
  failure the four-type rule exists to prevent, and a constraint nobody has
  tried is a constraint nobody knows works.

### DB-024 · `ck_sem_dataset_criticality` bounds the tier
- **Area:** `schema/*.sql`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** insert criticality 0, 1, 4, 5
- **Expected:** the declared range accepted, everything outside refused
- **Why:** `DatasetDao.by_criticality` and the alert router both index on it; an
  out-of-range tier is a dataset nothing routes.

### DB-025 · No foreign key leaves the evidence ledger
- **Area:** `schema/*.sql`, `db/models/evidence.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** scan the `ev_*` and `att_*` tables for references to platform tables
- **Expected:** none, and no `ON DELETE CASCADE` anywhere in the ledger
- **Why:** "the ledger … can never be created, migrated or truncated by a
  platform operation"; a cascade from a tenant delete would erase evidence.

### DB-026 · Every index the schema declares is created by `db init`
- **Area:** `db/schema/bootstrap.py`, `schema/*.sql`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a fresh database
- **Steps:** `db init`, then list indexes per table
- **Expected:** all 64 present
- **Why:** an index in the file that the splitter dropped would be invisible
  until a query got slow.

### DB-027 · Both files declare the same tables in the same order
- **Area:** `schema/*.sql`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** compare the parsed `table_names` of each
- **Expected:** identical tuples
- **Why:** the bootstrapper applies statements in file order, so a different
  order would mean a foreign key referencing a table that does not exist yet on
  one engine.

## The schema loader, bootstrapper and verifier

### DB-028 · The loader parses every table and column
- **Area:** `db/schema/loader.py::SchemaLoader.load`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the shipped SQLite schema
- **Steps:** load and count
- **Expected:** 34 tables; every column of a spot-checked table present with the
  right type and nullability, and a column count that matches the ORM's
- **Why:** verification is built entirely on this parse — a column the regex
  misses is a column nothing verifies, silently.

### DB-029 · A column whose definition wraps onto a continuation line is parsed
- **Area:** `db/schema/loader.py::_COLUMN`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a table whose column carries an inline `CHECK` on the next
  line
- **Steps:** load
- **Expected:** the column appears
- **Why:** the pattern uses `[\s\S]*` rather than `.*` precisely so "the wrap does
  not silently end the match and drop the column from the parsed schema — a
  defect that would make verification quietly incomplete rather than loudly
  wrong".

### DB-030 · Table-level constraints are not parsed as columns
- **Area:** `db/schema/loader.py::_NOT_A_COLUMN`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a table with `PRIMARY KEY (a, b)`, `FOREIGN KEY`, `UNIQUE`,
  `CHECK` and `CONSTRAINT` clauses
- **Steps:** load
- **Expected:** none becomes a `ColumnSpec`
- **Why:** a phantom column named `PRIMARY` would be reported as missing drift
  on every verification for ever.

### DB-031 · The statement splitter handles a semicolon inside a string literal
- **Area:** `db/schema/loader.py::_split`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a schema copy with `DEFAULT 'a;b'`
- **Steps:** load and apply
- **Expected:** one statement, applied correctly — or a loud refusal
- **Why:** the docstring names this as the failure mode of a half-clever
  splitter; the schema is "deliberately simple" today, and the guard is that a
  future edit which breaks the assumption fails visibly.

### DB-032 · Line comments are stripped and do not truncate statements
- **Area:** `db/schema/loader.py::_LINE_COMMENT`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** the shipped files, which are heavily commented
- **Steps:** count parsed statements
- **Expected:** every `CREATE` in the file becomes a statement
- **Why:** the comment regex runs before the split, so a `--` inside a string
  would eat the rest of the line.

### DB-033 · The digest changes when a single character of the file changes
- **Area:** `db/schema/loader.py::SchemaLoader.load`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a copy of the schema with one comment character added
- **Steps:** load both, compare digests
- **Expected:** different
- **Why:** the digest is the drift detector of last resort; hashing anything less
  than the whole file would miss a change to a `CHECK`.

### DB-034 · A comment-only change is reported as digest drift, not blocking
- **Area:** `db/schema/verifier.py`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a database bootstrapped from the original file, then the file
  gets a new comment
- **Steps:** `db verify`
- **Expected:** a `DIGEST` drift, informational, with the "re-run `prama db
  init`" advice; exit status is success
- **Why:** `DIGEST` is deliberately outside `BLOCKING`; a comment edit must not
  stop a fleet from booting.

### DB-035 · `db init` on an empty database creates everything
- **Area:** `db/schema/bootstrap.py::SchemaBootstrapper.apply`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an empty database
- **Steps:** apply
- **Expected:** `created=True`, `tables_present=34`, `statements_executed` equals
  the parsed count
- **Why:** the summary is what the CLI prints and what an operator reads as proof.

### DB-036 · `db init` twice is a no-op
- **Area:** `db/schema/bootstrap.py::apply`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a bootstrapped database
- **Steps:** apply again
- **Expected:** `created=False`, summary "already current", no error
- **Why:** the idempotence claim in CLAUDE.md and in every remedy that says
  "run `prama db init` (safe: it only creates missing objects)".

### DB-037 · `db init` never alters an existing object
- **Area:** `db/schema/bootstrap.py`
- **Type:** security
- **Priority:** P1
- **Precondition:** a table with an extra column and a different index
- **Steps:** apply
- **Expected:** the extra column and index survive untouched
- **Why:** "a tool that quietly reshapes a production database is a tool that can
  quietly lose data".

### DB-038 · A failing schema statement names the statement and the detail
- **Area:** `db/schema/bootstrap.py::_execute`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a schema copy with a syntax error in the twentieth statement
- **Steps:** apply
- **Expected:** `DatabaseError` `DB.SCHEMA_APPLY_FAILED` with the first 300
  characters of the statement and the engine's first error line
- **Why:** "fix the database or the schema file" is unactionable without knowing
  which statement.

### DB-039 · A failed apply leaves no partial schema
- **Area:** `db/schema/bootstrap.py::_execute`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** as above
- **Steps:** apply, then list tables
- **Expected:** on PostgreSQL, nothing was created — DDL is transactional; on
  SQLite, document what survives
- **Why:** `engine.begin()` wraps the whole loop, and the two engines differ in
  what that means for DDL. An operator needs to know which state they are in.

### DB-040 · `schema_state` records digest, version, dialect, who and when
- **Area:** `db/schema/bootstrap.py::_record_state`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a fresh apply
- **Steps:** read the single row
- **Expected:** `id=1`, the file digest, `SCHEMA_VERSION`, the dialect,
  `user@host`, `VERSION`, an ISO-8601 `Z` timestamp
- **Why:** "exactly one row, always overwritten, describing what this database
  was last built from".

### DB-041 · `applied_by` is overridable and defaults safely
- **Area:** `db/schema/bootstrap.py::_current_user`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** an environment where `getpass.getuser()` raises (no `USER`,
  no passwd entry — a container)
- **Steps:** apply
- **Expected:** `unknown@<hostname>`, not a traceback
- **Why:** the all-in-one image runs as uid 10001 with no login shell.

### DB-042 · `schema_state` has exactly one row after repeated applies
- **Area:** `db/schema/bootstrap.py::_record_state`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** three applies
- **Steps:** count rows
- **Expected:** one
- **Why:** the upsert conflicts on `id`; an insert-only path would build a
  migration history the design explicitly rejects.

### DB-043 · A freshly built database verifies clean
- **Area:** `db/schema/verifier.py::SchemaVerifier.verify`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `db init` just run
- **Steps:** `verify()`
- **Expected:** no drifts at all, and the summary says "no drift"
- **Why:** a verifier that reports drift against its own bootstrap is one nobody
  will ever trust to report real drift.

### DB-044 · A dropped table is blocking drift
- **Area:** `db/schema/verifier.py`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `DROP TABLE setting`
- **Steps:** `verify()`
- **Expected:** `MISSING_TABLE`, blocking, and `raise_if_blocking` raises
- **Why:** the whole no-migrations design rests on the verifier catching this.

### DB-045 · A dropped column is blocking drift
- **Area:** `db/schema/verifier.py`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a column removed from a live table
- **Steps:** `verify()`
- **Expected:** `MISSING_COLUMN` naming `table.column` and the declared type
- **Why:** a missing column fails at first write with an engine error nobody can
  attribute.

### DB-046 · A column that has become nullable is blocking drift
- **Area:** `db/schema/verifier.py`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a `NOT NULL` column altered to nullable
- **Steps:** `verify()`
- **Expected:** `NULLABILITY` drift, blocking
- **Why:** "intentionally strict about the things that change behaviour".

### DB-047 · A column whose **type** changed is detected
- **Area:** `db/schema/verifier.py::SchemaVerifier.verify`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `ev_record.verdict` altered from `VARCHAR(16)` to `TEXT` on
  PostgreSQL, and a `REAL` column altered to `INTEGER`
- **Steps:** `verify()`
- **Expected:** drift reported, blocking
- **Why:** the loader captures `ColumnSpec.type` and the verifier never compares
  it — only presence and nullability. A retyped column is exactly the drift a
  no-migrations product must catch, and the docstring's "tolerant about the
  things that do not [change behaviour]" does not cover it.

### DB-048 · A column whose declared width shrank is detected
- **Area:** `db/schema/verifier.py`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `VARCHAR(26)` altered to `VARCHAR(8)` on PostgreSQL
- **Steps:** `verify()`, then write a ULID
- **Expected:** verification reports it; otherwise the first write fails
- **Why:** the same gap as DB-047, with a sharper consequence: every id write
  fails at runtime.

### DB-049 · An extra table is reported and is not blocking
- **Area:** `db/schema/verifier.py::BLOCKING`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an operator's own table in the database
- **Steps:** `verify()`
- **Expected:** `EXTRA_TABLE`, informational; `ok` is still true
- **Why:** "tolerant about the things that do not [change behaviour]" — a
  reporting table an operator added must not stop the platform.

### DB-050 · An extra *column* on a declared table is not reported at all
- **Area:** `db/schema/verifier.py::verify`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an extra `NOT NULL` column with no default added to `tenant`
- **Steps:** `verify()`, then insert a tenant
- **Expected:** either the extra column is reported informationally, or the
  insert fails with nothing having warned
- **Why:** the verifier iterates the *declared* columns only. An extra nullable
  column is harmless; an extra `NOT NULL` one makes every insert fail and the
  verifier says the database is clean.

### DB-051 · A missing index is reported and is not blocking
- **Area:** `db/schema/verifier.py`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `DROP INDEX ix_audit_tenant_time`
- **Steps:** `verify()`
- **Expected:** `MISSING_INDEX` naming it, informational
- **Why:** correctness survives without an index; performance does not, and the
  operator needs to be told which kind of problem they have.

### DB-052 · A missing *unique* index is treated as more than performance
- **Area:** `db/schema/verifier.py::BLOCKING`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `DROP INDEX uq_ev_record_sequence`
- **Steps:** `verify()`
- **Expected:** blocking, or a documented decision that it is not
- **Why:** `MISSING_INDEX` is uniformly informational, but a dropped `uq_` index
  removes a *correctness* guarantee — the chain can then fork — and the
  verification would say the database is fine.

### DB-053 · A schema-version mismatch is blocking
- **Area:** `db/schema/verifier.py::verify`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `schema_state.schema_version` set to a different value
- **Steps:** `verify()`
- **Expected:** `VERSION` drift, blocking, naming both versions
- **Why:** an older database against a newer build is the upgrade case the Helm
  chart's `prama.io/upgrade-requires` annotation exists for.

### DB-054 · Verification survives an unbootstrapped database
- **Area:** `db/schema/verifier.py::_recorded_state`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an empty database with no `schema_state` table
- **Steps:** `verify()`
- **Expected:** 34 `MISSING_TABLE` drifts and no traceback from the state query
- **Why:** the first thing a new operator does is run `verify` before `init`.

### DB-055 · `_recorded_state` swallowing `SQLAlchemyError` is bounded
- **Area:** `db/schema/verifier.py::_recorded_state`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a database the process cannot connect to at all
- **Steps:** `verify()`
- **Expected:** a connection failure is reported, not turned into "no recorded
  state"
- **Why:** CLAUDE.md: "No exception is swallowed." The bare `except
  SQLAlchemyError: return None, None` makes an unreachable database look like an
  unbootstrapped one.

### DB-056 · `raise_if_blocking` carries every blocking drift in its context
- **Area:** `db/schema/verifier.py::VerificationReport.raise_if_blocking`
- **Type:** contract
- **Priority:** P1
- **Precondition:** three blocking drifts
- **Steps:** catch the error
- **Expected:** `SchemaDriftError` `DB.SCHEMA_DRIFT` listing all three as
  `kind:object`
- **Why:** an operator fixing them one at a time and re-running is three
  restarts; the list is one.

### DB-057 · The drift remedy says nothing will be altered automatically
- **Area:** `db/schema/verifier.py::raise_if_blocking`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** any blocking drift
- **Steps:** read the remedy
- **Expected:** it names `prama db init`, describes it as safe because it only
  creates, and states that nothing is altered automatically
- **Why:** the remedy is the only place the no-migrations policy is explained to
  somebody at 3am, and it must not suggest anything destructive.

### DB-058 · `summary()` marks blocking drift distinctly
- **Area:** `db/schema/verifier.py::Drift.__str__`
- **Type:** functional
- **Priority:** P3
- **Precondition:** a mix of blocking and informational drift
- **Steps:** render
- **Expected:** `!` for blocking, `-` for informational, counts in the heading
- **Why:** a wall of identical lines makes an operator read all of them or none.

### DB-059 · Verification works identically on PostgreSQL
- **Area:** `db/dialects.py::PostgresDialect.list_columns`, `list_indexes`
- **Type:** contract
- **Priority:** P1
- **Precondition:** `PRAMA_TEST_POSTGRES_DSN` set
- **Steps:** run DB-043 through DB-058 against PostgreSQL
- **Expected:** the same drifts, the same blocking classification
- **Why:** the introspection is entirely different code per dialect; the
  behaviour above it must not be.

### DB-060 · PostgreSQL introspection respects `database.postgres.schema`
- **Area:** `db/dialects.py::PostgresDialect.list_tables`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** the schema applied into `prama_alt`, `schema: prama_alt`
- **Steps:** `verify()`
- **Expected:** clean — the tables are found in the configured schema, and an
  identically-named table in `public` is not mistaken for them
- **Why:** `search_path` is set through `connect_args` and the introspection
  queries filter on `table_schema`; a mismatch would verify the wrong database.

### DB-061 · SQLite introspection ignores internal objects
- **Area:** `db/dialects.py::SqliteDialect.list_tables`, `list_indexes`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a bootstrapped SQLite database
- **Steps:** list tables and indexes
- **Expected:** no `sqlite_%` names
- **Why:** `sqlite_autoindex_*` entries would be reported as extra objects on
  every verification.

## Engines, sessions and the unit of work

### DB-062 · Both engines share the connect hook
- **Area:** `db/engine.py::EngineFactory._install_connect_hook`
- **Type:** contract
- **Priority:** P1
- **Precondition:** SQLite with a non-default `synchronous`
- **Steps:** read the pragma through the sync engine and the async engine
- **Expected:** identical
- **Why:** "so a pragma or a statement timeout cannot apply on one path and not
  the other".

### DB-063 · Engines are cached per factory
- **Area:** `db/engine.py::EngineFactory`
- **Type:** performance
- **Priority:** P2
- **Precondition:** none
- **Steps:** call `sync_engine()` and `async_engine()` twice each
- **Expected:** the same objects
- **Why:** "Engines are expensive and pooled; a process holds one of each."

### DB-064 · Two factories are independent
- **Area:** `db/engine.py::EngineFactory`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two `Database` objects on different files
- **Steps:** write through each
- **Expected:** no crossover
- **Why:** "what allows a test to run two databases side by side, and what would
  allow one process to serve more than one tenant estate".

### DB-065 · A missing driver produces a named error with an install hint
- **Area:** `db/engine.py::_creation_error`, `Dialect.driver_hint`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `asyncpg` not installed, `dialect: postgres`
- **Steps:** build the async engine
- **Expected:** `DatabaseError` `DB.ENGINE_CREATE_FAILED` whose remedy is
  `pip install 'prama[postgres]'`
- **Why:** the remedy must be followable literally; confirm the extra exists in
  `pyproject.toml` under that name.

### DB-066 · The password never appears in an engine error
- **Area:** `db/engine.py::_creation_error`
- **Type:** security
- **Priority:** P1
- **Precondition:** a PostgreSQL password set, a deliberately bad host
- **Steps:** trigger the failure, read the message and the context
- **Expected:** `***` where the password would be — `render_as_string(
  hide_password=True)` is used
- **Why:** a DSN in a log or a problem document is a credential in a ticket.

### DB-067 · `dispose` releases both pools and allows a restart
- **Area:** `db/engine.py::EngineFactory.dispose`
- **Type:** functional
- **Priority:** P2
- **Precondition:** both engines built
- **Steps:** `await dispose()`, then `sync_engine()` again
- **Expected:** a fresh engine is built; no leaked connections in between
- **Why:** "Called on shutdown and between tests" — a factory that could not be
  reused would make every test build a process.

### DB-068 · An in-memory SQLite keeps its schema across sessions
- **Area:** `db/dialects.py::SqliteDialect.engine_kwargs`
- **Type:** regression
- **Priority:** P1
- **Precondition:** `path: ":memory:"`
- **Steps:** `db init`, then open a unit of work and query
- **Expected:** the tables are there
- **Why:** the `StaticPool` is there because otherwise "an in-memory database is
  … silently re-created per checkout — the classic reason an in-memory test
  'loses' its schema".

### DB-069 · The async SQLite engine uses `NullPool`
- **Area:** `db/dialects.py::SqliteDialect.engine_kwargs`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a file-backed SQLite database
- **Steps:** inspect the pool class
- **Expected:** `NullPool` for async, `QueuePool` for sync
- **Why:** the choice is deliberate and asymmetric; a pooled aiosqlite connection
  shared across tasks is a locking failure under load.

### DB-070 · The asyncpg path sets application name, statement timeout and search path
- **Area:** `db/dialects.py::PostgresDialect.engine_kwargs`
- **Type:** functional
- **Priority:** P1
- **Precondition:** PostgreSQL available
- **Steps:** connect, read `application_name`, `statement_timeout`, `search_path`
- **Expected:** the configured values; the timeout in milliseconds
- **Why:** asyncpg takes server settings rather than libpq keywords and does not
  understand `sslmode` — an option passed on the wrong path is silently ignored.

### DB-071 · The psycopg path passes `sslmode`
- **Area:** `db/dialects.py::PostgresDialect.engine_kwargs`
- **Type:** security
- **Priority:** P1
- **Precondition:** `sslmode: require` against a server without TLS
- **Steps:** build the sync engine and connect
- **Expected:** refused
- **Why:** the async path deliberately omits `sslmode`; confirm the *sync* path
  honours it and that the asymmetry is documented rather than a gap in TLS
  enforcement.

### DB-072 · `sslmode` is not silently dropped on the async path
- **Area:** `db/dialects.py::PostgresDialect._url`, `engine_kwargs`
- **Type:** security
- **Priority:** P1
- **Precondition:** `sslmode: require`, an async connection to a non-TLS server
- **Steps:** connect
- **Expected:** either refused, or the configuration is refused at start-up with
  an explanation
- **Why:** the comment says "the driver negotiates TLS itself", which is not the
  same as honouring `require`. An operator who set `require` and got a plaintext
  connection has a compliance finding, not a preference.

### DB-073 · `statement_timeout` actually cancels a long query
- **Area:** `db/dialects.py::PostgresDialect.engine_kwargs`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `statement_timeout: 1s`
- **Steps:** run `SELECT pg_sleep(5)` on both engines
- **Expected:** cancelled after about a second on both
- **Why:** a timeout configured and not applied is a control plane that can hold
  a lock on somebody's production database indefinitely.

### DB-074 · A fractional statement timeout does not truncate to zero
- **Area:** `db/dialects.py::PostgresDialect.engine_kwargs`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `statement_timeout: 500us`
- **Steps:** build the kwargs
- **Expected:** not `0` — a zero statement timeout means *unlimited* in
  PostgreSQL, the exact opposite of what was asked for
- **Why:** `int(seconds * 1000)` of 0.0005 is 0.

### DB-075 · `upsert` produces a working statement on both engines
- **Area:** `db/dialects.py::upsert`
- **Type:** contract
- **Priority:** P1
- **Precondition:** both engines
- **Steps:** insert then upsert the same key through `SettingDao.put`
- **Expected:** one row, the later value, on both
- **Why:** the two implementations differ only in `excluded` versus `EXCLUDED`;
  the behaviour above them must be identical.

### DB-076 · `upsert` with every column in the conflict key produces valid SQL
- **Area:** `db/dialects.py::upsert`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** columns == conflict
- **Steps:** build the statement
- **Expected:** either a valid `DO NOTHING`, or a refusal — not `DO UPDATE SET`
  with an empty assignment list, which is a syntax error on both engines
- **Why:** the comprehension can produce an empty `assignments` string.

### DB-077 · `upsert` does not interpolate caller-supplied identifiers unsafely
- **Area:** `db/dialects.py::upsert`
- **Type:** security
- **Priority:** P2
- **Precondition:** none
- **Steps:** review every call site of `upsert` in `src/`
- **Expected:** every table and column name is a literal in Prama's own code,
  never derived from user input
- **Why:** the table and column names are f-string-interpolated; the safety is
  entirely a property of the call sites, so the call sites are the test.

### DB-078 · A unit of work commits on a clean exit
- **Area:** `db/session.py::UnitOfWork.__aexit__`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a fresh database
- **Steps:** create a tenant inside the block, then read it in a new unit
- **Expected:** present
- **Why:** the boundary is the whole contract.

### DB-079 · A unit of work rolls back on any exception
- **Area:** `db/session.py::UnitOfWork.__aexit__`
- **Type:** functional
- **Priority:** P1
- **Precondition:** as above
- **Steps:** create a tenant, then raise
- **Expected:** nothing persisted
- **Why:** "they cannot accidentally commit half of a change".

### DB-080 · A failure mid-transaction rolls back everything before it
- **Area:** `db/session.py::UnitOfWork`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a tenant, a principal and a role created in one block, then a
  constraint violated
- **Steps:** run the block
- **Expected:** none of the three persists
- **Why:** the evidence and platform writes deliberately share a transaction so
  that "a control result recorded without the run it belongs to … is worse than
  neither".

### DB-081 · An integrity error becomes a `ConflictError`
- **Area:** `db/session.py::UnitOfWork._guarded`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a duplicate tenant slug
- **Steps:** commit
- **Expected:** `ConflictError` `ENTITY.CONFLICT`, remedy "re-read the current
  state and retry, or correct the input", the first line of the driver error in
  the context
- **Why:** "a DAO never returns a sentinel meaning 'something went wrong'", and a
  raw `IntegrityError` reaching the API is a SQL fragment in a problem document.

### DB-082 · Any other SQLAlchemy error becomes a `DatabaseError`
- **Area:** `db/session.py::UnitOfWork._guarded`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a statement the engine rejects
- **Steps:** flush
- **Expected:** `DB.TRANSACTION_FAILED`, remedy noting the rollback happened
- **Why:** the remedy tells the caller the state they are in, which is the one
  thing they cannot determine themselves.

### DB-083 · The session is rolled back before the translated error is raised
- **Area:** `db/session.py::UnitOfWork._guarded`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a conflict on flush, caught by the caller
- **Steps:** catch the `ConflictError`, then use the same unit of work
- **Expected:** the session is usable — not in "this session is in prepared
  state" limbo
- **Why:** the rollback is inside the handler precisely so a caller can recover;
  confirm that it does.

### DB-084 · A translated error does not leak the driver's parameters
- **Area:** `db/session.py::_first_line`
- **Type:** security
- **Priority:** P1
- **Precondition:** a unique violation on a row containing a password hash
- **Steps:** read `exc.context["detail"]`
- **Expected:** no bound parameter values
- **Why:** SQLAlchemy's message includes the statement and, on some drivers, the
  parameters; the 400-character truncation is not a redaction.

### DB-085 · `close` is idempotent
- **Area:** `db/session.py::UnitOfWork.close`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a closed unit of work
- **Steps:** `close()` again
- **Expected:** no error
- **Why:** `__aexit__` closes in a `finally`; an explicit close in a caller's
  `finally` is the natural thing to write as well.

### DB-086 · Using a closed unit of work is refused clearly
- **Area:** `db/session.py::UnitOfWork`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a closed unit of work
- **Steps:** `await uow.tenants.get(id)`
- **Expected:** a named refusal rather than a raw SQLAlchemy "session is closed"
- **Why:** the layering claim is that nothing above `prama.db` ever sees
  SQLAlchemy, including in its exceptions.

### DB-087 · Nested units of work on one database are independent
- **Area:** `db/session.py::SessionManager.session`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** file-backed SQLite and PostgreSQL
- **Steps:** open two units of work, write in one, read in the other before
  committing
- **Expected:** the second does not see the uncommitted write
- **Why:** each unit gets its own session; a shared session would make two
  "transactions" one, and the in-memory `StaticPool` makes that concretely
  possible on SQLite.

### DB-088 · DAOs are lazily constructed and cached
- **Area:** `db/session.py::UnitOfWork._dao`
- **Type:** performance
- **Priority:** P3
- **Precondition:** a unit of work
- **Steps:** read `uow.tenants` twice and `uow.controls` once
- **Expected:** the same tenant DAO object; the control DAO built only when
  touched
- **Why:** "a unit of work that touches one table does not construct six
  objects"; there are 23 DAO properties.

### DB-089 · Every DAO property is reachable and returns its declared type
- **Area:** `db/session.py::UnitOfWork`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a unit of work
- **Steps:** touch all 23 properties
- **Expected:** each returns an instance of the type in its annotation
- **Why:** each is a hand-written property with a local import and a `type:
  ignore`; a copy-paste error would give two names one DAO and nothing would
  notice until a write went to the wrong table.

### DB-090 · `expire_on_commit` is off so objects survive the boundary
- **Area:** `db/session.py::SessionManager.maker`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a tenant created inside a unit of work
- **Steps:** read `tenant.slug` after the block exits
- **Expected:** the value, not a `DetachedInstanceError`
- **Why:** "objects stay usable after the boundary closes" — every CLI command
  that prints an id relies on it.

### DB-091 · `autoflush` is off so no surprise SQL is issued
- **Area:** `db/session.py::SessionManager.maker`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a pending unflushed object
- **Steps:** issue an unrelated query
- **Expected:** the pending object is not flushed
- **Why:** "flush is explicit; surprise SQL is a debugging tax" — and several
  DAOs call `flush()` deliberately before raw SQL for exactly this reason.

### DB-092 · Every DAO that issues raw SQL flushes first
- **Area:** `db/dao/platform.py::RoleDao.grant`, `SettingDao.put`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a pending ORM insert of the row the raw statement will touch
- **Steps:** call the method
- **Expected:** the correct final state — "raw SQL must not race pending ORM
  state"
- **Why:** with `autoflush` off, a raw `text()` statement is issued against a
  database that does not yet contain the caller's own pending rows.

## Portable types and credential handling

### DB-093 · `UtcDateTime` refuses a naive datetime on write
- **Area:** `db/types.py::UtcDateTime.process_bind_param`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a naive datetime
- **Steps:** persist
- **Expected:** `ValueError` — "refusing to store a naive datetime; attach UTC
  before persisting"
- **Why:** "Silent localisation is how an evidence record ends up an hour wrong
  twice a year."

### DB-094 · `UtcDateTime` refuses a non-datetime
- **Area:** `db/types.py::UtcDateTime.process_bind_param`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a string that looks like a timestamp
- **Steps:** persist
- **Expected:** `TypeError` naming the type received
- **Why:** a string written straight through would bypass the `Z` normalisation
  and break the sort order.

### DB-095 · A non-UTC aware datetime is converted, not rejected
- **Area:** `db/types.py::UtcDateTime.process_bind_param`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an instant in `Asia/Tokyo`
- **Steps:** persist and read back
- **Expected:** the same instant, expressed in UTC with a `Z`
- **Why:** the calendar layer produces local-zone datetimes legitimately.

### DB-096 · A datetime round-trips exactly, to the microsecond
- **Area:** `db/types.py::UtcDateTime`
- **Type:** contract
- **Priority:** P1
- **Precondition:** instants at microsecond 0, 1 and 999999
- **Steps:** persist and read, on both engines
- **Expected:** equal to the input
- **Why:** "The critical property is round-trip fidelity: what goes in comes out
  equal, on both engines."

### DB-097 · A stored `+00:00` form is still readable
- **Area:** `db/types.py::UtcDateTime.process_result_value`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a row written by hand with `+00:00`
- **Steps:** read through the ORM
- **Expected:** parsed to the same instant
- **Why:** external tooling and `scripts/verify_evidence.py` both touch these
  columns; a reader that only accepts `Z` would break on a hand-fixed row.

### DB-098 · A malformed timestamp in a row is refused, not silently defaulted
- **Area:** `db/types.py::UtcDateTime.process_result_value`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a row containing `not-a-date`
- **Steps:** read
- **Expected:** a clear failure naming the column, not a `ValueError` from
  `fromisoformat` with no context
- **Why:** a corrupted timestamp in the evidence ledger must be attributable.

### DB-099 · `JsonText` writes sorted keys by default
- **Area:** `db/types.py::JsonText`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the same mapping inserted in two key orders
- **Steps:** read the raw stored text
- **Expected:** identical
- **Why:** "a value written by a repository and a value written by the evidence
  ledger are byte-wise comparable — which matters as soon as anything is hashed".

### DB-100 · `JsonText` round-trips nested structures
- **Area:** `db/types.py::JsonText`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a nested dict with lists, numbers, nulls and unicode
- **Steps:** persist and read
- **Expected:** equal
- **Why:** every `*_json` column in the schema uses it.

### DB-101 · `JsonText` of `None` is SQL NULL, not `"null"`
- **Area:** `db/types.py::JsonText.process_bind_param`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a nullable JSON column set to `None`
- **Steps:** persist, then query `IS NULL`
- **Expected:** matched
- **Why:** `tombstone_json` is tested for truthiness in `EvidenceDao`; the string
  `"null"` is truthy.

### DB-102 · `JsonText` of an empty dict is `{}`, not NULL
- **Area:** `db/types.py::JsonText`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `settings_json={}`
- **Steps:** persist and read
- **Expected:** `{}`
- **Why:** "no settings" and "settings not recorded" are different, and
  `TenantDao.create` writes the empty dict deliberately.

### DB-103 · `BoolInt` stores 0 and 1 and nothing else
- **Area:** `db/types.py::BoolInt`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `True`, `False`, `1`, `0`, `"yes"`
- **Steps:** persist each, read the raw integer
- **Expected:** exactly 0 or 1 in every case
- **Why:** the schema's `CHECK (col IN (0,1))` and this decorator are the two
  halves of one guarantee.

### DB-104 · `BoolInt` of `None` is NULL and reads back as `None`
- **Area:** `db/types.py::BoolInt`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a nullable boolean column
- **Steps:** persist `None`
- **Expected:** `None` back, not `False`
- **Why:** "not recorded" and "false" are different for `representative` and
  `snapshot_exact`.

### DB-105 · `PasswordHasher` produces the documented stored form
- **Area:** `db/security.py::PasswordHasher.hash`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** hash a password
- **Expected:** `pbkdf2_sha256$210000$<32 hex>$<64 hex>`
- **Why:** "the algorithm and the storage format are a single decision"; the
  format is what `needs_rehash` and `verify` both parse.

### DB-106 · The salt differs between two hashes of the same password
- **Area:** `db/security.py::PasswordHasher.hash`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** hash the same password twice
- **Expected:** different stored strings
- **Why:** a per-password random salt is the only defence against a rainbow
  table and against seeing that two users share a password.

### DB-107 · An iteration count below the floor is refused
- **Area:** `db/security.py::PasswordHasher.__init__`
- **Type:** security
- **Priority:** P1
- **Precondition:** `iterations=1000`
- **Steps:** construct
- **Expected:** `ValidationError` whose remedy states this is "a code-level
  floor, not a setting" and that nothing reads it from configuration
- **Why:** the remedy makes an explicit negative claim about configuration —
  verify no configuration key reaches this constructor.

### DB-108 · `verify` is true for the right password and false for a near miss
- **Area:** `db/security.py::PasswordHasher.verify`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a stored hash
- **Steps:** verify the password, the password with a trailing space, and a
  case-flipped variant
- **Expected:** true, false, false
- **Why:** the basic contract, and the counterfactual that it is not trivially
  true.

### DB-109 · A malformed stored hash returns False rather than raising
- **Area:** `db/security.py::PasswordHasher.verify`
- **Type:** negative
- **Priority:** P1
- **Precondition:** stored values `""`, `"garbage"`, `"a$b$c"`, `"pbkdf2_sha256$x$y$z"`
- **Steps:** verify
- **Expected:** `False` for all, no exception
- **Why:** "turning it into an exception on the authentication path converts a
  bad row into an outage".

### DB-110 · Verification is constant-time in the comparison
- **Area:** `db/security.py::PasswordHasher.verify`
- **Type:** security
- **Priority:** P2
- **Precondition:** none
- **Steps:** confirm `hmac.compare_digest` is used on the derived digest
- **Expected:** yes
- **Why:** a `==` on a hex digest is a timing oracle for the digest, which is
  weaker than for a password but still a leak.

### DB-111 · `needs_rehash` is true for a lower iteration count
- **Area:** `db/security.py::PasswordHasher.needs_rehash`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a hash made at 100,000 iterations, a hasher at 210,000
- **Steps:** call
- **Expected:** `True`
- **Why:** "old hashes verify at their own cost and are re-hashed on next
  successful login" — the whole reason the count travels with the hash.

### DB-112 · `needs_rehash` is true for a malformed or foreign hash
- **Area:** `db/security.py::PasswordHasher.needs_rehash`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `"bcrypt$..."`, `""`, a non-numeric iteration field
- **Steps:** call
- **Expected:** `True` in every case
- **Why:** an unparseable hash must be replaced at the next opportunity, not
  left as it is.

### DB-113 · An issued API key is prefixed, unique and never stored in clear
- **Area:** `db/security.py::ApiKeyIssuer.issue`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** issue a thousand keys
- **Expected:** every plaintext starts `pk_live_`, no duplicates, the stored form
  is `sha256:<64 hex>` and shares no substring with the plaintext beyond the
  prefix
- **Why:** "`plaintext` exists only in this object, is returned to the caller
  once, and is never persisted".

### DB-114 · The prefix is the first twelve characters and is indexable
- **Area:** `db/security.py::ApiKeyIssuer.PREFIX_LENGTH`, `prefix_of`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an issued key
- **Steps:** compare `issued.prefix` with `prefix_of(issued.plaintext)`
- **Expected:** equal, and long enough to be selective across environments
  (`pk_live_` is eight characters, leaving four of entropy)
- **Why:** "so a presented key can be located in one lookup without scanning
  every hash" — four characters of entropy is a lot of collisions at scale, and
  `uq_api_key_prefix` then refuses legitimate issuance.

### DB-115 · The environment label changes the prefix
- **Area:** `db/security.py::ApiKeyIssuer.issue`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `environment="test"`
- **Steps:** issue
- **Expected:** `pk_test_...`; the prefix differs from a live key's
- **Why:** a test key that looks like a live key is one that gets pasted into
  production.

### DB-116 · `verify` is constant-time and rejects a near-miss key
- **Area:** `db/security.py::ApiKeyIssuer.verify`
- **Type:** security
- **Priority:** P1
- **Precondition:** an issued key and its hash
- **Steps:** verify the key, and the key with its last character changed
- **Expected:** true, then false; `compare_digest` used
- **Why:** the authentication path runs on every request.

### DB-117 · The SHA-256 choice is documented and sufficient
- **Area:** `db/security.py::ApiKeyIssuer`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** measure the entropy of `secrets.token_urlsafe(32)`
- **Expected:** 256 bits, matching the docstring's claim that "a 256-bit random
  key has no guessable structure"
- **Why:** the argument for not using a slow KDF rests entirely on that number.

## DAOs — the base, tenancy and identity

### DB-118 · `Dao.get` on a missing id returns None
- **Area:** `db/dao/base.py::Dao.get`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an empty table
- **Steps:** `get(new_ulid())`
- **Expected:** `None`
- **Why:** the sentinel-free rule applies to *errors*; absence is a legitimate
  answer and must be distinguishable from failure.

### DB-119 · `Dao.require` on a missing id raises `NotFoundError`
- **Area:** `db/dao/base.py::Dao.require`
- **Type:** negative
- **Priority:** P1
- **Precondition:** as above
- **Steps:** `require(id)`
- **Expected:** `ENTITY.NOT_FOUND` naming the model and the id, remedy suggesting
  listing first
- **Why:** every route that resolves an identifier from a URL goes through it.

### DB-120 · `Dao.count` over an empty table is zero
- **Area:** `db/dao/base.py::Dao.count`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an empty table
- **Steps:** `count()`
- **Expected:** `0`, not `None`
- **Why:** `scalar_one` on a count subquery is the correct form; a coverage
  figure built on `None` renders as "unknown" and reads as broken.

### DB-121 · `Dao.count` of a filtered statement counts the filter
- **Area:** `db/dao/base.py::Dao.count`
- **Type:** functional
- **Priority:** P2
- **Precondition:** ten rows, three matching
- **Steps:** `count(select(...).where(...))`
- **Expected:** `3`
- **Why:** it wraps the statement in a subquery; an ignored `where` would make
  every coverage number the table size.

### DB-122 · `list_for_tenant` never returns another tenant's rows
- **Area:** `db/dao/base.py::TenantScopedDao.list_for_tenant`
- **Type:** security
- **Priority:** P1
- **Precondition:** two tenants with rows in each
- **Steps:** list for one
- **Expected:** only that tenant's
- **Why:** "Multi-tenancy enforced by discipline is multi-tenancy that leaks."

### DB-123 · `list_for_tenant` pages deterministically
- **Area:** `db/dao/base.py::TenantScopedDao.list_for_tenant`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** 25 rows
- **Steps:** page at limit 10, offsets 0, 10, 20
- **Expected:** no row appears twice and none is missed
- **Why:** it orders by `id`, and ULID ordering is what makes that stable — this
  is the store the ULID docstring means by "several stores rely on id order to
  page deterministically".

### DB-124 · `limit=0` returns nothing rather than everything
- **Area:** `db/dao/base.py::TenantScopedDao.list_for_tenant`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** rows present
- **Steps:** `list_for_tenant(t, limit=0)`
- **Expected:** an empty list
- **Why:** some drivers treat `LIMIT 0` as unlimited; an accidental full-table
  read is a latency incident.

### DB-125 · A negative limit or offset is refused
- **Area:** `db/dao/base.py::TenantScopedDao.list_for_tenant`
- **Type:** negative
- **Priority:** P2
- **Precondition:** rows present
- **Steps:** `limit=-1`, `offset=-1`
- **Expected:** a named refusal, not an engine error
- **Why:** the values come from API query parameters.

### DB-126 · `get_for_tenant` with the wrong tenant returns None
- **Area:** `db/dao/base.py::TenantScopedDao.get_for_tenant`
- **Type:** security
- **Priority:** P1
- **Precondition:** a row in tenant A
- **Steps:** `get_for_tenant(B, id)`
- **Expected:** `None`
- **Why:** the id alone must never be enough.

### DB-127 · `require_for_tenant` with the wrong tenant reports absence
- **Area:** `db/dao/base.py::TenantScopedDao.require_for_tenant`
- **Type:** security
- **Priority:** P1
- **Precondition:** as above
- **Steps:** `require_for_tenant(B, id)`
- **Expected:** `NotFoundError` — "does not exist in this tenant", not forbidden
- **Why:** the pattern used throughout: "which identifiers exist in another
  tenant is itself not this caller's business".

### DB-128 · `count_for_tenant` counts only that tenant
- **Area:** `db/dao/base.py::TenantScopedDao.count_for_tenant`
- **Type:** security
- **Priority:** P1
- **Precondition:** rows in two tenants
- **Steps:** count each
- **Expected:** the right numbers
- **Why:** a cross-tenant count discloses the size of another estate.

### DB-129 · `TenantDao.by_slug` finds and misses correctly
- **Area:** `db/dao/platform.py::TenantDao.by_slug`
- **Type:** functional
- **Priority:** P1
- **Precondition:** one tenant
- **Steps:** look up the slug and an unknown slug
- **Expected:** the tenant, then `None`
- **Why:** `run_prama_web.py --prepare` and `prama tenant create` both depend on
  the miss being `None` rather than an error.

### DB-130 · `TenantDao.create` stamps both timestamps
- **Area:** `db/dao/platform.py::TenantDao.create`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** create, read
- **Expected:** `created_at` equals `updated_at`, both UTC-aware
- **Why:** an unset `updated_at` on a `NOT NULL` column is an insert failure.

### DB-131 · `TenantDao.list_active` excludes other statuses
- **Area:** `db/dao/platform.py::TenantDao.list_active`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an active and a suspended tenant
- **Steps:** list
- **Expected:** only the active one, ordered by slug
- **Why:** a suspended estate that still appears is one somebody will sign into.

### DB-132 · A password shorter than twelve characters is refused
- **Area:** `db/dao/platform.py::PrincipalDao.set_password`, `MINIMUM_PASSWORD`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a principal
- **Steps:** set an 11-character and a 12-character password
- **Expected:** refused, then accepted
- **Why:** the boundary is exact and the remedy explains why there are no
  character-class rules.

### DB-133 · The password refusal does not echo the password
- **Area:** `db/dao/platform.py::PrincipalDao.set_password`
- **Type:** security
- **Priority:** P1
- **Precondition:** a short password
- **Steps:** read the error's context
- **Expected:** the username only
- **Why:** a rejected password is still a password somebody uses elsewhere.

### DB-134 · `set_password` stores only the hash and updates the timestamp
- **Area:** `db/dao/platform.py::PrincipalDao.set_password`
- **Type:** security
- **Priority:** P1
- **Precondition:** a principal
- **Steps:** set a password, inspect every column
- **Expected:** the plaintext appears nowhere; `updated_at` moves
- **Why:** the plaintext must not survive in an audit detail or a settings blob
  either.

### DB-135 · `authenticate` returns the principal on correct credentials
- **Area:** `db/dao/platform.py::PrincipalDao.authenticate`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an active principal with a password
- **Steps:** authenticate
- **Expected:** the principal; `last_login_at` set
- **Why:** the happy path, and `last_login_at` is what an audit asks for.

### DB-136 · Every failure mode returns the same `None`
- **Area:** `db/dao/platform.py::PrincipalDao.authenticate`
- **Type:** security
- **Priority:** P1
- **Precondition:** an unknown username, a wrong password, a disabled account, an
  account with no password
- **Steps:** authenticate each
- **Expected:** `None` in every case, indistinguishable to the caller
- **Why:** "'that account is disabled' tells an attacker the account exists".

### DB-137 · An unknown username costs the same as a known one
- **Area:** `db/dao/platform.py::PrincipalDao.authenticate`, `_DUMMY_HASH`
- **Type:** security
- **Priority:** P1
- **Precondition:** one real principal
- **Steps:** time 200 authentications against a known and an unknown username
- **Expected:** the distributions overlap; no order-of-magnitude difference
- **Why:** "an enumeration oracle built out of timing rather than wording".

### DB-138 · `_DUMMY_HASH` is computed once at import
- **Area:** `db/dao/platform.py`
- **Type:** performance
- **Priority:** P2
- **Precondition:** none
- **Steps:** confirm it is a module constant
- **Expected:** yes
- **Why:** "deriving it on every failed sign-in would double the cost of exactly
  the request an attacker floods".

### DB-139 · A successful login rehashes when the cost has risen
- **Area:** `db/dao/platform.py::PrincipalDao.authenticate`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a hash at 100,000 iterations
- **Steps:** authenticate with a 210,000-iteration hasher
- **Expected:** the stored hash is replaced; the password still verifies
- **Why:** "A rehash scheduled for 'later' is one that never runs."

### DB-140 · A non-active principal is refused even with the right password
- **Area:** `db/dao/platform.py::PrincipalDao.authenticate`
- **Type:** security
- **Priority:** P1
- **Precondition:** `status='disabled'` and `status='locked'`
- **Steps:** authenticate
- **Expected:** `None`; `last_login_at` unchanged
- **Why:** the status check is after the hash comparison, which is right for
  timing — confirm it still refuses, and that it does not stamp the login.

### DB-141 · `authenticate` is tenant-scoped
- **Area:** `db/dao/platform.py::PrincipalDao.by_username`
- **Type:** security
- **Priority:** P1
- **Precondition:** `alice` in two tenants with different passwords
- **Steps:** authenticate each with the other's password
- **Expected:** `None` both ways
- **Why:** a cross-tenant username lookup is a full authentication bypass.

### DB-142 · `by_external_id` is *not* tenant-scoped
- **Area:** `db/dao/platform.py::PrincipalDao.by_external_id`
- **Type:** security
- **Priority:** P1
- **Precondition:** two tenants each with a principal whose IdP is `okta` and
  whose external id collides
- **Steps:** look up by IdP and external id
- **Expected:** either a tenant argument is required, or the pair is proven
  globally unique by a constraint
- **Why:** it is the SSO sign-in path and takes no tenant; a collision across
  tenants signs the wrong person in.

### DB-143 · `any_for` is true only for an active principal
- **Area:** `db/dao/platform.py::PrincipalDao.any_for`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a tenant whose only principal is disabled
- **Steps:** call
- **Expected:** `False`
- **Why:** the sign-in page says "nobody has been created here yet"; a disabled
  account makes that message wrong but the underlying advice right — confirm
  which is intended.

### DB-144 · `roles_of` returns sorted roles and an empty list for an unknown id
- **Area:** `db/dao/platform.py::PrincipalDao.roles_of`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a principal with three roles; and an unknown id
- **Steps:** call both
- **Expected:** three sorted by name; then `[]`
- **Why:** the empty case must not raise — a session for a deleted principal is
  a real state.

### DB-145 · `roles_of` uses the declared relationship, not a hand-written join
- **Area:** `db/dao/platform.py::PrincipalDao.roles_of`
- **Type:** performance
- **Priority:** P3
- **Precondition:** a principal with ten roles
- **Steps:** count the queries issued
- **Expected:** a bounded number — `selectin` means one extra query per
  collection, not one per row
- **Why:** CLAUDE.md states the ORM convention; the `refresh(...,["roles"])` call
  is the place it could quietly become N+1.

### DB-146 · `RoleDao.grant` is idempotent
- **Area:** `db/dao/platform.py::RoleDao.grant`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a role already granted
- **Steps:** grant again
- **Expected:** one row; `granted_at` updated; no error
- **Why:** "A read-then-write existence check is not idempotency: it loses to a
  concurrent grant."

### DB-147 · Two concurrent grants produce one row
- **Area:** `db/dao/platform.py::RoleDao.grant`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** two units of work
- **Steps:** grant the same pair simultaneously
- **Expected:** one row, no `ConflictError` escaping to the caller
- **Why:** the upsert is the whole reason this method carries no engine-specific
  SQL of its own.

### DB-148 · `grant` works on both engines
- **Area:** `db/dao/platform.py::RoleDao.grant`, `db/dialects.py::upsert`
- **Type:** contract
- **Priority:** P1
- **Precondition:** both engines
- **Steps:** grant, re-grant
- **Expected:** identical outcome
- **Why:** the statement is dialect-generated; this is the only test that proves
  both forms parse.

### DB-149 · `revoke` of a grant that does not exist is a no-op
- **Area:** `db/dao/platform.py::RoleDao.revoke`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** no grant
- **Steps:** revoke
- **Expected:** no error, nothing changed
- **Why:** revocation is the operation somebody runs twice under pressure.

### DB-150 · `RoleDao.by_name` is tenant-scoped
- **Area:** `db/dao/platform.py::RoleDao.by_name`
- **Type:** security
- **Priority:** P1
- **Precondition:** a role named `admin` in two tenants
- **Steps:** look up in each
- **Expected:** the right one each time
- **Why:** a cross-tenant role lookup grants another estate's permissions.

### DB-151 · `RoleDao.create` stores permissions as a JSON list
- **Area:** `db/dao/platform.py::RoleDao.create`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** create with three permissions, read back
- **Expected:** the same list in the same order
- **Why:** `tests/architecture/test_scopes.py` compares granted permissions with
  declared scopes; an order or type change breaks that comparison.

### DB-152 · A built-in role is marked and a custom one is not
- **Area:** `db/dao/platform.py::RoleDao.create`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** one of each
- **Steps:** read `is_builtin`
- **Expected:** `True` and `False`, stored as 1 and 0
- **Why:** the flag is what stops a console from offering to delete a system role.

### DB-153 · `ApiKeyDao.by_prefix` is not tenant-scoped, deliberately
- **Area:** `db/dao/platform.py::ApiKeyDao.by_prefix`
- **Type:** security
- **Priority:** P1
- **Precondition:** keys in two tenants
- **Steps:** look up a prefix
- **Expected:** the key, and the caller establishes the tenant *from* it rather
  than supplying it
- **Why:** authentication cannot know the tenant before the key is resolved —
  confirm that every caller then uses the key's own tenant and never a supplied
  one.

### DB-154 · `active_for_principal` excludes revoked keys
- **Area:** `db/dao/platform.py::ApiKeyDao.active_for_principal`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two keys, one revoked
- **Steps:** list
- **Expected:** one
- **Why:** a revoked key shown as active is a credential somebody believes is
  gone.

### DB-155 · `active_for_principal` does not filter on expiry
- **Area:** `db/dao/platform.py::ApiKeyDao.active_for_principal`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a key whose `expires_at` is in the past and which is not
  revoked
- **Steps:** list, and then authenticate with it
- **Expected:** the listing's meaning of "active" is documented, and
  authentication refuses the expired key
- **Why:** the method name promises active; the query only checks `revoked_at`.

### DB-156 · `AuditDao` exposes no update or delete
- **Area:** `db/dao/platform.py::AuditDao`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** enumerate the public methods
- **Expected:** `record`, `for_object`, `recent` and the inherited reads only —
  and confirm the inherited `Dao.delete` is either overridden or unreachable
- **Why:** the class says "Append-only. This class deliberately exposes no update
  or delete" while inheriting `Dao.delete`, which `EvidenceDao` and
  `AttestationDao` both had to override explicitly.

### DB-157 · `record` stamps the occurrence time itself
- **Area:** `db/dao/platform.py::AuditDao.record`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** record an event
- **Expected:** `occurred_at` from `utc_now()`, not from the caller
- **Why:** a caller-supplied audit timestamp is an audit trail that can be
  backdated.

### DB-158 · `record` defaults outcome and actor kind
- **Area:** `db/dao/platform.py::AuditDao.record`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** minimal arguments
- **Steps:** record
- **Expected:** `outcome='success'`, `actor_kind='human'`, `detail_json={}`
- **Why:** every column is `NOT NULL`; a default that is `None` is an insert
  failure at the moment something needs auditing.

### DB-159 · `for_object` and `recent` are tenant-scoped and newest first
- **Area:** `db/dao/platform.py::AuditDao`
- **Type:** security
- **Priority:** P1
- **Precondition:** events in two tenants
- **Steps:** call both
- **Expected:** only the caller's tenant, ordered by `occurred_at` descending
- **Why:** an audit log is exactly what must not cross an estate boundary.

### DB-160 · Two audit events in the same microsecond order deterministically
- **Area:** `db/dao/platform.py::AuditDao.recent`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** two events with identical `occurred_at`
- **Steps:** list
- **Expected:** a stable order across repeated queries
- **Why:** ordering by a single non-unique column gives the engine a free choice,
  and an audit page that reorders itself on refresh is one nobody trusts.

### DB-161 · `SettingDao.put` is an atomic upsert
- **Area:** `db/dao/platform.py::SettingDao.put`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** two units of work
- **Steps:** write the same key concurrently
- **Expected:** one row, the last value, no conflict escaping
- **Why:** "Atomic upsert, not read-then-write."

### DB-162 · `get_value` returns the default for a missing key
- **Area:** `db/dao/platform.py::SettingDao.get_value`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** no such key
- **Steps:** `get_value(..., default={"a": 1})`
- **Expected:** the default
- **Why:** the alternative is a `None` that every caller then has to handle.

### DB-163 · A setting round-trips a nested structure
- **Area:** `db/dao/platform.py::SettingDao`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** put a nested dict, get it back
- **Expected:** equal — `put` writes through `pjson.dumps(sort_keys=True)` and
  the column reads through `JsonText`
- **Why:** the write path bypasses the ORM type and the read path does not; a
  mismatch would show as a double-encoded string.

### DB-164 · Settings are scoped by tenant and by scope
- **Area:** `db/dao/platform.py::SettingDao`
- **Type:** security
- **Priority:** P1
- **Precondition:** the same key under two scopes and two tenants
- **Steps:** read each
- **Expected:** four distinct values; `all_for_scope` returns only its own
- **Why:** a settings leak across tenants is a configuration disclosure.

### DB-165 · Putting `None` as a value stores JSON null, readably
- **Area:** `db/dao/platform.py::SettingDao.put`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** `put(..., None)`, then `get_value(..., default="d")`
- **Expected:** a defined answer — either `None` or the default, documented
- **Why:** `pjson.dumps(None)` is the string `"null"`, which reads back as `None`
  and is then indistinguishable from a missing row.

## DAOs — the bitemporal protocol

### DB-166 · `create` writes an identity row and version 1
- **Area:** `db/dao/versioned.py::VersionedDao.create`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a tenant
- **Steps:** create a dataset declaration
- **Expected:** one identity row; one version with `version=1`,
  `valid_to IS NULL`, `superseded_at IS NULL`
- **Why:** every semantic object is created through this one path.

### DB-167 · `create` with an explicit `valid_from` honours it
- **Area:** `db/dao/versioned.py::create`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a backdated `valid_from`
- **Steps:** create, then `valid_at` just after it and just before it
- **Expected:** found, then not found
- **Why:** backfilling a declaration that was true before Prama existed is a
  real operation.

### DB-168 · `amend` closes the old version and opens a new one
- **Area:** `db/dao/versioned.py::amend`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a current version
- **Steps:** amend with a change
- **Expected:** old version `valid_to = effective`, new version `version=2`,
  `valid_from = effective`, `valid_to IS NULL`, neither superseded
- **Why:** "Both versions remain true, of their own periods."

### DB-169 · `correct` supersedes without touching validity
- **Area:** `db/dao/versioned.py::correct`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a current version with a validity period
- **Steps:** correct it
- **Expected:** old `superseded_at` set, `valid_from`/`valid_to` unchanged on
  both; new version inherits the period
- **Why:** "Conflating amend and correct is the single most common bitemporal
  defect, and it is unrecoverable after the fact."

### DB-170 · A correction does not change what an earlier `as_of` returns
- **Area:** `db/dao/versioned.py::as_of`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a version recorded at T1, corrected at T2
- **Steps:** `as_of(valid_at=T1.5, known_at=T1.5)`
- **Expected:** the mistaken version
- **Why:** "An evidence record produced while the mistake stood still resolves to
  the mistaken version, which is what makes the replay honest."

### DB-171 · `valid_at` reflects the correction
- **Area:** `db/dao/versioned.py::valid_at`
- **Type:** functional
- **Priority:** P1
- **Precondition:** as above
- **Steps:** `valid_at(T1.5)` today
- **Expected:** the corrected version
- **Why:** "the usual historical question … asked with the benefit of any
  corrections made since" — the two reads must differ, and that difference is
  the whole point of two axes.

### DB-172 · Amending with an effective date before the current version began is refused
- **Area:** `db/dao/versioned.py::amend`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a version valid from 1 April
- **Steps:** amend effective 1 March
- **Expected:** `ConflictError` whose remedy suggests correcting the earlier
  version instead
- **Why:** it would otherwise produce a version with `valid_to < valid_from`,
  which no query can interpret.

### DB-173 · Amending exactly at `valid_from` is allowed and produces a zero-length period
- **Area:** `db/dao/versioned.py::amend`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a version valid from T
- **Steps:** amend effective exactly T
- **Expected:** accepted; the old version has `valid_from == valid_to`; `valid_at(T)`
  resolves to the new version only
- **Why:** the comparison is `<`, so the boundary is inclusive — confirm the
  zero-length period does not make two versions match at T.

### DB-174 · Amending a non-existent entity raises `NotFoundError`
- **Area:** `db/dao/versioned.py::amend`
- **Type:** negative
- **Priority:** P1
- **Precondition:** an unknown id
- **Steps:** amend
- **Expected:** "has no current version to amend", remedy "Create the declaration
  before amending it"
- **Why:** the alternative is a `None` dereference deep in `_clone`.

### DB-175 · Amending another tenant's entity raises `NotFoundError`
- **Area:** `db/dao/versioned.py::_scoped`
- **Type:** security
- **Priority:** P1
- **Precondition:** an entity in tenant A
- **Steps:** amend it as tenant B
- **Expected:** not found
- **Why:** adversarial review finding S2 — "these methods previously took only an
  id, so any caller holding an identifier from another estate read and wrote
  another tenant's rows". Write the counterfactual.

### DB-176 · Every read on `VersionedDao` requires a tenant
- **Area:** `db/dao/versioned.py`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** inspect the signature of `current`, `require_current`, `valid_at`,
  `as_of`, `history`, `list_current`, `count_current`, `amend`, `correct`,
  `retire`
- **Expected:** every one takes `tenant_id`
- **Why:** "a scope you have to remember is not a scope" — and one new method
  without it re-opens S2.

### DB-177 · `tenant_of` is never used to satisfy a caller-supplied tenant
- **Area:** `db/dao/versioned.py::tenant_of`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** find every call site
- **Expected:** only trusted local paths (the CLI); never an API route
- **Why:** the docstring says using it that way "turns the scope into a
  tautology", which is a complete bypass of tenant isolation.

### DB-178 · Exactly one current version exists after an amend
- **Area:** `db/dao/versioned.py::amend`, the `uq_*_current` index
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** a current version
- **Steps:** amend, then query for rows with both temporal columns null
- **Expected:** exactly one
- **Why:** the explicit `flush()` before inserting the successor exists because
  "the flush order is otherwise the ORM's business rather than ours" — remove it
  and the partial unique index fires.

### DB-179 · Two concurrent amendments do not both succeed
- **Area:** `db/dao/versioned.py::amend`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** two units of work on one entity
- **Steps:** amend simultaneously
- **Expected:** one succeeds; the other gets a `ConflictError`
- **Why:** two current versions is a declaration with two meanings, which no read
  can disambiguate.

### DB-180 · `_clone` refuses an unknown field
- **Area:** `db/dao/versioned.py::_clone`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a current version
- **Steps:** `amend(..., grian="x")` (a typo)
- **Expected:** `ConflictError` listing the unknown names, remedy "a typo here
  would silently change nothing"
- **Why:** a silently ignored change is an amendment that claims to have happened
  and did not.

### DB-181 · `_clone` excludes the bitemporal and identity columns
- **Area:** `db/dao/versioned.py::_clone`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a version with approvals and a change reason
- **Steps:** amend
- **Expected:** the successor has a fresh `id`, `version`, timestamps and
  provenance — none inherited
- **Why:** "getting one of them wrong here would be invisible and permanent".

### DB-182 · Provenance is applied to every new version
- **Area:** `db/dao/versioned.py`, `db/temporal.py::Provenance.apply_to`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an amend with author, approver and reason
- **Steps:** read the new version
- **Expected:** all three present
- **Why:** "an unexplained change to a Tier-1 declaration is an audit finding".

### DB-183 · Omitting provenance clears rather than inherits it
- **Area:** `db/dao/versioned.py::amend`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a version approved by Bob
- **Steps:** amend with no provenance
- **Expected:** the successor is unapproved
- **Why:** `Provenance()` is applied with all-`None` fields; inheriting an
  approval onto an unreviewed change would be the dangerous alternative, so
  confirm the safe one happens.

### DB-184 · `retire` ends validity without deleting
- **Area:** `db/dao/versioned.py::retire`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a current version
- **Steps:** retire, then `current` and `history`
- **Expected:** `current` is `None`; the version is still in history with
  `valid_to` set
- **Why:** "a retired dataset's history is still needed to interpret evidence
  produced while it existed".

### DB-185 · `retire` of an absent entity returns None rather than raising
- **Area:** `db/dao/versioned.py::retire`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an unknown id
- **Steps:** retire
- **Expected:** `None`
- **Why:** it is the only mutation that returns `None` instead of raising —
  confirm the asymmetry with `amend` and `correct` is deliberate.

### DB-186 · `history` is oldest first and includes superseded versions
- **Area:** `db/dao/versioned.py::history`, `TemporalQuery.all_versions`
- **Type:** functional
- **Priority:** P1
- **Precondition:** create, amend, correct
- **Steps:** read the history
- **Expected:** three versions ordered by `recorded_at` then `version`, including
  the superseded one
- **Why:** "Every version, oldest first — the audit view."

### DB-187 · `history` of an unknown entity is an empty list
- **Area:** `db/dao/versioned.py::history`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an unknown id
- **Steps:** call
- **Expected:** `[]`, no error
- **Why:** a history screen for a deleted bookmark must not 500.

### DB-188 · `list_current` pages and excludes retired entities
- **Area:** `db/dao/versioned.py::list_current`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** 25 entities, three retired
- **Steps:** page through
- **Expected:** 22 across the pages, none repeated
- **Why:** a coverage number built on `list_current` counts what is live.

### DB-189 · `count_current` agrees with `list_current`
- **Area:** `db/dao/versioned.py::count_current`
- **Type:** contract
- **Priority:** P2
- **Precondition:** as above
- **Steps:** compare
- **Expected:** equal
- **Why:** two numbers for one question on one screen is the first thing a
  reviewer notices.

### DB-190 · `TemporalQuery.current` excludes both closed and superseded
- **Area:** `db/temporal.py::TemporalQuery.current`
- **Type:** contract
- **Priority:** P1
- **Precondition:** four version rows covering each combination
- **Steps:** run the predicate
- **Expected:** only the one with both null
- **Why:** "Hand-written `WHERE superseded_at IS NULL` clauses scattered through
  a codebase are how a bitemporal store quietly starts returning superseded rows
  in one query out of forty."

### DB-191 · `Versioned.was_valid_at` is half-open
- **Area:** `db/temporal.py::Versioned.was_valid_at`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a version valid `[T1, T2)`
- **Steps:** test T1-ε, T1, T2-ε, T2, T2+ε
- **Expected:** false, true, true, false, false
- **Why:** two adjacent versions must not both match at the boundary, or a
  temporal read returns two rows and `one_or_none` raises.

### DB-192 · `was_believed_at` is half-open in the same direction
- **Area:** `db/temporal.py::Versioned.was_believed_at`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a version recorded at T1, superseded at T2
- **Steps:** the same five points
- **Expected:** the same pattern
- **Why:** an inconsistency between the two axes makes `held_at` wrong at exactly
  the moment a correction landed.

### DB-193 · `as_of` returns at most one row at every point
- **Area:** `db/temporal.py::TemporalQuery.as_of`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a history of create, amend, correct
- **Steps:** sweep both axes over a grid of instants
- **Expected:** never more than one row
- **Why:** `as_of` uses `.first()` rather than `one_or_none()`, which hides a
  multiple match rather than reporting it.

### DB-194 · `is_current` on the model agrees with the SQL predicate
- **Area:** `db/temporal.py::Versioned.is_current`, `TemporalQuery.current`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a mixed set of versions
- **Steps:** compare the Python property with the query result
- **Expected:** identical membership
- **Why:** two implementations of "current" is how a screen and a certificate
  disagree.

## DAOs — the semantic layer, controls, evidence and the rest

### DB-195 · Every semantic DAO declares its model triple correctly
- **Area:** `db/dao/semantic.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** for each of the nine DAOs check `model`, `version_model` and
  `entity_key` against the ORM's foreign key
- **Expected:** consistent; `entity_key` names a real column on the version model
- **Why:** a mismatched `entity_key` makes `_scoped` join on nothing and return
  every row in the tenant.

### DB-196 · Every semantic by-slug and by-name lookup is tenant-scoped
- **Area:** `db/dao/semantic.py`
- **Type:** security
- **Priority:** P1
- **Precondition:** the same slug in two tenants
- **Steps:** look up in each
- **Expected:** the right row each time
- **Why:** these are the lookups a URL path segment resolves to.

### DB-197 · A by-slug lookup that misses returns None
- **Area:** `db/dao/semantic.py`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an unknown slug
- **Steps:** call each
- **Expected:** `None`
- **Why:** they use `one_or_none`; a duplicate slug within a tenant would raise
  instead, so confirm the uniqueness that makes the miss well-defined.

### DB-198 · `AttributeDao.for_dataset` refuses another tenant's dataset id
- **Area:** `db/dao/semantic.py::AttributeDao.for_dataset`
- **Type:** security
- **Priority:** P1
- **Precondition:** a dataset in tenant A with attributes
- **Steps:** call with tenant B and A's dataset id
- **Expected:** an empty list
- **Why:** QA finding F-02 — these by-parent reads "took a parent id and nothing
  else, so a caller holding an identifier from another estate read that estate's
  rows in full — a 200 with the data, not a 404". Write the counterfactual.

### DB-199 · `ConceptPropertyDao.for_concept` is tenant-scoped
- **Area:** `db/dao/semantic.py::ConceptPropertyDao.for_concept`
- **Type:** security
- **Priority:** P1
- **Precondition:** as above
- **Steps:** cross-tenant call
- **Expected:** empty
- **Why:** the same finding; one of the four methods it names.

### DB-200 · `BindingDao.for_dataset` and `for_attribute` are tenant-scoped
- **Area:** `db/dao/semantic.py::BindingDao`
- **Type:** security
- **Priority:** P1
- **Precondition:** bindings in two tenants
- **Steps:** cross-tenant calls
- **Expected:** empty and `None`
- **Why:** a binding carries the physical target — a connection, a schema and a
  table name — which is the most sensitive thing in the semantic layer.

### DB-201 · `AttributeDao.mapped_to_property` is not tenant-scoped
- **Area:** `db/dao/semantic.py::AttributeDao.mapped_to_property`
- **Type:** security
- **Priority:** P1
- **Precondition:** two tenants whose attributes map to the same property id
- **Steps:** call with the property id
- **Expected:** either a tenant argument is required, or the method is proven
  unreachable from any caller-supplied input
- **Why:** it is the fifth by-parent read on the same class and takes no tenant —
  the sweep in `tests/security/test_tenant_isolation.py` cannot see it because
  its first parameter is not `tenant_id`, which is exactly how F-02 hid.

### DB-202 · `DatasetDao.unbound` lists declared-but-unconnected datasets
- **Area:** `db/dao/semantic.py::DatasetDao.unbound`
- **Type:** functional
- **Priority:** P1
- **Precondition:** three datasets, one with `shape='unbound'`
- **Steps:** call
- **Expected:** the one
- **Why:** "the gaps between what the business says exists and what Prama can
  actually reach. No physical-first tool can produce this list at all."

### DB-203 · `DatasetDao.by_criticality` filters exactly
- **Area:** `db/dao/semantic.py::DatasetDao.by_criticality`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** datasets at tiers 1 to 4
- **Steps:** call for each tier and for an out-of-range tier
- **Expected:** exact matches; empty for the out-of-range tier
- **Why:** "tier 1 or better" is what a reader assumes; confirm the method is
  equality and that its callers know.

### DB-204 · `critical_data_elements` returns only CDEs and only in the tenant
- **Area:** `db/dao/semantic.py::AttributeDao.critical_data_elements`
- **Type:** security
- **Priority:** P1
- **Precondition:** CDEs in two tenants
- **Steps:** call for one
- **Expected:** only that tenant's
- **Why:** CDEs "attract the strictest controls, mandatory attestation and the
  longest evidence retention" — the population must be right.

### DB-205 · `RelationshipDao.touching` matches either side
- **Area:** `db/dao/semantic.py::RelationshipDao.touching`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a relationship from A to B
- **Steps:** call for A and for B
- **Expected:** found both times
- **Why:** "the estate map's edge query, and the starting point for both impact
  analysis and root-cause navigation" — a one-sided match halves the blast
  radius.

### DB-206 · `RelationshipDao.confirmed` excludes proposed relationships
- **Area:** `db/dao/semantic.py::RelationshipDao.confirmed`
- **Type:** security
- **Priority:** P1
- **Precondition:** one confirmed and one proposed relationship
- **Steps:** call
- **Expected:** one
- **Why:** "Only confirmed relationships may generate activatable controls" — a
  proposed one that slipped through would activate a control nobody approved.

### DB-207 · `JourneyDao.containing` finds a dataset inside a journey
- **Area:** `db/dao/semantic.py::JourneyDao.containing`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a journey listing three datasets
- **Steps:** call for one of them and for an unrelated one
- **Expected:** found, then empty
- **Why:** "the blast radius, in business terms".

### DB-208 · `JourneyDao.containing` does not silently truncate
- **Area:** `db/dao/semantic.py::JourneyDao.containing`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** more than 10,000 journeys in a tenant
- **Steps:** call for a dataset in the 10,001st
- **Expected:** found, or a documented ceiling
- **Why:** it loads `list_current(limit=10_000)` and filters in Python; past the
  limit the answer silently becomes "no journeys are affected".

### DB-209 · `ConnectionDao.unhealthy` has the same ceiling
- **Area:** `db/dao/semantic.py::ConnectionDao.unhealthy`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** as above
- **Steps:** call
- **Expected:** a complete answer or a stated limit
- **Why:** an operations screen that says all connections are healthy because the
  broken one is number 10,001 is the flattering failure.

### DB-210 · `BindingDao.drifted` finds all three drift states
- **Area:** `db/dao/semantic.py::BindingDao.drifted`
- **Type:** functional
- **Priority:** P1
- **Precondition:** bindings in `missing`, `retyped`, `renamed` and `ok`
- **Steps:** call
- **Expected:** the first three
- **Why:** "Each one is an incident for the business owner of the declaration" —
  a state omitted from the list is an incident nobody raises.

### DB-211 · `ControlDao.declare` stores a control and derives its fields
- **Area:** `db/dao/control.py::declare`, `derived_fields`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a tenant, valid PQL
- **Steps:** declare
- **Expected:** `name`, `dataset`, `severity`, `dimensions_json`, `content_hash`
  and `plan_id` all derived from the text, not from arguments
- **Why:** "A caller who could supply a severity could store a control whose text
  says `SEVERITY minor` and whose row says `critical` — and the row is what the
  alert router reads."

### DB-212 · A caller cannot override a derived field
- **Area:** `db/dao/control.py::declare`
- **Type:** security
- **Priority:** P1
- **Precondition:** valid PQL with `SEVERITY minor`
- **Steps:** attempt to pass `severity="critical"` through every route into
  `declare`
- **Expected:** impossible — `**fields` is applied last
- **Why:** the whole file is shaped by this rule; the test is that no keyword
  path defeats it.

### DB-213 · Unparseable PQL is refused rather than stored
- **Area:** `db/dao/control.py::derived_fields`
- **Type:** negative
- **Priority:** P1
- **Precondition:** malformed PQL
- **Steps:** declare
- **Expected:** `ValidationError` quoting the PQL error, remedy explaining that
  storing it "would hide that until it was due to run"
- **Why:** "an estate containing a control nothing can execute, discovered at run
  time by a scheduler with nowhere to report it".

### DB-214 · PQL that parses but cannot be lowered is stored with an empty plan id
- **Area:** `db/dao/control.py::derived_fields`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a control using a feature this build cannot lower
- **Steps:** declare, read `plan_id`
- **Expected:** `""`, the control stored, and the empty plan id visible somewhere
  an operator looks
- **Why:** the comment says the loss "is visible as an empty plan_id rather than
  as a control that quietly never runs" — confirm something actually surfaces it.

### DB-215 · `declare` is idempotent by identity, not by text
- **Area:** `db/dao/control.py::declare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a declared control
- **Steps:** declare the same identity with identical text, then with changed text
- **Expected:** no new version, then a new version
- **Why:** "re-running a generator after a threshold changed amends the control,
  and re-running it after nothing changed does nothing at all".

### DB-216 · An unchanged re-declaration does not touch the timestamps
- **Area:** `db/dao/control.py::declare`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a declared control
- **Steps:** re-declare identically, compare every column
- **Expected:** nothing changed
- **Why:** "Writing a new version anyway would fill the history with entries that
  differ only in their timestamp, and make a genuine change impossible to find in
  the diff."

### DB-217 · A whitespace-only change to the PQL does not create a version
- **Area:** `db/dao/control.py::derived_fields`, `content_hash`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a declared control
- **Steps:** re-declare with reindented but semantically identical PQL
- **Expected:** no new version — the hash is over `control.render()`, the
  canonical form, not the input text
- **Why:** a generator that reformats would otherwise amend every control every
  night.

### DB-218 · `activate` is an amend, not a correct
- **Area:** `db/dao/control.py::activate`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a proposed control
- **Steps:** activate, then read the history
- **Expected:** two versions; the proposal is still valid for its own period and
  is not superseded
- **Why:** "The control genuinely was a proposal until somebody approved it."

### DB-219 · `activate` records the approver
- **Area:** `db/dao/control.py::activate`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** activate with `approved_by`
- **Expected:** `approved_by` set on the new version
- **Why:** a control that started running with no named approver is an audit
  finding.

### DB-220 · `suppress` requires both an expiry and a reason
- **Area:** `db/dao/control.py::suppress`
- **Type:** negative
- **Priority:** P1
- **Precondition:** an active control
- **Steps:** suppress with an empty `until`, then an empty `because`, then
  whitespace in each
- **Expected:** refused in all four cases
- **Why:** "a control muted with neither is one nobody turns back on, and the
  estate stops checking something without anyone deciding to".

### DB-221 · A suppressed control is excluded from `live`
- **Area:** `db/dao/control.py::live`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an active, a proposed and a suppressed control
- **Steps:** `live`
- **Expected:** one
- **Why:** "both are states a reader mistakes for running, and a coverage figure
  that counted them would claim protection the estate does not have".

### DB-222 · `silenced_past_expiry` names controls nobody re-enabled
- **Area:** `db/dao/control.py::silenced_past_expiry`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a control suppressed until yesterday
- **Steps:** call with today
- **Expected:** the control; and it is still suppressed, not automatically
  re-enabled
- **Why:** "turning a control back on by itself would surprise whoever silenced
  it, and leaving it silent for ever is how 'temporary' becomes permanent".

### DB-223 · `silenced_past_expiry` compares ISO text correctly
- **Area:** `db/dao/control.py::silenced_past_expiry`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** suppressions expiring an hour ago, in an hour, and exactly now
- **Steps:** call
- **Expected:** the past one and the exact one (the comparison is `<=`)
- **Why:** the column is text; a caller passing a date-only string against a
  full timestamp compares wrongly at the boundary.

### DB-224 · `retire` keeps the control and its evidence attributable
- **Area:** `db/dao/control.py::retire`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a control with evidence
- **Steps:** retire, then look up the evidence's control id
- **Expected:** the control still resolves
- **Why:** "a record naming a control that no longer exists is an audit trail
  with a hole in it".

### DB-225 · `RejectionDao.was_rejected` keys on identity and content
- **Area:** `db/dao/control.py::RejectionDao.was_rejected`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a rejected proposal
- **Steps:** ask about the same content, then about a rewritten version
- **Expected:** true, then false
- **Why:** "rejecting a control does not reject every future version of it. A
  materially different rewrite … is a new question and deserves to be asked
  again."

### DB-226 · `was_rejected` is tenant-scoped
- **Area:** `db/dao/control.py::RejectionDao.was_rejected`
- **Type:** security
- **Priority:** P2
- **Precondition:** the same identity rejected in another tenant
- **Steps:** ask in this tenant
- **Expected:** false
- **Why:** another estate's rejection must not suppress a proposal here.

### DB-227 · A rejection with no content hash does not suppress everything
- **Area:** `db/dao/control.py::RejectionDao.record`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a rejection recorded with the default `content_hash=""`
- **Steps:** `was_rejected(identity, actual_hash)`
- **Expected:** false — an empty hash matches nothing
- **Why:** the default is empty and the comparison is equality; a caller that
  omitted the hash gets a rejection that never fires, which is safer than one
  that fires always but must be known.

### DB-228 · Appending evidence takes the sequence and previous hash from the ledger
- **Area:** `db/dao/evidence.py::EvidenceDao.append`
- **Type:** security
- **Priority:** P1
- **Precondition:** a chain at sequence 4
- **Steps:** append a record whose own `sequence` and `previous_hash` are set to
  nonsense
- **Expected:** stored at 5 with the real head hash
- **Why:** "A caller that could choose them could write a record that looked
  linked and was not."

### DB-229 · An append with no tenant is refused
- **Area:** `db/dao/evidence.py::append`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a record with an empty `tenant_id`
- **Steps:** append with no tenant argument
- **Expected:** `ConflictError` — "an evidence record needs a tenant"
- **Why:** a tenantless record joins no chain and is invisible to every read.

### DB-230 · `head` on an empty chain is GENESIS
- **Area:** `db/dao/evidence.py::head`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a tenant with no records
- **Steps:** `head`
- **Expected:** `GENESIS`
- **Why:** the first record must link to a defined value, and an empty string
  would make two different empty chains verify identically.

### DB-231 · `next_sequence` on an empty chain is 0
- **Area:** `db/dao/evidence.py::next_sequence`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** as above
- **Steps:** call
- **Expected:** `0`
- **Why:** an off-by-one here shifts every sequence in the chain and breaks the
  unique index's meaning.

### DB-232 · Chains are per tenant and do not interleave
- **Area:** `db/dao/evidence.py`
- **Type:** security
- **Priority:** P1
- **Precondition:** two tenants appending alternately
- **Steps:** append ten each, then verify both
- **Expected:** each chain is 0..9 and verifies independently
- **Why:** `max(sequence)` is filtered by tenant; a global sequence would make
  one tenant's write break another's chain.

### DB-233 · `verify` detects tampered content
- **Area:** `db/dao/evidence.py::verify`, `_as_stored`
- **Type:** security
- **Priority:** P1
- **Precondition:** a valid chain, then one row's `detail` edited by raw SQL
- **Steps:** `verify`
- **Expected:** failure naming the sequence
- **Why:** the `_as_stored` docstring records that reconstructing through
  `EvidenceRecord` "hashes whatever it currently holds — tampered content
  included — and every check would pass. That defect was written, shipped into
  this file, and caught by the tampering test."

### DB-234 · `chain` and `as_stored` differ in exactly the documented way
- **Area:** `db/dao/evidence.py::chain`, `as_stored`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a tampered row
- **Steps:** read both
- **Expected:** `chain` returns a record whose recomputed hash matches its
  content; `as_stored` returns the stored hash beside the tampered content
- **Why:** the distinction is the whole tamper-evidence mechanism.

### DB-235 · `delete` on an evidence record is refused
- **Area:** `db/dao/evidence.py::EvidenceDao.delete`
- **Type:** security
- **Priority:** P1
- **Precondition:** a record
- **Steps:** `delete`
- **Expected:** `ConflictError` naming the sequence, remedy pointing at `erase()`
  and at archive-then-truncate
- **Why:** "a method inherited from `Dao` that nobody wrote for this class, that
  does exactly what a caller under time pressure wants, and that would look
  entirely reasonable in review".

### DB-236 · `erase` blanks content and keeps the chain verifiable
- **Area:** `db/dao/evidence.py::erase`
- **Type:** security
- **Priority:** P1
- **Precondition:** a chain of five with a record at sequence 2
- **Steps:** erase 2, then verify the whole chain
- **Expected:** verifies; the record carries a tombstone; `content_hash` and
  `record_hash` are unchanged
- **Why:** "the original content hash is preserved, so everything before and
  after still links and the erasure is visible as a tombstone rather than as a
  hole nobody can account for".

### DB-237 · `erase` of a missing sequence reports it as a finding
- **Area:** `db/dao/evidence.py::erase`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a gap in the sequence
- **Steps:** erase the gap
- **Expected:** `NotFoundError` whose remedy says "a gap is itself a finding
  worth investigating"
- **Why:** the remedy turns a routine miss into the question that matters.

### DB-238 · Erasing twice is safe
- **Area:** `db/dao/evidence.py::erase`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an already-erased record
- **Steps:** erase again
- **Expected:** either idempotent or refused; never a hash change
- **Why:** the two `assert` statements at the end of `erase` compare the stored
  hashes with the recomputed ones of an already-erased record — a second erase
  must not trip them, and an `assert` is stripped under `python -O`.

### DB-239 · The erasure assertions are not the only guard
- **Area:** `db/dao/evidence.py::erase`
- **Type:** security
- **Priority:** P1
- **Precondition:** the process run with `-O`
- **Steps:** erase a record
- **Expected:** the hashes are still protected
- **Why:** `assert row.content_hash == erased.content_hash` is the stated
  protection for the chain and it disappears under optimisation.

### DB-240 · `in_period` is inclusive at both ends and ordered by sequence
- **Area:** `db/dao/evidence.py::in_period`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** records at the exact start and end instants
- **Steps:** call
- **Expected:** both included, ordered by sequence
- **Why:** "Sorting by timestamp would give a different root for the same set
  whenever two records finished in the same second."

### DB-241 · `period_root` is stable for the same period
- **Area:** `db/dao/evidence.py::period_root`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a period of records
- **Steps:** compute twice
- **Expected:** identical root and count
- **Why:** an attestation binds itself to this value; a root that varied would
  invalidate every signature.

### DB-242 · `period_root` over an empty period is defined
- **Area:** `db/dao/evidence.py::period_root`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a period with no records
- **Steps:** call
- **Expected:** a defined root and a count of zero — and an attestation built on
  it says so
- **Why:** an attestation over nothing that printed a plausible root would be the
  dishonest artefact `report/attestation.py` exists to prevent.

### DB-243 · `failing` includes error, skipped and indeterminate
- **Area:** `db/dao/evidence.py::failing`
- **Type:** functional
- **Priority:** P1
- **Precondition:** one record of each verdict
- **Steps:** call
- **Expected:** four records, not one
- **Why:** "a list of 'problems' that quietly omitted it would report the
  controls that did run as though they were all of them".

### DB-244 · `for_control` is not tenant-scoped
- **Area:** `db/dao/evidence.py::for_control`
- **Type:** security
- **Priority:** P1
- **Precondition:** two tenants; a control id known to a caller in one
- **Steps:** call with the other tenant's control id
- **Expected:** either a tenant argument is required, or control ids are proven
  globally unique and unguessable
- **Why:** it is the same shape as F-02 — an unscoped by-parent read whose first
  parameter is not `tenant_id`, so the isolation sweep does not probe it.

### DB-245 · `for_run` is not tenant-scoped
- **Area:** `db/dao/evidence.py::for_run`
- **Type:** security
- **Priority:** P1
- **Precondition:** two tenants with runs
- **Steps:** call with another tenant's run id
- **Expected:** as above
- **Why:** the same finding shape on the same class.

### DB-246 · `latest_per_control` counts each control once
- **Area:** `db/dao/evidence.py::latest_per_control`
- **Type:** functional
- **Priority:** P1
- **Precondition:** one control with sixty records and one with one
- **Steps:** call
- **Expected:** two entries
- **Why:** "A scorecard built from every record would weight a control that runs
  hourly sixty times as heavily as one that runs daily, which measures the
  schedule rather than the data."

### DB-247 · `latest_per_control` reads the whole chain
- **Area:** `db/dao/evidence.py::latest_per_control`
- **Type:** performance
- **Priority:** P2
- **Precondition:** a tenant with more than 10,000 records
- **Steps:** call
- **Expected:** a complete answer, or a stated ceiling
- **Why:** it calls `chain(tenant_id)` whose default limit is 10,000, so past
  that a scorecard silently stops seeing the newest controls.

### DB-248 · `last_run_at` counts an errored run as a run
- **Area:** `db/dao/evidence.py::last_run_at`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a control whose every record is an error
- **Steps:** call
- **Expected:** the latest timestamp is returned
- **Why:** "treating it as never run would make the scheduler retry it
  continuously while the source is down — turning one broken control into a load
  problem".

### DB-249 · `EvidenceRunDao.finish` counts the records it covered
- **Area:** `db/dao/evidence.py::EvidenceRunDao.finish`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a run with three records
- **Steps:** finish
- **Expected:** `record_count == 3`
- **Why:** the number an operator compares against the expected control count.

### DB-250 · `unfinished` surfaces runs that never reported
- **Area:** `db/dao/evidence.py::unfinished`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a run left in `running`
- **Steps:** call
- **Expected:** the run
- **Why:** "their controls have no verdict, and every screen built on 'the latest
  evidence' is silently missing them".

### DB-251 · `SampleDao.put` is idempotent on the digest
- **Area:** `db/dao/evidence.py::SampleDao.put`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a stored sample set
- **Steps:** put the same digest again with a later `expires_at`
- **Expected:** the existing row is returned unchanged
- **Why:** "Overwriting … would reset the expiry clock on personal data every
  time the same failure recurred."

### DB-252 · `expired` finds only samples past their expiry
- **Area:** `db/dao/evidence.py::expired`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** samples expiring yesterday, today at this instant, tomorrow,
  and one with no expiry
- **Steps:** call with now
- **Expected:** the first two; never the one with `expires_at IS NULL`
- **Why:** a null expiry is a sample under indefinite retention; deleting it
  would be an unauthorised erasure.

### DB-253 · `forget` deletes a sample but not the record
- **Area:** `db/dao/evidence.py::forget`
- **Type:** security
- **Priority:** P1
- **Precondition:** a record with samples
- **Steps:** forget, then read the record
- **Expected:** the record still says a control failed and how many rows failed
  it; the rows are gone
- **Why:** "the rows are the personal data and the record is the audit trail" —
  the asymmetry is the design.

### DB-254 · `forget` of an unknown digest returns False
- **Area:** `db/dao/evidence.py::forget`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an unknown digest
- **Steps:** call
- **Expected:** `False`, no error
- **Why:** a retention sweep that raised on a sample somebody already removed
  would abort the whole sweep.

### DB-255 · `SampleDao` is not tenant-scoped on read
- **Area:** `db/dao/evidence.py::SampleDao.expired`, `forget`
- **Type:** security
- **Priority:** P2
- **Precondition:** samples in two tenants
- **Steps:** call `expired`
- **Expected:** a retention job legitimately crosses tenants; confirm no
  API-reachable path does
- **Why:** the digest is content-addressed, so two tenants with identical failing
  rows share a row — which also means one tenant's `forget` removes the other's
  evidence sample.

### DB-256 · `AttestationDao.delete` is refused
- **Area:** `db/dao/attestation.py::AttestationDao.delete`
- **Type:** security
- **Priority:** P1
- **Precondition:** a signed attestation
- **Steps:** delete
- **Expected:** `ConflictError` naming the signing time, remedy explaining
  supersession
- **Why:** "the fact that somebody signed the first one is itself part of the
  record".

### DB-257 · `sign` writes the supersession on both rows
- **Area:** `db/dao/attestation.py::sign`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an earlier attestation
- **Steps:** sign a replacement naming it
- **Expected:** the new row names the old, and the old row's `superseded_by`
  names the new
- **Why:** "so a reader who lands on it learns it was replaced rather than
  having to go looking for a newer one".

### DB-258 · Superseding a non-existent attestation is refused after the new row was written
- **Area:** `db/dao/attestation.py::sign`
- **Type:** negative
- **Priority:** P2
- **Precondition:** an unknown `supersedes` id
- **Steps:** sign
- **Expected:** `NotFoundError` — and the new row must not persist
- **Why:** the row is added and flushed *before* the lookup; if the caller
  catches the error without rolling back, an attestation exists that claims to
  supersede something that does not.

### DB-259 · `current` excludes superseded attestations
- **Area:** `db/dao/attestation.py::current`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an attestation and its replacement
- **Steps:** call
- **Expected:** only the replacement
- **Why:** a superseded sign-off presented as current is the strongest possible
  misstatement this product can make.

### DB-260 · `history` includes superseded rows, oldest first
- **Area:** `db/dao/attestation.py::history`
- **Type:** functional
- **Priority:** P1
- **Precondition:** as above
- **Steps:** call for the scope
- **Expected:** both, ordered by `signed_at`
- **Why:** the correction and the original together are the interesting half of
  the record.

### DB-261 · `in_tenant` reports another tenant's attestation as absent
- **Area:** `db/dao/attestation.py::in_tenant`
- **Type:** security
- **Priority:** P1
- **Precondition:** an attestation in tenant A
- **Steps:** fetch as tenant B
- **Expected:** `NotFoundError`, not forbidden
- **Why:** "the kind of check that gets written on one screen and forgotten on
  the next — and the screen it gets forgotten on is the one that prints the
  pack".

### DB-262 · `verify` distinguishes tampering from a foreign key
- **Area:** `db/dao/attestation.py::verify`
- **Type:** security
- **Priority:** P1
- **Precondition:** three rows — intact and correctly sealed, intact and sealed
  with a different key, and content-edited
- **Steps:** verify each
- **Expected:** `(True, True)`, `(True, False)`, `(False, False)`
- **Why:** "Reporting a single boolean would make 'somebody edited this'
  indistinguishable from 'this came from another deployment', which are different
  incidents."

### DB-263 · `verify` of an unsealed row is not sealed
- **Area:** `db/dao/attestation.py::verify`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a row with an empty seal
- **Steps:** verify
- **Expected:** `(True, False)`
- **Why:** `bool(row.seal)` guards it; an empty seal compared with an empty
  computed seal must not read as verified.

### DB-264 · `BreakDao.observe` returns new, seen-again and cleared
- **Area:** `db/dao/recon.py::observe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a queue of forty breaks; a run reporting forty different ones
- **Steps:** observe
- **Expected:** `(40, 0, 40)`
- **Why:** "'nothing changed' and 'forty cleared and forty appeared' produce the
  same queue length, and a screen that reports only the length cannot tell them
  apart".

### DB-265 · A re-seen break keeps its original `first_seen`
- **Area:** `db/dao/recon.py::observe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a break first seen forty days ago
- **Steps:** observe it again today
- **Expected:** `first_seen` unchanged, `last_seen` today
- **Why:** "stamping each sighting with today reports every break as new every
  morning and nothing ever ages".

### DB-266 · A break absent from a run is cleared
- **Area:** `db/dao/recon.py::observe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an open break
- **Steps:** observe a run that does not report it
- **Expected:** state `cleared`, `cleared_at` set
- **Why:** "no reconciliation tells you a break has gone, it simply stops
  reporting it, and a queue that waits to be told never closes anything".

### DB-267 · An accepted break is not cleared by absence
- **Area:** `db/dao/recon.py::observe`, `OPEN`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an accepted break
- **Steps:** observe a run without it
- **Expected:** still accepted
- **Why:** `OPEN` excludes `accepted`; an accepted reconciling item that
  disappeared from the queue would hide the acceptance.

### DB-268 · A cleared break that returns is re-opened with its original age
- **Area:** `db/dao/recon.py::observe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a cleared break
- **Steps:** observe it again
- **Expected:** state `open`, `cleared_at` null, `first_seen` unchanged
- **Why:** "a break that recurs after being closed is an old problem, not a new
  one".

### DB-269 · `outstanding` includes accepted breaks
- **Area:** `db/dao/recon.py::OUTSTANDING`
- **Type:** contract
- **Priority:** P1
- **Precondition:** open, assigned, explained, accepted and cleared breaks
- **Steps:** call
- **Expected:** the first four
- **Why:** "a reconciliation reporting zero outstanding because the residue was
  accepted is hiding exactly the thing the acceptance was supposed to make
  visible".

### DB-270 · `definitions` includes reconciliations with only cleared breaks
- **Area:** `db/dao/recon.py::definitions`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a definition whose breaks all cleared
- **Steps:** call
- **Expected:** present
- **Why:** "a clean result is indistinguishable from one that never ran".

### DB-271 · `assign`, `explain` and `accept` refuse empty input
- **Area:** `db/dao/recon.py`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a break
- **Steps:** assign to `"  "`, explain with `""`, accept with `"  "`
- **Expected:** `ValidationError` each, with the reasons given in the docstrings
- **Why:** "an acceptance with no reason cannot be defended when somebody asks
  about it in a year".

### DB-272 · A handover is recorded in the comment trail
- **Area:** `db/dao/recon.py::assign`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a break owned by Alice
- **Steps:** assign to Bob
- **Expected:** a comment "Reassigned from Alice to Bob" with who and when
- **Why:** "only the trail answers 'who gave it to them and when', which is the
  question asked about a break that sat with the wrong team for a month".

### DB-273 · Accepting a cleared break is refused
- **Area:** `db/dao/recon.py::accept`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a cleared break
- **Steps:** accept
- **Expected:** `ConflictError` — "Accepting a break that has gone would carry a
  difference nobody has."
- **Why:** an accepted-but-gone break is a permanent reconciling item for a
  difference that does not exist.

### DB-274 · `explain` and `assign` append rather than rewrite
- **Area:** `db/dao/recon.py`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a break with two comments
- **Steps:** explain again
- **Expected:** three comments, the earlier two unchanged
- **Why:** "Appends; never rewrites" — the trail is the evidence.

### DB-275 · `delete` on a break is refused
- **Area:** `db/dao/recon.py::delete`
- **Type:** security
- **Priority:** P1
- **Precondition:** a break
- **Steps:** delete
- **Expected:** `ConflictError` with the "four hundred breaks" remedy
- **Why:** "A queue that forgets reports the same number as a clean one."

### DB-276 · `in_tenant` reports another tenant's break as absent
- **Area:** `db/dao/recon.py::in_tenant`
- **Type:** security
- **Priority:** P1
- **Precondition:** a break in tenant A
- **Steps:** fetch as B
- **Expected:** `NotFoundError`
- **Why:** every mutation routes through it, so it is the single isolation guard
  for the whole break workflow.

### DB-277 · A missing side renders as empty, not zero
- **Area:** `db/dao/recon.py::_text`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a break whose right side is `None` and one whose right side
  is `0`
- **Steps:** observe both, read the stored values
- **Expected:** `""` and `"0"`
- **Why:** "'nothing on the right' and 'zero on the right' are different breaks,
  and rendering the first as the second turns a missing record into a balanced
  one".

## Leases in the database, and the metric store

### DB-278 · A database lease is granted once across two processes
- **Area:** `db/lease_provider.py::DatabaseLeaseProvider.acquire`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** one database, two provider instances
- **Steps:** acquire the same resource simultaneously, repeatedly
- **Expected:** exactly one grant each time
- **Why:** "a single conditional statement, so two instances racing for the same
  resource cannot both win".

### DB-279 · The conditional upsert works on both engines
- **Area:** `db/lease_provider.py::acquire`
- **Type:** contract
- **Priority:** P1
- **Precondition:** both engines
- **Steps:** acquire, contend, take over an expired lease
- **Expected:** identical behaviour
- **Why:** the statement is hand-written SQL with `ON CONFLICT ... WHERE`, which
  SQLite and PostgreSQL parse differently enough to need executing on both.

### DB-280 · The fencing token increases on every acquisition
- **Area:** `db/lease_provider.py::acquire`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a resource acquired and released five times by different
  holders
- **Steps:** read the token each time
- **Expected:** strictly increasing
- **Why:** "the difference between 'we hope only one writer is active' and 'a
  second writer cannot do damage'".

### DB-281 · A lost race returns None rather than a lease
- **Area:** `db/lease_provider.py::acquire`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a live lease held elsewhere
- **Steps:** acquire
- **Expected:** `None` — the token comparison after the read is what detects it
- **Why:** the upsert's `WHERE` makes the update a no-op, and the follow-up
  `SELECT` is the only thing that notices.

### DB-282 · Renewal of a lease taken over returns None and logs
- **Area:** `db/lease_provider.py::renew`
- **Type:** negative
- **Priority:** P1
- **Precondition:** A's lease taken by B
- **Steps:** A renews
- **Expected:** `None`, with a warning naming the resource and the holder
- **Why:** the `rowcount != 1` check is the whole detection.

### DB-283 · Renewal of an expired lease returns None
- **Area:** `db/lease_provider.py::renew`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** A's lease expired but not taken
- **Steps:** A renews
- **Expected:** `None` — the `expires_at > :now` clause refuses it
- **Why:** a holder that could renew from beyond expiry would defeat the whole
  time bound.

### DB-284 · `release` expires the row rather than deleting it
- **Area:** `db/lease_provider.py::release`
- **Type:** security
- **Priority:** P1
- **Precondition:** a held lease with token 3
- **Steps:** release, then acquire
- **Expected:** the row survives; the next token is 4
- **Why:** "a fencing token that can go backwards protects nothing: a stalled
  holder from a previous era would present a token indistinguishable from a
  current one".

### DB-285 · `release` marks the holder
- **Area:** `db/lease_provider.py::release`
- **Type:** functional
- **Priority:** P3
- **Precondition:** a released lease
- **Steps:** read the row
- **Expected:** `holder` ends "(released)"
- **Why:** it is the only way an operator can tell a graceful hand-over from a
  crash; confirm the column is wide enough for the suffix.

### DB-286 · `inspect` returns None for an expired lease and parses both timestamps
- **Area:** `db/lease_provider.py::inspect`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a live lease and an expired one
- **Steps:** inspect both
- **Expected:** a `Lease` with UTC-aware `acquired_at` and `expires_at`, then
  `None`
- **Why:** the parse handles the `Z` suffix by hand; a `+00:00` row written by
  another path would fail it.

### DB-287 · `purge_before` removes only long-expired rows
- **Area:** `db/lease_provider.py::purge_before`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a live lease and one expired last month
- **Steps:** purge with a cutoff of a week ago
- **Expected:** one row deleted, the live one untouched
- **Why:** "the cutoff must be far enough in the past that no holder from before
  it could conceivably still be running — days, not minutes"; the method has no
  guard enforcing that, so the test is what documents the risk.

### DB-288 · ISO text comparison is correct for lease expiry
- **Area:** `db/lease_provider.py::_ISO`, `_iso`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** expiry times spanning a year boundary and a microsecond
  boundary
- **Steps:** acquire, contend
- **Expected:** correct ordering in every case
- **Why:** "expiry comparison is a plain string comparison and needs no dialect
  branch" — which is true only while every writer produces the same fixed-width
  form.

### DB-289 · `MetricStore.record` never updates
- **Area:** `db/metrics/store.py::MetricStore.record`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a point recorded twice with the same key and time
- **Steps:** read the series
- **Expected:** two observations — "history is not editable"
- **Why:** a metric store that deduplicated would let a re-run rewrite the past a
  monitor calibrated against.

### DB-290 · A series reads back oldest first
- **Area:** `db/metrics/store.py::series`
- **Type:** functional
- **Priority:** P1
- **Precondition:** points recorded out of order
- **Steps:** read
- **Expected:** ascending by `computed_at`
- **Why:** every detector treats the history as a time-ordered sequence; an
  unordered read silently changes the forecast and the changepoint.

### DB-291 · The memory and Parquet stores agree
- **Area:** `db/metrics/store.py::MemoryMetricStore`, `ParquetMetricStore`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the same points recorded in both
- **Steps:** compare `series`, `latest` and `count`
- **Expected:** identical
- **Why:** the memory store is used in tests and the CLI and the Parquet store in
  production; a divergence means every test proves the wrong thing.

### DB-292 · Sampling provenance survives a round trip
- **Area:** `db/metrics/model.py::MetricPoint`, `store.py::_point`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a point with `sampling="1pct"`, `representative=False`,
  `rows_examined=1000`, `snapshot_exact=False`
- **Steps:** record and read
- **Expected:** all four preserved
- **Why:** "A baseline built from observations that silently mixed full scans
  with 1% samples would be wrong in a way nobody could detect afterwards."

### DB-293 · `purge_before` drops whole day partitions only
- **Area:** `db/metrics/store.py::ParquetMetricStore.purge_before`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** points either side of a day boundary and a cutoff mid-day
- **Steps:** purge
- **Expected:** only whole days older than the cutoff are removed; the partial
  day survives
- **Why:** a retention sweep that removed half a day would leave a monitor
  calibrating against an incomplete window with no indication.

### DB-294 · A metric name outside `CORE_METRICS` is still recordable
- **Area:** `db/metrics/model.py::CORE_METRICS`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a tenant-defined metric
- **Steps:** record and read
- **Expected:** accepted — "A tenant may record others"
- **Why:** the constant is documentation of what monitors interpret, not a
  whitelist; confirm nothing enforces it as one.

### DB-295 · `MetricPoint.key` distinguishes segments
- **Area:** `db/metrics/model.py::MetricPoint.key`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** the same metric with `segment=None` and `segment="GB"`
- **Steps:** compare keys and read each series
- **Expected:** two distinct series
- **Why:** "what makes per-entity monitoring possible without a table per
  entity"; a key that collapsed them would pool the segments the segmented
  monitor exists to separate.

## Monitors — drift and accepting a new normal

### MON-001 · A sample below the minimum is refused, with the reason
- **Area:** `monitor/drift.py::compare`, `MINIMUM_SAMPLE`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 49 observations on one side, 50 on the other
- **Steps:** `compare`
- **Expected:** a report with no measures, `refusal` naming both sizes and
  explaining PSI's instability
- **Why:** "PSI in particular will report a shift between two draws from the same
  distribution" — a measure produced below the floor is noise presented as
  evidence.

### MON-002 · Exactly the minimum on both sides produces measures
- **Area:** `monitor/drift.py::compare`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 50 and 50
- **Steps:** `compare`
- **Expected:** five measures, no refusal
- **Why:** the boundary is `<`, so 50 is admissible; confirm rather than assume.

### MON-003 · Two samples from one distribution are not material
- **Area:** `monitor/drift.py::compare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 500 and 500 draws from the same normal, a fixed seed
- **Steps:** `compare`
- **Expected:** `is_material` false
- **Why:** the counterfactual that makes every positive result meaningful; run it
  across many seeds and record the false-positive rate.

### MON-004 · A shifted sample is material
- **Area:** `monitor/drift.py::compare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** reference N(1000, 50), current N(1400, 50), 500 each
- **Steps:** `compare`
- **Expected:** `is_material` true, a majority of the five measures material
- **Why:** a drift module that cannot see a eight-sigma shift is not a drift
  module.

### MON-005 · Materiality needs a majority, not one measure
- **Area:** `monitor/drift.py::DriftReport.is_material`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a report with two of five material
- **Steps:** read `is_material`
- **Expected:** false
- **Why:** "a single measure firing alone is more often that measure's weakness
  than a real shift". Three of five must be true.

### MON-006 · Disagreement is described when the measures split
- **Area:** `monitor/drift.py::DriftReport.disagreement`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a split report
- **Steps:** read `disagreement`
- **Expected:** a sentence naming which saw a shift and which did not
- **Why:** "Reporting several and their disagreement is more honest than picking
  one and calling it the answer."

### MON-007 · Disagreement is empty when all agree
- **Area:** `monitor/drift.py::DriftReport.disagreement`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** all five material, then none
- **Steps:** read
- **Expected:** `""` both times
- **Why:** a "disagreement" sentence on a unanimous report is a claim about
  uncertainty that does not exist.

### MON-008 · PSI's epsilon prevents an infinite value on an empty bin
- **Area:** `monitor/drift.py::_psi`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a current sample missing an entire reference bin
- **Steps:** `compare`
- **Expected:** a finite PSI
- **Why:** "without it PSI is infinite whenever the current sample misses a bin
  the reference had, which happens constantly on small samples".

### MON-009 · PSI is zero for identical histograms
- **Area:** `monitor/drift.py::_psi`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two identical samples
- **Steps:** `compare`
- **Expected:** PSI at or very near zero, not material
- **Why:** the epsilon must not introduce a floor that makes identical
  distributions look shifted.

### MON-010 · The PSI threshold is the industry's 0.2
- **Area:** `monitor/drift.py::PSI_SHIFT`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a PSI of exactly 0.2 and of 0.19999
- **Steps:** read `material`
- **Expected:** true, then false
- **Why:** "Quoted rather than invented" — "a PSI that disagrees with the one in
  somebody's spreadsheet is a PSI nobody will act on."

### MON-011 · Ten bins is the default and matches the PSI convention
- **Area:** `monitor/drift.py::DEFAULT_BINS`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** read the constant and count the histogram buckets
- **Expected:** ten bins, meaning nine edges
- **Why:** the same "matching the convention matters more here than an optimal
  choice" argument; `_edges` builds `range(1, bins)` edges, giving `bins`
  buckets — confirm the arithmetic.

### MON-012 · The KS statistic is bounded and its critical value scales with size
- **Area:** `monitor/drift.py::_kolmogorov_smirnov`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** identical samples, then disjoint ones
- **Steps:** `compare`
- **Expected:** statistic 0 then 1; the critical value falls as the samples grow
- **Why:** a fixed critical value would make KS fire on every large sample.

### MON-013 · Wasserstein is reported in the data's own units
- **Area:** `monitor/drift.py::_wasserstein`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a reference at about 1,000 and a current at about 5,100
- **Steps:** read the measure
- **Expected:** about 4,100, and the explanation says "moved by about 4,100 in
  its own units"
- **Why:** "the one a person understands: 'the typical row count moved by 4,100'
  is a sentence, where 'PSI 0.31' is a number somebody has to be trained to
  read".

### MON-014 · Wasserstein's materiality threshold is the reference's spread
- **Area:** `monitor/drift.py::_wasserstein`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a shift of exactly one standard deviation and of two
- **Steps:** read `material`
- **Expected:** false then true
- **Why:** the threshold is `distance > scale`; a constant reference makes
  `_spread` zero and the fallback `1.0` then compares a raw distance against one
  unit — check that boundary too.

### MON-015 · Jensen-Shannon is bounded in [0, 1]
- **Area:** `monitor/drift.py::_jensen_shannon`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** disjoint distributions
- **Steps:** read the value
- **Expected:** at most 1.0, never negative, never NaN
- **Why:** the docstring claims bounded and symmetric; a value outside the range
  would break every chart drawn against it.

### MON-016 · Jensen-Shannon is symmetric
- **Area:** `monitor/drift.py::_jensen_shannon`
- **Type:** contract
- **Priority:** P2
- **Precondition:** two samples
- **Steps:** compare in both orders
- **Expected:** the same value
- **Why:** the claim is in the module docstring, and an asymmetric "distance"
  makes the direction of a comparison change the answer.

### MON-017 · Chi-square uses the current sample size
- **Area:** `monitor/drift.py::_chi_square`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** the same proportional shift at 100 and at 10,000 observations
- **Steps:** read the statistic and `material`
- **Expected:** the statistic scales with size; the small sample is not material
  and the large one is
- **Why:** that is what a chi-square is *for*, and it is the only measure here
  that uses the size directly.

### MON-018 · The Wilson-Hilferty normalisation is right at the threshold
- **Area:** `monitor/drift.py::_chi_square`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a statistic at the 5% critical value for nine degrees of
  freedom
- **Steps:** read `material`
- **Expected:** on the boundary, matching the exact chi-square within a few
  percent
- **Why:** the approximation is used to avoid the full distribution; if it is off
  the "5%" it claims is not 5%.

### MON-019 · A constant reference does not produce a NaN anywhere
- **Area:** `monitor/drift.py::compare`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 100 identical values as the reference, a varied current
- **Steps:** `compare`, then `to_dict`
- **Expected:** every value finite; the document serialises
- **Why:** `_edges` on a constant sample produces identical edges, which puts
  everything in one bin; a NaN reaching `pjson` becomes `null` and a chart draws
  nothing.

### MON-020 · An empty reference is refused rather than crashing
- **Area:** `monitor/drift.py::compare`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an empty list on either side
- **Steps:** `compare`
- **Expected:** the refusal, not a `ZeroDivisionError` or an `IndexError`
- **Why:** the minimum check runs first — confirm it covers zero as well as small.

### MON-021 · `find_changepoint` needs two full segments
- **Area:** `monitor/drift.py::find_changepoint`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 39 observations with `minimum_segment=20`
- **Steps:** call
- **Expected:** `None`
- **Why:** a "changepoint" with nineteen observations on one side is a
  description of noise.

### MON-022 · `find_changepoint` locates a clean step
- **Area:** `monitor/drift.py::find_changepoint`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 100 at level 1,000 then 100 at 1,600, low noise
- **Steps:** call
- **Expected:** an index near 100, `before` ≈ 1,000, `after` ≈ 1,600, strength
  well above 1
- **Why:** the benchmark's `CHANGEPOINT` mechanism depends on it, and so does
  `history_after`.

### MON-023 · `find_changepoint` on a stationary series finds nothing convincing
- **Area:** `monitor/drift.py::find_changepoint`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 200 draws from one distribution
- **Steps:** call, read `strength`
- **Expected:** a best split is always returned, but its strength is far below
  the 1.5 the benchmark uses
- **Why:** the function always returns something when the length allows, so the
  *threshold* is what separates signal from noise — and the threshold lives in
  the caller, not here.

### MON-024 · `Changepoint.ratio` handles a zero baseline
- **Area:** `monitor/drift.py::Changepoint.ratio`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `before == 0`
- **Steps:** read `ratio`, `describe` and `to_dict`
- **Expected:** infinity, a readable sentence, and `None` in the document
- **Why:** `describe()` formats `abs(self.ratio - 1)` as a percentage, which on
  infinity produces "inf%" on a page somebody reads.

### MON-025 · An acceptance without a reason is refused
- **Area:** `monitor/drift.py::Acceptance.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `reason=""` and `reason="   "`
- **Steps:** construct
- **Expected:** `ValueError` in both cases, explaining the record "cannot
  distinguish a business change from somebody silencing an alert"
- **Why:** "the only question anybody asks about it later".

### MON-026 · The annotation carries who, when, the levels and the reason
- **Area:** `monitor/drift.py::Acceptance.annotation`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an acceptance
- **Steps:** render
- **Expected:** all five facts in one line
- **Why:** "a report six months later still shows the step and who signed for
  it" — this string is that report.

### MON-027 · `history_after` discards everything before the latest acceptance
- **Area:** `monitor/drift.py::history_after`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 200 values, acceptances at index 50 and 120
- **Steps:** call
- **Expected:** 80 values, starting at index 120
- **Why:** "what stops is treating the old regime as evidence about the new one,
  which is the thing that makes a monitor alert every day for six months after a
  business change".

### MON-028 · `history_after` with no acceptances changes nothing
- **Area:** `monitor/drift.py::history_after`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** no acceptances
- **Steps:** call
- **Expected:** the original series
- **Why:** the default path must not truncate.

### MON-029 · An acceptance index beyond the series is ignored safely
- **Area:** `monitor/drift.py::history_after`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an acceptance at index 500 over a 100-point series
- **Steps:** call
- **Expected:** the whole series, not an empty one
- **Why:** the guard is `if latest < len(values)`; a trimmed history of zero
  points would leave the monitor permanently unable to judge.

### MON-030 · An acceptance at the last index leaves one point
- **Area:** `monitor/drift.py::history_after`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an acceptance at `len(values) - 1`
- **Steps:** call
- **Expected:** one value, and the monitor then reports that it cannot judge
  rather than judging on one point
- **Why:** the handover between "accepted a new normal" and "cannot calibrate
  yet" must be explicit rather than silent.

## Monitors — detectors

### MON-031 · Every detector refuses a history below the minimum
- **Area:** `monitor/detect.py::MINIMUM_HISTORY`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** nine observations
- **Steps:** score with each of the five detectors
- **Expected:** `None` from each
- **Why:** "Below this, no detector says anything: the statistics it would
  compute are dominated by the points used to compute them."

### MON-032 · Each detector has its own additional floor
- **Area:** `monitor/detect.py`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** histories of exactly 10, `k+1`, `span+1` and `2*window`
- **Steps:** score with `RobustDeviation`, `LocalOutlierFactor`,
  `ForecastResidual` and `ShapeDistance`
- **Expected:** each returns a score at its own floor and `None` one below it
- **Why:** four different floors that are all called "too little history" must
  each be pinned, or a monitor silently goes quiet at a size nobody expects.

### MON-033 · The observation is scored against the same window as the calibration
- **Area:** `monitor/detect.py::Detector.score`, `MAXIMUM_CALIBRATION`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a 500-point history
- **Steps:** score an observation, and compute `scores(history)`
- **Expected:** both use the last 300 points
- **Why:** "Scoring the observation against the full history while calibrating
  against the last three hundred points … is a silent violation of
  exchangeability: the false-alarm rate drifts with no symptom anybody can see."

### MON-034 · Calibration scoring is leave-one-out
- **Area:** `monitor/detect.py::Detector.scores`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a 50-point history
- **Steps:** compute the calibration scores and compare against scoring each
  point against the full window
- **Expected:** the leave-one-out scores are systematically larger
- **Why:** "makes every calibration score slightly too small, so the observation
  looks relatively stranger than it is and the monitor over-alerts — by a
  little, consistently, in the direction that breaks the promise".

### MON-035 · `RobustDeviation` is unmoved by one extreme point
- **Area:** `monitor/detect.py::RobustDeviation`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 50 points around 1,000, plus one at 100,000
- **Steps:** score a point at 1,300 with and without the outlier in the history
- **Expected:** the scores are close
- **Why:** "the monitor is least sensitive exactly after something has gone
  wrong, which is when it is most needed" — a mean-and-standard-deviation
  detector fails this.

### MON-036 · `RobustDeviation` on a constant history falls back to raw distance
- **Area:** `monitor/detect.py::RobustDeviation.compute`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** 20 identical values
- **Steps:** score a different value
- **Expected:** a finite score equal to the raw distance divided by 1.4826, not
  infinity
- **Why:** "Any departure is infinitely surprising by this measure, which is
  useless."

### MON-037 · The MAD scaling does not change the ordering
- **Area:** `monitor/detect.py::RobustDeviation.compute`
- **Type:** contract
- **Priority:** P2
- **Precondition:** several observations against one history
- **Steps:** compare the ordering with and without the 1.4826 factor
- **Expected:** identical
- **Why:** "It has no effect on the ordering, and therefore none on the
  guarantee" — the claim is checkable and worth checking.

### MON-038 · `QuantileDistance` scores both tails
- **Area:** `monitor/detect.py::QuantileDistance`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a history spanning 0 to 1
- **Steps:** score a point below the minimum and one above the maximum
- **Expected:** both near 1.0; a point at the median near 0.0
- **Why:** "A one-sided monitor is a different declaration and gets a different
  detector rather than a flag on this one."

### MON-039 · `QuantileDistance` is the default for a bounded metric
- **Area:** `monitor/fleet.py::_default_detector`, `MetricKind.is_bounded`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `NULL_RATE` and `DISTRIBUTION`
- **Steps:** build a monitor with no explicit detector
- **Expected:** `QuantileDistance`
- **Why:** "a symmetric measure spends half its sensitivity on the impossible
  side of a null rate".

### MON-040 · `LocalOutlierFactor` finds a point between two clusters
- **Area:** `monitor/detect.py::LocalOutlierFactor`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a history of weekday 20,000s and weekend 500s
- **Steps:** score 10,000, and score 19,500
- **Expected:** 10,000 scores much higher
- **Why:** "A row count that is normally either 20,000 on weekdays or 500 at
  weekends is not reassured by an observation of 10,000."

### MON-041 · `LocalOutlierFactor` handles a point exactly on a history value
- **Area:** `monitor/detect.py::_local_density`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an observation equal to several history values
- **Steps:** score
- **Expected:** a finite score, no division by zero
- **Why:** `1.0 / distance` where distance is zero returns `math.inf`, which then
  makes `own <= 0` false and the ratio zero — confirm the result is usable.

### MON-042 · `LocalOutlierFactor` with a far-away point reports the degenerate case
- **Area:** `monitor/detect.py::LocalOutlierFactor.compute`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** an observation astronomically far from everything
- **Steps:** score
- **Expected:** the documented `len(history)` score with the "nowhere near
  anything seen before" explanation
- **Why:** the branch is only reachable when `own <= 0`, which needs an infinite
  distance — confirm it is reachable at all rather than dead code.

### MON-043 · `ForecastResidual` tracks a trending series
- **Area:** `monitor/detect.py::ForecastResidual`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a series growing 2% a period
- **Steps:** score the next in-trend value
- **Expected:** a low score; `RobustDeviation` on the same input scores it high
- **Why:** "a row count growing 2% a month is always far from the median of its
  own year, and a monitor built on that alerts continuously until somebody
  widens it into uselessness".

### MON-044 · The residual is relative, so the score distribution is scale-free
- **Area:** `monitor/detect.py::ForecastResidual.compute`, `_relative`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a series that doubles over the window
- **Steps:** compare the calibration score distribution over the first and last
  thirds
- **Expected:** comparable
- **Why:** "absolute residuals grow with the level … it breaks exchangeability,
  which is the assumption the conformal guarantee rests on, so the false-alarm
  rate drifts upward over the life of the monitor and nothing says why".

### MON-045 · `_relative` falls back to an absolute difference at zero
- **Area:** `monitor/detect.py::_relative`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a forecast of exactly 0.0
- **Steps:** score an observation of 5
- **Expected:** 5, not infinity
- **Why:** "where a ratio has no meaning and the absolute number is the only
  honest one available".

### MON-046 · `ShapeDistance` finds a changed profile with an unchanged total
- **Area:** `monitor/detect.py::ShapeDistance`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a history of smooth intraday curves, then one spiky window of
  the same total
- **Steps:** `score_window`
- **Expected:** a high score, where a level detector scores it low
- **Why:** "a feed that arrived all at once instead of throughout the day, which
  every level-based detector calls normal".

### MON-047 · `ShapeDistance` is blind to a level change
- **Area:** `monitor/detect.py::ShapeDistance`, `_standardise`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** the same shape at double the volume
- **Steps:** `score_window`
- **Expected:** near zero
- **Why:** the stated blind spot, and it is a direct consequence of per-window
  standardisation — a detector that scored it would not be measuring shape.

### MON-048 · `ShapeDistance` handles a flat window
- **Area:** `monitor/detect.py::_standardise`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a constant window
- **Steps:** score
- **Expected:** finite; `_standardise` returns zeros rather than dividing by zero
- **Why:** a flat day is normal for a dormant feed and must not crash the
  detector.

### MON-049 · `ShapeDistance` is not in the default ensemble
- **Area:** `monitor/detect.py::default_ensemble`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** read the ensemble
- **Expected:** four detectors; the module docstring describes five, "chosen
  because they fail differently"
- **Why:** either the docstring or the default is wrong, and the blind spot it
  covers — a changed profile with an unchanged total — is the one nothing else
  in the suite sees.

### MON-050 · `Ensemble.score_all` omits detectors that cannot score
- **Area:** `monitor/detect.py::Ensemble.score_all`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a history long enough for two detectors and not the others
- **Steps:** call
- **Expected:** only the two appear
- **Why:** a `None` in the result would be indistinguishable from a score of
  zero for whoever reads it.

### MON-051 · Scores are never combined before calibration
- **Area:** `monitor/detect.py::Ensemble`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** confirm the ensemble exposes per-detector scores and per-detector
  calibration only
- **Expected:** no method averages or weights raw scores
- **Why:** "the scores are on different scales with different distributions, and
  any weighting is a modelling choice that would silently change the false-alarm
  rate".

### MON-052 · `calibration_for` an unknown detector returns an empty list
- **Area:** `monitor/detect.py::Ensemble.calibration_for`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a name not in the ensemble
- **Steps:** call
- **Expected:** `[]`
- **Why:** an empty calibration set makes the calibrator refuse rather than
  produce a p-value from nothing — confirm that is what happens downstream.

### MON-053 · Every detector declares `good_at` and `blind_to`
- **Area:** `monitor/detect.py::Detector`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** read both class variables for all five
- **Expected:** non-empty, specific, and different from each other
- **Why:** "a suite that only advertises strengths is a suite whose gaps are
  discovered in production", and the model card prints these verbatim.

### MON-054 · A `Score` is not a probability and says so
- **Area:** `monitor/detect.py::Score`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a scored observation
- **Steps:** inspect the value across detectors
- **Expected:** values outside [0, 1] occur, and nothing downstream treats a
  score as a p-value
- **Why:** "Deliberately not a probability, not a severity and not a verdict" —
  a score interpreted as a probability would be a false-alarm rate nobody
  calibrated.

### MON-055 · Every score's explanation is a sentence a person can read
- **Area:** `monitor/detect.py`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** one score from each detector
- **Steps:** render the explanations
- **Expected:** each names the observation, the expectation and the unit of
  strangeness; none contains a bare identifier or a raw float repr
- **Why:** "Enough to put in front of a person without them reading the code."

## Monitors — seasonality

### MON-056 · `period_end` reports the last *business* day of the period
- **Area:** `monitor/season.py::SeasonalModel.period_end`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a weekdays calendar; a month ending on a Sunday
- **Steps:** classify the preceding Friday and the Sunday
- **Expected:** the Friday is `month`; the Sunday is `none`
- **Why:** "a monitor keyed on the calendar date compares that Friday against
  ordinary Fridays and alerts every quarter".

### MON-057 · Year end beats quarter end beats month end
- **Area:** `monitor/season.py::period_end`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 31 December, 31 March, 30 April
- **Steps:** classify each
- **Expected:** `year`, `quarter`, `month`
- **Why:** the checks are ordered; a mis-ordering would classify 31 December as a
  month end and pool it with eleven ordinary month ends.

### MON-058 · A non-business day is never a period end
- **Area:** `monitor/season.py::period_end`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a Saturday that is the calendar last day of a month
- **Steps:** classify
- **Expected:** `none`
- **Why:** no work happens, so pooling it with month ends would dilute the group
  with a day that has no volume.

### MON-059 · The grouping key includes every configured facet
- **Area:** `monitor/season.py::SeasonalModel.key`
- **Type:** functional
- **Priority:** P2
- **Precondition:** intraday on, two declared drivers
- **Steps:** build a key
- **Expected:** business day, period end, day of week, hour and both drivers
- **Why:** a facet silently dropped from the key is a distinction the monitor
  stops making without saying so.

### MON-060 · Declared drivers are sorted into the key deterministically
- **Area:** `monitor/season.py::SeasonalModel.key`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two drivers registered in different orders
- **Steps:** build keys
- **Expected:** identical
- **Why:** the key is rendered into the model card and into the verdict's
  explanation; an order-dependent rendering makes two identical monitors look
  different.

### MON-061 · Grouping stops at the first usable group, most specific first
- **Area:** `monitor/season.py::SeasonalModel.group`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two years of daily history; today is a year end
- **Steps:** group
- **Expected:** the group is "any period end" with about twenty-four members, not
  five hundred ordinary business days
- **Why:** the comment records the earlier defect exactly — "the monitor then
  compares a year-end against ordinary Wednesdays and alerts every December".

### MON-062 · A facet is blurred before it is dropped
- **Area:** `monitor/season.py::_steps`, `_relax_one`, `coarsened`
- **Type:** functional
- **Priority:** P1
- **Precondition:** as above
- **Steps:** read `relaxed`
- **Expected:** `period_end` is not listed as relaxed, because it was blurred
  rather than dropped
- **Why:** "only a drop is worth reporting as lost specificity — a blurred facet
  is still doing work".

### MON-063 · Facets are relaxed least-important first
- **Area:** `monitor/season.py::_relaxation_order`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an intraday model with all facets
- **Steps:** force successive relaxation
- **Expected:** hour, then day of week, then period end, then business day
- **Why:** "Dropping period-end first would be easier and would produce exactly
  the pooled band this module exists to avoid."

### MON-064 · A declared driver is dropped last
- **Area:** `monitor/season.py::_relaxation_order`
- **Type:** security
- **Priority:** P1
- **Precondition:** a model with a declared driver and a thin history
- **Steps:** group
- **Expected:** the driver survives every relaxation, including the final
  fall-back to everything
- **Why:** "discarding a declaration to make a sample bigger is exactly the trade
  this system exists not to make silently" — note that the final fall-back
  returns an empty key, which discards it, so confirm what actually happens.

### MON-065 · A group below the minimum is never returned
- **Area:** `monitor/season.py::group`, `MINIMUM_GROUP`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a group of exactly 19 and one of exactly 20
- **Steps:** group
- **Expected:** the 19 is relaxed past; the 20 is accepted
- **Why:** "A group thinner than this cannot calibrate anything."

### MON-066 · With nothing specific enough, everything is compared and it says so
- **Area:** `monitor/season.py::group`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a 25-point history with high seasonal variety
- **Steps:** group
- **Expected:** every index is a member, `relaxed` lists every facet, and
  `describe()` says so
- **Why:** "rather than returning an empty group and no p-value" — the
  degradation must be visible, not silent.

### MON-067 · `resolution` is `1/(n+1)` and is reported
- **Area:** `monitor/season.py::Grouping.resolution`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a group of 24
- **Steps:** read `resolution` and `describe`
- **Expected:** 0.04, and the description says "enough for a p-value no finer
  than 0.040"
- **Why:** "comparing a year-end against 24 period-ends means no budget below
  0.04 can be honoured that day".

### MON-068 · `resolution` of an empty group is 1.0
- **Area:** `monitor/season.py::Grouping.resolution`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an empty group
- **Steps:** read
- **Expected:** `1.0`, not a division by zero
- **Why:** the model card divides on it; an exception there loses the whole card.

### MON-069 · `describe` names what was given up
- **Area:** `monitor/season.py::Grouping.describe`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** a grouping with two dropped facets
- **Steps:** render
- **Expected:** the group size, the key, the resolution caveat and the dropped
  facets, in one paragraph
- **Why:** "a monitor that silently switches between them is a monitor whose
  alerts mean different things on different days without saying so".

### MON-070 · `_matches` accepts a coarsened facet's members
- **Area:** `monitor/season.py::_matches`, `_COARSE_MATCHES`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a target key with `period_end=any`
- **Steps:** match candidates with `month`, `quarter`, `year` and `none`
- **Expected:** the first three match, `none` does not
- **Why:** an "any period end" group that admitted ordinary days would be the
  pooled band under a different name.

### MON-071 · `month_end_driver` identifies month, quarter and year ends
- **Area:** `monitor/season.py::month_end_driver`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a weekdays calendar over a year
- **Steps:** apply the predicate to every day
- **Expected:** exactly twelve true days, including the quarter and year ends
- **Why:** the declaration "volume is three times normal at month-end" has to
  pick out the right twelve days or it labels the wrong ones.

### MON-072 · `nth_weekday_driver` finds the third Friday
- **Area:** `monitor/season.py::nth_weekday_driver`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a year of dates
- **Steps:** apply `nth_weekday_driver(4, 3)`
- **Expected:** exactly twelve days, each the third Friday of its month
- **Why:** index rebalances and futures expiry; `(day.day - 1) // 7 == occurrence
  - 1` is easy to get off by one at the start of a month.

### MON-073 · `day_of_month_driver` handles a month without that day
- **Area:** `monitor/season.py::day_of_month_driver`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `day_of_month_driver(31)` over a year
- **Steps:** apply
- **Expected:** seven true days; February contributes none
- **Why:** a payroll rule on the 31st must not silently mean "never" in February
  without that being visible.

### MON-074 · A driver is a predicate, not a multiplier
- **Area:** `monitor/season.py::month_end_driver`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** confirm the returned object takes a date and returns a bool
- **Expected:** yes
- **Why:** "A multiplier would have to be right, and the business's 'about three
  times' is a recollection; a predicate only has to identify the days."

## Monitors — the monitor, the fleet, cold start and the tournament

### MON-075 · A monitor with no history says it cannot judge
- **Area:** `monitor/fleet.py::Monitor.judge`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an empty history
- **Steps:** judge
- **Expected:** `alerted=False`, `uncalibrated.reason` "no history for this
  metric yet"
- **Why:** "an alert that means 'I do not know' trains people to ignore alerts".

### MON-076 · A monitor that cannot judge never alerts
- **Area:** `monitor/fleet.py::Monitor._cannot`
- **Type:** contract
- **Priority:** P1
- **Precondition:** each of the three refusal paths — no history, too few
  comparables, an uncalibrated p-value
- **Steps:** judge
- **Expected:** `alerted=False` in every case
- **Why:** the one invariant that makes an unjudgeable monitor a fleet statistic
  rather than a page.

### MON-077 · Only earlier observations in the same segment are comparable
- **Area:** `monitor/fleet.py::Monitor.judge`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a history containing later observations and other segments
- **Steps:** judge
- **Expected:** neither is used
- **Why:** scoring against the future is a leak that makes every historical
  backtest optimistic.

### MON-078 · An observation at exactly the same instant as a history point is excluded
- **Area:** `monitor/fleet.py::Monitor.judge`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a history point with the same timestamp
- **Steps:** judge
- **Expected:** excluded — the filter is `item.at < observation.at`
- **Why:** scoring a point against itself makes it look normal by construction.

### MON-079 · The verdict explains itself in one sentence with every clause
- **Area:** `monitor/fleet.py::Verdict.explain`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** a full verdict with score, grouping, p-value and a degraded
  validity
- **Steps:** render
- **Expected:** the dataset and metric, the segment, the detector's explanation,
  the comparison group, the p-value, and the validity disclosure
- **Why:** "'the row count was low' is not an alert anybody can act on".

### MON-080 · The validity disclosure appears on the alert, not only the dashboard
- **Area:** `monitor/fleet.py::Verdict.explain`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a monitor whose calibration has degraded
- **Steps:** render
- **Expected:** the ⚠ clause is present
- **Why:** "The person reading this at three in the morning is not on the
  dashboard."

### MON-081 · An uncalibrated verdict explains why rather than showing a score
- **Area:** `monitor/fleet.py::Verdict.explain`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an uncalibrated verdict that nonetheless has a score
- **Steps:** render
- **Expected:** "could not be judged: <reason>" and nothing else
- **Why:** a partial explanation reads as a verdict and is not one.

### MON-082 · `hypothesis()` is None without a p-value
- **Area:** `monitor/fleet.py::Verdict.hypothesis`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an uncalibrated verdict
- **Steps:** call
- **Expected:** `None`
- **Why:** feeding an unjudgeable monitor into the multiple-testing selector as
  a p-value of zero or one would corrupt the whole family's correction.

### MON-083 · A segmented hypothesis identity includes the segment
- **Area:** `monitor/fleet.py::Verdict.hypothesis`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two segments of one metric
- **Steps:** build hypotheses
- **Expected:** distinct identities
- **Why:** two hypotheses with one identity is a family whose size the selector
  gets wrong.

### MON-084 · The adaptive calibrator's level is what the verdict reports
- **Area:** `monitor/fleet.py::Monitor.judge`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an adaptive monitor after many judgements
- **Steps:** read `verdict.level`
- **Expected:** the adapted level, not the configured alpha
- **Why:** a card claiming a 1% budget while the monitor is testing at 4% is the
  kind of claim this wave exists to stop making.

### MON-085 · Recency weighting is off by default
- **Area:** `monitor/fleet.py::Monitor.__init__`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a monitor built with no `half_life`
- **Steps:** judge, and confirm no weights are passed to the calibrator
- **Expected:** none
- **Why:** "None means no recency weighting, and therefore exact validity …
  paying resolution for drift robustness should be a decision somebody made
  rather than one that arrived with the class."

### MON-086 · `MetricKind.is_bounded` is true for exactly two kinds
- **Area:** `monitor/fleet.py::MetricKind.is_bounded`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** check all seven
- **Expected:** `NULL_RATE` and `DISTRIBUTION`
- **Why:** it chooses the default detector; `FRESHNESS` is also bounded below at
  zero and is deliberately not in the list — confirm the choice.

### MON-087 · `FRESHNESS` defaults to `ForecastResidual`
- **Area:** `monitor/fleet.py::_default_detector`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a freshness monitor
- **Steps:** read the detector
- **Expected:** `ForecastResidual`
- **Why:** lateness has momentum; a robust-deviation monitor on it alerts every
  day a backlog is clearing.

### MON-088 · A default detector is overridable
- **Area:** `monitor/fleet.py::Monitor.__init__`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** an explicit detector for a bounded metric
- **Steps:** read
- **Expected:** the explicit one
- **Why:** "A default rather than a decision."

### MON-089 · `FleetReport.alerting`, `unjudgeable` and `degraded` partition sensibly
- **Area:** `monitor/fleet.py::FleetReport`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a fleet with one of each
- **Steps:** read all three
- **Expected:** an unjudgeable verdict is never in `alerting`; a degraded one may
  be in both `alerting` and `degraded`
- **Why:** the three are read as a summary line, and an operator needs to know
  whether they add up to the total.

### MON-090 · `describe` renders correctly for an empty fleet
- **Area:** `monitor/fleet.py::FleetReport.describe`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** no verdicts
- **Steps:** render
- **Expected:** "0 monitors ran" and zeros, no division
- **Why:** the first run of a new estate.

### MON-091 · `SegmentedMonitor` runs the same test per segment
- **Area:** `monitor/fleet.py::SegmentedMonitor.judge`
- **Type:** functional
- **Priority:** P1
- **Precondition:** three segments, one of which is entirely broken
- **Steps:** judge
- **Expected:** the broken segment alerts; the others do not
- **Why:** "'0.4% of LEIs are missing' and 'every LEI is missing for one legal
  entity' are the same number and different incidents".

### MON-092 · An observation for an unknown segment is dropped silently
- **Area:** `monitor/fleet.py::SegmentedMonitor.judge`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an observation whose segment was not declared
- **Steps:** judge
- **Expected:** either it is reported as unjudgeable, or the drop is documented
- **Why:** the comprehension filters it out with no record; a new legal entity
  appearing in the data is exactly the thing a segmented monitor should notice.

### MON-093 · Segments form one family for selection
- **Area:** `monitor/fleet.py::SegmentedMonitor.hypotheses`
- **Type:** functional
- **Priority:** P1
- **Precondition:** forty segments failing
- **Steps:** build hypotheses and select
- **Expected:** every hypothesis shares the `dataset.metric` parent
- **Why:** "a failure across most of them rolls up into one finding rather than
  forty".

### MON-094 · Each segment's monitor holds its own calibration
- **Area:** `monitor/fleet.py::SegmentedMonitor.__init__`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** two segments with very different histories
- **Steps:** judge both
- **Expected:** the calibrations do not interfere
- **Why:** one `Monitor` per segment is what makes the conditioning real; a
  shared one would be the pooled band again.

### MON-095 · A mandatory attribute gets a zero-tolerance prior
- **Area:** `monitor/coldstart.py::ColdStart.for_attribute`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an attribute declared mandatory
- **Steps:** build the prior
- **Expected:** `low=0, high=0`, source `DECLARATION`, explanation naming the
  declaration
- **Why:** "any missing value at all is a departure from what was declared" — the
  declaration beats every statistic on day one.

### MON-096 · A semantic type implies its null-rate band
- **Area:** `monitor/coldstart.py::SEMANTIC_NULL_RATES`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an optional attribute of each of the nine semantic types
- **Steps:** build the prior
- **Expected:** the documented band, source `SEMANTIC_TYPE`
- **Why:** "an ISIN column with a 40% null rate is wrong wherever it appears" —
  each of the nine is a separate claim about the world.

### MON-097 · `uuid` admits no nulls at all
- **Area:** `monitor/coldstart.py::SEMANTIC_NULL_RATES`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a uuid attribute
- **Steps:** `admits(0.0)` and `admits(0.001)`
- **Expected:** true, then false
- **Why:** the band is `(0.0, 0.0)`; a zero-width band on an optional attribute
  is a strong claim and must be intentional.

### MON-098 · A declaration beats a semantic type
- **Area:** `monitor/coldstart.py::for_attribute`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a mandatory ISIN attribute
- **Steps:** build
- **Expected:** the `DECLARATION` prior, not the `SEMANTIC_TYPE` one
- **Why:** the ordering of the branches is the ranking, and a declaration is the
  only origin that is authoritative about intent.

### MON-099 · Siblings are used only with at least three
- **Area:** `monitor/coldstart.py::for_attribute`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two siblings, then three
- **Steps:** build
- **Expected:** the estate default, then the sibling band
- **Why:** a band derived from two observations is a band derived from noise.

### MON-100 · The sibling band is widened and clamped
- **Area:** `monitor/coldstart.py::for_attribute`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** siblings at 0.4 and 0.6
- **Steps:** build
- **Expected:** `low=0.2`, `high=1.0` — halved and doubled, clamped to [0, 1]
- **Why:** a null rate above 1.0 is impossible and would make `admits` never
  fire.

### MON-101 · The estate default is the weakest and says so
- **Area:** `monitor/coldstart.py::for_attribute`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an attribute with no declaration, no known type and no
  siblings
- **Steps:** build
- **Expected:** source `DEFAULT`, and the explanation says it is "here only
  because the alternative is no monitoring at all"
- **Why:** the honesty of the weakest prior is what makes the strongest
  believable.

### MON-102 · A prior is never calibrated
- **Area:** `monitor/coldstart.py::Prior.is_calibrated`
- **Type:** contract
- **Priority:** P1
- **Precondition:** any prior
- **Steps:** read
- **Expected:** `False`
- **Why:** "A prior is not a calibration and never becomes one" — any code path
  asking "can I promise a false-alarm rate here?" must get the same answer from a
  prior as from an uncalibrated monitor.

### MON-103 · Every prior-based verdict carries its disclosure
- **Area:** `monitor/coldstart.py::Prior.disclosure`
- **Type:** security
- **Priority:** P1
- **Precondition:** a prior
- **Steps:** render
- **Expected:** "this is a prior, not a measurement", with the explanation and
  "No false-alarm rate is promised"
- **Why:** "saying '0.01' next to it would be a lie of exactly the kind this wave
  exists to stop telling".

### MON-104 · `for_volume` returns None when no rhythm declared a range
- **Area:** `monitor/coldstart.py::ColdStart.for_volume`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a declaration with no rhythm, and one with a rhythm but no
  volume bounds
- **Steps:** call
- **Expected:** `None` in both cases
- **Why:** inventing a volume band would be the weakest possible prior presented
  as a declaration.

### MON-105 · A one-sided volume range is honoured
- **Area:** `monitor/coldstart.py::for_volume`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a minimum but no maximum
- **Steps:** build
- **Expected:** `low` set, `high` infinite; the explanation renders infinity
  readably rather than as "inf"
- **Why:** `f"{high:,.0f}"` on infinity produces `inf` in the middle of a
  sentence a business owner reads.

### MON-106 · `for_dataset` puts volume first
- **Area:** `monitor/coldstart.py::for_dataset`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a declaration with a volume rhythm and three attributes
- **Steps:** call
- **Expected:** four priors, volume first
- **Why:** the ordering is what a screen shows; volume is the metric a person
  looks at first on a new feed.

### MON-107 · The handover from prior to calibration is announced
- **Area:** `monitor/coldstart.py::Handover.describe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a handover
- **Steps:** render
- **Expected:** the count of its own observations and what the prior had been
- **Why:** "A monitor whose basis changes without saying so has, from the
  reader's point of view, started behaving differently for no reason."

### MON-108 · A model card is derived from the running monitor
- **Area:** `monitor/cards.py::card_for`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a configured monitor
- **Steps:** build a card, then change the detector and rebuild
- **Expected:** the card changes
- **Why:** "It is derived, not written … A hand-written card is accurate on the
  day it is written."

### MON-109 · The card states what the monitor is blind to
- **Area:** `monitor/cards.py::ModelCard.render`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** any card
- **Steps:** render
- **Expected:** the `blind_to` sentence appears
- **Why:** "a card that lists only strengths is the kind of document that gets
  quoted back after an incident nobody caught".

### MON-110 · The card says when the budget cannot be expressed
- **Area:** `monitor/cards.py::ModelCard.budget_is_expressible`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** alpha 0.01 against a group of 24 (resolution 0.04)
- **Steps:** render
- **Expected:** the "promise cannot currently be kept" section, naming both
  numbers
- **Why:** the honest bound on what the budget dial can promise, and the case
  that occurs on every year end.

### MON-111 · A budget exactly equal to the resolution is expressible
- **Area:** `monitor/cards.py::budget_is_expressible`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** alpha 0.04, resolution 0.04
- **Steps:** read
- **Expected:** `True` — the comparison is `>=`
- **Why:** the boundary decides whether the warning fires on the most common
  configuration.

### MON-112 · Precision is precision, not accuracy
- **Area:** `monitor/cards.py::PrecisionHistory`
- **Type:** contract
- **Priority:** P1
- **Precondition:** 34 alerts, 29 confirmed, 5 unreviewed
- **Steps:** read `precision`, `reviewed`, `describe`
- **Expected:** 29/29 over the reviewed, the unreviewed counted separately
- **Why:** "Accuracy on a monitor that alerts twice a year is 99.5% whatever it
  does."

### MON-113 · Precision is None when nothing has been reviewed
- **Area:** `monitor/cards.py::PrecisionHistory.precision`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** ten alerts, none reviewed
- **Steps:** read
- **Expected:** `None`, and `describe` says "none of them reviewed yet"
- **Why:** a zero would read as "always wrong" and a one as "always right"; both
  are claims the data does not support.

### MON-114 · `with_alert` and `with_outcome` keep the arithmetic consistent
- **Area:** `monitor/cards.py::PrecisionHistory`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a sequence of alerts and reviews in every order
- **Steps:** apply
- **Expected:** `reviewed` never negative, `confirmed <= reviewed <= raised`
- **Why:** `with_outcome` decrements `unreviewed` with a floor of zero but does
  not check that an alert exists to review — a stray outcome would make
  `confirmed` exceed `reviewed`.

### MON-115 · A card records the version and the seasonal facets
- **Area:** `monitor/cards.py::ModelCard.render`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** a card built with a version and a grouping
- **Steps:** render
- **Expected:** "Prama <version>; seasonal grouping on <facets>"
- **Why:** "'which version of what, against which calibration window' is the
  first question when two runs disagree".

### MON-116 · A card with no grouping renders "nothing yet"
- **Area:** `monitor/cards.py::card_for`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `grouping=None`
- **Steps:** render
- **Expected:** "nothing yet", resolution 1.0, and the budget shown as
  inexpressible
- **Why:** a brand-new monitor's card must be printable and must not claim a
  budget.

### MON-117 · A challenger below the shadow minimum is held
- **Area:** `monitor/tournament.py::Tournament.judge`, `MINIMUM_SHADOW`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 199 and 200 shadow observations
- **Steps:** judge
- **Expected:** `HOLD` then a real decision
- **Why:** "Fewer than this and the comparison is between two samples of noise."

### MON-118 · A challenger with no reviewed alerts is held
- **Area:** `monitor/tournament.py::judge`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 300 observations, 20 alerts, none reviewed
- **Steps:** judge
- **Expected:** `HOLD` with the stated reason
- **Why:** promoting on unreviewed alerts is promoting on nothing.

### MON-119 · A challenger that missed anything the champion caught is referred
- **Area:** `monitor/tournament.py::judge`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a challenger with much better precision and one miss
- **Steps:** judge
- **Expected:** `REFER`, not `PROMOTE`
- **Why:** "Regression is disqualifying even when the average improves" — the
  asymmetry is the design.

### MON-120 · A material improvement with nothing lost is promoted
- **Area:** `monitor/tournament.py::judge`, `MATERIAL_MARGIN`
- **Type:** functional
- **Priority:** P1
- **Precondition:** precision 0.70 against 0.76, no misses, 300 observations
- **Steps:** judge
- **Expected:** `PROMOTE`
- **Why:** the happy path, and the 0.05 margin is exact — test 0.749 and 0.751.

### MON-121 · An improvement inside the margin is held
- **Area:** `monitor/tournament.py::judge`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an improvement of 0.03
- **Steps:** judge
- **Expected:** `HOLD` — "promoting on this would mean promoting whichever
  challenger was luckiest"
- **Why:** "a coin-flip's worth of improvement is not an improvement".

### MON-122 · A materially worse challenger is retired
- **Area:** `monitor/tournament.py::judge`
- **Type:** functional
- **Priority:** P2
- **Precondition:** precision 0.60 against 0.80
- **Steps:** judge
- **Expected:** `RETIRE` naming both numbers
- **Why:** a challenger that stays in shadow for ever consumes compute and
  attention.

### MON-123 · A champion with no reviewed alerts yields to a challenger
- **Area:** `monitor/tournament.py::judge`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** champion precision `None`, challenger 0.8 over 50 reviewed
- **Steps:** judge
- **Expected:** `PROMOTE` with the "nothing to defend" reason
- **Why:** the branch formats `challenger_precision` before asserting it is not
  None — confirm a challenger with reviewed alerts is guaranteed by the earlier
  guard.

### MON-124 · `should_roll_back` needs twenty reviewed alerts
- **Area:** `monitor/tournament.py::should_roll_back`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** 19 reviewed, then 20
- **Steps:** call
- **Expected:** empty, then the rollback sentence
- **Why:** rolling back on nineteen judgements repeats the small-sample mistake
  the promotion gate exists to avoid.

### MON-125 · Rollback fires only past the tolerance
- **Area:** `monitor/tournament.py::should_roll_back`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a promoted monitor 0.09 and 0.11 below its predecessor
- **Steps:** call
- **Expected:** empty, then the rollback
- **Why:** production precision wobbles; a tolerance of zero would roll back
  every promotion.

### MON-126 · `shadow_record` excludes unjudged alerts from the counts
- **Area:** `monitor/tournament.py::shadow_record`
- **Type:** contract
- **Priority:** P1
- **Precondition:** confirmations `[True, None, False]`
- **Steps:** build
- **Expected:** `reviewed=2`, `confirmed=1`
- **Why:** "treating unreviewed alerts as correct is how a challenger gets
  promoted on the strength of alerts nobody read".

### MON-127 · `alert_rate` handles zero observations
- **Area:** `monitor/tournament.py::Record.alert_rate`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a record with no observations
- **Steps:** read
- **Expected:** `0.0`
- **Why:** it is rendered as a percentage in `describe` on every judgement.

### MON-128 · Every benchmark regime produces the documented behaviour
- **Area:** `monitor/benchmark.py::REGIMES`
- **Type:** functional
- **Priority:** P1
- **Precondition:** seed 17
- **Steps:** generate each of the five series and characterise it
- **Expected:** stationary has constant mean and variance; seasonal has an
  order-of-magnitude weekday/weekend split; level shift has one step; regime
  switch alternates every hundred; bursty has constant mean and moving variance
- **Why:** "A row that is green everywhere would mean the regimes are not hard
  enough" — a regime that does not break what it claims to break makes its whole
  column meaningless.

### MON-129 · A regime series is reproducible from its seed
- **Area:** `monitor/benchmark.py::Regime.series`
- **Type:** contract
- **Priority:** P1
- **Precondition:** seed 17
- **Steps:** generate twice
- **Expected:** identical
- **Why:** a benchmark whose numbers change between runs cannot distinguish a
  regression from a reroll.

### MON-130 · Every cell of the grid is computed
- **Area:** `monitor/benchmark.py::run`
- **Type:** functional
- **Priority:** P1
- **Precondition:** default arguments
- **Steps:** run
- **Expected:** 25 cells, each with five nominal levels
- **Why:** "the benchmark runs each regime against each mechanism and reports the
  grid".

### MON-131 · Calibration error is the mean absolute deviation
- **Area:** `monitor/benchmark.py::Cell.calibration_error`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a cell firing at twice the nominal rate at one level and half
  at another
- **Steps:** read
- **Expected:** a non-zero error
- **Why:** "Signed deviation would average a monitor that fires twice as often as
  promised against one that fires half as often and call the pair perfect."

### MON-132 · A liberal cell is flagged as such
- **Area:** `monitor/benchmark.py::Cell.is_liberal`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a cell firing above nominal plus the target at one level
- **Steps:** read `is_liberal` and `describe`
- **Expected:** true, and the description says "fires more often than promised"
- **Why:** "the direction that breaks the promise rather than merely wasting
  sensitivity".

### MON-133 · An empty cell reports the worst possible error
- **Area:** `monitor/benchmark.py::Cell.calibration_error`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a cell where no p-value could be produced
- **Steps:** read
- **Expected:** `1.0`, and `meets_target` false
- **Why:** a mechanism that never produced a verdict must not score as perfect.

### MON-134 · Every regime has a mechanism that meets the target
- **Area:** `monitor/benchmark.py::BenchmarkReport.every_regime_has_a_mechanism`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the full grid at the default seed
- **Steps:** run
- **Expected:** `True`, with calibration error at or below 0.02 for the best
  mechanism in each regime
- **Why:** this is `W7.13`, the wave's headline acceptance criterion, stated as
  an executable claim.

### MON-135 · The changepoint mechanism beats forgetting on a level shift
- **Area:** `monitor/benchmark.py::Mechanism.CHANGEPOINT`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the level-shift regime
- **Steps:** compare the changepoint and weighted cells
- **Expected:** changepoint has the lower error
- **Why:** "a twelve-sigma step makes every subsequent observation more extreme
  than the whole pre-shift calibration set, so every p-value sits at its floor —
  forgetting is too slow".

### MON-136 · Seasonal conditioning beats weighting on the seasonal regime
- **Area:** `monitor/benchmark.py`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the seasonal regime
- **Steps:** compare the seasonal and weighted cells
- **Expected:** seasonal is better; weighting is *worse* than plain
- **Why:** "Recency weighting makes it worse, because the recent past is Friday
  and today is Monday." A result where weighting helps means the regime is not
  seasonal.

### MON-137 · Adaptation beats forgetting on a regime switch
- **Area:** `monitor/benchmark.py`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the regime-switch regime
- **Steps:** compare adaptive and weighted
- **Expected:** adaptive is better
- **Why:** "a monitor that has forgotten the old regime is wrong again the moment
  it returns" — the case the adaptive mechanism exists for.

### MON-138 · `_after_changepoint` keeps the old history when too little remains
- **Area:** `monitor/benchmark.py::_after_changepoint`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a shift ten observations ago
- **Steps:** call
- **Expected:** the full history
- **Why:** "the old regime is a poor reference but a better one than none".

### MON-139 · `_after_changepoint` ignores a weak break
- **Area:** `monitor/benchmark.py::_after_changepoint`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a stationary series whose best split has strength below 1.5
- **Steps:** call
- **Expected:** the full history
- **Why:** "recalibrating on noise throws away the history a monitor needs, and a
  monitor that keeps discarding its past never accumulates enough to promise
  anything".

### MON-140 · Every observation in the benchmark is a false alarm by construction
- **Area:** `monitor/benchmark.py::measure`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** confirm no anomalies are injected into any regime
- **Expected:** none are
- **Why:** "Anything that alerts is therefore a false alarm by construction,
  which is what makes the realised rate directly comparable with the nominal
  level." If a regime ever gains an injected anomaly, every number in the grid
  changes meaning.

## Incidents

### INC-001 · A feed failure across twelve datasets is one incident
- **Area:** `incident/correlate.py::Correlator.correlate`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a lineage graph where twelve datasets descend from one
  column; four hundred findings across them
- **Steps:** correlate
- **Expected:** one incident, `common_ancestor` set to the column
- **Why:** the acceptance criterion the module exists for: "a feed that fails to
  arrive must produce **one** incident, not four hundred".

### INC-002 · Correlation reports how much noise it removed
- **Area:** `incident/correlate.py::Correlation.reduction`
- **Type:** functional
- **Priority:** P2
- **Precondition:** as above
- **Steps:** read `reduction` and `describe`
- **Expected:** "400 findings became 1 incident (100% fewer things to look at)"
- **Why:** "How much noise the correlation removed. The number to publish."

### INC-003 · No findings gives an empty correlation, not a crash
- **Area:** `incident/correlate.py::correlate`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an empty list
- **Steps:** correlate
- **Expected:** an empty `Correlation`, `reduction` 0.0
- **Why:** a clean night is the common case and must not divide by zero.

### INC-004 · A single finding is one incident with full confidence
- **Area:** `incident/correlate.py::Incident.confidence`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** one finding
- **Steps:** read `confidence`
- **Expected:** `1.0`
- **Why:** "Reporting zero for it — which the signal arithmetic does on its own —
  reads as 'we are not sure this is an incident', which is a different and much
  more alarming claim."

### INC-005 · Signals combine as independent evidence, not by averaging
- **Area:** `incident/correlate.py::Incident.confidence`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an incident with lineage (0.8) and time (0.15)
- **Steps:** read `confidence`
- **Expected:** `1 - (0.2 * 0.85) = 0.83`, above the lineage signal alone
- **Why:** "averaging lets a time coincidence drag a well-supported grouping down
  to its level".

### INC-006 · A time-only grouping is marked speculative
- **Area:** `incident/correlate.py::Incident.is_speculative`
- **Type:** functional
- **Priority:** P1
- **Precondition:** findings grouped with no lineage and no change
- **Steps:** read `is_speculative` and `describe`
- **Expected:** true, and the description warns it "occasionally merges two
  unrelated problems"
- **Why:** "the person triaging needs to know which kind they are holding".

### INC-007 · A single finding is never speculative
- **Area:** `incident/correlate.py::Incident.is_speculative`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** one finding with a timestamp
- **Steps:** read
- **Expected:** `False`
- **Why:** "there is no grouping to be wrong about".

### INC-008 · Without a graph, correlation falls back to dataset and time
- **Area:** `incident/correlate.py::_by_dataset_and_time`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `graph=None`, findings across three datasets
- **Steps:** correlate
- **Expected:** one incident per dataset per window
- **Why:** "a graph that does not reach everywhere degrades rather than fails".

### INC-009 · Findings without a column fall back even when a graph exists
- **Area:** `incident/correlate.py::_by_ancestor`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a graph, and findings with no `column`
- **Steps:** correlate
- **Expected:** they are grouped by dataset and time, and are not lost
- **Why:** the rebuild of `groups` after removing the lineage-less findings is
  where one could silently disappear.

### INC-010 · The deepest shared ancestor is chosen, not the broadest
- **Area:** `incident/correlate.py::_shared_ancestor`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a chain where everything shares a raw feed but two findings
  share a nearer derived column
- **Steps:** correlate
- **Expected:** the incident names the derived column
- **Why:** "everything shares 'the raw feed' eventually, and an incident about
  the raw feed when the fault is in one derived column sends people to the wrong
  system".

### INC-011 · Table-level grouping is not what happens
- **Area:** `incident/correlate.py::_by_ancestor`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a warehouse feeding everything
- **Steps:** correlate two unrelated failures
- **Expected:** two incidents, not one about "the warehouse"
- **Why:** "Table-level would identify the common ancestor as 'the warehouse',
  which groups everything into one incident every night and is worse than not
  grouping at all."

### INC-012 · Two columns of one broken source fold into one incident
- **Area:** `incident/correlate.py::_merge_by_dataset`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a sub-ledger whose `amount` and `account` columns both break
- **Steps:** correlate
- **Expected:** one incident naming `subledger.*`
- **Why:** "this module's own failure, one level up" — two roots of two subgraphs
  reported as two problems about one sub-ledger.

### INC-013 · A lone finding is folded in by its upstream closure
- **Area:** `incident/correlate.py::_merge_by_dataset`
- **Type:** regression
- **Priority:** P1
- **Precondition:** one finding whose ancestor resolves to itself but whose
  sources reach the shared dataset
- **Steps:** correlate
- **Expected:** merged
- **Why:** "comparing ancestors directly misses exactly the lone finding that
  most needs folding in".

### INC-014 · Two columns of one table failing a fortnight apart are two incidents
- **Area:** `incident/correlate.py::_overlapping`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** as described, with timestamps two weeks apart
- **Steps:** correlate
- **Expected:** two incidents
- **Why:** "two columns of one warehouse table failing a fortnight apart are two
  problems that happen to share a table".

### INC-015 · Findings with no timestamps are treated as overlapping
- **Area:** `incident/correlate.py::_overlapping`, `_within_window`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** findings with `at=None`
- **Steps:** correlate
- **Expected:** grouped — the absence of a time is not evidence of separation
- **Why:** the permissive default is deliberate; confirm it and confirm that a
  mixture of timed and untimed findings behaves sensibly.

### INC-016 · The default window is an hour
- **Area:** `incident/correlate.py::DEFAULT_WINDOW`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** findings 59 and 61 minutes apart
- **Steps:** correlate on the dataset-and-time path
- **Expected:** grouped, then separate
- **Why:** "a nightly batch runs over about that long and two failures at
  opposite ends of it are usually the same batch".

### INC-017 · A change before the findings is attached
- **Area:** `incident/correlate.py::_nearest_change`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a deploy at midnight touching the ancestor; failures at 06:00
- **Steps:** correlate
- **Expected:** the change is attached, with a `CHANGE` signal
- **Why:** "'these twelve things broke twenty minutes after somebody changed
  that' … is a sentence with a next step in it".

### INC-018 · A change after the findings is not attached
- **Area:** `incident/correlate.py::_nearest_change`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a change an hour after the earliest finding
- **Steps:** correlate
- **Expected:** not attached
- **Why:** a change that cannot have caused it is the most misleading thing an
  incident can point at.

### INC-019 · A change older than the lookback is not attached
- **Area:** `incident/correlate.py::CHANGE_LOOKBACK`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** changes 11 and 13 hours before
- **Steps:** correlate
- **Expected:** attached, then not
- **Why:** "Longer than the correlation window on purpose: a deploy at midnight
  explains a failure at six."

### INC-020 · Only the nearest matching change is attached
- **Area:** `incident/correlate.py::_nearest_change`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** four qualifying changes
- **Steps:** correlate
- **Expected:** the latest one only
- **Why:** "a list of eleven changes is a list nobody reads".

### INC-021 · A change touching only an unrelated dataset is not attached
- **Area:** `incident/correlate.py::_nearest_change`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a recent change touching something else
- **Steps:** correlate
- **Expected:** no change signal
- **Why:** the intersection of `touched` with the incident's datasets and columns
  is the whole filter.

### INC-022 · Incidents are ordered largest first, then stably
- **Area:** `incident/correlate.py::correlate`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** incidents of sizes 4, 4 and 1
- **Steps:** correlate twice
- **Expected:** the same order both times
- **Why:** a triage screen that reorders itself between refreshes is one nobody
  can work through.

### INC-023 · An incident's identity is stable across runs
- **Area:** `incident/correlate.py::_build`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the same findings correlated twice
- **Steps:** compare identities
- **Expected:** identical
- **Why:** the alert router deduplicates on the alert's identity; an identity
  that changed between hourly runs would alert every hour, which is the exact
  failure `alert/route.py` exists to prevent.

### INC-024 · `datasets` preserves first-seen order and deduplicates
- **Area:** `incident/correlate.py::Incident.datasets`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** findings across three datasets, some repeated
- **Steps:** read
- **Expected:** three, in first-seen order
- **Why:** the count is printed in the incident's own description.

### INC-025 · `to_dict` renders every signal and the confidence
- **Area:** `incident/correlate.py::Incident.to_dict`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a full incident
- **Steps:** serialise through `pjson`
- **Expected:** every field present and JSON-safe; no naive datetimes
- **Why:** the API renders this document; a naive datetime raises inside the
  serialiser.

### INC-026 · RCA with no lineage origin returns an empty analysis
- **Area:** `incident/rca.py::RootCause.analyse`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an incident with no ancestor and no column on its findings
- **Steps:** analyse
- **Expected:** an `Analysis` with no hypotheses; `describe` says the cause is in
  the dataset itself or outside the graph
- **Why:** an empty list with an explanation is useful; an empty list without one
  reads as a failure.

### INC-027 · The origin is always a candidate
- **Area:** `incident/rca.py::analyse`
- **Type:** regression
- **Priority:** P1
- **Precondition:** an incident whose origin is the defect
- **Steps:** analyse
- **Expected:** the origin appears, with a proximity rationale saying the
  failures converge there
- **Why:** "an earlier version gave it no evidence at all, so it was omitted from
  its own analysis and the nearest upstream column ranked first".

### INC-028 · A demonstrated upstream failure outranks everything
- **Area:** `incident/rca.py::Evidence.weight`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an upstream column failing its own controls, and another with
  a recent change
- **Steps:** analyse
- **Expected:** the failing column ranks first; `is_demonstrated` is true
- **Why:** "a system that ranks a speculative cause above a demonstrated upstream
  failure is ranking on the wrong axis".

### INC-029 · Proximity is limited to three hops
- **Area:** `incident/rca.py::analyse`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a chain six hops deep with no other evidence
- **Steps:** analyse
- **Expected:** the columns beyond depth two carry no proximity evidence and are
  dropped
- **Why:** "a defect that travelled six hops would have been caught by something
  on the way if anything on the way were watching".

### INC-030 · Every hypothesis carries a check that can be run
- **Area:** `incident/rca.py::_hypothesis`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** one hypothesis of each of the three shapes
- **Steps:** read `check`, `confirms` and `rules_out`
- **Expected:** each names a specific artefact — a control's last result, a
  change's diff, a source comparison — never "investigate upstream"
- **Why:** "A hypothesis nobody can settle in a few minutes is not a hypothesis;
  it is a shrug with a rank."

### INC-031 · Every hypothesis says what would rule it out
- **Area:** `incident/rca.py::Hypothesis`
- **Type:** contract
- **Priority:** P1
- **Precondition:** all three shapes
- **Steps:** read `rules_out`
- **Expected:** non-empty and genuinely falsifying
- **Why:** "a check that can only confirm is a check that always confirms".

### INC-032 · A prior raises a hypothesis that would otherwise not appear
- **Area:** `incident/rca.py::analyse`, `Evidence.PRIOR`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a column four hops upstream that has been the confirmed cause
  three times
- **Steps:** analyse
- **Expected:** it appears, ranked low
- **Why:** "Weak individually and worth having because it is free, and because
  the answer is often the same as last time."

### INC-033 · Ties break toward the origin, then by name
- **Area:** `incident/rca.py::analyse`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two equally-supported hypotheses, one of them the origin
- **Steps:** analyse
- **Expected:** the origin first
- **Why:** "Without the first the ordering among equally-supported hypotheses is
  alphabetical, which puts whichever column sorts first at the top of a root
  cause analysis."

### INC-034 · `is_conclusive` requires a clear lead
- **Area:** `incident/rca.py::Analysis.is_conclusive`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** scores of 0.9 and 0.6, then 0.9 and 0.7
- **Steps:** read
- **Expected:** true, then false
- **Why:** the threshold is `>= 1.5x`; "presenting the first as the second is how
  an RCA loses its reader the second time it is wrong".

### INC-035 · A single hypothesis is conclusive
- **Area:** `incident/rca.py::is_conclusive`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** one hypothesis
- **Steps:** read
- **Expected:** `True`
- **Why:** there is nothing to be uncertain between — confirm the empty case is
  `False` rather than raising.

### INC-036 · An inconclusive analysis says so in its summary
- **Area:** `incident/rca.py::Analysis.describe`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** four close hypotheses
- **Steps:** render
- **Expected:** "this is where to start rather than the answer"
- **Why:** the sentence is the difference between an RCA a person trusts twice
  and one they trust once.

### INC-037 · `considered` counts what was examined
- **Area:** `incident/rca.py::Analysis.considered`
- **Type:** functional
- **Priority:** P2
- **Precondition:** forty upstream columns, five hypotheses
- **Steps:** read
- **Expected:** 41 considered, 5 offered
- **Why:** "so the analysis can say how wide it looked without listing forty
  things".

### INC-038 · The hypothesis list is capped
- **Area:** `incident/rca.py::RootCause.__init__`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** twenty supported hypotheses, `limit=5`
- **Steps:** analyse
- **Expected:** five, the highest scoring
- **Why:** the cap is applied after sorting; a cap before sorting would return an
  arbitrary five.

### INC-039 · `_touches` matches a dataset-wide incident against a column change
- **Area:** `incident/rca.py::_touches`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an incident on `subledger.*` and a change touching
  `subledger.amount`
- **Steps:** analyse
- **Expected:** the change is evidence
- **Why:** "Comparing only exact qualified names would fail to connect the two,
  and the analysis would lose the strongest evidence it had for the most
  clearly-diagnosed incidents."

### INC-040 · `_touches` does not match an unrelated dataset with a similar name
- **Area:** `incident/rca.py::_touches`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an incident on `ledger` and a change touching
  `ledger_archive.amount`
- **Steps:** analyse
- **Expected:** no match
- **Why:** the `startswith(f"{dataset}.")` and `rpartition` tests are both prefix
  comparisons; a near-miss name is the realistic false positive.

### INC-041 · `learn_from` counts confirmed causes
- **Area:** `incident/rca.py::learn_from`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a list of confirmed (incident, column) pairs
- **Steps:** call
- **Expected:** counts per column
- **Why:** "Deliberately counts rather than a model. There is nothing a model
  would add that a count does not" — and the count can be printed, argued with
  and reset.

## Alerts and routing

### INC-042 · Routing follows the fault, not the severity
- **Area:** `alert/route.py::Fault.route_to`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an arrival fault at severity 0.1 and a definition fault at
  0.9
- **Steps:** dispatch both
- **Expected:** the custodian, then the steward
- **Why:** "Sending each to the other is how an incident spends its first hour,
  and severity says nothing about which it is."

### INC-043 · Every fault kind routes somewhere
- **Area:** `alert/route.py::Fault.route_to`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** check all six
- **Expected:** arrival and schema to the custodian; value, definition and
  reconciliation to the steward; calibration to the custodian
- **Why:** a fault with no route is a finding nobody sees.

### INC-044 · A calibration fault does not go to a steward
- **Area:** `alert/route.py::Fault.route_to`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a calibration fault
- **Steps:** dispatch
- **Expected:** the custodian
- **Why:** "A monitor that has stopped being calibrated is Prama's problem, not
  the business's, and telling a steward about it teaches them to ignore Prama's
  messages."

### INC-045 · An alert with no recipient is quiet and says why
- **Area:** `alert/route.py::Router.dispatch`
- **Type:** negative
- **Priority:** P1
- **Precondition:** no contact for the dataset in any role
- **Steps:** dispatch
- **Expected:** `Delivery.QUIET` with a reason naming the missing role and
  telling the operator to assign one
- **Why:** "an alert with no recipient is a finding nobody will see".

### INC-046 · A missing role falls back to the owner
- **Area:** `alert/route.py::Router._recipients`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an owner but no custodian for the dataset
- **Steps:** dispatch an arrival fault
- **Expected:** the owner receives it, in the owner role
- **Why:** "The owner is accountable and can reassign; nobody is a black hole."

### INC-047 · The same incident does not alert every run
- **Area:** `alert/route.py::Router._change`, `DEFAULT_QUIET`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the same alert dispatched hourly for three hours
- **Steps:** dispatch each
- **Expected:** the first is sent; the next two are `UNCHANGED` and not sent
- **Why:** "A feed that has been broken for three days and is checked hourly has
  produced seventy-two alerts, and the seventy-second is indistinguishable from
  the first."

### INC-048 · The fingerprint ignores the message
- **Area:** `alert/route.py::Alert.fingerprint`
- **Type:** contract
- **Priority:** P1
- **Precondition:** two alerts identical except that one quotes 62% and the other
  63%
- **Steps:** compare fingerprints
- **Expected:** identical
- **Why:** "A message that changes slightly between runs — a count, a percentage
  — would make every run a new alert, which is the failure this whole module is
  about."

### INC-049 · A worsening alert breaks the quiet period
- **Area:** `alert/route.py::Router._change`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an alert sent at severity 0.4, then re-raised at 0.6
- **Steps:** dispatch
- **Expected:** `WORSENED`, sent
- **Why:** "the messages after the first exist to say what changed".

### INC-050 · A small change in severity is still unchanged
- **Area:** `alert/route.py::Router._change`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** severity moving by 0.09 and by 0.11
- **Steps:** dispatch
- **Expected:** `UNCHANGED`, then `WORSENED`
- **Why:** the 0.1 band is what stops a metric that wobbles from re-alerting
  hourly.

### INC-051 · An improvement is worth sending
- **Area:** `alert/route.py::Change.worth_sending`
- **Type:** functional
- **Priority:** P2
- **Precondition:** severity falling by 0.2
- **Steps:** dispatch
- **Expected:** `IMPROVED`, sent
- **Why:** everything except "still broken" is worth a message.

### INC-052 · A forgotten incident resurfaces after the quiet period
- **Area:** `alert/route.py::Router._change`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an alert sent, then re-raised seven hours later unchanged
- **Steps:** dispatch
- **Expected:** `OPENED`, sent
- **Why:** "short enough that a forgotten incident resurfaces within a working
  day".

### INC-053 · An alert with no timestamp is not recorded for deduplication
- **Area:** `alert/route.py::Router.dispatch`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an alert with `at=None`, dispatched twice
- **Steps:** dispatch both
- **Expected:** either both sent, or the behaviour is documented — the `_sent`
  map is only written when `at` is set
- **Why:** an alert without a timestamp bypasses deduplication entirely, which is
  the one thing this module exists to do.

### INC-054 · A high-severity alert is immediate
- **Area:** `alert/route.py::Alert.needs_immediate`, `DIGEST_CEILING`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** severity 0.49 and 0.50
- **Steps:** dispatch
- **Expected:** digest, then immediate
- **Why:** the threshold is `>=`, and it decides whether somebody is woken.

### INC-055 · A low-severity alert that blocks a submission is immediate
- **Area:** `alert/route.py::Alert.needs_immediate`
- **Type:** functional
- **Priority:** P1
- **Precondition:** severity 0.2, consequence "blocks the FINREP submission"
- **Steps:** dispatch
- **Expected:** immediate, with the reason "blocks a submission"
- **Why:** "a low-severity one blocking a submission in an hour is [immediate].
  Severity is a component; consequence is the rest."

### INC-056 · The word "blocks" is matched case-insensitively and not too eagerly
- **Area:** `alert/route.py::Alert.needs_immediate`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** consequences "Blocks submission", "does not block anything"
  and "unblocks the queue"
- **Steps:** dispatch
- **Expected:** immediate, digest, and — note — `"unblocks"` contains `"blocks"`
- **Why:** a substring test on prose is a classifier, and this one decides
  whether a person is woken at three in the morning.

### INC-057 · A digest collects only digest-delivery dispatches
- **Area:** `alert/route.py::Router.digest`
- **Type:** functional
- **Priority:** P1
- **Precondition:** forty low-severity and two immediate dispatches
- **Steps:** build the digest
- **Expected:** forty items
- **Why:** "Forty low-severity findings at three in the morning is not forty
  alerts, and it is also not silence: it is one message at nine."

### INC-058 · An empty digest says so
- **Area:** `alert/route.py::Digest.compose`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** no dispatches
- **Steps:** compose
- **Expected:** "nothing to report"
- **Why:** a blank message is indistinguishable from a broken sender.

### INC-059 · A digest names the worst five and counts the rest
- **Area:** `alert/route.py::Digest.compose`
- **Type:** functional
- **Priority:** P2
- **Precondition:** forty dispatches
- **Steps:** compose
- **Expected:** a count of findings and datasets, then the five most severe
- **Why:** a digest that listed forty is a message nobody reads, which is the
  problem it was built to solve.

### INC-060 · An alert body says what to do, not only what happened
- **Area:** `alert/route.py::Alert.compose`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** an alert with a consequence and a likely cause
- **Steps:** compose
- **Expected:** the fact, the consequence, and "Likeliest cause: …"
- **Why:** the difference "costs nothing to produce and everything to omit".

### INC-061 · An incident alert says how many findings it stands for
- **Area:** `alert/route.py::Alert.compose`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `covers=400`
- **Steps:** compose
- **Expected:** "(400 findings, one incident)"
- **Why:** the recipient otherwise cannot tell a single failure from a fleet-wide
  one.

### INC-062 · A degraded monitor's disclosure rides on the alert
- **Area:** `alert/route.py::Alert.compose`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a disclosure set
- **Steps:** compose
- **Expected:** the ⚠ clause
- **Why:** "the person reading this at three in the morning is not on the
  dashboard".

### INC-063 · `compose` does not produce double full stops
- **Area:** `alert/route.py::Alert.compose`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** parts that already end in a full stop
- **Steps:** compose
- **Expected:** one full stop each
- **Why:** `part.rstrip(".") + "."` handles it; a message ending "..".  reads as
  a rendering bug in the one place a product must look careful.

### INC-064 · A residency-refused alert is withheld from everybody
- **Area:** `alert/route.py::Router._residency_refusals`
- **Type:** security
- **Priority:** P1
- **Precondition:** a gate refusing one of two recipients
- **Steps:** dispatch
- **Expected:** `QUIET`, with a reason naming the refused recipient; neither
  recipient receives it
- **Why:** "an alert delivered to some of its recipients and silently withheld
  from others is worse than either, because the ones who got it assume everyone
  did".

### INC-065 · The residency refusal explains why an alert is data movement
- **Area:** `alert/route.py::Router.dispatch`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** as above
- **Steps:** read the reason
- **Expected:** "The alert body quotes failing values, so sending it moves the
  tenant's data"
- **Why:** an operator who does not understand why an alert was withheld will
  disable the gate.

### INC-066 · With no gate, nothing is refused
- **Area:** `alert/route.py::Router._residency_refusals`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `gate=None`
- **Steps:** dispatch
- **Expected:** delivered
- **Why:** "most deployments have no obligation and a required argument would be
  one every caller passes None to".

### INC-067 · The region belongs to the channel, not the person
- **Area:** `alert/route.py::Router._recipient`, `channel_regions`
- **Type:** security
- **Priority:** P1
- **Precondition:** one steward reachable on an in-region chat tool and on an
  external pager
- **Steps:** dispatch with each channel configured
- **Expected:** different residency answers
- **Why:** "the same steward reachable on an in-region chat tool and on an
  external pager is two different residency answers".

### INC-068 · A residency check happens before deduplication
- **Area:** `alert/route.py::Router.dispatch`
- **Type:** security
- **Priority:** P1
- **Precondition:** an alert that would be `UNCHANGED` and is also refused
- **Steps:** dispatch
- **Expected:** the residency reason, not the quiet-period one
- **Why:** the order of the branches decides which reason an operator sees, and
  a compliance refusal must not be masked by a routine one.

### INC-069 · `resolve` sends even when the opening alert was a digest item
- **Area:** `alert/route.py::Router.resolve`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a low-severity alert previously digested
- **Steps:** resolve
- **Expected:** a `RESOLVED` dispatch with recipients
- **Why:** "'that thing is fixed' is the message people most want and least often
  get, and its absence is why nobody believes a dashboard".

### INC-070 · `resolve` clears the deduplication state
- **Area:** `alert/route.py::Router.resolve`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a resolved alert that recurs
- **Steps:** dispatch again
- **Expected:** `OPENED`, sent immediately rather than waiting out a quiet period
- **Why:** a recurrence after a resolution is new information.

### INC-071 · `resolve` bypasses the residency gate
- **Area:** `alert/route.py::Router.resolve`
- **Type:** security
- **Priority:** P1
- **Precondition:** a gate that refuses the recipient
- **Steps:** resolve
- **Expected:** the resolution is also withheld, or the difference is documented
- **Why:** `resolve` does not call `_residency_refusals`; a resolution message
  still names the dataset and may quote values, so the asymmetry needs a reason.

### INC-072 · Router state does not leak between tenants
- **Area:** `alert/route.py::Router._sent`
- **Type:** security
- **Priority:** P1
- **Precondition:** two tenants with datasets of the same name
- **Steps:** dispatch an alert in each
- **Expected:** the second is not deduplicated against the first
- **Why:** the fingerprint is over dataset, fault and identity with no tenant; a
  shared router would silence one tenant's alert because another tenant's looked
  the same.

### INC-073 · `Dispatch.sent` combines delivery and change correctly
- **Area:** `alert/route.py::Dispatch.sent`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** each combination of delivery and change
- **Steps:** read
- **Expected:** false for `QUIET` and for `UNCHANGED`, true otherwise
- **Why:** it is what an integration test and an operator both read as "did this
  go out".

## Reports — attestations, packs and charts

### RPT-001 · An attestation names its scope and period
- **Area:** `report/attestation.py::Attestation`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an assembled attestation
- **Steps:** read `scope`, `period_start`, `period_end`
- **Expected:** all three non-empty and in the content hash
- **Why:** "'The controls were fine' with no boundary is a sentence nobody can
  check and nobody can be held to."

### RPT-002 · The evidence root is in the content and in the seal
- **Area:** `report/attestation.py::Attestation.content`
- **Type:** security
- **Priority:** P1
- **Precondition:** an attestation
- **Steps:** change the evidence root and recompute the hash
- **Expected:** the hash changes
- **Why:** "Without it the attestation floats free of the records, and evidence
  written afterwards is indistinguishable from evidence written before."

### RPT-003 · Every field except the seal is inside the hash
- **Area:** `report/attestation.py::Attestation.content`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** compare the dataclass fields with the keys of `content()`
- **Expected:** every field is covered
- **Why:** "a field outside the hash is a field somebody can change after the
  signature, which is the only thing a signature is for".

### RPT-004 · Coverage states what did not run
- **Area:** `report/attestation.py::Coverage.describe`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** 100 in scope, 40 run, 30 passed, 5 failed, 3 errored, 2
  indeterminate, 60 never ran
- **Steps:** render
- **Expected:** every number appears, including "this covers 40% of the scope"
  and "60 never ran at all"
- **Why:** "An attestation over 40% coverage that does not say 40% is worse than
  no attestation: it converts an unexamined estate into a signed one."

### RPT-005 · `rate` and `is_complete` handle an empty scope
- **Area:** `report/attestation.py::Coverage`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `controls_in_scope=0`
- **Steps:** read both
- **Expected:** `0.0` and `False` — not a division by zero and not "complete"
- **Why:** an estate with no controls must not produce an attestation that reads
  as fully covered.

### RPT-006 · `is_clean` is not the same question as "can it be signed"
- **Area:** `report/attestation.py::Coverage.is_clean`
- **Type:** contract
- **Priority:** P1
- **Precondition:** coverage with failures
- **Steps:** build and seal an attestation
- **Expected:** it seals; `is_clean` is false; `is_qualified` is true
- **Why:** "It can be signed either way; the reader needs to know which."

### RPT-007 · Incomplete coverage makes an attestation qualified
- **Area:** `report/attestation.py::Attestation.is_qualified`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** everything that ran passed, but only 40% ran
- **Steps:** read
- **Expected:** qualified
- **Why:** "Presenting one as unqualified is the fraud."

### RPT-008 · Every exception appears individually
- **Area:** `report/attest.py::build`
- **Type:** contract
- **Priority:** P1
- **Precondition:** twelve failing controls in the period
- **Steps:** build
- **Expected:** twelve `Exception_` entries, not a count
- **Why:** "an attestation that summarised them into a count would be asking
  somebody to sign for things they were not shown".

### RPT-009 · Coverage and exceptions are derived, never supplied
- **Area:** `report/attest.py::build`
- **Type:** security
- **Priority:** P1
- **Precondition:** a ledger and an estate
- **Steps:** inspect the signature of `build`
- **Expected:** the attester supplies only the statement, the name, the scope and
  the period; every number comes from `uow`
- **Why:** "An attestation whose figures were typed is a statement about what the
  attester believed; one whose figures were derived is a statement about what
  happened."

### RPT-010 · One line per control, not one per record
- **Area:** `report/attest.py::build`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a control that ran thirty times in the period, failing at the
  end
- **Steps:** build
- **Expected:** one exception, carrying the *last* verdict in the period
- **Why:** "the line is its state at the end of the period rather than the first
  time it was checked".

### RPT-011 · `never_ran` counts live controls with no record in the period
- **Area:** `report/attest.py::build`
- **Type:** functional
- **Priority:** P1
- **Precondition:** ten live controls, four of which produced nothing
- **Steps:** build
- **Expected:** `never_ran == 4`, and they are not exceptions
- **Why:** "there is no verdict to except from — but the number that decides
  whether the attestation means anything".

### RPT-012 · Every non-pass verdict becomes an exception
- **Area:** `report/attest.py::UNRESOLVED`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** one record of each of fail, error, skipped, indeterminate
- **Steps:** build
- **Expected:** four exceptions, each with its own wording
- **Why:** "each has to appear as an exception rather than be folded into a
  total".

### RPT-013 · An unknown verdict is still counted
- **Area:** `report/attest.py::build`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a record with a verdict outside the known set
- **Steps:** build
- **Expected:** an exception carrying the verdict verbatim; the coverage
  arithmetic still adds up
- **Why:** `tally` is seeded from `UNRESOLVED` and then extended with
  `tally.get(...)`; an unknown verdict lands in neither `failed` nor
  `not_established` nor `errored`, so the coverage totals silently disagree with
  the exception list.

### RPT-014 · A missing disposition is permitted and visible
- **Area:** `report/attest.py::build`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** exceptions with no dispositions supplied
- **Steps:** build and render
- **Expected:** blank dispositions, printed as blank
- **Why:** "Blank is permitted and is itself informative: an exception signed
  without a word is one nobody explained."

### RPT-015 · `_counts` renders a detail from the metrics
- **Area:** `report/attest.py::_counts`
- **Type:** functional
- **Priority:** P2
- **Precondition:** records with `distinct_keys` and with `violating_rows`
- **Steps:** build
- **Expected:** "N duplicate(s) in M rows" and "N of M rows"
- **Why:** an exception with no detail is a line an auditor asks about and nobody
  can answer.

### RPT-016 · A seal is an HMAC over the content hash
- **Area:** `report/attestation.py::Attestation.seal`, `verify`
- **Type:** security
- **Priority:** P1
- **Precondition:** a key
- **Steps:** seal, verify with the same key and with another
- **Expected:** true, then false
- **Why:** the seal is the artefact's whole integrity claim.

### RPT-017 · What the seal says is stated plainly
- **Area:** `report/attestation.py`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** none
- **Steps:** read the module docstring and the attestation pack template
- **Expected:** both say the seal proves only that a holder of the key sealed it,
  and that an asymmetric signature would say more
- **Why:** "the distinction is stated here rather than left for a regulator to
  discover" — confirm the *rendered artefact* says it too, not only the source.

### RPT-018 · `describe` qualifies the sentence correctly
- **Area:** `report/attestation.py::Attestation.describe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a clean and a qualified attestation
- **Steps:** render both
- **Expected:** "without exception" and "with exceptions"
- **Why:** it is the sentence a reader takes away, and the word is the auditor's.

### RPT-019 · The attestation version travels with the document
- **Area:** `report/attestation.py::ATTESTATION_VERSION`
- **Type:** contract
- **Priority:** P2
- **Precondition:** an attestation
- **Steps:** read `content()["version"]`
- **Expected:** `"1.0"`, inside the hash
- **Why:** "one from 2026 is still read the way it was written after the format
  has moved on".

### RPT-020 · An RDARR pack leads with the gaps
- **Area:** `report/rdarr.py::Pack.sections`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a coverage with unaddressed and unproven obligations
- **Steps:** read the sections in order
- **Expected:** obligations with no control, then those with no evidence, then
  exceptions, then clean
- **Why:** "The order is the argument. A pack that led with what passed would be
  a marketing document."

### RPT-021 · "We have a control" and "we have evidence" are separate sections
- **Area:** `report/rdarr.py::Pack.sections`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an obligation with a control that never ran
- **Steps:** read
- **Expected:** it appears under "controls that produced no evidence", not under
  "no control"
- **Why:** "the two answers an examiner is separating".

### RPT-022 · A pack with a gap is not defensible
- **Area:** `report/rdarr.py::Pack.is_defensible`
- **Type:** functional
- **Priority:** P1
- **Precondition:** one unaddressed obligation and everything else clean
- **Steps:** read `is_defensible` and `headline`
- **Expected:** false; the headline counts the gaps
- **Why:** "a pack with an obligation nobody has evidence for is not [defensible],
  however clean the rest looks".

### RPT-023 · A pack full of explained exceptions is defensible
- **Area:** `report/rdarr.py::Pack.is_defensible`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** every obligation proven, several with exceptions
- **Steps:** read
- **Expected:** true
- **Why:** "A pack full of exceptions that were found, explained and signed is
  defensible" — the opposite reading would make the pack useless.

### RPT-024 · A pack with no obligations says it establishes nothing
- **Area:** `report/rdarr.py::Pack.headline`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an empty catalogue
- **Steps:** render the headline
- **Expected:** "no obligations are loaded, so this pack establishes nothing"
- **Why:** an empty pack that read as clean is the most dangerous artefact this
  product could produce.

### RPT-025 · `rdarr.build` stores the evidence root, not the tuple
- **Area:** `report/rdarr.py::build`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a tenant with evidence in the period
- **Steps:** build a pack, read `evidence_root`
- **Expected:** a hash string
- **Why:** `period_root` returns `(root, count)` and `build` assigns the whole
  tuple to `evidence_root`, where `attest.build` unpacks it — so the pack's root
  renders as a Python tuple and the count is lost. Confirm against the rendered
  artefact, not the intent.

### RPT-026 · A pack's verdicts are the latest per control in the period
- **Area:** `report/rdarr.py::build`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a control that ran twenty times
- **Steps:** build
- **Expected:** one standing, from the latest record
- **Why:** "an obligation is not more addressed for having been checked hourly".

### RPT-027 · A pack names the controls bound to each obligation
- **Area:** `report/rdarr.py::Pack.bindings`
- **Type:** functional
- **Priority:** P2
- **Precondition:** bindings supplied
- **Steps:** read
- **Expected:** the control identifiers, not a count
- **Why:** "an examiner asking which controls address an obligation wants their
  identifiers".

### RPT-028 · A declaration pack counts what is not covered
- **Area:** `report/render.py::declaration_pack`, `Coverage`
- **Type:** contract
- **Priority:** P1
- **Precondition:** forty datasets included and one hundred excluded
- **Steps:** render
- **Expected:** "40 of 140 covered (29%). 100 excluded: <reason>."
- **Why:** "A pack listing forty datasets is a claim about forty datasets; the
  reader cannot tell whether that is the estate or a fifth of it."

### RPT-029 · Coverage renders even when nothing is excluded
- **Area:** `report/render.py::Coverage.describe`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `excluded=0`
- **Steps:** render
- **Expected:** "All 40 covered."
- **Why:** "Both numbers, always, and the second one rendered whether or not it
  is zero."

### RPT-030 · An exclusion with no reason says so
- **Area:** `report/render.py::Coverage.describe`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `excluded=5`, no reason
- **Steps:** render
- **Expected:** "5 excluded: no reason recorded."
- **Why:** a blank reason rendered as blank looks like a rendering fault; named,
  it is a finding.

### RPT-031 · A declaration pack includes datasets nobody has connected
- **Area:** `report/render.py::declaration_pack`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a mix of bound and unbound datasets
- **Steps:** render, read `unconnected`
- **Expected:** the unbound ones counted and shown
- **Why:** "it is a record of *declarations*, so it includes the datasets nobody
  has connected to. Those are the interesting rows."

### RPT-032 · A declaration pack counts undeclared grains
- **Area:** `report/render.py::declaration_pack`
- **Type:** functional
- **Priority:** P2
- **Precondition:** three datasets without a grain
- **Steps:** render
- **Expected:** `undeclared_grain == 3`, shown on the page
- **Why:** a grain nobody declared is a uniqueness control nobody can generate.

### RPT-033 · A control pack includes the compiled SQL
- **Area:** `report/render.py::control_pack`
- **Type:** contract
- **Priority:** P1
- **Precondition:** controls with compiled SQL
- **Steps:** render
- **Expected:** the SQL appears, escaped
- **Why:** "a reader who cannot see the query is being asked to take the verdict
  on faith, which is the thing Prama exists to stop doing".

### RPT-034 · A control pack lists unsatisfiable controls
- **Area:** `report/render.py::control_pack`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two controls that cannot be compiled for the bound engine
- **Steps:** render
- **Expected:** both listed in their own section
- **Why:** a pack that silently omitted them would claim coverage the estate does
  not have.

### RPT-035 · An attestation pack states whether the record still verifies, first
- **Area:** `report/render.py::attestation_pack`
- **Type:** security
- **Priority:** P1
- **Precondition:** `intact=False`
- **Steps:** render
- **Expected:** the failure appears before the statement
- **Why:** "handing somebody a seal on an envelope nobody checked".

### RPT-036 · Every artefact carries its provenance
- **Area:** `report/render.py::Provenance`
- **Type:** contract
- **Priority:** P1
- **Precondition:** any artefact
- **Steps:** render
- **Expected:** tenant, generated-at instant, generated-by, and the version read
  from `prama.version`
- **Why:** "An artefact that cannot say which build produced it, from which
  tenant, at which instant, is not evidence — it is a screenshot."

### RPT-037 · The provenance stamp is UTC and says so
- **Area:** `report/render.py::Provenance.stamp`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a provenance from `utc_now`
- **Steps:** render
- **Expected:** `YYYY-MM-DD HH:MM:SSZ`
- **Why:** a pack timestamped in the server's local zone with no offset is
  unusable as evidence of when it was produced.

### RPT-038 · A filename sorts chronologically and does not collide
- **Area:** `report/render.py::Artefact.filename`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two packs of the same title one second apart
- **Steps:** read the filenames
- **Expected:** distinct, both starting with the date and time
- **Why:** "two packs for the same estate on the same day are a normal thing to
  produce and silently overwriting the first is not".

### RPT-039 · A title with punctuation produces a clean slug
- **Area:** `report/render.py::Artefact.filename`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** titles containing `/`, `..`, unicode and a run of spaces
- **Steps:** read the filename
- **Expected:** no path separators, no `..`, no double hyphens
- **Why:** the title reaches a filesystem path; a slug containing `/` writes
  outside the target directory.

### RPT-040 · Templates refuse an undefined variable
- **Area:** `report/render.py::_environment`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a template referencing a key the caller did not pass
- **Steps:** render
- **Expected:** a Jinja `UndefinedError` — `StrictUndefined` is configured
- **Why:** a silently blank field on a signed artefact is the failure mode this
  setting exists to prevent.

### RPT-041 · Templates autoescape
- **Area:** `report/render.py::_environment`
- **Type:** security
- **Priority:** P1
- **Precondition:** a dataset named `<script>alert(1)</script>`
- **Steps:** render every artefact
- **Expected:** escaped in all of them
- **Why:** a pack is opened in a browser; a dataset name is user-supplied.

### RPT-042 · The print stylesheet is inlined
- **Area:** `report/render.py::_render`
- **Type:** functional
- **Priority:** P2
- **Precondition:** any artefact
- **Steps:** render and check for external references
- **Expected:** the CSS is in the document; no external URL is fetched
- **Why:** "a pack is read by an auditor six months later with nothing but the
  paper" — and an air-gapped host has no CDN.

### RPT-043 · `write` creates the directory and returns the path
- **Area:** `report/render.py::Artefact.write`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a non-existent directory
- **Steps:** write
- **Expected:** created; the file is UTF-8
- **Why:** the CLI writes packs into a directory an operator names.

### RPT-044 · There is no server-side PDF and the documentation says so
- **Area:** `report/render.py`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** search the CLI, the API and the documentation for a PDF promise
- **Expected:** none claims a PDF file is produced
- **Why:** "there is no server-side PDF *file* until a deployment adds a
  renderer" — a documented PDF endpoint that does not exist is finding-shaped.

### RPT-045 · An empty series renders "not examined", never a flat line
- **Area:** `report/charts.py::sparkline`, `_nothing_observed`
- **Type:** contract
- **Priority:** P1
- **Precondition:** `values=[]`
- **Steps:** render
- **Expected:** the "not examined" text and a description saying this is "the
  absence of observation, not a measurement of zero"
- **Why:** "A zero-height bar and an absent bar look identical and mean opposite
  things."

### RPT-046 · A single observation is not drawn as a trend
- **Area:** `report/charts.py::sparkline`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** one value
- **Steps:** render
- **Expected:** a dot, and a description saying a single point has no trend
- **Why:** "Drawing a line through it invents a direction the data does not
  have."

### RPT-047 · A truncated axis is labelled as truncated
- **Area:** `report/charts.py::Axis.is_truncated`, `sparkline`
- **Type:** contract
- **Priority:** P1
- **Precondition:** values between 0.997 and 1.0
- **Steps:** render
- **Expected:** the description says the axis runs from a non-zero minimum
- **Why:** "The truncation is allowed and it is *labelled*, on the chart, in the
  axis."

### RPT-048 · An axis is zero-based when the data reaches low enough
- **Area:** `report/charts.py::Axis.for_values`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** values from 10 to 100 (variation ≥ 25% of the level)
- **Steps:** build the axis
- **Expected:** minimum 0
- **Why:** "a zero baseline shows the shape perfectly well and there is no reason
  to distort it".

### RPT-049 · The truncation threshold is exact
- **Area:** `report/charts.py::Axis.for_values`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `high - low` exactly `0.25 * low`, and just below
- **Steps:** build
- **Expected:** zero-based, then truncated
- **Why:** the `>=` decides whether a chart exaggerates or flattens, and the
  boundary is where a reviewer will look.

### RPT-050 · A zero or negative value forces a zero-based axis
- **Area:** `report/charts.py::Axis.for_values`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** values including 0 and −5
- **Steps:** build
- **Expected:** minimum 0
- **Why:** the `low <= 0.0` branch; a truncated axis below zero would put the
  baseline in the middle of the chart with no label.

### RPT-051 · A flat series does not divide by zero
- **Area:** `report/charts.py::Axis.span`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** twenty identical values
- **Steps:** render a sparkline
- **Expected:** a line drawn at a defined height, not at the very top or very
  bottom
- **Why:** "drawing a flat series along the top of the chart is as wrong as along
  the bottom".

### RPT-052 · `Axis.position` clamps to [0, 1]
- **Area:** `report/charts.py::Axis.position`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a value outside the axis range
- **Steps:** call
- **Expected:** 0.0 or 1.0
- **Why:** an SVG coordinate outside the viewBox draws outside the chart and over
  the text beside it.

### RPT-053 · An unmeasured bar is not a zero-length bar
- **Area:** `report/charts.py::bars`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a series with no values
- **Steps:** render
- **Expected:** the "not examined" text in Unverified Grey, no filled rectangle
- **Why:** "which is what a bar chart naturally renders it as and which reads as
  'measured, and it was nothing'".

### RPT-054 · A bar longer than the maximum is clamped
- **Area:** `report/charts.py::bars`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an explicit `maximum` below the largest value
- **Steps:** render
- **Expected:** the bar fills the track and does not overflow
- **Why:** the `min(1.0, ...)` guard; an overflowing bar overlaps the value label.

### RPT-055 · An empty bar chart renders the empty state
- **Area:** `report/charts.py::bars`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** no series
- **Steps:** render
- **Expected:** "no observations of …"
- **Why:** the same claim as the sparkline, at a different entry point.

### RPT-056 · A score ring of `None` is not an empty ring
- **Area:** `report/charts.py::score_ring`
- **Type:** contract
- **Priority:** P1
- **Precondition:** `value=None`
- **Steps:** render
- **Expected:** a dashed ring, an em dash, and a description saying this is not a
  score of zero
- **Why:** "an unmeasured score drawn as 0% is a false alarm, and drawn as 100%
  is a false assurance".

### RPT-057 · A score ring clamps out-of-range values
- **Area:** `report/charts.py::score_ring`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `-0.2` and `1.5`
- **Steps:** render
- **Expected:** 0.0% and 100.0%; the dash array never exceeds the circumference
- **Why:** a stroke-dasharray longer than the circle draws a second lap.

### RPT-058 · A score ring at exactly 0.0 and 1.0 renders correctly
- **Area:** `report/charts.py::score_ring`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** both
- **Steps:** render
- **Expected:** "0.0%" with no filled arc, and "100.0%" with a full one — and
  neither is confusable with the `None` state
- **Why:** the three states must be distinguishable to a reader at a glance.

### RPT-059 · A distribution of all-zero buckets is the empty state
- **Area:** `report/charts.py::distribution`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** buckets present, every count zero
- **Steps:** render
- **Expected:** "no observations of …"
- **Why:** the guard is `all(count == 0 ...)`; drawing five zero-height bars would
  say "measured, and every bucket was empty", which is a different claim.

### RPT-060 · Every histogram bar carries its bucket name
- **Area:** `report/charts.py::distribution`
- **Type:** contract
- **Priority:** P1
- **Precondition:** eight buckets
- **Steps:** render
- **Expected:** eight labels
- **Why:** "A histogram whose axis labels were dropped to fit is a picture of
  some numbers."

### RPT-061 · Chart output is byte-stable for the same input
- **Area:** `report/charts.py::_number`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the same series rendered twice, and on two platforms
- **Steps:** compare
- **Expected:** identical bytes
- **Why:** "an SVG whose coordinates depend on the last bits of a float cannot be
  asserted against, and the diff of two identical charts becomes unreadable".

### RPT-062 · `_number` never emits an empty coordinate
- **Area:** `report/charts.py::_number`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** values 0, 0.0, 0.001 and 100.0
- **Steps:** render
- **Expected:** `0`, `0`, `0` and `100` — never `""` or `.`
- **Why:** the `rstrip("0").rstrip(".") or "0"` chain has an empty-string case it
  guards against; an empty coordinate makes the whole SVG invalid.

### RPT-063 · Every label reaching the markup is escaped
- **Area:** `report/charts.py::_escape`
- **Type:** security
- **Priority:** P1
- **Precondition:** a series labelled `<img src=x onerror=alert(1)>` and one
  containing `&`
- **Steps:** render every chart function
- **Expected:** escaped in the title, the desc, the aria-label and the text nodes
- **Why:** "an unescaped `<` is script injection through a chart title", and
  labels come from a warehouse catalogue.

### RPT-064 · Every chart is announced to a screen reader
- **Area:** `report/charts.py::_frame`
- **Type:** contract
- **Priority:** P1
- **Precondition:** each chart function
- **Steps:** render
- **Expected:** `role="img"`, an `aria-label`, a `<title>` and a `<desc>`
- **Why:** "the minimum that makes a chart exist for a screen reader at all".

### RPT-065 · Every chart's description carries the numbers
- **Area:** `report/charts.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** each chart function
- **Steps:** read the `<desc>`
- **Expected:** the actual values, not just a shape
- **Why:** "a described picture is still a picture" — the description is the only
  thing a non-visual reader gets.

### RPT-066 · `table_alternative` renders the same facts
- **Area:** `report/charts.py::table_alternative`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the same data as a chart
- **Steps:** render both
- **Expected:** every value in the chart appears in the table
- **Why:** "Not a fallback for a broken chart — a peer of it."

### RPT-067 · Colour is never the only signal
- **Area:** `report/charts.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a bar chart with six dimension series
- **Steps:** render
- **Expected:** every series carries its name as text
- **Why:** the module's third stated rule, and the reason it holds for the eight
  per cent of men with a colour vision deficiency.

### RPT-068 · Unverified Grey is used for nothing else
- **Area:** `report/palette.py::UNVERIFIED_GREY`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** grep the chart code and the stylesheet for the constant
- **Expected:** only the unverified states
- **Why:** "Nothing else may use it, in any chart, ever … giving that state a
  colour nothing else may take is how the decision survives a designer in a
  hurry."

### RPT-069 · The themed palette carries a literal fallback
- **Area:** `report/palette.py::Palette.dimension`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `SCREEN`
- **Steps:** render
- **Expected:** `var(--dim-accuracy, #00B3A4)` — both parts present
- **Why:** "an SVG pulled out of the page — saved, emailed, embedded — keeps its
  colours".

### RPT-070 · The print palette emits literal hex only
- **Area:** `report/palette.py::PRINT`
- **Type:** contract
- **Priority:** P1
- **Precondition:** `PRINT`
- **Steps:** render every accessor
- **Expected:** no `var(` anywhere
- **Why:** "a `var(--dim-accuracy)` in a PDF renders as nothing at all —
  silently, as a blank chart that looks like a chart with no data".

### RPT-071 · An unknown dimension name falls back to the muted ink
- **Area:** `report/palette.py::Palette.dimension`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `dimension="nonsense"`
- **Steps:** render
- **Expected:** the muted hex, unthemed, never a `var(--dim-nonsense)`
- **Why:** a CSS variable nothing defines renders as nothing.

### RPT-072 · Fill and text colours are separate and meet different thresholds
- **Area:** `report/palette.py::dimension`, `dimension_text`, `contrast.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** each of the eight dimensions on the light surface
- **Steps:** measure the contrast of each fill and each text colour
- **Expected:** fills at or above 3.0:1, texts at or above 4.5:1
- **Why:** "Accuracy Teal on white is 2.63:1: fine as a large area, illegible as
  a word."

### RPT-073 · Derived text colours preserve the hue
- **Area:** `report/contrast.py::accessible_on`
- **Type:** functional
- **Priority:** P2
- **Precondition:** each dimension
- **Steps:** compare the hue of the source and the derived colour
- **Expected:** recognisably the same
- **Why:** "teal still means accuracy after this function has run" — the
  dimension language depends on it.

### RPT-074 · `accessible_on` returns the original when it already passes
- **Area:** `report/contrast.py::accessible_on`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a colour already at 5:1
- **Steps:** call
- **Expected:** the same hex
- **Why:** darkening a colour that already passes moves it away from the brand
  for nothing.

### RPT-075 · `accessible_on` returns black or white when the threshold is unreachable
- **Area:** `report/contrast.py::accessible_on`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a yellow on white at a 7:1 threshold
- **Steps:** call
- **Expected:** `#000000`, not a colour that still fails
- **Why:** "which is a real outcome for a yellow on white and is better than
  silently returning something that fails".

### RPT-076 · `rgb` refuses a colour it cannot parse
- **Area:** `report/contrast.py::rgb`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `"red"`, `"#ff"`, `"rgb(1,2,3)"`
- **Steps:** call
- **Expected:** `ValueError` in each case
- **Why:** "a colour this cannot parse is a colour the check would otherwise
  skip, and a skipped check reports a pass".

### RPT-077 · `rgb` expands the three-digit form
- **Area:** `report/contrast.py::rgb`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `#fff` and `#ffffff`
- **Steps:** call
- **Expected:** identical
- **Why:** the stylesheet uses both forms.

### RPT-078 · `ratio` is symmetric and bounded
- **Area:** `report/contrast.py::ratio`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** black and white
- **Steps:** call in both orders
- **Expected:** 21.0 both ways; a colour against itself is 1.0
- **Why:** "Order does not matter" is a stated property and the arithmetic is the
  place it could quietly stop being true.

### RPT-079 · `report` carries the measured ratio
- **Area:** `report/contrast.py::report`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** a failing pair
- **Steps:** render
- **Expected:** "3.10:1 FAILS (needs 4.5:1)"
- **Why:** "a bare 'fails' sends them guessing".

### RPT-080 · `blend` refuses an alpha outside [0, 1]
- **Area:** `report/contrast.py::blend`
- **Type:** negative
- **Priority:** P3
- **Precondition:** `alpha=1.5`
- **Steps:** call
- **Expected:** `ValueError`
- **Why:** an out-of-range alpha produces a channel outside 0–255 and a hex that
  is not a colour.

### RPT-095 · Every theme's colours are legible on every ground
- **Area:** `report/themes.py::Theme._legible`, `grounds`
- **Type:** contract
- **Priority:** P1
- **Precondition:** all five themes
- **Steps:** for each theme, measure every dimension text colour, the ink, the
  muted and the link against the card, the page and the striped row
- **Expected:** at least 4.5:1 everywhere
- **Why:** "a colour checked against the background the test assumed rather than
  the one it renders on is a colour nobody has checked" — the defect axe found
  three times.

### RPT-081 · Every theme's fills meet the non-text threshold
- **Area:** `report/themes.py::Theme.fills`
- **Type:** contract
- **Priority:** P1
- **Precondition:** all five themes
- **Steps:** measure each fill against each ground
- **Expected:** at least 3.0:1
- **Why:** WCAG 1.4.11 — "the rule most often missed, and it is exactly the rule a
  data quality product cannot afford to miss, because its charts *are* the
  meaning".

### RPT-082 · The accent is held to the non-text threshold only
- **Area:** `report/themes.py::Theme.legible_accent`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** all five themes
- **Steps:** confirm nothing in the stylesheet reads `color: var(--accent)`
- **Expected:** nothing does
- **Why:** the relaxation is justified by that fact alone — "A test asserts it
  stays a mark."

### RPT-083 · The striped-row ground is computed, not declared
- **Area:** `report/themes.py::Theme.raised`, `RAISED_GREY`, `RAISED_ALPHA`
- **Type:** contract
- **Priority:** P1
- **Precondition:** each theme
- **Steps:** compare the computed blend with `--bg-raised` in `src/prama/web/static/css/prama.css`
- **Expected:** identical
- **Why:** "a blend computed from one number here and painted from another there
  is a ground nothing has checked" — and a table header was failing at 4.12:1
  because of it.

### RPT-084 · A dark theme derives from the lifted hue set
- **Area:** `report/themes.py::Theme.source_hues`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** the dark and wallstreet themes
- **Steps:** read
- **Expected:** `DIMENSION_DARK_HEX`
- **Why:** "darkening a mid-tone teal against black would make it *less* legible,
  and the derivation only moves away from the background".

### RPT-085 · A dimension keeps its identity across themes
- **Area:** `report/themes.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** all five themes
- **Steps:** compare the hue family of `accuracy` in each
- **Expected:** recognisably teal everywhere
- **Why:** "the same colour means the same dimension on every chart, chip and
  scorecard, and a reader learns it once".

### RPT-086 · A brand colour is never a dimension colour
- **Area:** `report/themes.py::THEMES`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the crimson and bmo themes
- **Steps:** compare the accent with every dimension colour
- **Expected:** distinct enough not to be confused
- **Why:** Harvard Crimson "sits between the validity red and the uniqueness
  orange, and a brand colour that reads as a dimension would corrupt the language
  on this theme alone".

### RPT-087 · Every theme declares a distinguishing note
- **Area:** `report/themes.py::Theme.note`
- **Type:** documentation
- **Priority:** P3
- **Precondition:** all five
- **Steps:** read
- **Expected:** non-empty and distinct
- **Why:** "A theme nobody can tell apart from the next one is a theme nobody
  chooses deliberately."

### RPT-088 · A rate that is not exactly whole never prints as 100%
- **Area:** `report/rate.py::percent`
- **Type:** contract
- **Priority:** P1
- **Precondition:** 412 failing rows in 1,284,301 — a rate of 0.99967…
- **Steps:** render at the default precision
- **Expected:** precision grows until the number is distinguishable from 100
- **Why:** "the number a business owner reads says the data is perfect, and it is
  not".

### RPT-089 · A rate of exactly 1.0 prints as 100%
- **Area:** `report/rate.py::percent`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `1.0`
- **Steps:** render
- **Expected:** `100%`
- **Why:** the counterfactual — a rule that never printed 100% would be equally
  dishonest in the other direction.

### RPT-090 · A rate past four decimals degrades to `>99.99%`
- **Area:** `report/rate.py::percent`, `MAX_DECIMALS`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a rate of 0.9999999
- **Steps:** render
- **Expected:** `&gt;99.99%`, never `100%`
- **Why:** "past the point where that stops being readable it degrades to
  `>99.99%` rather than to `100%`".

### RPT-091 · A tiny non-zero rate never prints as 0%
- **Area:** `report/rate.py::percent`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `0.0001` and `0.0000001`
- **Steps:** render
- **Expected:** `0.0100%` and `&lt;0.0001%`
- **Why:** "'nothing passed' and 'almost nothing passed' are different facts
  about a remediation that is underway".

### RPT-092 · A rate of exactly 0.0 prints as 0%
- **Area:** `report/rate.py::percent`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `0.0`
- **Steps:** render
- **Expected:** `0%`
- **Why:** the counterfactual at the bottom end.

### RPT-093 · `plain` is the same number without HTML entities
- **Area:** `report/rate.py::plain`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** the degraded cases
- **Steps:** render
- **Expected:** `>99.99%` and `<0.0001%`
- **Why:** the CLI and the alt text must not print `&gt;`.

### RPT-094 · Out-of-range rates are handled
- **Area:** `report/rate.py::percent`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `1.5` and `-0.5`
- **Steps:** render
- **Expected:** `100%` and `0%` — clamped, not a nonsensical percentage
- **Why:** a rate above one arrives from a division whose denominator was wrong,
  and printing 150% on a scorecard is a defect report from a customer.

## The benchmark corpus and its baselines

### BCH-001 · `build` has no default seed
- **Area:** `bench/corpus.py::build`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** call `build()` with no seed
- **Expected:** `TypeError`
- **Why:** "a default seed is a seed nobody records", and a result nobody can
  reproduce cannot distinguish a regression from a reroll.

### BCH-002 · The same seed produces the same corpus, byte for byte
- **Area:** `bench/corpus.py::build`
- **Type:** contract
- **Priority:** P1
- **Precondition:** seed 42
- **Steps:** build twice, compare every row and every label
- **Expected:** identical
- **Why:** "The seed is part of the corpus."

### BCH-003 · Different seeds produce different corpora
- **Area:** `bench/corpus.py::build`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** seeds 42 and 43
- **Steps:** compare
- **Expected:** different
- **Why:** the counterfactual — a seed that was ignored would make BCH-002 pass
  trivially.

### BCH-004 · Every defect class is present and correctly classified
- **Area:** `bench/corpus.py::CLASSES`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** enumerate the 27 classes
- **Expected:** five structural, seven content, five statistical, four
  relational, three temporal, four semantic — every one naming a real column of
  `_base_row` and a difficulty
- **Why:** "the taxonomy, the injectors and the labelling discipline … is the
  part that has to be right before scale is worth buying".

### BCH-005 · Every family is represented
- **Area:** `bench/corpus.py::Family`, `classes_of`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** `classes_of(family)` for all six
- **Expected:** non-empty for each
- **Why:** "An overall F1 hides the semantic family, which is where the argument
  lives."

### BCH-006 · Every difficulty tier is represented
- **Area:** `bench/corpus.py::Difficulty`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** group the classes by difficulty
- **Expected:** each of obvious, ordinary, subtle and adversarial has at least
  one class
- **Why:** "A tool that finds every *obvious* defect and no *subtle* one has a
  different problem from a tool that finds a few of each."

### BCH-007 · Each class gets its own window
- **Area:** `bench/corpus.py::Scenario`, `_window`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a built corpus
- **Steps:** collect the windows
- **Expected:** one distinct ISO date per class, sequential from 2026-01-01
- **Why:** "six classes that all damage `amount` in one window share a locus, so
  a single alert on `amount` would be credited with finding all six".

### BCH-008 · Only rows the injector actually changed are labelled
- **Area:** `bench/corpus.py::build`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the sign-flip class over rows whose amounts are already
  positive and negative
- **Steps:** build, compare `damaged_rows` with a diff of clean against damaged
- **Expected:** exactly the rows that differ
- **Why:** "crediting a detector for finding it would be crediting it for finding
  a defect that is not there. This is the difference between a corpus that
  measures detection and one that flatters it."

### BCH-009 · A class that plants nothing is recorded as barren
- **Area:** `bench/corpus.py::build`, `Corpus.barren`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a class whose injector cannot change any sampled row
- **Steps:** build
- **Expected:** it appears in `barren` with a reason; no `Defect` is labelled
- **Why:** "a class that quietly plants nothing turns into recall a detector is
  credited with never having to earn".

### BCH-010 · Every injector returns True only when it changed something
- **Area:** `bench/corpus.py` — the 27 injectors
- **Type:** contract
- **Priority:** P1
- **Precondition:** rows crafted to make each a no-op
- **Steps:** call each injector on such a row
- **Expected:** `False`, and the row unchanged
- **Why:** the named cases — `_sign_flip` on a negative amount, `_truncate` on a
  short string, `_retype` on a value that already reads as text — are the ones
  most likely to lie.

### BCH-011 · `_null_out` on an already-null column returns False
- **Area:** `bench/corpus.py::_null_out`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a row whose `amount` is already `None`
- **Steps:** inject
- **Expected:** `False`
- **Why:** nulling a null is not a defect.

### BCH-012 · `_drop_column` and `_rename_column` change the row's key set
- **Area:** `bench/corpus.py`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a clean row
- **Steps:** inject each
- **Expected:** the column disappears; the renamed key appears and the old one
  does not
- **Why:** `_detect_schema_only` compares key sets, so the injector and the
  baseline have to agree about what "a column stopped arriving" means.

### BCH-013 · `_duplicate_key` produces a grain violation
- **Area:** `bench/corpus.py::_duplicate_key`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a scenario
- **Steps:** build with only that class
- **Expected:** at least two rows share an `account_id`
- **Why:** the label claims "two rows at a grain declared unique"; if the
  injector writes a constant the duplication is real, and if it does not there is
  no defect to find.

### BCH-014 · `_legitimate_change_with_defect` is adversarial by construction
- **Area:** `bench/corpus.py::_legitimate_change_with_defect`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the class
- **Steps:** inspect the damaged rows
- **Expected:** a legitimate-looking change and a defect together
- **Why:** "Tests false-positive discipline rather than sensitivity: the tool
  that alerts on both is worse than the tool that alerts on neither."

### BCH-015 · `rate` outside (0, 1] is refused
- **Area:** `bench/corpus.py::build`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `rate=0`, `rate=1.5`, `rate=-0.1`
- **Steps:** build
- **Expected:** `ValueError` naming the value
- **Why:** a rate of zero produces a corpus with nothing planted, which scores
  every detector perfectly.

### BCH-016 · `rows` below one is refused
- **Area:** `bench/corpus.py::build`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `rows=0`
- **Steps:** build
- **Expected:** `ValueError`
- **Why:** `rng.sample(range(0), 0)` would otherwise succeed and produce empty
  scenarios that score as barren rather than as an error.

### BCH-017 · `rate` is an attempt rate, not a hit rate
- **Area:** `bench/corpus.py::build`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** `rate=0.05` over 200 rows with a class that is often a no-op
- **Steps:** build, count `damaged_rows`
- **Expected:** fewer than ten, and the label's note reports the real count
- **Why:** "an injector that finds nothing to change on a row plants nothing
  there, and the labels follow what happened rather than what was intended".

### BCH-018 · `per_class` is at least one row
- **Area:** `bench/corpus.py::build`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `rows=10`, `rate=0.01`
- **Steps:** build
- **Expected:** one attempt per class, not zero
- **Why:** `max(1, ...)` is the guard; without it a small corpus plants nothing
  and every class is barren.

### BCH-019 · `control_total` matches `amount` in the clean rows
- **Area:** `bench/corpus.py::build`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a built corpus
- **Steps:** compare the two columns in `scenario.clean`
- **Expected:** equal
- **Why:** the aggregate-mismatch class depends on them agreeing before the
  injection, or the "defect" is present in the clean data too.

### BCH-020 · `Corpus.rows` and `clean` cover every scenario
- **Area:** `bench/corpus.py::Corpus`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a corpus of 27 scenarios at 200 rows
- **Steps:** count
- **Expected:** 5,400 each
- **Why:** a baseline that reads `corpus.rows` must see everything, or its recall
  is measured against a corpus it never saw.

### BCH-021 · `to_dict` reports the barren classes
- **Area:** `bench/corpus.py::Corpus.to_dict`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a corpus with one barren class
- **Steps:** serialise
- **Expected:** the class and its reason appear
- **Why:** "Never silent" — the absence has to be visible in the output somebody
  reads.

### BCH-022 · Detection requires dataset, column and window to all match
- **Area:** `bench/scoring.py::score`
- **Type:** contract
- **Priority:** P1
- **Precondition:** one planted defect and four alerts — exact, wrong dataset,
  wrong column, wrong window
- **Steps:** score
- **Expected:** one found; the rest uncredited
- **Why:** "a generic 'something is wrong with this table' scores zero", which is
  the rule most data quality benchmarks quietly break.

### BCH-023 · A near miss is reported, not credited
- **Area:** `bench/scoring.py::score`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an alert with the right dataset and column and the wrong
  window
- **Steps:** score
- **Expected:** it appears in `near_misses`, `found` is zero
- **Why:** "reported, so the score is arguable rather than merely low".

### BCH-024 · One alert credits one defect
- **Area:** `bench/scoring.py::score`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** ten identical alerts at one locus with one defect there
- **Steps:** score
- **Expected:** one found; nine uncredited and counted as false alarms
- **Why:** "Crediting a repeated alert again would let a tool improve its recall
  by shouting."

### BCH-025 · Two defects at one locus are both creditable
- **Area:** `bench/scoring.py::score`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two defects sharing a locus and two alerts there
- **Steps:** score
- **Expected:** both found
- **Why:** `planted.index(defect)` finds the *first* equal defect, so two
  identical `Defect` values at one locus resolve to the same index and the second
  can never be credited — while the corpus's one-window-per-class rule is what
  currently makes that unreachable.

### BCH-026 · A family with nothing planted scores nothing, not one
- **Area:** `bench/scoring.py::FamilyScore.recall`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a family with no planted defects
- **Steps:** score and read
- **Expected:** `recall is None`, and `describe` says nothing was planted
- **Why:** "a benchmark that reports 1.0 for a family it never tested is a
  benchmark that rewards not being tested".

### BCH-027 · Family precision is `None`, always, and the reason is printed
- **Area:** `bench/scoring.py::FamilyScore.precision`
- **Type:** contract
- **Priority:** P1
- **Precondition:** any scored run
- **Steps:** read `precision` and `describe`
- **Expected:** `None`, and the description says precision is an aggregate figure
- **Why:** "A false alarm corresponds to *no planted defect*, so it belongs to no
  family."

### BCH-028 · Family F1 is therefore always None
- **Area:** `bench/scoring.py::FamilyScore.f1`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a family with perfect recall
- **Steps:** read `f1`
- **Expected:** `None`
- **Why:** it is a direct consequence of BCH-027; a field that can never hold a
  value is either dead or a promise the report should stop making.

### BCH-029 · The run's false-alarm total is carried on every family
- **Area:** `bench/scoring.py::score`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** three families and five uncredited alerts
- **Steps:** read each family's `false_alarms`
- **Expected:** five on each, and `Score.false_alarms` is five, not fifteen
- **Why:** the aggregate reads it from `families[0]`; summing it would triple the
  false-alarm count.

### BCH-030 · Aggregate precision uses a real denominator
- **Area:** `bench/scoring.py::Score.precision`
- **Type:** contract
- **Priority:** P1
- **Precondition:** eight found, two false alarms
- **Steps:** read
- **Expected:** 0.8
- **Why:** precision is computable at the aggregate "where the denominator is
  real".

### BCH-031 · Precision and recall are `None` when nothing was predicted or planted
- **Area:** `bench/scoring.py::Score`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** the `detect-nothing` baseline
- **Steps:** score
- **Expected:** `precision is None`, `recall` a real number, `f1 is None`
- **Why:** "Its precision is undefined rather than zero, which is the correct
  answer to 'how many of your alerts were right' when there were none."

### BCH-032 · The weakest family is named before the aggregate
- **Area:** `bench/scoring.py::Score.describe`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** a run with one weak family
- **Steps:** render
- **Expected:** the weakest family leads the sentence
- **Why:** "an average hides it by construction … the thing it is bad at is what
  a buyer will hit in week two".

### BCH-033 · `by_difficulty` counts found and planted per tier
- **Area:** `bench/scoring.py::score`
- **Type:** functional
- **Priority:** P2
- **Precondition:** defects across all four tiers
- **Steps:** read
- **Expected:** `(found, planted)` per tier, summing to the totals
- **Why:** the tiers are the argument, and a total that does not reconcile is a
  report nobody can defend.

### BCH-034 · `Defect.difficulty`'s documented vocabulary matches the corpus
- **Area:** `bench/scoring.py::Defect`, `bench/corpus.py::Difficulty`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** compare the docstring's "`easy` · `moderate` · `hard`" with the four
  values the corpus actually plants
- **Expected:** they agree
- **Why:** the corpus plants `obvious`, `ordinary`, `subtle` and `adversarial`,
  and the default value is `moderate`, which nothing produces — so a report keyed
  on the documented vocabulary finds nothing.

### BCH-035 · `detect-nothing` is the floor
- **Area:** `bench/baselines.py::_detect_nothing`
- **Type:** contract
- **Priority:** P1
- **Precondition:** any corpus
- **Steps:** run
- **Expected:** zero found, zero false alarms, recall 0.0, precision `None`
- **Why:** "Any claim that does not beat it is not a claim."

### BCH-036 · `alert-on-everything` reaches perfect recall at terrible precision
- **Area:** `bench/baselines.py::_detect_everything`
- **Type:** contract
- **Priority:** P1
- **Precondition:** any corpus
- **Steps:** run
- **Expected:** recall 1.0; precision low
- **Why:** "a recall figure cannot be read without it: the interesting question is
  always what precision was paid for that recall".

### BCH-037 · `alert-on-everything` covers every column of every window
- **Area:** `bench/baselines.py::_detect_everything`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a corpus whose classes drop and rename columns
- **Steps:** run
- **Expected:** the alert set includes the dropped and renamed names, because it
  unions the clean and damaged key sets
- **Why:** a perfect-recall bound that missed a defect would not be a bound.

### BCH-038 · `schema-only` finds structural defects and nothing else
- **Area:** `bench/baselines.py::_detect_schema_only`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the full corpus
- **Steps:** run, read `blind_families`
- **Expected:** it finds structural defects; it is blind to semantic and
  statistical ones
- **Why:** "the honest floor for point-and-shoot tooling".

### BCH-039 · `schema-only` catches a column dropped from only some rows
- **Area:** `bench/baselines.py::_detect_schema_only`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a partial column drop
- **Steps:** run
- **Expected:** an alert — "the column is missing from some rows"
- **Why:** "comparing key sets alone reports nothing"; the second pass is what
  makes the baseline honest rather than accidentally weak.

### BCH-040 · `patterns-only` is blind to the semantic family
- **Area:** `bench/baselines.py::_detect_patterns_only`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the full corpus
- **Steps:** run, read `blind_families`
- **Expected:** `semantic` appears
- **Why:** "this is what a generated rule set gets you without a semantic layer.
  Whatever it cannot see is the part the rest of the system has to justify" —
  this is the single most important ablation in the product's argument.

### BCH-041 · `statistics-only` is blind to anything only wrong against a rule
- **Area:** `bench/baselines.py::_detect_statistics_only`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the full corpus
- **Steps:** run, read `blind_families`
- **Expected:** it finds distribution shifts and new categories; it misses
  `plausible-but-wrong` and `silent-rule-violation`
- **Why:** "Finds shifts and outliers; blind to anything that is only wrong
  relative to a stated business rule."

### BCH-042 · Every baseline is deterministic
- **Area:** `bench/baselines.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** one corpus
- **Steps:** run each twice
- **Expected:** identical scores
- **Why:** "Every detector here is deterministic and inspectable."

### BCH-043 · `blind_families` reports only families the corpus actually planted
- **Area:** `bench/baselines.py::Comparison.blind_families`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a corpus built from one family
- **Steps:** compare
- **Expected:** the other five are not reported as blind spots
- **Why:** a detector is not blind to a family nobody tested it on, and reporting
  it as such is the mirror image of BCH-026.

### BCH-044 · `NOT_RUN` is emitted with every comparison
- **Area:** `bench/baselines.py::NOT_RUN`, `Comparison.to_dict`
- **Type:** contract
- **Priority:** P1
- **Precondition:** any comparison
- **Steps:** serialise
- **Expected:** all fifteen named tools with their reasons
- **Why:** "a comparison table with four rows reads as four contenders, and a
  reader has no way to know that eleven others were never attempted".

### BCH-045 · No external tool is run
- **Area:** `bench/baselines.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** confirm no baseline shells out or imports a competitor
- **Expected:** none does
- **Why:** "a comparison configured by the party that benefits from the result is
  not evidence" — the honesty claim has to be structurally true.

### BCH-046 · `baseline` on an unknown name lists the real ones
- **Area:** `bench/baselines.py::baseline`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `baseline("nope")`
- **Steps:** call
- **Expected:** `ValidationError` whose remedy names all five
- **Why:** the same "Available:" discipline as the registry.

### BCH-047 · Every baseline declares what it stands for
- **Area:** `bench/baselines.py::Baseline.describes`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** all five
- **Steps:** read
- **Expected:** non-empty, and each says whether it is a bound or an ablation
- **Why:** "A detector, and an honest statement of what it stands for."

### BCH-048 · A blinded alert does not reveal its system
- **Area:** `bench/shadow.py::Blinding.for_adjudication`
- **Type:** security
- **Priority:** P1
- **Precondition:** alerts from two systems
- **Steps:** read what a steward sees
- **Expected:** no field carries the system name
- **Why:** "A harness that handed a steward a record carrying the system name —
  even in a field nobody displays — has unblinded the study."

### BCH-049 · Adjudication order does not reveal arrival order
- **Area:** `bench/shadow.py::Blinding.for_adjudication`
- **Type:** security
- **Priority:** P1
- **Precondition:** ten alerts from one system registered first
- **Steps:** read the listing
- **Expected:** sorted by blind id, which is a content hash, not by registration
- **Why:** "Sorting by arrival groups a system's alerts together and a steward
  notices the pattern within an afternoon."

### BCH-050 · The blind id is a content hash, not a sequence
- **Area:** `bench/shadow.py::ShadowAlert.blind_id`
- **Type:** security
- **Priority:** P1
- **Precondition:** two alerts
- **Steps:** read the ids
- **Expected:** 16 hex characters each, derived from the content
- **Why:** "a sequence betrays which system was registered first, and a steward
  who notices that has been unblinded by the harness itself".

### BCH-051 · Two systems raising an identical alert do not collide
- **Area:** `bench/shadow.py::Blinding.register`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** both systems raising the same dataset, column, time, detail
  and reference
- **Steps:** register both, then `len(blinding)`
- **Expected:** two alerts
- **Why:** the blind id excludes the system, and `register` stores into a dict
  keyed on it — so the second silently replaces the first and one system's alert
  disappears from its own precision. Two systems agreeing is the *normal* case in
  a shadow run.

### BCH-052 · An unjudged alert is not a false positive
- **Area:** `bench/shadow.py::SystemResult.precision`
- **Type:** contract
- **Priority:** P1
- **Precondition:** 100 alerts, 20 judged, 18 confirmed
- **Steps:** read `precision` and `examined_share`
- **Expected:** 0.9 and 0.2
- **Why:** "the obvious arithmetic — everything not confirmed is wrong —
  punishes a system for raising more than the stewards had time to look at, which
  is the system raising them fastest".

### BCH-053 · `examined_share` is reported beside precision always
- **Area:** `bench/shadow.py::SystemResult.describe`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** as above
- **Steps:** render
- **Expected:** "precision 90% over the 20% of 100 alert(s) that were judged"
- **Why:** "A precision of 0.95 over four per cent" is a number that means
  nothing without the second figure.

### BCH-054 · An `unclear` verdict is neither confirmed nor rejected
- **Area:** `bench/shadow.py::evaluate`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** judgements of `real`, `false` and `unclear`
- **Steps:** evaluate
- **Expected:** the unclear one is counted separately and is excluded from
  `adjudicated`
- **Why:** a third verdict folded into either direction is a thumb on the scale.

### BCH-055 · Only a rejected alert wastes time
- **Area:** `bench/shadow.py::evaluate`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a confirmed alert costing 30 minutes and a rejected one
  costing 30
- **Steps:** evaluate
- **Expected:** `minutes_spent` 60, `wasted_minutes` 30
- **Why:** "An alert that found something took time and bought something for it."

### BCH-056 · Alerts outside the window are dropped from both sides and counted
- **Area:** `bench/shadow.py::evaluate`
- **Type:** contract
- **Priority:** P1
- **Precondition:** one system starting three days late
- **Steps:** evaluate
- **Expected:** the early alerts are dropped, counted per system, and named in
  `describe`
- **Why:** "a tool that started three days late has three days of free silence".

### BCH-057 · The window comparison is on ISO text
- **Area:** `bench/shadow.py::evaluate`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a window of `2026-01-01` to `2026-01-31` and an alert at
  `2026-01-31T23:59:00Z`
- **Steps:** evaluate
- **Expected:** a defined answer — as a string comparison,
  `"2026-01-31T23:59:00Z" <= "2026-01-31"` is false, so the alert is dropped
- **Why:** a date-only window boundary silently excludes the last day, which is
  exactly the kind of arithmetic a shadow run's conclusions rest on.

### BCH-058 · Burden is reported as well as precision
- **Area:** `bench/shadow.py::SystemResult.alerts_per_steward_week`,
  `wasted_hours_per_week`
- **Type:** contract
- **Priority:** P1
- **Precondition:** `steward_weeks=12`
- **Steps:** read both
- **Expected:** real numbers, printed in `describe`
- **Why:** "a system can win on precision and still be unusable because it raises
  forty times as many".

### BCH-059 · Burden is `None` when no steward-weeks were recorded
- **Area:** `bench/shadow.py::SystemResult`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `steward_weeks=0`
- **Steps:** read
- **Expected:** `None`, and `describe` omits the clauses rather than printing a
  division
- **Why:** the default is zero, so this is the path every first run takes.

### BCH-060 · A system that raised nothing is reported, not omitted
- **Area:** `bench/shadow.py::evaluate`, `SystemResult.describe`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a system all of whose alerts fell outside the window
- **Steps:** evaluate
- **Expected:** a result row saying "raised nothing in this window"
- **Why:** a missing row reads as a system that was not evaluated, which is a
  much weaker claim than one that found nothing.

### BCH-061 · A judgement for an unknown blind id is ignored safely
- **Area:** `bench/shadow.py::evaluate`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a judgement whose blind id matches nothing
- **Steps:** evaluate
- **Expected:** no crash; ideally it is counted somewhere visible
- **Why:** a judgement that silently evaporates is adjudication effort lost with
  no record of the loss.

## Deployment, the gate, and telemetry

### OPS-001 · The Helm chart refuses to render without a session secret
- **Area:** `deploy/helm/prama/templates/_helpers.tpl::prama.validate`
- **Type:** security
- **Priority:** P1
- **Precondition:** neither `existingSecret` nor `createSecretFrom`
- **Steps:** `helm template`
- **Expected:** a failure whose message explains that a default "means every
  installation shares a key that is public in this chart"
- **Why:** "this fails at `helm install` rather than quietly at the first
  sign-in".

### OPS-002 · The chart refuses SQLite with more than one replica
- **Area:** `deploy/helm/prama/templates/_helpers.tpl`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `database.dialect=sqlite`, `replicaCount=2`
- **Steps:** `helm template`
- **Expected:** refused — "sqlite with replicaCount > 1 is corruption, not high
  availability"
- **Why:** two pods writing one file interleave, and the symptom is a corrupt
  database rather than an error.

### OPS-003 · SQLite with one replica is allowed
- **Area:** `deploy/helm/prama/templates/_helpers.tpl`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `dialect=sqlite`, `replicaCount=1`, a secret supplied
- **Steps:** `helm template`
- **Expected:** renders
- **Why:** the counterfactual; a guard that refused every SQLite deployment would
  remove the single-node option the product advertises.

### OPS-004 · PostgreSQL without a host is refused
- **Area:** `deploy/helm/prama/templates/_helpers.tpl`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `dialect=postgres`, `postgres.host=""`
- **Steps:** `helm template`
- **Expected:** refused by name
- **Why:** the default `host` in the chart is empty, so this is the first thing a
  new operator hits.

### OPS-005 · There is no default secret anywhere in the chart
- **Area:** `deploy/helm/prama/values.yaml`, `templates/secret.yaml`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** grep the chart for any secret-shaped literal
- **Expected:** none; the `Secret` template renders only when
  `createSecretFrom` is set deliberately
- **Why:** CLAUDE.md rule 5, applied to the deployment artefacts.

### OPS-006 · `existingSecret` takes precedence over `createSecretFrom`
- **Area:** `deploy/helm/prama/templates/secret.yaml`, `deployment.yaml`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** both set
- **Steps:** `helm template`
- **Expected:** no `Secret` object is created; the deployment references the
  existing one
- **Why:** the guard is `and .Values.createSecretFrom (not .Values.existingSecret)`
  — confirm the deployment and the secret agree about which wins.

### OPS-007 · Every configuration value reaches the container as `PRAMA_` env
- **Area:** `deploy/helm/prama/templates/deployment.yaml`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a full values file
- **Steps:** render, then check each variable against `EnvironmentSource`'s
  mapping
- **Expected:** each maps to the key it names — `PRAMA_DATABASE__POSTGRES__HOST`
  to `database.postgres.host`, and so on
- **Why:** a variable whose name does not round-trip through the double-underscore
  rule is a setting that is silently ignored in production.

### OPS-008 · `tenancy.defaultTenant` is omitted when empty
- **Area:** `deploy/helm/prama/templates/deployment.yaml`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** empty
- **Steps:** render
- **Expected:** the variable is absent, not set to `""`
- **Why:** either works, but an explicit empty string is a value the provenance
  attributes to the environment, which misleads whoever runs `prama config show`.

### OPS-009 · Liveness and readiness are the same endpoint, deliberately
- **Area:** `deploy/helm/prama/templates/deployment.yaml`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** read both probes
- **Expected:** both `/api/v1/health`, with different delays
- **Why:** "Prama has no state that makes it live-but-not-ready … Two probes with
  different meanings invites one of them to be wrong."

### OPS-010 · The health endpoint touches the database
- **Area:** `db/__init__.py::Database.health`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the database stopped or unreachable
- **Steps:** call the endpoint
- **Expected:** failure — the probe executes `SELECT 1`
- **Why:** "A liveness probe that actually touches the database"; a probe that
  only proves the process is running keeps a broken pod in the load balancer.

### OPS-011 · A failing readiness probe removes the pod, and liveness does not flap
- **Area:** `deploy/helm/prama/templates/deployment.yaml`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a database outage of 30 seconds
- **Steps:** observe the pod
- **Expected:** it goes unready and is not restarted, or the restart behaviour is
  a deliberate choice
- **Why:** with one endpoint behind both probes, a database blip restarts every
  pod at once — which is the failure mode the shared endpoint trades for
  simplicity.

### OPS-012 · The container runs as a non-root user
- **Area:** `deploy/Dockerfile`, `values.yaml::podSecurityContext`
- **Type:** security
- **Priority:** P1
- **Precondition:** the built image
- **Steps:** `docker run ... id`
- **Expected:** uid 10001, matching the chart's `runAsUser`
- **Why:** "A control plane that reads a bank's data as root fails the first
  container review", and a mismatch between the image's user and the chart's
  makes `/data` unwritable.

### OPS-013 · The root filesystem is read-only and `/tmp` is mounted
- **Area:** `deploy/helm/prama/templates/deployment.yaml`
- **Type:** security
- **Priority:** P1
- **Precondition:** a rendered deployment
- **Steps:** confirm `readOnlyRootFilesystem` and the `tmp` volume
- **Expected:** both present
- **Why:** "A chart that turned the flag off to avoid this trades a real security
  property for one line of YAML."

### OPS-014 · With a read-only root, every write path has a volume
- **Area:** `deploy/helm/prama/templates/deployment.yaml`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** the rendered deployment, `dialect: sqlite`
- **Steps:** start and write
- **Expected:** either a data volume is mounted or SQLite is refused in this
  configuration
- **Why:** only `/tmp` is mounted, and `database.sqlite.path` defaults to
  `data/prama.db` under the read-only working directory.

### OPS-015 · Capabilities are dropped and privilege escalation is off
- **Area:** `deploy/helm/prama/values.yaml::securityContext`
- **Type:** security
- **Priority:** P1
- **Precondition:** a rendered deployment
- **Steps:** read the container security context
- **Expected:** `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`,
  `seccompProfile: RuntimeDefault`
- **Why:** "set here rather than left to the cluster's admission policy — a chart
  that relies on one is a chart that runs privileged on a cluster without one".

### OPS-016 · The image ships the schema files
- **Area:** `deploy/Dockerfile`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the built image
- **Steps:** `ls /opt/prama/schema`
- **Expected:** both files, and `PRAMA_DATABASE__SCHEMA_DIR` points at them
- **Why:** "an image whose schema came from somewhere else is an image whose
  database nobody can verify".

### OPS-017 · The image's interpreter matches `.python-version`
- **Area:** `deploy/Dockerfile`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** compare `python:3.13-slim` with `.python-version`
- **Expected:** the same minor version
- **Why:** "an image cannot be built on a Python the test suite has never run
  on" — and the pin is a decision recorded in the repository.

### OPS-018 · The runtime image carries no build tooling
- **Area:** `deploy/Dockerfile`
- **Type:** security
- **Priority:** P2
- **Precondition:** the built image
- **Steps:** look for a compiler and for pip's build dependencies
- **Expected:** none — the venv is copied from the build stage
- **Why:** "a compiler in a production image is a finding".

### OPS-019 · The image refuses to start without a secret
- **Area:** `deploy/Dockerfile`
- **Type:** security
- **Priority:** P1
- **Precondition:** no `PRAMA_SECURITY__SESSION_SECRET`
- **Steps:** `docker run`
- **Expected:** a refusal naming the variable
- **Why:** "an image that generated its own would mean every deployment that
  never read the documentation runs on a key baked into a public layer".

### OPS-020 · The `HEALTHCHECK` matches the chart's probe path
- **Area:** `deploy/Dockerfile`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** compare the healthcheck URL with the probe path
- **Expected:** both `/api/v1/health` on 8080
- **Why:** two definitions of "healthy" is one that will drift.

### OPS-021 · `/data` is owned before the volume is declared
- **Area:** `deploy/Dockerfile`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a fresh named volume
- **Steps:** run and write
- **Expected:** writable as uid 10001
- **Why:** "so a fresh volume inherits the right ownership rather than root's" —
  the ordering of `chown` and `VOLUME` is the whole mechanism.

### OPS-022 · The chart's `appVersion` matches `VERSION`
- **Area:** `deploy/helm/prama/Chart.yaml`, `src/prama/version.py`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** compare `appVersion`, `image.tag` and `VERSION`
- **Expected:** all three agree
- **Why:** CLAUDE.md: `VERSION` "is the only authority; every other version
  string is a copy that can rot".

### OPS-023 · The chart states that an upgrade requires `prama db verify`
- **Area:** `deploy/helm/prama/Chart.yaml`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** none
- **Steps:** read the annotation, then follow it literally
- **Expected:** `prama db verify` exists and exits non-zero on blocking drift
- **Why:** "A chart that upgraded silently would leave a drifted schema nobody
  was told about" — and the remedy must be a command that exists.

### OPS-024 · An upgrade against a drifted database fails loudly
- **Area:** `db/__init__.py::Database.start`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a database built for an older schema version
- **Steps:** start a newer build
- **Expected:** `SchemaDriftError` at start-up, before serving
- **Why:** the whole no-migrations design; this is the case it exists for.

### OPS-025 · A backup taken with the server running restores cleanly
- **Area:** `deploy/README.md`, `db/dialects.py::SqliteDialect` (WAL)
- **Type:** functional
- **Priority:** P1
- **Precondition:** SQLite in WAL mode, writes in progress
- **Steps:** follow the documented backup procedure, restore into a new
  directory, `prama db verify`
- **Expected:** verifies clean; the evidence chain verifies
- **Why:** a `cp` of a WAL-mode database without the `-wal` and `-shm` files is a
  backup that restores to yesterday.

### OPS-026 · A restored evidence chain still verifies
- **Area:** `db/dao/evidence.py::verify`
- **Type:** security
- **Priority:** P1
- **Precondition:** a restored backup
- **Steps:** verify the chain
- **Expected:** intact
- **Why:** a backup that silently truncates the ledger destroys the one artefact
  the product exists to produce.

### OPS-027 · `scripts/gate.sh` respects every step's exit status
- **Area:** `scripts/gate.sh`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a deliberately failing pytest collection
- **Steps:** run the gate
- **Expected:** non-zero exit
- **Why:** "piping pytest into `tail` returns tail's status, so a collection
  error sails through an `&&` chain and a commit lands on a red suite. That
  happened twice." `set -o pipefail` is the fix, and this is its counterfactual.

### OPS-028 · The gate fails on a lint error, a type error and an over-long file
- **Area:** `scripts/gate.sh`
- **Type:** negative
- **Priority:** P1
- **Precondition:** each fault introduced in a copy of the tree
- **Steps:** run the gate
- **Expected:** non-zero in each case, naming the fault
- **Why:** four separate gates that have never been observed to fail are four
  gates nobody knows work.

### OPS-029 · `mypy src | tail -1` does not mask a failure
- **Area:** `scripts/gate.sh`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a type error in `src/`
- **Steps:** run the gate
- **Expected:** non-zero
- **Why:** it is the same pipe-to-`tail` shape the script was written to fix;
  `pipefail` covers it, and this is the case that proves it.

### OPS-030 · `check_file_length.py` enforces 1500 lines of code
- **Area:** `scripts/check_file_length.py`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a file with 1,500 and one with 1,501 significant lines
- **Steps:** run
- **Expected:** pass, then fail naming the file and the count
- **Why:** CLAUDE.md rule 4; the boundary is exact and the rule says to split
  rather than raise the limit.

### OPS-031 · Comments, docstrings and blanks do not count
- **Area:** `scripts/check_file_length.py::LengthChecker`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a file of 3,000 lines, 1,400 of them code
- **Steps:** run
- **Expected:** passes
- **Why:** "documenting a module is never penalised" — several files in this
  codebase are more than half prose by design.

### OPS-032 · The UI tree and vendored directories are exempt
- **Area:** `scripts/check_file_length.py::EXEMPT_PREFIXES`, `EXEMPT_PARTS`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a long file under `.venv`, `node_modules` and `prama-web/`
- **Steps:** run
- **Expected:** all skipped
- **Why:** a checker that failed on site-packages would be turned off within a
  day.

### OPS-033 · The checker covers `.sql` and `.sh` as well as `.py`
- **Area:** `scripts/check_file_length.py::CHECKED_SUFFIXES`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** the schema files, which are over a thousand lines
- **Steps:** run
- **Expected:** they are checked, and they pass — comments do not count
- **Why:** the schema is more than half commentary; if SQL comments counted, the
  authoritative files would already be failing the rule.

### OPS-034 · The CI gate calls `scripts/gate.sh` rather than restating it
- **Area:** `.github/workflows/gate.yml`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** read the workflow
- **Expected:** the gate job runs the script; no step duplicates a check
- **Why:** "A second list of checks is a second thing to keep in step, and it
  drifts in the flattering direction."

### OPS-035 · CI builds the pinned interpreter, not the runner's
- **Area:** `.github/workflows/gate.yml`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** read the setup steps
- **Expected:** `uv python install "$(cat .python-version)"` in every job
- **Why:** "an interpreter the package manager owns is one the package manager
  can delete, and it did".

### OPS-036 · The conformance job runs against a real PostgreSQL
- **Area:** `.github/workflows/gate.yml`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** read the job and confirm `PRAMA_TEST_POSTGRES_DSN` is set
- **Expected:** the service is present and the DSN is exported
- **Why:** finding T7 — "a run that silently drops to DuckDB and SQLite proves
  less than it looks".

### OPS-037 · The conformance job fails when PostgreSQL is absent
- **Area:** `.github/workflows/gate.yml`, `tests/db`
- **Type:** negative
- **Priority:** P1
- **Precondition:** the DSN unset
- **Steps:** run the conformance suite
- **Expected:** the PostgreSQL cases are reported as skipped, loudly, and the job
  configuration makes that impossible in CI
- **Why:** a silent skip is how T7 happened; the counterfactual is what proves
  the service is load-bearing.

### OPS-038 · The accessibility job installs a browser and runs axe
- **Area:** `.github/workflows/gate.yml`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** read the job
- **Expected:** `playwright install --with-deps chromium` and
  `pytest tests/web/test_axe.py`
- **Why:** "docs/19 said 'the accessibility guarantee is held by axe-core in CI'
  on one page and listed [it] under Not done on another. This is the half that
  was missing."

### OPS-039 · The gate runs on both `main` and `develop`
- **Area:** `.github/workflows/gate.yml`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** read the triggers
- **Expected:** push and pull request on both branches
- **Why:** the git drill lands work on `develop` and merges to `main`; a gate on
  one of them is a gate half the work skips.

### OPS-040 · The lock-file check is skipped rather than failed without uv
- **Area:** `scripts/gate.sh`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `uv` absent
- **Steps:** run the gate
- **Expected:** a printed note, and the rest of the gate runs
- **Why:** "a contributor without it can still run everything else" — but confirm
  CI always has it, or the check never runs where it matters.

### OPS-041 · `uv lock --check` fails when `pyproject.toml` has drifted
- **Area:** `scripts/gate.sh`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a dependency added to `pyproject.toml` without relocking
- **Steps:** run the gate
- **Expected:** non-zero
- **Why:** "A lock that has drifted is worse than none: it looks like a
  reproducible build and is not one."

### OPS-042 · `generate_docs.py --check` fails on hand-edited generated docs
- **Area:** `scripts/generate_docs.py`, `scripts/gate.sh`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a generated reference edited by hand
- **Steps:** run the gate
- **Expected:** non-zero, naming the file
- **Why:** "A reference edited by hand is a second source of truth, and it drifts
  in the flattering direction."

### OPS-043 · `run_prama_web.py` refuses to invent a secret
- **Area:** `run_prama_web.py::main`
- **Type:** security
- **Priority:** P1
- **Precondition:** no secret configured, no `--init-secret`
- **Steps:** run
- **Expected:** a refusal naming `--init-secret` and
  `PRAMA_SECURITY__SESSION_SECRET`; exit 1
- **Why:** "signed sessions would be forgeable by anyone holding the source".

### OPS-044 · `--init-secret` writes only into the git-ignored overlay
- **Area:** `run_prama_web.py::_write_local_secret`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** run with the flag, then `git status`
- **Expected:** `config/application.local.yaml` written; nothing tracked changes
- **Why:** "the file the pre-commit hook refuses to let a secret out of".

### OPS-045 · `--init-secret` refuses to overwrite an existing secret
- **Area:** `run_prama_web.py::_write_local_secret`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a local file already setting `session_secret`
- **Steps:** run with the flag
- **Expected:** a refusal that leaves the file alone; exit 1
- **Why:** rotating a secret silently invalidates every live session with no
  warning.

### OPS-046 · The generated secret is not derivable from the machine
- **Area:** `run_prama_web.py::_write_local_secret`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** generate twice on the same host
- **Expected:** different values, each 48 bytes of `token_urlsafe`
- **Why:** "a secret you could recompute from the hostname is not one".

### OPS-047 · `--prepare` applies the schema and creates the estate idempotently
- **Area:** `run_prama_web.py::_prepare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a fresh clone with a secret
- **Steps:** run with `--prepare` twice
- **Expected:** created, then found; the same tenant id both times
- **Why:** the three steps "somebody has to know about before `serve` is any
  use", and running it twice is what a person does.

### OPS-048 · `--prepare` does not silently touch a PostgreSQL database
- **Area:** `run_prama_web.py`
- **Type:** security
- **Priority:** P1
- **Precondition:** `database.dialect: postgres`
- **Steps:** run with `--prepare`
- **Expected:** either a confirmation is required, or the documented promise is
  corrected
- **Why:** the module docstring promises it will not "touch a database that is
  not SQLite without being told", and `_prepare` calls `initialise()` on whatever
  the configuration names.

### OPS-049 · Without a tenant, the launcher says why the console will redirect
- **Area:** `run_prama_web.py::main`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** no default tenant
- **Steps:** run
- **Expected:** the printed explanation and the `prama tenant create` command
- **Why:** "'it redirected me to a sign-in page that does not exist' is the
  specific way a fresh installation looks broken when it is merely empty".

### OPS-050 · The launcher does not mutate the configuration in place
- **Area:** `run_prama_web.py::main`
- **Type:** contract
- **Priority:** P2
- **Precondition:** `--prepare`
- **Steps:** inspect how the tenant is applied
- **Expected:** a new `Configuration` is built; provenance names
  `run-prama-web`
- **Why:** "a launcher that patched it in place would be the one place in the
  codebase where [configuration] is not [immutable]".

### OPS-051 · The URLs are flushed before uvicorn takes over
- **Area:** `run_prama_web.py::main`
- **Type:** regression
- **Priority:** P2
- **Precondition:** stdout redirected to a file
- **Steps:** run, then read the file immediately
- **Expected:** the URLs are present
- **Why:** "stdout is block-buffered whenever it is not a terminal, so piping
  this to a file or running it under a supervisor showed the log and never the
  URLs".

### OPS-052 · A missing `uvicorn` produces an install hint, not a traceback
- **Area:** `run_prama_web.py::main`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `serve` extra not installed
- **Steps:** run
- **Expected:** "the HTTP server is not installed" and
  `pip install -e ".[serve]"`; exit 1
- **Why:** the remedy must be followable literally — confirm the extra is named
  that in `pyproject.toml`.

### OPS-053 · The launcher uses the same code paths as the CLI
- **Area:** `run_prama_web.py`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** confirm it calls `Database`, `create_app` and `load_configuration`
  and defines no application assembly of its own
- **Expected:** it does
- **Why:** "A launcher with its own opinion about how to build the application is
  a launcher that will one day start something the CLI cannot."

### OPS-054 · `SIGTERM` shuts the server down gracefully
- **Area:** `run_prama_web.py`, `core/concurrency/supervisor.py`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a running server with in-flight work
- **Steps:** send `SIGTERM`, wait
- **Expected:** the process exits within the shutdown grace; leases are released;
  no partial transaction is committed
- **Why:** Kubernetes sends exactly this on every rolling update.

### OPS-055 · `SIGKILL` leaves a recoverable state
- **Area:** `db/lease_provider.py`, `db/dao/evidence.py`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a server killed mid-run
- **Steps:** restart, verify the schema and the chain, list unfinished runs
- **Expected:** the schema verifies, the chain verifies, the interrupted run
  appears in `unfinished`, and its lease expires on its own
- **Why:** the three recovery mechanisms are designed for exactly this, and none
  of them has been exercised together.

### OPS-056 · A tracer records a span even when the block raises
- **Area:** `telemetry/trace.py::Tracer.span`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a `MemoryTracer`
- **Steps:** raise inside a span
- **Expected:** the span is recorded with an `error` and a duration; the
  exception propagates
- **Why:** "A span abandoned on an exception is the one you most want: it is the
  four-minute query that failed."

### OPS-057 · `NullTracer` is the default and costs nothing
- **Area:** `telemetry/trace.py::NullTracer`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** confirm no OpenTelemetry import is required to run
- **Expected:** none
- **Why:** "A bank evaluating the platform on a laptop and a bank running it on a
  fleet want the same code."

### OPS-058 · Span names are constants, not literals at call sites
- **Area:** `telemetry/trace.py`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** grep for `"prama.` string literals passed to `span(`
- **Expected:** every call uses one of the six constants
- **Why:** "so a dashboard built against one deployment works against the next —
  and so renaming one is a change to a constant rather than a search".

### OPS-059 · `Span.set` records what was learned during the span
- **Area:** `telemetry/trace.py::Span.set`
- **Type:** functional
- **Priority:** P3
- **Precondition:** a span
- **Steps:** set an attribute inside the block, read the recorded span
- **Expected:** present
- **Why:** "a trace whose attributes are guesses is a trace nobody can reason
  from".

### OPS-060 · A lineage event carries no data values
- **Area:** `telemetry/lineage.py::Lineage.finished`, `Assertion`
- **Type:** security
- **Priority:** P1
- **Precondition:** evidence records with failing samples and metrics
- **Steps:** emit and inspect the event
- **Expected:** dataset names, column names and outcomes only; no metric values,
  no sample rows, no detail text
- **Why:** "a lineage bus is the least access-controlled pipe in most estates and
  the fastest way to move personal data somewhere nobody meant it to be".

### OPS-061 · A failing control is a COMPLETE event, not a FAIL
- **Area:** `telemetry/lineage.py::EventType.for_verdict`
- **Type:** contract
- **Priority:** P1
- **Precondition:** verdicts of pass, fail, error and aborted
- **Steps:** map each
- **Expected:** COMPLETE for pass and fail; FAIL for error and aborted
- **Why:** "the job did exactly what it was asked. FAIL is reserved for a run
  that could not answer, which is … what an operator's alerting should key on".

### OPS-062 · The worst verdict decides the event type
- **Area:** `telemetry/lineage.py::_worst_verdict`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a run with one error among ninety-nine passes
- **Steps:** emit
- **Expected:** FAIL
- **Why:** an event that reported the modal verdict would say a broken run
  completed.

### OPS-063 · An unknown verdict does not silently become the best one
- **Area:** `telemetry/lineage.py::_worst_verdict`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a verdict outside the known order
- **Steps:** emit
- **Expected:** a defined, documented outcome
- **Why:** the key function returns 0 for an unknown verdict, which ranks it with
  `pass` — so a new verdict kind would be the most flattering possible default.

### OPS-064 · The event conforms to the OpenLineage shape
- **Area:** `telemetry/lineage.py::RunEvent.to_dict`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a finished run
- **Steps:** serialise
- **Expected:** `eventType`, `eventTime`, `run.runId`, `job.namespace`,
  `job.name`, `inputs`, `producer`, `schemaURL`, and the
  `dataQualityAssertions` facet with its `_producer` and `_schemaURL`
- **Why:** "a Prama verdict appears *inside* whatever catalogue the bank already
  runs" only if the document is the one the catalogue expects.

### OPS-065 · A START event is emitted before the work
- **Area:** `telemetry/lineage.py::Lineage.started`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a run
- **Steps:** emit
- **Expected:** a START event with a run id that the COMPLETE event reuses
- **Why:** "a consumer that only ever sees COMPLETE cannot tell a run that is
  slow from one that never happened".

### OPS-066 · `NullEmitter` is the default
- **Area:** `telemetry/lineage.py::Lineage.__init__`
- **Type:** contract
- **Priority:** P1
- **Precondition:** no emitter configured
- **Steps:** emit
- **Expected:** nothing published, no error
- **Why:** "A platform that emitted to a bus nobody configured would fail on
  every run in an air-gapped deployment."

### OPS-067 · The producer URL carries the version
- **Area:** `telemetry/lineage.py::PRODUCER`
- **Type:** documentation
- **Priority:** P3
- **Precondition:** none
- **Steps:** read
- **Expected:** it embeds `VERSION` from `prama.version`
- **Why:** "the thing a consumer uses to tell Prama's events from everybody
  else's", and the version is what lets them tell two Prama deployments apart.

### OPS-068 · `verify_evidence.py` runs without importing Prama
- **Area:** `scripts/verify_evidence.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a sealed bundle, a Python with no Prama installed
- **Steps:** run it
- **Expected:** it verifies the chain and exits zero
- **Why:** an auditor who has to install the product to check its evidence is
  being asked to trust the product to check itself.

### OPS-069 · `verify_evidence.py` detects a tampered record
- **Area:** `scripts/verify_evidence.py`
- **Type:** security
- **Priority:** P1
- **Precondition:** a bundle with one record's content edited
- **Steps:** run
- **Expected:** non-zero, naming the sequence
- **Why:** the counterfactual that makes the clean run mean something.

### OPS-070 · Only `prama.db` imports SQLAlchemy
- **Area:** all of `src/prama/`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** scan every module's imports
- **Expected:** only `prama/db/**`
- **Why:** CLAUDE.md rule 3, already enforced by
  `tests/architecture/test_layering.py` — the case exists so the counterfactual
  is written: add the import elsewhere and confirm the build fails.

### OPS-071 · No model output reaches a verdict
- **Area:** all of `src/prama/`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** trace every path into `EvidenceRecord.verdict` and into
  `Verdict.alerted`
- **Expected:** none passes through a model
- **Why:** `CON-007` and `NFR-AI-002` — "Models author, rank, explain, calibrate
  and summarise. A deterministic, versioned engine decides."

### OPS-072 · `metadata.create_all` is never called
- **Area:** all of `src/prama/`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** grep
- **Expected:** absent outside tests, and absent from tests that touch a real
  database
- **Why:** "a second source of schema truth is how the two silently diverge" —
  the ORM metadata and the schema files would then both be authorities.

### OPS-073 · No tracked file contains a non-empty secret
- **Area:** `config/application.yaml`, `deploy/`, `.github/`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** scan every tracked file for a non-empty value under a sensitive key
- **Expected:** none
- **Why:** CLAUDE.md rule 5, and the pre-commit hook only protects somebody who
  installed it.

### OPS-074 · No commit message carries an assistant attribution trailer
- **Area:** `.githooks/commit-msg`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the repository history
- **Steps:** scan every commit message for the three forbidden strings
- **Expected:** none
- **Why:** CLAUDE.md rule 1 — "Authorship of this repository is Ashutosh Sinha's
  alone", and a hook is enforcement only for somebody who ran
  `git config core.hooksPath .githooks`.
