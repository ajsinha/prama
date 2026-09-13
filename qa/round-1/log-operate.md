<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# QA execution log — installation, configuration and operation

Cases: [`cases-operate.md`](cases-operate.md), written before any of this ran.

**Executed:** 2026-09-12, 20:19–20:45 local.
**Build:** a fresh `git clone --branch develop` of this repository into
`/tmp/qa-operate/clone`, taken at 20:19. That clone holds **committed `develop`
only** — uncommitted working-tree changes belonging to other concurrent QA
passes are not in it, so every result below is a result about committed code.
`VERSION = 0.1.0`, `SCHEMA_VERSION = 1`.
**Host:** Linux 7.0.11-76070011-generic, Docker 29.8.0, uv-managed CPython
3.13.15 at `~/.local/share/uv/python/cpython-3.13.15-linux-x86_64-gnu`.
**Scratch:** `/tmp/qa-operate/`. Ports 19410–19441 and 19433 (PostgreSQL).

No file under `src/`, `tests/`, `schema/` or `config/` was modified. Everything
that needed a mutated schema, config or database operated on a copy under
`/tmp`.

---

## Summary first

| | |
|---|---|
| **Total cases** | 134 |
| **Passed** | 110 |
| **Failed** | 23 |
| **Blocked** | 1 |
| **Not run** | 0 |

**The five that matter most, in order:**

1. **OPS-016 — all four case studies crash.** `python run.py` dies with a
   `TypeError` in `case-studies/_common/harness.py`. Both `README.md` and
   `QUICKSTART.md` send a first-time reader here. Two distinct broken call
   signatures, one for studies 1–2 and one for 3–4.
2. **OPS-112 — `prama bundle verify` exits 0 on a bundle containing a file
   nobody signed for.** It *reports* the extra file and then does not say "do
   not install". A backdoored wheel dropped into a staged bundle passes.
3. **OPS-067 / OPS-082 — `prama db verify` does not detect an added column**,
   on SQLite or on PostgreSQL. An extra *table* is reported; an extra *column*
   is invisible. `ALTER TABLE tenant ADD COLUMN qa_sneaky` → "no drift".
4. **OPS-096 — `/api/v1/health` returns `200 {"status":"ok"}` after the SQLite
   database file has been deleted.** The Helm chart uses that endpoint as both
   liveness and readiness probe, with the comment "it either reaches its
   database or it does not".
5. **OPS-084 — `prama serve`'s startup banner and its "No tenant is
   configured" warning are never emitted when stdout is not a terminal** —
   i.e. under systemd, Docker or any supervisor. `run_prama_web.py` carries an
   explicit `sys.stdout.flush()` and a comment about exactly this problem;
   `prama serve` did not get the fix.

Plus two things that exist only as an error message: **`prama apikey create`**
(the remedy the API's own 401 prints — no such command exists, so the HTTP API
cannot be reached at all) and an **evidence-bundle export** (the runbook tells
an auditor to verify one; nothing produces one). Both under *Unplanned
observations*.

And one omission: **there is no documented backup procedure anywhere**
(OPS-099), in a product that has deliberately no migrations.

---

## Section 1 — A clean install, following the documentation literally

### OPS-001 — fresh clone inventory · **PASS**

```
$ git clone -q --branch develop /home/ashutosh/PycharmProjects/prama clone
$ ls config/
application.yaml
$ ls -d data
ls: cannot access 'data': No such file or directory
```

No `application.local.yaml`, no `data/prama.db`. `.gitignore` covers
`config/*.local.yaml`, `*.db` and `data/`. A "fresh clone" is reproducible, so
the rest of this section is testing the real thing.

### OPS-002 — `uv venv --python 3.13` · **PASS**

```
$ uv venv --python 3.13
Using CPython 3.13.15
Creating virtual environment at: .venv
Activate with: source .venv/bin/activate
real 0m0.060s
$ readlink -f .venv/bin/python
/home/ashutosh/.local/share/uv/python/cpython-3.13.15-linux-x86_64-gnu/bin/python3.13
```

Resolves under `~/.local/share/uv/python`, not `/usr/bin`, as `CLAUDE.md` and
`troubleshooting.md §Environment` require.

One note on the literal read: `uv` was not on `PATH` in this shell
(`uv: command not found`). QUICKSTART §1 does print `source ~/.local/bin/env`
as part of the one-time install block, so a reader who runs the block in order
is fine. Worked around with `export PATH="$HOME/.local/bin:$PATH"`.

### OPS-003 — `uv pip install -e ".[dev,serve]"` · **PASS**

Exit 0, `real 0m4.869s` against a warm uv cache; 60-odd wheels including
`pytest 9.1.1`, `sqlalchemy 2.0.52`, `starlette 1.6.0`, `uvicorn 0.52.4`.
Whether a cold cache needs the network is **unconfirmed** — this host had one.

### OPS-004 — `prama version` · **FAIL**

This is the first point at which a literal reader is stuck.

```
$ prama version
/bin/bash: line 1: prama: command not found
[exit=127]
```

QUICKSTART §1 reads, in order: `uv venv --python 3.13`,
`uv pip install -e ".[dev,serve]"`, then *"Check it:"* `prama version`. Nothing
between those steps activates the environment. `uv venv` prints
`Activate with: source .venv/bin/activate` as part of its own output, but the
document never repeats it — and the *plain-venv alternative immediately below*
does show `source .venv/bin/activate`, which makes the omission read as
deliberate rather than as a step the reader must supply. `README.md §Run it`
has the same shape: `uv venv && uv pip install`, then
`python run_prama_web.py`, with no activation.

Workaround used for the rest of this pass: `source .venv/bin/activate`.

```
$ .venv/bin/prama version
Prama 0.1.0 — Declare it. Prove it. Trust it.
  IR version:     0.1.0
  schema version: 1
[exit=0]
```

### OPS-005 — the launcher refuses without a secret · **PASS**

```
$ python run_prama_web.py --prepare
  security.session_secret is empty, and Prama will not start without it.
  Run once with --init-secret, or export PRAMA_SECURITY__SESSION_SECRET.

   ___
  | _ \_ _ __ _ _ __  __ _     Prama 0.1.0
  |  _/ '_/ _` | '  \/ _` |    Declare it. Prove it. Trust it.
  |_| |_| \__,_|_|_|_\__,_|
[exit=1]
```

The refusal is exactly the text QUICKSTART §2 promises, and it names the fix.
Cosmetic: the banner goes to stdout and the refusal to stderr, so when either
is redirected they arrive out of order, as above.

### OPS-006 — `--init-secret --prepare` · **PASS**

Deviation recorded: port 8080 was occupied on this host by an unrelated
process, so `--port 19410` was added. Nothing else changed.

```
$ python run_prama_web.py --init-secret --prepare --port 19410
   ___
  | _ \_ _ __ _ _ __  __ _     Prama 0.1.0
  |  _/ '_/ _` | '  \/ _` |    Declare it. Prove it. Trust it.
  |_| |_| \__,_|_|_|_\__,_|

  wrote a session secret to /tmp/qa-operate/clone/config/application.local.yaml
  schema applied · estate acme-bank · 01M2C26MZK9RJTEBGFB5DRH15G
  (created)

  Console  http://127.0.0.1:19410/estate
  API      http://127.0.0.1:19410/api/v1
  Docs     http://127.0.0.1:19410/api/v1/docs

  This run set tenancy.default_tenant for itself only. To make it
  stick, put it in config/application.local.yaml:
      tenancy:
        default_tenant: 01M2C26MZK9RJTEBGFB5DRH15G
```

`config/application.local.yaml` was written with a `token_urlsafe(48)` value
and a comment explaining why the file is git-ignored. Matches the documented
output line for line.

### OPS-007 — `GET /estate` · **PASS**

`http=200`, 9,925 bytes, `<title>Estate — Prama</title>`.

### OPS-008 — `GET /api/v1/health` · **PASS**

```json
{"status":"ok","version":"0.1.0","schema_version":"1","dialect":"sqlite","schema_file":"schema/sqlite.sql"}
```

### OPS-009 — `--init-secret` a second time · **PASS**

```
  /tmp/qa-operate/clone/config/application.local.yaml already sets session_secret
  Leaving it alone. Edit the file if you meant to change it.
[exit=1]
```

### OPS-010 — QUICKSTART §3, one step at a time · **PASS**

Against a clean database (`PRAMA_DATABASE__SQLITE__PATH=/tmp/qa-operate/step3/prama.db`):

```
$ prama db init
schema created: 35 tables, 99 statements from schema/sqlite.sql (digest 5df0746f832e)
[exit=0]
$ prama tenant create acme-bank --name "Acme Bank"
created Acme Bank (acme-bank)
  id: 01M2C285A0CHW55E9K1AKG1JE4
...
Then create somebody who can sign in:
  prama principal create <username> --admin --tenant acme-bank
[exit=0]
```

Run against the database `--prepare` had already populated, `tenant create`
refuses correctly and hands back the id:

```
error: there is already a tenant called 'acme-bank'
  code: ENTITY.CONFLICT
  next: Its id is 01M2C26MZK9RJTEBGFB5DRH15G. Use that, or choose a different slug.
```

The command `tenant create` prints at the end —
`prama principal create <username> --admin --tenant acme-bank` — now works
(OPS-013). The release blocker recorded in `docs/qa/README.md` is fixed.

### OPS-011 — the four "useful neighbours" · **PASS**

`config show`, `db verify`, `db info`, `tenant list` all exist and exit 0.
`tenant list` correctly says *"tenancy.default_tenant is not set, so the console
has no estate."*

### OPS-012 — every documented no-service command · **PASS**

All ran, exit 0: `pack list`, `pack claims`, `pack calendar TARGET2 --year 2030`,
`pack concepts Exposure`, `pack recognise account_id ccy`, `pack soc2`,
`pack parse` (on a hand-built FIX 4.4 message — it found the two deliberate
defects, body-length and checksum), `control functions` (33 functions;
sqlite 32/33, `ROUND` refused), `connectors`, `estate maturity`, `mcp tools`,
`bench taxonomy`, `control check|explain|compile --fuse`, `bundle sbom`.

Three observations from inside this case, all about **tenant resolution**, all
the same shape as the release blocker this QA pass was commissioned after:

```
$ prama principal list --tenant acme-bank
Nobody. Create one with `prama principal create <username> --admin`.
[exit=0]

$ prama principal list --tenant 01M2C285A0CHW55E9K1AKG1JE4
   alice                active     admin
[exit=0]
```

`principal create --tenant` accepts a **slug**; `principal list --tenant` does
not, and reports an empty estate rather than refusing. And an id that names no
tenant at all is never refused by anything:

```
$ prama principal list --tenant no-such-tenant     → "Nobody."           exit 0
$ prama estate maturity --tenant totally-made-up   → "estate: 0%"        exit 0
$ prama lsp catalogue --tenant totally-made-up     → "0 dataset(s)"      exit 0
$ prama estate diff --tenant <real> --dir /tmp/qa-operate/definitely-not-here
in sync: no drift between Prama and the repository                        exit 0
```

The last one compares against a directory that does not exist and reports "in
sync". For a product whose doctrine is that a check which cannot be made is a
refusal, four commands answering *"nothing is wrong"* about an estate or a
directory that does not exist is the flattering direction.

### OPS-013 — `principal roles` / `create` / `list` · **PASS**

`roles` prints the four built-ins and their scopes. `create` works. Password
policy enforced and well explained:

```
$ printf 'hunter2\n' | prama principal create svc-loader --role steward --tenant acme-bank
error: a password must be at least 12 characters
  code: INPUT.INVALID
  next: Length is the only property that reliably helps. Prama does not impose
        character-class rules: they demonstrably push people towards Password1!
        and away from anything longer.
```

The **interactive** prompt was not exercised (no TTY available in this
harness); `src/prama/cli/principal.py` uses `getpass.getpass` with a confirm
round, confirmed by reading, not by running. Recorded as unconfirmed.

A documentation-ordering note: QUICKSTART §2 places *"Signing in"* **before**
*"Make the estate stick"*, and `--prepare` sets `tenancy.default_tenant` for its
own run only. So a literal reader who has just run
`python run_prama_web.py --init-secret --prepare` and types the next printed
command in a second terminal gets:

```
error: no tenant to create this principal in
  next: Pass --tenant, or set tenancy.default_tenant. Create an estate first
        with `prama tenant create <slug>` if there is none.
```

A correct refusal with a correct remedy — but it is the documented next step
that produced it.

### OPS-014 — password on stdin, exactly as printed · **PASS**

```
$ PASSWORD='correct-horse-battery-staple'; printf '%s' "$PASSWORD" | prama principal create svc-loader --role steward --tenant 01M2C285A0CHW55E9K1AKG1JE4
created svc-loader
  id:    01M2C2A7XQAYN6SDVGQR854E9S
  roles: steward
```

No trailing newline required; nothing appeared in the process table.

### OPS-015 — CLI reference completeness · **FAIL**

`docs/operations/cli-reference.md` opens with: *"Every command Prama ships,
taken from the argument parser itself. If a flag is here it exists; if it is
not here it does not."*

Walking the parser tree and comparing against the document:

```
in doc but NOT in parser:  []          ← good
in parser but NOT in doc:
   ('', '--config')
   ('', '--json')
   ('', '--log-level')
   ('', '--set')
```

The four **global** options — the ones `src/prama/cli/base.py` describes as
inherited by every command *"so configuration is resolved identically no matter
which subcommand is invoked"* — appear nowhere in the reference. `--set` and
`--config` are the two an operator most needs, and `--json` is the whole
machine-readable contract.

This is not a stale file. The generator agrees the file is current:

```
$ python3 scripts/generate_docs.py --check
every generated document matches the code (2 checked)
[exit=0]
```

So the gate that is supposed to make the claim true cannot see the gap.

### OPS-016 — `cd case-studies/01-trading-book-sqlite && python run.py` · **FAIL**

The command both `README.md §Run it` and `QUICKSTART.md §4` give as the way to
"see it actually do something". It builds the data and declares the estate, then
dies at step 3:

```
$ python run.py --no-serve
  ... (steps 1 and 2 complete and look excellent) ...
──────────────────────────────────────────────────────────────────────────────
  3. Derive the controls (Γ), and accept them
──────────────────────────────────────────────────────────────────────────────
Traceback (most recent call last):
  File ".../case-studies/01-trading-book-sqlite/run.py", line 275, in <module>
    asyncio.run(main(serve=not args.no_serve, port=args.port))
  ...
  File ".../case-studies/_common/harness.py", line 152, in derive_and_accept
    version = await uow.datasets.require_current(dataset_id)
TypeError: VersionedDao.require_current() missing 1 required keyword-only argument: 'tenant_id'
[exit=1, wall=0.81s]
```

`src/prama/db/dao/versioned.py:243` reads
`async def require_current(self, entity_id: str, *, tenant_id: str) -> V:`.
The shared harness was not updated when the keyword became required.

All four studies are affected, in two distinct places:

```
01-trading-book-sqlite   exit=1  VersionedDao.require_current() missing 'tenant_id'
02-feeds-csv-parquet     exit=1  VersionedDao.require_current() missing 'tenant_id'
03-mixed-estate          exit=1  ControlDao.activate()        missing 'tenant_id'
04-expressions-and-plugins exit=1 ControlDao.activate()       missing 'tenant_id'
```

Nothing in `tests/` exercises `case-studies/`, which is why 4,000-odd green
tests do not see this.

---

## Section 2 — Configuration

### OPS-017 / OPS-018 — no config file at all · **PASS** / **PASS**

From `/tmp/qa-operate/nocfg`, an empty directory: `prama config show` prints the
full built-in default set, exit 0; `prama version` works. `load_configuration`'s
docstring — *"a fresh clone and a CI job both work with no file at all"* — holds.

### OPS-019 — `db init` from an empty directory · **PASS**

```
error: authoritative schema file not found: schema/sqlite.sql
  code: DB.SCHEMA_FILE_MISSING
  next: Prama has no migrations; this file is the schema. Restore it from the
        repository, or set database.schema_dir to where it lives.
  path: schema/sqlite.sql
[exit=1]
```

Named, with a remedy. Side note: it created an empty `data/` directory in the
cwd before failing.

### OPS-020 — shipped config, empty secret, launcher · **PASS**

Refuses. Same text as OPS-005.

### OPS-021 — shipped config, empty secret, `prama serve` · **PASS**

`serve` refuses too, and with the fuller CLI-shaped refusal:

```
error: security.session_secret is empty, and Prama will not start without it
  code: CONFIG.SECRET_MISSING
  next: Set security.session_secret in config/application.local.yaml
        (git-ignored), or export PRAMA_SECURITY__SESSION_SECRET. Never put it
        in a tracked file.
  key: security.session_secret
[exit=1]
```

Note the ordering: the URLs are printed **before** `create_app` runs, so on
stdout the operator sees `Console http://…/estate` and then, on stderr, the
refusal. Nothing was served.

### OPS-022 — headless (`web.enabled=false`) without a secret · **PASS**

Starts, by design (`api/app.py`: *"a headless deployment … should not be made to
hold a session secret it has no use for"*).

```
GET /api/v1/health → 200 {"status":"ok",...}
GET /estate        → 404
```

A clean 404, not a 500.

### OPS-023 — malformed YAML · **PASS**

```
error: invalid YAML in /tmp/qa-operate/badcfg/bad.yaml
  code: CONFIG.YAML_INVALID
  next: Fix the YAML syntax reported below and retry.
  detail: mapping values are not allowed here
  in "<unicode string>", line 3, column 14:
       bad_indent: x
                 ^
```

### OPS-024 — YAML whose top level is a list · **PASS**

`CONFIG.YAML_SHAPE`, `found: list`, `next: Wrap the document in key: value pairs.`

### OPS-025 — zero-byte YAML · **PASS** — treated as `{}`, exit 0.

### OPS-026 — string where an integer goes · **PASS**

`config show` displays the raw value (`database.pool.size 'not-a-number'`);
the refusal arrives at the point of use, typed:

```
error: configuration key database.pool.size is not a valid integer
  code: CONFIG.TYPE
  next: Provide a whole number, e.g. 20.
  wanted: integer
```

### OPS-027 — string where a boolean goes · **PASS**

```
error: configuration key database.verify_on_start is not a valid boolean
  code: CONFIG.TYPE
  next: Use true/false, yes/no, on/off or 1/0.
```

### OPS-028 — unknown top-level key · **PASS**

`nonsense: {a: 1}` is accepted silently **and shown**:
`prama config show` prints `nonsense.a  1`. Visible is enough.

### OPS-029 — misspelled known key · **FAIL**

```
$ prama --config misspelled.yaml db info      # file contains: databse: {dialect: postgres}
dialect:     sqlite
url:         sqlite+pysqlite:////tmp/qa-operate/cfg/data/prama.db
[exit=0]
```

The operator wrote `databse.dialect: postgres` and is running on SQLite. There
is no unknown-key validation, so a typo in a database-, security- or
residency-relevant key is silently inert. The only mitigation is that
`config show` echoes it (`databse.dialect  'postgres'` sitting one line above
`database.dialect  'sqlite'`) — which requires the operator to already suspect
the problem.

### OPS-030 — the secret key absent entirely · **PASS**

Identical refusal to "present but empty". Absent and empty do not differ.

### OPS-031 — explicitly named file that does not exist · **PASS**

`CONFIG.FILE_MISSING`, exit 1.

### OPS-032 — unsupported extension · **PASS**

`CONFIG.FORMAT_UNSUPPORTED: .txt`, `next: Use a .yaml, .yml or .properties file.`

### OPS-033 — `.properties` · **PASS**

`database.pool.size = 42` / `logging.level = DEBUG` expand to the same nested
shape (`database.pool.size '42'`, `logging.level 'DEBUG'`).

### OPS-034 — malformed `.properties` · **PASS**

`CONFIG.PROPERTIES_INVALID`, naming `bad.properties:2`.

### OPS-035 … OPS-039 — `--set` · **PASS** ×5

```
--set database.dialect=postgres                    → database.dialect 'postgres'
--set database.pool.size=99 --set logging.level=DEBUG → both applied
--set database.dialect      (no '=')               → CONFIG.CLI_INVALID, exit 1
--set a=1 --set a.b=2                              → CONFIG.KEY_CONFLICT, exit 1
--provenance:
  app.name           'Prama'    [config/application.yaml]
  database.dialect   'sqlite'   [config/application.yaml]
  database.pool.size '99'       [command line]
```

### OPS-040 / OPS-041 / OPS-043 — redaction · **PASS** ×3

A local config carrying `QA-SECRET-SENTINEL-…` and `QA-PGPASSWORD-SENTINEL-…`:

```
$ prama config show          → security.session_secret '***'  ·  0 sentinel hits
$ prama --json config show   → "security.session_secret": "***"  ·  0 sentinel hits
$ PRAMA_ALLOW_RAW_CONFIG=1 prama config show --raw
security.session_secret 'QA-SECRET-SENTINEL-aaaaaaaaaaaaaaaaaaaaaaaaaaaa'
! secrets were NOT redacted; do not paste this anywhere
```

`prama db info` also redacts inside a DSN it builds itself:
`postgresql+psycopg://prama:***@127.0.0.1:19433/prama`.

### OPS-042 — `--raw` without the environment variable · **PASS** (with a wording defect)

Still redacted, exit 0 — the safe outcome. But the flag's own help says
*"do not redact (refused unless PRAMA_ALLOW_RAW_CONFIG=1)"*, and it is not
refused, it is **ignored**. An operator who types `--raw`, sees `***`, and
concludes the value really is `***` is the failure mode.

Redaction is also a fixed 15-name allowlist (`core/log.py::SENSITIVE_KEYS`):

```
security.oidc.client_secret   '***'
warehouse.api_key             '***'
warehouse.pat                 'QA-PAT-SENTINEL'                       ← shown
database.postgres.dsn         'postgresql://prama:QA-DSN-SENTINEL@…'  ← shown
```

`troubleshooting.md §Getting a useful bug report` says *"`prama config show` —
secrets are redacted, so this is safe to paste"*, unconditionally. The
mechanism is name-based, so the claim is broader than the guarantee. Mitigated
in practice because connection credentials are stored as `env://` references
rather than literals.

### OPS-044 — `PRAMA_` environment override · **PASS**

`PRAMA_DATABASE__DIALECT=postgres` → `database.dialect 'postgres' [environment]`.

### OPS-045 — a `PRAMA_` variable at the wrong depth · **PASS**

`PRAMA_DATABASE__PATH=/tmp/qa-operate/wrong.db prama db info` → still
`sqlite+pysqlite:///data/prama.db`. Silently ignored, exactly as
`troubleshooting.md` warns. It does surface in `config show` as
`database.path '/tmp/qa-operate/wrong.db'`, one line from `database.sqlite.path`.
The product documents this hazard and does not detect it; nothing validates that
a `PRAMA_`-prefixed variable names a real setting.

### OPS-046 / OPS-047 / OPS-048 — placeholders · **PASS** ×3

```
${NO_SUCH_VAR_XYZ}   → CONFIG.PLACEHOLDER_UNRESOLVED, names the var and offers ${X:default}
app.name: ${app.name} → CONFIG.PLACEHOLDER_CYCLE: app.name -> app.name
$${NOT_A_VAR}        → app.name '${NOT_A_VAR}'
```

### OPS-049 / OPS-050 / OPS-051 — secret references · **PASS** ×3

```
env://QA_ENV_SECRET              → 'QA-ENV-SENTINEL'
env://NO_SUCH_QA_VAR             → refusal naming the variable and where to set it
file:///tmp/qa-operate/secret.txt → value, trailing newline stripped
   WARNING secret file … is readable by group or other (mode 644); tighten it to 0400 or 0600
file:///…/nope.txt               → "no secret file at …", remedy names the k8s mountPath
SecretRef.parse("hunter2-my-actual-password")
   → "that is not a secret reference" · context: {}   ← the pasted text is NOT in the context
SecretRef.parse("env://")        → "names no location after env://"
SecretRef.parse("")              → "a secret reference is empty"
```

The empty `context: {}` on the literal-password case is the code's stated
intent (*"the offending text may be the password somebody pasted, and this
error gets logged"*) and it holds in practice.

### OPS-052 — vault reference, no Vault configured · **PASS** (with doc rot)

```
refused: Vault is referenced but not configured
next: Set the Vault address and a token reference in configuration. The token
      is itself a credential, so it is given as a reference (env://VAULT_TOKEN)
      and not as a literal.

resolver, unknown scheme:
refused: no secret provider is installed for hashicorp://
next: Installed: env. Either use one of those, or install the package providing hashicorp.
```

Two mismatches worth recording:

* `troubleshooting.md` quotes the message as *"the vault secret provider is not
  usable in this deployment"*. The product says *"Vault is referenced but not
  configured"*.
* `src/prama/secrets/reference.py`'s module docstring advertises
  `hashicorp://secret/data/prod/warehouse#password` as an example reference.
  The implemented scheme is `vault` (`vault.py:110`). `hashicorp` resolves to
  nothing.

---

## Section 3 — Paths and the working directory

### OPS-053 — `prama db info` from a foreign cwd · **FAIL**

```
$ cd /tmp && prama db info
dialect:     sqlite
schema file: schema/sqlite.sql
url:         sqlite+pysqlite:///data/prama.db
tables (0): (none)
[exit=0]

$ ls -la /tmp/data
-rw-r--r-- 1 ashutosh ashutosh 4096 Sep 12 20:27 prama.db
```

Two problems. The informational command **created** `/tmp/data/prama.db` as a
side effect; and it reported a database that did not exist a moment earlier as
`tables (0): (none)` with exit 0, rather than saying there is no database here.
This is the machinery behind the hazard `troubleshooting.md` describes as
*"you are pointed at a different database than you think"* — and `db info` is
the command the same document recommends for diagnosing it.

### OPS-054 — relative `schema_dir` with an explicit `--config` · **FAIL**

```
$ cd /tmp/qa-operate/cwdtest
$ prama --config /tmp/qa-operate/clone/config/application.yaml db init
error: authoritative schema file not found: schema/sqlite.sql
  code: DB.SCHEMA_FILE_MISSING
[exit=1]
```

`database.schema_dir: schema` resolves against the **process working
directory**, not against the directory of the configuration file that declares
it. A config file therefore cannot be self-contained: point a systemd unit at
`/etc/prama/application.yaml` without setting `WorkingDirectory` and it refuses.
The remedy text is correct ("set database.schema_dir to where it lives") but the
surprise is the resolution rule, which nothing documents. Same applies to
`database.sqlite.path`.

### OPS-055 — absolute paths from any cwd · **PASS**

```
$ cd /tmp && prama --config /tmp/qa-operate/abs/app.yaml db init
schema created: 35 tables, 99 statements from /tmp/qa-operate/clone/schema/sqlite.sql (digest 5df0746f832e)
$ prama --config … db verify
schema verified against …: no drift
```

### OPS-056 — sqlite path whose parent directory does not exist · **PASS**

Creates the parent chain and initialises. Exit 0.

### OPS-057 — sqlite path is a **directory** · **FAIL**

```
$ prama --config … --set database.sqlite.path=/tmp/qa-operate/abs/data db init
Traceback (most recent call last):
  File ".../sqlalchemy/engine/base.py", line 144, in __init__
  ...
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) unable to open database file
(Background on this error at: https://sqlalche.me/e/20/e3q8)
[exit=1]
```

A 40-line SQLAlchemy traceback with no Prama frame in the message, no code, no
`next:`. `docs/operations/troubleshooting.md` opens with *"Every error this
product raises carries a remedy … If you are reading an error with no remedy,
that is itself a defect worth reporting."*

### OPS-058 — sqlite path in an unwritable directory (0555) · **FAIL**

Identical traceback, identical `unable to open database file`. The permission —
the one fact that would let the operator fix it in one command — is nowhere in
the output.

### OPS-059 — `:memory:` · **PASS**

`db init` reports `schema created: 35 tables`; a separate `db info` invocation
reports `tables (0): (none)` against `sqlite+pysqlite:///:memory:`, which is the
correct per-process semantics.

### OPS-060 — `schema_dir` pointing at a directory with no `sqlite.sql` · **PASS**

`DB.SCHEMA_FILE_MISSING`, naming `/tmp/qa-operate/emptyschema/sqlite.sql`.

---

## Section 4 — Database lifecycle

### OPS-061 / OPS-062 — `db init`, then again · **PASS** / **PASS**

```
schema created: 35 tables, 99 statements from …/sqlite.sql (digest 5df0746f832e)
schema already current: 35 tables, 99 statements from …/sqlite.sql (digest 5df0746f832e)
```

Same digest both times. Idempotent.

### OPS-063 — `db init` over a populated database · **PASS**

```
rows before:  tenants 1 principals 1
$ prama db init  → schema already current …  [exit=0]
rows after:   tenants 1 principals 1
```

Non-destructive.

### OPS-064 / OPS-065 — `verify` / `info` on a good database · **PASS** ×2

`schema verified against …/sqlite.sql (digest 5df0746f832e): no drift`, exit 0.
`db info` names the dialect, the schema file, the URL and all 35 tables.

### OPS-066 — the **schema file** edited · **PASS**

A copy of `sqlite.sql` with `qa_extra_column VARCHAR(16)` added to `tenant`:

```
schema drift against /tmp/qa-operate/schemacopy/sqlite.sql (1 blocking, 1 informational):
  ! [missing_column] tenant.qa_extra_column: declared VARCHAR(16), absent
  - [digest] schema_state: applied digest 5df0746f832e differs from the current
    file (26874357106c); re-run `prama db init` to re-apply
[exit=3]
```

Exit 3 is `EXIT_DRIFT`. Names the object and the difference. Repairs nothing.

### OPS-067 — the **live database** edited (`ALTER TABLE … ADD COLUMN`) · **FAIL**

```
$ python -c "sqlite3.connect(db).execute('ALTER TABLE tenant ADD COLUMN qa_sneaky VARCHAR(8)')"
$ prama db verify
schema verified against …/sqlite.sql (digest 5df0746f832e): no drift
[exit=0]

$ PRAGMA table_info(tenant)
['id','slug','display_name','status','residency','settings_json','created_at','updated_at','qa_sneaky']
```

**Drift detection is one-directional for columns.** Declared-but-absent is
blocking (OPS-066). Present-but-undeclared is not reported at all — not even
informationally.

The asymmetry is specific to columns. Tables are checked both ways:

```
$ DROP TABLE rec_break; CREATE TABLE qa_rogue_table (…);
$ prama db verify
schema drift against …/sqlite.sql (1 blocking, 1 informational):
  ! [missing_table] rec_break: declared in the schema file, absent
  - [extra_table] qa_rogue_table: present in the database, not in the schema file
[exit=3]
```

The runbook's whole argument for `db verify` is *"a schema that silently changed
under running controls is how evidence stops meaning what it said"*. A DBA
adding a column is the commonest form of that change, and it is the form this
does not see.

### OPS-068 — `db init` after a live `ALTER TABLE` · **PASS**

`schema already current`; `qa_sneaky` still present afterwards. Nothing dropped
or altered, as the runbook promises.

### OPS-069 / OPS-070 — dropped table, then repair · **PASS** ×2

Verify reports it blocking (above). `db init` then recreates it:

```
schema created: 36 tables, 99 statements …
rec_break present: True   ·   qa_rogue_table present: True
```

and a follow-up verify drops to `0 blocking, 1 informational`, exit 0 — i.e. the
still-present rogue table is informational only. Correct.

### OPS-071 — `serve` against a drifted database, `verify_on_start: true` · **PASS**

It refuses, with the right content:

```
prama.core.errors.SchemaDriftError: [DB.SCHEMA_DRIFT] the live sqlite database
does not match /tmp/qa-operate/clone/schema/sqlite.sql | Next: Prama has no
migrations. Either run `prama db init` (safe: it only creates missing objects),
or reconcile the database with the schema file deliberately. Nothing will be
altered automatically. | Context: blocking=['missing_table:rec_break'], …
20:29:23 ERROR uvicorn.error Application startup failed. Exiting.
[exit=3]
```

QUICKSTART's troubleshooting table promises `SchemaDriftError` on start, so this
is documented. Presentation note: it arrives as an uncaught exception through
uvicorn's lifespan, so the remedy is the last line of a 40-line traceback rather
than the formatted `error: / code: / next:` block the CLI produces everywhere
else.

### OPS-072 — same, `verify_on_start: false` · **PASS**

Starts; `/api/v1/health` → 200. The operator asked for it.

### OPS-073 — `verify` against a path whose parent does not exist · **FAIL**

Reports all 35 tables missing, exit 3 — informative in itself, but it first
**created** `/tmp/qa-operate/no/such/place/` and a 4,096-byte
`p.db` inside it. A command whose entire job is to inspect and never repair
created a directory tree and a database file.

### OPS-074 — zero-byte file · **PASS**

Same "every table missing", exit 3. The case allowed this reading.

### OPS-075 — 4 KiB of `/dev/urandom` where the database should be · **FAIL**

```
  File ".../src/prama/db/dialects.py", line 169, in on_connect
    cursor.execute(f"PRAGMA journal_mode = {s.journal_mode}")
sqlalchemy.exc.DatabaseError: (sqlite3.DatabaseError) file is not a database
[exit=1]
```

No code, no remedy.

### OPS-076 — `verify` on a read-only (0444) database file · **PASS**

`no drift`, exit 0. Verify only reads.

### OPS-077 — `init` on a read-only database file · **FAIL**

```
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) attempt to write a readonly database
[SQL: INSERT INTO schema_state (id, schema_version, dialect, file_digest, applied_at, applied_by, product_version) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET …]
[parameters: (1, '1', 'sqlite', '5df0746f832ea8…', '2026-09-13T00:29:55.041375Z', 'ashutosh@oryxpro', '0.1.0')]
[exit=1]
```

OPS-057, OPS-058, OPS-075 and OPS-077 are one defect with four faces: no
filesystem or permission error from the SQLite layer is translated into the
Prama error taxonomy.

### OPS-078 — the two schema files · **PASS**

```
$ diff <(tail -n +2 schema/sqlite.sql) <(tail -n +2 schema/postgres.sql)
3c3
< -- THIS FILE IS THE AUTHORITY FOR SQLITE. …
> -- THIS FILE IS THE AUTHORITY FOR POSTGRESQL. …
8c8
< -- schema/postgres.sql is the same logical schema for PostgreSQL. …
> -- schema/sqlite.sql is the same logical schema for SQLite. …
```

Two header lines, 55,377 vs 55,379 bytes. Exactly as `CLAUDE.md` asserts.

### OPS-079 — PostgreSQL container · **PASS**

```
$ docker run -d --name qa-pg -e POSTGRES_PASSWORD=prama -e POSTGRES_USER=prama \
    -e POSTGRES_DB=prama -p 19433:5432 postgres:16-alpine
$ docker exec qa-pg pg_isready -U prama
/var/run/postgresql:5432 - accepting connections
```

`uv pip install -e ".[postgres]"` pulled `psycopg 3.3.5`.

### OPS-080 / OPS-081 — `db init` / `verify` on PostgreSQL · **PASS** ×2

```
schema created: 35 tables, 99 statements from …/postgres.sql (digest 3be7ad104901)
schema already current: …                                    (second run)
schema verified against …/postgres.sql (digest 3be7ad104901): no drift
url:  postgresql+psycopg://prama:***@127.0.0.1:19433/prama
```

### OPS-082 — PostgreSQL drift · **FAIL**

```
$ psql -c "ALTER TABLE tenant ADD COLUMN qa_sneaky VARCHAR(8);"
$ psql -c "CREATE TABLE qa_rogue (id VARCHAR(26) NOT NULL PRIMARY KEY);"
$ prama db verify
schema drift against …/postgres.sql (0 blocking, 1 informational):
  - [extra_table] qa_rogue: present in the database, not in the schema file
[exit=0]

$ psql -c "DROP TABLE rec_break;"
$ prama db verify
schema drift against …/postgres.sql (1 blocking, 1 informational):
  ! [missing_table] rec_break: declared in the schema file, absent
  - [extra_table] qa_rogue: present in the database, not in the schema file
[exit=3]
```

`qa_sneaky` is invisible on PostgreSQL too. The gap is engine-independent,
which means it is in the verifier's comparison and not in a dialect adapter.

---

## Section 5 — Running the server

### OPS-083 — `prama serve` with a tenant · **PASS**

`/api/v1/health` → 200, `/estate` → 200, `/api/v1/docs` → 200.

### OPS-084 — the "No tenant is configured" warning · **FAIL**

The warning is produced — but only when stdout is a terminal.

```
$ nohup prama --config … --set tenancy.default_tenant= serve --port 19421 > log 2>&1 &
$ grep -c "Console" log
0
$ curl -o /dev/null -w "%{http_code} %{redirect_url}" http://127.0.0.1:19421/estate
303 http://127.0.0.1:19421/sign-in
```

Isolated:

```
default                    : banner lines in the log while running = 0
PYTHONUNBUFFERED=1         : banner lines in the log while running = 1
default, after SIGTERM exit: banner lines in the log            = 0
```

So under a supervisor the operator gets **neither** the Console/API/Docs URLs
**nor** the tenant warning — not delayed, lost. `run_prama_web.py` carries the
fix and the reasoning for it:

> ```python
> # Flushed before uvicorn takes the process over. stdout is block-buffered
> # whenever it is not a terminal, so piping this to a file or running it
> # under a supervisor showed the log and never the URLs — which are the only
> # part somebody actually needs.
> sys.stdout.flush()
> ```

`src/prama/cli/commands.py::ServeCommand.run` has no equivalent. The warning
exists specifically to stop the *"every console page redirects to a sign-in
that does not exist"* confusion, and it is absent in the one deployment shape
where that confusion costs an on-call hour.

(Unrelated good news from the same case: `/sign-in` itself returns **200**, not
a redirect. The other blocker in `docs/qa/README.md` is fixed.)

### OPS-085 — port already in use · **FAIL**

```
20:31:41 INFO  uvicorn.error Application startup complete.
20:31:41 ERROR uvicorn.error [Errno 98] error while attempting to bind on address ('127.0.0.1', 19420): address already in use
[exit=3]
```

Two problems. The error is raw uvicorn with no Prama remedy — and the exit code
is **3**, which `docs/operations/cli-reference.md` defines as *"the thing being
checked is wrong and must not be used"*, the code a CI gate reads as a contract
breach or a bundle that must not be installed. A port conflict is exit **1**
("the command could not be completed"). `prama serve` leaks uvicorn's exit code
straight through and collides with the documented taxonomy.

(Also cosmetic, and uvicorn's: `Application startup complete` is logged *before*
the bind is attempted.)

### OPS-086 — `--port 0` · **PASS**

```
20:31:54 INFO uvicorn.error Uvicorn running on http://127.0.0.1:36393
LISTEN 127.0.0.1:36393  users:(("prama",pid=4161192,fd=16))
```

Binds an ephemeral port and uvicorn logs the real one. Prama's own banner builds
its URL as `f"http://{host}:{port}"` from the requested value, so it would print
`:0` — unobservable here because of OPS-084, and confirmed by reading
`ServeCommand.run` rather than by running it.

### OPS-087 — `--host 300.300.300.300` · **FAIL**

`ERROR uvicorn.error [Errno -2] Name or service not known`, exit 3. Raw, and it
printed `Console http://300.300.300.300:19422/estate` first.

### OPS-088 — `--host 10.255.255.1` (an address this host does not own) · **FAIL**

`[Errno 99] … cannot assign requested address`, exit 3. Same shape as OPS-085
and OPS-087.

### OPS-089 — SIGTERM · **PASS**

```
exit=143 (128+15)  elapsed=181 ms
uvicorn.error Shutting down / Waiting for application shutdown. /
Application shutdown complete. / Finished server process [4164318]
port 19424 listeners afterwards: 0
```

### OPS-090 — SIGINT · **PASS**

`exit=0`, 482 ms, same clean sequence.

### OPS-091 — stale state after shutdown · **PASS**

```
prama.db      610304
prama.db-shm   32768
prama.db-wal       0     ← checkpointed
$ prama db verify → no drift  [exit=0]
```

### OPS-092 — SIGKILL mid-write · **PASS**

`exit=137`. Afterwards `db verify` → no drift, `tenant list` → correct contents,
`PRAGMA integrity_check` → `ok`. WAL recovery worked.

### OPS-093 / OPS-094 — two servers on one SQLite database · **PASS** ×2

Both `/api/v1/health` → 200. With both servers up, six concurrent
`prama tenant create` processes all succeeded and all six rows landed:

```
conc1: created C1 (qa-conc-1)   …   conc6: created C6 (qa-conc-6)
tenant list → 7 tenants
```

WAL plus `busy_timeout: 5s` handled it. (`deploy/helm/prama/values.yaml`
separately forbids multi-replica SQLite, which is the right call for sustained
write load; this case only shows that light concurrency does not corrupt.)

### OPS-095 — health with the database file unreadable · **FAIL**

```
$ chmod 000 h.db h.db-wal h.db-shm
$ curl http://127.0.0.1:19441/api/v1/health
{"type":"https://prama.dev/problems/internal","title":"an unexpected error occurred",
 "status":500,"code":"PRAMA.INTERNAL",
 "remedy":"Retry; if it persists, quote the correlation id to support. The detail
           has been logged server-side.","correlation_id":"01M2C3EYKYV9F35QBCZ1KTFS4H",
 "instance":"/api/v1/health"}
[500]
```

It does not lie — but a health endpoint returning `PRAMA.INTERNAL` with
*"quote the correlation id to support"* for a `chmod` the operator can undo in
one command is the wrong shape. A health check's failure mode should be an
unhealthy health document (`status: "unhealthy"`, a named reason, 503), which is
what a probe and a load balancer are built to read.

### OPS-096 — health after the database file is deleted · **FAIL**

```
$ rm -f h.db
$ curl http://127.0.0.1:19441/api/v1/health
{"status":"ok","version":"0.1.0","schema_version":"1","dialect":"sqlite",
 "schema_file":"/tmp/qa-operate/clone/schema/sqlite.sql"}
[200]
```

The pool holds the unlinked inode, so `SELECT 1` still answers and the endpoint
says `ok`. Every new process — a CLI invocation, a restarted replica, a backup
job — sees nothing at that path. The health check never asks whether the
configured file exists.

This matters beyond the curiosity because of what consumes it.
`deploy/helm/prama/templates/deployment.yaml` uses `/api/v1/health` as **both**
`readinessProbe` and `livenessProbe`, with:

> ```yaml
> # Liveness and readiness are the SAME endpoint deliberately, because
> # Prama has no state that makes it live-but-not-ready: it either
> # reaches its database or it does not.
> ```

For SQLite, it can reach a database that is no longer there.

Related, observed while moving the file out from under two running servers and
back: for as long as the servers held the old handle, a **new** process opening
the same path got a bare `sqlite3.OperationalError: disk I/O error` while
`/api/v1/health` continued to return 200. Once the servers exited the file was
fine (`integrity_check: ok`, 7 tenants). Recorded as a consequence of OPS-096
rather than as a separate defect.

### OPS-097 — recovery · **PASS**

`chmod 644` restored → next request returns 200 `ok`, no restart needed.

### OPS-098 — docs and OpenAPI · **PASS**

`/api/v1/docs` → 200; `/api/v1/openapi.json` → `title Prama version 0.1.0
paths 25`. Version matches `VERSION`.

---

## Section 6 — Backup, restore, upgrade

### OPS-099 — is there a documented backup procedure? · **FAIL**

```
$ grep -rni "backup\|restore\|pg_dump\|\.backup" README.md QUICKSTART.md \
      docs/operations/ deploy/ SECURITY.md CONTRIBUTING.md
CONTRIBUTING.md:45: … then restore and watch it pass. Both halves.
```

One hit, about restoring a *test fixture*. **There is no backup or restore
procedure documented anywhere in this repository** — not in the runbook, not in
troubleshooting, not in `deploy/`, not in `SECURITY.md`.

That is a gap with unusual weight here, because of two deliberate design
choices this product has already made:

* **There are no migrations.** Recovering from a schema mistake means restoring,
  not rolling back.
* **The evidence ledger is the product.** Immutable hash-linked records that a
  regulator may read are the artefact; nothing tells an operator how to protect
  them, how often, or how to prove a restore worked.

The runbook has eight sections and none of them is "you have lost the
database". `deploy/README.md §What is missing` is admirably explicit about the
operator, the offline bundle and KMS; backup is not listed there either, so it
is absent rather than deferred.

### OPS-100 — is there a documented upgrade path? · **PASS**

Thin, but present, and in the right place:

`deploy/README.md §"Upgrades are not automatic, by design"`:

```bash
kubectl exec deploy/prama -- prama db verify
```

> `db verify` reports drift and never repairs it. A chart that upgraded silently
> would leave a schema nobody was told had diverged …

and `deploy/helm/prama/Chart.yaml` carries the machine-readable form:

```yaml
prama.io/upgrade-requires: "prama db verify"
```

What is not written down: what to do when `db verify` *does* report drift during
an upgrade — the answer must be "restore, or reconcile by hand", and the first
half of that depends on OPS-099.

### OPS-101 — naive `cp` of the SQLite file during writes · **FAIL**

```
server running on the database; 30 concurrent `tenant create` in flight
$ cp prama.db naive2.db        # main file only, as an operator would
$ ls -la prama.db-wal
-rw-r--r-- 1 ashutosh ashutosh 24752 Sep 12 20:36 prama.db-wal

naive2 integrity: ok
naive2 tenants:   7
live   tenants:  37
```

`PRAGMA integrity_check` says **ok**. The backup is missing 30 of 37 rows,
because everything not yet checkpointed lives in the `-wal` the copy did not
take. A silently truncated backup that verifies is the worst possible failure
mode for a backup, and — per OPS-099 — nothing in the documentation warns
against it, because nothing in the documentation discusses backup at all.

`journal_mode: WAL` is the shipped default (`config/application.yaml`), so this
is the configuration every operator has.

### OPS-102 — cold copy, restore elsewhere, start · **PASS**

Copy with the server stopped, restore to `/tmp/qa-operate/restored/`, point a
config at it:

```
$ prama db verify   → no drift  [exit=0]
$ prama tenant list → 37 tenants, default marked
$ prama serve --port 19431 → /api/v1/health 200 · /estate 200
```

### OPS-103 — the correct online backup · **PASS**

```python
src.backup(dst)          # SQLite's own online backup API
online integrity: ok
online tenants:  37      # all of them
```

The remedy exists; only the documentation of it does not.

### OPS-104 — `db verify` on the restored copy · **PASS** — no drift, exit 0.

### OPS-105 — what the database records about its own schema · **PASS**

```
schema_state: ['id','schema_version','dialect','file_digest','applied_at','applied_by','product_version']
(1, '1', 'sqlite', '5df0746f832ea8eebeedf0eea7924472460325bdc003dc26578d1b5bdbcc6dc6',
 '2026-09-13T00:28:40.542072Z', 'ashutosh@oryxpro', '0.1.0')
```

Dialect, file digest, when, by whom, and which product version applied it. A
future build can tell it is looking at an older schema. This is the piece an
upgrade procedure would be built on.

### OPS-106 — what `deploy/` tells a Kubernetes operator · **PASS**, with findings

Good: the chart defaults to `dialect: postgres` and `replicaCount: 2`; it
refuses at `helm install` on no session secret and on SQLite-with-replicas, with
the reasoning printed; `readOnlyRootFilesystem` is on and only `/tmp` is an
`emptyDir`, so no persistence is silently implied. `deploy/README.md §What is
missing` is candid about the operator and CRDs.

Two problems:

* The liveness/readiness comment is falsified by OPS-096 for the SQLite case.
* `deploy/README.md §What is missing` says
  *"**The signed offline bundle (W10.8)** — an air-gapped install: images,
  chart, wheels and a local model, with a signature and a verification step.
  Not built."* — while `README.md §Status` lists *"an offline bundle with
  publisher signing"* among what is implemented, the CLI reference documents
  `prama bundle seal|verify|sbom`, and Section 7 below exercises all of it
  successfully. One of the two documents is wrong.

---

## Section 7 — Offline / air-gapped bundle

Staged directory: `images/prama.tar`, `charts/prama-0.1.0.tgz`,
`wheels/prama-0.1.0-py3-none-any.whl` (200 KB of random bytes).

### OPS-107 — `bundle seal` · **PASS**

```
sealed 3 file(s), 0.2 MiB
  manifest: 632315aaf32f1b5c09f626ea1126c227d5207bc552e46c77f5595dad1821c541
  sbom:     50 distribution(s)

The seal is an HMAC over the manifest hash. …
No publisher signature: --sign-with was not given. An air-gapped
customer cannot check an HMAC without the key, so this bundle
carries no provenance they can verify.
[exit=0]
```

Wrote `manifest.json` and `manifest.sig`; both are excluded from the catalogue
on a re-seal (still "3 file(s)").

### OPS-108 — seal with no session secret · **PASS**

```
error: security.session_secret is empty, and Prama will not start without it
  code: CONFIG.SECRET_MISSING
  next: Set security.session_secret in config/application.local.yaml (git-ignored), …
[exit=1]
```

But `verify` refuses identically — and that is the command an air-gapped
customer runs *first*, on a host where the fresh-clone secret is empty by
design:

```
$ prama --config <no-secret>.yaml bundle verify ./offline
error: security.session_secret is empty …
[exit=1]
```

Giving the host *any* secret of its own is enough — the publisher path then
works correctly:

```
$ prama --config <customer-with-own-secret>.yaml bundle verify ./offline \
      --publisher-key key_a.pub.pem
Prama 0.1.0, sealed 2026-09-13T00:38:55.709734+00:00
3 file(s) verified, and the publisher signature holds.
[exit=0]
```

So the refusal is a gate in the wrong place rather than a broken mechanism: a
verification that checks only an Ed25519 signature has no use for a session
secret, and requiring one makes the air-gapped first run fail for a reason that
has nothing to do with the bundle. Recorded here rather than as a separate FAIL.

### OPS-109 — `bundle verify` on a good bundle · **PASS**

```
Prama 0.1.0, sealed 2026-09-13T00:37:33.387512+00:00
3 file(s) verified, and this deployment's seal holds — no publisher signature was checked.
[exit=0]
```

### OPS-110 — a file body modified · **PASS**

```
1 file(s) present with the wrong hash — this is a build or tampering problem,
not a transfer one: images/prama.tar. 3 file(s) checked.

Do not install this bundle.
[exit=3]
```

### OPS-111 — a file removed · **PASS**

```
1 file(s) listed and absent — a transfer problem: charts/prama-0.1.0.tgz. 2 file(s) checked.

Do not install this bundle.
[exit=3]
```

The distinction between "wrong hash" and "absent" is drawn, and correctly
characterised as a build/tamper problem versus a transfer problem.

### OPS-112 — a file **added** · **FAIL**

```
$ echo "evil" > off_add/images/backdoor.tar
$ prama bundle verify ./off_add
Prama 0.1.0, sealed 2026-09-13T00:37:33.387512+00:00
1 file(s) present that nobody signed for: images/backdoor.tar. 3 file(s) checked.
[exit=0]
```

It sees the file. It describes it in exactly the right words — *"present that
nobody signed for"*. And then it does **not** print "Do not install this
bundle", and exits **0**.

`src/prama/cli/bundle.py`'s own module docstring: *"`verify` exits 3 on a bundle
that must not be installed … an operator has to tell 'this bundle is wrong' from
'I ran the command wrong', and on an air-gapped host there is nobody to ask."*
An unsigned wheel in the `wheels/` directory of a bundle about to be installed
on a bank's disconnected host is the definition of a bundle that must not be
installed, and this is the only check standing between it and `pip install`.

Note that an extra *table* in a database is at least reported as informational
(OPS-069) — here an extra *file* does not even change the exit code.

### OPS-113 — manifest rewritten to match a tampered file · **PASS**

```
the seal does not verify against this deployment's key: the bundle was altered,
or sealed elsewhere. 3 file(s) checked.

Do not install this bundle.
[exit=3]
```

The HMAC over the manifest catches a self-consistent forgery. This is the check
that makes OPS-112 stranger, not weaker: the cryptography is right and the
verdict logic is not.

### OPS-114 — `manifest.sig` deleted · **PASS**

```
no signature was offered, so this bundle proves nothing about where it came
from — it is internally consistent and could have been built by anybody.
3 file(s) checked.

Do not install this bundle.
[exit=3]
```

### OPS-115 — a directory that is not a bundle · **PASS**

```
error: there is no manifest.json in /tmp/qa-operate/notabundle
  code: INPUT.INVALID
  next: This is a directory of files, not a bundle. A bundle carries a manifest,
        because without one there is nothing to check the files against.
[exit=1]
```

Exit 1, distinct from the exit 3 of a bad bundle. Exactly the distinction the
module set out to draw.

### OPS-116 — `--sign-with` on a documented install · **FAIL**

On the install the documentation prescribes (`.[dev,serve]`):

```
$ prama bundle seal ./offline --sign-with key.pem
  File ".../src/prama/cli/bundle.py", line 52, in _private_key
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
ModuleNotFoundError: No module named 'cryptography'
[exit=1]
```

`docs/operations/troubleshooting.md §Optional extras`: *"A missing extra always
produces a **named** refusal. If you are getting an `ImportError` traceback
instead, that is a defect."*

Worse, the extra is undiscoverable: `cryptography` appears in `pyproject.toml`
only under `sso = ["cryptography>=43"]`, and the extras table describes `sso` as
*"OIDC sign-in, customer-managed keys"*. Nothing connects bundle signing —
`CLAUDE.md`'s `prama bundle seal ./offline --sign-with k.pem  # Ed25519
provenance for an air-gapped host` — to `pip install -e ".[sso]"`.

Also note the seal is **not transactional**: it had already written
`manifest.json` and `manifest.sig` before crashing on the signature, leaving a
sealed-but-unsigned bundle behind.

With `cryptography 50.0.1` installed, the feature itself works:

```
$ prama bundle seal ./offline --sign-with key_a.pem
An Ed25519 signature is also written. That one a customer can check
with the public half alone, which is what an auditor asks about an
artefact that arrived on a disk.
[exit=0]
$ ls ./offline → manifest.ed25519  manifest.json  manifest.sig  …
$ prama bundle verify ./offline --publisher-key key_a.pub.pem
3 file(s) verified, and both the publisher signature and this deployment's seal hold.
[exit=0]
```

### OPS-117 — verify against the **wrong** publisher key · **PASS**

```
$ prama bundle verify ./offline --publisher-key key_b.pub.pem
the publisher signature does not verify against the key given: the bundle was
altered, or signed by somebody else. 3 file(s) checked.

Do not install this bundle.
[exit=3]
```

The signature is genuinely checked, not merely present.

### OPS-118 — `bundle sbom` · **PASS**

53 distributions with pinned versions (`SQLAlchemy==2.0.52`, `asyncpg==0.31.0`,
…), sorted, one per line.

---

## Section 8 — Evidence verification without Prama

### OPS-119 — the verifier's independence · **PASS**

```
imports: ['__future__', 'hashlib', 'json', 'pathlib', 'sys']
imports prama?  False
non-stdlib:     []
```

The claim holds exactly.

### OPS-120 — a good bundle · **PASS**

Bundle built through `prama.evidence.retention.Archivist` over a six-record
ledger (see *Unplanned observations* for why it had to be built by hand):

```
$ python3 scripts/verify_evidence.py /tmp/qa-operate/evbundle
Bundle:   /tmp/qa-operate/evbundle
Tenant:   tenant-a
Period:   sequence 0 to 5, written 2026-09-13T00:39:37.941459+00:00
Records:  6

  [PASS] every record's content hashes to its stored content_hash
  [PASS] every record links to the one before it
  [PASS] sequence numbers are contiguous
  [PASS] the manifest's record count (6) matches the file (6)
  [PASS] the evidence file is the one the manifest describes
  [PASS] the Merkle root matches the records
  [PASS] the chain head matches the last record

Every check passed.
[exit=0]
```

### OPS-121 — one record's verdict altered, same byte length · **PASS**

`"verdict":"fail"` → `"verdict":"pass"` on record 2 (5,279 bytes before and
after, so length alone reveals nothing):

```
  [FAIL] every record's content hashes to its stored content_hash
         record 2: content_hash is 15f9c75f4319…, the bytes give 8d09f111317c…
  [PASS] every record links to the one before it
  [PASS] sequence numbers are contiguous
  [PASS] the manifest's record count (6) matches the file (6)
  [FAIL] the evidence file is the one the manifest describes
         manifest says ecb342a75c62cbe4…, file is 21954a6796bb69b2…
  [PASS] the Merkle root matches the records
  [PASS] the chain head matches the last record

At least one check FAILED. This bundle is not what its manifest claims.
[exit=1]
```

Names the record and both checks that caught it. The counterfactual matters
here: a first attempt that changed only whitespace tripped **only** the payload
digest and left the per-record content hash green, which is the correct
discrimination — so the content-hash check is doing real work and not merely
following the digest.

### OPS-122 — not a bundle · **PASS**

```
$ python3 scripts/verify_evidence.py /tmp/qa-operate/notabundle
no such file: /tmp/qa-operate/notabundle/manifest.json
[exit=2]

$ python3 scripts/verify_evidence.py
usage:  python3 verify_evidence.py <bundle-directory>
        python3 verify_evidence.py manifest.json evidence.ndjson
[exit=2]
```

0 / 1 / 2 are all distinct and all as documented.

---

## Section 9 — Resource behaviour

Nothing pathological. Measured with `/usr/bin/time -f "wall=%e peakRSS=%M"`.

| Case | Command | Wall | Peak RSS | Exit |
|---|---|---|---|---|
| OPS-123 | `prama db init` (fresh, 35 tables, 99 statements) | 0.41 s | 61.7 MB | 0 |
| OPS-124 | `prama version` | 0.38 s | 59.0 MB | 0 |
| OPS-124 | `prama --help` | 0.40 s | 58.9 MB | 0 |
| OPS-011 | `prama config show` | 0.35 s | 59.4 MB | 0 |
| OPS-125 | `prama bench run --seed 42` (28 scenarios × 200 rows, 5 baselines) | 0.65 s | 66.8 MB | 0 |
| OPS-127 | `prama bundle seal` over 191 MB | 0.51 s | 61.6 MB | 0 |
| OPS-127 | `prama bundle verify` over 191 MB | 0.56 s | 60.7 MB | 0 |

**OPS-123 / OPS-124 · PASS.** ~0.4 s and ~59 MB is the floor for *any*
invocation, including `prama version`, because `main()` calls
`install_shipped()` before argument parsing. Acceptable; worth knowing if the
CLI is ever called in a loop.

**OPS-125 · PASS.** Output is coherent and honest — bounds (`detect-nothing`
0/28, `alert-on-everything` 28/28 at precision 0.08) and ablations, with a
blind-spot table per baseline.

**OPS-126 · BLOCKED.** The interesting version of this case — `prama control
run` over a populated estate — could not be run: the only thing that populates
an estate is the case studies, and all four crash (OPS-016). Against an empty
estate the command behaves correctly:

```
run 01M2C3D65XEWYJFZ4YCMPV4V6W
  no controls were live, so nothing ran
[exit=0]
```

**OPS-127 · PASS.** 191 MB sealed and verified in ~0.5 s each at ~61 MB RSS —
streamed, not buffered. Confirmed the hashing is real rather than skipped by
flipping one byte at offset 25,000,000 of a 50 MB blob:

```
1 file(s) present with the wrong hash … blob2.bin. 4 file(s) checked.
Do not install this bundle.
[exit=3]
```

**OPS-128 · PASS.** 200 sequential `GET /api/v1/health`:

```
200 requests in 1844 ms
RSS before: 97804 kB   RSS after: 99560 kB   (+1.8 MB)
open fds: 19 (stable)
```

---

## Section 10 — Cross-cutting operator sanity

| Case | Command | Result | Exit |
|---|---|---|---|
| OPS-129 | `prama` | full help | 2 · **PASS** |
| OPS-130 | `prama nosuchcommand` | `invalid choice: 'nosuchcommand' (choose from …)` | 2 · **PASS** |
| OPS-131 | `prama db` | `usage: prama db <init\|verify\|info>` | 2 · **PASS** |
| OPS-132 | `prama --json db init` on a broken schema dir | JSON error object with `code`, `context`, `message`, `remedy` | 1 · **PASS** |
| OPS-133 | `prama --log-level DEBUG db info` | `DEBUG prama.db.engine sync engine created for sqlite`; 0 sentinel leaks | 0 · **PASS** |
| OPS-134 | `prama --json config show \| json.load` | valid JSON, 43 keys, `security.session_secret: "***"` | 0 · **PASS** |

Exit codes match the documented taxonomy everywhere except `prama serve`
(OPS-085/087/088).

---

## Unplanned observations

Not pre-written cases. Found while executing the cases above, recorded here so
they are not lost, and explicitly marked as unplanned.

### U-1 — `prama apikey create` does not exist, so the HTTP API cannot be used

```
$ curl http://127.0.0.1:19420/api/v1/datasets
{"type":"https://prama.dev/problems/auth-unauthorised","title":"this request carried no API key",
 "status":401,"code":"AUTH.UNAUTHORISED",
 "remedy":"Send `Authorization: Bearer pk_live_…`, or the X-Prama-API-Key header.
           Create one with `prama apikey create`.","instance":"/api/v1/datasets"}

$ prama apikey create
prama: error: argument <command>: invalid choice: 'apikey'
  (choose from 'version','config','connect','connectors','bundle','contract','control',
   'db','estate','lsp','mcp','pack','bench','principal','serve','tenant')
```

`src/prama/api/deps.py` prints that remedy twice (lines 100 and 112, the second
recommending `prama apikey list`). There is an `api_key` table in the schema, an
`ApiKeyDao`, and an `ApiKeyIssuer` — and no CLI command, no API route, and no
console screen that mints one. Searched: `grep -rn "apikey" docs/operations/`
returns nothing.

QUICKSTART §0 presents the API as one of the product's two surfaces, *"for
programs"*. As shipped, no program can authenticate to it.

### U-2 — nothing produces an evidence bundle

`runbook.md §3` tells an auditor:

```bash
python3 scripts/verify_evidence.py /path/to/bundle
```

There is no `prama evidence export`, no `--bundle` flag on any command, and
`grep -rn "evidence" src/prama/cli/*.py` finds only role scopes and help text.
`prama.evidence.retention.Archivist` produces the bundle in-process and is the
only way to get one — which is how OPS-120 obtained a bundle to verify. So the
independently-verifiable evidence bundle, which is the product's central claim,
has no operator-facing export.

### U-3 — `prama db info` and `prama db verify` create files

Recorded under OPS-053 and OPS-073. Both commands read as inspection-only and
both will create directories and a database file at whatever path configuration
names.

---

## Execution incident

While clearing listeners after Section 5, a `pkill`-by-port sweep terminated
three servers belonging to **other concurrent QA passes** — `qa-console` on
:19200, `qa-datapath` on :19510, and a `run_prama_web.py` on :8080 — as well as
my own. Nothing was lost beyond the running processes; those passes will need to
restart their servers. Recorded rather than quietly omitted. Subsequent cleanup
matched on `/tmp/qa-operate` in the command line only.

## Cleanup performed

* `docker rm -f qa-pg` — the PostgreSQL container on :19433 is gone.
* All `/tmp/qa-operate` servers terminated; no listener remains on 19410–19441.
* File modes restored under `/tmp/qa-operate` (the 0555 directory and 0444/0000
  database files from OPS-058, OPS-076, OPS-077, OPS-095).
* `git status` confirms nothing under `src/`, `tests/`, `schema/` or `config/`
  was touched by this pass. The scratch tree `/tmp/qa-operate/` is left in
  place for reproduction.

---

## Summary table

| Section | Cases | Pass | Fail | Blocked | Not run |
|---|---:|---:|---:|---:|---:|
| 1 — Clean install, documentation followed literally | 16 | 13 | 3 | 0 | 0 |
| 2 — Configuration | 36 | 35 | 1 | 0 | 0 |
| 3 — Paths and the working directory | 8 | 4 | 4 | 0 | 0 |
| 4 — Database lifecycle | 22 | 17 | 5 | 0 | 0 |
| 5 — Running the server | 16 | 11 | 5 | 0 | 0 |
| 6 — Backup, restore, upgrade | 8 | 6 | 2 | 0 | 0 |
| 7 — Offline / air-gapped bundle | 12 | 10 | 2 | 0 | 0 |
| 8 — Evidence verification without Prama | 4 | 4 | 0 | 0 | 0 |
| 9 — Resource behaviour | 6 | 5 | 0 | 1 | 0 |
| 10 — Cross-cutting operator sanity | 6 | 6 | 0 | 0 | 0 |
| **Total** | **134** | **110** | **23** | **1** | **0** |

Failed cases: OPS-004, 015, 016, 029, 053, 054, 057, 058, 067, 073, 075, 077,
082, 084, 085, 087, 088, 095, 096, 099, 101, 112, 116.
Blocked: OPS-126 (dependent on OPS-016).

---

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
