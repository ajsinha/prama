# The regression suite

Tests derived from QA round 2 — one per defect the round found, each of which
**provably failed before its fix**.

This is the difference between the two directories beside each other:

| | `qa/harness/` | `qa/regression-suite/` |
|---|---|---|
| What it is | the scripts that executed the catalogue | tests derived from what they found |
| Behaviour | prints observations | asserts, and fails the build |
| Collected | no | yes |
| Lifetime | evidence for round 2 | permanent guard |

A harness prints `CON-132: FAIL :: read a file outside root_path`. That is
evidence when a person reads it and worthless in CI, because the script exits 0
either way. Promoting it here means putting the catalogue's **Expected** field
into an assertion — real work per case, not a mechanical translation, which is
why this directory grows one remediation batch at a time rather than in one
dump of 4,660 generated tests that all pass unconditionally.

## The xfail-first rule

A test lands here **before** its fix, marked strict:

```python
@pytest.mark.xfail(strict=True, reason="QA-2 CON-132: path escapes root_path")
def test_filesystem_connector_refuses_a_path_outside_its_root() -> None: ...
```

`strict=True` means the suite fails if the test **unexpectedly passes**. So the
marker cannot be left behind after the defect is fixed, and a defect fixed
accidentally — by an unrelated change, or by someone who did not know what they
were fixing — breaks the build until it is recorded. It is the counterfactual
discipline expressed as a marker instead of a promise.

Write the test, watch it xfail for the stated reason, fix the code, watch the
strictness break the build, remove the marker. A test that was never seen to
fail is not evidence that anything works.

## Layout

    qa/regression-suite/<area>/test_<theme>.py

Areas mirror `qa/catalogue/`. Names say what must be true, not which
function is called, so a failure reads as a sentence.

## Running

Collected by the default `pytest` run — `testpaths` names this directory
alongside `tests`. Slow cases carry `@pytest.mark.slow` so `-m "not slow"`
stays quick; the full gate runs everything.

    pytest -q qa/regression-suite          # this suite alone
    pytest -q                              # the whole gate, including it

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
