# Prama — working notes

Prama is a business-owned, evidence-first data quality control plane. The design corpus is
`docs/00`–`docs/19`; `docs/03` (business semantic layer) is the conceptual heart and `docs/19` is
the implementation roadmap. Version is `src/prama/version.py::VERSION` — that constant is the only
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

### 6. AI never adjudicates.

No code path may allow a model output to determine a pass/fail verdict on data (`CON-007`,
`NFR-AI-002`). Models author, rank, explain, calibrate and summarise. A deterministic, versioned
engine decides. `tests/architecture/test_no_model_verdicts.py` guards this.

---

## Git drill

Work lands on `develop`; `main` moves only at the end of a wave.

```
# during a wave — freely
git commit && git push origin develop

# at the end of a wave — once
git checkout main && git merge --no-ff develop && git push origin main
git checkout develop && git merge main && git push origin develop
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
uv venv --python 3.13 && uv pip install -e ".[dev]"   # the interpreter is pinned in .python-version
pip install -e ".[dev]"                  # or plain venv, if the interpreter is already right
pytest -q                                # full suite
pytest -q tests/architecture             # layering, file length, no-model-verdict guards
prama config show                        # effective merged configuration, secrets redacted
prama control check suite.pql            # parse, type-check and lint; non-zero on error
prama control explain suite.pql          # each control as a sentence a data owner reads
prama control compile suite.pql --fuse   # the SQL that will run, grouped into shared scans
prama control functions                  # pushdown coverage: what runs on which engine
prama control import schema.yml --from dbt   # and what did not come across
prama tenant create acme-bank            # the estate; prints the id to configure
prama principal create alice --admin     # somebody who can sign in (password prompted)
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
prama lsp catalogue --out cat.json       # export the estate's schemas for an editor
prama lsp serve --catalogue cat.json     # PQL language server on stdio
python scripts/check_file_length.py      # the 1500-line ceiling
python3 scripts/verify_evidence.py bundle/   # check evidence without importing Prama
prama bundle seal ./offline --sign-with k.pem  # Ed25519 provenance for an air-gapped host
pytest -q tests/web/test_axe.py           # axe-core in Chrome; needs pip install -e ".[audit]"
pytest -q tests/security/test_oidc.py     # ID-token forgeries; needs pip install -e ".[sso]"
ruff check src tests && ruff format --check src tests
mypy src
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
uv pip install -e ".[dev,serve,postgres,fast,audit,sso]"
```

The suite passes on 3.13 and on 3.14 — both were run before choosing, and every
dependency has wheels for both. The pin exists so that *which* one is in use is
a decision recorded in the repository rather than a consequence of the last
`apt upgrade`.

**Dependency floors have no ceilings.** Every requirement in `pyproject.toml` is
a `>=`, so a rebuild floats to the newest release of everything. Rebuilding on
3.14 pulled mypy 2.3, pytest 9.1 and starlette 1.6 in one step and the gate
stayed green — that was luck, not design. A lock file is the thing that would
make it not luck.
