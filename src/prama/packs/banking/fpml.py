"""FpML: derivatives, where the two sides of a trade are the point.

An FpML trade names its parties and, for each leg, who pays and who receives. A
parser that flattened it into a row of amounts would lose the direction — and a
swap whose direction is lost is a position of twice the size or none at all,
depending on which way the loss went.

So the shape here keeps three things a flat reader drops:

* **Payer and receiver, per leg.** Not "counterparty": a two-leg swap has four
  party references and the same firm appears on both sides of different legs.
* **Notional per leg, with its currency.** Legs in different currencies are
  ordinary, and a total that added them is a number in no currency at all.
* **Which party the document is written from.** ``onBehalfOf`` decides whether a
  leg is an asset or a liability, and a report built without it has the sign of
  every position depending on who sent the file.

**Namespaces are matched on local name**, as in ``iso20022``: FpML's namespace
carries its version, and a parser keyed on the full namespace refuses next
year's file.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import re
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree import ElementTree

_VERSION = re.compile(r"fpml-(\d+-\d+)|version=\"([\d-]+)\"")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(element: Any, *path: str) -> Any:
    if element is None:
        return None
    current = element
    for name in path:
        found = next((c for c in list(current) if _local(c.tag) == name), None)
        if found is None:
            return None
        current = found
    return current


def _text(element: Any, *path: str) -> str:
    if element is None:
        return ""
    found = _find(element, *path) if path else element
    if found is None or found.text is None:
        return ""
    text: str = found.text
    return text.strip()


def _children(element: Any, name: str) -> list[Any]:
    if element is None:
        return []
    return [child for child in list(element) if _local(child.tag) == name]


def _decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text) if text else None
    except (InvalidOperation, ValueError):
        return None


@dataclasses.dataclass(frozen=True, slots=True)
class Leg:
    """One side of a trade, with its direction intact."""

    payer: str
    receiver: str
    notional: Decimal | None
    currency: str
    #: ``fixed`` · ``floating`` · ``unknown``
    kind: str = "unknown"
    rate: Decimal | None = None
    index: str = ""

    @property
    def has_direction(self) -> bool:
        """Whether this leg says who pays whom.

        A leg without it is not a leg with an unknown counterparty — it is a
        leg whose sign cannot be determined, and any position built from it is
        wrong in a direction nobody can predict.
        """
        return bool(self.payer and self.receiver)

    def signed_for(self, party: str) -> Decimal | None:
        """The notional from one party's point of view.

        Positive when they receive, negative when they pay, ``None`` when the
        leg does not involve them or does not say. ``None`` rather than zero:
        zero is a position, and this is the absence of one.
        """
        if self.notional is None or not self.has_direction:
            return None
        if party == self.receiver:
            return self.notional
        if party == self.payer:
            return -self.notional
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "payer": self.payer,
            "receiver": self.receiver,
            "notional": None if self.notional is None else str(self.notional),
            "currency": self.currency,
            "kind": self.kind,
            "rate": None if self.rate is None else str(self.rate),
            "index": self.index,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Trade:
    """An FpML trade, in a shape a control can assert on."""

    trade_id: str
    trade_date: str
    version: str
    parties: tuple[str, ...] = ()
    #: The party the document is written from. Decides whether a leg is an
    #: asset or a liability.
    on_behalf_of: str = ""
    legs: tuple[Leg, ...] = ()
    defects: tuple[str, ...] = ()

    @property
    def has_two_legs(self) -> bool:
        """Two legs are present. Says nothing about whether they are directed."""
        return len(self.legs) >= 2

    @property
    def is_two_sided(self) -> bool:
        """Two legs, *and* each one says who pays and who receives.

        Counting legs alone would answer yes for a document where a leg has no
        payer, and "two-sided" is read downstream as "the offsetting obligation
        is known" — which is precisely what a directionless leg does not give.
        """
        return self.has_two_legs and all(leg.has_direction for leg in self.legs)

    @property
    def currencies(self) -> tuple[str, ...]:
        return tuple(sorted({leg.currency for leg in self.legs if leg.currency}))

    @property
    def is_cross_currency(self) -> bool:
        return len(self.currencies) > 1

    def net_for(self, party: str) -> Decimal | None:
        """Net notional from one party's view, or ``None`` if it cannot be netted.

        Refuses on a cross-currency trade rather than adding euros to dollars:
        a total across currencies is a number in no currency at all, and it
        looks exactly like a number in one.
        """
        if self.is_cross_currency:
            return None
        if not self.legs:
            # A trade with no legs, or a party on none of them, nets to
            # nothing — and `Decimal(0)` is a number, which reads as "these
            # positions cancel out" rather than "there were no positions"
            # (QA finding PCK-105). The two are opposite conclusions about the
            # same counterparty and this method is where they were conflated.
            return None
        amounts = [leg.signed_for(party) for leg in self.legs]
        if any(amount is None for amount in amounts):
            return None
        total = Decimal(0)
        for amount in amounts:
            assert amount is not None  # every None was rejected above
            total += amount
        return total

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "trade_date": self.trade_date,
            "version": self.version,
            "parties": list(self.parties),
            "on_behalf_of": self.on_behalf_of,
            "legs": [leg.to_dict() for leg in self.legs],
            "leg_count": len(self.legs),
            "currencies": list(self.currencies),
            "cross_currency": self.is_cross_currency,
            "defect_count": len(self.defects),
        }


def parse(xml: str) -> Trade:
    """One FpML document. Never raises on malformed XML."""
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        return Trade(
            trade_id="",
            trade_date="",
            version="",
            defects=(f"the document is not well-formed XML: {exc}",),
        )

    matched = _VERSION.search(root.tag) or _VERSION.search(
        " ".join(f'{k}="{v}"' for k, v in root.attrib.items())
    )
    version = next((g for g in (matched.groups() if matched else ()) if g), "")

    defects: list[str] = []
    # Not `or root`: that truth-tests an Element, which ElementTree deprecates
    # and which is ambiguous anyway — an element with no children is falsy
    # while being perfectly present.
    trade = _find(root, "trade")
    if trade is None:
        trade = root
    header = _find(trade, "tradeHeader")
    identifier = _find(header, "partyTradeIdentifier")

    parties = tuple(
        party.get("id", "") or _text(party, "partyId") for party in _children(root, "party")
    )
    behalf = _find(root, "onBehalfOf")
    on_behalf_of = "" if behalf is None else (behalf.get("href", "") or _text(behalf, "href"))

    legs: list[Leg] = []
    swap = _find(trade, "swap")
    containers = _children(swap, "swapStream") if swap is not None else []
    if not containers:
        containers = _children(trade, "swapStream")
    for stream in containers:
        legs.append(_leg(stream))

    if not legs:
        defects.append("the document carries no legs, so it states no obligation")
    for position, leg in enumerate(legs, start=1):
        if not leg.has_direction:
            # Named, because a leg without direction has a sign nobody can
            # determine and every position built from it is wrong in a
            # direction nobody can predict.
            defects.append(f"leg {position} does not say who pays and who receives")

    return Trade(
        trade_id=_text(identifier, "tradeId"),
        trade_date=_text(header, "tradeDate"),
        version=version,
        parties=tuple(p for p in parties if p),
        on_behalf_of=on_behalf_of,
        legs=tuple(legs),
        defects=tuple(defects),
    )


def _reference(stream: Any, name: str) -> str:
    """A party reference, from ``href`` or from the element's own text.

    FpML writes it as an attribute; some producers write it as text. Reading
    only one returns nothing for the other, and "no payer" is a finding a
    control reports as a missing direction rather than as a parser that did not
    look.
    """
    node = _find(stream, name)
    if node is None:
        return ""
    return node.get("href", "") or _text(node)


def _leg(stream: Any) -> Leg:
    payer = _reference(stream, "payerPartyReference")
    receiver = _reference(stream, "receiverPartyReference")
    amount = _find(
        stream, "calculationPeriodAmount", "calculation", "notionalSchedule", "notionalStepSchedule"
    )
    if amount is None:
        amount = _find(stream, "calculationPeriodAmount", "calculation", "notionalAmount")

    fixed = _find(stream, "calculationPeriodAmount", "calculation", "fixedRateSchedule")
    floating = _find(stream, "calculationPeriodAmount", "calculation", "floatingRateCalculation")

    return Leg(
        payer=payer,
        receiver=receiver,
        notional=_decimal(_text(amount, "initialValue") or _text(amount, "amount")),
        currency=_text(amount, "currency"),
        kind="fixed" if fixed is not None else ("floating" if floating is not None else "unknown"),
        rate=_decimal(_text(fixed, "initialValue")) if fixed is not None else None,
        index=_text(floating, "floatingRateIndex") if floating is not None else "",
    )


__all__ = ["Leg", "Trade", "parse"]
