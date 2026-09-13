"""Findings a QA pass made against a corpus with known defect counts.

Each was reported by an agent driving the product the way a person does, and
each was reproduced by hand before being acted on. They share a shape, which
the agent's own summary named better than I would have:

    the paths that decide "nothing to report" are weaker than the paths that
    decide "something to report".

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sqlite3

import pytest

from prama.connect.sources.query import register_regexp


class TestANullIsUnknownNotANonMatch:
    """Finding Q-12. `register_regexp` returned `False` for a null.

    Its own docstring said the opposite — "a null is neither matching nor
    non-matching, and the control's TREAT UNKNOWN policy decides what that
    means" — and `False` is a definite non-match. So a null reaching a validity
    check was a certain violation, the unknown policy never saw it, and
    `TREAT UNKNOWN AS PASS` could not rescue it. Measured: 11 violations on
    SQLite against 4 on DuckDB, same control, same rows.
    """

    def connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        register_regexp(conn)
        conn.execute("CREATE TABLE t (v TEXT)")
        conn.executemany("INSERT INTO t VALUES (?)", [("AAA",), (None,), ("zz",)])
        return conn

    def count(self, conn: sqlite3.Connection, where: str) -> int:
        return int(conn.execute(f"SELECT COUNT(*) FROM t WHERE {where}").fetchone()[0])

    def test_a_null_is_neither_matching_nor_non_matching(self) -> None:
        conn = self.connection()
        pattern = "'^[A-Z]+$'"
        assert self.count(conn, f"v REGEXP {pattern}") == 1
        assert self.count(conn, f"NOT (v REGEXP {pattern})") == 1
        assert self.count(conn, f"(v REGEXP {pattern}) IS NULL") == 1

    def test_the_three_account_for_every_row(self) -> None:
        """The property rather than three numbers: every row is matched,
        non-matched or unknown, and exactly one of them."""
        conn = self.connection()
        pattern = "'^[A-Z]+$'"
        total = (
            self.count(conn, f"v REGEXP {pattern}")
            + self.count(conn, f"NOT (v REGEXP {pattern})")
            + self.count(conn, f"(v REGEXP {pattern}) IS NULL")
        )
        assert total == 3

    def test_an_ordinary_match_is_unaffected(self) -> None:
        """The counterfactual. A hook that returned NULL for everything would
        satisfy the unknown assertion above and check nothing."""
        conn = self.connection()
        assert self.count(conn, "v REGEXP '^AAA$'") == 1
        assert self.count(conn, "v REGEXP '^nothing-matches-this$'") == 0


class TestALowerBoundSaysSoWhicheverWayItWent:
    """Finding Q-10. The caveat was attached only when the verdict would be a
    pass.

    A two-stage control's SQL is a screen, so its violation count is a lower
    bound *whatever* the verdict. The run recorded the caveat when the screen
    found zero — converting the pass to indeterminate — and said nothing when it
    found some, so 11-of-23 and 3-of-9 went into the ledger as completed
    measurements. Disclosed exactly when the understatement was zero, and silent
    whenever it was not.
    """

    def test_the_failing_branch_now_carries_the_caveat(self) -> None:
        """Read from the source, because constructing a half-compiled control
        with a live engine here would test the harness rather than the rule."""
        import inspect

        from prama.execute import run as run_module

        source = inspect.getsource(run_module.ControlRun._run_one)
        assert "LOWER BOUND" in source, (
            "a failing verdict from an incomplete screen must say the count is "
            "understated; it used to say nothing at all"
        )
        # And the pass branch keeps its own, stronger statement.
        assert "a pass cannot be reported from a screen alone" in source

    def test_the_caveat_is_not_inside_the_pass_branch(self) -> None:
        """The defect precisely: `if not complete and verdict == 'pass'`. The
        condition must not mention the verdict."""
        import inspect

        from prama.execute import run as run_module

        source = inspect.getsource(run_module.ControlRun._run_one)
        assert 'if not compiled.is_complete and verdict == "pass":' not in source


class TestEverySegmentIsJudged:
    """Finding Q-11. `_metrics_from` read `rows[0]` and nothing else.

    A segmented control returns one row per segment, so one segment of five
    decided the verdict, the totals came from that segment alone, and the
    samples in the same record contradicted its own metrics. `judge_segments`
    had been in the backend all along.
    """

    def test_segments_are_labelled_by_their_key(self) -> None:
        from prama.execute.run import _segments_from

        rows = [
            {"region": "EMEA", "scanned_rows": 10.0, "violating_rows": 3.0},
            {"region": "APAC", "scanned_rows": 10.0, "violating_rows": 0.0},
        ]
        pairs = _segments_from(rows, ("region",))
        assert [key for key, _ in pairs] == ["EMEA", "APAC"], (
            "a reader needs 'EMEA failed', not 'segment 3 failed'"
        )

    def test_every_segment_contributes(self) -> None:
        from prama.execute.run import _segments_from

        rows = [
            {"region": f"R{i}", "scanned_rows": 10.0, "violating_rows": float(i)} for i in range(5)
        ]
        pairs = _segments_from(rows, ("region",))
        assert len(pairs) == 5
        assert sum(m["violating_rows"] for _, m in pairs) == 10.0

    def test_the_run_uses_it(self) -> None:
        import inspect

        from prama.execute import run as run_module

        source = inspect.getsource(run_module.ControlRun._run_one)
        assert "judge_segments" in source, "a segmented control is still judged on rows[0]"


class TestTheEvidenceCarriesWhatTheVerdictWasBasedOn:
    """Finding Q-13. `judge` enriches a *copy* of the metrics.

    `violating_rows` for a uniqueness or functional-dependency control is not
    returned by any engine — Prama derives it from the two counts, because a
    duplicate cannot be identified row by row. That derivation lived inside the
    `ControlResult` and the run recorded the raw dict, so the ledger held the
    verdict and not the number it was based on.
    """

    def test_a_unique_key_derives_its_violations(self) -> None:
        from prama.backend.execute import _derive

        class Plan:
            assertion_kind = "unique_key"

        metrics = _derive(
            Plan(), {"scanned_rows": 100.0, "distinct_keys": 98.0, "null_key_rows": 0.0}
        )
        assert metrics["violating_rows"] == 2.0

    def test_a_dependency_derives_its_violations(self) -> None:
        from prama.backend.execute import _derive

        class Plan:
            assertion_kind = "functional_dependency"

        metrics = _derive(
            Plan(),
            {"scanned_rows": 100.0, "distinct_determinants": 10.0, "distinct_pairs": 12.0},
        )
        assert metrics["violating_rows"] == 2.0

    def test_the_run_records_the_derived_metrics(self) -> None:
        """The defect was the assignment, not the derivation."""
        import inspect

        from prama.execute import run as run_module

        source = inspect.getsource(run_module.ControlRun._run_one)
        assert "metrics = dict(result.metrics)" in source, (
            "the run records the raw metrics, so a derived violating_rows never reaches the ledger"
        )


class TestACodelistThatShipsIsACodelistThatCompiles:
    """Finding Q-14. `prama control compile` refused `IN CODELIST 'iso4217'` —
    a list the product ships and registers.

    The fix is at the *call site*, not in a default. `prama.ir.resolve` exists
    to be the one function that lowers a control properly, and its own module
    docstring says "every call site uses it… the alternative — each caller
    remembering — is how three of six call sites end up subtly different, which
    is exactly what happened before this existed." `control compile` was a
    caller that did not use it.

    A first attempt made the bare `Lowerer` default to the shipped registry
    instead. That worked and was wrong: it broke
    `test_bare_lowering_refuses_the_same_control`, whose whole job is to prove
    `resolved` does something — and a bare lowering that quietly reaches for a
    registry is the layering violation the resolve module was written to
    prevent.
    """

    def test_a_shipped_list_compiles_through_resolved(self) -> None:
        from prama.ir.resolve import resolved
        from prama.pql.parser import parse_control

        plan = resolved(parse_control("CHECK positions.ccy IN CODELIST 'iso4217' BECAUSE 'x'"))
        assert plan.plan_id

    def test_bare_lowering_still_refuses_it(self) -> None:
        """The layering, kept. If this stopped raising, `resolved` would be
        doing nothing and nobody would notice."""
        from prama.core.errors import ValidationError
        from prama.ir.lower import Lowerer
        from prama.pql.parser import parse_control

        with pytest.raises(ValidationError, match="not registered"):
            Lowerer().control(
                parse_control("CHECK positions.ccy IN CODELIST 'iso4217' BECAUSE 'x'")
            )

    def test_an_unregistered_list_is_refused_even_through_resolved(self) -> None:
        """The counterfactual. Resolving everything to an empty set would
        compile a control against no values at all, which passes every row —
        worse than the refusal it replaced."""
        from prama.core.errors import ValidationError
        from prama.ir.resolve import resolved
        from prama.pql.parser import parse_control

        with pytest.raises(ValidationError, match="not registered"):
            resolved(parse_control("CHECK t.ccy IN CODELIST 'no_such_list' BECAUSE 'x'"))

    def test_the_cli_uses_the_resolving_entry_point(self) -> None:
        """The defect was one call site reaching past it."""
        import inspect

        from prama.cli import control as control_cli

        source = inspect.getsource(control_cli)
        assert "resolved(control)" in source, (
            "`control compile` lowers without resolving, so every IN CODELIST "
            "control is refused against lists the product ships"
        )


class TestABareClockIsStillAClock:
    """Finding Q-16. `NON_DETERMINISTIC` was checked on function *calls* only.

    Every engine here spells these without parentheses, so
    `CHECK t.d < CURRENT_DATE` parsed as a comparison against a column of that
    name and sailed past a guard written for exactly it. On an engine where the
    identifier resolves, the control reads the clock and its evidence cannot be
    replayed; on one where it does not, the control fails for a reason nobody
    can see.
    """

    @pytest.mark.parametrize(
        "source",
        [
            "CHECK t.d < CURRENT_DATE BECAUSE 'x'",
            "CHECK t SATISFIES d < NOW BECAUSE 'x'",
            "CHECK t.d IS NOT NULL WHERE d = CURRENT_DATE BECAUSE 'x'",
            "CHECK t SATISFIES x > RANDOM BECAUSE 'x'",
            "CHECK t.d < SYSDATE BECAUSE 'x'",
        ],
    )
    def test_a_bare_one_is_refused(self, source: str) -> None:
        from prama.core.errors import PramaError
        from prama.pql.parser import parse_control

        with pytest.raises(PramaError, match="cannot be used in a control"):
            parse_control(source)

    def test_the_call_form_is_still_refused(self) -> None:
        """The branch that already worked, kept."""
        from prama.core.errors import PramaError
        from prama.pql.parser import parse_control

        with pytest.raises(PramaError, match="cannot be used in a control"):
            parse_control("CHECK t.d < NOW() BECAUSE 'x'")

    @pytest.mark.parametrize(
        "source",
        [
            "CHECK t.d < $business_date BECAUSE 'x'",
            "CHECK t.current_status IS NOT NULL BECAUSE 'x'",
            "CHECK t.random_seed IS NOT NULL BECAUSE 'x'",
        ],
    )
    def test_an_ordinary_column_is_not(self, source: str) -> None:
        """The counterfactual, and not a hypothetical: a guard matching on a
        substring would refuse `current_status` and `random_seed`, which are
        perfectly good column names. The supplied `$business_date` — the thing
        the remedy tells you to use — has to keep working too."""
        from prama.pql.parser import parse_control

        assert parse_control(source) is not None


class TestTheEvidenceSaysWhatItWasMeasuredAgainst:
    """Finding Q-15. Four records, identical metrics, two pass and two fail.

    The threshold lives in the plan and `plan_id` hashes it, so the records
    were not ambiguous — they were *unreadable*. Answering "why did this one
    fail?" meant resolving a hash against a plan store, which an auditor holding
    a sealed bundle cannot do.
    """

    def test_the_threshold_is_recorded(self) -> None:
        import inspect

        from prama.execute import run as run_module

        source = inspect.getsource(run_module.ControlRun._run_one)
        assert "plan.threshold.to_dict()" in source

    def test_two_thresholds_are_distinguishable_without_the_plan(self) -> None:
        """The property: the parameters alone must tell them apart."""
        from prama.ir.lower import Lowerer
        from prama.pql.parser import parse_control

        strict = Lowerer().control(parse_control("CHECK t.a IS NOT NULL BECAUSE 'x'"))
        lenient = Lowerer().control(parse_control("CHECK t.a IS NOT NULL BELOW 5% BECAUSE 'x'"))
        assert strict.threshold.to_dict() != lenient.threshold.to_dict()

    def test_it_is_inside_the_hashed_content(self) -> None:
        """A field outside the hash is one somebody can change without
        detection, which is the whole point of the record."""
        from prama.evidence.record import EvidenceRecord

        record = EvidenceRecord(control_id="c", dataset="d", parameters={"threshold": "x"})
        assert "parameters" in record.content()
