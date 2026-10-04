<img src="docs/assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# Contributing

Prama is proprietary and authorship of this repository is Ashutosh Sinha's
alone. This document is for anyone working on it under a separate written
agreement, and for the future maintainer who is me in eighteen months.

`CLAUDE.md` is the short list of things that are cheap to get wrong here and
expensive to discover later. Read that first; this is the longer form. How to
extend or change each part (a connector, a PQL function, an endpoint, a table)
is in the [developer guides](docs/developer/README.md).

---

## The one idea

The failure mode this class of system keeps producing is **artifacts that build,
validate, and look right while being wrong**. A control that compiles and checks
nothing. A schema that round-trips and swaps two fields. A signature that
verifies and proves nothing to the person holding it. A benchmark whose recall
is high because its corpus is easy.

Everything below follows from trying not to produce those.

---

## Three habits

### Assert the rendered artefact, not the intent

Assert the *executed verdict on real data*, not that the compiler emitted
plausible SQL. The conformance suite is this habit as a release gate: every
catalogued function is executed on DuckDB, SQLite and — when a DSN is set — a
real PostgreSQL, and compared against its own reference implementation.

A test that checks a function *renders* catches a template with a hole in it and
nothing else. That is roughly one bug class out of twenty.

### Write the counterfactual

A control that cannot fail is worth nothing. When you add a guard, break the
thing it guards and watch it fail; then restore and watch it pass. Both halves.

This is not ceremony. Twice in this repository a counterfactual **corrected the
claim being made**:

- An injection guard was credited with stopping SQL injection. The
  counterfactual showed the dialect's quoting was the barrier and the guard was
  decoration. The comment and the test names were rewritten.
- A `ROUND` lowering routed through a double was expected to fail a conformance
  test. It passed — because PostgreSQL's `float8→numeric` conversion uses
  shortest-representation output and recovers the value exactly. The edit was
  not the change it appeared to be, and a different one was needed.

### Derive, never restate

Anything stated in a second place will drift, silently, in the flattering
direction. So: scores derive from evidence, controls derive from declarations,
connector configuration forms derive from connector source, the CLI reference
derives from the argument parser, and advertised test counts derive from a green
run.

When you find yourself copying a fact, stop and generate it instead.

---

## Hard rules

They fail the build, and `CLAUDE.md` is where they are stated: authorship, no
migrations, database code in one package, the 1500-line ceiling, no secrets in
tracked configuration, the SDK, kernel and agent as separate packages, and AI
never adjudicates. Each [developer guide](docs/developer/README.md#the-gate-a-change-must-pass)
names the guard that enforces the rules it touches.

---

## Writing errors

Every error carries a **remedy**: the next thing to do, not a restatement of the
problem. `ValidationError` will not construct without one, which is deliberate.

Compare:

```
error: invalid configuration
```

```
error: Vault is installed but not configured: it has no token reference.
  next: Set the address and a token reference (env://VAULT_TOKEN) in
        configuration — the token is itself a credential, so it is given as a
        reference and not as a literal.
```

The second tells somebody what to do at three in the morning. It also tells them
*why*, which is what stops them working around it.

**Refusals are a feature.** Most failures in this product are refusals, and a
refusal that explains itself is working as designed. What is not acceptable is a
refusal that leaves somebody guessing, or a silent fallback to something weaker.

---

## Writing tests

Name the test after the belief it defends, not the method it calls.
`test_a_committed_message_is_not_redelivered` beats `test_commit`.

Say *why* in the docstring, especially when the behaviour looks wrong:

```python
def test_a_party_not_on_the_leg_gets_none_rather_than_zero(self) -> None:
    """Zero is a position; this is the absence of one."""
```

Six months later that sentence is the only thing standing between the code and
somebody "simplifying" it.

**Parametrised tests must use their parameter.** A test parametrised three ways
that ignores the parameter looks like three tests and is one. Ruff catches the
lambda form; the class form it does not.

**Prefer a real service to a double** where one can be run. The Kafka transport's
offset semantics, the REST connector's pagination and the PostgreSQL conformance
runs all found bugs that a mock would have been instructed not to have —
including `params={}` silently stripping a query string, which made a paginated
read return page one repeatedly and call itself complete.

---

## Documentation

Design documents describe intent. Each opens with an **As built** section saying
what is built, what is not, and what is built but has never met the real thing —
that third category is the one summaries lose.

`tests/architecture/test_documentation.py` fails the build on a path that does
not exist, a module that does not exist, a link that does not resolve, or a
design document with no as-built section.

Code a developer guide shows as a complete implementation lives in
`docs/developer/examples/`, and `tests/docs/test_developer_examples.py` runs
every file there, so a guide's code cannot rot unseen.

Generated references (`docs/operations/cli-reference.md`,
`configuration-reference.md`) carry a banner. Edit the code and regenerate;
editing the prose fails the gate.

---

## The loop

```bash
bash scripts/gate.sh     # ruff, format, mypy, file length, generated docs, pytest
```

The gate exists because piping pytest into `tail` returns tail's exit code, so a
collection error sails through an `&&` chain and a commit lands on a red suite.
That happened twice before the script existed.

With real services, the suite covers more. Both are optional, and the suite is
green without them; it skips more.

```bash
docker run -d --name prama-pg -e POSTGRES_PASSWORD=prama -e POSTGRES_USER=prama \
  -e POSTGRES_DB=prama -p 55432:5432 postgres:16-alpine
export PRAMA_TEST_POSTGRES_DSN=postgresql://prama:prama@127.0.0.1:55432/prama
export PRAMA_TEST_KAFKA_BOOTSTRAP=127.0.0.1:19092   # see tests/execute/test_kafka.py
```

With PostgreSQL the function conformance corpus runs on three engines instead of
two, which is the version of that test worth the name.

---

## Git

Adopted from Maya's branch and release workflow (Maya ADR-002), which Prama
already mostly followed; this makes it policy rather than habit.

- **All work is committed on `develop`.** `main` receives only merges from
  `develop`, never a direct commit.
- **`main` is promoted to, deliberately.** It is not synced on a schedule, and
  `main` sitting behind `develop` mid-wave is normal, not drift to close.
- **Promotion requires** the gate green (`scripts/gate.sh`, or
  `python3 scripts/sync_test_counts.py --write`, which refuses a red run), a
  clean tree, and generated documents current (`generate_docs.py --check`).

**The owner's shorthand is binding:**

| Word | Means |
|---|---|
| *drill* | commit and push `develop`, merge `develop` into `main` with `--no-ff`, push `main`, fast-forward `develop` to `main`, push `develop` |
| *drill to develop* | the first half only: commit and push `develop` |
| *drill to main* | the second half only: merge, push `main`, fast-forward `develop` |

The drill, from a detached worktree so the live tree never checks out `main`:

```bash
git push origin develop                                   # drill to develop
git worktree add /tmp/mainwt main                         # drill to main ↓
git -C /tmp/mainwt merge --no-ff develop -m "Merge <ids> into main: <summary>"
git -C /tmp/mainwt push origin main
git merge --ff-only main && git push origin develop
git worktree remove /tmp/mainwt && git worktree prune
```

Enable the hooks once per clone: `git config core.hooksPath .githooks`. The
pre-commit hook runs the file-length ceiling, the tracked-secret check, the
version single-source gate and ruff, using the repository's `.venv` even when
it is not activated. Never pass `--no-verify`.

**Push early.** An unpushed branch is one disk failure from gone, and a
local-only commit is not safe either.

### Commit messages

Say what changed and **why it is right**, in prose. The bar: somebody reading it
in a year should understand the decision without opening the diff.

Record the things that surprised you — the bug you introduced and caught, the
counterfactual that did not bite the first time, the assumption that turned out
wrong. Those are the most valuable lines in the history, and they are the ones a
summary would delete.

Sentence-style subjects that state the outcome, no Conventional-Commit
prefixes, at most 100 characters (the hook enforces the limit).

Author is `ajsinha <ajsinha@gmail.com>`, set repo-locally. **The developer is
Ashutosh Sinha alone**: no `Co-Authored-By: Claude`, no `Claude-Session:`, no
"Generated with Claude" — the hook refuses them, and they are dropped at the
source rather than left for the hook to catch.

### Licence notice

Prama is proprietary (`LICENSE`, `NOTICE`). Every source file — Python,
template, stylesheet, script, SQL, hook, deployment manifest, console guide —
carries `Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights
reserved.`, and every console page shows it in the footer with a link to
`/legal`. `tests/architecture/test_proprietary_notice.py` fails the build on a
file without it.
