"""The three vendor adapters.

What is verified here is each adapter's own behaviour — what it sends, what it
drops, and what it refuses. **Not** that a real Collibra accepts it: none of
these has been run against a live server, and a passing suite must not be read
as saying otherwise.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.integrate.catalog import Badge, Standing
from prama.integrate.vendors import (
    AlationTarget,
    CollibraTarget,
    DataHubTarget,
    WriteCall,
)
from prama.security.egress import Gate


class Recorder:
    """A transport that records, and can be told to fail."""

    def __init__(self, fail: Exception | None = None) -> None:
        self.calls: list[WriteCall] = []
        self._fail = fail

    def __call__(self, call: WriteCall) -> dict:
        self.calls.append(call)
        if self._fail is not None:
            raise self._fail
        return {"ok": True}


def badge(dataset: str = "positions_eod", **changes) -> Badge:
    base = {
        "dataset": dataset,
        "standing": Standing.HEALTHY,
        "established_at": "2026-09-10",
        "coverage": "full",
        "evidence_reference": "ev:01J8Z",
        "jurisdiction": "EU",
    }
    base.update(changes)
    return Badge(**base)


class TestCollibra:
    def target(self, transport, **changes):
        kwargs = {
            "asset_ids": {"positions_eod": "asset-1"},
            "attribute_type_id": "attr-quality",
        }
        kwargs.update(changes)
        return CollibraTarget(transport, **kwargs)

    def test_a_badge_is_written_against_the_mapped_asset_id(self) -> None:
        transport = Recorder()
        report = self.target(transport).publish([badge()])
        assert report.written == 1
        assert transport.calls[0].body["assetId"] == "asset-1"

    def test_an_unmapped_dataset_is_refused_and_says_why(self) -> None:
        """Two systems in one estate can have a table with the same name, and a
        name-keyed write puts a trading badge on a finance table."""
        report = self.target(Recorder()).publish([badge("unknown_table")])
        assert report.written == 0
        assert "trading badge on a finance table" in report.refused[0][1]

    def test_it_carries_every_field(self) -> None:
        """Collibra's typed attributes hold all of it, so nothing is dropped."""
        transport = Recorder()
        report = self.target(transport).publish([badge()])
        assert report.dropped_fields == ()
        assert transport.calls[0].body["prama"]["evidence_reference"] == "ev:01J8Z"

    def test_the_written_value_is_the_dated_sentence(self) -> None:
        transport = Recorder()
        self.target(transport).publish([badge()])
        assert "as at 2026-09-10" in transport.calls[0].body["value"]


class TestAlation:
    def target(self, transport, **changes):
        kwargs = {"object_ids": {"positions_eod": 42}, "field_id": 7}
        kwargs.update(changes)
        return AlationTarget(transport, **kwargs)

    def test_a_badge_is_written_against_the_mapped_object(self) -> None:
        transport = Recorder()
        assert self.target(transport).publish([badge()]).written == 1
        assert transport.calls[0].body["oid"] == 42

    def test_the_evidence_reference_is_reported_as_dropped(self) -> None:
        """There is no field for a link meaning "this is the run behind the
        verdict", and free text makes it look like a comment somebody typed.
        Reported, so nobody reads an absent link as "there was no evidence"."""
        report = self.target(Recorder()).publish([badge()])
        assert "evidence_reference" in report.dropped_fields
        assert "cannot store" in report.describe()

    def test_the_dropped_field_is_not_smuggled_into_the_value(self) -> None:
        transport = Recorder()
        self.target(transport).publish([badge()])
        assert "ev:01J8Z" not in str(transport.calls[0].body)

    def test_object_id_zero_is_a_real_id_not_a_missing_one(self) -> None:
        """`if not object_id` would treat object 0 as unmapped."""
        transport = Recorder()
        target = self.target(transport, object_ids={"positions_eod": 0})
        assert target.publish([badge()]).written == 1


class TestDataHub:
    def target(self, transport, **changes):
        kwargs = {"platform": "snowflake"}
        kwargs.update(changes)
        return DataHubTarget(transport, **kwargs)

    def test_the_urn_is_built_from_platform_dataset_and_env(self) -> None:
        target = self.target(Recorder())
        assert target.urn_for("db.schema.t") == (
            "urn:li:dataset:(urn:li:dataPlatform:snowflake,db.schema.t,PROD)"
        )

    def test_the_env_segment_changes_the_urn(self) -> None:
        """A URN that differs by its environment segment creates a second, empty
        dataset rather than failing, and the badge lands on a dataset nobody
        looks at."""
        prod = self.target(Recorder()).urn_for("t")
        dev = self.target(Recorder(), env="DEV").urn_for("t")
        assert prod != dev

    def test_the_whole_badge_goes_across(self) -> None:
        transport = Recorder()
        assert self.target(transport).publish([badge()]).written == 1
        aspect = transport.calls[0].body["proposal"]["aspect"]["value"]
        assert aspect["evidence_reference"] == "ev:01J8Z"
        assert aspect["standing"] == "healthy"

    def test_it_upserts_rather_than_appends(self) -> None:
        """Appending would leave yesterday's verdict alongside today's, and a
        reader has no way to tell which is current."""
        transport = Recorder()
        self.target(transport).publish([badge()])
        assert transport.calls[0].body["proposal"]["changeType"] == "UPSERT"


class TestWhatTheyAllShare:
    @pytest.mark.parametrize(
        "make",
        [
            lambda t: CollibraTarget(t, asset_ids={"d": "a"}, attribute_type_id="x"),
            lambda t: AlationTarget(t, object_ids={"d": 1}, field_id=1),
            lambda t: DataHubTarget(t, platform="snowflake"),
        ],
        ids=["collibra", "alation", "datahub"],
    )
    def test_a_transport_failure_is_a_refusal_not_an_exception(self, make) -> None:
        """A catalogue rejecting one table must not leave the other
        thirty-nine unwritten, showing yesterday's verdict with today's
        confidence."""
        target = make(Recorder(fail=TimeoutError("gateway")))
        report = target.publish([badge("d")])
        assert report.written == 0
        assert report.refused

    @pytest.mark.parametrize(
        "make",
        [
            lambda t: CollibraTarget(t, asset_ids={"d": "a"}, attribute_type_id="x"),
            lambda t: AlationTarget(t, object_ids={"d": 1}, field_id=1),
            lambda t: DataHubTarget(t, platform="snowflake"),
        ],
        ids=["collibra", "alation", "datahub"],
    )
    def test_a_missing_asset_is_refused_rather_than_created(self, make) -> None:
        """An adapter that created it would define the estate in the catalogue,
        and an estate defined in two places disagrees with itself."""
        target = make(Recorder(fail=LookupError("no such asset")))
        report = target.publish([badge("d")])
        assert report.written == 0
        assert "does not create assets" in report.refused[0][1]

    @pytest.mark.parametrize(
        "make",
        [
            lambda t: CollibraTarget(t, asset_ids={"d": "a"}, attribute_type_id="x", region="US"),
            lambda t: AlationTarget(t, object_ids={"d": 1}, field_id=1, region="US"),
            lambda t: DataHubTarget(t, platform="snowflake", region="US"),
        ],
        ids=["collibra", "alation", "datahub"],
    )
    def test_each_is_residency_checked(self, make) -> None:
        target = make(Recorder())
        report = target.publish([badge("d")], gate=Gate.for_tenant("EU", tenant_id="t1"))
        assert report.written == 0

    def test_an_undated_badge_cannot_be_constructed_at_all(self) -> None:
        """Not parametrised across the three: the refusal is in Badge itself,
        so none of them gets the chance to decide. Writing it three times would
        look like three tests and be one.

        "Trusted" on a table nobody has checked since March reads as current,
        and a reader has no way to tell."""
        from prama.core.errors import ValidationError

        with pytest.raises(ValidationError, match="has no date"):
            badge("d", established_at="")

    @pytest.mark.parametrize(
        "make",
        [
            lambda t: CollibraTarget(t, asset_ids={"d": "a"}, attribute_type_id="x"),
            lambda t: AlationTarget(t, object_ids={"d": 1}, field_id=1),
            lambda t: DataHubTarget(t, platform="snowflake"),
        ],
        ids=["collibra", "alation", "datahub"],
    )
    def test_none_of_them_can_read_the_catalogue(self, make) -> None:
        """A target that could read would invite the estate to be defined
        there, and an estate defined in two places disagrees with itself."""
        target = make(Recorder())
        assert not hasattr(target, "read")
        assert not hasattr(target, "fetch")


class TestNoVendorClientIsImported:
    def test_the_transport_is_injected(self) -> None:
        """Which is what lets all three be tested, and lets a deployment
        substitute a client with its own mTLS and rate-limit policy."""
        import ast
        import pathlib

        from prama.integrate import vendors

        tree = ast.parse(pathlib.Path(vendors.__file__).read_text())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not {"httpx", "requests", "urllib"} & imported

    def test_the_module_says_it_is_unverified(self) -> None:
        """A passing suite must not be read as saying a real Collibra accepts
        these requests."""
        from prama.integrate import vendors

        assert "has been run against a live server" in (vendors.__doc__ or "")
