"""A small trading book, fabricated but shaped like the real thing.

Every field here exists because a control depends on it, and every defect is
one somebody has actually shipped to production: a duplicated delivery, a
truncated file, an ISIN whose checksum is wrong, a position that does not tie
to the ledger, a rate nobody refreshed.

The instruments and counterparties are real, publicly-listed identifiers —
ISINs and LEIs that pass their own checksums — because a study built on
invented identifiers would have every validity control fail for the wrong
reason and prove nothing.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import random
from datetime import date, timedelta
from decimal import Decimal

#: Real ISINs, checksum-valid. Used so that a validity control failing means
#: the *planted* defect and not the fabrication.
INSTRUMENTS: tuple[tuple[str, str, str, str, str], ...] = (
    ("GB0002634946", "BAE Systems plc", "EQUITY", "GBP", "XLON"),
    ("US0378331005", "Apple Inc", "EQUITY", "USD", "XNAS"),
    ("US5949181045", "Microsoft Corp", "EQUITY", "USD", "XNAS"),
    ("DE0007164600", "SAP SE", "EQUITY", "EUR", "XETR"),
    ("FR0000120271", "TotalEnergies SE", "EQUITY", "EUR", "XPAR"),
    ("NL0011821202", "ING Groep NV", "EQUITY", "EUR", "XAMS"),
    ("CH0012032048", "Roche Holding AG", "EQUITY", "CHF", "XSWX"),
    ("JP3633400001", "Toyota Motor Corp", "EQUITY", "JPY", "XTKS"),
    ("US912828YV68", "US Treasury 1.5% 2030", "GOVT_BOND", "USD", "XNYS"),
    ("DE0001102614", "Bund 0% 2031", "GOVT_BOND", "EUR", "XETR"),
    ("XS2434891219", "Vodafone 2.625% 2032", "CORP_BOND", "EUR", "XLUX"),
    ("US459200HU86", "IBM 4.15% 2039", "CORP_BOND", "USD", "XNYS"),
)

#: Real LEIs, checksum-valid (ISO 17442, mod-97).
COUNTERPARTIES: tuple[tuple[str, str, str, str], ...] = (
    ("7LTWFZYICNSX8D621K86", "Deutsche Bank AG", "DE", "A-"),
    ("HWUPKR0MPOU8FGXBT394", "JPMorgan Chase Bank NA", "US", "A+"),
    ("R0MUWSFPU8MPRO8K5P83", "BNP Paribas SA", "FR", "A+"),
    ("W22LROWP2IHZNBB6K528", "UBS AG", "CH", "A-"),
    ("K8MS7FD7N5Z2WQ51AZ71", "Barclays Bank PLC", "GB", "A"),
    ("MP6I5ZYZBEU3UXPYFY54", "Citibank NA", "US", "A+"),
)

CURRENCIES = ("USD", "EUR", "GBP", "CHF", "JPY")
SIDES = ("BUY", "SELL")
VENUES = ("XLON", "XNAS", "XETR", "XPAR", "XAMS", "XSWX", "XTKS", "XNYS", "XLUX")
BOOKS = ("EQ-CASH-01", "EQ-CASH-02", "RATES-01", "CREDIT-01", "TREASURY-01")
SETTLEMENT_STATES = ("PENDING", "SETTLED", "FAILED", "CANCELLED")

#: End-of-day rates against USD. Fixed rather than random, so a reconciliation
#: that fails is failing for the reason the study planted.
FX: dict[str, Decimal] = {
    "USD": Decimal("1.0000"),
    "EUR": Decimal("1.0850"),
    "GBP": Decimal("1.2670"),
    "CHF": Decimal("1.1240"),
    "JPY": Decimal("0.0067"),
}


@dataclasses.dataclass(frozen=True, slots=True)
class Trade:
    trade_id: str
    book: str
    isin: str
    counterparty_lei: str
    side: str
    quantity: float
    price: float
    notional: float | None
    currency: str
    trade_date: str
    settlement_date: str
    venue: str
    trader: str


@dataclasses.dataclass(frozen=True, slots=True)
class Position:
    book: str
    isin: str
    as_of_date: str
    quantity: float
    market_value: float
    currency: str


@dataclasses.dataclass(frozen=True, slots=True)
class LedgerEntry:
    book: str
    posting_date: str
    currency: str
    balance_usd: float


def business_days(end: date, count: int) -> list[date]:
    """The last *count* weekdays ending at *end*.

    Weekdays rather than a calendar, because these studies do not ship a
    holiday file and pretending they did would make the timeliness controls
    lie on Good Friday.
    """
    days: list[date] = []
    cursor = end
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    return sorted(days)


class Book:
    """Generates a coherent set of trades, positions and ledger balances.

    Coherent is the important word: positions are derived from trades and the
    ledger from positions, so the reconciliation control has something true to
    find when a defect breaks the chain. Data generated independently would
    reconcile only by accident, and every study would show a break.
    """

    def __init__(self, seed: int = 20260909, days: int = 10) -> None:
        # Seeded: two runs of a study must produce the same numbers, or the
        # README's figures are fiction the first time somebody re-runs it.
        self.random = random.Random(seed)
        self.dates = business_days(date(2026, 9, 8), days)
        self.trades: list[Trade] = []
        self.positions: list[Position] = []
        self.ledger: list[LedgerEntry] = []

    def generate(self, trades_per_day: int = 400) -> None:
        self._trades(trades_per_day)
        self._positions()
        self._ledger()

    def _trades(self, per_day: int) -> None:
        counter = 0
        for day in self.dates:
            for _ in range(per_day):
                counter += 1
                isin, _name, _kind, currency, venue = self.random.choice(INSTRUMENTS)
                lei, _cp, _juris, _rating = self.random.choice(COUNTERPARTIES)
                quantity = float(self.random.randint(1, 25_000))
                price = round(self.random.uniform(1.5, 480.0), 4)
                self.trades.append(
                    Trade(
                        trade_id=f"TRD{counter:08d}",
                        book=self.random.choice(BOOKS),
                        isin=isin,
                        counterparty_lei=lei,
                        side=self.random.choice(SIDES),
                        quantity=quantity,
                        price=price,
                        notional=round(quantity * price, 2),
                        currency=currency,
                        trade_date=day.isoformat(),
                        settlement_date=(day + timedelta(days=2)).isoformat(),
                        venue=venue,
                        trader=f"T{self.random.randint(100, 140)}",
                    )
                )

    def _positions(self) -> None:
        """Positions as the trades imply them, on the last business day."""
        as_of = self.dates[-1].isoformat()
        held: dict[tuple[str, str], list[float]] = {}
        for trade in self.trades:
            signed = trade.quantity if trade.side == "BUY" else -trade.quantity
            key = (trade.book, trade.isin)
            entry = held.setdefault(key, [0.0, 0.0, 0.0])
            entry[0] += signed
            entry[1] += signed * trade.price
        for (book, isin), (quantity, value, _) in sorted(held.items()):
            currency = next(i[3] for i in INSTRUMENTS if i[0] == isin)
            self.positions.append(
                Position(
                    book=book,
                    isin=isin,
                    as_of_date=as_of,
                    quantity=round(quantity, 4),
                    market_value=round(value, 2),
                    currency=currency,
                )
            )

    def _ledger(self) -> None:
        """The book of record: positions summed to USD, per book.

        This is what the reconciliation control compares against, so it is
        derived from the positions rather than generated — the two agree until
        a defect makes them disagree.
        """
        as_of = self.dates[-1].isoformat()
        totals: dict[str, Decimal] = {}
        for position in self.positions:
            rate = FX[position.currency]
            totals[position.book] = totals.get(position.book, Decimal(0)) + (
                Decimal(str(position.market_value)) * rate
            )
        for book, total in sorted(totals.items()):
            self.ledger.append(
                LedgerEntry(
                    book=book,
                    posting_date=as_of,
                    currency="USD",
                    balance_usd=float(round(total, 2)),
                )
            )

    # -- reference data ----------------------------------------------------

    def instrument_rows(self) -> list[dict[str, object]]:
        return [
            {
                "isin": isin,
                "name": name,
                "asset_class": kind,
                "currency": currency,
                "primary_venue": venue,
            }
            for isin, name, kind, currency, venue in INSTRUMENTS
        ]

    def counterparty_rows(self) -> list[dict[str, object]]:
        return [
            {
                "lei": lei,
                "legal_name": name,
                "jurisdiction": juris,
                "credit_rating": rating,
            }
            for lei, name, juris, rating in COUNTERPARTIES
        ]

    def fx_rows(self) -> list[dict[str, object]]:
        as_of = self.dates[-1].isoformat()
        return [
            {
                "currency_pair": f"{currency}USD",
                "rate_date": as_of,
                "rate": float(rate),
                "source": "VENDOR-A",
            }
            for currency, rate in FX.items()
            if currency != "USD"
        ]
