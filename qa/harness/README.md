# QA harnesses — round 2

The scripts that **executed** the catalogue in `qa/catalogue/`, kept
because they are the difference between a QA round you can repeat and a QA
round you have to take on trust.

Each was written to run a batch of catalogue cases against the live tree and
print one line per case: the id, the verdict, and what was actually observed.
They are the evidence behind `qa/logs/*.md` — a log without the thing
that produced it is an assertion, not a record.

## Why these are kept rather than thrown away

Round 1 could not be re-run. Its findings had to be re-derived by hand before
any of them could be trusted, and two of them turned out not to reproduce at
all. That cost more than keeping the scripts would have.

These are also the seed corpus for regression. Several of them exercise paths
the pytest suite does not reach — the async PostgreSQL engine, `IS UNIQUE`
lowering, windowed evidence verification, connector path containment — each of
which was green in a 4,800-case suite while being broken. A harness that found
a defect once is the cheapest possible guard against it returning.

## Shape

    qa/harness/<area>/…        mirrors qa/catalogue/<area>.md

They are **not** pytest tests and are deliberately outside collection:
`pyproject.toml` sets `testpaths = ["tests"]`, and `ruff` is pointed at
`src tests`, so nothing here is linted, formatted or collected. They are run
directly:

    python qa/harness/trust/h_evd1.py

Expect them to need the venv on `PATH` and to be run from the repository root.

## What is missing, and why

**`language/` is absent.** That agent delegated to sub-workers which wrote into
their own scratch directories and removed them on completion, so 629 cases'
worth of harnesses were gone before they could be copied. The log survives; the
means of reproducing it does not. Those cases have to be re-executed from the
catalogue rather than re-run.

That is the argument for this directory existing, made by the one area that
does not have it.

## Fixtures are generated, not stored

A harness that needs a 1501-line file, a drifted `pyproject.toml` or a fake
`.venv` **builds it at run time**. None of that is committed. The first attempt
to keep these harnesses swept the generated inputs in with them, and the
pre-commit hook refused the commit because one of them was a 1501-line file
built specifically to prove the 1500-line ceiling refuses it — the guard
catching a fixture written to test the guard.

It was right to refuse. Those files are derived data: large, uninteresting, and
reproducible by the script that needs them.

## Status

These are working scripts, not curated tests. They hard-code paths, print
rather than assert, and vary in style by author. Promoting a harness into
`tests/` — with a real assertion and a counterfactual confirming it fails
against the old code — is a deliberate step, taken per defect as it is fixed.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
