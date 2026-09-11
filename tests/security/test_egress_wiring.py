"""Each egress point, refusing for real.

`tests/architecture/test_egress.py` checks that a registered module *mentions*
the gate. That is a coarse check and says so. These are the behavioural ones:
given a tenant with a rule and a destination outside it, does anything actually
stop?

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from prama.alert.route import Alert, Fault, Role, Router
from prama.evidence.ledger import Ledger
from prama.evidence.record import EvidenceRecord, SnapshotRef
from prama.evidence.retention import Archivist
from prama.integrate.catalog import Badge, RecordingTarget, Standing
from prama.security import siem
from prama.security.egress import Gate, ResidencyRefused

EU_ONLY = Gate.for_tenant("EU", tenant_id="t1")
NO_RULE = Gate.for_tenant(None, tenant_id="t2")


def a_badge(dataset: str = "positions_eod", jurisdiction: str = "EU") -> Badge:
    return Badge(
        dataset=dataset,
        standing=Standing.HEALTHY,
        established_at="2026-09-10",
        jurisdiction=jurisdiction,
    )


def a_record(index: int = 0) -> EvidenceRecord:
    return EvidenceRecord(
        plan_id=f"ir:sha256:{index:064x}",
        dataset="positions_eod",
        snapshot=SnapshotRef(kind="lsn", identifier=f"0/{index}", exact=True),
        verdict="pass",
        metrics={"scanned_rows": 10.0},
        finished_at="2026-09-10T06:00:00Z",
        tenant_id="t1",
    )


class TestCatalogWriteBack:
    def test_a_badge_that_may_not_cross_is_refused(self) -> None:
        target = RecordingTarget()
        target.region = "US"
        report = target.publish([a_badge()], gate=EU_ONLY)
        assert report.written == 0
        assert "must stay in EU" in report.refused[0][1]

    def test_the_other_badges_still_land(self) -> None:
        """A residency breach is not a reason to leave forty tables stale."""
        target = RecordingTarget()
        target.region = "EU"
        report = target.publish(
            [a_badge("a", "EU"), a_badge("b", "US"), a_badge("c", "EU")], gate=EU_ONLY
        )
        assert report.written == 2
        assert [name for name, _ in report.refused] == ["b"]

    def test_a_target_with_no_region_is_refused_under_a_rule(self) -> None:
        """An unstated destination is not a domestic one."""
        target = RecordingTarget()
        report = target.publish([a_badge()], gate=EU_ONLY)
        assert report.written == 0

    def test_without_a_gate_nothing_changes(self) -> None:
        """Most deployments have no residency obligation, and the argument is
        optional so they are not made to care."""
        target = RecordingTarget()
        assert target.publish([a_badge()]).written == 1

    def test_a_tenant_with_no_rule_writes_anywhere(self) -> None:
        target = RecordingTarget()
        target.region = "US"
        assert target.publish([a_badge()], gate=NO_RULE).written == 1


class TestSiemExport:
    def test_an_export_to_the_wrong_region_is_refused(self) -> None:
        with pytest.raises(ResidencyRefused):
            siem.render([], gate=EU_ONLY, collector_region="US", jurisdiction="EU")

    def test_it_refuses_wholesale_rather_than_per_event(self) -> None:
        """An audit export missing the records that could not cross is an audit
        export with a hole in it, and nothing in the file says so."""
        with pytest.raises(ResidencyRefused):
            siem.render(
                [object(), object()], gate=EU_ONLY, collector_region="US", jurisdiction="EU"
            )

    def test_a_permitted_export_renders(self) -> None:
        exported = siem.render([], gate=EU_ONLY, collector_region="EU", jurisdiction="EU")
        assert exported.events == 0

    def test_without_a_gate_it_renders(self) -> None:
        assert siem.render([]).events == 0


class TestEvidenceExport:
    def test_a_bundle_to_the_wrong_region_is_refused(self) -> None:
        ledger = Ledger()
        ledger.append(a_record())
        with pytest.raises(ResidencyRefused):
            Archivist().bundle(
                ledger.records(),
                tenant_id="t1",
                gate=EU_ONLY,
                archive_region="US",
                jurisdiction="EU",
            )

    def test_the_refusal_names_the_tenant_and_the_destination(self) -> None:
        ledger = Ledger()
        ledger.append(a_record())
        with pytest.raises(ResidencyRefused) as caught:
            Archivist().bundle(
                ledger.records(),
                tenant_id="northbank",
                gate=EU_ONLY,
                archive_region="US",
                jurisdiction="EU",
            )
        assert caught.value.context["destination"] == "US"
        assert "northbank" in caught.value.message

    def test_a_permitted_bundle_is_built(self) -> None:
        ledger = Ledger()
        ledger.append(a_record())
        bundle = Archivist().bundle(
            ledger.records(), tenant_id="t1", gate=EU_ONLY, archive_region="EU", jurisdiction="EU"
        )
        assert bundle.manifest.records == 1

    def test_the_check_happens_before_the_empty_refusal(self) -> None:
        """Order matters: an empty bundle raises too, and if that came first a
        residency breach would be reported as 'there is nothing to bundle'."""
        with pytest.raises(ResidencyRefused):
            Archivist().bundle([], gate=EU_ONLY, archive_region="US", jurisdiction="EU")


class TestAlertDelivery:
    def alert(self, jurisdiction: str = "EU") -> Alert:
        return Alert(
            identity="a1",
            dataset="positions_eod",
            fault=Fault.VALUE,
            what="notional is null on 4,182 rows",
            severity=0.9,
            at=datetime(2026, 9, 10, 6, tzinfo=UTC),
            jurisdiction=jurisdiction,
        )

    def router(self, region: str, *, gate: Gate | None = EU_ONLY) -> Router:
        return Router(
            {("positions_eod", Role.OWNER): "jsmith"},
            channels={Role.OWNER: "pager"},
            channel_regions={"pager": region},
            gate=gate,
        )

    def test_an_alert_to_a_channel_outside_the_region_is_withheld(self) -> None:
        dispatch = self.router("US").dispatch(self.alert())
        assert not dispatch.sent
        assert "withheld on residency" in dispatch.reason

    def test_the_reason_says_why_an_alert_is_data(self) -> None:
        """An alert body quotes failing values, so sending it moves the
        tenant's data and is not merely a notification."""
        assert "quotes failing values" in self.router("US").dispatch(self.alert()).reason

    def test_the_region_belongs_to_the_channel_not_the_person(self) -> None:
        """The same steward reachable on an in-region chat tool and on an
        external pager is two different residency answers."""
        contacts = {("positions_eod", Role.OWNER): "jsmith"}
        router = Router(
            contacts,
            channels={Role.OWNER: "chat"},
            channel_regions={"chat": "EU", "pager": "US"},
            gate=EU_ONLY,
        )
        assert router.dispatch(self.alert()).sent

    def test_it_is_withheld_from_everybody_or_nobody(self) -> None:
        """An alert delivered to some recipients and silently withheld from
        others is worse than either: the ones who got it assume everyone did."""
        dispatch = self.router("US").dispatch(self.alert())
        assert not dispatch.sent
        assert dispatch.recipients  # they are named, not dropped

    def test_an_undeclared_channel_region_is_refused_under_a_rule(self) -> None:
        """A channel nobody said where it delivers is not a domestic one."""
        router = Router({("positions_eod", Role.OWNER): "jsmith"}, gate=EU_ONLY)
        assert not router.dispatch(self.alert()).sent

    def test_a_permitted_alert_is_sent(self) -> None:
        assert self.router("EU").dispatch(self.alert()).sent

    def test_without_a_gate_alerts_are_unaffected(self) -> None:
        assert self.router("US", gate=None).dispatch(self.alert()).sent

    def test_a_tenant_with_no_rule_alerts_anywhere(self) -> None:
        assert self.router("US", gate=NO_RULE).dispatch(self.alert()).sent
