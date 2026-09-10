"""Reference reconciliation templates.

Every bank runs the same eleven reconciliations and every bank builds them
again, because the shape is standard and the column names never are. What a
template usefully supplies is the part that is hard *and* portable: which keys,
which tolerance, and which breaks to expect.

The key is the design decision, and most of these tests are about it. A cash
book keyed on amount and date matches the wrong pairs whenever two payments
share a value — and both look correct afterwards.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from prama.core.errors import ValidationError
from prama.packs.banking.reconciliations import TEMPLATES, identities, template
from prama.recon import Matcher
from prama.recon.classify import BreakKind


class TestEveryTemplateIsUsable:
    @pytest.mark.parametrize("identity", identities())
    def test_it_binds_and_produces_a_definition(self, identity: str) -> None:
        entry = template(identity)
        roles = {role: f"col_{role}" for role in (*entry.key_roles, entry.amount_role)}
        definition = entry.bind(
            left_dataset="left_table",
            right_dataset="right_table",
            left_columns=roles,
            right_columns=roles,
        )
        assert definition.key.left == tuple(f"col_{r}" for r in entry.key_roles)
        assert definition.left.amount_column == f"col_{entry.amount_role}"

    @pytest.mark.parametrize("identity", identities())
    def test_it_says_why_those_keys(self, identity: str) -> None:
        """The key is the design decision. A template that supplied one without
        the reasoning is a template somebody will change on a hunch."""
        entry = template(identity)
        assert len(entry.why_these_keys) > 80, identity
        assert entry.key_roles, identity

    @pytest.mark.parametrize("identity", identities())
    def test_it_states_a_tolerance_and_its_rationale(self, identity: str) -> None:
        """A tolerance invented by an engineer is one operations override on the
        first day."""
        entry = template(identity)
        assert entry.tolerance is not None, identity
        assert len(entry.tolerance_rationale) > 40, identity

    @pytest.mark.parametrize("identity", identities())
    def test_it_names_the_breaks_to_expect(self, identity: str) -> None:
        """A reconciliation whose breaks are all "genuine" has not been
        classified, and a queue of unexplained differences is one nobody
        works."""
        entry = template(identity)
        assert entry.expected_breaks, identity
        assert all(isinstance(kind, BreakKind) for kind in entry.expected_breaks)

    def test_a_missing_role_is_refused(self) -> None:
        """A reconciliation with an unbound key matches nothing and reports
        every row on both sides as unmatched — which reads as a total outage
        rather than as a mapping error."""
        entry = template("subledger-to-gl")
        with pytest.raises(ValidationError, match="does not bind"):
            entry.bind(
                left_dataset="a",
                right_dataset="b",
                left_columns={"account": "acct"},
                right_columns={"account": "acct"},
            )

    def test_the_two_sides_may_name_their_columns_differently(self) -> None:
        """The whole reason roles exist. A cash book calls it `ref` and a
        statement calls it `bank_reference`, and neither is going to change."""
        definition = template("cashbook-to-statement").bind(
            left_dataset="cash_book",
            right_dataset="statement",
            left_columns={
                "account": "acct",
                "value_date": "val_dt",
                "reference": "ref",
                "amount": "amt",
            },
            right_columns={
                "account": "iban",
                "value_date": "value_date",
                "reference": "bank_reference",
                "amount": "signed_amount",
            },
        )
        assert definition.key.left == ("acct", "val_dt", "ref")
        assert definition.key.right == ("iban", "value_date", "bank_reference")


class TestTheKeysAreTheDesign:
    def test_a_cash_book_is_keyed_on_the_reference(self) -> None:
        """Not on amount and date. The reference is the only field both sides
        carry unchanged."""
        assert "reference" in template("cashbook-to-statement").key_roles

    def test_two_payments_of_one_value_match_correctly_on_reference(self) -> None:
        """The defect the key choice prevents, demonstrated. Keyed on amount and
        date these two cross-match, and both pairs look correct."""
        book = [
            {"ref": "INV-100", "amt": Decimal("500.00")},
            {"ref": "INV-200", "amt": Decimal("500.00")},
        ]
        statement = [
            {"bank_reference": "INV-200", "signed_amount": Decimal("500.00")},
            {"bank_reference": "INV-100", "signed_amount": Decimal("499.00")},
        ]
        from prama.recon import MatchKey

        report = Matcher(MatchKey(left=("ref",), right=("bank_reference",))).match(book, statement)
        # `left` and `right` are tuples: a pair aggregates every row sharing
        # the key, and here each side has exactly one.
        paired = {pair.left[0]["ref"]: pair.right[0]["signed_amount"] for pair in report.pairs}
        # INV-100 is the one that disagrees, and keying on reference is what
        # makes that visible rather than pairing it with the other 500.
        assert paired["INV-100"] == Decimal("499.00")
        assert paired["INV-200"] == Decimal("500.00")

    def test_the_subledger_key_includes_the_cost_centre(self) -> None:
        """Keyed on account alone it aggregates across cost centres and nets two
        errors into an agreement."""
        assert "cost_centre" in template("subledger-to-gl").key_roles

    def test_the_roll_forward_key_includes_the_instrument(self) -> None:
        """Without it, a gain on one holding nets against a loss on another and
        the balance sheet balances while both are wrong."""
        assert "instrument_id" in template("roll-forward").key_roles

    def test_the_translation_check_is_keyed_on_the_end_to_end_reference(self) -> None:
        """Matching on the transaction id fails on every payment, because MT and
        MX each assign their own."""
        assert template("mt-to-mx").key_roles == ("payment_reference",)


class TestTolerances:
    @pytest.mark.parametrize(
        "identity",
        [
            "cashbook-to-statement",
            "nostro-vostro",
            "roll-forward",
            "repository-to-trade-store",
            "mt-to-mx",
            "return-to-feeder",
            "position-to-custodian",
        ],
    )
    def test_the_exact_ones_are_exactly_zero(self, identity: str) -> None:
        """Zero means the two sides must agree. It is a decision, and it is a
        different decision from having no tolerance at all."""
        assert template(identity).tolerance.absolute == 0.0

    def test_a_value_reconciliation_uses_materiality_on_both_bounds(self) -> None:
        """A penny or a basis point, whichever is larger — the convention
        operations already use, so the generated control agrees with the
        spreadsheet somebody checks it against."""
        tolerance = template("subledger-to-gl").tolerance
        assert tolerance.absolute == 0.01
        assert tolerance.relative == 0.0001


class TestTimingWindows:
    def test_a_general_ledger_compares_same_day(self) -> None:
        assert template("subledger-to-gl").date_window == 0

    def test_a_custodian_gets_a_settlement_window(self) -> None:
        """Settlement timing is the commonest explanation, and a same-day
        comparison reports all of it as genuine."""
        assert template("position-to-custodian").date_window == 2

    def test_a_bank_statement_gets_an_in_transit_window(self) -> None:
        """Unpresented cheques and in-transit credits are timing. Classified as
        genuine they fill the queue with differences that clear themselves."""
        assert template("cashbook-to-statement").date_window == 3
        assert BreakKind.TIMING in template("cashbook-to-statement").expected_breaks


class TestTheCatalogueIsHonest:
    def test_every_identity_is_unique(self) -> None:
        assert len(set(identities())) == len(TEMPLATES)

    def test_an_unknown_identity_raises(self) -> None:
        with pytest.raises(KeyError):
            template("no-such-reconciliation")

    def test_the_description_carries_keys_tolerance_and_taxonomy(self) -> None:
        described = template("front-office-to-subledger").describe()
        assert "keyed on" in described
        assert "Expect:" in described
        assert "timing" in described

    def test_the_dictionary_form_is_complete(self) -> None:
        payload = template("mt-to-mx").to_dict()
        assert payload["key_roles"] == ["payment_reference"]
        assert payload["expected_breaks"]
        assert payload["why_these_keys"]
        assert payload["tolerance_rationale"]
