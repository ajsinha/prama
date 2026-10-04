<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# QA test cases — installation, configuration and operation

**Surface:** everything an operator does *before and around* using the product —
installing it, configuring it, standing up its database, running the server,
backing it up, sealing it for an air-gapped host.

**Written before execution.** Nothing in this file was written after seeing a
result. The results are in [`log-operate.md`](log-operate.md).

**Build under test:** `develop` at the working-tree state of 2026-09-12,
`VERSION = 0.1.0`, `SCHEMA_VERSION = 1`.

**Environment:** Linux 7.0.11-76070011-generic, Python 3.13 from the pinned uv
interpreter, Docker 29.8.0 available.

**Scratch:** `/tmp/qa-operate/`. Ports 19400–19499. Nothing under `src/`,
`tests/`, `schema/` or `config/` is modified; where a case needs a mutated
config or schema it operates on a **copy** of the tree under `/tmp`.

---

## How to read a case

| Field | Meaning |
|---|---|
| **Given** | the precondition the case sets up |
| **When** | the verbatim command |
| **Then** | what the product must do for the case to pass |

A case passes only if the *observed* behaviour matches **Then**. "It did
something reasonable" is not a pass; neither is "it crashed but the message was
nice" unless the case says a refusal is the expected behaviour.

The product's own doctrine is that *almost every failure mode is a refusal
carrying a remedy* (`docs/operations/README.md`). So for most negative cases the
expected result is **not** a traceback — it is a named error with a `next:`
line. A traceback where a refusal was promised is a defect, and several cases
below exist only to test that.

---

## Section 1 — A clean install, following the documentation literally (OPS-001 … OPS-016)

A person who has never seen this repository reads `README.md`, then
`QUICKSTART.md`, then `docs/operations/`. They type what is printed. These cases
are that person. Deviating from the printed text — even to fix an obvious typo —
is recorded as a finding, not absorbed.

| # | Given | When | Then |
|---|---|---|---|
| OPS-001 | A fresh clone of the repository at `/tmp/qa-operate/clone`, no venv, no local config | Inventory: does the clone contain `config/application.local.yaml` or `data/prama.db`? | Neither is present. A "fresh clone" in the documentation's sense must be reproducible; if the working tree ships a database or a local config the rest of the documentation is being tested against a lie. |
| OPS-002 | Fresh clone | `uv venv --python 3.13` in the clone | A venv is created from a standalone CPython under `~/.local/share/uv/python`, not `/usr/bin` (`CLAUDE.md`, troubleshooting §Environment). |
| OPS-003 | Venv created | `uv pip install -e ".[dev,serve]"` — the exact line from `README.md` §Run it | Installs without error. Record wall time and whether the network is required. |
| OPS-004 | Installed | `prama version` — QUICKSTART §1 "Check it" | Prints `0.1.0`, sourced from `src/prama/version.py`. Exit 0. |
| OPS-005 | Installed, no local config | `python run_prama_web.py --prepare` — QUICKSTART §2 first command | **Refuses**, with `security.session_secret is empty, and Prama will not start without it.` and a remedy naming `--init-secret` or `PRAMA_SECURITY__SESSION_SECRET`. Non-zero exit. QUICKSTART says this is intended. |
| OPS-006 | As OPS-005 | `python run_prama_web.py --init-secret --prepare` — QUICKSTART §2 the fix, and `README.md` §Run it | Writes a secret to `config/application.local.yaml`, applies the schema, creates estate `acme-bank`, prints the banner with console/API/docs URLs, and starts serving on `127.0.0.1:8080`. |
| OPS-007 | Server from OPS-006 running | `curl -sS http://127.0.0.1:8080/estate` | HTTP 200 and an HTML console page — README says "Then open http://127.0.0.1:8080/estate". |
| OPS-008 | Server from OPS-006 running | `curl -sS http://127.0.0.1:8080/api/v1/health` | HTTP 200, a health document naming the database. |
| OPS-009 | A secret already in `application.local.yaml` | `python run_prama_web.py --init-secret` a second time | Refuses to overwrite, saying the file already sets `session_secret`, and leaves the existing value alone. |
| OPS-010 | Installed, schema applied | The one-step-at-a-time sequence of QUICKSTART §3, verbatim: `prama db init`, `prama tenant create acme-bank --name "Acme Bank"`, `prama serve --host 0.0.0.0 --port 8080` | Each command works as printed. Record any that does not. |
| OPS-011 | Installed | The "useful neighbours" of QUICKSTART §3: `prama config show`, `prama db verify`, `prama db info`, `prama tenant list` | All four exist and exit 0. |
| OPS-012 | Installed | Every command printed in `README.md` §Run it and in `CLAUDE.md` §Commands that needs no external service | Each runs. Record any command printed in a document that does not exist or fails as printed. |
| OPS-013 | Installed, tenant exists | QUICKSTART §2 "Signing in": `prama principal roles`, `prama principal create alice --admin --name "Alice Chen"`, `prama principal list` | Works as printed. The password is prompted, not an argument. |
| OPS-014 | Installed | QUICKSTART §2 provisioning form: `printf '%s' "$PASSWORD" \| prama principal create svc-loader --role steward` | Accepts the password on stdin without a TTY. |
| OPS-015 | Installed | The CLI reference's claim: "If a flag is here it exists; if it is not here it does not." Compare `docs/operations/cli-reference.md` against `prama --help` and the parser | Every flag in the document exists; every flag the parser accepts is in the document. |
| OPS-016 | Installed | `cd case-studies/01-trading-book-sqlite && python run.py` — README §Run it and QUICKSTART §4 | Runs to completion, seeds a book, runs controls, reports planted-vs-caught. |

---

## Section 2 — Configuration (OPS-017 … OPS-052)

| # | Given | When | Then |
|---|---|---|---|
| OPS-017 | A directory containing **no** `config/` at all | `prama config show` from that directory | Boots on built-in defaults. `load_configuration` documents that "a missing configuration file is not an error". Exit 0. |
| OPS-018 | No config file | `prama version` from a directory with no `config/` | Works. The version command must not need configuration. |
| OPS-019 | No config file, defaults only | `prama db init` from an empty directory | Either creates `data/prama.db` relative to cwd, or refuses naming the missing schema directory. Whichever it does, it must be deliberate and must say which path it used. |
| OPS-020 | Repository config, unmodified, `session_secret: ""` | `python run_prama_web.py` | Refuses. The refusal names the fix (`--init-secret` or the env var). |
| OPS-021 | Repository config, unmodified, `session_secret: ""` | `prama serve --port 194xx` | **Question under test:** does `serve` refuse too, or does it start and fail later? QUICKSTART §3 offers `prama serve` as the equivalent of the launcher. If the launcher refuses and `serve` does not, that is an inconsistency worth recording. |
| OPS-022 | Empty secret, `web.enabled=true` | `curl /estate` against a `serve` started with an empty secret | If the server started, the console must refuse coherently rather than 500. |
| OPS-023 | A config file that is not valid YAML | `prama --config <bad.yaml> config show` | `CONFIG.YAML_INVALID` with the parser detail and a remedy. Not a traceback. |
| OPS-024 | A YAML file whose top level is a list | `prama --config <list.yaml> config show` | `CONFIG.YAML_SHAPE`: "must contain a mapping at the top level". |
| OPS-025 | An empty (zero-byte) YAML file | `prama --config <empty.yaml> config show` | Treated as `{}`; defaults apply; exit 0. |
| OPS-026 | A config with a string where a number goes (`database.pool.size: "not-a-number"`) | `prama config show` and then a command that reads the value | A typed refusal naming the key, at the point of use. A `ValueError` traceback is a defect. |
| OPS-027 | A config with a string where a boolean goes (`database.verify_on_start: "yes please"`) | `prama db verify` | A typed refusal naming the key. |
| OPS-028 | A config with an unknown top-level key (`nonsense: {a: 1}`) | `prama config show` | Records the observed behaviour. Accepting it silently is defensible; so is refusing. What must not happen is accepting a *misspelled known* key silently — see OPS-029. |
| OPS-029 | A config with a misspelled known key (`databse.dialect: postgres`) | `prama db info` | Records what happens. A silently ignored misspelling that leaves the operator on SQLite while they believe they are on PostgreSQL is a finding. |
| OPS-030 | A config missing a key the product needs (`security.session_secret` absent entirely, not empty) | `python run_prama_web.py` | Same refusal as empty. Absent and empty must not differ. |
| OPS-031 | A config file that does not exist, named explicitly | `prama --config /tmp/qa-operate/nope.yaml config show` | `CONFIG.FILE_MISSING`. `load_configuration` documents that an explicitly named missing file **is** an error. |
| OPS-032 | A config file with an unsupported extension | `prama --config /tmp/qa-operate/x.txt config show` | `CONFIG.FORMAT_UNSUPPORTED`, naming `.yaml`, `.yml`, `.properties`. |
| OPS-033 | A `.properties` file | `prama --config <x.properties> config show` | Dotted keys expand to the same nested shape YAML produces. |
| OPS-034 | A `.properties` file with a line that is not `key = value` | `prama --config <bad.properties> config show` | `CONFIG.PROPERTIES_INVALID` naming the line number. |
| OPS-035 | Default config | `prama --set database.dialect=postgres config show` | The override wins over the file. |
| OPS-036 | Default config | `prama --set database.pool.size=99 --set logging.level=DEBUG config show` | Repeated `--set` both apply; nested paths work. |
| OPS-037 | Default config | `prama --set database.dialect config show` (no `=`) | `CONFIG.CLI_INVALID`: "malformed override". |
| OPS-038 | Default config | `prama --set a=1 --set a.b=2 config show` | `CONFIG.KEY_CONFLICT` — a key cannot be both a scalar and a branch. |
| OPS-039 | Default config | `prama --set database.pool.size=99 config show --provenance` | The provenance column names `command line` for that key and the file for others. |
| OPS-040 | A local config containing a realistic-looking secret (`session_secret`, `postgres.password`) | `prama config show` | Neither value appears anywhere in the output. Redaction shows `***` or similar. |
| OPS-041 | Same | `prama config show --json` | Redacted in JSON output too. |
| OPS-042 | Same | `prama config show --raw` **without** `PRAMA_ALLOW_RAW_CONFIG=1` | Redaction is **not** lifted. The help text says raw is "refused unless PRAMA_ALLOW_RAW_CONFIG=1"; observe whether it is actually *refused* (an error) or merely *ignored*. Both are safe; only one matches the printed word. |
| OPS-043 | Same | `PRAMA_ALLOW_RAW_CONFIG=1 prama config show --raw` | Secrets are shown, and the output carries the warning line. |
| OPS-044 | Environment override | `PRAMA_DATABASE__DIALECT=postgres prama config show` | Applies. Documented in QUICKSTART §6 and the configuration reference. |
| OPS-045 | Environment override at a wrong depth | `PRAMA_DATABASE__PATH=/tmp/x.db prama db info` | Silently ignored — troubleshooting says so explicitly. Confirm it *is* silently ignored, and record that a silently ignored `PRAMA_`-prefixed variable is itself a hazard the product documents but does not detect. |
| OPS-046 | `${VAR}` with no value and no default in a config | `prama config show` | `CONFIG.PLACEHOLDER_UNRESOLVED`, not an empty string. |
| OPS-047 | A self-referential placeholder (`a: ${a}`) | `prama config show` | `CONFIG.PLACEHOLDER_CYCLE` naming the chain. |
| OPS-048 | `$${NOT_A_VAR}` in a config | `prama config show` | Resolves to the literal `${NOT_A_VAR}`. |
| OPS-049 | A connection secret expressed as `env://VAR` | Resolve it through `prama.secrets` | The reference resolves from the environment; a missing variable is a named refusal. |
| OPS-050 | A connection secret expressed as `file:///path` | Resolve it | Reads the file; a missing file is a named refusal; a world-readable file is or is not objected to — record which. |
| OPS-051 | A literal password where a `SecretRef` is expected | Parse it | "that is not a secret reference", and the error context must **not** contain the pasted text (the code comments say so deliberately). |
| OPS-052 | `hashicorp://` / vault reference with no Vault configured | Resolve it | "the vault secret provider is not usable in this deployment", naming what is missing — per troubleshooting. |

---

## Section 3 — Paths and the working directory (OPS-053 … OPS-060)

The configuration reference gives `database.schema_dir: schema` and
`database.sqlite.path: data/prama.db` — both **relative**. Relative to what is
the question, and the answer determines whether the product can be run from a
systemd unit or a cron job.

| # | Given | When | Then |
|---|---|---|---|
| OPS-053 | Installed repository | `cd /tmp && prama db info` | Records what happens with the default relative paths from a foreign cwd. QUICKSTART's troubleshooting table says `authoritative schema file not found` → "Run from the repository root, or set `database.schema_dir`". Confirm the refusal is that one and that it names the remedy. |
| OPS-054 | Installed repository | `cd /tmp && prama --config <repo>/config/application.yaml db init` | With an explicit config whose `schema_dir` is still relative, does the path resolve against the config file or the cwd? Record which. Resolving against cwd means a config file cannot be self-contained. |
| OPS-055 | Config with an **absolute** `database.schema_dir` and an absolute sqlite path | `cd /tmp && prama db init` | Works from any directory. |
| OPS-056 | Config with `database.sqlite.path` pointing into a directory that does not exist | `prama db init` | Either creates the parent or refuses naming it. A bare `sqlite3.OperationalError: unable to open database file` is a defect — no remedy. |
| OPS-057 | `database.sqlite.path` pointing at a **directory** | `prama db init` | A named refusal, not a driver-level error. |
| OPS-058 | `database.sqlite.path` in a directory the process cannot write (mode 0555) | `prama db init` | A named refusal naming the permission, with a remedy. |
| OPS-059 | `database.sqlite.path: ":memory:"` | `prama db init` then `prama db info` | Honoured (the configuration reference says so, "for tests"). Each process gets its own empty database; `db info` on a separate invocation shows an empty one. |
| OPS-060 | `database.schema_dir` pointing at a directory with no `sqlite.sql` | `prama db init` | A named refusal naming the file it looked for. |

---

## Section 4 — Database lifecycle (OPS-061 … OPS-082)

| # | Given | When | Then |
|---|---|---|---|
| OPS-061 | An empty scratch directory with a valid config | `prama db init` | Creates the database, applies `schema/sqlite.sql`, reports the dialect, the schema path, a digest and a table count. Exit 0. |
| OPS-062 | Database just initialised | `prama db init` a second time | Idempotent. No error, nothing dropped, same digest. |
| OPS-063 | Database with a tenant and a principal in it | `prama db init` | The data survives. **This is the destructive-init case**; any row loss is a release blocker. |
| OPS-064 | Database just initialised | `prama db verify` | Reports no drift. Exit 0. |
| OPS-065 | A good database | `prama db info` | Names the dialect, the file, and what is in it. |
| OPS-066 | A good database, then the **schema file on disk** is edited (a column added to a copy of `sqlite.sql`) | `prama db verify` | Reports drift, naming the object and the difference. Exits non-zero. Does **not** repair. |
| OPS-067 | A good database, then the **live database** is edited (`ALTER TABLE … ADD COLUMN`) | `prama db verify` | Reports drift, naming the added column. Non-zero. |
| OPS-068 | A good database with a live `ALTER TABLE` | `prama db init` | Must not attempt to reconcile. "`db init` applies the schema file idempotently and will not drop or alter an existing column" (runbook §1). |
| OPS-069 | A live database with a table **dropped** | `prama db verify` | Reports the missing table. |
| OPS-070 | A live database with a table dropped | `prama db init` | Recreates the missing table (init creates what is missing) without touching the rest. |
| OPS-071 | A drifted database, `database.verify_on_start: true` (the shipped default) | `prama serve` / the API's lifespan | Refuses to start, with `SchemaDriftError`. QUICKSTART's table promises exactly this. |
| OPS-072 | A drifted database, `database.verify_on_start: false` | `prama serve` | Starts. The operator asked for it. |
| OPS-073 | A path that does not exist (parent missing) | `prama db verify` | A named refusal. Verifying a database that is not there is not "no drift". |
| OPS-074 | A zero-byte file where the database should be | `prama db verify` | Either "not initialised" or drift naming every missing table — but a named refusal, not a driver error. |
| OPS-075 | A file that is not a SQLite database (random bytes) | `prama db init` | A named refusal. `file is not a database` from the driver with no remedy is a defect. |
| OPS-076 | A read-only database **file** (mode 0444), schema already applied | `prama db verify` | Works — verify only reads. |
| OPS-077 | A read-only database file | `prama db init` | A named refusal naming the permission. |
| OPS-078 | Both schema files | `cmp` of `schema/sqlite.sql` and `schema/postgres.sql` ignoring headers | Byte-identical apart from headers, as `CLAUDE.md` asserts and `tests/db/test_schema.py` enforces. An operator's sanity check. |
| OPS-079 | Docker available | `docker run -d --name qa-pg … postgres:16-alpine` on 19433 | Container starts and accepts connections. |
| OPS-080 | PostgreSQL running, `database.dialect: postgres` | `prama db init` | Applies `schema/postgres.sql`. |
| OPS-081 | PostgreSQL initialised | `prama db verify` | No drift. |
| OPS-082 | PostgreSQL initialised, then `ALTER TABLE … ADD COLUMN` in psql | `prama db verify` | Reports the drift. |

---

## Section 5 — Running the server (OPS-083 … OPS-098)

| # | Given | When | Then |
|---|---|---|---|
| OPS-083 | Prepared database, secret set, tenant set | `prama serve --port 19401` | Starts. Console, API and docs URLs printed. `/api/v1/health` answers. |
| OPS-084 | Secret set, **no** tenant configured | `prama serve --port 19402` | Starts, and prints the "No tenant is configured" warning with the remedy — the fix for one of the two release blockers this QA pass exists because of. |
| OPS-085 | Nothing listening | `prama serve --port 19403` twice, concurrently | The second fails with an address-in-use error. Record whether it is a refusal with a remedy or a raw `OSError`. |
| OPS-086 | Prepared database | `prama serve --port 0` | Binds an ephemeral port. Record whether the printed URL says `:0` — if it does, the printed URL is wrong and unusable. |
| OPS-087 | Prepared database | `prama serve --host 300.300.300.300 --port 19404` | A refusal. Record the shape. |
| OPS-088 | Prepared database | `prama serve --host 10.255.255.1 --port 19405` (an address this host does not own) | A refusal naming the bind failure. |
| OPS-089 | Server running | `kill -TERM <pid>` | Exits within the shutdown grace, with a zero or conventional exit status, and releases the port. |
| OPS-090 | Server running | `kill -INT <pid>` | Same. |
| OPS-091 | Server killed with SIGTERM | Inspect the sqlite directory | No stale `-wal`/`-shm` left in a state that blocks a restart; the database opens cleanly. |
| OPS-092 | Server killed with SIGKILL mid-write | Restart | Recovers from the WAL. |
| OPS-093 | One server running on a sqlite database | Start a **second** server on the same database, different port | Record what happens. SQLite WAL permits multiple readers and one writer; two processes both believing they own the schema is the interesting case. |
| OPS-094 | Two servers on one database | `GET /api/v1/health` on both | Both answer. |
| OPS-095 | Server running | `chmod 000` the sqlite file, then `GET /api/v1/health` | Health must report unhealthy, not 200-OK-with-a-lie. This is the case that decides whether the health endpoint is load-bearing. |
| OPS-096 | Server running | `mv` the sqlite file away, then `GET /api/v1/health` | Same expectation. |
| OPS-097 | Server running | Restore the file, `GET /api/v1/health` again | Recovers without a restart, or says clearly that a restart is needed. |
| OPS-098 | Server running | `GET /api/v1/docs` and `GET /api/v1/openapi.json` | Both answer; the OpenAPI version matches `VERSION`. |

---

## Section 6 — Backup, restore, upgrade (OPS-099 … OPS-106)

| # | Given | When | Then |
|---|---|---|---|
| OPS-099 | The whole documentation corpus | `grep` for a documented backup procedure across `README.md`, `QUICKSTART.md`, `docs/operations/`, `deploy/` | There is one, or there is not. If there is not, that is a finding: a product whose thesis is *immutable evidence a regulator will read* and which has **no migrations** has made backup the only recovery mechanism it owns. |
| OPS-100 | Same | `grep` for a documented upgrade path between versions | There is one, or there is not. With no migrations, upgrading across a `SCHEMA_VERSION` bump is exactly the operation that needs a written procedure. |
| OPS-101 | Server running, writes happening | `cp` the sqlite file (naive file copy, no `.backup`) | Record whether the copy is usable. A naive copy of a WAL database mid-write is the classic way to get a torn backup; whether the product warns about this is the finding. |
| OPS-102 | Server stopped | `cp` the sqlite file, restore it over a fresh location, start a server against it | Works; the estate is intact. |
| OPS-103 | Server running | `sqlite3 … ".backup"` — the correct online backup | Works and produces a verifiable database. |
| OPS-104 | A backup taken with the server running | `prama db verify` against the restored copy | No drift. |
| OPS-105 | A database created by this build | Change `SCHEMA_VERSION` expectations (read-only inspection of how the recorded digest is stored) | The product records what it applied, so a future build can tell it is looking at an older schema. |
| OPS-106 | `deploy/` | Read `deploy/README.md` and the Helm chart for operational guidance: persistence, backup, upgrade strategy | Record what an operator deploying to Kubernetes is told. |

---

## Section 7 — Offline / air-gapped bundle (OPS-107 … OPS-118)

| # | Given | When | Then |
|---|---|---|---|
| OPS-107 | A staged directory with a few files | `prama bundle seal ./offline` | Writes `manifest.json` and `manifest.sig`; reports file count, bytes, content hash, SBOM size. Exit 0. |
| OPS-108 | No session secret configured | `prama bundle seal ./offline` | Refuses — the seal is HMAC'd with the session secret (`_key` calls `require_secret`). Record whether the refusal names the fix. |
| OPS-109 | A sealed bundle | `prama bundle verify ./offline` | Exit 0, and says what it checked. |
| OPS-110 | A sealed bundle, one **file body** modified | `prama bundle verify ./offline` | Exit **3**, naming the file. The CLI reference and `bundle.py` both state 3 = must not be installed. |
| OPS-111 | A sealed bundle, one file **removed** | `prama bundle verify ./offline` | Exit 3, naming the missing file. |
| OPS-112 | A sealed bundle, one file **added** | `prama bundle verify ./offline` | Exit 3 — an unlisted file in a bundle is exactly what an attacker adds. Record if it passes instead. |
| OPS-113 | A sealed bundle, `manifest.json` edited to match a tampered file | `prama bundle verify ./offline` | Exit 3 — the HMAC seal over the manifest must fail even though the manifest is self-consistent. |
| OPS-114 | A sealed bundle, `manifest.sig` deleted | `prama bundle verify ./offline` | A refusal, exit non-zero. |
| OPS-115 | A directory with no manifest | `prama bundle verify ./notabundle` | The named refusal: "there is no manifest.json in …". |
| OPS-116 | An Ed25519 key pair | `prama bundle seal ./offline --sign-with key.pem` then `prama bundle verify ./offline --publisher-key pub.pem` | Signature verifies. |
| OPS-117 | A bundle signed by key A | `prama bundle verify ./offline --publisher-key <key B public>` | Exit 3. A wrong publisher key must fail, and this is the case that proves the signature is checked rather than merely present. |
| OPS-118 | Installed | `prama bundle sbom` | Lists the dependency set. |

---

## Section 8 — Evidence verification without Prama (OPS-119 … OPS-122)

The runbook tells an auditor to run `scripts/verify_evidence.py`, which
"imports nothing from this product and nothing outside the standard library",
with exit codes 0/1/2. An auditor is an operator too.

| # | Given | When | Then |
|---|---|---|---|
| OPS-119 | The script | `python3 -c "import ast; …"` — static check that it imports only the standard library and nothing from `prama` | True. If it imports anything of ours the promise is void. |
| OPS-120 | An evidence bundle produced by a case study | `python3 scripts/verify_evidence.py <bundle>` | Exit 0. |
| OPS-121 | The same bundle, one record's content altered | Re-run | Exit 1, naming the record and the check. |
| OPS-122 | A directory that is not a bundle | Re-run | Exit 2 — "the bundle could not be read", distinct from 1. |

---

## Section 9 — Resource behaviour (OPS-123 … OPS-128)

Not a benchmark. The question is only whether anything is pathological.

| # | Given | When | Then |
|---|---|---|---|
| OPS-123 | Installed | `prama db init` on a fresh database, timed | Completes in a time an operator would accept; record peak RSS. |
| OPS-124 | Installed | `prama version`, timed | CLI start-up cost. A CLI that takes seconds to print a version string is a CLI nobody scripts. |
| OPS-125 | Installed | `prama bench run --seed 42`, timed, with peak RSS | Completes. Record time and memory. |
| OPS-126 | Installed, a case study's data | `prama control run --against <db>` over the case-study estate | Record time and memory. |
| OPS-127 | A staged bundle of ~200 MB | `prama bundle seal` then `verify`, timed with peak RSS | Does not read the whole bundle into memory. |
| OPS-128 | Server running | 200 sequential `GET /api/v1/health` | No leak visible in RSS; latency stable. |

---

## Section 10 — Cross-cutting operator sanity (OPS-129 … OPS-134)

| # | Given | When | Then |
|---|---|---|---|
| OPS-129 | Installed | `prama` with no arguments | Prints help, exit **2** (`EXIT_USAGE`), per the CLI reference's uniform exit codes. |
| OPS-130 | Installed | `prama nosuchcommand` | Exit 2 with a usage error. |
| OPS-131 | Installed | `prama db` with no subcommand | Exit 2 and a usage line. |
| OPS-132 | Installed | `prama --json db info` on a broken database | The error is emitted as JSON, not as text on stderr — the CLI base promises this. |
| OPS-133 | Installed | `prama --log-level DEBUG db info` | Debug logging appears and does not leak a secret. |
| OPS-134 | Installed | `prama --json config show \| python -c "import json,sys; json.load(sys.stdin)"` | Valid JSON on stdout with nothing else mixed in — the property a script depends on. |

---

## What this plan deliberately does not cover

* **The console's screens.** A separate surface with its own pass.
* **PQL semantics, control verdicts, evidence content.** Also separate.
* **A real air-gapped host, a real Kubernetes cluster, a real cloud KMS.**
  `docs/corpus/19` and the runbook §8 already say these are unexercised; this pass can
  confirm the *commands* behave, not that a disconnected install succeeds.
* **Performance targets.** Section 9 looks for pathology, not for a number.

---

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
