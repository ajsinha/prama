"""No test git cannot see.

Found while committing the `DB-179` repair, QA round 4. The new regression lived
in `qa/regression-suite/data/`, `pytest` collected it and it passed — and
`git status` did not mention it, because `.gitignore` carried an unanchored
`data/`. An unanchored pattern matches a directory of that name at **any**
depth, so a whole cluster of the regression suite was invisible: not untracked
and offered, simply absent. It would have run on this machine forever and never
existed anywhere else.

The rule had already been learnt once and not generalised. `.gitignore`'s own
comment two lines below says `logs/` was anchored after it swallowed
`docs/qa/logs/` — *"a test log nobody can review"*. The same mistake sat
directly above it, unfixed, because the earlier repair fixed the instance rather
than the class.

This is the session's recurring shape once more: **a check that cannot reach the
thing it describes returns the answer you were hoping for.** A green suite says
nothing about whether the suite is in the repository.

**What a careless version of this test would assert.** That `.gitignore`
contains no unanchored patterns — too strict, since `__pycache__/` and `*.pyc`
are meant to match everywhere. The question is not how a pattern is written but
whether any file the test runner collects is one git would refuse to store.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SUITES = ("tests", "qa/regression-suite")


def collected_files() -> list[Path]:
    """Every test module the runner would import, found the way it finds them."""
    found: list[Path] = []
    for suite in SUITES:
        for path in sorted((ROOT / suite).rglob("test_*.py")):
            if "__pycache__" not in path.parts:
                found.append(path)
    return found


def test_every_test_module_is_one_git_would_store() -> None:
    inside_a_repo = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if inside_a_repo.returncode != 0:  # pragma: no cover - a source export, not a clone
        pytest.skip("not a git checkout, so there is nothing to be ignored by")

    modules = collected_files()
    assert modules, "no test modules were found at all, so this proves nothing"

    # `check-ignore` answers the only question that matters — would git store
    # this file — rather than reimplementing pattern matching, which is how a
    # test of `.gitignore` ends up with `.gitignore`'s bug.
    result = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        cwd=ROOT,
        input="\n".join(str(path.relative_to(ROOT)) for path in modules),
        capture_output=True,
        text=True,
    )
    ignored = [line for line in result.stdout.splitlines() if line.strip()]

    assert not ignored, (
        f"{len(ignored)} test module(s) are ignored by .gitignore and would never "
        f"be committed: {ignored[:5]}. They run here and exist nowhere else. "
        "The usual cause is an unanchored directory pattern — `data/` matches a "
        "directory of that name at any depth; `/data/` matches only the one at "
        "the repository root."
    )


def test_the_conftests_the_suites_depend_on_are_stored_too() -> None:
    """A tracked test importing an ignored fixture file fails for everyone else.

    The worse version of the same defect: the suite *is* in the repository and
    does not run, which reads as a broken checkout rather than a missing file.
    """
    conftests = [
        path
        for suite in SUITES
        for path in sorted((ROOT / suite).rglob("conftest.py"))
        if "__pycache__" not in path.parts
    ]
    assert conftests, "no conftest.py was found, so this proves nothing"

    result = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        cwd=ROOT,
        input="\n".join(str(path.relative_to(ROOT)) for path in conftests),
        capture_output=True,
        text=True,
    )
    assert not result.stdout.strip(), f"ignored conftest(s): {result.stdout.split()[:5]}"
