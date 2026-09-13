# QA test cases — the command-line interface

Surface: `prama`, every command group and subcommand.
Written **before** execution. Results live in `log-cli.md`.

## Environment

```bash
cd /home/ashutosh/PycharmProjects/prama
export PATH="$PWD/.venv/bin:$PATH"
```

Scratch root is `/tmp/qa-cli/`. Nothing is written into the repository.

`/tmp/qa-cli/app.yaml`:

```yaml
database:
  dialect: sqlite
  sqlite: {path: /tmp/qa-cli/prama.db}
  schema_dir: /home/ashutosh/PycharmProjects/prama/schema
security:
  session_secret: "qa-cli-secret-long-enough-0123456789"
```

Every invocation below is `prama --config /tmp/qa-cli/app.yaml …` unless the case
is specifically about configuration loading. `CFG` abbreviates
`--config /tmp/qa-cli/app.yaml`.

## Fixtures

| File | What it is |
|---|---|
| `good.pql` | three well-formed controls over `positions` |
| `lint.pql` | two controls that parse but lint (`never-fires`, `always-fires`) |
| `bad.pql` | a truncated control — a syntax error |
| `empty.pql` | zero bytes |
| `onebyte.pql` | one byte, `x` |
| `adir/` | a directory, used wherever a file is expected |
| `contract.yaml` / `contract.json` | an ODCS 3.0.0 contract, one of its columns a type ODCS carries and Prama does not |
| `rows.json` | rows that satisfy the contract |
| `rows_missing.json` | rows missing a contracted column |
| `rows_extra.json` | rows with an extra column |
| `before.csv` / `after.csv` | three rows, then one changed, one removed, one added |
| `malformed.yaml`, `malformed.json`, `empty.yaml`, `empty.json` | broken and empty documents |
| `dbt_schema.yml`, `soda.yml`, `ge.json` | one estate each, in another tool's spelling |
| `fix.txt` | one FIX 4.4 NewOrderSingle |

## Exit-code contract under test

From `src/prama/cli/base.py`: `0` ok, `1` error, `2` usage, `3` drift/breach.
Every case records the observed code. A stack trace reaching the terminal is a
failure regardless of the code, because the taxonomy in `base.py` exists to stop
exactly that.

---

## 1. The entry point, global flags, version

### CLI-001 — `prama --help`
**Steps:** `prama --help`
**Expected:** exit 0; lists all sixteen command groups; names the version and tagline.

### CLI-002 — `prama` with no arguments
**Steps:** `prama`
**Expected:** help printed, exit 2 (usage). Not 0 — a bare invocation did not do anything.

### CLI-003 — `prama version`
**Steps:** `prama version`
**Expected:** exit 0; prints `0.1.0`, matching `src/prama/version.py::VERSION`.

### CLI-004 — `prama version --json`
**Steps:** `prama --json version`
**Expected:** exit 0; valid JSON on stdout; contains the same version, and IR/schema versions.

### CLI-005 — `--json` placed after the subcommand
**Steps:** `prama version --json`
**Expected:** either accepted, or exit 2 with a usage message naming the correct position. Silently ignoring it would be a finding.

### CLI-006 — an unknown command
**Steps:** `prama frobnicate`
**Expected:** exit 2; argparse names the invalid choice; no traceback.

### CLI-007 — an unknown global flag
**Steps:** `prama --nonsense version`
**Expected:** exit 2, usage error.

### CLI-008 — `--config` naming a file that does not exist
**Steps:** `prama --config /tmp/qa-cli/nope.yaml version`
**Expected:** a Prama error naming the path, with a `next:` remedy; exit 1. A traceback is a failure.

### CLI-009 — `--config` naming malformed YAML
**Steps:** `prama --config /tmp/qa-cli/malformed.yaml config show`
**Expected:** error naming the file and the parse position; exit 1; no traceback.

### CLI-010 — `--config` naming a directory
**Steps:** `prama --config /tmp/qa-cli/adir config show`
**Expected:** error saying it is a directory; exit 1; no `IsADirectoryError` traceback.

### CLI-011 — `--config` naming an empty file
**Steps:** `prama --config /tmp/qa-cli/empty.yaml config show`
**Expected:** either treated as no overrides (exit 0) or a clear error. Whichever, no traceback. Note that the shipped `session_secret` is empty on purpose, so a command needing it should refuse.

### CLI-012 — `--set` with a well-formed override
**Steps:** `prama CFG --set logging.level=DEBUG config show`
**Expected:** exit 0; the shown configuration carries `DEBUG`.

### CLI-013 — `--set` with no `=`
**Steps:** `prama CFG --set nonsense config show`
**Expected:** exit 1 or 2 with a message naming the expected `KEY=VALUE` form; no traceback.

### CLI-014 — `--set` repeated
**Steps:** `prama CFG --set logging.level=DEBUG --set logging.format=json config show`
**Expected:** exit 0; both overrides present.

### CLI-015 — `--set` with an unknown key
**Steps:** `prama CFG --set not.a.key=1 config show`
**Expected:** either rejected with a message naming the key, or accepted and shown. A silent discard is a finding.

### CLI-016 — `--log-level` with a bogus value
**Steps:** `prama CFG --log-level LOUD version`
**Expected:** a message naming the four permitted levels; no traceback.

### CLI-017 — `--log-level DEBUG`
**Steps:** `prama CFG --log-level DEBUG version`
**Expected:** exit 0; debug logging visible or at least harmless.

---

## 2. `config`

### CLI-018 — `prama config` with no subcommand
**Steps:** `prama CFG config`
**Expected:** `usage: prama config <show>`; exit 2.

### CLI-019 — `config show`
**Steps:** `prama CFG config show`
**Expected:** exit 0; the merged configuration; the session secret redacted.

### CLI-020 — `config show --json`
**Steps:** `prama CFG --json config show`
**Expected:** exit 0; parseable JSON; secret still redacted.

### CLI-021 — `config show --provenance`
**Steps:** `prama CFG config show --provenance`
**Expected:** exit 0; each value labelled with where it came from — default, file, `--set`, environment.

### CLI-022 — `config show --raw` without the environment variable
**Steps:** `prama CFG config show --raw`
**Expected:** refused; message names `PRAMA_ALLOW_RAW_CONFIG=1`; non-zero exit. The secret must not appear.

### CLI-023 — `config show --raw` with `PRAMA_ALLOW_RAW_CONFIG=1`
**Steps:** `PRAMA_ALLOW_RAW_CONFIG=1 prama CFG config show --raw`
**Expected:** exit 0; the real secret shown.

### CLI-024 — redaction actually covers the secret
**Steps:** `prama CFG config show | grep -c qa-cli-secret`
**Expected:** zero matches. Any leak is a security finding.

### CLI-025 — `config show --raw --provenance` together
**Steps:** `PRAMA_ALLOW_RAW_CONFIG=1 prama CFG config show --raw --provenance`
**Expected:** exit 0; both behaviours compose.

### CLI-026 — `config show` with no `--config` at all
**Steps:** `prama config show` (from the repo root, so `config/application.yaml` may be found)
**Expected:** exit 0 or a clear error; the shipped empty `session_secret` shown as empty/redacted, not invented.

---

## 3. `db`

### CLI-027 — `prama db` with no subcommand
**Expected:** usage line, exit 2.

### CLI-028 — `db info` before `db init`
**Precondition:** `/tmp/qa-cli/prama.db` does not exist.
**Expected:** either reports "not initialised" with a `next:` remedy naming `db init`, or errors cleanly. Non-zero if it cannot answer. No traceback.

### CLI-029 — `db verify` before `db init`
**Precondition:** no database file.
**Expected:** non-zero; message says the schema is absent; remedy names `prama db init`.

### CLI-030 — follow the CLI-029 remedy literally
**Steps:** run whatever CLI-029 printed after `next:`, verbatim.
**Expected:** it succeeds. A remedy whose own advice fails is a finding.

### CLI-031 — `db init`
**Expected:** exit 0; the database file is created; output names the schema file applied.

### CLI-032 — `db init` twice (idempotence)
**Steps:** `prama CFG db init` again.
**Expected:** exit 0; no error; no duplicate-object failure. Rule 2 of CLAUDE.md says it applies idempotently.

### CLI-033 — `db verify` after `db init`
**Expected:** exit 0; no drift.

### CLI-034 — `db verify --json`
**Expected:** exit 0; parseable JSON.

### CLI-035 — `db info` after `db init`
**Expected:** exit 0; names the dialect, the path, the table count.

### CLI-036 — `db info --json`
**Expected:** exit 0; parseable JSON with the same facts.

### CLI-037 — `db verify` against a drifted database
**Steps:** `sqlite3 /tmp/qa-cli/drift.db` copy, drop one table, point config at it, `db verify`.
**Expected:** non-zero (3, drift); the message names the missing table; the remedy does **not** offer to migrate.

### CLI-038 — `db init` with a `schema_dir` that does not exist
**Steps:** `prama CFG --set database.schema_dir=/tmp/qa-cli/nope db init`
**Expected:** clean error naming the directory; exit 1; no traceback.

### CLI-039 — `db init` into an unwritable location
**Steps:** `--set database.sqlite.path=/proc/nope/prama.db`
**Expected:** clean error; exit 1; no raw `OperationalError`.

### CLI-040 — `db init` with an unknown dialect
**Steps:** `--set database.dialect=oracle db info`
**Expected:** error naming the two supported dialects; exit 1.

### CLI-041 — `db info` against `postgres` with nothing listening
**Steps:** `--set database.dialect=postgres db info`
**Expected:** a connection error phrased as a sentence, with a remedy; exit 1; no raw driver traceback.

### CLI-042 — `db init` when the database file is a directory
**Steps:** `--set database.sqlite.path=/tmp/qa-cli/adir db init`
**Expected:** clean error; exit 1.

---

## 4. `tenant`

### CLI-043 — `prama tenant` with no subcommand
**Expected:** usage, exit 2.

### CLI-044 — `tenant list` on an empty, initialised database
**Expected:** exit 0; says there are none; ideally names `tenant create`.

### CLI-045 — `tenant create acme-bank`
**Expected:** exit 0; prints the tenant id; likely prints a `next:` line naming `principal create`.

### CLI-046 — follow whatever CLI-045 printed, verbatim
**Expected:** it works. This is the exact shape of a previously shipped defect (`tenant create` printing a command `principal create` refused), so it gets its own case.

### CLI-047 — `tenant create acme-bank` twice
**Expected:** a clear "already exists" with the existing id, or a clean non-zero error. Not a raw `IntegrityError`.

### CLI-048 — `tenant list` after creation
**Expected:** exit 0; the tenant listed with its id and slug.

### CLI-049 — `tenant list --json`
**Expected:** exit 0; parseable JSON.

### CLI-050 — `tenant create` with `--name` and `--residency`
**Steps:** `tenant create eu-desk --name "EU Desk" --residency EU`
**Expected:** exit 0; both recorded and visible in `tenant list`.

### CLI-051 — `tenant create` with no slug
**Expected:** exit 2; argparse names the missing argument.

### CLI-052 — `tenant create ""`
**Expected:** rejected with a sentence; not a database constraint error.

### CLI-053 — `tenant create ACME_Bank!` (an invalid slug)
**Expected:** rejected, naming the permitted shape ("lowercase, e.g. acme-bank" per the help), or accepted consistently. A help text that promises lowercase while the code accepts anything is a finding.

### CLI-054 — `tenant create` with a 500-character slug
**Expected:** rejected against the `VARCHAR(n)` width with a sentence, not a truncation and not a driver error.

### CLI-055 — `tenant create` before `db init`
**Precondition:** a fresh config pointing at a database that was never initialised.
**Expected:** error whose remedy names `prama db init`; exit 1; no traceback.

### CLI-056 — follow the CLI-055 remedy literally
**Expected:** it works and the create then succeeds.

---

## 5. `principal`

### CLI-057 — `principal roles`
**Expected:** exit 0; the four roles (admin, owner, steward, auditor) and what each may do.

### CLI-058 — `principal roles --json`
**Expected:** exit 0; parseable JSON.

### CLI-059 — `principal list` with no tenant configured
**Expected:** a sentence naming `tenancy.default_tenant` or `--tenant`; non-zero; no traceback.

### CLI-060 — `principal create` before any tenant exists
**Precondition:** initialised database, no tenants.
**Expected:** error naming the missing tenant, remedy naming `prama tenant create`; exit 1.

### CLI-061 — `principal create alice --admin --tenant <id>`
**Steps:** password supplied on stdin (twice, if confirmed).
**Expected:** exit 0; the principal created; the password never echoed.

### CLI-062 — `principal create` with the tenant *slug* rather than its id
**Expected:** either accepted (slug resolves) or a message saying an id is wanted and how to get one. `tenant create` prints an id; `tenant list` shows both — whichever `--tenant` wants must be stated.

### CLI-063 — `principal list --tenant <id>`
**Expected:** exit 0; alice listed with her roles.

### CLI-064 — `principal list --json`
**Expected:** exit 0; parseable JSON; no password hash in the output.

### CLI-065 — `principal create alice` a second time
**Expected:** a clean "already exists"; not a raw uniqueness violation.

### CLI-066 — `principal create` with no username
**Expected:** exit 2; argparse names it.

### CLI-067 — `principal create bob --role auditor --role steward`
**Expected:** exit 0; both roles recorded (the flag is documented as repeatable).

### CLI-068 — `principal create carol --role wizard`
**Expected:** rejected, naming the four valid roles; exit 1 or 2.

### CLI-069 — `principal create dave --email not-an-email`
**Expected:** either validated and rejected with a sentence, or accepted. Silently storing an unusable address is worth recording.

### CLI-070 — `principal create eve --tenant 01NOSUCHTENANT`
**Expected:** error naming the tenant; exit 1; no traceback.

### CLI-071 — `principal create` with an empty password
**Steps:** press enter at the prompt.
**Expected:** refused with a minimum-length sentence; not accepted.

### CLI-072 — `principal create` with mismatched confirmation
**Expected:** refused and re-prompted or exited cleanly.

### CLI-073 — `principal create` with stdin closed (non-interactive CI)
**Steps:** `prama CFG principal create frank --admin < /dev/null`
**Expected:** a sentence saying a password cannot be read, not an `EOFError` traceback.

---

## 6. `connectors`

### CLI-074 — `connectors`
**Expected:** exit 0; a table of installed connectors, ending with a count and a pointer to `--key`.

### CLI-075 — `connectors --json`
**Expected:** exit 0; parseable JSON catalogue.

### CLI-076 — `connectors --key <a real key from CLI-074>`
**Expected:** exit 0; the configuration form, grouped, with required fields marked.

### CLI-077 — `connectors --key <real key> --json`
**Expected:** exit 0; the same form as JSON.

### CLI-078 — `connectors --key nosuchconnector`
**Expected:** a sentence naming the unknown key and listing what is installed; exit 1; not a `KeyError` traceback.

### CLI-079 — `connectors --key ""`
**Expected:** same treatment as CLI-078, or the full catalogue. Not a traceback.

---

## 7. `connect`

### CLI-080 — `prama connect` with no subcommand
**Expected:** usage, exit 2.

### CLI-081 — `connect test` with no `--connection`
**Expected:** exit 2; argparse names the required flag.

### CLI-082 — `connect test --connection 01NOSUCH`
**Expected:** a sentence naming the unknown connection id, with a remedy; exit 1. There is no `connect create` in the CLI, so the remedy has to point somewhere real — where it points is the case.

### CLI-083 — `connect discover --connection 01NOSUCH`
**Expected:** as CLI-082.

### CLI-084 — `connect profile --connection 01NOSUCH`
**Expected:** as CLI-082.

### CLI-085 — `connect discover --limit 0`
**Expected:** either an empty result or a sentence about the bound; no traceback.

### CLI-086 — `connect discover --limit -5`
**Expected:** rejected with a sentence, or clamped. A negative limit reaching SQL is a finding.

### CLI-087 — `connect discover --limit abc`
**Expected:** exit 2; argparse type error.

### CLI-088 — `connect test` against an uninitialised database
**Expected:** the `db init` remedy, not a missing-table error.

### CLI-089 — `connect profile --object nosuchtable --connection 01NOSUCH`
**Expected:** the connection error first; exit 1.

---

## 8. `control` — static commands

### CLI-090 — `prama control` with no subcommand
**Expected:** usage, exit 2.

### CLI-091 — `control check good.pql`
**Expected:** exit 0; three controls parsed and type-checked; says so.

### CLI-092 — `control check --json good.pql`
**Expected:** exit 0; parseable JSON.

### CLI-093 — `control check bad.pql`
**Expected:** non-zero; a syntax error with line, column and a caret; a remedy.

### CLI-094 — `control check empty.pql`
**Expected:** exit 0 with "no controls", or a clean error. Not a traceback.

### CLI-095 — `control check onebyte.pql`
**Expected:** a syntax error pointing at column 1; non-zero.

### CLI-096 — `control check /tmp/qa-cli/nope.pql`
**Expected:** a sentence naming the missing file; exit 1; not a `FileNotFoundError` traceback.

### CLI-097 — `control check adir`
**Expected:** a sentence saying it is a directory; exit 1; not an `IsADirectoryError`.

### CLI-098 — `control check lint.pql` without `--strict`
**Expected:** exit 0; the two lint findings printed as warnings.

### CLI-099 — `control check --strict lint.pql`
**Expected:** non-zero; the same findings, now fatal; suitable as a CI gate.

### CLI-100 — `control check` with no file
**Expected:** exit 2.

### CLI-101 — `control explain good.pql`
**Expected:** exit 0; one plain sentence per control, no PQL in the output.

### CLI-102 — `control explain bad.pql`
**Expected:** the same syntax error as CLI-093; non-zero.

### CLI-103 — `control explain --json good.pql`
**Expected:** exit 0; parseable JSON.

### CLI-104 — `control format good.pql`
**Expected:** exit 0; canonical text on stdout; the file untouched.

### CLI-105 — `control format --write` then `git`-style diff
**Steps:** copy `good.pql`, `control format --write` on the copy, compare.
**Expected:** exit 0; the file rewritten.

### CLI-106 — `control format --write` twice (idempotence)
**Expected:** the second run changes nothing. A formatter that is not a fixed point is a finding.

### CLI-107 — `control format` on a file that already is canonical
**Expected:** identical output; exit 0.

### CLI-108 — `control format bad.pql`
**Expected:** the syntax error; the file left untouched even with `--write`.

### CLI-109 — `control functions`
**Expected:** exit 0; the coverage table, one row per engine.

### CLI-110 — `control functions --engine duckdb`
**Expected:** exit 0; that engine's coverage in detail.

### CLI-111 — `control functions --engine oracle`
**Expected:** a sentence naming the engines that exist; exit 1; not a `KeyError`.

### CLI-112 — `control functions --json`
**Expected:** exit 0; parseable JSON.

### CLI-113 — `control compile good.pql`
**Expected:** exit 0; SQL for the default dialect.

### CLI-114 — `control compile --dialect sqlite good.pql`
**Expected:** exit 0; SQLite SQL.

### CLI-115 — `control compile --dialect duckdb good.pql`
**Expected:** exit 0; DuckDB SQL, differing from SQLite where the dialects differ.

### CLI-116 — `control compile --dialect postgresql good.pql`
**Expected:** exit 0; PostgreSQL SQL.

### CLI-117 — `control compile --dialect mysql good.pql`
**Expected:** a sentence naming the three supported dialects; exit 1.

### CLI-118 — `control compile --fuse good.pql`
**Expected:** exit 0; the three controls grouped into fewer scans than three, and the grouping said out loud.

### CLI-119 — `control compile --fuse --dialect duckdb good.pql`
**Expected:** exit 0; flags compose.

### CLI-120 — `control compile bad.pql`
**Expected:** syntax error; non-zero.

### CLI-121 — `control compile empty.pql`
**Expected:** no SQL, exit 0, or a clean error. Emitting an empty query that would run is a finding.

---

## 9. `control run`

### CLI-122 — `control run` with no `--against`
**Expected:** exit 2; argparse names it.

### CLI-123 — `control run --against /tmp/qa-cli/nope.db`
**Expected:** a sentence naming the missing data file; exit 1.

### CLI-124 — `control run --against adir`
**Expected:** a clean error; exit 1.

### CLI-125 — `control run` before `db init`
**Expected:** the `db init` remedy; exit 1.

### CLI-126 — `control run --tenant <id> --against data.db` with no live controls
**Precondition:** data SQLite file with a `positions` table; no controls declared in the store.
**Expected:** exit 0 with "nothing to run", or a clean statement of what is live. Reporting a pass over zero controls without saying zero is a finding.

### CLI-127 — `control run --due-only`
**Expected:** exit 0; runs the subset the schedules say is due; says how many it skipped.

### CLI-128 — `control run --samples`
**Expected:** exit 0; the caveat about personal data on a clock is stated.

### CLI-129 — `control run --dialect sqlite` and `--dialect duckdb`
**Expected:** both accepted (the help restricts the choice to these two).

### CLI-130 — `control run --dialect postgresql`
**Expected:** exit 2; argparse rejects it against the declared choices.

### CLI-131 — `control run --tenant 01NOSUCH --against data.db`
**Expected:** a sentence naming the unknown tenant; exit 1.

### CLI-132 — `control run --against` a file that is not a database
**Steps:** point it at `good.pql`.
**Expected:** a sentence saying it is not a database; exit 1; not a raw `DatabaseError`.

---

## 10. `control import`

### CLI-133 — `control import --from dbt dbt_schema.yml`
**Expected:** exit 0; the controls that came across **and** a list of what did not, with reasons — `my_company.check_frtb_eligible` must appear as unmapped.

### CLI-134 — `control import --from soda soda.yml`
**Expected:** exit 0; `anomaly score` reported as not coming across.

### CLI-135 — `control import --from great_expectations ge.json`
**Expected:** exit 0; the KL-divergence expectation reported as unmapped.

### CLI-136 — `control import --from dbt --json dbt_schema.yml`
**Expected:** exit 0; parseable JSON carrying both halves.

### CLI-137 — `control import --from dbt --out out.pql dbt_schema.yml`
**Expected:** exit 0; the file written; the unmapped list still shown somewhere, not swallowed.

### CLI-138 — the output of CLI-137 fed back through `control check`
**Expected:** exit 0. An importer that emits PQL its own checker rejects is a finding.

### CLI-139 — `control import` with no `--from`
**Expected:** exit 2.

### CLI-140 — `control import --from sqlmesh x.yml`
**Expected:** exit 2; argparse names the three supported tools.

### CLI-141 — `control import --from dbt ge.json` (right tool, wrong file)
**Expected:** a sentence saying nothing was recognised; non-zero or a zero with an explicit "0 imported". Silently reporting success on zero is a finding.

### CLI-142 — `control import --from dbt malformed.yaml`
**Expected:** a parse error naming the file; exit 1; not a raw `yaml.scanner.ScannerError`.

### CLI-143 — `control import --from dbt empty.yaml`
**Expected:** "nothing to import"; no traceback.

### CLI-144 — `control import --from dbt /tmp/qa-cli/nope.yml`
**Expected:** a sentence naming the missing file; exit 1.

### CLI-145 — `control import --from dbt --out adir dbt_schema.yml`
**Expected:** a clean error about the output path; exit 1.

---

## 11. `contract`

### CLI-146 — `prama contract` with no subcommand
**Expected:** usage, exit 2.

### CLI-147 — `contract import contract.yaml`
**Expected:** exit 0; the declaration summarised; the `geospatial` column reported as **not** coming across; defaults stated as defaults.

### CLI-148 — `contract import contract.json`
**Expected:** identical result to CLI-147. A format that changes the meaning is a finding.

### CLI-149 — `contract import --controls contract.yaml`
**Expected:** exit 0; the controls the quality blocks become, and the ones they do not.

### CLI-150 — `contract import --json contract.yaml`
**Expected:** exit 0; parseable JSON.

### CLI-151 — `contract import malformed.yaml`
**Expected:** clean parse error; exit 1.

### CLI-152 — `contract import empty.yaml`
**Expected:** a sentence, e.g. "no schema"; exit non-zero or zero with an explicit statement; no traceback.

### CLI-153 — `contract import /tmp/qa-cli/nope.yaml`
**Expected:** a sentence naming the missing file; exit 1.

### CLI-154 — `contract import adir`
**Expected:** a sentence; exit 1.

### CLI-155 — `contract import onebyte.pql` (an unsuffixed, meaningless file)
**Expected:** a sentence; no traceback.

### CLI-156 — `contract export positions_eod --tenant <id>`
**Precondition:** nothing declared yet.
**Expected:** a sentence naming the unknown dataset with a remedy; exit 1. Not an empty contract that looks valid.

### CLI-157 — `contract export` with no dataset
**Expected:** exit 2.

### CLI-158 — `contract export x --tenant 01NOSUCH`
**Expected:** the tenant error; exit 1.

### CLI-159 — `contract export x --out /tmp/qa-cli/out.yaml`
**Expected:** consistent with CLI-156; no empty file left behind on failure.

### CLI-160 — `contract diff before.csv after.csv` with no `--key`
**Expected:** exit 0 or 3; the output **says** it is a membership comparison, per the help text.

### CLI-161 — `contract diff --key id before.csv after.csv`
**Expected:** row 2 changed, row 3 removed, row 4 added — named, not counted.

### CLI-162 — `contract diff --key id --ignore amount before.csv after.csv`
**Expected:** row 2 no longer differs.

### CLI-163 — `contract diff --key nosuch before.csv after.csv`
**Expected:** a sentence naming the column that is not there; exit 1.

### CLI-164 — `contract diff before.csv before.csv`
**Expected:** no differences; exit 0.

### CLI-165 — `contract diff /tmp/qa-cli/nope.csv after.csv`
**Expected:** a sentence naming the missing file; exit 1.

### CLI-166 — `contract diff empty.yaml after.csv`
**Expected:** a clean error about an unreadable/empty table; exit 1.

### CLI-167 — `contract diff --json --key id before.csv after.csv`
**Expected:** exit 0/3; parseable JSON.

### CLI-168 — `contract check contract.yaml --data rows.json`
**Expected:** exit 0; the contract is satisfied.

### CLI-169 — `contract check contract.yaml --data rows_missing.json`
**Expected:** exit 3 (breach), per `prama contract check` documented as "exit 3 on breach"; the missing column named.

### CLI-170 — `contract check contract.yaml --data rows_extra.json`
**Expected:** exit 3; the added column named.

### CLI-171 — `contract check --allow-additions contract.yaml --data rows_extra.json`
**Expected:** exit 0; the addition tolerated, and said so.

### CLI-172 — `contract check` with no `--data`
**Expected:** exit 2.

### CLI-173 — `contract check contract.yaml --data empty.json`
**Expected:** a clean statement; not a traceback; exit code recorded.

### CLI-174 — `contract check /tmp/qa-cli/nope.yaml --data rows.json`
**Expected:** a sentence; exit 1.

### CLI-175 — `contract check contract.yaml --data adir`
**Expected:** a sentence; exit 1.

### CLI-176 — `contract check --json contract.yaml --data rows_missing.json`
**Expected:** exit 3; parseable JSON naming the breach.

---

## 12. `estate`

### CLI-177 — `prama estate` with no subcommand
**Expected:** usage, exit 2.

### CLI-178 — `estate export` with no `--tenant`
**Expected:** exit 2.

### CLI-179 — `estate export --tenant <id> --dry-run`
**Expected:** exit 0; the files it *would* write listed; nothing written.

### CLI-180 — `estate export --tenant <id> --out /tmp/qa-cli/estate`
**Expected:** exit 0; the directory created and populated with YAML (possibly empty, if nothing is declared — which it should say).

### CLI-181 — `estate export --tenant 01NOSUCH --out …`
**Expected:** a sentence naming the tenant; exit 1.

### CLI-182 — `estate export --out` into a path that is a file
**Expected:** a clean error; exit 1.

### CLI-183 — `estate diff --tenant <id> --dir <the CLI-180 output>`
**Expected:** exit 0; no drift, since it was just exported.

### CLI-184 — `estate diff` after a file in the exported directory is edited
**Expected:** non-zero (drift); the changed file and field named; nothing resolved.

### CLI-185 — `estate diff --tenant <id> --dir /tmp/qa-cli/adir` (empty directory)
**Expected:** drift reported, or a sentence saying the directory holds no estate. Not a silent pass.

### CLI-186 — `estate diff --dir /tmp/qa-cli/nope`
**Expected:** a sentence naming the missing directory; exit 1.

### CLI-187 — `estate maturity --tenant <id>`
**Expected:** exit 0; a score with its components, and what is undescribed.

### CLI-188 — `estate maturity --json --tenant <id>`
**Expected:** exit 0; parseable JSON.

### CLI-189 — `estate maturity --tenant <id> --domain nosuchdomain`
**Expected:** a sentence, or an explicit zero. A silent 100% over an empty set is a finding.

### CLI-190 — `estate maturity` with no `--tenant`
**Expected:** exit 2.

---

## 13. `lsp`

### CLI-191 — `prama lsp` with no subcommand
**Expected:** usage, exit 2.

### CLI-192 — `lsp catalogue --tenant <id> --out /tmp/qa-cli/cat.json`
**Expected:** exit 0; a JSON file written; valid JSON.

### CLI-193 — `lsp catalogue` with no `--out`
**Expected:** written to stdout, or a stated default path.

### CLI-194 — `lsp catalogue --tenant 01NOSUCH`
**Expected:** a sentence; exit 1.

### CLI-195 — `lsp catalogue --out adir`
**Expected:** a clean error; exit 1.

### CLI-196 — `lsp serve --catalogue cat.json`, an LSP `initialize` over stdio
**Steps:** send a Content-Length framed `initialize` request; read the reply; close stdin; `timeout 30`.
**Expected:** a JSON-RPC response with `capabilities`; the process exits when stdin closes.

### CLI-197 — `lsp serve` with no catalogue
**Expected:** it starts and, per the help, *says* nothing is checked against a schema.

### CLI-198 — `lsp serve --catalogue /tmp/qa-cli/nope.json`
**Expected:** a sentence naming the missing file; exit 1; it must not start silently unarmed.

### CLI-199 — `lsp serve --catalogue malformed.json`
**Expected:** a clean parse error; exit 1.

### CLI-200 — `lsp serve` fed garbage on stdin
**Expected:** it does not hang forever and does not traceback; recorded either way.

---

## 14. `mcp`

### CLI-201 — `prama mcp` with no subcommand
**Expected:** usage, exit 2.

### CLI-202 — `mcp tools`
**Expected:** exit 0; the tools listed; each marked read/propose, never adjudicate (CON-007).

### CLI-203 — `mcp tools --json`
**Expected:** exit 0; parseable JSON.

### CLI-204 — no tool in `mcp tools` claims a verdict
**Steps:** inspect the list for any tool that could decide pass/fail.
**Expected:** none. This is a hard rule in CLAUDE.md.

### CLI-205 — `mcp serve --tenant <id>`, an MCP `initialize` over stdio
**Steps:** JSON-RPC `initialize` on stdin, `timeout 30`.
**Expected:** a response naming the protocol version and server; exits on stdin close.

### CLI-206 — `mcp serve --tenant 01NOSUCH`
**Expected:** a sentence; exit 1; it must not serve an estate that does not exist.

### CLI-207 — `mcp serve` before `db init`
**Expected:** the `db init` remedy; exit 1.

### CLI-208 — `mcp serve` fed malformed JSON-RPC
**Expected:** a JSON-RPC parse error, not a crash.

---

## 15. `pack`

### CLI-209 — `prama pack` with no subcommand
**Expected:** usage, exit 2.

### CLI-210 — `pack list`
**Expected:** exit 0; what the banking pack ships.

### CLI-211 — `pack list --json`
**Expected:** exit 0; parseable JSON.

### CLI-212 — `pack claims`
**Expected:** exit 0; discharged vs merely supported, separated.

### CLI-213 — `pack claims --json`
**Expected:** exit 0; parseable JSON.

### CLI-214 — `pack calendar TARGET2 --year 2030`
**Expected:** exit 0; the closures, computed from rules, with Good Friday and 25/26 December present.

### CLI-215 — `pack calendar TARGET2` with no year
**Expected:** exit 0; the current year.

### CLI-216 — `pack calendar NYSE --year 2026` and `FederalReserve`, `London`
**Expected:** exit 0 for each of the four names the help lists.

### CLI-217 — `pack calendar Narnia`
**Expected:** a sentence naming the four calendars; exit 1; not a `KeyError`.

### CLI-218 — `pack calendar TARGET2 --year 1500`
**Expected:** either computed, or refused with a sentence about the range. Not a crash.

### CLI-219 — `pack calendar TARGET2 --year abc`
**Expected:** exit 2; argparse type error.

### CLI-220 — `pack calendar` with no name
**Expected:** exit 2.

### CLI-221 — `pack calendar --json TARGET2 --year 2030`
**Expected:** exit 0; parseable JSON.

### CLI-222 — two runs of CLI-214 are identical
**Expected:** byte-identical. A calendar computed from rules must not drift between runs.

### CLI-223 — `pack reconciliation` with no identity
**Expected:** exit 0; all reference reconciliations listed.

### CLI-224 — `pack reconciliation <one from CLI-223>`
**Expected:** exit 0; its keys, tolerance and expected breaks.

### CLI-225 — `pack reconciliation nosuch`
**Expected:** a sentence listing what exists; exit 1.

### CLI-226 — `pack soc2`
**Expected:** exit 0; the criteria, **gaps first** as the CLAUDE.md command list claims.

### CLI-227 — `pack soc2 --json`
**Expected:** exit 0; parseable JSON.

### CLI-228 — `pack parse fix.txt`
**Expected:** exit 0 or non-zero if the message is faulty; the format inferred as FIX; what is wrong named.

### CLI-229 — `pack parse --format fix fix.txt`
**Expected:** same as CLI-228.

### CLI-230 — `pack parse --format iso8583 fix.txt`
**Expected:** a sentence saying it is not an ISO 8583 message; non-zero; not a traceback.

### CLI-231 — `pack parse --format fpml fix.txt`
**Expected:** a clean XML/parse error; non-zero.

### CLI-232 — `pack parse empty.pql`
**Expected:** a sentence about an empty message; no traceback.

### CLI-233 — `pack parse onebyte.pql`
**Expected:** a sentence; no traceback.

### CLI-234 — `pack parse /tmp/qa-cli/nope.fix`
**Expected:** a sentence naming the missing file; exit 1.

### CLI-235 — `pack parse adir`
**Expected:** a sentence; exit 1.

### CLI-236 — `pack parse --format bogus fix.txt`
**Expected:** exit 2; argparse names the three formats.

### CLI-237 — `pack parse --json fix.txt`
**Expected:** parseable JSON.

### CLI-238 — a FIX message with a broken checksum
**Steps:** change `10=128` to `10=001`.
**Expected:** the checksum failure named. A parser that does not check it is a finding for this domain.

### CLI-239 — `pack concepts`
**Expected:** exit 0; the concept model.

### CLI-240 — `pack concepts Exposure`
**Expected:** exit 0; the concept, and explicitly where it ends.

### CLI-241 — `pack concepts NoSuchConcept`
**Expected:** a sentence listing the concepts; exit 1.

### CLI-242 — `pack concepts exposure` (wrong case)
**Expected:** either resolved, or a sentence suggesting `Exposure`. A bare "unknown" when the only difference is case is poor but not wrong; recorded.

### CLI-243 — `pack concepts --json Exposure`
**Expected:** parseable JSON.

### CLI-244 — `pack recognise account_id ccy`
**Expected:** exit 0; the concept, or why that cannot be said.

### CLI-245 — `pack recognise zzz qqq`
**Expected:** exit 0 with "cannot be said", or non-zero; either way a reason, not a guess.

### CLI-246 — `pack recognise --as Exposure account_id ccy`
**Expected:** exit 0/non-zero against that one concept, with the evidence.

### CLI-247 — `pack recognise --as NoSuch account_id`
**Expected:** a sentence; exit 1.

### CLI-248 — `pack recognise` with no columns
**Expected:** exit 2.

### CLI-249 — `pack recognise --json account_id ccy`
**Expected:** parseable JSON.

### CLI-250 — `pack recognise` with 200 column names
**Expected:** no blow-up; completes.

---

## 16. `bench`

### CLI-251 — `prama bench` with no subcommand
**Expected:** usage, exit 2.

### CLI-252 — `bench taxonomy`
**Expected:** exit 0; defect classes by family and difficulty.

### CLI-253 — `bench taxonomy --json`
**Expected:** exit 0; parseable JSON.

### CLI-254 — `bench taxonomy --family <one from CLI-252>`
**Expected:** exit 0; that family only.

### CLI-255 — `bench taxonomy --family nosuch`
**Expected:** a sentence listing the families; exit 1; not an empty success.

### CLI-256 — `bench run --seed 42 --rows 200`
**Expected:** exit 0; a corpus built and every baseline scored; bounds stated.

### CLI-257 — `bench run --seed 42 --rows 200` a second time
**Expected:** identical scores. A seeded benchmark that is not reproducible is worthless.

### CLI-258 — `bench run --seed 43 --rows 200`
**Expected:** exit 0; different corpus, and it says which seed.

### CLI-259 — `bench run` with no `--seed`
**Expected:** exit 2; the help says it is required.

### CLI-260 — `bench run --seed abc`
**Expected:** exit 2; type error.

### CLI-261 — `bench run --seed 42 --rate 0.05 --rows 200`
**Expected:** exit 0; the rate honoured and reported.

### CLI-262 — `bench run --seed 42 --rate 5`
**Expected:** a sentence about a share being between 0 and 1; not silently planting five defects per row.

### CLI-263 — `bench run --seed 42 --rows 0`
**Expected:** a sentence; not a division by zero.

### CLI-264 — `bench run --seed -1`
**Expected:** either accepted and recorded, or refused with a sentence.

### CLI-265 — `bench run --json --seed 42 --rows 200`
**Expected:** parseable JSON carrying the seed.

---

## 17. `bundle`

### CLI-266 — `prama bundle` with no subcommand
**Expected:** usage, exit 2.

### CLI-267 — `bundle sbom`
**Expected:** exit 0; the dependency list.

### CLI-268 — `bundle sbom --json`
**Expected:** exit 0; parseable JSON, ideally CycloneDX or SPDX shaped.

### CLI-269 — `bundle seal /tmp/qa-cli/offline`
**Precondition:** a staged directory with a fake image tarball, a chart and a wheel.
**Expected:** exit 0; a manifest and an SBOM written; HMAC seal stated.

### CLI-270 — `bundle verify /tmp/qa-cli/offline`
**Expected:** exit 0; the seal checks out.

### CLI-271 — `bundle verify` on a directory that was never sealed
**Expected:** non-zero (3, "must not be installed"); a sentence saying there is no manifest.

### CLI-272 — `bundle verify` after one byte of a payload is changed
**Expected:** exit 3; the changed file named.

### CLI-273 — `bundle verify` after a file is added post-seal
**Expected:** exit 3; the unlisted file named. A manifest that only checks listed files misses an injected one.

### CLI-274 — `bundle verify` after a file is deleted post-seal
**Expected:** exit 3; the missing file named.

### CLI-275 — `bundle seal --no-sbom`
**Expected:** exit 0; the warning in the help text actually printed, not just documented.

### CLI-276 — `bundle seal --sign-with key.pem`
**Steps:** generate an Ed25519 key with `openssl genpkey -algorithm ed25519`.
**Expected:** exit 0; a signature produced.

### CLI-277 — `bundle verify --publisher-key pub.pem`
**Expected:** exit 0; provenance confirmed.

### CLI-278 — `bundle verify --publisher-key` with the *wrong* public key
**Expected:** exit 3; provenance refused. This is the case that matters: a verifier that accepts any key is worse than none.

### CLI-279 — `bundle verify --publisher-key` on an unsigned bundle
**Expected:** non-zero; a sentence saying there is no signature. Not a pass.

### CLI-280 — `bundle seal --sign-with notakey.pem`
**Expected:** a sentence; exit 1; not an `openssl`/cryptography traceback.

### CLI-281 — `bundle seal /tmp/qa-cli/nope`
**Expected:** a sentence naming the missing directory; exit 1.

### CLI-282 — `bundle seal good.pql` (a file, not a directory)
**Expected:** a sentence; exit 1.

### CLI-283 — `bundle seal` with no root
**Expected:** exit 2.

### CLI-284 — `bundle verify` with no root
**Expected:** exit 2.

### CLI-285 — `bundle seal` twice on the same directory
**Expected:** the second seal succeeds and `bundle verify` still passes — the manifest must not end up cataloguing its own previous manifest inconsistently.

### CLI-286 — `bundle seal` on an empty directory
**Expected:** either sealed with an empty manifest and said so, or refused. A silently valid empty bundle is a finding.

### CLI-287 — `bundle verify --json`
**Expected:** parseable JSON on both the pass and the fail path.

---

## 18. `serve`

### CLI-288 — `serve --port 19100` starts and answers
**Steps:** background it, poll `/` or `/health` for up to 20s, then kill it.
**Expected:** it binds; something answers; it shuts down on SIGTERM.

### CLI-289 — `serve` before `db init`
**Expected:** it refuses with the `db init` remedy rather than serving 500s.

### CLI-290 — `serve` with an empty `session_secret`
**Steps:** `--set security.session_secret=`
**Expected:** refuses to boot, per CLAUDE.md rule 5. This is a security case.

### CLI-291 — `serve --port abc`
**Expected:** exit 2; type error.

### CLI-292 — `serve --port 99999`
**Expected:** a sentence about the port range; not a raw `OverflowError`.

### CLI-293 — `serve --port <already bound>`
**Expected:** a sentence naming the port in use; not a raw `OSError`.

### CLI-294 — `serve --host 999.999.999.999`
**Expected:** a sentence; not a raw `socket.gaierror`.

---

## 19. Cross-command consistency and remedies

### CLI-295 — every `next:` remedy observed in this pass, run verbatim
**Expected:** each one succeeds, or at minimum does not fail with a *different* error. Collected as a table.

### CLI-296 — `--json` on a failing command
**Steps:** pick three failures from above and re-run with `--json`.
**Expected:** JSON on stdout with an `error` object; never a human sentence mixed into a JSON stream.

### CLI-297 — the version the CLI prints matches `version.py`
**Expected:** equal. CLAUDE.md says that constant is the only authority.

### CLI-298 — the tenant id printed by `tenant create` is accepted everywhere `--tenant` appears
**Steps:** feed it to `principal list`, `estate maturity`, `estate export`, `lsp catalogue`, `contract export`, `mcp serve`, `control run`.
**Expected:** all seven accept it. One that wants a slug instead is a seam defect.

### CLI-299 — the tenant *slug* everywhere `--tenant` appears
**Expected:** consistent — all accept it or all refuse it. A mixture is the finding.

### CLI-300 — `QUICKSTART.md` followed literally
**Steps:** run the commands in the repo's QUICKSTART in order, in the scratch directory.
**Expected:** each works as written. Documentation drift against the CLI is a finding.

### CLI-301 — every command group responds to `--help` with exit 0
**Expected:** all sixteen, and all forty-odd subcommands.

### CLI-302 — no command writes into the repository when run from the repo root
**Expected:** `git status` is clean after the whole pass.
