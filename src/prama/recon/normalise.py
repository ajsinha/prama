"""Making two sides comparable, and recording what it took.

`FR-REC-002`. Almost no real reconciliation compares like with like. The
sub-ledger holds trade currency and the GL holds reporting currency; one uses
ISO country codes and the other uses an internal three-letter scheme; one
stamps UTC and the other local time; one holds amounts in units and the other
in thousands. Every one of those is a translation, and every translation is a
place a break can be manufactured.

**The rate used is part of the answer, not part of the plumbing.** A
reconciliation that converts last month's balances at today's rate is wrong,
and the error is invisible: the breaks look like ordinary differences. Worse,
it is not reproducible — run it again next week and the breaks move, so a break
somebody investigated and cleared reappears with a different number and nobody
can tell whether the data changed or the rate did.

So every normalisation resolves **as of the business date being reconciled**,
carries the source it resolved from, and refuses when it cannot. A missing rate
is a refusal, never a fallback to 1.0 or to the latest — both of which produce
a number that looks like a reconciliation and is not one.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Mapping
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

from prama.core.errors import ValidationError


class Unavailable(Exception):
    """A normalisation input that is missing, and must not be guessed at.

    An exception rather than a sentinel because there is no safe default. A
    missing FX rate cannot become 1.0 (which silently reconciles euros against
    dollars), nor the latest rate (which makes the run irreproducible), nor
    zero. The only correct behaviour is to stop and say which rate, for which
    day, was not there.
    """


@dataclasses.dataclass(frozen=True, slots=True)
class Rate:
    """One exchange rate, as of one day, from one source."""

    base: str
    quote: str
    #: Decimal throughout. A reconciliation exists to detect small differences,
    #: and binary floating point manufactures exactly the kind of small
    #: difference it is looking for — a rate applied in float to a million
    #: amounts produces a residual indistinguishable from a real break.
    rate: Decimal
    as_of: date
    source: str

    def convert(self, amount: Decimal) -> Decimal:
        return amount * self.rate

    def to_dict(self) -> dict[str, Any]:
        return {
            "base": self.base,
            "quote": self.quote,
            "rate": str(self.rate),
            "as_of": self.as_of.isoformat(),
            "source": self.source,
        }


class RateSource:
    """Rates, addressable by day. Nothing here interpolates or falls back.

    A rate table with gaps is a normal thing to have, and filling them is a
    business decision — carry forward the previous close, or refuse and chase
    the vendor. Making that choice inside a converter would bury it, so the
    choice is a constructor argument and the answer is recorded either way.
    """

    def __init__(
        self,
        rates: Mapping[tuple[str, str, date], Decimal] | None = None,
        *,
        source: str = "",
        carry_forward_days: int = 0,
    ) -> None:
        self._rates: dict[tuple[str, str, date], Decimal] = dict(rates or {})
        self._source = source or "unnamed rate source"
        #: How many days back a missing rate may be carried forward from. Zero
        #: means refuse, which is the right default: a bank holiday is a
        #: legitimate gap and a vendor outage is not, and only the business
        #: knows which it is looking at.
        self._carry_forward = carry_forward_days

    def add(self, base: str, quote: str, when: date, rate: Decimal | str) -> None:
        self._rates[(base.upper(), quote.upper(), when)] = Decimal(str(rate))

    def get(self, base: str, quote: str, when: date) -> Rate:
        base, quote = base.upper(), quote.upper()
        if base == quote:
            return Rate(base, quote, Decimal(1), when, "identity")

        direct = self._lookup(base, quote, when)
        if direct is not None:
            rate, actual = direct
            return Rate(base, quote, rate, actual, self._describe(actual, when))

        inverse = self._lookup(quote, base, when)
        if inverse is not None:
            rate, actual = inverse
            if rate == 0:
                raise Unavailable(f"the {quote}/{base} rate for {when} is zero")
            # Inverting is arithmetic rather than a second opinion, and the
            # source says so: a break traced back to a rate should show whether
            # the number was quoted or derived.
            return Rate(
                base,
                quote,
                Decimal(1) / rate,
                actual,
                f"{self._describe(actual, when)}, inverted from {quote}/{base}",
            )

        raise Unavailable(
            f"no {base}/{quote} rate for {when.isoformat()} in {self._source}"
            + (
                f" (and none within {self._carry_forward} days before it)"
                if self._carry_forward
                else ". Rates are not carried forward unless the business has said "
                "they may be; a bank holiday is a legitimate gap and a vendor "
                "outage is not, and only you know which this is"
            )
        )

    def _lookup(self, base: str, quote: str, when: date) -> tuple[Decimal, date] | None:
        exact = self._rates.get((base, quote, when))
        if exact is not None:
            return exact, when
        for back in range(1, self._carry_forward + 1):
            earlier = date.fromordinal(when.toordinal() - back)
            found = self._rates.get((base, quote, earlier))
            if found is not None:
                return found, earlier
        return None

    def _describe(self, actual: date, wanted: date) -> str:
        if actual == wanted:
            return self._source
        return f"{self._source}, carried forward from {actual.isoformat()}"


# ---------------------------------------------------------------------------
# Normalisers
# ---------------------------------------------------------------------------


class Applied(enum.Enum):
    """What a normalisation did, for the audit trail on a break."""

    NOTHING = "nothing"
    CURRENCY = "currency"
    SCALE = "scale"
    CODE_SET = "code_set"
    SIGN = "sign"
    ROUNDING = "rounding"


@dataclasses.dataclass(frozen=True, slots=True)
class Normalised:
    """A value made comparable, and every step that got it there.

    The steps are kept because the first question about any break is "is this
    real, or did we translate it wrong?", and a value with no history behind it
    cannot answer.
    """

    value: Any
    steps: tuple[tuple[Applied, str], ...] = ()

    def with_step(self, applied: Applied, detail: str, value: Any) -> Normalised:
        return Normalised(value=value, steps=(*self.steps, (applied, detail)))

    def describe(self) -> str:
        if not self.steps:
            return "compared as it stands"
        return "; ".join(detail for _, detail in self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": str(self.value),
            "steps": [[applied.value, detail] for applied, detail in self.steps],
            "description": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class AmountSpec:
    """How one side states a monetary amount."""

    currency_column: str = ""
    #: A fixed currency when the side does not carry one per row.
    currency: str = ""
    #: Multiplier to units: 1000 for a ledger stated in thousands.
    scale: Decimal = Decimal(1)
    #: True when this side states the opposite sign — the single most common
    #: cause of a reconciliation that is exactly double the expected break.
    invert_sign: bool = False
    #: Decimal places to round to before comparison. None compares at full
    #: precision, which is right when both sides are exact and wrong when one
    #: has already been rounded for reporting.
    scale_places: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "currency_column": self.currency_column,
            "currency": self.currency,
            "scale": str(self.scale),
            "invert_sign": self.invert_sign,
            "scale_places": self.scale_places,
        }


class AmountNormaliser:
    """Brings two monetary columns onto one currency, scale and sign."""

    def __init__(
        self,
        spec: AmountSpec,
        *,
        target_currency: str,
        rates: RateSource | None = None,
    ) -> None:
        self._spec = spec
        self._target = target_currency.upper()
        self._rates = rates

    def normalise(self, row: Mapping[str, Any], column: str, when: date) -> Normalised:
        raw = row.get(column)
        if raw is None:
            return Normalised(value=None)
        try:
            amount = Decimal(str(raw))
        except InvalidOperation as error:
            raise ValidationError(
                f"{column} holds {raw!r}, which is not an amount",
                remedy=(
                    "A reconciliation cannot compare a value it cannot parse. Correct "
                    "the source, or exclude the row explicitly rather than letting it "
                    "become a break of unknown size."
                ),
                cause=error,
            ) from error

        result = Normalised(value=amount)
        spec = self._spec

        if spec.invert_sign:
            amount = -amount
            result = result.with_step(
                Applied.SIGN,
                "sign inverted: this side states the opposite convention",
                amount,
            )

        if spec.scale != 1:
            amount = amount * spec.scale
            result = result.with_step(Applied.SCALE, f"scaled by {spec.scale} to units", amount)

        currency = (
            str(row.get(spec.currency_column) or "").upper()
            if spec.currency_column
            else spec.currency.upper()
        )
        if currency and currency != self._target:
            if self._rates is None:
                raise Unavailable(
                    f"{column} is in {currency} and must be compared in "
                    f"{self._target}, and no rate source was configured"
                )
            rate = self._rates.get(currency, self._target, when)
            amount = rate.convert(amount)
            result = result.with_step(
                Applied.CURRENCY,
                f"converted {currency} to {self._target} at {rate.rate} "
                f"({rate.source}, as of {rate.as_of.isoformat()})",
                amount,
            )

        if spec.scale_places is not None:
            quantum = Decimal(1).scaleb(-spec.scale_places)
            # Banker's rounding, matching what ledgers do. Rounding half up
            # instead introduces a systematic upward bias that shows as a small
            # persistent break on every large population.
            amount = amount.quantize(quantum, rounding=ROUND_HALF_EVEN)
            result = result.with_step(
                Applied.ROUNDING,
                f"rounded to {spec.scale_places} places (half to even)",
                amount,
            )

        return Normalised(value=amount, steps=result.steps)


class CodeNormaliser:
    """Maps one side's code set onto the other's.

    An unmapped code is a refusal rather than a pass-through. Passing it
    through produces a row that matches nothing and appears in the break
    population as a missing record — a break whose real cause is a mapping gap,
    and which somebody will spend an afternoon investigating as a data problem.
    """

    def __init__(self, mapping: Mapping[str, str], *, name: str = "") -> None:
        self._mapping = {key.upper(): value for key, value in mapping.items()}
        self._name = name or "code mapping"

    def normalise(self, value: Any) -> Normalised:
        if value is None:
            return Normalised(value=None)
        key = str(value).upper()
        if key not in self._mapping:
            raise Unavailable(
                f"{value!r} is not in the {self._name}. An unmapped code passed "
                f"through would appear in the break population as a missing record, "
                f"and the afternoon spent investigating it would be spent on the "
                f"wrong thing"
            )
        mapped = self._mapping[key]
        if mapped == str(value):
            return Normalised(value=mapped)
        return Normalised(value=mapped).with_step(
            Applied.CODE_SET, f"{value} mapped to {mapped} via {self._name}", mapped
        )

    def covers(self, values: set[str]) -> tuple[str, ...]:
        """Codes present in the data and absent from the mapping.

        Offered so a gap is found before a run rather than during one: a
        reconciliation that fails halfway through on an unmapped code has
        already spent the scan.
        """
        return tuple(sorted(v for v in values if str(v).upper() not in self._mapping))
