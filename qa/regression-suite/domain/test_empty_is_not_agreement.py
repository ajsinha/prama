"""Comparing nothing is not the same as finding no difference.

QA round 2, `RCN-015`, `PCK-105`, `INT-014`. Three places where an absence of
input produced the most reassuring possible output — a perfect reconciliation,
a netted exposure of zero, a completed publish — each of which is a positive
claim reached with no evidence.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from decimal import Decimal

from prama.integrate.catalog import WriteReport
from prama.packs.banking.fpml import Trade


class TestTwoEmptySidesDidNotReconcile:
    """`RCN-015`. `match_rate` returned `1.0` when nothing was compared.

    A reconciliation exists to show that two systems agree. Over no rows it has
    shown that neither was asked — and "the feed did not arrive" reported as
    "everything matched" is the most expensive possible mistranslation.
    """

    @staticmethod
    def _empty():
        from prama.recon.match import MatchReport

        return MatchReport()

    def test_the_rate_is_unknown_rather_than_perfect(self) -> None:
        assert self._empty().match_rate is None

    def test_it_says_so_in_words(self) -> None:
        described = self._empty().describe()
        assert "nothing was compared" in described

    def test_the_json_keeps_the_distinction(self) -> None:
        """A consumer reading the payload must be able to tell the two apart."""
        assert self._empty().to_dict()["match_rate"] is None

    def test_a_real_perfect_match_still_reports_one(self) -> None:
        """The counterfactual.

        If every reconciliation now reported None, the assertions above would
        hold while the measure became useless.
        """
        from prama.recon.match import MatchReport, Pair

        result = MatchReport(
            pairs=(Pair(key=("k",), left=({"a": 1},), right=({"a": 1},)),),
            left_rows=1,
            right_rows=1,
        )
        assert result.match_rate == 1.0


class TestATradeWithNoLegsNetsToNothing:
    """`PCK-105`. `net_for` returned `Decimal(0)` for a trade with no legs.

    Zero is a number, and it reads as "these positions cancel out" — the
    opposite conclusion from "there were no positions", about the same
    counterparty. The method already returns None for a cross-currency trade,
    with a docstring explaining that a total across currencies is a number in
    no currency at all. This is the same argument.
    """

    def test_no_legs_gives_no_answer(self) -> None:
        trade = Trade(trade_id="t1", trade_date="2026-09-01", version=1)
        assert trade.net_for("PARTYA") is None

    def test_a_trade_with_legs_still_nets(self) -> None:
        """The counterfactual: netting must still work."""
        from prama.packs.banking.fpml import Leg

        trade = Trade(
            trade_id="t2",
            trade_date="2026-09-01",
            version=1,
            legs=(Leg(payer="PARTYA", receiver="PARTYB", notional=Decimal(100), currency="EUR"),),
        )
        assert trade.net_for("PARTYA") == Decimal(-100)


class TestAPublishThatWroteNothingIsNotComplete:
    """`INT-014`. `written == attempted` is trivially true when both are zero.

    So `publish([])` reported a complete write while `describe()` said "nothing
    was written, because nothing was offered" — the two halves of one object
    disagreeing, and the machine-readable half taking the flattering view. A
    caller polling `complete` to decide whether a catalogue sync succeeded was
    told yes by a sync that never ran.
    """

    def test_an_empty_publish_is_not_complete(self) -> None:
        assert WriteReport(attempted=0, written=0).complete is False

    def test_a_real_publish_is_still_complete(self) -> None:
        assert WriteReport(attempted=3, written=3).complete is True

    def test_a_partial_publish_is_still_incomplete(self) -> None:
        assert WriteReport(attempted=3, written=2).complete is False
