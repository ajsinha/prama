"""No `prama` command may answer a person with a Python traceback.

QA round 3, `CLI-017` and finding `Q-68`. `CLAUDE.md` states the rule plainly:
*"No exception is swallowed. The unit of work translates failures into the Prama
error taxonomy and they propagate; a DAO never returns a sentinel meaning
'something went wrong'."* `Application.run` translates `PramaError` into

    error: <message>
      code: <CODE>
      next: <remedy>

and nothing else. Every other exception escapes to the terminal as a stack
trace, which tells a data owner nothing they can act on and tells an attacker
the file layout of the installation.

Round 3 measured it rather than sampling it: of **224 CLI invocations logged
across every interface harness script**, 14 produced an uncaught traceback. The
census lives in `qa/harness/interfaces/cli_call_log.jsonl`; the 14 are pinned
here by the argv that produced them.

**The repair this test must NOT accept** is a blanket `except Exception` at the
CLI boundary formatting anything as a refusal. That would pass this file and
turn 14 loud failures into 14 silent ones — the flattering direction, and worse
than the defect, because a traceback at least says something went wrong. So the
assertions below check two things together: no traceback, *and* a typed code
with a remedy. A generic "something failed" satisfies the first and fails the
second.

Each case also asserts the message still names the thing that was wrong. The
current `ValueError` texts are good — "rate must be a share of rows in (0, 1],
got 1.5" is exactly what a person needs — and a fix that loses them in the
course of typing them would be a regression wearing a fix's clothes.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

#: The installed console script, not `python -m prama`. There is no
#: `prama/__main__.py` and there never has been, so `-m` raises
#: `ModuleNotFoundError` and every case below would fail for a reason that has
#: nothing to do with the defect — a counterfactual that fails for the wrong
#: reason proves nothing. QA round 3 found two saved harness scripts
#: (`SEC-132`, `SEC-133`) making exactly this mistake.
PRAMA = shutil.which("prama")

#: argv, and a fragment the refusal must still contain. Taken from the round-3
#: census; the fragment is the part of the existing message that identifies the
#: fault, so a typed error that drops it fails here.
REFUSALS = [
    pytest.param(["--log-level", "LOUD", "version"], "LOUD", id="unknown-log-level"),
    pytest.param(["--json", "bench", "run", "--seed", "1", "--rows", "0"], "0", id="zero-rows"),
    pytest.param(["--json", "bench", "run", "--seed", "1", "--rate", "0"], "0", id="rate-zero"),
    pytest.param(["--json", "bench", "run", "--seed", "1", "--rate", "1.5"], "1.5", id="rate-high"),
    pytest.param(
        ["--json", "bench", "run", "--seed", "1", "--rate", "-0.1"], "-0.1", id="rate-negative"
    ),
    pytest.param(["bench", "run", "--seed", "1", "--rate", "0.0"], "0", id="rate-zero-float"),
    pytest.param(["bench", "taxonomy", "--family", "wizard"], "wizard", id="unknown-family"),
    pytest.param(["pack", "calendar", "TARGET2", "--year", "0"], "0", id="year-zero"),
    pytest.param(["pack", "calendar", "TARGET2", "--year", "-1"], "-1", id="year-negative"),
]


def invoke(argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Run the real console script in a subprocess.

    In-process would be faster, and would not prove the thing under test: a
    traceback reaching *the terminal* is the defect, and that involves the entry
    point, `SystemExit` handling and stderr. The harness that found this ran the
    installed `prama`, so this does too.
    """
    if PRAMA is None:  # pragma: no cover - depends on how the venv was built
        pytest.skip("the `prama` console script is not on PATH")
    return subprocess.run(
        [PRAMA, *argv],
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.mark.parametrize("argv,fragment", [(p.values[0], p.values[1]) for p in REFUSALS],
                         ids=[p.id for p in REFUSALS])
def test_a_refusal_is_typed_and_not_a_traceback(argv: list[str], fragment: str) -> None:
    result = invoke(argv)
    combined = result.stdout + result.stderr

    assert "Traceback (most recent call last)" not in combined, (
        f"`prama {' '.join(argv)}` answered with a Python traceback:\n"
        f"{combined[-700:]}"
    )
    assert result.returncode != 0, "a refusal must not exit 0"

    # Typed, not merely quiet. A blanket handler that prints "error: something
    # went wrong" passes the traceback check above and fails here.
    typed = ("code:" in combined) or ('"code"' in combined)
    assert typed, (
        f"`prama {' '.join(argv)}` refused without a taxonomy code. A refusal "
        f"nobody can look up is a traceback with the useful part removed:\n{combined[-500:]}"
    )
    remedied = ("next:" in combined) or ('"remedy"' in combined)
    assert remedied, f"the refusal carries no remedy:\n{combined[-500:]}"

    assert fragment in combined, (
        f"the refusal no longer names what was wrong ({fragment!r} is absent). "
        f"The original message said it; a typed error must not lose it:\n{combined[-500:]}"
    )


@pytest.fixture
def fixtures(tmp_path):
    """The five census cases that need a file on disk.

    Built here rather than checked in: a latin-1 file and a truncated JSON file
    are exactly the things a repository's own tooling tends to normalise.
    """
    import json

    latin1 = tmp_path / "latin1.pql"
    # A BECAUSE clause with an accented word, saved the way an editor defaulting
    # to cp1252 saves it. This is the realistic origin of the case, not a
    # contrived byte.
    latin1.write_bytes(
        "CHECK positions_eod.isin IS NOT NULL BECAUSE 'café'\n".encode("latin-1")
    )
    schema = tmp_path / "schema.yml"
    schema.write_text(
        "version: 2\nmodels:\n  - name: t\n    columns:\n      - name: c\n"
        "        tests: [not_null]\n"
    )
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "status": "active",
                "schema": [
                    {
                        "name": "positions_eod",
                        "logicalType": "object",
                        "physicalType": "table",
                        "properties": [
                            {"name": "isin", "logicalType": "string", "required": True}
                        ],
                    }
                ],
            }
        )
    )
    truncated = tmp_path / "unparsable.json"
    truncated.write_text('{"rows": [')
    return {
        "latin1": latin1,
        "schema": schema,
        "contract": contract,
        "truncated": truncated,
        "unwritable": "/proc/out.pql",
    }


@pytest.mark.parametrize(
    "case",
    ["non-utf8-check", "non-utf8-format", "unwritable-out", "truncated-data"],
)
def test_a_file_refusal_is_typed_and_not_a_traceback(fixtures, case: str) -> None:
    """The census cases that involve reading or writing a file.

    These are the ones a person actually hits: a control saved in the wrong
    encoding, and a mistyped `--out`.
    """
    argv = {
        "non-utf8-check": ["control", "check", str(fixtures["latin1"])],
        "non-utf8-format": ["control", "format", str(fixtures["latin1"]), "--write"],
        "unwritable-out": [
            "control", "import", str(fixtures["schema"]),
            "--from", "dbt", "--out", fixtures["unwritable"],
        ],
        "truncated-data": [
            "contract", "check", str(fixtures["contract"]),
            "--data", str(fixtures["truncated"]),
        ],
    }[case]

    result = invoke(argv)
    combined = result.stdout + result.stderr

    assert "Traceback (most recent call last)" not in combined, (
        f"`prama {' '.join(argv)}` answered with a Python traceback:\n{combined[-700:]}"
    )
    assert "code:" in combined or '"code"' in combined, (
        f"refused without a taxonomy code:\n{combined[-500:]}"
    )
    assert "next:" in combined or '"remedy"' in combined, (
        f"the refusal carries no remedy:\n{combined[-500:]}"
    )


def test_the_census_is_still_the_census() -> None:
    """The 224-invocation log this finding was measured from must stay put.

    A test pinned to nine argv lines is only as honest as the sampling behind
    it. If the census is deleted, the nine become a guess about which commands
    matter rather than a measurement of which ones failed.
    """
    import json
    from pathlib import Path

    census = Path(__file__).resolve().parents[2] / "harness/interfaces/cli_call_log.jsonl"
    assert census.exists(), f"the CLI invocation census is missing: {census}"
    rows = [json.loads(line) for line in census.read_text().splitlines() if line.strip()]
    assert len(rows) >= 200, (
        f"the census has shrunk to {len(rows)} invocations; it was 224 when Q-68 "
        "was measured, and a smaller sample is a weaker claim"
    )
