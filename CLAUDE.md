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

Both files describe the same logical schema. A change goes into both, in the same commit, and
`tests/db/test_schema_parity.py` fails if the two drift apart.

### 3. Database code lives in exactly one package.

Only `src/prama/db/**` may import `sqlalchemy`. Everything else talks to repositories and the
unit of work. `tests/architecture/test_layering.py` enforces this by import scanning, and it will
fail the build, not warn.

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
pip install -e ".[dev]"                  # editable install with the dev extras
pytest -q                                # full suite
pytest -q tests/architecture             # layering, file length, no-model-verdict guards
prama config show                        # effective merged configuration, secrets redacted
prama db init                            # apply schema/<dialect>.sql idempotently
prama db verify                          # fail loudly if the live schema has drifted
python scripts/check_file_length.py      # the 1500-line ceiling
ruff check src tests && ruff format --check src tests
mypy src
```
