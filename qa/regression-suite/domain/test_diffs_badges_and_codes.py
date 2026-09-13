"""Four claims made about work that did not happen.

QA round 2, `CTR-050`, `INT-009`, `INT-041`, `CLS-062`. A diff that reported
"identical" without comparing, a badge whose evidence answered a different
question, a controller that abandoned nine estates over one, and a codelist
that contradicted its own comment.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import date

import pytest

from prama.contract.diff import compare
from prama.core.errors import ValidationError


class TestADiffWithoutItsKeyIsNotADiff:
    """`CTR-050`. `_key_of` uses `row.get(name)`.

    A key column absent from the rows gives every row the identity `(None,)` —
    they all collide, the last one wins, and the comparison reports
    "identical: 1 row(s), none added, removed or changed" about two sets it
    never compared.

    `prama contract diff` runs in a build. "Nothing changed" from a diff that
    could not find its key is the most dangerous sentence this module can
    produce, and it is the one it produced.
    """

    def test_a_missing_key_column_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="in neither side's rows"):
            compare([{"a": 1}], [{"a": 2}], key=["id"])

    def test_the_refusal_names_what_is_available(self) -> None:
        """So the reader can fix it without reading the data themselves."""
        with pytest.raises(ValidationError) as refusal:
            compare([{"account": 1}], [{"account": 2}], key=["id"])
        assert "account" in str(refusal.value)

    def test_a_real_key_still_compares(self) -> None:
        result = compare([{"id": 1, "v": "a"}], [{"id": 1, "v": "b"}], key=["id"])
        assert result.changed == 1

    def test_two_empty_sides_are_still_identical(self) -> None:
        """The counterfactual.

        Empty sides have no columns for a key to be absent from, and comparing
        nothing to nothing is arithmetically identical — a statement about the
        comparison, not a claim about data that was examined.
        """
        assert compare([], [], key=["id"]).is_identical


class TestABadgesEvidenceExplainsItsStanding:
    """`INT-009`. The reference was `records[0]` whatever the standing.

    A badge reading FAILING pointed at the first record inserted, which dict
    order makes arbitrary and which is usually one that passed. A badge is a
    claim and that reference is its evidence; a link answering a different
    question than the badge raises is worse than no link, because the reader
    checks it, sees a pass, and concludes the badge is wrong.
    """

    def test_a_failing_badge_points_at_a_failure(self) -> None:
        from prama.integrate.catalog import _explains

        class Record:
            def __init__(self, verdict: str, record_hash: str) -> None:
                self.verdict, self.record_hash = verdict, record_hash

        passing, failing = Record("pass", "hash_pass"), Record("fail", "hash_fail")
        assert _explains([failing], [], [passing, failing]) == "hash_fail"

    def test_an_unestablished_badge_points_at_one_that_could_not_run(self) -> None:
        class Record:
            def __init__(self, verdict: str, record_hash: str) -> None:
                self.verdict, self.record_hash = verdict, record_hash

        from prama.integrate.catalog import _explains

        passing = Record("pass", "hash_pass")
        unknown = Record("indeterminate", "hash_unknown")
        assert _explains([], [unknown], [passing, unknown]) == "hash_unknown"

    def test_a_healthy_badge_still_has_a_reference(self) -> None:
        """Any record explains a healthy dataset, so the first is fine."""
        from prama.integrate.catalog import _explains

        class Record:
            def __init__(self, verdict: str, record_hash: str) -> None:
                self.verdict, self.record_hash = verdict, record_hash

        assert _explains([], [], [Record("pass", "hash_one")]) == "hash_one"


class TestACodelistKeepsItsOutgoingCode:
    """`CLS-062`. The comment said the outgoing code is not removed in the same
    step; the two lines beneath it removed it in exactly that step.

    `SLE` three lines above is the same situation handled correctly, so the
    rule was known, written down, and then not applied twice. A comment
    contradicted by the line under it is worse than no comment: a reader
    checking whether the transition was handled is told it was.
    """

    @staticmethod
    def _codes(when: date) -> frozenset[str]:
        from prama.classify.codelists import REGISTRY

        currencies = REGISTRY.find("iso4217")
        assert currencies is not None
        return frozenset(currencies.as_of(when).codes)

    def test_the_outgoing_code_survives_its_transition(self) -> None:
        during = self._codes(date(2024, 6, 1))
        assert "ZWL" in during, "the code being retired was gone the day its replacement arrived"
        assert "ZWG" in during, "the replacement was not available"

    def test_it_is_retired_afterwards(self) -> None:
        """The counterfactual: a transition period that never ends is not one."""
        assert "ZWL" not in self._codes(date(2025, 6, 1))

    def test_the_second_transition_behaves_the_same_way(self) -> None:
        during = self._codes(date(2025, 6, 1))
        assert "ANG" in during and "XCG" in during
        assert "ANG" not in self._codes(date(2026, 6, 1))
