"""Code lists, and the date they were true on.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import date

import pytest

from prama.classify.codelists import (
    ISO_3166,
    ISO_4217,
    REGISTRY,
    CodeList,
    CodeListVersion,
)
from prama.core.errors import ValidationError


def test_a_currency_retired_last_year_was_valid_the_year_before() -> None:
    """Croatia adopted the euro in 2023. A trade booked in HRK in 2022 was
    correct, and a control replaying that year must still say so."""
    assert ISO_4217.contains("HRK", when=date(2022, 6, 1))
    assert not ISO_4217.contains("HRK", when=date(2024, 6, 1))


def test_a_currency_introduced_this_year_was_not_valid_before_it() -> None:
    assert not ISO_4217.contains("ZWG", when=date(2023, 1, 1))
    assert ISO_4217.contains("ZWG", when=date(2025, 1, 1))


def test_the_outgoing_code_survives_its_replacement_by_one_version() -> None:
    """SLE was added in 2022 while SLL remained tender. Removing the outgoing
    code in the same step is how a correct payment file gets rejected."""
    version = ISO_4217.as_of(date(2023, 6, 1))
    assert "SLE" in version
    assert "SLL" in version


def test_resolution_defaults_to_the_newest_state() -> None:
    assert ISO_4217.as_of() is ISO_4217.latest


def test_a_date_before_the_earliest_snapshot_is_refused_not_guessed() -> None:
    """Resolving to the oldest list would silently answer a question about 1998
    with a fact about 2021, and the answer would look authoritative."""
    with pytest.raises(ValidationError, match="no state as of"):
        ISO_4217.as_of(date(1998, 1, 1))


def test_case_insensitivity_is_a_property_of_the_list() -> None:
    assert REGISTRY.get("trade_side").contains("buy")
    assert not ISO_4217.contains("eur")


def test_versions_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="out of order"):
        CodeList(
            name="x",
            label="x",
            authority="x",
            versions=(
                CodeListVersion(effective_from=date(2024, 1, 1), codes=frozenset({"A"})),
                CodeListVersion(effective_from=date(2021, 1, 1), codes=frozenset({"B"})),
            ),
        )


def test_the_well_known_lists_are_the_right_size() -> None:
    """A rough guard against a code being lost in an edit. ISO 3166-1 alpha-2
    has 249 assignments; ISO 4217 has a little under two hundred."""
    assert len(ISO_3166.latest) == 249
    assert 170 <= len(ISO_4217.latest) <= 200


def test_zero_decimal_currencies_are_listed_because_precision_controls_need_them() -> None:
    """A precision control that rounds JPY to two places is wrong in a way
    nobody notices until a reconciliation breaks by a yen."""
    zero_decimal = REGISTRY.get("zero_decimal_currencies").latest
    assert "JPY" in zero_decimal
    assert "KRW" in zero_decimal
    assert "USD" not in zero_decimal


def test_resolution_for_lowering_flattens_every_list_at_one_date() -> None:
    """The IR wants values, not references — a plan must mean one fixed thing."""
    resolved = REGISTRY.resolve(date(2022, 1, 1))
    assert "HRK" in resolved["iso4217"]
    assert resolved["iso4217"] == tuple(sorted(resolved["iso4217"]))


def test_an_unregistered_list_is_refused_with_the_known_ones_named() -> None:
    with pytest.raises(ValidationError, match="no code list named") as caught:
        REGISTRY.get("iso9999")
    assert "iso4217" in str(caught.value)
