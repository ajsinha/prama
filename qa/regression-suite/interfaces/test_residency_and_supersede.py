"""Two boundaries that held on one path and not on its sibling.

QA round 2, `INC-071` and `UI-122`. Both are the same shape — a rule enforced
where somebody thought about it, and absent one function away.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from prama.alert.route import Alert, Delivery, Fault, Role, Router
from prama.security.egress import ResidencyRefused

BASE = datetime(2026, 4, 1, 6, 0)
CONTACTS = {("positions", Role.OWNER): "o.accountable"}


class _RefuseEverything:
    """A residency gate that permits no movement at all.

    Refusing everything rather than one region, so the test cannot pass because
    the alert happened to be routed somewhere the gate allowed.
    """

    def require(self, egress: str, **_: object) -> None:
        raise ResidencyRefused(
            f"{egress} may not leave the jurisdiction",
            remedy="Use an in-region channel for this recipient.",
        )


def _alert(**overrides: object) -> Alert:
    base: dict[str, object] = {
        "identity": "a1",
        "dataset": "positions",
        "fault": Fault.VALUE,
        "what": "62% of counterparty LEIs are malformed",
        "severity": 0.8,
        "at": BASE,
    }
    base.update(overrides)
    return Alert(**base)  # type: ignore[arg-type]


class TestAResolutionCrossesTheSameBoundaryAsTheAlert:
    """`dispatch` withheld on residency; `resolve` did not.

    The rule held for the bad news and not for the good, which is the worse
    half to lose. A resolution names the dataset and the control it was raised
    on, so "this is fixed now" still reports what was wrong a moment ago — to
    somebody the gate has just said may not hear it.
    """

    def test_an_alert_refused_on_residency_is_withheld(self) -> None:
        """The half that already worked, pinned so the fix cannot lose it."""
        router = Router(CONTACTS, gate=_RefuseEverything())
        outcome = router.dispatch(_alert())
        assert outcome.delivery is Delivery.QUIET
        assert "residency" in outcome.reason

    def test_the_resolution_for_that_alert_is_withheld_too(self) -> None:
        router = Router(CONTACTS, gate=_RefuseEverything())
        router.dispatch(_alert())
        outcome = router.resolve(_alert())
        assert outcome.delivery is Delivery.QUIET, (
            "the resolution went out to a recipient the residency gate refused for the alert itself"
        )
        assert "residency" in outcome.reason

    def test_without_a_gate_a_resolution_still_goes_out(self) -> None:
        """The counterfactual.

        If resolutions were withheld generally, the test above would pass while
        proving nothing about residency. With no gate configured, a resolution
        must still be delivered — "that thing is fixed" is the message people
        least often get.
        """
        router = Router(CONTACTS)
        router.dispatch(_alert())
        assert router.resolve(_alert()).delivery is not Delivery.QUIET


class TestASupersedeCannotReachAnotherEstate:
    """`supersedes` arrived in a form field and was applied verbatim.

    Signing in one estate while naming another estate's attestation id
    succeeded — a 303, not a refusal — and the record then claimed to supersede
    an attestation its signer had no standing over. Worse, `AttestationDao.sign`
    then wrote `superseded_by` onto that other estate's row, so the damage was
    not confined to the new record.
    """

    async def _an_attestation_in(self, estate, tenant_id: str) -> str:
        """A real, signed attestation belonging to one estate."""
        from prama.report.attestation import Attestation, Coverage

        async with estate.unit_of_work() as uow:
            attestation = Attestation(
                tenant_id=tenant_id,
                attester_id="u-other",
                attester_name="An Officer",
                statement="The book is fairly stated.",
                scope="A book",
                period_start="2026-08-01",
                period_end="2026-08-31",
                coverage=Coverage(controls_in_scope=1, controls_run=1, passed=1, failed=0),
                evidence_root="ab" * 32,
                evidence_records=1,
                signed_at="2026-09-01T00:00:00Z",
            )
            row = await uow.attestations.sign(attestation, seal=attestation.seal(b"k"))
            await uow.flush()
            return str(row.id)

    async def test_signing_cannot_supersede_another_estates_attestation(
        self, estate, two_tenants: tuple[str, str]
    ) -> None:
        """The damage was not confined to the new record.

        `sign` wrote `superseded_by` onto the row being superseded, so a claim
        made in one estate reached into a sealed attestation belonging to
        another. That write is the thing to prove impossible.
        """
        from prama.core.errors import NotFoundError

        ours, theirs = two_tenants
        target = await self._an_attestation_in(estate, theirs)

        async with estate.unit_of_work() as uow:
            with pytest.raises(NotFoundError):
                await uow.attestations.sign(
                    self._attestation_for(ours),
                    seal="our-seal",
                    supersedes=target,
                )

        # And their row is untouched — the refusal happened before the write,
        # not after it.
        async with estate.unit_of_work() as uow:
            theirs_row = await uow.attestations.in_tenant(target, theirs)
            assert theirs_row.superseded_by is None

    async def test_superseding_our_own_attestation_still_works(
        self, estate, two_tenants: tuple[str, str]
    ) -> None:
        """The counterfactual.

        A check that refused every supersede would pass the test above while
        breaking the feature. Superseding within one's own estate is the whole
        point of the field, and it must still mark both rows.
        """
        ours, _ = two_tenants
        target = await self._an_attestation_in(estate, ours)

        async with estate.unit_of_work() as uow:
            replacement = await uow.attestations.sign(
                self._attestation_for(ours),
                seal="our-seal",
                supersedes=target,
            )
            await uow.flush()
            assert replacement.supersedes == target

        async with estate.unit_of_work() as uow:
            earlier = await uow.attestations.in_tenant(target, ours)
            assert earlier.superseded_by == str(replacement.id)

    @staticmethod
    def _attestation_for(tenant_id: str):
        from prama.report.attestation import Attestation, Coverage

        return Attestation(
            tenant_id=tenant_id,
            attester_id="u-ours",
            attester_name="Our Officer",
            statement="Our book is fairly stated.",
            scope="Our book",
            period_start="2026-09-01",
            period_end="2026-09-30",
            coverage=Coverage(controls_in_scope=1, controls_run=1, passed=1, failed=0),
            evidence_root="cd" * 32,
            evidence_records=1,
            signed_at="2026-10-01T00:00:00Z",
        )
