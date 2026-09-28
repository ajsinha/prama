"""Anchoring the evidence chain outside Prama.

The hash chain proves a record has not been altered since the next one was
written. It cannot prove the *whole* chain was not rebuilt: somebody with write
access to the database can recompute every hash from genesis, and the rebuilt
chain verifies perfectly. What stops that is a witness outside Prama's control
that saw the chain head at a time.

An **anchor** is that witness. After a run, the head's record hash is sent to
it (32 bytes: no record, no dataset, no tenant name) and the receipt it returns
is stored beside the chain. A rebuilt chain then disagrees with a receipt the
rebuilder cannot forge, dated before the rebuild.

The anchor shipped is an RFC 3161 time-stamp authority: a standard every
auditor's toolkit already verifies (`openssl ts -verify`), run by a party that
is not the one being audited. Anchors are plugins behind `Anchor`; another
witness (a transparency log, a notary) is another subclass.

What an anchor does **not** do: it does not make a record true, and it does not
cover records written after the last anchor. The gap between anchors is the
window in which a rewrite goes unwitnessed, which is why a run anchors on
completion rather than on a daily schedule.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import abc
import asyncio
import base64
import dataclasses
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, ClassVar

from prama.core.errors import PramaError, ValidationError
from prama.evidence import tsp
from prama.security.egress import Gate


@dataclasses.dataclass(frozen=True, slots=True)
class Receipt:
    """What a witness returned for one digest."""

    kind: str
    authority: str
    digest: str
    #: The witness's own time, UTC ISO-8601.
    witnessed_at: str
    #: The proof, base64: for RFC 3161, the DER time-stamp token.
    token: str


class Anchor(abc.ABC):
    """A witness outside Prama that can attest a digest existed at a time."""

    kind: ClassVar[str]

    @property
    @abc.abstractmethod
    def authority(self) -> str:
        """Who the witness is, as a reader would look it up (a URL)."""

    @abc.abstractmethod
    def anchor(self, digest: str) -> Receipt:
        """Obtain a receipt for *digest*, or raise `PramaError`."""

    @abc.abstractmethod
    def check(self, receipt: Receipt) -> str:
        """Why *receipt* does not bind its digest, or ``""`` when it does.

        The binding only: that the proof names this digest. Whether the
        witness's signature is genuine is for the witness's own verifier, run
        by the auditor with the witness's certificate.
        """


class Rfc3161Anchor(Anchor):
    """An RFC 3161 time-stamp authority, over HTTP."""

    kind = "rfc3161"

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 30.0,
        region: str = "",
        gate: Gate | None = None,
        post: Callable[[bytes], bytes] | None = None,
    ) -> None:
        if not url and post is None:
            raise ValidationError(
                "an RFC 3161 anchor needs the time-stamp authority's URL",
                remedy="Set evidence.anchor.url to the time-stamp authority's address.",
            )
        self._url = url
        self._timeout = timeout
        self._region = region
        self._gate = gate
        self._post = post or self._http

    @property
    def authority(self) -> str:
        return self._url

    def anchor(self, digest: str) -> Receipt:
        if self._gate is not None:
            # What leaves is a digest, but it leaves, so it is declared and
            # checked like any other movement across the boundary.
            self._gate.require(
                "evidence-anchor",
                destination=self._region,
                subject="a digest of the evidence chain head",
            )
        request, nonce = tsp.request(digest)
        token = tsp.token_of(self._post(request))
        read = tsp.read_token(token)
        if read.imprint != digest or (read.nonce is not None and read.nonce != nonce):
            raise ValidationError(
                "the time-stamp authority answered for a different request",
                remedy="The reply does not bind this digest and nonce; do not store it.",
                context={"asked": digest, "answered": read.imprint},
            )
        return Receipt(
            kind=self.kind,
            authority=self._url,
            digest=digest,
            witnessed_at=read.at.isoformat().replace("+00:00", "Z"),
            token=base64.b64encode(token).decode("ascii"),
        )

    def check(self, receipt: Receipt) -> str:
        try:
            read = tsp.read_token(base64.b64decode(receipt.token))
        except (PramaError, ValueError) as exc:
            return f"the token could not be read: {exc}"
        if read.imprint != receipt.digest:
            return f"the token binds {read.imprint[:16]}…, not {receipt.digest[:16]}…"
        return ""

    def _http(self, body: bytes) -> bytes:
        import urllib.request

        request = urllib.request.Request(
            self._url,
            data=body,
            headers={"Content-Type": "application/timestamp-query"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            return bytes(response.read())


#: Kinds by name, for configuration. A new witness registers here.
ANCHORS: dict[str, type[Anchor]] = {Rfc3161Anchor.kind: Rfc3161Anchor}


def anchor_from(config: Any, *, residency: str | None = None) -> Anchor | None:
    """The configured anchor, or ``None`` when anchoring is off."""
    kind = str(config.get("evidence.anchor.kind", "none") or "none")
    if kind == "none":
        return None
    if kind not in ANCHORS:
        raise ValidationError(
            f"no evidence anchor of kind {kind!r}",
            remedy=f"One of: none, {', '.join(sorted(ANCHORS))}.",
            context={"kind": kind},
        )
    return Rfc3161Anchor(
        str(config.get("evidence.anchor.url", "") or ""),
        timeout=float(config.get("evidence.anchor.timeout", 30) or 30),
        region=str(config.get("evidence.anchor.region", "") or ""),
        gate=Gate.for_tenant(residency),
    )


async def anchor_head(uow: Any, tenant_id: str, anchor: Anchor) -> Any:
    """Anchor the tenant's chain head, and store what happened.

    Idempotent: a head already anchored is not sent again. A witness that
    cannot be reached is recorded as a failed anchor, with the reason, rather
    than raised past the caller, because the evidence it was protecting is
    already written and must not be rolled back on its account. The failure is
    visible (`prama evidence anchors`), and the next anchor covers the gap.
    """
    sequence = await uow.evidence.next_sequence(tenant_id) - 1
    if sequence < 0:
        return None
    head = await uow.evidence.head(tenant_id)
    existing = await uow.anchors.at(tenant_id, sequence)
    if existing is not None and existing.status == "anchored":
        return existing
    requested = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    try:
        receipt = await asyncio.to_thread(anchor.anchor, head)
    except (PramaError, OSError) as exc:
        return await uow.anchors.record(
            tenant_id=tenant_id,
            sequence=sequence,
            digest=head,
            kind=anchor.kind,
            authority=anchor.authority,
            status="failed",
            requested_at=requested,
            detail=str(exc)[:2000],
        )
    return await uow.anchors.record(
        tenant_id=tenant_id,
        sequence=sequence,
        digest=head,
        kind=receipt.kind,
        authority=receipt.authority,
        status="anchored",
        requested_at=requested,
        witnessed_at=receipt.witnessed_at,
        token=receipt.token,
    )


async def anchor_after_run(database: Any, tenant_id: str, config: Any) -> Any:
    """Anchor the chain head in a unit of work of its own, if anchoring is on.

    Called after the run's own unit of work has committed: the evidence exists
    whatever the witness does, and a witness that is down cannot roll it back.
    """
    if str(config.get("evidence.anchor.kind", "none") or "none") == "none":
        return None
    async with database.unit_of_work() as uow:
        tenant = await uow.tenants.get(tenant_id)
        anchor = anchor_from(config, residency=getattr(tenant, "residency", None))
        if anchor is None:
            return None
        return await anchor_head(uow, tenant_id, anchor)
