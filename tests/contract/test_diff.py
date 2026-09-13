"""Data diff.

The question behind a migration, a parallel run and every "did my change do what
I meant". The interesting answer is almost never the row count, so most of these
tests are about the four ways the obvious implementation gives a number nobody
can act on.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.contract.diff import DETAIL_LIMIT, compare, compare_schema

LEFT = [
    {"id": 1, "amount": 10, "currency": "EUR"},
    {"id": 2, "amount": 20, "currency": "EUR"},
    {"id": 3, "amount": 30, "currency": "USD"},
]
RIGHT = [
    {"id": 1, "amount": 10, "currency": "EUR"},
    {"id": 2, "amount": 99, "currency": "EUR"},
    {"id": 4, "amount": 40, "currency": "GBP"},
]


class TestTheBasicCounts:
    def test_added_removed_changed_and_unchanged(self) -> None:
        diff = compare(LEFT, RIGHT, key=["id"])
        assert (diff.added, diff.removed, diff.changed, diff.unchanged) == (1, 1, 1, 1)

    def test_identical_inputs_are_identical(self) -> None:
        diff = compare(LEFT, LEFT, key=["id"])
        assert diff.is_identical
        assert diff.unchanged == 3
        assert "identical" in diff.describe()

    def test_empty_against_empty_is_identical(self) -> None:
        assert compare([], [], key=["id"]).is_identical


class TestAChangedRowNamesItsColumns:
    def test_the_changed_column_is_reported(self) -> None:
        """ "4,120 rows differ" is a number nobody can act on. "4,120 rows
        differ, all of them only in settlement_date" is a finding with an
        owner."""
        diff = compare(LEFT, RIGHT, key=["id"])
        assert diff.columns_that_changed == ("amount",)
        assert "changes are in amount" in diff.describe()

    def test_the_before_and_after_are_both_carried(self) -> None:
        diff = compare(LEFT, RIGHT, key=["id"])
        [change] = [c for c in diff.changed_examples if c.key == (2,)]
        assert change.changes[0].before == 20
        assert change.changes[0].after == 99
        assert "amount: 20 -> 99" in change.render()

    def test_the_most_common_column_comes_first(self) -> None:
        """Four thousand rows differing in one column is one bug; in forty
        columns it is a different conversation."""
        left = [{"id": n, "a": 1, "b": 1} for n in range(10)]
        right = [{"id": n, "a": 2, "b": 1 if n else 2} for n in range(10)]
        assert compare(left, right, key=["id"]).columns_that_changed == ("a", "b")


class TestWithoutAKeyThereIsNoDiff:
    def test_it_says_rows_cannot_be_matched(self) -> None:
        """Two bags of rows can be compared for membership and nothing more. A
        positional comparison would report every row as changed the moment an
        ordering differed."""
        diff = compare(LEFT, RIGHT)
        assert not diff.comparable
        assert diff.changed == 0
        assert "rows cannot be matched" in diff.describe()
        assert "which row is which" in diff.describe()

    def test_membership_is_still_answered(self) -> None:
        diff = compare(LEFT, RIGHT)
        assert diff.unchanged == 1  # the row identical on both sides
        assert diff.added == 2
        assert diff.removed == 2

    def test_reordering_alone_is_not_a_difference(self) -> None:
        """The specific failure a positional diff produces."""
        diff = compare(LEFT, list(reversed(LEFT)))
        assert diff.added == 0
        assert diff.removed == 0
        assert diff.unchanged == 3


class TestSchemaDominates:
    def test_a_removed_column_is_reported_first(self) -> None:
        """A row diff across a changed schema is a diff where everything
        changed, and the one fact that explains it would be buried."""
        left = [{"id": 1, "amount": 10, "old_column": "x"}]
        right = [{"id": 1, "amount": 10}]
        diff = compare(left, right, key=["id"])
        assert diff.schema.removed == ("old_column",)
        assert diff.describe().startswith("the schema differs")

    def test_a_column_present_on_one_side_does_not_make_rows_differ(self) -> None:
        """Comparing it would report every shared row as changed, which is the
        schema difference said again and much less clearly."""
        left = [{"id": 1, "amount": 10, "only_left": "x"}]
        right = [{"id": 1, "amount": 10}]
        diff = compare(left, right, key=["id"])
        assert diff.changed == 0
        assert diff.unchanged == 1

    def test_a_retype_needs_both_sides_to_have_declared_one(self) -> None:
        """A type on one side and not the other is a change in how much is
        known, not a change of type — and reporting it as a retype sends
        somebody looking for a migration that never happened."""
        assert compare_schema({"a": "INTEGER"}, {"a": ""}).retyped == ()
        assert compare_schema({"a": "INTEGER"}, {"a": "VARCHAR"}).retyped == (
            ("a", "INTEGER", "VARCHAR"),
        )

    def test_identical_schemas_say_so(self) -> None:
        assert compare_schema(["a", "b"], ["b", "a"]).is_identical


class TestDuplicateKeys:
    def test_a_repeated_key_is_counted_and_named(self) -> None:
        """A key that is not unique is not a key, and a diff computed on one is
        arithmetic on the wrong pairs."""
        left = [{"id": 1, "amount": 10}, {"id": 1, "amount": 20}]
        right = [{"id": 1, "amount": 10}]
        diff = compare(left, right, key=["id"])
        assert diff.duplicate_keys_left == 1
        assert "the wrong pairs" in diff.describe()

    def test_unique_keys_produce_no_such_warning(self) -> None:
        assert "wrong pairs" not in compare(LEFT, RIGHT, key=["id"]).describe()


class TestIgnoredColumns:
    def test_an_ignored_column_does_not_make_a_row_differ(self) -> None:
        """A load timestamp differs on every row of every reload, and a diff
        dominated by it hides everything else."""
        left = [{"id": 1, "amount": 10, "loaded_at": "T1"}]
        right = [{"id": 1, "amount": 10, "loaded_at": "T2"}]
        assert compare(left, right, key=["id"], ignore=["loaded_at"]).changed == 0
        assert compare(left, right, key=["id"]).changed == 1

    def test_ignoring_works_without_a_key_too(self) -> None:
        left = [{"amount": 10, "loaded_at": "T1"}]
        right = [{"amount": 10, "loaded_at": "T2"}]
        assert compare(left, right, ignore=["loaded_at"]).unchanged == 1


class TestCapping:
    def test_examples_are_bounded_and_the_counts_are_not(self) -> None:
        """A million differing rows is not a report, and a bound presented as a
        total is the most dangerous number here."""
        left = [{"id": n, "amount": 1} for n in range(DETAIL_LIMIT + 50)]
        right = [{"id": n, "amount": 2} for n in range(DETAIL_LIMIT + 50)]
        diff = compare(left, right, key=["id"])
        assert diff.changed == DETAIL_LIMIT + 50
        assert len(diff.changed_examples) == DETAIL_LIMIT
        assert diff.truncated
        assert "capped" in diff.describe()

    def test_a_small_diff_is_not_marked_truncated(self) -> None:
        assert not compare(LEFT, RIGHT, key=["id"]).truncated

    def test_the_cap_is_configurable(self) -> None:
        left = [{"id": n, "amount": 1} for n in range(10)]
        right = [{"id": n, "amount": 2} for n in range(10)]
        diff = compare(left, right, key=["id"], limit=3)
        assert diff.changed == 10
        assert len(diff.changed_examples) == 3


class TestMixedTypeKeys:
    def test_keys_of_mixed_type_do_not_raise(self) -> None:
        """Sorting raw tuples raises the moment a key column holds both an
        integer and a string — which is exactly what a mid-migration dataset
        looks like."""
        left = [{"id": 1, "v": "a"}, {"id": "2", "v": "b"}]
        right = [{"id": 1, "v": "a"}]
        diff = compare(left, right, key=["id"])
        assert diff.removed == 1

    def test_a_null_key_is_sortable(self) -> None:
        left = [{"id": None, "v": "a"}, {"id": 1, "v": "b"}]
        right = [{"id": 1, "v": "b"}]
        assert compare(left, right, key=["id"]).removed == 1


class TestTheDictionaryForm:
    def test_it_carries_everything_a_report_needs(self) -> None:
        payload = compare(LEFT, RIGHT, key=["id"]).to_dict()
        assert payload["key"] == ["id"]
        assert payload["comparable"] is True
        assert payload["columns_that_changed"] == ["amount"]
        assert payload["changed_examples"]
        assert "message" in payload

    def test_the_keyless_form_says_it_is_not_comparable(self) -> None:
        payload = compare(LEFT, RIGHT).to_dict()
        assert payload["comparable"] is False
        assert payload["changed"] == 0


class TestTheColumnTallyCoversEveryRow:
    """Finding C10. `columns_that_changed` was derived from `changed_examples`,
    which is capped at `DETAIL_LIMIT`.

    The docstring makes this summary the headline value of the tool — "four
    thousand rows differing in one column is one bug, and in forty columns is a
    different conversation" — and it was computed from the first hundred rows by
    key. The trailing note on `describe()` then told the reader that "examples
    are capped and the counts are not", which was true of the counts and not of
    this.
    """

    def corpus(self) -> tuple[list[dict], list[dict]]:
        """The shape that hides the real finding.

        The first hundred rows by key change only `settlement_date`; the other
        9,900 change only `notional`. Anything reading the capped examples sees
        the rare column and misses the common one.
        """
        left = [
            {"id": f"{i:05d}", "settlement_date": "2026-01-01", "notional": 100.0}
            for i in range(10_000)
        ]
        right = [
            {
                "id": row["id"],
                "settlement_date": "2026-01-02" if index < 100 else row["settlement_date"],
                "notional": 100.0 if index < 100 else 200.0,
            }
            for index, row in enumerate(left)
        ]
        return left, right

    def test_the_common_column_is_named(self) -> None:
        left, right = self.corpus()
        result = compare(left, right, key=("id",))
        assert result.changed == 10_000
        assert "notional" in result.columns_that_changed, (
            "the column that changed in 99% of rows was never mentioned"
        )

    def test_the_common_column_is_named_first(self) -> None:
        """Most common first, as the docstring says. Ordering by a capped
        sample puts the rare column at the top."""
        left, right = self.corpus()
        assert compare(left, right, key=("id",)).columns_that_changed[0] == "notional"

    def test_the_rare_column_is_still_named(self) -> None:
        """A tally that only reported the winner would be a different defect."""
        left, right = self.corpus()
        assert "settlement_date" in compare(left, right, key=("id",)).columns_that_changed

    def test_the_summary_does_not_contradict_itself(self) -> None:
        """`describe()` promises the counts are not capped. It has to be true
        of everything the sentence carries."""
        left, right = self.corpus()
        sentence = compare(left, right, key=("id",)).describe()
        assert "notional" in sentence

    def test_a_small_diff_is_unchanged(self) -> None:
        """The counterfactual: below the cap, the old and new answers agree, so
        this cannot be passing because the tally changed meaning."""
        left = [{"id": "1", "a": 1, "b": 2}]
        right = [{"id": "1", "a": 9, "b": 2}]
        assert compare(left, right, key=("id",)).columns_that_changed == ("a",)
