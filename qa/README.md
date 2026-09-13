# QA

Everything about testing Prama as a product rather than as a set of modules.
`tests/` is written alongside the code by whoever wrote it; this is written
against the code by somebody trying to break it.

| Directory | What it holds | In the gate |
|---|---|---|
| [`catalogue/`](catalogue/) | 4,660 test cases, written from the code, nothing executed | linted for broken references |
| [`logs/`](logs/) | what happened when they were executed | no |
| [`harness/`](harness/) | the scripts that executed them | no |
| [`regression-suite/`](regression-suite/) | tests derived from what they found | **yes** |
| [`round-1/`](round-1/) | the first, smaller pass — kept for comparison | no |
| [`findings.md`](findings.md) | the ranked register, `Q-01`… | no |

## How a finding travels

    catalogue/   a case is written from reading the code
    harness/     a script executes it against the live tree
    logs/        the observed result is recorded, pass or fail
    findings.md  a failure is reproduced by hand and ranked
    regression-suite/   it becomes a test that failed before its fix

The last step is the one that makes the round worth repeating. A log says
something was broken on a Tuesday. A test says it is not broken now, and will
say so again without anybody remembering to look.

## Why the catalogue is linted and the logs are not

`tests/architecture/test_documentation.py` checks that every module a document
names actually exists. The catalogue is in scope: a case naming a module that
does not exist is a case that can never run, and the guard has already caught
two of them.

The logs are deliberately out of scope. A defect log's job is to name what is
broken or missing — `qa/logs/dataplane.md` says `prama.profile.from_rows`
precisely *because* importing it fails. Requiring every module a defect report
names to exist would forbid it from reporting the defect.

## Rounds

**Round 1** — 1,014 cases, 170 failures. Could not be re-run: its harnesses
were never kept, so every finding had to be re-derived by hand and two did not
reproduce at all. That is why `harness/` exists.

**Round 2** — 4,660 cases across seven areas, executed against the live tree.
Counts in [`logs/`](logs/), ranked findings in [`findings.md`](findings.md).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
