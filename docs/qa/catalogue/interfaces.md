# Interfaces — every way a human or a program reaches Prama

Seven entry points, enumerated from the code: the command line, the HTTP API,
the console, the PQL language server, the MCP server, the assistant, and the
remote agent. Round 1 exercised the first three *as surfaces* — does the product
work when you use it. This catalogue asks the other question: for every flag,
every route's authorisation matrix, every protocol message, and the four
surfaces round 1 never touched at all, is there a case?

Ids are namespaced by surface, so nothing collides with the other catalogue
files: `CLI-`, `API-`, `UI-`, `LSP-`, `MCP-`, `AST-` (assistant), `AGT-` (agent).

| Area | Module | Count | P1 | P2 | P3 |
|---|---|---:|---:|---:|---:|
| Command line | `cli/` | 96 | 34 | 46 | 16 |
| HTTP API | `api/` | 62 | 23 | 33 | 6 |
| Console | `web/` | 76 | 26 | 40 | 10 |
| Language server | `lsp/` | 25 | 9 | 12 | 4 |
| MCP server | `mcp/` | 25 | 9 | 13 | 3 |
| Assistant | `assistant/` | 32 | 11 | 18 | 3 |
| Remote agent | `agent/` | 42 | 15 | 23 | 4 |
| **Total** | | **358** | **127** | **185** | **46** |

Nothing here was executed. Where a case repeats round 1 it is because the
*combination* — a flag, a role, a content type — was not covered there; where it
does not, it is new ground.

---

## CLI — the framework: `cli/base.py`, `cli/main.py`

### CLI-001 · No command prints help and exits 2
- **Area:** `cli/base.py::Application.run`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** run `prama` with no arguments
- **Expected:** the full parser help on stdout, exit `EXIT_USAGE` (2)
- **Why:** the code branches on `not args.command`; an entry point that exits 0
  on no input makes a shell script unable to tell "I forgot the command" from
  "it worked"

### CLI-002 · An unknown command is a usage error, not a crash
- **Area:** `cli/base.py::Application.build_parser`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** run `prama frobnicate`
- **Expected:** argparse refusal naming the valid choices, exit 2, nothing on stdout
- **Why:** the valid set is built from `all_commands()`; a refusal that does not
  list them sends the reader to `--help` for information the refusal had

### CLI-003 · Every command in `all_commands()` appears in `--help`
- **Area:** `cli/commands.py::all_commands`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `prama --help`, compare the command list against the 17 names
  returned by `all_commands()`
- **Expected:** exact set equality
- **Why:** finding Q-36 was four global flags absent from the reference that
  claims completeness; the same drift is possible for a command group

### CLI-004 · A command group invoked bare prints its usage line and exits 2
- **Area:** `cli/base.py::CommandGroup.run`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** run each of `config`, `db`, `tenant`, `principal`, `apikey`,
  `connect`, `control`, `contract`, `estate`, `bundle`, `bench`, `pack`, `lsp`,
  `mcp` with no subcommand
- **Expected:** `usage: prama <group> <a|b|c>` listing that group's real
  subcommands, exit 2 — for all fourteen
- **Why:** the usage string is built from `self._commands`; a group whose
  registration and help disagree is a group whose help is a lie

### CLI-005 · An unknown subcommand is refused before any database is opened
- **Area:** `cli/base.py::CommandGroup.run`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `database.dialect: sqlite` pointing at a path that does not exist
- **Steps:** run `prama db frobnicate`
- **Expected:** exit 2; no database file is created as a side effect
- **Why:** finding Q-40 was `db info`/`db verify` creating database files; a
  usage error must not

### CLI-006 · A `PramaError` prints message, code and remedy on stderr and exits 1
- **Area:** `cli/base.py::Application.run`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** run `prama tenant create 'Not A Slug'`
- **Expected:** stderr carries `error:`, `code:`, `next:` and each context key;
  stdout is empty; exit 1
- **Why:** the taxonomy's whole claim is that a failure says what to do next,
  and the CLI is where a person reads it

### CLI-007 · `--json` renders a `PramaError` as `{"error": …}` and nothing else
- **Area:** `cli/base.py::Application.run`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** run `prama --json tenant create 'Not A Slug'`; pipe stdout to `jq .`
- **Expected:** stdout is exactly one JSON document with an `error` object
  carrying `code`, `message`, `remedy`; `jq` exits 0
- **Why:** finding Q-37 — `--json` on a PQL syntax error emitted prose, breaking
  the contract at the CI integration point; this is the general form of it

### CLI-008 · `--json` is refused or accepted consistently after the command word
- **Area:** `cli/base.py::Application.build_parser`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** run `prama version --json` and `prama --json version`
- **Expected:** the two agree — either both emit JSON, or the first is a usage
  error naming the correct position. A silently ignored flag is a failure
- **Why:** global options are declared on the top-level parser only, so the
  post-command form is at best an argparse error and at worst discarded

### CLI-009 · `--config` naming a missing file is refused with the path
- **Area:** `cli/base.py::CommandContext.config`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** run `prama --config /nope/nope.yaml config show`
- **Expected:** a `PramaError` naming the path, exit 1, no traceback
- **Why:** configuration is resolved lazily on first `ctx.config`, so the
  failure surfaces inside a command rather than at parse time

### CLI-010 · `--config` naming a directory is refused, not read
- **Area:** `cli/base.py::CommandContext.config`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `mkdir /tmp/adir`
- **Steps:** run `prama --config /tmp/adir config show`
- **Expected:** a typed refusal with a remedy; no `IsADirectoryError` traceback
- **Why:** finding Q-28 — 22 tracebacks reached the terminal, mostly "directory
  where a file is expected"

### CLI-011 · `--config` naming an unreadable file is refused with the reason
- **Area:** `cli/base.py::CommandContext.config`
- **Type:** negative
- **Priority:** P3
- **Precondition:** a config file with mode `000`
- **Steps:** run `prama --config that config show`
- **Expected:** a refusal that distinguishes "cannot read" from "not valid YAML"
- **Why:** the two have different remedies and only one is the operator's fault

### CLI-012 · `--set key=value` overrides, and is visible in `config show`
- **Area:** `cli/base.py::CommandContext.config`, `commands.py::ConfigShowCommand`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `prama --set logging.level=DEBUG config show --provenance`
- **Expected:** the value is DEBUG and its provenance names the override, not a file
- **Why:** `--provenance` exists so an operator can tell where a value came
  from; an override that reports a file's provenance is worse than none

### CLI-013 · `--set` with no `=` is refused
- **Area:** `cli/base.py::CommandContext.config`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `prama --set logginglevelDEBUG config show`
- **Expected:** a refusal naming the expected `KEY=VALUE` form; exit 1
- **Why:** silently ignoring a malformed override means a run that did not do
  what its command line says

### CLI-014 · `--set` repeated for one key: the last wins, deterministically
- **Area:** `cli/base.py::CommandContext.config`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** `prama --set logging.level=DEBUG --set logging.level=ERROR config show`
- **Expected:** ERROR, documented as last-wins
- **Why:** `--set` is `action="append"`; the merge order is a contract a
  deployment script depends on

### CLI-015 · `--log-level` with an invalid name
- **Area:** `cli/base.py::Application.run`, `core/log.py::LoggingConfigurator`
- **Type:** negative
- **Priority:** P3
- **Precondition:** none
- **Steps:** `prama --log-level LOUD version`
- **Expected:** a refusal naming the four permitted levels, or a documented
  fallback that is *said* — never silence
- **Why:** the help string names `DEBUG | INFO | WARNING | ERROR`; a value
  outside that set must not silently become INFO

### CLI-016 · `--json` forces JSON log format
- **Area:** `cli/base.py::Application.run`
- **Type:** functional
- **Priority:** P3
- **Precondition:** `logging.format: text` in configuration
- **Steps:** `prama --json --log-level DEBUG version 2>logs`; parse each line of `logs`
- **Expected:** every log line is valid JSON
- **Why:** the code passes `fmt="json" if args.json`; a machine-readable stdout
  beside human-readable stderr is half a contract

### CLI-017 · An unexpected exception does not reach the terminal as a traceback
- **Area:** `cli/base.py::Application.run`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a malformed `.pql` file that triggers a non-`PqlError`
- **Steps:** run every command against inputs chosen to break them; count tracebacks
- **Expected:** zero tracebacks; every failure is a typed error with a remedy
- **Why:** finding Q-28 counted 22; the `except PramaError` clause catches only
  the taxonomy, and everything else escapes

### CLI-018 · `Ctrl-C` during a long command exits 1 with one line
- **Area:** `cli/base.py::Application.run`
- **Type:** functional
- **Priority:** P3
- **Precondition:** a `control run` against a large source
- **Steps:** interrupt it
- **Expected:** `interrupted` on stderr, exit 1, no traceback, database closed
- **Why:** the handler exists; whether the `finally: await database.stop()`
  inside `asyncio.run` runs first is the part worth asserting

### CLI-019 · Exit codes are the four documented values and nothing else
- **Area:** `cli/base.py` constants `EXIT_OK/ERROR/USAGE/DRIFT`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** run the whole command matrix, success and failure, recording exit codes
- **Expected:** only 0, 1, 2, 3 are ever returned
- **Why:** `contract check` and `bundle verify` tell a build to distinguish 3
  from 1; a fifth code makes that rule wrong

### CLI-020 · Shipped packs are installed before any command runs
- **Area:** `cli/main.py::main`, `packs.install_shipped`
- **Type:** regression
- **Priority:** P2
- **Precondition:** none
- **Steps:** `prama control check` a suite using a banking pack function, in a
  fresh process
- **Expected:** the function resolves; the same function is listed by
  `prama control functions`
- **Why:** the comment says this exists so `check` and `pack list` agree; a
  regression here is a control that lints clean and will not compile

---

## CLI — `version`, `config`: `cli/commands.py`

### CLI-021 · `version` prints product, version, IR and schema versions
- **Area:** `cli/commands.py::VersionCommand`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `prama version`
- **Expected:** four values, all matching `src/prama/version.py`
- **Why:** CLAUDE.md makes `VERSION` the only authority; a copy that has rotted
  is discovered here first

### CLI-022 · `version --json` carries the same four fields
- **Area:** `cli/commands.py::VersionCommand.run`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** `prama --json version | jq -r '.product,.version,.ir_version,.schema_version'`
- **Expected:** four non-empty values identical to the text form
- **Why:** two renderings of one fact drift; this is the cheapest place to catch it

### CLI-023 · `version` works with no configuration and no database
- **Area:** `cli/commands.py::VersionCommand.run`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** no config file, no database, empty `security.session_secret`
- **Steps:** `prama version`
- **Expected:** exit 0
- **Why:** finding Q-35 — the first literal step of QUICKSTART is this command;
  it must not require a booted install

### CLI-024 · `config show` redacts every secret by default
- **Area:** `cli/commands.py::ConfigShowCommand.run`
- **Type:** security
- **Priority:** P1
- **Precondition:** a local config with a non-empty `security.session_secret`
  and a database password
- **Steps:** `prama config show | grep -i secret`
- **Expected:** no plaintext secret appears anywhere in the output
- **Why:** the command's own help promises redaction; this is the claim

### CLI-025 · `config show --raw` is refused without the environment variable
- **Area:** `cli/commands.py::ConfigShowCommand.run`
- **Type:** security
- **Priority:** P1
- **Precondition:** `PRAMA_ALLOW_RAW_CONFIG` unset
- **Steps:** `prama config show --raw`
- **Expected:** values stay redacted; the flag does not silently succeed
- **Why:** the code ANDs the flag with the variable; a change that drops the
  second half turns a documented guard into a no-op

### CLI-026 · `config show --raw` with the variable set warns loudly
- **Area:** `cli/commands.py::ConfigShowCommand.run`
- **Type:** security
- **Priority:** P2
- **Precondition:** `PRAMA_ALLOW_RAW_CONFIG=1`
- **Steps:** `prama config show --raw`
- **Expected:** secrets shown *and* the trailing "do not paste this anywhere" warning
- **Why:** the warning is the only thing between a support ticket and a leaked key

### CLI-027 · `config show --raw --json` — does the warning survive?
- **Area:** `cli/commands.py::ConfigShowCommand.run`
- **Type:** security
- **Priority:** P2
- **Precondition:** `PRAMA_ALLOW_RAW_CONFIG=1`
- **Steps:** `prama --json config show --raw`
- **Expected:** either the payload carries a `redacted: false` marker, or the
  warning is emitted on stderr; unmarked raw JSON is a defect
- **Why:** the code returns before the warning on the JSON path — a secret dump
  with nothing saying so is the worst combination of the two

### CLI-028 · `config show --provenance` names a source for every key
- **Area:** `cli/commands.py::ConfigShowCommand.run`, `Configuration.provenance`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a layered config: defaults, tracked file, local file, `--set`
- **Steps:** `prama config show --provenance`
- **Expected:** every line ends in a source, `built-in defaults` where nothing overrode
- **Why:** provenance that silently omits a layer is how a leaked value's origin
  becomes unknowable

### CLI-029 · `config show --provenance --json` — the flag is ignored on the JSON path
- **Area:** `cli/commands.py::ConfigShowCommand.run`
- **Type:** contract
- **Priority:** P3
- **Precondition:** none
- **Steps:** `prama --json config show --provenance`
- **Expected:** provenance is present in the JSON, or the combination is refused
- **Why:** the JSON branch returns before `--provenance` is consulted; a flag
  accepted and discarded is a flag that lies

---

## CLI — `db`: `cli/commands.py`

### CLI-030 · `db init` is idempotent
- **Area:** `cli/commands.py::DbInitCommand`, `db.Database.initialise`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a fresh sqlite path
- **Steps:** run `prama db init` three times
- **Expected:** exit 0 each time; the digest is identical; `created` is true only
  on the first
- **Why:** "applies them idempotently" is a hard rule of the project

### CLI-031 · `db init --json` reports the digest and statement count
- **Area:** `cli/commands.py::DbInitCommand.run`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** `prama --json db init | jq .digest`
- **Expected:** a hex digest matching the schema file's own
- **Why:** the digest is what `db verify` later compares against; if it is not
  emitted it cannot be recorded in a change ticket

### CLI-032 · `db verify` exits 3 on drift and 0 when clean
- **Area:** `cli/commands.py::DbVerifyCommand.run`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a database initialised, then an extra table added by hand
- **Steps:** `prama db verify; echo $?`
- **Expected:** 3, with the extra table named
- **Why:** `EXIT_DRIFT` is what a deployment gate reads

### CLI-033 · `db verify` sees an added *column*
- **Area:** `cli/commands.py::DbVerifyCommand.run`, `db` verification
- **Type:** regression
- **Priority:** P1
- **Precondition:** a live database with one extra column added via `ALTER TABLE`
- **Steps:** `prama db verify`
- **Expected:** the column is reported as drift, exit 3
- **Why:** finding Q-20 — extra tables are reported, extra columns are invisible,
  on both engines. This is that finding as a case

### CLI-034 · `db verify` sees a *removed* column and a changed type
- **Area:** `cli/commands.py::DbVerifyCommand.run`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a rebuilt table missing one column, and another whose
  `VARCHAR(64)` became `TEXT`
- **Steps:** `prama db verify --json`
- **Expected:** both drifts reported, each `blocking`
- **Why:** the no-migrations rule means drift detection is the only safety net
  there is

### CLI-035 · `db verify` never repairs
- **Area:** `cli/commands.py::DbVerifyCommand`
- **Type:** security
- **Priority:** P1
- **Precondition:** a drifted database
- **Steps:** run `db verify`, then diff the live schema before and after
- **Expected:** byte-identical; nothing was altered
- **Why:** the command's own help says "report drift, never repair it"

### CLI-036 · `db info` answers when the database is unreachable
- **Area:** `cli/commands.py::DbInfoCommand.run`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `database.dialect: postgres` pointing at a closed port
- **Steps:** `prama db info`
- **Expected:** dialect, schema file and URL printed; `reachable: no` with a
  one-line reason; exit 0
- **Why:** the docstring says this is exactly the question asked when it is not
  reachable

### CLI-037 · `db info` never prints a password
- **Area:** `cli/commands.py::DbInfoCommand.run`
- **Type:** security
- **Priority:** P1
- **Precondition:** a postgres DSN with a password
- **Steps:** `prama db info`, `prama --json db info`
- **Expected:** the password appears in neither; `render_as_string(hide_password=True)`
  is honoured on both paths
- **Why:** the comment calls this the only form of a URL that may ever be printed

### CLI-038 · `db info` does not create a database as a side effect
- **Area:** `cli/commands.py::DbInfoCommand.run`
- **Type:** regression
- **Priority:** P2
- **Precondition:** `database.path` pointing at a file that does not exist
- **Steps:** `prama db info`; then `ls` the path
- **Expected:** the file still does not exist
- **Why:** finding Q-40 — `db info` and `db verify` created files by reaching
  for an engine

### CLI-039 · A relative `schema_dir` resolves against the config file, not the cwd
- **Area:** `cli/commands.py::DbInitCommand`, `db.settings`
- **Type:** regression
- **Priority:** P2
- **Precondition:** a config with a relative `schema_dir`
- **Steps:** run `prama --config /abs/path/app.yaml db init` from three
  different working directories
- **Expected:** identical behaviour from all three
- **Why:** finding Q-40; a command whose meaning depends on `cd` is one that
  works for whoever wrote the runbook and nobody else

### CLI-040 · `db init` against a database at a *different* schema version
- **Area:** `cli/commands.py::DbInitCommand.run`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a database stamped with a recorded digest that does not match
- **Steps:** `prama db init`
- **Expected:** a loud refusal — never a silent migration, never a silent overwrite
- **Why:** "A live schema that has drifted is a loud failure, never a silent
  migration" is a hard rule

---

## CLI — `tenant` and `principal`

### CLI-041 · `tenant create` prints the id and the two next steps
- **Area:** `cli/tenant.py::TenantCreateCommand.run`
- **Type:** functional
- **Priority:** P1
- **Precondition:** initialised database, no tenants
- **Steps:** `prama tenant create acme-bank --name 'Acme Bank'`
- **Expected:** the id, the `tenancy.default_tenant` snippet, and the
  `principal create … --tenant acme-bank` line
- **Why:** the printed next step is executed verbatim by CLI-047; it must name a
  command that exists and accepts what it is given

### CLI-042 · `tenant create` refuses an unusable slug, with the rule
- **Area:** `cli/tenant.py::SLUG`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** try `Acme_Bank`, `-acme`, `acme bank`, `""`, a 63-character slug, a
  64-character slug, and a slug of only digits
- **Expected:** the 63-character one and the all-digits one are accepted; every
  other is refused naming the rule; the 64-character one is refused on length
- **Why:** the regex allows 1+62 characters starting alphanumeric; a boundary
  nobody tested is a boundary PostgreSQL will enforce differently

### CLI-043 · `tenant create` lowercases before validating
- **Area:** `cli/tenant.py::TenantCreateCommand.run`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** `prama tenant create ACME-BANK`
- **Expected:** created as `acme-bank`, and the output says the stored slug
- **Why:** the code lowercases first; a user who typed uppercase and is not told
  will later pass the uppercase form to `--tenant`

### CLI-044 · A duplicate slug is refused with the existing id
- **Area:** `cli/tenant.py::TenantCreateCommand.run`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `acme-bank` exists
- **Steps:** `prama tenant create acme-bank`
- **Expected:** `ConflictError`, exit 1, the message quoting the existing id
- **Why:** the comment says a typo in the slug must not be indistinguishable
  from a second estate

### CLI-045 · `tenant create --residency` is stored and shown by `tenant list`
- **Area:** `cli/tenant.py`
- **Type:** functional
- **Priority:** P3
- **Precondition:** none
- **Steps:** create with `--residency eu-west`; then `prama --json tenant list`
- **Expected:** the residency round-trips
- **Why:** residency is load-bearing for the agent's redaction policy and is set
  nowhere else from the CLI

### CLI-046 · `tenant list` marks the configured default
- **Area:** `cli/tenant.py::TenantListCommand.run`
- **Type:** functional
- **Priority:** P2
- **Precondition:** three tenants, `tenancy.default_tenant` set to the second
- **Steps:** `prama tenant list`
- **Expected:** exactly one `*`, on the second, plus the explanatory footer
- **Why:** a list of three ULIDs with no marker is a list the reader must then
  go and check against the configuration

### CLI-047 · The remedy printed by `tenant create` works verbatim
- **Area:** `cli/tenant.py`, `cli/principal.py::_resolve_tenant`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** a fresh estate
- **Steps:** run the exact `prama principal create <username> --admin --tenant acme-bank`
  line the previous command printed
- **Expected:** success — the slug is accepted where an id is expected
- **Why:** this pairing failed once with a raw `FOREIGN KEY constraint failed`;
  every `remedy=` gets a case that follows it literally

### CLI-048 · `principal create` rejects a password given as an argument
- **Area:** `cli/principal.py::PrincipalCreateCommand.configure`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** `prama principal create alice --password hunter2`
- **Expected:** argparse refuses the unknown flag; no such option exists
- **Why:** the module docstring states passwords are never accepted as arguments;
  adding one later would be silent

### CLI-049 · One line on stdin is the password
- **Area:** `cli/principal.py::_read_password`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a tenant exists
- **Steps:** `printf 'correct horse' | prama principal create alice --admin`
- **Expected:** created; and that exact string authenticates in the console
- **Why:** finding Q-01 — the CLI said created and the console said invalid

### CLI-050 · Two identical lines on stdin are accepted
- **Area:** `cli/principal.py::_read_password`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** `printf 'pw\npw\n' | prama principal create bob`
- **Expected:** created with password `pw` — no trailing newline stored
- **Why:** the interactive path asks twice, so piping twice is the natural thing

### CLI-051 · Two differing lines are refused and nothing is written
- **Area:** `cli/principal.py::_read_password`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `printf 'pw\nqw\n' | prama principal create carol`; then `principal list`
- **Expected:** refusal; carol does not exist
- **Why:** "Nothing was written" is the remedy's claim and must be true

### CLI-052 · Three or more lines are refused as a piped file
- **Area:** `cli/principal.py::_read_password`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `cat /etc/hostname /etc/hostname /etc/hostname | prama principal create dave`
- **Expected:** refusal naming the line count
- **Why:** accepting it would set a password nobody can type

### CLI-053 · Empty stdin is refused with a pipe example
- **Area:** `cli/principal.py::_read_password`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `prama principal create eve < /dev/null`
- **Expected:** "no password on stdin" with the `printf` remedy; exit 1
- **Why:** the remedy names a command form, which CLI-054 runs literally

### CLI-054 · The `_read_password` remedy works verbatim
- **Area:** `cli/principal.py::_read_password`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** `PASSWORD=s3cret` exported
- **Steps:** run `printf '%s' "$PASSWORD" | prama principal create alice` exactly
  as the remedy prints it
- **Expected:** success, and the password is `s3cret` with no newline
- **Why:** a remedy that has never been executed is a sentence, not a fix

### CLI-055 · Blank lines among piped lines are ignored
- **Area:** `cli/principal.py::_read_password`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** `printf '\npw\n\n' | prama principal create frank`
- **Expected:** password is `pw`; the blank lines are filtered before counting
- **Why:** the filter runs before the length checks; a password of only
  whitespace is therefore impossible and should be said

### CLI-056 · A password that is only whitespace
- **Area:** `cli/principal.py::_read_password`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** `printf '   \n' | prama principal create gina`
- **Expected:** refused as "no password on stdin" — not accepted as three spaces
- **Why:** `line.strip()` filters it out, so the user sees a message about an
  empty stream having supplied a value they can see

### CLI-057 · Username validation, at both ends of the regex
- **Area:** `cli/principal.py::USERNAME`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** try `a`, a 128-character name, a 129-character name, `.alice`,
  `alice@example.com`, `al ice`, `""`, and `Ålice`
- **Expected:** the first three-minus-one accepted; `.alice`, the email, the
  space, the empty and the non-ASCII refused with the rule quoted
- **Why:** the pattern is `[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}`; 128 is the last
  accepted length and nothing states it

### CLI-058 · `--role` with an unknown name lists the four built-ins
- **Area:** `cli/principal.py::BUILTIN_ROLES`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `printf pw | prama principal create h --role wizard`
- **Expected:** refusal listing admin, owner, steward, auditor; nothing written
- **Why:** the refusal happens before the password is read in the code order —
  assert that too, so a typo does not consume the piped secret

### CLI-059 · `--role` repeated grants both
- **Area:** `cli/principal.py::_grant`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** create with `--role steward --role auditor`; then `principal list`
- **Expected:** both listed; the union of their scopes is what the console enforces
- **Why:** roles are granted in a loop and created lazily; the second grant
  exercising an already-created role is the interesting path

### CLI-060 · `--admin` and `--role admin` together grant once, not twice
- **Area:** `cli/principal.py::PrincipalCreateCommand.run`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** create with both
- **Expected:** one grant; no integrity error from a duplicate role assignment
- **Why:** `wanted` is a plain list concatenation with no de-duplication

### CLI-061 · A principal with no role is created and *told* so
- **Area:** `cli/principal.py::PrincipalCreateCommand.run`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** create with no `--role` and no `--admin`
- **Expected:** created, plus the "can sign in and do nothing" paragraph naming
  the four roles
- **Why:** an account that signs in and is refused everything reads as a broken
  console

### CLI-062 · The remedy in the no-role message works
- **Area:** `cli/principal.py`
- **Type:** documentation
- **Priority:** P3
- **Precondition:** the previous case's output
- **Steps:** run the printed `--role admin | --role owner | …` form literally
- **Expected:** either it works or the message is rewritten; a pipe-separated
  "choose one" printed as though it were a command line is ambiguous
- **Why:** every `remedy=` gets a case that follows it literally

### CLI-063 · A duplicate username in one estate is a conflict
- **Area:** `cli/principal.py::PrincipalCreateCommand.run`
- **Type:** negative
- **Priority:** P2
- **Precondition:** alice exists in acme-bank
- **Steps:** create alice again in acme-bank
- **Expected:** `ConflictError`, exit 1, the existing account untouched
- **Why:** a second create that silently reset the password would be a privilege
  escalation with a friendly message

### CLI-064 · The same username in two estates is allowed
- **Area:** `cli/principal.py`, `PrincipalDao.by_username`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two tenants
- **Steps:** create alice in each
- **Expected:** both succeed; each authenticates only against its own estate
- **Why:** tenancy is the product's hardest boundary and usernames are the
  obvious place to cross it

### CLI-065 · `--tenant` naming a non-existent estate lists the known ones
- **Area:** `cli/principal.py::_resolve_tenant`
- **Type:** negative
- **Priority:** P1
- **Precondition:** two estates exist
- **Steps:** `printf pw | prama principal create x --tenant 01NOSUCH`
- **Expected:** refusal naming both known slugs; nothing written
- **Why:** finding Q-17 — seven of eight commands accepted a non-existent
  `--tenant` and reported a plausible empty result at exit 0

### CLI-066 · `--tenant` accepts an id as readily as a slug
- **Area:** `cli/principal.py::_resolve_tenant`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** create one principal by slug and one by ULID
- **Expected:** both land in the same estate
- **Why:** the id is what the schema needs and the slug is what a human has

### CLI-067 · `principal list` marks accounts that cannot sign in
- **Area:** `cli/principal.py::PrincipalListCommand.run`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a principal row with a NULL password hash
- **Steps:** `prama principal list`
- **Expected:** `!` beside it and the footer explaining the mark
- **Why:** a list showing only roles describes an unusable account as though it
  were in service

### CLI-068 · `principal list` on an empty estate says how to fix it
- **Area:** `cli/principal.py::PrincipalListCommand.run`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an estate with no principals
- **Steps:** `prama principal list --tenant acme-bank`
- **Expected:** the "Nobody." message with the create command; exit 0
- **Why:** an empty list and a broken query look identical without it

### CLI-069 · `principal list --tenant` for another estate shows nothing of it
- **Area:** `cli/principal.py::PrincipalListCommand.run`
- **Type:** security
- **Priority:** P1
- **Precondition:** two estates, each with principals
- **Steps:** list each
- **Expected:** disjoint sets; no usernames, ids or roles cross
- **Why:** `list_for_tenant` is the whole isolation, and there is no second check

### CLI-070 · `principal roles` needs no database
- **Area:** `cli/principal.py::PrincipalRolesCommand.run`
- **Type:** functional
- **Priority:** P2
- **Precondition:** database unreachable
- **Steps:** `prama principal roles`
- **Expected:** the four roles, their sentences and permissions; exit 0
- **Why:** the docstring says it is answerable from a change ticket

### CLI-071 · Every permission `principal roles` prints is in `SCOPES`
- **Area:** `cli/principal.py::BUILTIN_ROLES`, `security/scopes.py::SCOPES`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** `prama --json principal roles | jq -r '.roles[].permissions[]'`;
  compare against `SCOPES` allowing `*` and one-level `x:*`
- **Expected:** every name resolves
- **Why:** finding H5 was two vocabularies a comment insisted were one; a role
  granting a permission no route requires is a role that cannot be satisfied

### CLI-072 · The wildcard claim is true: `control:*` satisfies `control:approve`
- **Area:** `security/scopes.py::permits`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** assert `permits(("control:*",), "control:approve")` and
  `not permits(("control:*",), "incident:read")`
- **Expected:** as stated by the sentence `principal roles` prints
- **Why:** the command prints "wildcards go one level deep only" as a promise

---

## CLI — `apikey`

### CLI-073 · A key is printed once and is not recoverable
- **Area:** `cli/apikey.py::ApiKeyCreateCommand.run`
- **Type:** security
- **Priority:** P1
- **Precondition:** a principal exists
- **Steps:** create a key; then `apikey list`; then query the database directly
- **Expected:** the plaintext appears in the create output only; the row holds a
  prefix and a hash, and nothing that can reconstruct the key
- **Why:** the docstring's claim is "a key that can be re-read from the database
  is a key the database's backups also carry"

### CLI-074 · A key with no `--scope` is refused at creation
- **Area:** `cli/apikey.py::ApiKeyCreateCommand.run`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** `prama apikey create ci --principal alice`
- **Expected:** refusal listing the scope vocabulary; no row written
- **Why:** "'none recorded' must not mean 'no limit'" — and refusing at creation
  beats discovering it on the first 403

### CLI-075 · An invented scope is refused, naming it
- **Area:** `cli/apikey.py`, `security/scopes.py::unknown`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `--scope declaration:read --scope wizard:everything`
- **Expected:** refusal naming `wizard:everything` only
- **Why:** naming the good one too would send the operator to fix a scope that
  was fine

### CLI-076 · `--scope '*'` is accepted and permits everything
- **Area:** `cli/apikey.py`, `security/scopes.py::WILDCARD`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** issue a `*` key and call one route from each scope family
- **Expected:** all succeed
- **Why:** the help offers `'*'`; whether the API honours it is a separate fact

### CLI-077 · A one-level wildcard scope is accepted at creation
- **Area:** `security/scopes.py::unknown`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `--scope declaration:*`
- **Expected:** accepted (the checker skips names ending `:*`), and the API
  honours it for both `declaration:read` and `declaration:write`
- **Why:** creation accepting a form the API does not honour is the worst case

### CLI-078 · `--principal` is required and must exist
- **Area:** `cli/apikey.py::ApiKeyCreateCommand.run`
- **Type:** negative
- **Priority:** P1
- **Precondition:** no principal called `nobody`
- **Steps:** omit `--principal`; then pass `--principal nobody`
- **Expected:** argparse refusal for the first; a typed refusal quoting the
  `prama principal create` remedy for the second
- **Why:** every key is attributable, and the remedy names a command that must exist

### CLI-079 · `--expires-in-days 0` means never, and says so
- **Area:** `cli/apikey.py::ApiKeyCreateCommand.run`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** create with the default; read the `expires:` line
- **Expected:** `never`
- **Why:** the help calls this "a decision rather than a default"; a blank line
  would let somebody believe an expiry was set

### CLI-080 · `--expires-in-days` negative, and a key already expired
- **Area:** `cli/apikey.py::ApiKeyCreateCommand.run`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `--expires-in-days -1`
- **Expected:** refused — or created and *immediately* refused by the API with
  the ordinary 401; never created and silently usable
- **Why:** `timedelta(days=-1)` produces a past `expires_at`, which `get_caller`
  treats as expired; creating one is at best pointless and at worst confusing

### CLI-081 · `--expires-in-days` a very large number
- **Area:** `cli/apikey.py::ApiKeyCreateCommand.run`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** `--expires-in-days 3650000`
- **Expected:** either refused or stored without a `datetime` overflow traceback
- **Why:** `datetime.now(UTC) + timedelta(days=…)` raises `OverflowError` past
  year 9999, which is not in the taxonomy

### CLI-082 · `--environment` changes the prefix tag
- **Area:** `cli/apikey.py`, `db/security.py::ApiKeyIssuer`
- **Type:** functional
- **Priority:** P3
- **Precondition:** none
- **Steps:** create with `--environment test` and with the default
- **Expected:** distinguishable prefixes; both authenticate
- **Why:** the prefix is what `apikey list` and `apikey revoke` address; a tag
  that changes the lookup key is worth proving

### CLI-083 · `--environment` with a value containing separators
- **Area:** `cli/apikey.py`, `ApiKeyIssuer.issue`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `--environment 'live_pk'`, `--environment ''`, `--environment '../x'`
- **Expected:** refused or sanitised; the prefix must stay unambiguous for
  `prefix_of` to recover it
- **Why:** authentication parses the prefix out of the presented key; an
  environment that injects the separator makes two keys share a prefix

### CLI-084 · `apikey list` never shows a key
- **Area:** `cli/apikey.py::ApiKeyListCommand.run`
- **Type:** security
- **Priority:** P1
- **Precondition:** several keys
- **Steps:** `prama apikey list`, `prama --json apikey list`
- **Expected:** prefixes only; no `key`, no `key_hash` field in the JSON
- **Why:** the help says "by prefix — never the key itself"

### CLI-085 · `apikey list` shows revoked and expired state
- **Area:** `cli/apikey.py::ApiKeyListCommand.run`
- **Type:** functional
- **Priority:** P2
- **Precondition:** one active, one revoked, one expired key
- **Steps:** `prama apikey list`
- **Expected:** the revoked one marked; the expired one distinguishable — an
  expired key shown as `active` is a defect
- **Why:** the code derives `state` from `revoked_at` alone and never consults
  `expires_at`, so an expired key reads as active

### CLI-086 · `apikey list` on an empty estate prints the create command
- **Area:** `cli/apikey.py::ApiKeyListCommand.run`
- **Type:** functional
- **Priority:** P3
- **Precondition:** no keys
- **Steps:** `prama apikey list`
- **Expected:** the "Issue one:" line, which CLI-087 runs literally
- **Why:** an empty state that does not say what to do next is a dead end

### CLI-087 · The `apikey list` empty-state remedy works verbatim
- **Area:** `cli/apikey.py`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** a principal called alice exists
- **Steps:** run `prama apikey create ci --principal alice --scope '*'` exactly
- **Expected:** a key is issued
- **Why:** finding Q-06 was a remedy naming a command group that did not exist

### CLI-088 · `apikey revoke` stops the key working immediately
- **Area:** `cli/apikey.py::ApiKeyRevokeCommand.run`
- **Type:** security
- **Priority:** P1
- **Precondition:** a working key
- **Steps:** call the API with it; revoke; call again
- **Expected:** 200 then 401, with no restart in between
- **Why:** `get_caller` reads `revoked_at` per request; a cached identity would
  make revocation advisory

### CLI-089 · `apikey revoke` twice reports "already revoked"
- **Area:** `cli/apikey.py::ApiKeyRevokeCommand.run`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a revoked key
- **Steps:** revoke again
- **Expected:** `already revoked`, exit 0, `revoked_at` unchanged
- **Why:** moving the timestamp on a second call would rewrite when the
  credential stopped being trusted

### CLI-090 · `apikey revoke` with another estate's prefix is refused as not found
- **Area:** `cli/apikey.py::ApiKeyRevokeCommand.run`
- **Type:** security
- **Priority:** P1
- **Precondition:** two estates, one key each
- **Steps:** revoke estate B's prefix while `--tenant` names estate A
- **Expected:** "no key with prefix … in this estate"; B's key still works
- **Why:** `by_prefix` is not tenant-scoped; the handler compares `tenant_id`
  afterwards, and that comparison is the entire boundary

### CLI-091 · `apikey revoke` with a prefix that is a prefix of another
- **Area:** `cli/apikey.py`, `ApiKeyDao.by_prefix`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two keys whose prefixes share a leading substring
- **Steps:** revoke using the shorter string
- **Expected:** exact-match only — either not found, or the one key whose prefix
  equals the argument; never both, never the wrong one
- **Why:** revoking the wrong credential is silent until something else breaks

### CLI-092 · Every `apikey` subcommand honours `--tenant` and the configured default
- **Area:** `cli/apikey.py::_tenant_of`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `tenancy.default_tenant` set
- **Steps:** run create, list, revoke with and without `--tenant`
- **Expected:** identical results; and with neither, a refusal naming both ways
  to supply it
- **Why:** `_tenant_of` is one function for three commands, so the failure mode
  is uniform — which is worth confirming rather than assuming

### CLI-093 · `apikey create --json` emits the plaintext exactly once
- **Area:** `cli/apikey.py::ApiKeyCreateCommand.run`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** `prama --json apikey create ci --principal alice --scope '*' | jq -r .key`
- **Expected:** a usable key on stdout and nothing secret on stderr
- **Why:** this is the provisioning path a script uses, and it must not require
  parsing prose

### CLI-094 · `apikey create` is refused when the tenant does not exist
- **Area:** `cli/apikey.py`, `cli/principal.py::_resolve_tenant`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `--tenant 01NOSUCH`
- **Expected:** the estate refusal listing known slugs; no key row written
- **Why:** finding Q-17's shape; an orphan key is a credential nobody can audit

### CLI-095 · The scopes on a key are not the principal's roles
- **Area:** `cli/apikey.py::ApiKeyCreateCommand.configure`
- **Type:** security
- **Priority:** P1
- **Precondition:** alice is an admin
- **Steps:** issue a key for alice with `--scope declaration:read`; call a write route
- **Expected:** 403 — the admin role is not inherited
- **Why:** the help states the roles are NOT inherited; if they were, every key
  would be as powerful as its owner

### CLI-096 · A key for a principal in another estate is refused
- **Area:** `cli/apikey.py::ApiKeyCreateCommand.run`
- **Type:** security
- **Priority:** P1
- **Precondition:** alice exists only in estate A
- **Steps:** `--tenant estate-b --principal alice`
- **Expected:** "there is no principal called 'alice' in this estate"
- **Why:** `by_username` is called with the resolved tenant; a lookup that fell
  back to a global search would issue a cross-estate credential
