<!--
Prama — Quick Start.
Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary. No licence is granted except by separate written agreement.
-->

# Prama — Quick Start

**Declare it. Prove it. Trust it.**

From a fresh clone to the console, in about two minutes. Every command below was
run against this repository before it was written down; where a step can fail,
what it looks like when it fails is shown too.

---

## 0. What you are about to start

Two things, in one process:

| | Where | Who it is for |
|---|---|---|
| **The front door** | `http://127.0.0.1:5900/` — landing page, `/help`, `/about` | Anybody, signed in or not |
| **The console** | `http://127.0.0.1:5900/estate` | People — business owners, stewards, architects |
| **The API** | `http://127.0.0.1:5900/api/v1` (docs at `/api/v1/docs`) | Programs |

5900 is `server.port`; change it there (or pass `--port`), not in several places.

### From another machine

The server binds every interface (`server.host: 0.0.0.0`), so a phone or a
colleague on the same network opens it at `http://<this machine's address>:5900`;
`prama serve` prints that address beside the loopback one. Two consequences:

- **Anybody who can reach the machine can reach the sign-in page.** To keep it
  on this machine only, set `server.host: 127.0.0.1`.
- **Signing in from another machine over plain `http` needs
  `security.cookies_https_only: false`** in `config/application.local.yaml`, or
  TLS in front. The session cookie is secure-only by default, and browsers keep
  such a cookie only for `https` and for `localhost`, so without one of those the
  sign-in page simply returns.

They are one application deliberately, not two that share a database: a console
and an API that could disagree about the estate would eventually disagree about
whether a control passed.

---

## 1. Install

### Which Python

| | Version | Where it is stated |
|---|---|---|
| **Required** | **3.12 or newer** | `requires-python` in `pyproject.toml`, and in the SDK, kernel and agent packages |
| **Developed and pinned** | **3.13** | `.python-version`, which `uv venv` reads; the Docker image uses the same |
| **Tested** | 3.12, 3.13 and 3.14 | the whole suite, on each |

3.12 is the floor for a correctness reason, not a stylistic one. SQLite reads a
double-quoted column name it cannot find as a *string*, so a control on a
misspelled column would test a constant and pass every row. Prama switches that
off on every SQLite connection that runs a control, and the switch
(`Connection.setconfig`) only exists from Python 3.12. On an older interpreter
Prama refuses the connection rather than trusting it.

The interpreter is pinned, and deliberately not the operating system's: an
Ubuntu upgrade removed this project's Python once already, mid-build, and took
the virtual environment with it.

```bash
# One-time: a Python that apt cannot delete
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env
uv python install 3.13

# The project
uv venv --python 3.13
uv sync --extra dev --extra serve
source .venv/bin/activate        # every command below assumes this
```

`uv sync` installs exactly what `uv.lock` pins — the set the gate last ran green
on, rather than whatever released this morning. It also removes anything outside
the extras you name, which is what makes it reproducible; to *add* an extra to
an environment you already have, use `uv pip install -e ".[postgres]"` instead,
as the PostgreSQL section below does.

Plain `pip` works too, if the interpreter on your PATH is already 3.12 or newer.
`pip` cannot read `uv.lock`, so the same pins are exported for it:
`requirements.txt` (the server and console) and `requirements-dev.txt` (plus the
tests and linters). They are generated from the lock by
`scripts/export_requirements.py`, and the gate refuses a copy that has drifted.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt          # or requirements.txt to only run it
```

Check it:

```bash
prama version                    # or python -m prama version: the same CLI
```

Every extra (`serve`, `postgres`, `sso`, `kafka`, `audit`, …) is listed in
`pyproject.toml`; a feature that needs one you have not installed refuses by
name (§7).

---

## 2. Run it

```bash
python run_prama_web.py --prepare
```

`--prepare` applies the schema and creates an estate before starting. Leave it
off once both exist. `--reload` restarts the server on every source change, for
development; it reads configuration files and the environment, not `--set`.

```
   ___
  | _ \_ _ __ _ _ __  __ _     Prama 0.1.0
  |  _/ '_/ _` | '  \/ _` |    Declare it. Prove it. Trust it.
  |_| |_| \__,_|_|_|_\__,_|

  schema applied · estate acme-bank · 01M249QPWYQF653C699XYJWY65

  Console  http://127.0.0.1:5900/estate
  API      http://127.0.0.1:5900/api/v1
  Docs     http://127.0.0.1:5900/api/v1/docs
```

Open the console URL.

### It will refuse the first time

```
  security.session_secret is empty, and Prama will not start without it.
  Run once with --init-secret, or export PRAMA_SECURITY__SESSION_SECRET.
```

**This is the intended behaviour, not a defect.** The shipped
`config/application.yaml` is tracked by git and its session secret is empty on
purpose, so that no installation can ever run on a key that is public in the
source. Fix it once:

```bash
python run_prama_web.py --init-secret --prepare
```

That writes a generated secret into `config/application.local.yaml`, which is
git-ignored. The pre-commit hook refuses a non-empty secret in a tracked file,
so you cannot commit one by accident.

For a container or a CI job, use the environment instead — nothing is written to
disk:

```bash
export PRAMA_SECURITY__SESSION_SECRET="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"
```

### Signing in

**A fresh installation has one account: `admin`, password `prama-dev-admin`.**
It is created the first time the server starts against an estate with nobody
in it, and every page then carries a banner until the password is changed
(user menu → **Change password**). `/metrics` reports
`prama_default_admin_password 1` while it has not been. Outside development
(`app.environment` other than `development` or `test`) the server refuses to
start while the default is still in force, unless
`security.allow_default_admin_password: true` says so knowingly. Set
`security.bootstrap_admin: false` to create nobody.

The console is readable without signing in when `tenancy.default_tenant` is
set — that is how the case studies and a first evaluation run. To attribute
approvals, suppressions and attestations to a person rather than to the
deployment, create one:

```bash
prama principal roles                       # what each built-in role may do
prama principal create alice --admin --name "Alice Chen"
prama principal list
```

The password is prompted for, never passed as an argument: an argument lands in
your shell history and in the process table, where every other user on the
machine can read it. A provisioning script pipes it instead:

```bash
printf '%s' "$PASSWORD" | prama principal create svc-loader --role steward
```

Then sign in at `/sign-in`. The user menu (the avatar, top right) and, for an
`admin`, the **Admin** menu are explained in the console under **Help → Accounts,
roles and sign-in** and **Help → API keys**; every page also has an **About this page**
note at its foot.

### Make the estate stick

`--prepare` names its estate for that run only. To keep it, put the id the
runner printed into `config/application.local.yaml`:

```yaml
tenancy:
  default_tenant: 01M249QPWYQF653C699XYJWY65
```

Then `python run_prama_web.py` on its own is enough.

Without it, every console page asks you to sign in first — as `admin` on a
fresh installation, above.

---

## 3. The same thing, one step at a time

`run_prama_web.py` is a convenience. Everything it does is a command, and on a
real deployment you would run these separately — the schema from a change
ticket, the estate once, the server from a unit file.

```bash
prama db init                                  # apply schema/<dialect>.sql, idempotent
prama tenant create acme-bank --name "Acme Bank"
# put the printed id in config/application.local.yaml, then:
prama serve --host 0.0.0.0 --port 5900
```

Useful neighbours:

```bash
prama config show          # the effective merged configuration, secrets redacted
prama db verify            # fail loudly if the live schema has drifted
prama db info              # which database is configured, and what is in it
prama tenant list          # the estates, with the configured one marked
```

Prama has **no migrations, by design.** `schema/sqlite.sql` and
`schema/postgres.sql` are the authority; `db init` only ever creates what is
missing, and `db verify` reports drift rather than repairing it.

---

## 4. See it actually do something

An empty console is honest but not persuasive — it has nothing to report because
nothing has run. The case studies build a realistic banking estate and drive **the
Prama you are running** through the Python SDK, so the evidence lands in your console.

```bash
python run_prama_web.py                  # the server, if it is not already running
cd case-studies/01-trading-book-sqlite
python run.py
```

That seeds a trading book in SQLite with known defects, signs in to your server (as
`admin` / `prama-dev-admin` unless told otherwise), creates an estate for the run, declares
it, derives the controls from the declarations, and has the server run them. It prints what
it planted against what it caught, what it did **not** catch, and where to look in the
console: sign in to the run's estate (the form asks which, once there is more than one).

There are eight studies, each an estate of its own, so they can run one after another or at
once against the same server. **[case-studies/README.md](case-studies/README.md)** lists them,
and says how a study finds your server and which data the server may read; the console shows
the same under **Help → Case studies**. The SDK they use is yours to script with:
[docs/sdk](docs/sdk/README.md).

---|---|---|
| 1 | `01-trading-book-sqlite` | The whole loop on one source |
| 2 | `02-feeds-csv-parquet` | Arrival, and content in CSV, Parquet and JSON Lines feeds |
| 3 | `03-mixed-estate` | Relationships: defects no single dataset can see |
| 4 | `04-expressions-and-plugins` | Excel formulas, and a third-party validator |
| 5 | `05-dq-delegates` | Python checks named from PQL, one run on a remote agent |
| 6 | `06-month-end-close` | `RECONCILE` with currencies and a timing offset |
| 7 | `07-metadata-governance` | Rules from metadata, correlation, fitness search |
| 8 | `08-code-to-impact` | Lineage from ETL code, and a defect's blast radius |

Each run is an estate of its own on your server, so all eight can run one after another, or at
once, against the same server. The console lists them under **Help → Case studies**, one card
per study with its README.

---

## 5. Writing a control

The console has a studio at `/controls/studio`, and the same three answers are
available from the terminal:

```bash
prama control check   suite.pql   # parse, type-check and lint; non-zero on error
prama control explain suite.pql   # each control as a sentence a data owner reads
prama control compile suite.pql   # the SQL that will run, and what it does NOT test
```

A control looks like this:

```
CHECK positions_eod HAS UNIQUE KEY (account_id, instrument_id, as_of_date)
  SEVERITY critical
  DIMENSION uniqueness
  BECAUSE 'one position per account per instrument per business day'
```

`compile` is the one worth running before you trust anything. When the generated
SQL applies a *screen* rather than the exact test, it says so — and a violation
count from a screen is a **lower bound**, never a pass.

For an editor outside the console:

```bash
prama lsp catalogue --tenant acme-bank --out cat.json   # the estate's schemas
prama lsp serve --catalogue cat.json    # language server on stdio
```

---

## 5a. The banking pack

Prama ships a domain pack for banking. It is inspectable from a terminal without
a database, because a pack nobody can audit is a pack nobody should trust:

```bash
prama pack list          # calendars, cross-field checks, message formats, obligations
prama pack claims        # and what it deliberately does NOT claim to discharge
prama pack calendar TARGET2 --year 2030      # closures, computed from rules
prama pack reconciliation cashbook-to-statement   # keys, tolerance, expected breaks
prama pack parse order.fix   # one FIX/ISO 8583/FpML message, and its defects
prama pack concepts          # the banking business concept model
prama pack recognise account_id balance_date bal_type balance ccy   # -> Balance
```

`claims` is the one worth reading first. It separates the BCBS 239 principles
the pack discharges *with controls* from the ones it merely supports — because a
pack that listed only what it covers invites you to assume the rest.

The pack gives PQL the cross-field checks a column-by-column tool cannot reach:

```pql
CHECK pacs008 SATISFIES IBAN_BIC_CONSISTENT(creditor_iban, creditor_bic)
CHECK ledger  SATISFIES MINOR_UNITS_OK(amount, currency)
CHECK trades  SATISFIES SETTLES_AFTER_TRADE(trade_date, settlement_date)
```

Every one of those passes every single-field validator in the product, which is
exactly why they are worth having.

---

## 5b. Data contracts and CI

```bash
prama contract import contract.yaml            # ODCS in, saying what did not come across
prama contract check contract.yaml --data rows.json   # gate a build
prama contract diff before.csv after.csv --key id     # what changed, not how many
```

`check` is built for a pipeline and the exit code is the interface:

| Code | Meaning |
|---|---|
| `0` | the contract holds |
| `3` | the contract is breached |
| `1` | the check could not be made |

Three rather than two, so a build can tell *"your change broke the contract"*
from *"the checker fell over"*. An empty data file is a **breach**, not a pass —
a check over no rows passes every test it can run and has established nothing.

---

## 6. Configuration

Five sources, later winning: built-in defaults → `config/application.yaml`
(tracked) → `config/application.local.yaml` (git-ignored) → environment →
`--set key=value` on the command line.

Environment variables use `PRAMA_` and `__` for nesting:

```bash
PRAMA_DATABASE__DIALECT=postgres
PRAMA_SECURITY__SESSION_SECRET=...
PRAMA_TENANCY__DEFAULT_TENANT=01M2...
```

To use PostgreSQL instead of SQLite:

```yaml
database:
  dialect: postgres
  postgres:
    host: localhost
    database: prama
```

```bash
uv pip install -e ".[postgres]"     # plain pip: pip install -e ".[postgres]"
prama db init
```

`prama config show` prints the merged result with secrets redacted, which is the
fastest way to find out why a setting is not taking effect.

---

## 7. When something is wrong

| What you see | What it means |
|---|---|
| `security.session_secret is empty` | Working as designed. §2. |
| Every page redirects, console is unreachable | No `tenancy.default_tenant`. §2. |
| `authoritative schema file not found` | Run from the repository root, or set `database.schema_dir`. |
| `SchemaDriftError` on start | The live database no longer matches the schema file. `prama db verify` names every difference. Prama will not migrate it for you. |
| Console loads but every screen is empty | Nothing has run. That is a different fact from "nothing is wrong", and the screens say which. Try a case study (§4). |
| `there is already a tenant called …` | You are pointed at a different database than you think. The environment variable is `PRAMA_DATABASE__SQLITE__PATH` — double underscores between path segments. `PRAMA_DATABASE__PATH` is not a setting and is silently ignored. |
| A named refusal mentioning an *extra* | An optional dependency is not installed — `sso`, `kafka`, `rest`, `audit`. It refuses by name rather than falling back to something weaker. |

More of these, and the reasoning behind them, in
[`docs/operations/troubleshooting.md`](docs/operations/troubleshooting.md).

---

## Where to read next

**Running it**

* [`docs/operations/`](docs/operations/) — the operations index, and the shape of a Prama incident
* [`docs/operations/runbook.md`](docs/operations/runbook.md) — when something is wrong in production
* [`docs/operations/troubleshooting.md`](docs/operations/troubleshooting.md) — errors that mean something other than they say
* [`docs/operations/cli-reference.md`](docs/operations/cli-reference.md) — every command and flag, generated from the parser
* [`docs/operations/configuration-reference.md`](docs/operations/configuration-reference.md) — every setting and its default

**Understanding it**

* [`README.md`](README.md) — what Prama is, and the claim it makes falsifiable
* [`docs/corpus/03-business-semantic-layer.md`](docs/corpus/03-business-semantic-layer.md) — the conceptual heart
* [`docs/corpus/07-rule-language-spec.md`](docs/corpus/07-rule-language-spec.md) — PQL in full
* [`docs/corpus/19-implementation-roadmap.md`](docs/corpus/19-implementation-roadmap.md) — what is built and what is not
* [`CLAUDE.md`](CLAUDE.md) — the rules this codebase is held to

Every design document in `docs/` opens with an **As built** section saying how
much of it exists. Where a document and the code disagree, `docs/corpus/19` decides.

---

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Prama is proprietary and confidential. No licence is granted except by separate
written agreement.
