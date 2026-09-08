"""The deterministic layer, checked against identifiers that really exist.

Every positive case here is a real ISIN, LEI, IBAN or SEDOL, taken from a public
register rather than constructed by running this code and recording what it
said. A validator tested against its own output is a tautology: it proves the
implementation is self-consistent, which is exactly what a wrong implementation
also is.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.classify.validators import (
    REGISTRY,
    Expressibility,
    ValidatorRegistry,
)
from prama.core.errors import ValidationError

# Real identifiers. Apple, Vodafone, Siemens, LVMH, Microsoft, Toyota, Nestlé.
REAL_ISINS = [
    "US0378331005",
    "GB0002634946",
    "DE0005190003",
    "FR0000131104",
    "US5949181045",
    "JP3633400001",
    "CH0012032048",
]

# The last two predate the ISO 17442 reservation of characters 5-6 as "00" and
# carry letters there. They are here on purpose: an earlier screen required the
# zeros, and would have reported live reference data as invalid.
REAL_LEIS = [
    "5493001KJTIIGC8Y1R12",
    "213800LBQA1Y9L22JB70",
    "HWUPKR0MPOU8FGXBT394",
    "7LTWFZYICNSX8D621K86",
]

REAL_IBANS = [
    "GB82WEST12345698765432",
    "DE89370400440532013000",
    "FR1420041010050500013M02606",
    "NL91ABNA0417164300",
]


@pytest.mark.parametrize("value", REAL_ISINS)
def test_real_isins_verify(value: str) -> None:
    assert REGISTRY.get("isin").judge(value).valid


@pytest.mark.parametrize("value", REAL_LEIS)
def test_real_leis_verify(value: str) -> None:
    assert REGISTRY.get("lei").judge(value).valid


@pytest.mark.parametrize("value", REAL_IBANS)
def test_real_ibans_verify(value: str) -> None:
    assert REGISTRY.get("iban").judge(value).valid


def test_a_legacy_lei_is_not_rejected_for_lacking_the_reserved_zeros() -> None:
    """ISO 17442 reserves characters 5-6 as "00", and interim-era LEIs ignore
    it. Screening on the reservation would fail live reference data."""
    validator = REGISTRY.get("lei")
    for value in ("HWUPKR0MPOU8FGXBT394", "7LTWFZYICNSX8D621K86"):
        assert value[4:6] != "00"
        assert validator.judge(value).valid


def test_a_transposed_isin_is_caught() -> None:
    """The typo the check digit exists for."""
    judgement = REGISTRY.get("isin").judge("US0378313005")  # 31 <-> 13
    assert not judgement.valid
    assert not judgement.failed_screen


def test_the_reason_names_the_value_that_would_have_been_right() -> None:
    """A steward with four thousand rows needs the fix, not the diagnosis."""
    judgement = REGISTRY.get("isin").judge("US0378331006")
    assert "US0378331005" in judgement.reason


def test_a_wrong_shape_is_reported_as_a_screen_failure() -> None:
    """Distinguished because it usually means the wrong column entirely."""
    judgement = REGISTRY.get("isin").judge("hello")
    assert not judgement.valid
    assert judgement.failed_screen


def test_a_fabricated_isin_fails_despite_a_perfect_shape() -> None:
    """The whole reason a pattern is not allowed to stand in for the check."""
    validator = REGISTRY.get("isin")
    assert validator.screen("GB0000000000")
    assert not validator.judge("GB0000000000").valid


def test_null_and_blank_are_not_format_failures() -> None:
    """Emptiness is a completeness question, and conflating the two would make
    every nullable identifier column fail its format control."""
    validator = REGISTRY.get("isin")
    assert validator.judge(None).valid
    assert validator.judge("   ").valid


def test_a_truncated_iban_is_rejected_even_when_mod_97_passes() -> None:
    """Country length is part of ISO 13616, and one in ninety-seven truncations
    verifies by luck."""
    validator = REGISTRY.get("iban")
    truncated = "DE8937040044053201"
    assert not validator.judge(truncated).valid
    assert "22 characters" in validator.judge(truncated).reason


def test_an_unknown_country_iban_says_so() -> None:
    assert "does not issue IBANs" in REGISTRY.get("iban").judge("ZZ82WEST12345698765432").reason


def test_sedol_excludes_vowels() -> None:
    """Part of the scheme, not a nicety: it is what stops a truncated ticker
    being read as a SEDOL."""
    assert REGISTRY.get("sedol").judge("0263494").valid
    assert REGISTRY.get("sedol").judge("A263494").failed_screen


def test_leap_years_are_handled_in_both_directions() -> None:
    validator = REGISTRY.get("iso_date")
    assert validator.judge("2024-02-29").valid
    assert not validator.judge("2026-02-29").valid
    assert validator.judge("2000-02-29").valid  # divisible by 400
    assert not validator.judge("1900-02-29").valid  # divisible by 100, not 400


def test_an_ambiguous_ipv4_octet_is_rejected() -> None:
    """A leading zero routes as octal in some resolvers and decimal in others,
    so the same string reaches two different hosts."""
    assert REGISTRY.get("ipv4").judge("10.0.0.1").valid
    assert not REGISTRY.get("ipv4").judge("10.0.0.010").valid
    assert not REGISTRY.get("ipv4").judge("10.0.0.256").valid


def test_gtin_accepts_every_declared_length() -> None:
    for value in ("73513537", "012345678905", "4006381333931", "00012345600012"):
        assert REGISTRY.get("gtin").judge(value).valid, value


def test_pattern_validators_declare_that_the_screen_is_the_whole_test() -> None:
    assert REGISTRY.get("uuid").screen_is_complete
    assert REGISTRY.get("bic").screen_is_complete


def test_algorithmic_validators_declare_that_it_is_not() -> None:
    """The property a compiler must consult before emitting a regex and calling
    the job done."""
    for name in ("isin", "lei", "iban", "cusip", "sedol"):
        validator = REGISTRY.get(name)
        assert validator.expressibility is Expressibility.ALGORITHM
        assert not validator.screen_is_complete


def test_every_screen_admits_every_valid_value() -> None:
    """The screen is a *necessary* condition. If a valid value could fail it,
    the two-stage plan would report a violation on good data — the one failure
    mode the design cannot tolerate.
    """
    for values, name in ((REAL_ISINS, "isin"), (REAL_LEIS, "lei"), (REAL_IBANS, "iban")):
        validator = REGISTRY.get(name)
        for value in values:
            assert validator.screen(value), f"{name} screen rejects the valid {value}"


def test_every_validator_names_its_authority() -> None:
    """An identifier check that cannot cite a standard is folklore, and a
    steward disputing a finding has nowhere to look."""
    for name in REGISTRY.names():
        validator = REGISTRY.get(name)
        assert validator.label, name
        if name != "hex_colour":  # no standards body owns a hex triplet
            assert validator.authority, name


def test_two_validators_cannot_claim_one_name() -> None:
    """A control saying IS VALID 'lei' must mean one thing, or it means
    different things on different nodes."""
    registry = ValidatorRegistry()
    registry.register(REGISTRY.get("isin"))

    class Impostor(type(REGISTRY.get("lei"))):  # type: ignore[misc]
        name = "isin"

    with pytest.raises(ValidationError, match="two different validators"):
        registry.register(Impostor())


def test_an_unknown_type_is_refused_rather_than_ignored() -> None:
    """Silently accepting one would compile to a check that passes everything."""
    with pytest.raises(ValidationError, match="no validator named"):
        REGISTRY.get("not_a_real_type")
