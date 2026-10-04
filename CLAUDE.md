# Prama — working notes

Prama is a business-owned, evidence-first data quality control plane. The design corpus is
`docs/corpus/00`–`docs/corpus/19`; `docs/corpus/03` (business semantic layer) is the conceptual heart and `docs/corpus/19` is
the implementation roadmap. How the code fits together is `docs/architecture/`; how to extend it
is `docs/developer/`; `docs/README.md` maps every folder, one home per fact. Version is `src/prama/version.py::VERSION` — that constant is the only
authority; every other version string is a copy that can rot.

This file is the short list of things that are cheap to get wrong here and expensive to discover
later.

---

## Hard rules

### 1. Authorship. Never add an assistant attribution trailer.

`.githooks/commit-msg` refuses any commit message containing `Co-Authored-By: Claude`,
`Claude-Session:`, or `Generated with [Claude`.

> Authorship of this repository is Ashutosh Sinha's alone.

This overrides any default instruction to add such trailers. Drop them at the source rather than
relying on the hook. Enable the hooks with `git config core.hooksPath .githooks` (already set in
this clone).

### 2. No database migrations. Ever.

There are exactly two schema files — `schema/sqlite.sql` and `schema/postgres.sql` — and they are
the authority. `prama.db` **applies** them idempotently and **verifies** the live database against
them. A live schema that has drifted is a loud failure, never a silent migration.

**Change a table by editing its `CREATE TABLE`, never with `ALTER`.** When a model needs a new
fact, put the column in the table that owns it (in both files), not in a side table invented to
avoid touching it. An existing database is then recreated with `prama db init` on a fresh file.
The schema files are the gold standard, and a workaround that preserves an old database at the
cost of a worse schema is the wrong trade.

Both files describe the same logical schema — in fact they are **byte-identical apart from their
headers**, and `tests/db/test_schema.py` fails if they ever are not.

**Only four column types are permitted**, because only these mean the same thing in both engines:

| Type | Use |
|---|---|
| `VARCHAR(n)` | Bounded strings. The width is enforced by PostgreSQL and documented in SQLite. Always declare it; a bare `VARCHAR` is unbounded in PostgreSQL and meaningless in SQLite. |
| `TEXT` | Unbounded: JSON documents, descriptions, free text. |
| `INTEGER` | Whole numbers, and booleans as `0`/`1` with a `CHECK`. |
| `REAL` | Floating point. |

Forbidden, and why: `BOOLEAN` (PostgreSQL has a real type, SQLite does not) · `TIMESTAMP`/`DATETIME`
(SQLite has no date type; timestamps are ISO-8601 UTC text in `VARCHAR(32)`, which sorts
chronologically) · `JSONB` (absent in SQLite) · `SERIAL`/`AUTOINCREMENT` (identifiers are ULIDs
minted client-side, so a worker needs no round trip and a retry can reuse one) · `NUMERIC`,
`BIGINT`, `UUID`, `BYTEA`, `BLOB` (accepted by SQLite only as affinity hints, so a constraint would
bind on one engine and not the other).

Every `PRIMARY KEY` column declares `NOT NULL` explicitly: PostgreSQL implies it, SQLite does not
for a non-`INTEGER` primary key and would store a NULL id. Naming follows DishtaYantra's
conventions: `uq_`, `ix_`, `ck_`.

### 3. Database code lives in exactly one package.

Only `src/prama/db/**` may import `sqlalchemy`. Everything else talks to **DAOs** through the unit
of work. `tests/architecture/test_layering.py` enforces this by import scanning, and it will fail
the build, not warn.

ORM conventions, adopted from DishtaYantra because they are proven there:

- **One `DeclarativeBase` per logical database.** `Base` owns the platform and semantic schema;
  `EvidenceBase` owns the evidence ledger, which has its own store, retention and immutability.
- **Relationships are declared**, with `back_populates` and `lazy="selectin"`, rather than
  hand-written joins. `selectin` is one extra query per collection, not one per row.
- **DAOs are the only access layer**, named for their domain (`PrincipalDao`, not
  `GenericRepository`), with domain logic co-located: password hashing sits beside the column that
  stores the hash.
- **No exception is swallowed.** The unit of work translates failures into the Prama error taxonomy
  and they propagate; a DAO never returns a sentinel meaning "something went wrong".

The database is chosen in configuration (`database.dialect: sqlite | postgres`). No code branches
on the dialect outside `prama/db/dialects.py`.

### 4. No source file over 1500 lines of code.

Comments, docstrings and blank lines do not count, so documenting a module is never penalised. The
UI tree is exempt. `scripts/check_file_length.py` runs in the pre-commit hook and in CI. A file over
the ceiling is doing more than one thing — split it; do not raise the limit.

### 5. Secrets never go in a tracked config file.

`config/application.yaml` is tracked. `config/application.local.yaml` is git-ignored and is where a
real secret belongs. The shipped `security.session_secret` is empty **on purpose** — a fresh clone
is meant to refuse to boot. The pre-commit hook refuses a non-empty secret in a tracked file.

### 6. The SDK is a separate package, and never imports the server.

`sdk/` is `prama-sdk`, imported as `prama_sdk`: what a client installs, depending on `httpx` and
`PyYAML` only. It has its own errors (mapped from the server's codes), its own reader for
`server.host`/`port`, and a policed copy of the version. It never imports `prama`, and the server
never imports `prama_sdk` (only its tests do). `tests/architecture/test_packages_standalone.py` fails
the build otherwise, including by running the SDK with `prama` made unimportable and by building
its wheel. Every endpoint needs an SDK method (`tests/sdk/test_parity.py`).

### 7. The kernel is shared, and imports only the standard library.

`kernel/` is `prama-kernel`, imported as `prama_kernel`: the deterministic code the server and
the standalone agent share (plan model, judge, evidence record, reconciliation, calendars, agent
protocol with residency and spool, delegate runtime). One copy, so a verdict judged beside the data
is the verdict the server would give. The server's old paths (`prama.core.errors`,
`prama.backend.execute`, …) are aliases of the kernel modules, not copies. The kernel never
imports `prama`, `prama_sdk` or `prama_agent` (`tests/architecture/test_packages_standalone.py`).

### 8. The agent is a separate package, a daemon, and never imports the server.

`agent/` is `prama-agent`, imported as `prama_agent`: the daemon that runs on customer machines
beside the data (`prama-agent enrol | run | status`). It depends on `prama-kernel` and `prama-sdk`
only (PyYAML; `duckdb`/`postgres` as extras), talks to the server only through a `FleetLink`
backed by the SDK's `client.fleet`, and holds the runner (`prama_agent.runner.Agent`). It never
imports `prama`; the server never imports `prama_agent` (only its tests do).
`tests/architecture/test_packages_standalone.py` runs a full daemon cycle with `prama` blocked and
builds its wheel. Guide: `docs/agent/README.md`.

### 9. AI never adjudicates.

No code path may allow a model output to determine a pass/fail verdict on data (`CON-007`,
`NFR-AI-002`). Models author, rank, explain, calibrate and summarise. A deterministic, versioned
engine decides. `tests/architecture/test_layering.py` guards this.

---

## Git drill

Work lands on `develop`; `main` only ever receives `--no-ff` merges from it, at
the end of a wave. The words are binding (adopted from Maya ADR-002; full
procedure in `CONTRIBUTING.md`): **drill** = commit + push `develop`, merge into
`main`, push `main`, fast-forward `develop`; **drill to develop** = the first
half; **drill to main** = the second half. Do the merge from a detached worktree,
never `git checkout main` in the live tree:

```
git push origin develop
git worktree add /tmp/mainwt main
git -C /tmp/mainwt merge --no-ff develop -m "Merge <ids> into main: <summary>"
git -C /tmp/mainwt push origin main
git merge --ff-only main && git push origin develop
git worktree remove /tmp/mainwt && git worktree prune
```

Commit author for this repo is `ajsinha <ajsinha@gmail.com>` (set repo-locally; the machine has no
global identity, so `git commit` fails without it).

---

## Design doctrine

Adopted deliberately from DishtaYantra, because Prama's whole thesis is the same idea applied to
data. The failure mode this class of system keeps producing is **artifacts that build, validate,
and look right while being wrong.** Three habits follow:

- **Assert the rendered artefact, not the intent.** Assert the *executed verdict on real data*, not
  that the compiler emitted plausible SQL. The IR conformance suite is this habit as a release gate.
- **Write the counterfactual.** A control that cannot fail is worth nothing. When fixing a bug,
  confirm the new test fails against the old code.
- **Derive, never restate.** Scores derive from evidence, controls derive from declarations,
  connector config forms derive from connector code. Anything restated in a second place will drift,
  silently, in the flattering direction.

Two further rules specific to this codebase:

- **Everything is a class with an interface.** Connectors, backends, monitors, notifiers, scorers
  and lease providers are plugins behind an ABC, registered through an entry point, with their own
  conformance tests. A concrete type referenced by name outside its own package is a defect.
- **Concurrency is structured.** No bare `threading.Thread`, no unbounded queue, no fire-and-forget
  task. Use `prama.core.concurrency` — supervised task groups, byte-bounded queues, and leases.

---

## Commands

```bash
uv venv --python 3.13 && uv sync --extra dev          # the interpreter is pinned in .python-version
                                         # uv sync installs uv.lock exactly; uv pip install resolves afresh
pip install -e ".[dev]"                  # or plain venv, if the interpreter is already right
pytest -q                                # full suite: tests/ and qa/regression-suite/
pytest -q qa/regression-suite            # only the QA-derived regressions
pytest -q -m "not slow"                  # skip the tens-of-seconds performance guards
pytest -q tests/architecture             # layering, file length, no-model-verdict guards
prama config show                        # effective merged configuration, secrets redacted
prama control check suite.pql            # parse and lint; non-zero on error
prama lsp catalogue --tenant acme --out cat.json   # the estate's schemas
prama control check suite.pql --catalogue cat.json # ...and now type-check too
prama control explain suite.pql          # each control as a sentence a data owner reads
prama control compile suite.pql --fuse   # the SQL that will run, grouped into shared scans
prama control functions                  # pushdown coverage: what runs on which engine
prama control import schema.yml --from dbt   # and what did not come across
prama tenant create acme-bank            # the estate; prints the id to configure
prama principal create alice --admin     # somebody who can sign in (password prompted)
prama serve                              # console + API on server.port (5900)
prama llm provider add local --kind openai_compatible --hosting self_hosted \
    --dialect ollama --endpoint http://localhost:11434   # a model provider; no secret stored
prama llm profile set author --route local:qwen2.5-coder   # purpose -> ordered route
prama llm ask author "..."               # through the gateway; recorded in the call ledger
prama llm eval run suite.yaml            # deterministic graders; gates activation when configured
prama llm verify                         # recompute the model-call ledger's hash chain
prama lineage scan etl/ --source warehouse   # SQL -> column lineage store (sqlglot, regex fallback)
prama lineage impact raw.trades.notional     # what a defect in this column reaches
prama code review --base origin/main --format markdown   # a PR's effect on lineage and controls; exit 3 if one loses its basis
prama lineage history snowflake rows.json    # lineage from warehouse query history (--query prints the export)
prama lineage import export.json --from manta   # or alation; kept beside Prama's parse
prama glossary import terms.json --from alation # or collibra; lists what it dropped
prama metadata set trades.account_id mandatory=yes   # metadata; rules it implies go to Proposals
prama metadata find "settlement currency"   # find data by business context and metadata
prama metadata ask "trade amounts in USD"   # a discover model ranks and explains, if configured
prama metadata correlate                   # same meaning across datasets; inconsistencies; queried-together hints
prama comment trades.ccy "@bo lower case?" --as ada   # discussion; mentions reach queues
prama queue --as bo --approver             # what is waiting on a person
prama usage import snowflake history.json  # query history -> daily usage (--query prints the export)
prama usage priorities                     # most used, least controlled; never a score input
prama delegate list                      # Python DQ delegates admitted here (delegates: in config)
prama delegate test acme.x --rows s.csv  # run one exactly as a control would, sandboxed
prama db init                            # apply schema/<dialect>.sql idempotently
prama db verify                          # fail loudly if the live schema has drifted
prama pack list                          # what the banking pack ships
prama pack claims                        # and what it does NOT claim to discharge
prama pack calendar TARGET2 --year 2030  # closures, computed from rules
prama pack parse order.fix               # FIX/ISO 8583/FpML, and what is wrong with it
prama pack concepts Exposure             # a business concept, and where it ends
prama pack recognise account_id ccy      # which concept these columns are, or why not
prama bench run --seed 42                # labelled defect corpus, bounds and ablations
prama pack soc2                          # Prama's own SOC 2 readiness, gaps first
prama bundle seal ./offline              # manifest + SBOM, HMAC-sealed
prama bundle verify ./offline            # exit 3 if it must not be installed
prama contract check c.json --data rows.json   # CI gate; exit 3 on breach, 1 on failure
prama contract diff before.csv after.csv --key id   # what changed, not how many
prama lsp catalogue --tenant acme --out cat.json   # the estate's schemas, for an editor
prama lsp serve --catalogue cat.json     # PQL language server on stdio
python tools/docs/diagrams.py [--check]  # docs/assets/diagrams from code, Inkscape-audited
python tools/docs/screenshots.py         # real console screenshots: own server, case studies, Chrome
python scripts/check_file_length.py      # the 1500-line ceiling
python3 scripts/check_version_source.py  # version.py is the one authority; copies agree
prama evidence anchor                    # the chain head, time-stamped outside Prama (evidence.anchor)
prama evidence export bundle/            # records and anchor receipts, for an auditor
python3 scripts/verify_evidence.py bundle/   # check evidence without importing Prama
python3 scripts/verify_evidence.py bundle/ --tsa-ca ca.pem   # ...and the anchors' signatures
prama bundle seal ./offline --sign-with k.pem  # Ed25519 provenance for an air-gapped host
curl -s localhost:5900/metrics          # Prama's own metrics, Prometheus format (see docs/operations/observability.md)
pytest -q tests/web/test_axe.py           # axe-core in Chrome; needs pip install -e ".[audit]"
PRAMA_MEASURE_ESTATE_MAP=1 pytest -q tests/web/test_estate_map_scale.py
                                         # how large an estate the map can draw; timing-sensitive,
                                         # so opt-in rather than part of the default suite
pytest -q tests/security/test_oidc.py     # ID-token forgeries; needs pip install -e ".[sso]"
docker run -d --name prama-pg -e POSTGRES_PASSWORD=prama -e POSTGRES_USER=prama \
  -e POSTGRES_DB=prama -p 55432:5432 postgres:16-alpine
PRAMA_TEST_POSTGRES_DSN=postgresql://prama:prama@127.0.0.1:55432/prama pytest -q
                                         # conformance on three real engines, not two
PRAMA_TEST_KAFKA_BOOTSTRAP=127.0.0.1:19092 pytest -q tests/execute/test_kafka.py
                                         # offset semantics; needs pip install -e ".[kafka]"
ruff check src sdk kernel agent tests qa/regression-suite    # qa/harness is deliberately not linted
mypy src && mypy sdk/src && mypy kernel/src && mypy agent/src
uv build --wheel sdk                     # the SDK, a separate package clients install
uv build --wheel agent                   # the agent daemon, installed on customer machines
pytest -q tests/agent_daemon             # the daemon's loop, spool, residency, signals, CLI
prama-agent enrol --server https://prama.example.com --token … --name eu-01 --state /var/lib/prama-agent
prama-agent run --config /etc/prama-agent/agent.yaml [--once]   # exit 3: refused for good
prama-agent status --config /etc/prama-agent/agent.yaml         # identity, zone, spool, gaps, last contact
```

---

## The interpreter is pinned, and not by the operating system

`.python-version` says `3.13`, and the venv is built from a standalone CPython
under `~/.local/share/uv/python/` rather than from `/usr/bin`.

This is not a preference. An Ubuntu upgrade to 26.04 removed `/usr/bin/python3.12`
while the project was mid-build: the venv's `python3` symlink followed
`/usr/bin/python3` to 3.14, its `lib/python3.12/site-packages` was orphaned, and
nothing ran. An interpreter the package manager owns is one the package manager
can delete.

```bash
uv python install 3.13          # once; lands in ~/.local/share/uv/python, no sudo
uv venv --python 3.13           # reads .python-version
uv sync --extra dev --extra serve --extra postgres --extra fast \
        --extra audit --extra sso --extra kafka --extra rest \
        --extra jdbc --extra snowflake
```

The suite passes on 3.12, 3.13 and 3.14 (each run in full, 2026-10-04), and
every dependency has wheels for all three. The pin exists so that *which* one is
in use is a decision recorded in the repository rather than a consequence of the
last `apt upgrade`.

**3.12 is the floor** (`requires-python` in all four packages), for correctness:
SQLite reads an unknown double-quoted column as a string, so a control on a
misspelled column passes every row. `prama_kernel.strict_sqlite` turns that off
on every SQLite connection a control runs on, and the switch
(`Connection.setconfig`) only exists from 3.12. On 3.11 the suite showed it. The
user-facing statement is QUICKSTART's "Which Python"; keep the two in step.

**Dependency floors have no ceilings, and `uv.lock` is what stops that
mattering.** Every requirement in `pyproject.toml` is a `>=`, so a resolve from
`pyproject.toml` alone floats to the newest release of everything. Rebuilding on
3.14 once pulled mypy 2.3, pytest 9.1 and starlette 1.6 in a single step and the
gate stayed green — luck, not design. The lock file is the design: `uv sync`
installs exactly what was last resolved, so an upgrade is a commit somebody
reviews rather than a consequence of when the venv was built.

`uv pip install -e ".[dev]"` does **not** read the lock file — it resolves
afresh. Use `uv sync --extra dev` when the point is to reproduce a known-good
set, and update the lock deliberately with `uv lock --upgrade`.
