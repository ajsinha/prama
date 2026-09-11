<img src="docs/assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# Contributing

Prama is proprietary and authorship of this repository is Ashutosh Sinha's
alone. This document is for anyone working on it under a separate written
agreement, and for the future maintainer who is me in eighteen months.

`CLAUDE.md` is the short list of things that are cheap to get wrong here and
expensive to discover later. Read that first; this is the longer form.

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

These fail the build. They are in `CLAUDE.md` in full; the short form:

1. **No assistant attribution in commit messages.** `.githooks/commit-msg`
   refuses them.
2. **No database migrations, ever.** Two schema files, byte-identical apart from
   their headers, applied idempotently and verified. A drifted schema is a loud
   failure, never a silent repair.
3. **Only `prama.db` imports SQLAlchemy.** Everything else uses DAOs behind a
   unit of work.
4. **No source file over 1500 code lines.** Comments and docstrings do not
   count, so documenting a module is never penalised. A file over the ceiling is
   doing more than one thing.
5. **No secrets in tracked configuration.** The shipped session secret is empty
   on purpose.
6. **AI never adjudicates** (`CON-007`). No module may both call a model and
   produce a verdict. Enforced by import scanning.
7. **Concurrency is structured.** No bare threads, no unbounded queues, no
   fire-and-forget tasks. Use `prama.core.concurrency`.

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

With real services, the suite covers more:

```bash
export PRAMA_TEST_POSTGRES_DSN=postgresql://prama:prama@127.0.0.1:55432/prama
export PRAMA_TEST_KAFKA_BOOTSTRAP=127.0.0.1:19092
```

---

## Git

Work lands on `develop`. `main` moves at the end of a wave.

```bash
git commit && git push origin develop            # freely, during a wave
git checkout main && git merge --no-ff develop   # once, at the end
git push origin main
git checkout develop && git merge main && git push origin develop
```

**Push early.** An unpushed branch is one disk failure from gone, and a
local-only commit is not safe either.

### Commit messages

Say what changed and **why it is right**, in prose. The bar: somebody reading it
in a year should understand the decision without opening the diff.

Record the things that surprised you — the bug you introduced and caught, the
counterfactual that did not bite the first time, the assumption that turned out
wrong. Those are the most valuable lines in the history, and they are the ones a
summary would delete.

Author is `ajsinha <ajsinha@gmail.com>`, set repo-locally. No attribution
trailers; the hook refuses them.
