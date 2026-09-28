"""Γ: a business declaration in, running controls out.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.backend.execute import unanswerable
from prama.classify.codelists import REGISTRY as CODELISTS
from prama.core.provenance import Origin
from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.derive.generator import ControlGenerator, evidence_for, severity_for
from prama.ir.lower import Lowerer
from prama.pql import ast
from prama.pql.parser import parse_control
from prama.pql.types import Catalogue
from prama.semantic.values import (
    Authoritativeness,
    Criticality,
    Frequency,
    Grain,
    Optionality,
    Rhythm,
    Sensitivity,
    Temporality,
    ValueDomain,
    ValueDomainKind,
)


def positions(**overrides: object) -> DatasetDeclaration:
    """The declaration from the docs/03 §5 worked example."""
    base = {
        "name": "positions",
        "slug": "pos",
        "criticality": Criticality.TIER_1,
        "declared_by": "a.sinha",
        "declared_at": "2026-03-04T09:12:00Z",
        "reference": "DS01",
        "grain": Grain(
            attributes=("account_id", "business_date"),
            statement="one position per account per business day",
        ),
        "rhythm": Rhythm(
            frequency=Frequency.DAILY,
            arrival_by="06:30",
            arrival_column="loaded_at",
            calendar="TARGET2",
            lateness_tolerance_seconds=900,
            expected_volume_min=10_000,
            expected_volume_max=90_000,
        ),
        "attributes": (
            AttributeDeclaration(name="account_id", optionality=Optionality.MANDATORY),
            AttributeDeclaration(name="loaded_at"),
            AttributeDeclaration(name="business_date", optionality=Optionality.MANDATORY),
            AttributeDeclaration(
                name="counterparty_lei",
                semantic_type="lei",
                is_cde=True,
                obligations=("FR Y-14Q",),
                optionality=Optionality.MANDATORY,
            ),
            AttributeDeclaration(
                name="market_value",
                currency_attribute="settlement_ccy",
                value_domain=ValueDomain(kind=ValueDomainKind.RANGE, minimum=0),
            ),
            AttributeDeclaration(name="settlement_ccy"),
        ),
    }
    base.update(overrides)
    return DatasetDeclaration(**base)  # type: ignore[arg-type]


# -- the claim ---------------------------------------------------------------


def test_one_declaration_produces_a_suite_with_no_sql_written() -> None:
    generated = ControlGenerator().generate(positions())
    assert len(generated) >= 8
    assert generated.is_complete


def test_every_generated_control_can_say_why_it_exists() -> None:
    """ "Because you declared X on 4 March" — the answer that makes a generated
    estate one somebody owns rather than one nobody recognises."""
    for derived in ControlGenerator().generate(positions()).controls:
        sentence = derived.provenance.sentence()
        assert "a.sinha declared it on 2026-03-04" in sentence
        assert derived.provenance.origin is Origin.DECLARATION
        assert derived.control.because


def test_every_generated_control_re_parses_to_itself() -> None:
    """Assert the rendered artefact, not the intent. A generator that emits
    plausible PQL and is never asked to read it back is a generator whose bugs
    are found in production — this test found two."""
    for derived in ControlGenerator().generate(positions()).controls:
        text = derived.content
        assert parse_control(text).render() == text, text


def test_every_generated_control_can_reach_a_verdict() -> None:
    """Lowering is not the property worth asserting; answerability is.

    This asserted `plan_id` alone until QA round 3 (`Q-71`). A freshness control
    lowers cleanly, compiles to real SQL, runs, and is then judged against a
    metric nobody emits — so it can never pass and never fail. The old
    assertion held the whole time.
    """
    lowerer = Lowerer(codelists=CODELISTS.resolve())
    for derived in ControlGenerator().generate(positions()).controls:
        plan = lowerer.control(derived.control)
        assert plan.plan_id
        reason = unanswerable(plan)
        assert not reason, f"{derived.control.render().splitlines()[0]}: {reason}"


# -- grain -------------------------------------------------------------------


def test_a_grain_generates_its_uniqueness_control() -> None:
    generated = ControlGenerator().generate(positions())
    key = generated.by_rule("grain.uniqueness")[0]
    assert isinstance(key.control.assertion, ast.UniqueKeyAssertion)
    assert [c.name for c in key.control.assertion.columns] == [
        "account_id",
        "business_date",
    ]
    assert key.control.because == "one position per account per business day"


def test_a_grain_also_requires_its_members_to_be_present() -> None:
    """Not a nicety. SQL's COUNT(DISTINCT) ignores nulls, so a thousand rows
    with a null account_id slip past the uniqueness control, and the table has
    no grain at all while the control reports green."""
    generated = ControlGenerator().generate(positions())
    completeness = [
        c
        for c in generated.controls
        if "grain.completeness" in c.rule
        and isinstance(c.control.assertion, ast.PredicateAssertion)
    ]
    subjects = {
        c.control.assertion.subject.name  # type: ignore[union-attr]
        for c in completeness
    }
    assert subjects == {"account_id", "business_date"}
    assert "does not count nulls as duplicates" in completeness[0].control.because


def test_a_grain_naming_a_column_that_does_not_exist_is_reported_not_emitted() -> None:
    """Emitting it produces something that compiles, deploys and fails at three
    in the morning. Skipping it silently leaves the declarer believing
    something is checked that is not."""
    declaration = positions(
        grain=Grain(attributes=("account_id", "book_id"), statement="one per book")
    )
    generated = ControlGenerator().generate(declaration)
    assert not generated.is_complete
    (problem,) = [u for u in generated.unsatisfiable if u.rule != "rhythm.freshness"]
    assert "book_id" in problem.reason
    assert problem.remedy


# -- deduplication -----------------------------------------------------------


def test_two_rules_reaching_the_same_check_produce_one_control() -> None:
    """A second alert saying exactly what the first said is how people learn to
    ignore the first."""
    generated = ControlGenerator().generate(positions())
    rendered = [c.content for c in generated.controls]
    assert len(rendered) == len(set(rendered))


def test_but_both_reasons_survive_the_merge() -> None:
    """Dropping one would lose a reason the owner declared."""
    generated = ControlGenerator().generate(positions())
    merged = next(c for c in generated.controls if "+" in c.rule)
    assert "declared grain" in merged.control.because
    assert "is mandatory" in merged.control.because


def test_the_merged_control_keeps_the_strictest_treatment() -> None:
    declaration = positions(
        attributes=(
            AttributeDeclaration(
                name="account_id",
                optionality=Optionality.MANDATORY,
                is_cde=True,
                obligations=("FINREP",),
            ),
            AttributeDeclaration(name="business_date", optionality=Optionality.MANDATORY),
        )
    )
    generated = ControlGenerator().generate(declaration)
    merged = next(
        c
        for c in generated.controls
        if isinstance(c.control.assertion, ast.PredicateAssertion)
        and c.control.assertion.subject.name == "account_id"  # type: ignore[union-attr]
    )
    assert merged.control.on_fail is ast.FailAction.BLOCK
    assert merged.control.evidence.level is ast.EvidenceLevel.FULL


# -- rhythm ------------------------------------------------------------------


def test_an_arrival_expectation_generates_a_freshness_control_with_the_calendar() -> None:
    freshness = ControlGenerator().generate(positions()).by_rule("rhythm.freshness")[0]
    assertion = freshness.control.assertion
    assert isinstance(assertion, ast.FreshnessAssertion)
    assert assertion.due_time == "06:30"
    assert assertion.calendar == "TARGET2"
    assert assertion.tolerance_minutes == 15


def test_the_freshness_reason_does_not_quote_the_expected_record_count() -> None:
    """A reason that includes an irrelevant number reads as boilerplate, and
    boilerplate is what people stop reading."""
    freshness = ControlGenerator().generate(positions()).by_rule("rhythm.freshness")[0]
    assert "90,000" not in freshness.control.because
    assert "90000" not in freshness.control.because


def test_a_seasonal_driver_is_deferred_to_a_monitor_and_says_so() -> None:
    """A fixed threshold wide enough for a month-end spike cannot detect an
    ordinary day collapsing to half its size."""
    declaration = positions(
        rhythm=Rhythm(
            frequency=Frequency.DAILY,
            expected_volume_min=100,
            volume_drivers=("month_end", "trading_days"),
        )
    )
    generated = ControlGenerator().generate(declaration)
    deferred = next(d for d in generated.deferred if d.rule == "rhythm.seasonality")
    assert "month_end" in deferred.declared
    assert "baseline" in deferred.destination


# -- attributes --------------------------------------------------------------


def test_a_semantic_type_generates_a_validity_control_naming_its_standard() -> None:
    control = ControlGenerator().generate(positions()).by_rule("attribute.semantic_type")[0]
    assert "ISO 17442" in control.control.because
    assert "check characters" in control.control.because


def test_an_unknown_semantic_type_is_refused_with_the_known_ones_offered() -> None:
    """It would compile to a check that passes everything, which is worse than
    no control because it looks like coverage."""
    declaration = positions(
        grain=None,
        attributes=(AttributeDeclaration(name="x", semantic_type="klingon_id"),),
    )
    generated = ControlGenerator().generate(declaration)
    (problem,) = [u for u in generated.unsatisfiable if u.rule != "rhythm.freshness"]
    assert "klingon_id" in problem.reason
    assert "isin" in problem.remedy


def test_a_numeric_bound_renders_as_a_number_not_a_string() -> None:
    """Engines mostly coerce a quoted bound, which is worse than failing: the
    control runs, and where the comparison is lexical it reports that -5 is
    above zero."""
    control = ControlGenerator().generate(positions()).by_rule("attribute.value_domain")[0]
    assert control.content.splitlines()[0].endswith(">= 0")


def test_a_declared_pattern_renders_as_a_pattern_literal() -> None:
    declaration = positions(
        grain=None,
        attributes=(
            AttributeDeclaration(
                name="ref",
                value_domain=ValueDomain(
                    kind=ValueDomainKind.PATTERN, pattern="^[A-Z]{3}[0-9]{6}$"
                ),
            ),
        ),
    )
    control = ControlGenerator().generate(declaration).by_rule("attribute.value_domain")[0]
    assert "MATCHES /^[A-Z]{3}[0-9]{6}$/" in control.content
    assert parse_control(control.content).render() == control.content


def test_a_monetary_amount_generates_a_control_on_the_column_beside_it() -> None:
    """An invalid currency code does not make one row wrong; it makes every
    total over the amount meaningless."""
    control = ControlGenerator().generate(positions()).by_rule("attribute.currency")[0]
    assert "settlement_ccy IN CODELIST 'iso4217'" in control.content
    assert "cannot be added" in control.control.because


def test_an_amount_whose_currency_column_is_missing_is_reported() -> None:
    declaration = positions(
        grain=None,
        attributes=(AttributeDeclaration(name="market_value", currency_attribute="ccy"),),
    )
    generated = ControlGenerator().generate(declaration)
    (problem,) = [u for u in generated.unsatisfiable if u.rule != "rhythm.freshness"]
    assert "no column 'ccy'" in problem.reason


def test_a_conditional_attribute_becomes_a_filtered_control() -> None:
    declaration = positions(
        grain=None,
        attributes=(
            AttributeDeclaration(
                name="maturity_date",
                optionality=Optionality.CONDITIONAL,
                optionality_condition="product_type = 'BOND'",
            ),
            AttributeDeclaration(name="product_type"),
        ),
    )
    control = ControlGenerator().generate(declaration).by_rule("attribute.completeness")[0]
    assert control.control.where is not None
    assert "product_type = 'BOND'" in control.content


def test_an_unparseable_condition_does_not_become_an_unconditional_control() -> None:
    """That would be stricter than declared: alerting on rows the business said
    were fine, and switched off within the week."""
    declaration = positions(
        grain=None,
        attributes=(
            AttributeDeclaration(
                name="maturity_date",
                optionality=Optionality.CONDITIONAL,
                optionality_condition="if the product is a bond, obviously",
            ),
        ),
    )
    generated = ControlGenerator().generate(declaration)
    assert not generated.by_rule("attribute.completeness")
    (problem,) = [u for u in generated.unsatisfiable if u.rule != "rhythm.freshness"]
    assert "not a PQL expression" in problem.reason
    assert "stricter than you declared" in problem.remedy


def test_an_optional_attribute_generates_no_completeness_control() -> None:
    declaration = positions(
        grain=None,
        attributes=(AttributeDeclaration(name="comment", optionality=Optionality.OPTIONAL),),
    )
    assert not ControlGenerator().generate(declaration).by_rule("attribute.completeness")


# -- severity and evidence, derived rather than defaulted --------------------


def test_a_tier_one_dataset_cannot_produce_a_suite_of_warnings() -> None:
    """A defect in regulatory reporting is reportable, so the control that
    finds it cannot be something nobody pages on."""
    for control in ControlGenerator().generate(positions()).controls:
        assert control.control.severity.rank >= ast.Severity.MAJOR.rank


def test_a_cde_raises_the_floor_of_its_dataset() -> None:
    routine = DatasetDeclaration(name="t", criticality=Criticality.TIER_3)
    plain = AttributeDeclaration(name="x")
    critical = AttributeDeclaration(name="x", is_cde=True)
    assert severity_for(routine, critical).rank > severity_for(routine, plain).rank


def test_a_regulated_cde_blocks_rather_than_alerts() -> None:
    """Submitting wrong is worse than submitting late, and an alert nobody
    reads before the deadline is not a control."""
    lei = ControlGenerator().generate(positions()).by_rule("attribute.semantic_type")[0]
    assert lei.control.on_fail is ast.FailAction.BLOCK
    assert lei.control.evidence.level is ast.EvidenceLevel.FULL


def test_a_sensitive_attribute_keeps_counts_rather_than_samples() -> None:
    """A masked sample of a PII column tells the reader nothing they can act
    on, and storing it unmasked is not an option."""
    spec = evidence_for(AttributeDeclaration(name="ssn", sensitivity=Sensitivity.PII))
    assert spec.level is ast.EvidenceLevel.COUNTS


# -- authoritativeness -------------------------------------------------------


def test_a_replica_is_sent_to_parity_rather_than_given_its_own_suite() -> None:
    """A perfect copy of wrong data is a perfect copy, and a replica scoring
    well on its own content says nothing."""
    declaration = positions(
        authoritativeness=Authoritativeness.REPLICA, source_of_truth="positions_golden"
    )
    generated = ControlGenerator().generate(declaration)
    deferred = next(d for d in generated.deferred if d.rule == "authoritativeness.parity")
    assert "MIRRORS" in deferred.destination


def test_a_replica_with_no_named_origin_is_reported() -> None:
    declaration = positions(authoritativeness=Authoritativeness.REPLICA)
    generated = ControlGenerator().generate(declaration)
    assert "no source of truth" in generated.unsatisfiable[0].reason


def test_an_append_only_table_is_told_what_it_needs_rather_than_given_a_proxy() -> None:
    """A within-scan approximation would report green on a table being quietly
    rewritten, and that is worse than emitting nothing."""
    declaration = positions(temporality=Temporality.APPEND_ONLY)
    deferred = next(
        d for d in ControlGenerator().generate(declaration).deferred if d.rule == "temporality"
    )
    assert "consecutive snapshots" in deferred.destination


# -- stability under regeneration -------------------------------------------


def test_regenerating_an_unchanged_declaration_changes_nothing() -> None:
    first = ControlGenerator().generate(positions())
    second = ControlGenerator().generate(positions())
    assert [c.identity for c in first.controls] == [c.identity for c in second.controls]
    assert [c.content_hash for c in first.controls] == [c.content_hash for c in second.controls]


def test_editing_a_declaration_updates_a_control_rather_than_orphaning_it() -> None:
    """Identity from the text would make every edit orphan one control and
    create another, so the review queue fills with controls that already
    exist."""
    before = ControlGenerator().generate(positions())
    after = ControlGenerator().generate(
        positions(
            rhythm=Rhythm(
                frequency=Frequency.DAILY,
                arrival_by="07:00",
                arrival_column="loaded_at",
                calendar="TARGET2",
                expected_volume_min=10_000,
                expected_volume_max=90_000,
            )
        )
    )
    old = before.by_rule("rhythm.freshness")[0]
    new = after.by_rule("rhythm.freshness")[0]
    assert old.identity == new.identity
    assert old.content_hash != new.content_hash


# -- checking against the real schema ---------------------------------------


def test_a_control_that_does_not_type_check_is_reported_not_offered() -> None:
    """Doctrine: assert the rendered artefact. A generator whose output is
    never compiled is a generator whose bugs are found in production."""
    catalogue = Catalogue.of(positions={"account_id": "text", "business_date": "date"})
    declaration = positions(
        attributes=(
            AttributeDeclaration(name="account_id", optionality=Optionality.MANDATORY),
            AttributeDeclaration(name="business_date", optionality=Optionality.MANDATORY),
            AttributeDeclaration(name="ghost", optionality=Optionality.MANDATORY),
        )
    )
    generated = ControlGenerator(catalogue=catalogue).generate(declaration)
    assert not generated.is_complete
    assert any("ghost" in u.reason for u in generated.unsatisfiable)
    assert all("ghost" not in c.content for c in generated.controls)


def test_a_dataset_with_no_profile_yet_is_taken_at_its_word() -> None:
    """Refusing to generate anything for a dataset whose columns have not been
    read would make Γ useless at exactly the moment it is most wanted."""
    declaration = DatasetDeclaration(
        name="new_feed",
        grain=Grain(attributes=("id",), statement="one row per id"),
    )
    assert ControlGenerator().generate(declaration).is_complete


@pytest.mark.parametrize("rule", ["grain.uniqueness", "rhythm.freshness", "rhythm.volume"])
def test_each_documented_declaration_generates_its_stated_control(rule: str) -> None:
    """docs/03 §5, row by row."""
    assert ControlGenerator().generate(positions()).by_rule(rule)


def test_a_generated_freshness_control_can_reach_a_verdict() -> None:
    """Q-64, closed. Declaring a rhythm with an arrival column generates a
    freshness control that measures the newest arrival and can be red. It was
    pinned by a strict xfail until this held."""
    lowerer = Lowerer(codelists=CODELISTS.resolve())
    fresh = [
        lowerer.control(d.control)
        for d in ControlGenerator().generate(positions()).controls
        if lowerer.control(d.control).assertion_kind == "freshness"
    ]
    assert fresh, "the generator no longer produces a freshness control"
    for plan in fresh:
        assert not unanswerable(plan), unanswerable(plan)
