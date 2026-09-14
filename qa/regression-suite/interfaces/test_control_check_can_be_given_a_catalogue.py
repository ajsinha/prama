"""The CI gate can type-check, which needs something to check against.

QA round 4, finding `Q-82`, from `CLI-109` and `CLI-110`. `cli/control.py` read:

    checker = TypeChecker(Catalogue())

An empty catalogue, unconditionally, and `prama control check --help` offered
only `--strict`. So every dataset reference resolved to `[unchecked] nothing is
known about …`, a clean file never printed "Nothing to report.", and a column of
the wrong type could not be detected at all. Neither case could pass, and no
fixture made them pass.

The command's own help says *"parse, type-check and lint"*, and `CLAUDE.md`
lists it as the CI gate: *"`prama control check suite.pql` — parse, type-check
and lint; non-zero on error"*. Two of those three worked.

**The sharper statement of the defect is the remedy.** The `[unchecked]`
diagnostic said *"Declare positions_eod, or bind it to a source so its columns
can be discovered."* Declaring it changed nothing, because the CLI never looked.
An unfollowable remedy is worse than a bare refusal: it sends somebody to do
work that cannot help, and they conclude the tool is broken in some other way.

**The repair is not a new mechanism.** `prama lsp catalogue` already exports the
estate's schemas to a file and `prama lsp serve --catalogue` already consumes
it, through `load_catalogue`, which refuses a missing file rather than silently
falling back to an empty one — *"an empty catalogue silently turns every schema
check off, and the editor then shows a clean file that has not been checked"*.
The gate now takes the same flag, reads it with the same loader, and inherits
that refusal.

**What a careless version of this test would do.** Assert that `--catalogue`
exists, or that the command exits 0 with one. Both pass against a `--catalogue`
that is parsed and ignored. The assertions below require the catalogue to change
the *findings*: an unchecked warning must disappear, and a type error that was
invisible must appear.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PRAMA = shutil.which("prama")


def run(*argv: str) -> subprocess.CompletedProcess[str]:
    if PRAMA is None:  # pragma: no cover - depends on how the venv was built
        pytest.skip("the `prama` console script is not on PATH")
    return subprocess.run([PRAMA, *argv], capture_output=True, text=True, timeout=120)


@pytest.fixture
def estate(tmp_path: Path) -> dict[str, Path]:
    """A catalogue file, a clean control, and one with a type error."""
    catalogue = tmp_path / "catalogue.json"
    # The shape `prama lsp catalogue` writes and `load_catalogue` reads: a
    # mapping of dataset name to a mapping of column name to type. Written from
    # the loader rather than from memory — the first draft of this fixture
    # invented a list of objects and the tests failed on the refusal rather than
    # on the defect.
    catalogue.write_text(
        json.dumps(
            {
                "written_at": "2026-09-14T00:00:00Z",
                "datasets": {
                    "positions_eod": {
                        "isin": "text",
                        "account_id": "text",
                        "notional_amount": "numeric",
                    }
                },
            }
        )
    )

    clean = tmp_path / "clean.pql"
    clean.write_text(
        "CHECK positions_eod.isin IS NOT NULL\n"
        "  SEVERITY major DIMENSION completeness BECAUSE 'every position has an instrument'\n"
    )

    # MATCHES is a text operation; notional_amount is numeric. Invisible without
    # a catalogue, because nothing knows the column's type.
    type_error = tmp_path / "typeerr.pql"
    type_error.write_text(
        "CHECK positions_eod.notional_amount MATCHES /abc/\n"
        "  SEVERITY major DIMENSION validity BECAUSE 'x'\n"
    )
    return {"catalogue": catalogue, "clean": clean, "type_error": type_error}


def test_a_clean_control_is_clean_when_the_columns_are_known(estate) -> None:
    """`CLI-109`. Without a catalogue this can never be reached."""
    result = run("control", "check", str(estate["clean"]), "--catalogue", str(estate["catalogue"]))
    combined = result.stdout + result.stderr

    assert "[unchecked]" not in combined, (
        "the checker still says nothing is known about positions_eod, so the "
        f"catalogue was not consulted:\n{combined[:400]}"
    )
    assert "Nothing to report." in combined, f"expected a clean report:\n{combined[:400]}"
    assert result.returncode == 0


def test_a_type_error_is_found_when_the_column_types_are_known(estate) -> None:
    """`CLI-110`. The half of "parse, type-check and lint" that never ran."""
    result = run(
        "control", "check", str(estate["type_error"]), "--catalogue", str(estate["catalogue"])
    )
    combined = (result.stdout + result.stderr).lower()

    assert result.returncode == 1, (
        f"a type error exited {result.returncode}; the CI gate would not have stopped it"
    )
    assert "notional_amount" in combined, "the finding does not name the offending column"


def test_without_a_catalogue_it_says_so_rather_than_passing_quietly(estate) -> None:
    """The behaviour that was already right, and must stay right.

    An empty catalogue is not an error — checking a file with no estate to hand
    is legitimate — but it must be visible. The `[unchecked]` diagnostic is the
    thing that keeps a green run honest, and the repair must not silence it by
    making the absent case look clean.
    """
    result = run("control", "check", str(estate["clean"]))
    combined = result.stdout + result.stderr

    assert "[unchecked]" in combined, (
        "without a catalogue the checker reported nothing unchecked, so a file "
        f"nobody verified now reads as verified:\n{combined[:400]}"
    )


def test_a_missing_catalogue_is_refused_not_ignored(estate, tmp_path: Path) -> None:
    """`load_catalogue`'s own rule, inherited rather than reimplemented.

    A `--catalogue` pointing at nothing must refuse. Falling back to an empty
    catalogue would produce a green run that checked no schemas while the caller
    believes they supplied one — strictly worse than not offering the flag.
    """
    result = run(
        "control", "check", str(estate["clean"]), "--catalogue", str(tmp_path / "absent.json")
    )
    combined = result.stdout + result.stderr

    assert result.returncode != 0, "a missing catalogue was ignored"
    assert "Traceback" not in combined, f"refused with a stack trace:\n{combined[-400:]}"
    assert "code:" in combined, f"refused without a taxonomy code:\n{combined[-400:]}"
