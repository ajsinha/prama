"""Relationship discovery: several weak signals, none sufficient alone.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.discover.relationships import (
    RelationshipDiscoverer,
    Signal,
    discovery_provenance,
)
from prama.mine.sample import Sample
from prama.semantic.relationships import RelationshipKind


def positions() -> Sample:
    return Sample.of(
        "positions",
        [
            {
                "account_id": f"A{i % 50}",
                "instrument_id": f"I{i % 20}",
                "id": i,
                "status": "OK",
            }
            for i in range(400)
        ],
    )


def accounts() -> Sample:
    return Sample.of(
        "accounts",
        [
            {"account_id": f"A{i}", "legal_entity": f"LE{i % 5}", "id": i, "status": "OK"}
            for i in range(50)
        ],
    )


def test_a_generic_column_name_never_proposes_a_relationship() -> None:
    """Every table has id, name, status and created_at. Matching on one
    proposes a relationship between every pair in the estate, which discredits
    the ones that were real."""
    report = RelationshipDiscoverer().discover(positions(), accounts())
    matched = {k.left for c in report.candidates for k in c.match_keys}
    assert "id" not in matched
    assert "status" not in matched
    assert report.suppressed["generic_name"] == 2


def test_the_suppressed_count_is_reported_rather_than_the_entries() -> None:
    """ "412 pairs matched on `id`" says why the report is short; 412 entries
    say nothing and bury the four that mattered."""
    report = RelationshipDiscoverer().discover(positions(), accounts())
    assert report.suppressed
    assert all(isinstance(count, int) for count in report.suppressed.values())


def test_containment_and_naming_together_make_a_corroborated_candidate() -> None:
    report = RelationshipDiscoverer().discover(positions(), accounts())
    candidate = report.candidates[0]
    assert candidate.is_corroborated
    assert Signal.CONTAINMENT in candidate.signals
    assert Signal.NAMING in candidate.signals
    assert candidate.kind is RelationshipKind.REFERENCES


def test_a_candidate_resting_on_one_signal_says_so() -> None:
    """It is a question rather than a finding, and should look like one."""
    left = Sample.of("a", [{"widget_ref": f"W{i}"} for i in range(300)])
    right = Sample.of("b", [{"widget_ref": f"X{i}"} for i in range(300)])
    report = RelationshipDiscoverer().discover(left, right)
    candidate = report.candidates[0]
    assert not candidate.is_corroborated
    assert "a question rather than a finding" in candidate.describe()


def test_agreement_counts_for_more_than_any_single_signal() -> None:
    """Averaging would let one naming match drag a well-corroborated candidate
    down to its level, which is the whole reason to gather five signals."""
    plain = RelationshipDiscoverer().discover(positions(), accounts())
    with_log = RelationshipDiscoverer().discover(
        positions(), accounts(), co_access=38, co_access_total=200
    )
    assert with_log.candidates[0].confidence > plain.candidates[0].confidence


def test_query_co_access_is_the_only_signal_about_what_people_do() -> None:
    report = RelationshipDiscoverer().discover(
        positions(), accounts(), co_access=38, co_access_total=200
    )
    detail = next(e.detail for e in report.candidates[0].evidence if e.signal == Signal.CO_ACCESS)
    assert "38 of 200 logged queries" in detail


def test_discovery_runs_without_a_query_log() -> None:
    """A discoverer that needed one would be a discoverer that does not run."""
    assert RelationshipDiscoverer().discover(positions(), accounts()).candidates


def test_a_shared_schema_signature_suggests_a_copy() -> None:
    """It finds replicas and migrations nothing else finds, and genuinely
    cannot tell them from two tables built from one template — which is why it
    contributes a signal rather than a verdict."""
    original = Sample.of(
        "positions",
        [{"account_id": f"A{i}", "instrument_id": "I", "market_value": 1.0} for i in range(300)],
    )
    replica = Sample.of(
        "positions_replica",
        [{"account_id": f"A{i}", "instrument_id": "I", "market_value": 1.0} for i in range(300)],
    )
    report = RelationshipDiscoverer().discover(original, replica)
    assert report.candidates
    assert any(Signal.SCHEMA_SIGNATURE in c.signals for c in report.candidates)
    assert report.candidates[0].kind is RelationshipKind.MIRRORS


def test_the_candidate_sentence_reads_as_english() -> None:
    """The kind's prompt is written for a screen that already names both
    datasets, so slotting it into a sentence produced word salad."""
    report = RelationshipDiscoverer().discover(positions(), accounts())
    sentence = report.candidates[0].describe()
    assert sentence.startswith("positions → accounts may be references:")


def test_a_discovered_relationship_is_mined_and_therefore_never_auto_applied() -> None:
    report = RelationshipDiscoverer().discover(positions(), accounts())
    provenance = discovery_provenance(report.candidates[0])
    assert not provenance.origin.may_auto_activate
    assert provenance.observations
