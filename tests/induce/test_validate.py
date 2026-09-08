"""The gate, and the counterfactual that is the point of it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.induce.validate import Gate, Rejection, SandboxResult, Validated, Validator
from prama.pql.types import Catalogue

CATALOGUE = Catalogue.of(trades={"side": "text", "qty": "number", "ccy": "text", "lei": "text"})
ROWS = [{"side": "BUY", "qty": 10, "ccy": "EUR", "lei": "5493001KJTIIGC8Y1R12"}] * 60


def validator() -> Validator:
    return Validator(catalogue=CATALOGUE, codelists={"iso4217": ("EUR", "USD")})


def check(text: str) -> Validated | Rejection:
    return validator().validate(text, ROWS)


# -- the guarantee is the type -----------------------------------------------


def test_a_validated_control_cannot_be_built_without_passing_every_gate() -> None:
    """This type *is* the acceptance criterion. A discipline enforced by review
    is a discipline with an exception in it by March."""
    passed = check("CHECK trades.side IN ('BUY', 'SELL')")
    assert isinstance(passed, Validated)
    with pytest.raises(ValueError, match="must have passed every gate"):
        Validated(
            control=passed.control,
            plan=passed.plan,
            sandbox=passed.sandbox,
            passed=(Gate.PARSE, Gate.TYPE_CHECK),
        )


def test_a_good_control_passes_all_five_gates() -> None:
    passed = check("CHECK trades.ccy IN CODELIST 'iso4217'")
    assert isinstance(passed, Validated)
    assert set(passed.passed) == set(Gate)


# -- the gates, in order -----------------------------------------------------


def test_prose_is_rejected_at_parse() -> None:
    rejected = check("Certainly! Here is a control for your trades table.")
    assert isinstance(rejected, Rejection)
    assert rejected.gate is Gate.PARSE


def test_a_code_fence_is_unwrapped_rather_than_rejected() -> None:
    """Rejecting a correct control for its packaging teaches nothing and costs
    a retry."""
    assert isinstance(check("```sql\nCHECK trades.qty > 0\n```"), Validated)


def test_nothing_beyond_the_fence_is_repaired() -> None:
    """A candidate needing edits to parse should be rejected, because whatever
    the edit fixed is what the next one will get wrong too."""
    rejected = check("CHECK trades.qty >> 0")
    assert isinstance(rejected, Rejection)
    assert rejected.gate is Gate.PARSE


def test_an_invented_column_is_rejected_at_type_check() -> None:
    """A model will confidently reference a column that would be sensible if it
    existed."""
    rejected = check("CHECK trades.counterparty_name IS NOT NULL")
    assert isinstance(rejected, Rejection)
    assert rejected.gate is Gate.TYPE_CHECK
    assert "counterparty_name" in rejected.detail


def test_an_unregistered_codelist_is_rejected_at_compile() -> None:
    """It type-checks and cannot be lowered, which means it would fail on its
    first scheduled run — the worst possible time to find out."""
    rejected = check("CHECK trades.ccy IN CODELIST 'iso4217_extended'")
    assert isinstance(rejected, Rejection)
    assert rejected.gate is Gate.COMPILE


def test_a_control_that_flags_half_the_data_is_rejected_at_the_sandbox() -> None:
    """It is describing the data, not checking it."""
    rejected = check("CHECK trades.side = 'SELL'")
    assert isinstance(rejected, Rejection)
    assert rejected.gate is Gate.SANDBOX
    assert "describing it, not checking it" in rejected.detail


# -- the counterfactual ------------------------------------------------------


def test_a_control_that_cannot_fail_is_rejected_however_well_formed() -> None:
    """The gate that earns the module. `MATCHES /.*/` parses, type-checks,
    compiles, runs, reports a clean pass on every row, and is worth nothing.
    Nothing in the first four gates can tell it from a good control, because on
    the data they are given the two behave identically."""
    rejected = check("CHECK trades.side MATCHES /.*/")
    assert isinstance(rejected, Rejection)
    assert rejected.gate is Gate.COUNTERFACTUAL
    assert "accepted every one" in rejected.detail


def test_a_bound_so_wide_that_nothing_breaches_it_is_rejected() -> None:
    rejected = check("CHECK trades.qty >= -1e308")
    assert isinstance(rejected, Rejection)
    assert rejected.gate is Gate.COUNTERFACTUAL


def test_probes_are_built_from_the_predicate_rather_than_at_random() -> None:
    """A random row rarely violates a specific predicate, and a probe that
    tests nothing proves nothing."""
    passed = check("CHECK trades.side IN ('BUY', 'SELL')")
    assert isinstance(passed, Validated)
    assert passed.sandbox.value_probes >= 1
    assert passed.sandbox.value_probes_caught == passed.sandbox.value_probes


def test_the_null_probe_is_not_counted_as_evidence_that_a_control_works() -> None:
    """PQL inverts SQL's default, so a missing value breaks every row predicate
    ever written — including a bound wide enough to be useless."""
    result = SandboxResult(
        scanned=100, violations=0, probes=3, probes_caught=1, value_probes=2, value_probes_caught=0
    )
    assert result.is_vacuous
    assert result.can_fail  # it does reject a null; that is not the same thing


def test_a_nullity_assertion_is_probed_with_the_null_itself() -> None:
    """There is nothing else that violates it, and reporting "0 of 0 value
    probes" would read as though the control was never tested."""
    passed = check("CHECK trades.lei IS NOT NULL")
    assert isinstance(passed, Validated)
    assert passed.sandbox.value_probes == 1
    assert passed.sandbox.value_probes_caught == 1


def test_a_two_stage_semantic_type_survives_the_gate() -> None:
    """The residual is applied by the reference interpreter, so a fabricated
    identifier probe is caught even though no SQL engine could catch it."""
    passed = check("CHECK trades.lei IS VALID 'lei'")
    assert isinstance(passed, Validated)
    assert passed.plan.is_two_stage
    assert passed.sandbox.value_probes_caught > 0


def test_a_rejection_says_what_the_gate_means() -> None:
    """ "type_check" is jargon; "it refers to something that is not there" is
    what somebody fixing the prompt needs."""
    rejected = check("CHECK trades.nope IS NOT NULL")
    assert isinstance(rejected, Rejection)
    assert "not there" in rejected.gate.explains
    assert rejected.candidate
