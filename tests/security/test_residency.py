"""Residency.

Where data is allowed to be, and what may cross a border. Three of these tests
are about directions the obvious implementation gets wrong, and one of them —
treating undeclared as unrestricted — fails silently and permanently.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.security.residency import Policy, Verdict, refusals


class TestARuleThatExists:
    def test_a_permitted_destination_is_permitted(self) -> None:
        decision = Policy.of("EU,DE").decide(destination="DE", jurisdiction="DE")
        assert decision.verdict is Verdict.PERMITTED
        assert decision.may_proceed

    def test_a_destination_outside_the_rule_is_refused(self) -> None:
        decision = Policy.of("EU,DE").decide(destination="US", jurisdiction="DE")
        assert decision.verdict is Verdict.REFUSED
        assert not decision.may_proceed

    def test_data_from_outside_the_rule_is_refused_even_to_a_permitted_place(
        self,
    ) -> None:
        """Both ends have to be inside. Checking only the destination lets data
        that should never have been in the region be moved around inside it."""
        decision = Policy.of("EU,DE").decide(destination="DE", jurisdiction="US")
        assert decision.verdict is Verdict.REFUSED

    def test_case_and_spacing_do_not_decide_the_outcome(self) -> None:
        assert Policy.of(" eu , de ").decide(destination="de", jurisdiction="EU").may_proceed


class TestUndeclaredIsNotUnrestricted:
    def test_data_with_no_jurisdiction_is_refused(self) -> None:
        """The direction that matters. Treating undeclared as unrestricted is
        how the one dataset nobody got round to declaring is the one that leaves
        the region."""
        decision = Policy.of("EU").decide(destination="EU", jurisdiction="")
        assert decision.verdict is Verdict.UNDECLARED
        assert not decision.may_proceed

    def test_the_refusal_explains_the_choice(self) -> None:
        """It will block work until somebody declares the thing, so the message
        has to say why that is the safe direction rather than looking like a
        bug."""
        described = Policy.of("EU").decide(destination="EU").describe()
        assert "does not declare a jurisdiction" in described
        assert "rather than assumed unrestricted" in described

    def test_a_movement_with_no_destination_is_refused(self) -> None:
        """A check that cannot be made is a refusal, not a pass."""
        decision = Policy.of("EU").decide(destination="", jurisdiction="EU")
        assert not decision.may_proceed


class TestNoRuleIsNotDenyEverything:
    def test_an_unrestricted_tenant_may_move_anything_anywhere(self) -> None:
        """Most deployments are in one region with no residency obligation, and
        a product that refused every movement until a rule was written is one
        nobody finishes installing."""
        decision = Policy.of(None).decide(destination="US", jurisdiction="")
        assert decision.verdict is Verdict.UNRESTRICTED
        assert decision.may_proceed

    def test_it_says_that_is_an_absence_rather_than_an_approval(self) -> None:
        described = Policy.of("").decide(destination="US").describe()
        assert "declares no residency rule" in described
        assert "not an approval" in described

    def test_an_empty_string_and_none_mean_the_same_thing(self) -> None:
        assert Policy.of("").is_unrestricted
        assert Policy.of(None).is_unrestricted
        assert Policy.of([]).is_unrestricted


class TestHowARuleCanBeWritten:
    def test_a_comma_separated_string_works(self) -> None:
        assert Policy.of("EU,DE,FR").allowed == ("DE", "EU", "FR")

    def test_a_list_works(self) -> None:
        """A form produces a string and an API produces a list. Accepting only
        one means the rule silently does not apply for half the ways it can be
        set."""
        assert Policy.of(["eu", "de"]).allowed == ("DE", "EU")

    def test_duplicates_and_blanks_are_dropped(self) -> None:
        assert Policy.of("EU, ,EU,DE,").allowed == ("DE", "EU")


class TestTheRefusalIsArguable:
    def test_it_names_the_rule_the_data_and_the_destination(self) -> None:
        """A bare refusal produces an outage nobody can diagnose: the operator
        sees a failure and not a policy, and spends the first hour looking at
        the network."""
        described = (
            Policy.of("EU")
            .decide(destination="US", jurisdiction="DE", subject="positions_eod")
            .describe()
        )
        assert "positions_eod" in described
        assert "US" in described
        assert "DE" in described
        assert "must stay in EU" in described

    def test_the_dictionary_form_carries_the_same_facts(self) -> None:
        payload = (
            Policy.of("EU")
            .decide(destination="US", jurisdiction="DE", subject="positions_eod")
            .to_dict()
        )
        assert payload["may_proceed"] is False
        assert payload["rule"] == ["EU"]
        assert payload["jurisdiction"] == "DE"
        assert payload["message"]


class TestReporting:
    def test_refusals_selects_only_what_was_blocked(self) -> None:
        """A residency report is about what was stopped. The permitted ones are
        the majority and are not the finding."""
        policy = Policy.of("EU")
        decisions = [
            policy.decide(destination="EU", jurisdiction="EU", subject="a"),
            policy.decide(destination="US", jurisdiction="EU", subject="b"),
            policy.decide(destination="EU", subject="c"),
        ]
        blocked = refusals(decisions)
        assert [d.subject for d in blocked] == ["b", "c"]

    def test_a_policy_describes_itself(self) -> None:
        assert "must stay in DE, EU" in Policy.of("EU,DE").describe()
        assert "may go anywhere" in Policy.of(None).describe()


@pytest.mark.parametrize(
    "rule,destination,jurisdiction,expected",
    [
        ("EU", "EU", "EU", True),
        ("EU", "EU", "US", False),
        ("EU", "US", "EU", False),
        ("EU,US", "US", "EU", True),
        ("", "US", "", True),
        ("EU", "EU", "", False),
    ],
)
def test_the_decision_table(rule: str, destination: str, jurisdiction: str, expected: bool) -> None:
    """Every combination, in one place, so a change to the logic has to face
    all of them at once."""
    decision = Policy.of(rule).decide(destination=destination, jurisdiction=jurisdiction)
    assert decision.may_proceed is expected
