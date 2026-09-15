"""The conformance harness cannot call silence agreement.

QA round 4, `BE-135` and `BE-139`. This is the file the release gate rests on.
`CLAUDE.md`: *"Assert the rendered artefact, not the intent. Assert the executed
verdict on real data… The IR conformance suite is this habit as a release
gate."* Two functions in it could not tell "nobody answered" from "everybody
agreed".

`BE-135`. `compare()` built a set of distinct answers and reported a
disagreement when it held more than one. A set of **one** answer is trivially
unanimous, so a case only the reference interpreter could run was scored as
agreement. Run against the interpreter alone, the harness reported:

    conforming: True | cases_compared: 0 / 25

The number that contradicts the verdict was printed directly beside it — a
previous finding (T7) had added `cases_compared` for exactly this reason — and
the verdict never consulted it. **Measuring the right thing and not deciding on
it is a distinct failure from not measuring it**, and it looks healthier,
because the report contains the evidence that it is wrong.

`BE-139`. `_compare_two_stage` returned `[]` — no disagreements — whenever the
reference interpreter had not answered. The two-stage comparison is the
product's actual thesis: a SQL screen plus an exact check, each catching what
the other cannot. The single most valuable comparison in the suite was the one
that could be skipped without a word.

**What a careless version of this test would assert.** That `disagreements == []`
for a healthy run, or that a reference-only run produces *some* disagreement.
The first passes on the broken code. The second is close but weak — the
assertion below is on `conforming`, because that is the field a release decision
reads, and on `cases_compared`, because a gate that is green while it compared
nothing is the exact failure.

**The counterfactual that matters is the control.** Making the harness stricter
is easy and useless if it also fails a genuine run. `tests/backend` exercises the
real DuckDB and SQLite engines over all 25 cases and must stay green.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

import pytest

from prama.backend.conformance import ConformanceRun
from prama.backend.corpus import CASES, COLUMNS, ROWS


def corpus_rows() -> list[dict[str, Any]]:
    return [dict(zip([name for name, _ in COLUMNS], row, strict=True)) for row in ROWS]


def test_a_run_nobody_compared_is_not_conforming() -> None:
    """`BE-135`. The interpreter alone cannot establish that engines agree."""
    run = ConformanceRun(rows=corpus_rows())
    report = run.summarise({"reference": lambda _sql: []})

    assert report["cases_compared"] == 0, (
        "this test's premise is gone: something other than the reference answered"
    )
    assert not report["conforming"], (
        "the harness reported conforming against a run in which no case was "
        f"compared by two engines. cases_compared={report['cases_compared']} of "
        f"{report['cases']}, engines_that_ran={report['engines_that_ran']}"
    )


def test_the_refusal_says_how_many_answered() -> None:
    """A gate that fails without saying why sends people to the wrong place.

    "Not conforming" on a corpus that is in fact fine reads as a product defect
    until somebody notices only one engine was present.
    """
    run = ConformanceRun(rows=corpus_rows())
    rendered = " ".join(run.summarise({"reference": lambda _sql: []})["disagreements"])

    assert "answered" in rendered and "two" in rendered, (
        f"the report does not say the problem is how many engines answered: {rendered[:300]}"
    )


def test_a_two_stage_case_with_no_reference_is_not_silently_excused() -> None:
    """`BE-139`. The comparison the product's thesis rests on."""
    two_stage = [case for case in CASES if ConformanceRun().plan_for(case).is_two_stage]
    assert two_stage, "no two-stage case in the corpus, so this proves nothing"

    found = ConformanceRun._compare_two_stage(two_stage[0], {})
    assert found, (
        "a two-stage case whose reference interpreter did not answer reported no "
        "disagreement, so the screen-versus-exact comparison was skipped silently"
    )
    assert "reference" in found[0].outcomes


def test_a_genuine_two_engine_run_still_conforms() -> None:
    """The control, and the one that decides whether the repair is any good.

    Making a gate stricter is easy; making it stricter without failing honest
    runs is the work. This runs the real corpus against a real DuckDB alongside
    the interpreter — two independent implementations, which is what the suite
    is for.
    """
    duckdb = pytest.importorskip("duckdb")
    from prama.backend.corpus import create_table, insert_rows

    connection = duckdb.connect()
    connection.execute(create_table(dialect="duckdb"))
    connection.executemany(insert_rows(), [list(row) for row in ROWS])

    def run_sql(sql: str) -> list[dict[str, Any]]:
        relation = connection.sql(sql)
        names = [description[0] for description in relation.description]
        return [dict(zip(names, row, strict=True)) for row in relation.fetchall()]

    report = ConformanceRun(rows=corpus_rows()).summarise(
        {"reference": lambda _sql: [], "duckdb": run_sql}
    )
    connection.close()

    assert report["cases_compared"] > 0, "the run compared nothing, so it proves nothing"
    assert report["conforming"], (
        "a genuine two-engine run is now reported as non-conforming — the repair "
        f"fails honest runs: {report['disagreements'][:3]}"
    )
