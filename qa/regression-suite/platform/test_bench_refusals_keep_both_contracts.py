"""`bench.corpus` refuses with `ValueError`; the CLI turns that into a typed error.

QA rounds 3 and 4, findings `Q-68` and `Q-77`. Two contracts meet here and the
first attempt satisfied one by breaking the other.

`Q-68`: `prama bench run --rows 0` answered with a Python traceback, because
`Application.run` translates only `PramaError` and `corpus.build` raised a bare
`ValueError`. Batch B fixed that by raising `ValidationError` from the library.

`Q-77`: that broke `BCH-015` and `BCH-016`, whose catalogue `Expected` names
`ValueError` — and, more to the point, broke every caller written as
`except ValueError`. One such caller existed and was the saved harness
`bch_001_061.py`, which crashed mid-run and took 45 downstream cases with it
until repaired. `corpus.build` is a library function in a package whose purpose
is to be driven by other people's benchmark scripts, and `rate=1.5` is exactly
what Python's `ValueError` means: right type, wrong value.

The resolution keeps both. The library raises `ValueError`; the CLI command
translates at its boundary, which is what `CLAUDE.md` describes — *"the unit of
work translates failures into the Prama error taxonomy"* — translation **at a
boundary**, not taxonomy all the way down.

**This file asserts both halves together on purpose.** Either one alone can be
satisfied by reintroducing the other's defect: assert only the `ValueError` and
the traceback comes back; assert only the typed refusal and the library contract
breaks again. A fix that trades one for the other passes half of this file.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from prama.bench import corpus
from prama.core.errors import PramaError

PRAMA = shutil.which("prama")

#: The bad arguments, and the fragment the refusal must still name. Taken from
#: `BCH-015`/`BCH-016` and round 3's traceback census.
BAD = [
    pytest.param({"rate": 0.0}, "0", id="rate-zero"),
    pytest.param({"rate": -0.1}, "-0.1", id="rate-negative"),
    pytest.param({"rate": 1.5}, "1.5", id="rate-above-one"),
    pytest.param({"rows": 0}, "0", id="rows-zero"),
]


@pytest.mark.parametrize(
    "kwargs,fragment", [(p.values[0], p.values[1]) for p in BAD], ids=[p.id for p in BAD]
)
def test_the_library_refuses_with_a_plain_value_error(kwargs: dict, fragment: str) -> None:
    """The half `Q-77` is about: a caller may write `except ValueError`."""
    with pytest.raises(ValueError) as caught:
        corpus.build(seed=1, **kwargs)

    assert fragment in str(caught.value), (
        f"the refusal no longer names the bad value ({fragment!r} absent): {caught.value}"
    )
    # Not a PramaError wearing a ValueError's name. If the taxonomy is ever made
    # to inherit ValueError, this is the assertion that should be reconsidered
    # deliberately rather than silently satisfied.
    assert not isinstance(caught.value, PramaError), (
        "the library raises a taxonomy error again; a caller catching ValueError "
        "only works here by inheritance, which is not what Q-77 decided"
    )


@pytest.mark.parametrize(
    "argv,fragment",
    [
        (["bench", "run", "--seed", "1", "--rows", "0"], "0"),
        (["bench", "run", "--seed", "1", "--rate", "1.5"], "1.5"),
        (["bench", "run", "--seed", "1", "--rate", "-0.1"], "-0.1"),
    ],
    ids=["rows-zero", "rate-above-one", "rate-negative"],
)
def test_the_cli_answers_with_a_typed_refusal_not_a_traceback(
    argv: list[str], fragment: str
) -> None:
    """The half `Q-68` is about: no stack trace reaches a person.

    Runs the installed console script rather than `python -m prama`, which has
    never worked — there is no `prama/__main__.py`, so `-m` fails with
    `ModuleNotFoundError` and every case would fail for a reason unrelated to
    the defect. Round 3 found two saved harnesses making that mistake, and the
    first draft of this round's traceback test made it again.
    """
    if PRAMA is None:  # pragma: no cover - depends on how the venv was built
        pytest.skip("the `prama` console script is not on PATH")
    result = subprocess.run([PRAMA, *argv], capture_output=True, text=True, timeout=120)
    combined = result.stdout + result.stderr

    assert "Traceback (most recent call last)" not in combined, (
        f"`prama {' '.join(argv)}` answered with a stack trace:\n{combined[-700:]}"
    )
    assert result.returncode != 0, "a refusal must not exit 0"
    assert "code:" in combined, f"refused without a taxonomy code:\n{combined[-400:]}"
    assert "next:" in combined, f"the refusal carries no remedy:\n{combined[-400:]}"
    assert fragment in combined, (
        f"the refusal no longer names what was wrong ({fragment!r} absent):\n{combined[-400:]}"
    )


def test_the_translation_lives_at_the_boundary_and_not_in_the_library() -> None:
    """Asserted on the source, so the two halves cannot drift back together.

    The response tests above both pass if somebody moves the taxonomy back into
    `corpus.build` *and* the CLI stops translating — for one release, until a
    caller notices. This names where the translation belongs.
    """
    import inspect

    # `raise ValidationError`, not the bare word: the function's comment explains
    # why the taxonomy is NOT raised here, and a substring check on the name
    # fails on that explanation. A test that cannot tell a prohibition from its
    # own rationale is the kind of check this suite exists to be sceptical of.
    library = inspect.getsource(corpus.build)
    assert "raise ValidationError" not in library, (
        "bench.corpus.build raises the taxonomy again; Q-77 decided the library "
        "keeps ValueError and the CLI translates"
    )
    assert "raise ValueError" in library, "the library no longer refuses at all"

    from prama.cli import bench as cli_bench

    command = inspect.getsource(cli_bench)
    assert "ValueError" in command and "ValidationError" in command, (
        "prama.cli.bench no longer translates ValueError into the taxonomy, so a "
        "bad --rate or --rows will reach the terminal as a stack trace"
    )
