# QA execution logs — round 2

One file per catalogue area. Each records the **executed** result of every case
in the corresponding `docs/qa/catalogue/*.md` file.

## The rule that matters

A case is `PASS` only if it was **run** and the observed behaviour matched the
catalogue's **Expected** field. Not "the code looks right", not "the test suite
covers this". If it was not executed, it is `BLOCKED`, and the reason is stated.

Marking a case passed without running it is the one failure this whole exercise
exists to catch, and it is worse than a missed defect because it is invisible.

## Per-case line

Cases are logged as a table, one row each, in catalogue id order:

| Id | Result | Observed |
|---|---|---|
| `PQL-042` | PASS | `PqlSyntaxError: a control needs BECAUSE …` |
| `PQL-043` | FAIL | parsed without error; plan_id `01J…` produced |
| `PQL-044` | BLOCKED | needs a live Snowflake account |

`Observed` is what actually happened — a value, an exception, an exit code, a
row count. Never a restatement of the expectation.

## Per-failure entry

Every `FAIL` gets a section below the table:

### PQL-043 · A control with no BECAUSE is refused
- **Expected:** `PqlSyntaxError`, naming the missing clause
- **Observed:** parsed cleanly; `Control(because='')`
- **Reproduce:** `python -c "from prama.pql.parser import parse; parse('CHECK t.a IS NOT NULL')"`
- **Severity:** P1
- **Assessment:** defect · not-a-defect (catalogue was wrong) · working-as-designed

The third is not a rubber stamp. Use it when the code is right and the case was
written from a misreading — and say what the misreading was, because a catalogue
that is wrong in one place is worth correcting in that place.

## Header

Each log opens with counts: total, passed, failed, blocked, and the pass rate,
followed by the failures ranked by severity.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
