"""Wave 6's acceptance criteria, measured rather than asserted.

"≥ 80% of columns and ≥ 95% of declared CDEs under a reviewed control after one
week of effort" is a claim about a real source and a real week. What can be
measured here is the mechanism: given a realistic declaration and a realistic
extract, how much of the estate do the generators actually cover, and does
combining them beat either alone?

The numbers this prints are Prama's own, on synthetic data, and they are
reported as such. They establish that the machinery reaches the target when the
declarations are there — which is the part that is this codebase's to get right.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import random

from prama.core.provenance import Origin
from prama.derive.coverage import CoverageAnalyser
from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.derive.generator import ControlGenerator
from prama.derive.relationships import generation_for
from prama.mine.dependencies import DependencyMiner
from prama.mine.keys import KeyMiner
from prama.mine.sample import Sample
from prama.pql import ast
from prama.pql.parser import parse_control
from prama.propose.adapt import from_generation
from prama.propose.proposal import Proposal
from prama.propose.queue import ProposalQueue
from prama.propose.utility import Context
from prama.semantic.relationships import (
    MatchKey,
    RelationshipDeclaration,
    RelationshipKind,
)
from prama.semantic.values import (
    Criticality,
    Frequency,
    Grain,
    Optionality,
    Rhythm,
    Sensitivity,
    ValueDomain,
    ValueDomainKind,
)

NOW = "2026-09-08T12:00:00Z"

REAL_LEIS = [
    "5493001KJTIIGC8Y1R12",
    "213800LBQA1Y9L22JB70",
    "HWUPKR0MPOU8FGXBT394",
    "7LTWFZYICNSX8D621K86",
    "ZXTILKJKG63JELOEG630",
]


def declared() -> DatasetDeclaration:
    """A dataset declared the way a business owner would declare it."""
    return DatasetDeclaration(
        name="exposures",
        slug="exp",
        criticality=Criticality.TIER_1,
        purpose="counterparty credit exposure, reported on FR Y-14Q",
        declared_by="a.sinha",
        declared_at="2026-03-04T09:12:00Z",
        reference="DS01",
        grain=Grain(
            attributes=("counterparty_lei", "business_date"),
            statement="one exposure per counterparty per business day",
        ),
        rhythm=Rhythm(
            frequency=Frequency.DAILY,
            arrival_by="06:30",
            arrival_column="loaded_at",
            calendar="TARGET2",
            lateness_tolerance_seconds=900,
            expected_volume_min=1_000,
            expected_volume_max=50_000,
        ),
        attributes=(
            AttributeDeclaration(name="loaded_at"),
            AttributeDeclaration(
                name="counterparty_lei",
                definition="the legal entity identifier of the obligor",
                semantic_type="lei",
                is_cde=True,
                obligations=("FR Y-14Q",),
                optionality=Optionality.MANDATORY,
            ),
            AttributeDeclaration(
                name="business_date",
                semantic_type="iso_date",
                optionality=Optionality.MANDATORY,
            ),
            AttributeDeclaration(
                name="exposure_amount",
                definition="the current outstanding exposure",
                interpretation="gross of collateral, from the firm's perspective",
                currency_attribute="exposure_ccy",
                is_cde=True,
                obligations=("FR Y-14Q",),
                optionality=Optionality.MANDATORY,
                value_domain=ValueDomain(kind=ValueDomainKind.RANGE, minimum=0),
            ),
            AttributeDeclaration(name="exposure_ccy", optionality=Optionality.MANDATORY),
            AttributeDeclaration(
                name="rating",
                optionality=Optionality.OPTIONAL,
                value_domain=ValueDomain(
                    kind=ValueDomainKind.CODELIST,
                    allowed_values=("AAA", "AA", "A", "BBB", "BB", "B", "CCC"),
                ),
            ),
            AttributeDeclaration(name="internal_note", sensitivity=Sensitivity.CONFIDENTIAL),
        ),
    )


#: A hundred counterparties over twenty business days: one row each, so the
#: declared grain really is the grain. Getting this wrong the first time was
#: instructive — with five LEIs recycled, the key miner correctly found no key
#: at all, which is what it is supposed to do when the data does not have one.
COUNTERPARTIES = [
    f"{REAL_LEIS[index % len(REAL_LEIS)][:14]}{index:04d}{index % 100:02d}" for index in range(100)
]


def extract(days: int = 20) -> Sample:
    rng = random.Random(19)
    data = [
        {
            "counterparty_lei": lei,
            "business_date": f"2026-03-{day + 1:02d}",
            "exposure_amount": round(rng.uniform(0, 1_000_000), 2),
            "exposure_ccy": rng.choice(["EUR", "USD", "GBP"]),
            "rating": rng.choice(["AAA", "AA", "A", "BBB"]),
            "internal_note": None,
        }
        for day in range(days)
        for lei in COUNTERPARTIES
    ]
    return Sample.of(
        "exposures",
        data,
        total_rows=len(data),
        partition_column="business_date",
        method="full scan",
    )


# -- the coverage target -----------------------------------------------------


def test_a_dataset_declaration_alone_cannot_cover_its_own_cdes() -> None:
    """The honest finding, and the reason the coverage analyser exists.

    Everything a business owner can say about *one* dataset — its grain, its
    rhythm, its value domains, its semantic types — leaves a CDE's accuracy
    unaddressed, because accuracy means comparison against something outside
    the row and a single dataset has nothing outside it. A per-column coverage
    count would report this estate as fully covered and finished.
    """
    declaration = declared()
    generated = ControlGenerator().generate(declaration)
    coverage = CoverageAnalyser().analyse(declaration, [c.control for c in generated.controls])
    print(f"\n  declaration only:   {coverage.describe()}")
    assert generated.is_complete
    assert not coverage.meets_target
    assert ast.Dimension.ACCURACY in {g.dimension for g in coverage.gaps}
    assert all(g.is_cde for g in coverage.gaps)


def test_adding_the_relationships_reaches_the_target() -> None:
    """The claim the wave rests on: a business owner answers questions about
    their data — including how it relates to other data — and gets a
    controlled estate, with nobody writing SQL."""
    declaration = declared()
    generated = ControlGenerator().generate(declaration)
    related = generation_for(
        RelationshipDeclaration(
            kind=RelationshipKind.REFERENCES,
            from_dataset_id="exposures",
            to_dataset_id="counterparty_master",
            match_keys=(MatchKey("counterparty_lei"),),
            name="REL01",
        )
    )
    controls = [c.control for c in (*generated.controls, *related.controls)]
    controls.append(
        parse_control(
            "CHECK exposures.exposure_amount REFERENCES gl.exposure_amount DIMENSION integrity"
        )
    )
    coverage = CoverageAnalyser().analyse(declaration, controls)
    print(f"\n  with relationships: {coverage.describe()}")
    assert coverage.cde_fraction >= 0.95, coverage.describe()
    assert coverage.fraction >= 0.80, coverage.describe()
    assert coverage.meets_target


def test_the_uncovered_remainder_is_named_rather_than_rounded_away() -> None:
    """Reaching 80% is worth little if nobody can say which 20%."""
    declaration = declared()
    coverage = CoverageAnalyser().analyse(declaration, [])
    assert coverage.gaps
    assert all(gap.remedy for gap in coverage.gaps)


# -- fusion ------------------------------------------------------------------


def test_mining_and_declaring_the_same_rule_produces_one_corroborated_proposal() -> None:
    """`RQ5` asks whether fusion beats either source alone. What can be shown
    here is the mechanism it rests on: the two agreeing produces a single
    proposal carrying both origins, not two proposals or one with the evidence
    discarded.
    """
    declaration = declared()
    queue = ProposalQueue()
    for proposal in from_generation(ControlGenerator().generate(declaration)):
        queue.offer(proposal)

    # The miner independently finds the declared grain in the extract.
    findings = KeyMiner().mine(extract())
    assert findings.best is not None
    assert set(findings.best.columns) == {"counterparty_lei", "business_date"}

    grain_proposal = next(p for p in queue.pending() if p.rule == "grain.uniqueness")
    mined = Proposal(
        identity=grain_proposal.identity,
        content=grain_proposal.content,
        content_hash=grain_proposal.content_hash,
        provenance=__import__("prama.mine.keys", fromlist=["as_provenance"]).as_provenance(
            "exposures", findings.best, extract()
        ),
        description=findings.best.describe(),
        dataset="exposures",
        rule="mine.unique_key",
    )
    admission = queue.offer(mined)
    assert admission.outcome == "corroborated"
    assert admission.proposal is not None
    assert admission.proposal.origin is Origin.DECLARATION
    assert admission.proposal.provenance.is_corroborated


def test_a_corroborated_proposal_outranks_the_same_rule_from_one_source() -> None:
    """Agreement between a declaration and the data is confirmation, and the
    ranking reflects it — modestly, because it is confirmation and not proof."""
    from prama.propose.utility import UtilityScorer

    declaration = declared()
    [alone] = [
        p
        for p in from_generation(ControlGenerator().generate(declaration))
        if p.rule == "grain.uniqueness"
    ]
    findings = KeyMiner().mine(extract())
    assert findings.best is not None
    mined = Proposal(
        identity=alone.identity,
        content=alone.content,
        content_hash=alone.content_hash,
        provenance=__import__("prama.mine.keys", fromlist=["as_provenance"]).as_provenance(
            "exposures", findings.best, extract()
        ),
        description="mined",
        dataset="exposures",
        rule="mine.unique_key",
    )
    together = alone.corroborated_by(mined)
    scorer = UtilityScorer()
    context = Context(criticality=1, is_cde=True)
    assert scorer.score(together, context).score > scorer.score(alone, context).score


def with_a_real_dependency(days: int = 20) -> Sample:
    """An extract where a rule genuinely holds and nobody declared it.

    A counterparty's credit rating does not change from day to day, so
    `counterparty_lei → rating` is a functional dependency in any real
    exposures table. `extract()` draws the rating at random per *row*, so no
    dependency exists in it to find — which is why the acceptance test for
    mining passed while mining found nothing (finding T9).
    """
    rng = random.Random(19)
    rating_of = {lei: rng.choice(["AAA", "AA", "A", "BBB"]) for lei in COUNTERPARTIES}
    data = [
        {
            "counterparty_lei": lei,
            "business_date": f"2026-03-{day + 1:02d}",
            "exposure_amount": round(rng.uniform(0, 1_000_000), 2),
            "exposure_ccy": rng.choice(["EUR", "USD", "GBP"]),
            "rating": rating_of[lei],
        }
        for day in range(days)
        for lei in COUNTERPARTIES
    ]
    return Sample.of(
        "exposures",
        data,
        total_rows=len(data),
        partition_column="business_date",
        method="full scan",
    )


def test_mining_finds_a_rule_the_declaration_did_not_state() -> None:
    """The other half of fusion: mining covers ground nobody declared, which is
    what makes it worth running against a thin semantic layer.

    Finding T9. This asserted `findings.dependencies or findings.discarded`,
    and against `extract()` the answer is 0 dependencies and 2 discarded — so
    it passed entirely on the second disjunct, having found nothing. The third
    assertion sits inside `for dependency in findings.dependencies` and never
    executed. The acceptance test for the capability did not demonstrate the
    capability.
    """
    sample = with_a_real_dependency()
    findings = DependencyMiner().mine(sample)
    assert findings.dependencies, (
        "mining found no rule at all, which is what this test is named for"
    )
    assert any(
        "counterparty_lei" in dependency.describe() and "rating" in dependency.describe()
        for dependency in findings.dependencies
    ), [d.describe() for d in findings.dependencies]

    # Whatever it finds, none of it may activate on its own.
    assert not Origin.MINING.may_auto_activate
    for dependency in findings.dependencies:
        # A full scan spanning twenty partitions has nothing to caveat, which
        # is the point of computing caveats from the sample rather than
        # attaching a boilerplate warning to everything.
        assert dependency.evidence.rows_examined == sample.size


def test_mining_finds_nothing_where_there_is_nothing() -> None:
    """The counterfactual, and the reason the corpus above had to change.

    `extract()` draws its rating per row, so no functional dependency exists.
    A miner reporting one here would be inventing rules, which is worse than
    finding none — and is the failure the test above could not have caught,
    because it accepted "found nothing" as a pass.
    """
    findings = DependencyMiner().mine(extract())
    assert not findings.dependencies, [d.describe() for d in findings.dependencies]
    assert findings.discarded, "candidates were considered and rejected, which is the work"


# -- the review path ---------------------------------------------------------


def test_only_declared_controls_can_reach_the_estate_without_a_person() -> None:
    """Mining is right about the data and silent about the intent."""
    declaration = declared()
    queue = ProposalQueue()
    for proposal in from_generation(ControlGenerator().generate(declaration)):
        queue.offer(proposal)
    assert queue.auto_activatable()
    assert all(p.origin is Origin.DECLARATION for p in queue.auto_activatable())


def test_the_whole_suite_survives_a_regeneration_without_refilling_the_queue() -> None:
    """The property that makes any of this safe to run nightly."""
    declaration = declared()
    queue = ProposalQueue()
    for proposal in from_generation(ControlGenerator().generate(declaration)):
        admission = queue.offer(proposal)
        assert admission.proposal is not None
        queue.accept(admission.proposal.identity, "a.sinha", NOW)
        queue.register_existing(proposal.identity, proposal.content_hash)

    outcomes = {
        queue.offer(p).outcome for p in from_generation(ControlGenerator().generate(declaration))
    }
    assert outcomes == {"already_live"}
