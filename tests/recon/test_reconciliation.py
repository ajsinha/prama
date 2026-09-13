"""Reconciliation: matching, normalisation, classification, and the certificate.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from prama.recon.classify import BreakKind, Classifier, Population, attribute_to_fx
from prama.recon.engine import Definition, Reconciliation, Side
from prama.recon.match import Matcher, MatchKey, ToleranceMatcher, aggregate
from prama.recon.normalise import (
    AmountNormaliser,
    AmountSpec,
    CodeNormaliser,
    RateSource,
    Unavailable,
)
from prama.recon.workflow import BreakQueue, State, certify
from prama.semantic.relationships import Tolerance

WHEN = date(2026, 3, 31)


def rates() -> RateSource:
    source = RateSource(source="ECB")
    source.add("USD", "EUR", WHEN, "0.9200")
    return source


def definition(**overrides: object) -> Definition:
    base: dict[str, object] = {
        "name": "sub-ledger vs GL",
        "left": Side("subledger", "amount", AmountSpec(currency_column="ccy")),
        "right": Side("gl", "balance", AmountSpec(currency="EUR")),
        "key": MatchKey(left=("account", "cost_centre"), right=("acct", "cc")),
        "tolerance": Tolerance(absolute=1.0, currency="EUR"),
        "target_currency": "EUR",
    }
    base.update(overrides)
    return Definition(**base)  # type: ignore[arg-type]


# -- normalisation -----------------------------------------------------------


def test_a_missing_rate_is_a_refusal_and_never_a_fallback() -> None:
    """A missing rate cannot become 1.0, which silently reconciles euros
    against dollars, nor the latest, which makes the run irreproducible."""
    with pytest.raises(Unavailable, match="no USD/EUR rate"):
        RateSource(source="ECB").get("USD", "EUR", WHEN)


def test_rates_are_not_carried_forward_unless_the_business_said_they_may_be() -> None:
    """A bank holiday is a legitimate gap and a vendor outage is not, and only
    the business knows which it is looking at."""
    strict = RateSource(source="ECB")
    strict.add("USD", "EUR", date(2026, 3, 30), "0.92")
    with pytest.raises(Unavailable):
        strict.get("USD", "EUR", WHEN)

    lenient = RateSource(source="ECB", carry_forward_days=1)
    lenient.add("USD", "EUR", date(2026, 3, 30), "0.92")
    found = lenient.get("USD", "EUR", WHEN)
    assert "carried forward from 2026-03-30" in found.source


def test_an_inverted_rate_says_it_was_derived_rather_than_quoted() -> None:
    """A break traced back to a rate should show whether the number was quoted
    or computed."""
    source = RateSource(source="ECB")
    source.add("EUR", "USD", WHEN, "1.0870")
    found = source.get("USD", "EUR", WHEN)
    assert "inverted from EUR/USD" in found.source


def test_amounts_are_decimal_because_the_whole_point_is_small_differences() -> None:
    """Binary floating point manufactures exactly the kind of small difference
    a reconciliation is looking for."""
    normaliser = AmountNormaliser(AmountSpec(currency="USD"), target_currency="EUR", rates=rates())
    result = normaliser.normalise({"amount": "1000.00"}, "amount", WHEN)
    assert result.value == Decimal("920.0000")
    assert isinstance(result.value, Decimal)


def test_the_conversion_is_recorded_on_the_value() -> None:
    """The first question about any break is whether it is real or a
    translation error, and a value with no history behind it cannot answer."""
    normaliser = AmountNormaliser(AmountSpec(currency="USD"), target_currency="EUR", rates=rates())
    result = normaliser.normalise({"amount": "1000.00"}, "amount", WHEN)
    assert "converted USD to EUR at 0.9200" in result.describe()
    assert "as of 2026-03-31" in result.describe()


def test_rounding_is_half_to_even() -> None:
    """Half up introduces a systematic upward bias that shows as a small
    persistent break on every large population."""
    normaliser = AmountNormaliser(AmountSpec(currency="EUR", scale_places=0), target_currency="EUR")
    assert normaliser.normalise({"a": "0.5"}, "a", WHEN).value == Decimal("0")
    assert normaliser.normalise({"a": "1.5"}, "a", WHEN).value == Decimal("2")


def test_an_unmapped_code_is_refused_rather_than_passed_through() -> None:
    """Passing it through produces a row that matches nothing and appears as a
    missing record — a break whose real cause is a mapping gap."""
    mapper = CodeNormaliser({"GB": "UK"}, name="country mapping")
    assert mapper.normalise("GB").value == "UK"
    with pytest.raises(Unavailable, match="not in the country mapping"):
        mapper.normalise("FR")


def test_mapping_gaps_can_be_found_before_a_run_rather_than_during_one() -> None:
    mapper = CodeNormaliser({"GB": "UK"})
    assert mapper.covers({"GB", "FR", "DE"}) == ("DE", "FR")


# -- tolerance ---------------------------------------------------------------


class TestWhicheverIsLarger:
    """Finding C2. `Tolerance.permits` computed "whichever is **smaller**".

    Three separate statements of intent said otherwise and disagreed with the
    code they describe: the class docstring ("a difference must breach **both**
    to count"), `render()`, which prints "within 1 EUR or 0.1%", and the inline
    comment on the return statement itself. Only the expression was wrong, and
    it returned `absolute_ok and relative_ok` — permitted only if within *both*
    bounds, which is the intersection, not the union.

    The consequence is not a subtle one. A 500 EUR difference on a 1,000,000 EUR
    position, under a declared materiality of "1 EUR or 10 bps", was a break —
    though 10 bps of that position is 1,000 EUR. Every large position generates
    a break the declaration says is immaterial, which is the phantom-break flood
    this module exists to prevent.

    No existing test exercised both bounds at once; the one place `permits` was
    asserted used an absolute bound alone.
    """

    #: "A penny or a basis point, whichever is larger" — the convention the
    #: class docstring names, as a bank's operations team states it.
    BOTH = Tolerance(absolute=1.00, relative=0.001, currency="EUR")

    def test_the_relative_bound_governs_a_large_position(self) -> None:
        """10 bps of a million is a thousand, and the declaration says so."""
        assert self.BOTH.permits(500.00, 1_000_000) is True

    def test_the_absolute_bound_governs_a_small_position(self) -> None:
        """10 bps of ten is a penny; the declared floor of 1 EUR is larger."""
        assert self.BOTH.permits(0.50, 10) is True

    def test_a_difference_breaching_both_is_still_a_break(self) -> None:
        assert self.BOTH.permits(2_000.00, 1_000_000) is False
        assert self.BOTH.permits(5.00, 10) is False

    def test_render_says_what_permits_does(self) -> None:
        """The sentence a data owner reads has to be the rule that runs."""
        assert self.BOTH.render() == "within 1 EUR or 0.1%"

    def test_one_bound_alone_is_unchanged(self) -> None:
        """The union must not become a licence when only one bound is set."""
        only_absolute = Tolerance(absolute=1.00)
        assert only_absolute.permits(0.50, 1_000_000) is True
        assert only_absolute.permits(1.50, 1_000_000) is False

        only_relative = Tolerance(relative=0.001)
        assert only_relative.permits(500.00, 1_000_000) is True
        assert only_relative.permits(2_000.00, 1_000_000) is False

    def test_a_relative_bound_against_nothing_permits_only_an_exact_match(self) -> None:
        """There is no percentage of zero.

        Taking a relative bound as satisfied when the magnitude is zero — which
        is what the old expression did — would, under a union, make a declared
        absolute bound unreachable on precisely the rows where a difference is
        most obviously real: something against nothing.
        """
        assert Tolerance(relative=0.001).permits(0.0, 0) is True
        assert Tolerance(relative=0.001).permits(0.01, 0) is False
        # With an absolute bound present, that bound still governs.
        assert self.BOTH.permits(0.50, 0) is True
        assert self.BOTH.permits(5.00, 0) is False


# -- matching ----------------------------------------------------------------


def test_a_key_typed_differently_on_each_side_still_matches() -> None:
    """The most common cause of a zero-match reconciliation: one side reads the
    column as an integer and the other as text."""
    report = Matcher(MatchKey(left=("id",), right=("id",))).match([{"id": 1}], [{"id": "1"}])
    assert len(report.pairs) == 1


@pytest.mark.parametrize("number", [1, 10, 1000, 100000, 1234000, 250])
def test_a_round_number_key_matches_its_text_form(number: int) -> None:
    """Finding C3. The normaliser used ``Decimal.normalize()``, which renders a
    round number in scientific notation: 1000 became ``'1E+3'`` while the text
    side stayed ``'1000'``, and the two never collided.

    It bit *only* numbers with trailing zeros, which is why it survived — the
    test above uses ``1``, one of the values that happens to work. Account
    numbers, trade ids and quantities ending in zeros are not rare, so a
    reconciliation would match most of its rows and report the rest as breaks
    on both sides: the exact failure ``_key_part`` exists to prevent, arriving
    as a partial result that looks like a genuine finding.
    """
    report = Matcher(MatchKey(left=("id",), right=("id",))).match(
        [{"id": number}], [{"id": str(number)}]
    )
    assert len(report.pairs) == 1, f"{number} did not match its own text form"
    assert not report.unmatched_left and not report.unmatched_right


def test_a_repeated_key_compares_totals_rather_than_pairing_rows() -> None:
    """One GL entry against twenty sub-ledger postings is the ordinary shape,
    and pairing them row by row produces one match and nineteen phantom missing
    records."""
    report = Matcher(MatchKey(left=("k",), right=("k",))).match(
        [{"k": "A", "v": 1}, {"k": "A", "v": 2}], [{"k": "A", "v": 3}]
    )
    assert len(report.pairs) == 1
    assert report.pairs[0].is_aggregated
    assert report.aggregated_pairs == 1
    assert "compare totals rather than rows" in report.describe()


def test_a_poor_match_rate_is_the_headline_rather_than_a_footnote() -> None:
    """A reconciliation matching sixty percent of its rows produces a break
    population that is mostly artefacts of the mapping gap."""
    report = Matcher(MatchKey(left=("k",), right=("k",))).match(
        [{"k": f"L{index}"} for index in range(10)],
        [{"k": f"R{index}"} for index in range(10)],
    )
    assert report.looks_misconfigured
    assert "configuration problem rather than a break population" in report.describe()


def test_a_date_one_day_apart_is_matched_rather_than_double_counted() -> None:
    """Matched exactly, every such row appears twice in the breaks — once as
    missing and once as extra — and the break total is double the real
    difference, which is zero."""
    matcher = ToleranceMatcher(MatchKey(left=("id", "d"), right=("id", "d")), window=1)
    report = matcher.match([{"id": "X", "d": "2026-03-30"}], [{"id": "X", "d": "2026-03-31"}])
    assert len(report.pairs) == 1
    assert report.pairs[0].matched_by_tolerance
    assert not report.unmatched_left


def test_an_exact_match_is_never_quietly_paired_with_the_wrong_day() -> None:
    matcher = ToleranceMatcher(MatchKey(left=("id", "d"), right=("id", "d")), window=1)
    report = matcher.match(
        [{"id": "X", "d": "2026-03-31"}],
        [{"id": "X", "d": "2026-03-31"}, {"id": "X", "d": "2026-03-30"}],
    )
    assert len(report.pairs) == 1
    assert not report.pairs[0].matched_by_tolerance


def test_a_key_with_no_columns_is_refused() -> None:
    with pytest.raises(ValueError, match="not a reconciliation"):
        MatchKey(left=(), right=())


def test_a_null_amount_is_not_silently_treated_as_zero() -> None:
    """It would turn a missing value into a value difference of exactly the
    wrong size."""
    with pytest.raises(ValueError, match="missing value into a value difference"):
        aggregate([{"v": None}], "v")


# -- classification ----------------------------------------------------------


def classifier() -> Classifier:
    return Classifier(Tolerance(absolute=1.0), rounding_places=2)


def test_a_sign_convention_error_is_named_rather_than_reported_as_a_big_break() -> None:
    """A break of exactly twice the value is not a data problem, and reporting
    it as one sends somebody to the wrong system."""
    found = classifier().classify("k", Decimal("2000"), Decimal("-2000"))
    assert found is not None
    assert found.kind is BreakKind.SIGN
    assert "twice the value and none of it is real" in found.because
    assert found.kind.is_configuration


def test_a_duplicated_posting_is_named() -> None:
    found = classifier().classify("k", Decimal("100"), Decimal("200"))
    assert found is not None
    assert found.kind is BreakKind.DUPLICATE
    assert "counted 2 times" in found.because


def test_agreement_within_tolerance_is_not_a_break() -> None:
    assert classifier().classify("k", Decimal("100.00"), Decimal("100.50")) is None


def test_a_genuine_difference_says_what_was_ruled_out() -> None:
    found = classifier().classify("k", Decimal("750"), Decimal("790"))
    assert found is not None
    assert found.kind is BreakKind.GENUINE
    assert "no sign, duplication, rounding or timing explanation fits" in found.because


def test_a_timing_difference_is_expected_to_clear() -> None:
    found = classifier().classify("k", Decimal("100"), Decimal("104"), timing=True)
    assert found is not None
    assert found.kind is BreakKind.TIMING
    assert found.kind.clears_itself


def test_a_population_sharing_one_ratio_is_a_rate_not_a_coincidence() -> None:
    """One break explained by an exchange rate is arithmetic; four hundred with
    the same ratio is a missing conversion."""
    breaks = []
    for index in range(30):
        value = Decimal(1000 + index)
        found = classifier().classify(f"k{index}", value, value * Decimal("1.0870"))
        assert found is not None
        breaks.append(found)
    assert all(item.kind is BreakKind.GENUINE for item in breaks)

    reclassified = attribute_to_fx(breaks)
    assert all(item.kind is BreakKind.FX for item in reclassified)
    assert "different currencies" in reclassified[0].because


def test_one_break_with_an_odd_ratio_is_left_alone() -> None:
    found = classifier().classify("k", Decimal("1000"), Decimal("1087"))
    assert found is not None
    assert attribute_to_fx([found])[0].kind is BreakKind.GENUINE


def test_the_population_separates_what_will_clear_from_what_will_not() -> None:
    """A hundred-million timing break is less urgent than a thousand-euro
    genuine one, and triaging by size gets that backwards."""
    timing = classifier().classify("t", Decimal("100000000"), Decimal("0"), timing=True)
    genuine = classifier().classify("g", Decimal("1000"), Decimal("2500"))
    assert timing is not None and genuine is not None
    population = Population(breaks=(timing, genuine))
    assert [item.key for item in population.needs_a_person] == ["g"]


def test_configuration_faults_are_routed_away_from_the_data_steward() -> None:
    """Sending them to a steward wastes the steward's day and leaves the setup
    wrong."""
    sign = classifier().classify("s", Decimal("100"), Decimal("-100"))
    genuine = classifier().classify("g", Decimal("1000"), Decimal("2500"))
    assert sign is not None and genuine is not None
    population = Population(breaks=(sign, genuine))
    assert [item.key for item in population.configuration_faults] == ["s"]
    assert "at the reconciliation's own setup" in population.describe()


# -- the engine --------------------------------------------------------------


def sub_ledger() -> list[dict[str, object]]:
    return [
        {"account": "A1", "cost_centre": "CC1", "amount": "1000.00", "ccy": "EUR"},
        {"account": "A1", "cost_centre": "CC1", "amount": "500.00", "ccy": "EUR"},
        {"account": "A2", "cost_centre": "CC1", "amount": "2000.00", "ccy": "EUR"},
        {"account": "A3", "cost_centre": "CC1", "amount": "1000.00", "ccy": "USD"},
        {"account": "A4", "cost_centre": "CC1", "amount": "750.00", "ccy": "EUR"},
        {"account": "A5", "cost_centre": "CC1", "amount": "100.00", "ccy": "EUR"},
    ]


def general_ledger() -> list[dict[str, object]]:
    return [
        {"acct": "A1", "cc": "CC1", "balance": "1500.00"},
        {"acct": "A2", "cc": "CC1", "balance": "-2000.00"},
        {"acct": "A3", "cc": "CC1", "balance": "920.00"},
        {"acct": "A4", "cc": "CC1", "balance": "790.00"},
        {"acct": "A6", "cc": "CC1", "balance": "60.00"},
    ]


def run():  # type: ignore[no-untyped-def]
    return Reconciliation(definition(), rates=rates()).run(
        sub_ledger(), general_ledger(), business_date=WHEN
    )


def test_a_reconciliation_runs_end_to_end() -> None:
    result = run()
    assert result.completed
    kinds = {item.key: item.kind for item in result.population.breaks}
    assert kinds["A2 / CC1"] is BreakKind.SIGN
    assert kinds["A4 / CC1"] is BreakKind.GENUINE
    assert kinds["A5 / CC1"] is BreakKind.MISSING
    assert kinds["A6 / CC1"] is BreakKind.EXTRA


def test_a_one_to_many_posting_agrees_with_its_summary() -> None:
    """1000 and 500 against a GL entry of 1500 is agreement, not two breaks."""
    assert all(item.key != "A1 / CC1" for item in run().population.breaks)


def test_a_converted_amount_agrees_after_conversion() -> None:
    """1,000 USD at 0.92 is 920 EUR, and the GL says 920."""
    assert all(item.key != "A3 / CC1" for item in run().population.breaks)


def test_the_rates_used_are_recorded_on_the_run() -> None:
    """Without it a break somebody cleared reappears next week with a different
    number and nobody can say whether the data changed or the rate did."""
    recorded = " ".join(rate["detail"] for rate in run().rates_used)
    assert "converted USD to EUR at 0.9200" in recorded
    assert "ECB" in recorded


def test_a_run_is_reproducible() -> None:
    first, second = run(), run()
    assert [item.to_dict() for item in first.population.breaks] == [
        item.to_dict() for item in second.population.breaks
    ]


def test_a_missing_rate_refuses_the_whole_run_rather_than_part_of_it() -> None:
    """A reconciliation missing some of its rows is not a smaller
    reconciliation; it is a wrong one, and the total it reports would be
    quoted."""
    result = Reconciliation(definition(), rates=RateSource(source="ECB")).run(
        sub_ledger(), general_ledger(), business_date=WHEN
    )
    assert not result.completed
    assert "no USD/EUR rate" in result.refusal
    assert result.population.breaks == ()
    assert "could not be run" in result.headline()


# -- the workflow ------------------------------------------------------------


def queue_over_days() -> BreakQueue:
    queue = BreakQueue()
    result = run()
    for offset in range(5):
        queue.observe(result.population.breaks, when=date(2026, 3, 27 + offset))
    return queue


def test_ageing_runs_from_when_a_break_first_appeared() -> None:
    """A break re-detected for forty days is forty days old. Stamping each
    detection with today reports it as new every morning, and then everything
    in the queue is one day old and nothing can be prioritised."""
    queue = queue_over_days()
    item = queue.get("A4 / CC1")
    assert item is not None
    assert item.first_seen == date(2026, 3, 27)
    assert item.age(date(2026, 4, 30)) == 34


def test_a_break_that_stops_appearing_is_cleared_and_not_deleted() -> None:
    """ "We had four hundred breaks and they cleared" and "we had four hundred
    breaks" are the same sentence in a system that forgets."""
    queue = queue_over_days()
    queue.observe([], when=date(2026, 4, 1))
    item = queue.get("A4 / CC1")
    assert item is not None
    assert item.state is State.CLEARED
    assert not queue.open_items()


def test_accepting_a_break_requires_a_reason() -> None:
    """A carried break with no explanation is indistinguishable from one nobody
    looked at, and the certificate has to tell them apart."""
    queue = queue_over_days()
    item = queue.get("A4 / CC1")
    assert item is not None
    with pytest.raises(ValueError, match="requires a reason"):
        item.accepted("a.sinha", "2026-04-01T09:00:00Z", "  ")


def test_a_stale_break_is_escalated_whatever_its_size() -> None:
    """A small break nobody has explained in a month says the process is not
    working, and the amount is beside the point."""
    queue = queue_over_days()
    assert not queue.stale(date(2026, 4, 1))
    assert len(queue.stale(date(2026, 5, 1))) > 0


def test_the_ageing_buckets_are_the_ones_a_manager_reads() -> None:
    assert set(queue_over_days().ageing(date(2026, 4, 1))) == {
        "0-7",
        "8-30",
        "31-90",
        "90+",
    }


# -- the certificate ---------------------------------------------------------


def test_a_certificate_names_the_residue_rather_than_claiming_it_was_clean() -> None:
    """A certificate that can only be issued clean is one nobody issues."""
    queue = queue_over_days()
    item = queue.get("A4 / CC1")
    assert item is not None
    queue.update(item.accepted("a.sinha", "2026-04-01T09:00:00Z", "known reconciling item"))
    certificate = certify(
        "sub-ledger vs GL",
        queue,
        period_end=date(2026, 3, 31),
        signed_by="a.sinha",
        signed_at="2026-04-01T09:00:00Z",
        matched_rate=run().match.match_rate,
        population=run().population.describe(),
    )
    rendered = certificate.render()
    assert not certificate.is_clean
    assert "items outstanding" in rendered
    assert "known reconciling item" in rendered
    assert "explicitly accepted" in rendered


def test_the_certificate_separates_accepted_from_unexplained() -> None:
    """A single number would let an accepted residue and an unexplained one
    look identical."""
    queue = queue_over_days()
    item = queue.get("A4 / CC1")
    assert item is not None
    queue.update(item.accepted("a.sinha", "2026-04-01T09:00:00Z", "known"))
    certificate = certify(
        "r",
        queue,
        period_end=date(2026, 3, 31),
        signed_by="a.sinha",
        signed_at="2026-04-01T09:00:00Z",
        matched_rate=0.99,
    )
    assert certificate.accepted_total != 0
    assert certificate.unexplained_total != certificate.outstanding_total


def test_an_edited_certificate_does_not_verify() -> None:
    """The hash covers everything except the signature."""
    queue = queue_over_days()
    original = certify(
        "r",
        queue,
        period_end=date(2026, 3, 31),
        signed_by="a.sinha",
        signed_at="2026-04-01T09:00:00Z",
        matched_rate=0.99,
    )
    tampered = certify(
        "r",
        queue,
        period_end=date(2026, 3, 31),
        signed_by="a.sinha",
        signed_at="2026-04-01T09:00:00Z",
        matched_rate=1.0,
    )
    assert original.content_hash != tampered.content_hash


def test_an_accepted_break_still_counts_as_outstanding() -> None:
    """A reconciliation reporting zero outstanding because the residue was
    accepted is reporting the thing the acceptance was supposed to make
    visible."""
    queue = queue_over_days()
    for item in queue.open_items():
        queue.update(item.accepted("a.sinha", "2026-04-01T09:00:00Z", "known"))
    assert not queue.open_items()
    assert queue.outstanding()
