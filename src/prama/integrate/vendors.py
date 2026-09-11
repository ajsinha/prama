"""Catalogue adapters for the vendors an estate is most likely to already have.

Three targets behind the SPI in :mod:`prama.integrate.catalog`: Collibra,
Alation and DataHub. Each writes a quality badge into the vendor's own model of
an asset, which is the whole difficulty — the three disagree about what a
quality state *is*, and the honest adapter is the one that says what it had to
drop rather than the one that maps everything onto something.

What each can carry, and what it cannot:

===========  ==========================================  ==========================
Catalogue    How it holds a badge                        What it cannot hold
===========  ==========================================  ==========================
Collibra     A custom attribute on an asset              Nothing important
Alation      A custom field on a data object             The evidence reference,
                                                         which has nowhere to go
                                                         except free text
DataHub      An aspect on a dataset URN                  Nothing important
===========  ==========================================  ==========================

Two decisions apply to all three.

**A badge with nowhere to put its date is refused wholesale, not written
undated.** That behaviour already lives in the base class and these adapters
inherit it rather than each deciding again. "Trusted" on a table nobody has
checked since March reads as current, and nothing in the catalogue tells a
reader otherwise.

**An asset the catalogue does not have is a refusal, not a creation.** An
adapter that created the missing asset would define the estate in the
catalogue, and an estate defined in two places is one that disagrees with
itself. The refusal names the identifier that did not resolve, because that is
the mapping somebody has to fix.

**The transport is injected.** Nothing here opens a socket, which is what lets
all three be tested — and lets a deployment substitute a client with its own
mTLS, proxy, retry and rate-limit policy already applied.

**None of these has been run against a live server.** The request shapes are
from each vendor's documented API. What is verified here is the adapter's own
behaviour — what it sends, what it drops, and what it refuses — not that a real
Collibra accepts it. That distinction is recorded rather than left to be
assumed from the presence of a test suite.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from typing import Any

from prama.integrate.catalog import Badge, CatalogTarget

__all__ = [
    "AlationTarget",
    "CollibraTarget",
    "DataHubTarget",
    "VendorTransport",
    "WriteCall",
]

#: What a transport is given and what it returns. A callable rather than a
#: client class, so a deployment can pass a closure over its own HTTP stack
#: without inheriting from anything here.
VendorTransport = Callable[["WriteCall"], Mapping[str, Any]]


@dataclasses.dataclass(frozen=True, slots=True)
class WriteCall:
    """One request an adapter wants made.

    Carries the vendor's own shape rather than a normalised one: a normalised
    request would need un-normalising in every transport, and the place that
    knows the vendor's API is the adapter.
    """

    vendor: str
    method: str
    path: str
    body: Mapping[str, Any]

    def render(self) -> str:
        return f"{self.method} {self.path}"


class _VendorTarget(CatalogTarget):
    """What the three share: a transport, a region, and honest refusals."""

    def __init__(self, transport: VendorTransport, *, region: str = "") -> None:
        self._transport = transport
        self.region = region

    def _send(self, call: WriteCall, badge: Badge) -> Mapping[str, Any]:
        try:
            return self._transport(call)
        except LookupError as exc:
            # The asset is not in the catalogue. Deliberately not created: an
            # adapter that created it would define the estate in the
            # catalogue, and an estate defined in two places disagrees with
            # itself.
            raise RuntimeError(
                f"{self.name} has no asset for {badge.dataset!r}: {exc}. "
                "Map it in the catalogue first — Prama does not create assets, "
                "because an estate defined in two places disagrees with itself."
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"{self.name} refused {call.render()}: {exc}") from exc


class CollibraTarget(_VendorTarget):
    """Collibra: a quality attribute on an asset.

    Collibra models everything as an asset with typed attributes, so a badge
    maps cleanly and nothing has to be dropped. The identifier is Collibra's own
    asset id — not the dataset name — because two systems in one estate can
    legitimately have a table with the same name, and a name-keyed write would
    put a trading badge on a finance table.
    """

    name = "collibra"
    supports = frozenset({"standing", "established_at", "coverage", "evidence_reference", "detail"})

    def __init__(
        self,
        transport: VendorTransport,
        *,
        asset_ids: Mapping[str, str],
        attribute_type_id: str,
        region: str = "",
    ) -> None:
        super().__init__(transport, region=region)
        self._asset_ids = dict(asset_ids)
        self._attribute_type_id = attribute_type_id

    def write(self, badge: Badge) -> None:
        asset_id = self._asset_ids.get(badge.dataset)
        if not asset_id:
            raise RuntimeError(
                f"no Collibra asset id is mapped for {badge.dataset!r}. Prama "
                "does not resolve assets by name: two systems in one estate can "
                "have a table with the same name, and a name-keyed write puts a "
                "trading badge on a finance table."
            )
        self._send(
            WriteCall(
                vendor=self.name,
                method="POST",
                path="/rest/2.0/attributes",
                body={
                    "assetId": asset_id,
                    "typeId": self._attribute_type_id,
                    "value": badge.render(),
                    "prama": badge.to_dict(),
                },
            ),
            badge,
        )


class AlationTarget(_VendorTarget):
    """Alation: a custom field on a data object.

    Alation's custom fields are typed and configured per instance, so the set an
    adapter may write is a deployment fact rather than a constant. What it
    cannot hold is the evidence reference — there is no field for a link that
    means "this is the run behind the verdict", and putting it in free text
    makes it look like a comment somebody typed.

    Declaring that here is the point: the base class then reports
    ``evidence_reference`` as a dropped field on every write report, so nobody
    reads an absent link as "there was no evidence".
    """

    name = "alation"
    supports = frozenset({"standing", "established_at", "coverage", "detail"})

    def __init__(
        self,
        transport: VendorTransport,
        *,
        object_ids: Mapping[str, int],
        field_id: int,
        object_type: str = "table",
        region: str = "",
    ) -> None:
        super().__init__(transport, region=region)
        self._object_ids = dict(object_ids)
        self._field_id = field_id
        self._object_type = object_type

    def write(self, badge: Badge) -> None:
        object_id = self._object_ids.get(badge.dataset)
        if object_id is None:
            raise RuntimeError(
                f"no Alation object id is mapped for {badge.dataset!r}. Map it "
                "in the catalogue first."
            )
        self._send(
            WriteCall(
                vendor=self.name,
                method="PUT",
                path=f"/integration/v2/custom_field_value/{self._field_id}/",
                body={
                    "oid": object_id,
                    "otype": self._object_type,
                    "value": badge.render(),
                },
            ),
            badge,
        )


class DataHubTarget(_VendorTarget):
    """DataHub: an aspect on a dataset URN.

    DataHub's aspect model takes arbitrary structured documents, so the whole
    badge goes across. The URN is constructed from the platform and the dataset
    name and must match the one the ingestion job produced — a URN that differs
    by its environment segment creates a second, empty dataset rather than
    failing, and the badge lands on a dataset nobody looks at.
    """

    name = "datahub"
    supports = frozenset({"standing", "established_at", "coverage", "evidence_reference", "detail"})

    def __init__(
        self,
        transport: VendorTransport,
        *,
        platform: str,
        env: str = "PROD",
        region: str = "",
    ) -> None:
        super().__init__(transport, region=region)
        self._platform = platform
        self._env = env

    def urn_for(self, dataset: str) -> str:
        return f"urn:li:dataset:(urn:li:dataPlatform:{self._platform},{dataset},{self._env})"

    def write(self, badge: Badge) -> None:
        self._send(
            WriteCall(
                vendor=self.name,
                method="POST",
                path="/aspects?action=ingestProposal",
                body={
                    "proposal": {
                        "entityType": "dataset",
                        "entityUrn": self.urn_for(badge.dataset),
                        "aspectName": "pramaQuality",
                        "changeType": "UPSERT",
                        "aspect": {"value": badge.to_dict()},
                    }
                },
            ),
            badge,
        )
