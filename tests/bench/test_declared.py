"""Prama on its own benchmark: the declared path, scored like every baseline.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from prama.bench import declared
from prama.bench.baselines import baseline
from prama.bench.corpus import build
from prama.classify.validators import REGISTRY


def test_clean_windows_raise_nothing() -> None:
    """The fairness test. A control that fires on clean data is not detecting the
    defect in the window next door; it is wrong. The corpus's own IBANs failed
    this until their check digits were computed rather than made up."""
    corpus = build(seed=42)
    plans = declared.controls(corpus.dataset)
    for scenario in corpus.scenarios:
        wrong = declared.failing(plans, [dict(r) for r in scenario.clean])
        assert not wrong, (scenario.window, [c.render().splitlines()[0] for c in wrong])


def test_the_corpus_ibans_are_valid() -> None:
    iban = REGISTRY.get("iban")
    rows = build(seed=42).scenarios[0].clean
    assert all(iban.judge(r["iban"]).valid for r in rows)


def test_the_declared_path_scores_and_names_what_it_cannot_see() -> None:
    """Pinned for seed 42, so a change in the number is a decision, not drift."""
    score = baseline("prama-declared").run(build(seed=42))
    found = {f.family: f.found for f in score.families}
    assert found == {
        "structural": 5,
        "content": 4,
        "statistical": 1,
        "relational": 0,
        "semantic": 0,
        "temporal": 0,
    }


def test_the_declaration_is_written_from_the_domain_not_the_defects() -> None:
    """A guard on the method, not a proof: no defect class is named in it."""
    from prama.bench.corpus import classes_of

    text = repr(declared.DECLARED).lower()
    assert not [c.name for c in classes_of() if c.name.lower() in text]
