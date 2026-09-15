"""A regular expression is validated where it is written, not where it runs.

QA round 4, `BE-016` and `BE-015`. Nothing validated a `MATCHES` pattern
anywhere. `/[/` parsed without complaint and was first noticed by `re.compile`
inside the reference interpreter, or by the engine itself, at execution — a run
that starts, costs a scan, and then fails, instead of a control that never
compiles.

**`BE-015` is the more interesting half, and the triage's account of it was
wrong in a way worth recording.** It said a non-portable feature makes engines
"silently match different rows". Measured against a real DuckDB, the
lookaround and backreference cases are not silent at all — RE2 rejects them
outright with `InvalidInputException`. What was silent was the *timing*: the
control compiled, the run began, and the engine refused mid-flight on one engine
only, while the interpreter and SQLite were perfectly happy.

**Two genuinely silent divergences do exist, and neither is fixed here.**
Measured, not assumed:

* `\\d` is Unicode-aware in Python and ASCII-only in RE2, so `/^\\d+$/` matches
  `١٢٣` on SQLite and on the interpreter and not on DuckDB — no error on either
  side, different rows, same control.
* `[[:alpha:]]` is a POSIX class RE2 honours and Python reads as a nested set,
  so it matches on DuckDB and not on SQLite.

Neither can be found by scanning a pattern for forbidden constructs, because
nothing about the pattern is forbidden — the flavours simply disagree about what
it means. Refusing `\\d` outright is not defensible; it is the most common
construct in the language. They are recorded as known divergences rather than
repaired, and this docstring is the record. **A fix that covered the loud cases
and left these unstated would read as if the problem were solved.**

**What a careless version of this test would assert.** That a malformed pattern
raises *somewhere* in the pipeline — true before the repair, at the wrong,
later, much less useful point. The assertion below is on *when*: at `parse`,
before an IR plan exists.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.backend.dialect import re2_gap
from prama.backend.sql import SqlCompiler
from prama.ir.lower import Lowerer
from prama.pql.errors import PqlSyntaxError, PqlUnsupportedError
from prama.pql.parser import parse_control

VALID = r"^[A-Z]{2}[0-9A-Z]{9}[0-9]$"


def control_with(pattern: str) -> str:
    return (
        f"CHECK corpus.isin MATCHES /{pattern}/ "
        "SEVERITY major DIMENSION validity BECAUSE 'an ISIN has a shape'"
    )


# -- BE-016: the pattern is checked at parse time ---------------------------


# Not `*x`: `/*` opens a block comment, so the lexer refuses it earlier and for
# a different reason. A case that passes for the wrong reason is worse than no
# case, and this one would have read as proof the pattern gate works.
@pytest.mark.parametrize("pattern", ["[", "(", "a{2,1}", "a**", "[a-"], ids=str)
def test_a_malformed_pattern_is_refused_by_the_parser(pattern: str) -> None:
    with pytest.raises(PqlSyntaxError) as caught:
        parse_control(control_with(pattern))
    assert "regular expression" in str(caught.value)


def test_it_is_refused_at_parse_not_at_execution() -> None:
    """The point of the repair is *when*, so that is what is asserted.

    A control that only fails once an engine is running has already cost a
    connection and a scan, and the error arrives attributed to the engine.
    """
    with pytest.raises(PqlSyntaxError):
        parse_control(control_with("["))


def test_a_valid_pattern_still_parses() -> None:
    """The counterfactual. Refusing every pattern would satisfy the above."""
    control = parse_control(control_with(VALID))
    assert control is not None


# -- BE-015: RE2's gaps are a refusal, not a mid-run engine error -----------


@pytest.mark.parametrize(
    "pattern,gap",
    [
        ("(?<=a)b", "lookbehind"),
        ("(?<!a)b", "negative lookbehind"),
        ("a(?=b)", "lookahead"),
        ("a(?!b)", "negative lookahead"),
        (r"(a)\1", "a backreference"),
    ],
    ids=["lookbehind", "neg-lookbehind", "lookahead", "neg-lookahead", "backreference"],
)
def test_duckdb_refuses_a_pattern_re2_cannot_run(pattern: str, gap: str) -> None:
    plan = Lowerer().control(parse_control(control_with(pattern)))

    with pytest.raises(PqlUnsupportedError) as caught:
        SqlCompiler("duckdb").compile(plan, table="corpus")

    assert gap in str(caught.value), f"the refusal does not name the construct: {caught.value}"


@pytest.mark.parametrize("pattern", ["(?:ab)+", "(?i)abc", "(?P<x>a)", VALID], ids=str)
def test_the_detector_does_not_refuse_what_re2_supports(pattern: str) -> None:
    """The counterfactual, and the one that decides whether this is any good.

    Non-capturing groups, inline flags and named groups all look like the
    constructs above and are all fine in RE2. A detector that refused them would
    make DuckDB useless for patterns while appearing to fix a portability bug.
    """
    assert re2_gap(pattern) == ""
    plan = Lowerer().control(parse_control(control_with(pattern)))
    assert SqlCompiler("duckdb").compile(plan, table="corpus").metric_query


def test_sqlite_still_accepts_what_pythons_re_supports() -> None:
    """SQLite runs Python's `re`, so a lookbehind is legitimate there.

    Refusing it everywhere would be the easy over-correction: one rule, applied
    uniformly, removing a capability from the engine that actually has it.
    """
    plan = Lowerer().control(parse_control(control_with("(?<=a)b")))
    assert SqlCompiler("sqlite").compile(plan, table="corpus").metric_query


# -- BE-075 / the silent divergences: stated, not claimed -------------------


def test_the_known_silent_divergences_are_written_down() -> None:
    """Asserted on the record, because the record is the deliverable.

    `\\d` and POSIX character classes mean different things to Python's `re` and
    to RE2, and no scan of a pattern can detect it — nothing about the pattern is
    wrong. If a later change deletes the note, the repair starts reading as
    though it covered everything.
    """
    import inspect
    import sys

    import prama.backend.dialect  # noqa: F401 - imported for sys.modules

    # By name from `sys.modules`, not `from prama.backend import dialect`, which
    # resolves to the re-exported *function* of that name and reads its source
    # instead of the module's.
    note = inspect.getsource(sys.modules["prama.backend.dialect"])
    assert "ASCII-only in RE2" in note, (
        "the note recording the `\\d` divergence is gone, so the RE2 check now "
        "reads as a complete portability guarantee"
    )


@pytest.mark.parametrize("pattern", [r"(a+)+b", r"(a|a)*c"], ids=["nested-plus", "alternation"])
def test_a_catastrophic_pattern_is_not_claimed_to_be_handled(pattern: str) -> None:
    """`BE-075`, recorded as unfixed rather than quietly left out.

    A pattern like `(a+)+b` does not complete against a long non-matching
    subject in Python's backtracking engine — a denial of service against the
    interpreter, reachable from an authored control. Static ReDoS detection is
    not reliable, and the triage said to budget it separately.

    So this test asserts what is true today: such a pattern parses. It exists so
    that the day a runtime bound is added, this test fails and somebody has to
    come back and say so.
    """
    assert parse_control(control_with(pattern)) is not None
    assert re2_gap(pattern) == "", "the RE2 check is not a ReDoS check and must not pretend to be"
