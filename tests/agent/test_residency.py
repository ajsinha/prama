"""What may leave the machine the data is on.

Getting this wrong is not a bug; it is a regulatory incident.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.agent.residency import (
    Boundary,
    ResidencyPolicy,
    SampleDisposition,
)
from prama.core.errors import ValidationError

ROWS = [
    {"account_id": "A1", "lei": "5493001KJTIIGC8Y1R12", "notional": 1000.0, "note": "x"},
    {"account_id": "A2", "lei": "213800WAVVOPS85N2205", "notional": None, "note": "y"},
]


def masking(**changes: object) -> Boundary:
    base: dict[str, object] = {
        "zone": "eu-frankfurt",
        "samples": SampleDisposition.MASK,
        "may_send": ("account_id",),
    }
    base.update(changes)
    return Boundary(ResidencyPolicy(**base))  # type: ignore[arg-type]


class TestMasking:
    def test_only_permitted_columns_travel_in_clear(self) -> None:
        redaction = masking().apply(ROWS)
        assert redaction.rows[0]["account_id"] == "A1"
        assert redaction.rows[0]["lei"] == Boundary.MASK
        assert redaction.rows[0]["notional"] == Boundary.MASK

    def test_a_column_nobody_classified_is_masked_not_sent(self) -> None:
        # An allow-list, because a deny-list is one new column away from
        # leaking, and new columns appear without anybody telling the policy.
        rows = [{"account_id": "A1", "newly_added_pii": "secret"}]
        assert masking().apply(rows).rows[0]["newly_added_pii"] == Boundary.MASK

    def test_the_masked_columns_are_declared(self) -> None:
        # So a reader knows what they are not seeing rather than assuming the
        # row is complete.
        assert set(masking().apply(ROWS).masked) == {"lei", "notional", "note"}

    def test_a_never_send_column_is_masked_even_if_also_permitted(self) -> None:
        boundary = masking(may_send=("account_id", "lei"), never_send=("lei",))
        assert boundary.apply(ROWS).rows[0]["lei"] == Boundary.MASK
        assert not boundary.permits("lei")

    def test_the_row_count_is_capped(self) -> None:
        boundary = masking(max_sample_rows=1)
        redaction = boundary.apply(ROWS)
        assert len(redaction.rows) == 1
        assert redaction.withheld == 1


class TestWithholding:
    def test_nothing_travels(self) -> None:
        boundary = Boundary(
            ResidencyPolicy(
                zone="pci", samples=SampleDisposition.WITHHOLD, investigate_at="pci-agent-1"
            )
        )
        redaction = boundary.apply(ROWS)
        assert redaction.rows == ()
        assert redaction.withheld == 2

    def test_a_withheld_sample_is_not_an_absent_sample(self) -> None:
        # Conflating them sends an investigator looking for rows that were
        # never collected — and lets a zone silently dropping everything look
        # identical to a zone that is clean.
        withheld = Boundary(ResidencyPolicy(zone="pci", samples=SampleDisposition.WITHHOLD)).apply(
            ROWS
        )
        nothing_found = masking().apply([])
        assert withheld.withheld == 2 and "does not permit" in withheld.reason
        assert nothing_found.withheld == 0 and "no failing rows" in nothing_found.reason

    def test_it_says_where_to_look_instead(self) -> None:
        boundary = Boundary(
            ResidencyPolicy(
                zone="pci", samples=SampleDisposition.WITHHOLD, investigate_at="pci-agent-1"
            )
        )
        assert "pci-agent-1" in boundary.apply(ROWS).reason
        assert "pci-agent-1" in boundary.policy.describe()


class TestFingerprints:
    def test_a_repeated_bad_row_is_recognisable_without_being_known(self) -> None:
        boundary = Boundary(ResidencyPolicy(zone="ch", samples=SampleDisposition.FINGERPRINT))
        first = boundary.apply([ROWS[0]])
        again = boundary.apply([dict(ROWS[0])])
        assert first.rows == again.rows
        assert "A1" not in str(first.rows)

    def test_different_rows_fingerprint_differently(self) -> None:
        boundary = Boundary(ResidencyPolicy(zone="ch", samples=SampleDisposition.FINGERPRINT))
        assert boundary.apply([ROWS[0]]).rows != boundary.apply([ROWS[1]]).rows


class TestContradictoryPolicies:
    def test_send_plus_never_send_is_refused(self) -> None:
        # A policy that says both would have to choose one silently, and the
        # safe choice is not the one anybody would notice being wrong.
        with pytest.raises(ValidationError) as caught:
            ResidencyPolicy(zone="z", samples=SampleDisposition.SEND, never_send=("lei",))
        assert "Use MASK" in caught.value.remedy

    def test_mask_with_no_allow_list_is_refused(self) -> None:
        with pytest.raises(ValidationError) as caught:
            ResidencyPolicy(zone="z", samples=SampleDisposition.MASK)
        assert "rows of asterisks" in caught.value.remedy


class TestThePolicyExplainsItself:
    @pytest.mark.parametrize(
        "policy",
        [
            ResidencyPolicy(zone="z", samples=SampleDisposition.SEND),
            ResidencyPolicy(zone="z", samples=SampleDisposition.MASK, may_send=("k",)),
            ResidencyPolicy(zone="z", samples=SampleDisposition.FINGERPRINT),
            ResidencyPolicy(zone="z", samples=SampleDisposition.WITHHOLD),
        ],
    )
    def test_in_words_a_data_protection_officer_would_use(self, policy) -> None:
        described = policy.describe()
        assert "z" in described
        assert described.endswith(".")
