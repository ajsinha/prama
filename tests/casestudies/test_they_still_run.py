"""The case studies still run.

QA found all four dead on committed code: `require_current` and `activate` had
gained a required `tenant_id` and the harness was never updated, so
`cd case-studies/01-trading-book-sqlite && python run.py` — the command both
README and QUICKSTART give as "see it actually do something" — died with a
TypeError. A second defect sat behind it: `harness.serve()` calls
`uvicorn.run()`, which calls `asyncio.run()`, from inside a function already
running under one.

**Nothing under `tests/` exercised `case-studies/`.** They are the product's
own demonstration that it works, they are the first thing a new reader runs,
and they were the last thing anybody checked.

These are slow — each builds a database and runs an estate — so they are marked
and excluded from the default run. `pytest -m casestudy` is the gate that
matters before a release, and `scripts/gate.sh` runs it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

STUDIES = Path(__file__).resolve().parents[2] / "case-studies"

pytestmark = pytest.mark.casestudy


def study_directories() -> list[Path]:
    return sorted(p for p in STUDIES.glob("0*") if (p / "run.py").is_file())


def test_there_are_studies_to_run() -> None:
    """Anti-vacuity. A glob that matched nothing would make every test below
    pass by not existing."""
    assert len(study_directories()) >= 4


@pytest.mark.parametrize("study", study_directories(), ids=lambda p: p.name)
def test_it_runs_to_completion(study: Path, tmp_path: Path) -> None:
    """Run it the way the documentation says to, and require exit 0.

    `--no-serve` because the console would block; the serving path is covered
    by `test_serve_is_not_called_inside_the_loop` below, which is the half that
    was broken.
    """
    result = subprocess.run(
        [sys.executable, "run.py", "--no-serve"],
        cwd=study,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert result.returncode == 0, (
        f"{study.name} exited {result.returncode}\n"
        f"--- stdout (tail) ---\n{result.stdout[-2000:]}\n"
        f"--- stderr (tail) ---\n{result.stderr[-2000:]}"
    )


@pytest.mark.parametrize("study", study_directories(), ids=lambda p: p.name)
def test_serve_is_not_called_inside_the_loop(study: Path) -> None:
    """`uvicorn.run` cannot start inside a running event loop.

    Checked by reading rather than by running, because starting the console
    here would block. What is asserted is the shape that broke: `main` is a
    coroutine, so a `harness.serve(...)` inside it is unreachable code that
    raises the moment somebody omits `--no-serve` — which is the default.
    """
    import ast

    tree = ast.parse((study / "run.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "serve"
            ):
                pytest.fail(
                    f"{study.name}: harness.serve() is called inside the coroutine "
                    f"{node.name!r} at line {inner.lineno}. uvicorn.run calls "
                    "asyncio.run, which cannot start inside a running loop."
                )
