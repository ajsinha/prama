"""Cross-field checks: the defects single-field validation cannot see.

Every identifier in this system already validates on its own — an IBAN's mod-97,
an ISIN's Luhn, a BIC's shape. All of those pass on a payment whose IBAN says
Germany and whose BIC says France, and that payment is wrong. docs/12 §3 names
this class as the one that catches real defects, and it is the class that a
column-by-column data quality tool structurally cannot reach.

These are registered as **PQL functions** rather than as a parallel validator
system, for one reason: ``SATISFIES`` already takes an arbitrary per-row
condition, so

    CHECK pacs008 SATISFIES IBAN_BIC_CONSISTENT(creditor_iban, creditor_bic)

needs no change to the language, compiles to SQL, and carries a reference
implementation the compiler is checked against. A second mechanism would have
needed all three built again.

**They compile.** Each of these has real SQL rather than falling back to a
residual, and that is worth the effort: a check that runs in the warehouse
examines every row, where a residual examines the rows a screen let through.
The arithmetic here is substring comparison and sign agreement, which every
engine can do.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from prama.pql.families import BOOLEAN, NUMBER, TEMPORAL, TEXT
from prama.pql.functions import UNSET, Function, FunctionRegistry


#: Currencies with no minor unit, from ISO 4217 list one. Duplicated from
#: ``prama.classify.codelists`` deliberately *not* — imported, so the two cannot
#: drift. A control that rounds JPY to two places is wrong in a way nobody
#: notices until a reconciliation breaks by a yen.
def _zero_decimal() -> tuple[str, ...]:
    from prama.classify.codelists import ISO_4217_MINOR_UNITS

    return tuple(sorted(ISO_4217_MINOR_UNITS.latest.codes))


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


# -- the checks ------------------------------------------------------------


def _iban_bic_consistent(args: list[Any]) -> Any:
    """IBAN country against BIC country.

    Both carry a country in a fixed position — the IBAN's first two characters,
    the BIC's fifth and sixth — and a payment where they disagree is routed
    somewhere the account is not. Neither identifier can detect this on its own,
    and both are individually valid when it happens.
    """
    iban, bic = _text(args[0]).upper(), _text(args[1]).upper()
    if len(iban) < 2 or len(bic) < 6:
        # Not a judgement about consistency. A malformed identifier is the
        # format control's finding, and answering False here would report one
        # defect as two and send it to the wrong person.
        return UNSET
    return iban[:2] == bic[4:6]


def _minor_units_ok(args: list[Any]) -> Any:
    """An amount's scale against its currency's minor unit.

    JPY has none. A ledger holding 1050.75 JPY is holding a number no yen amount
    can take, and every downstream sum inherits it. The check is only ever run
    against currencies whose minor unit is zero, because two decimal places is
    right for most of the rest and this is not the place to enumerate the
    exceptions.
    """
    amount, currency = _decimal(args[0]), _text(args[1]).upper()
    if amount is None or len(currency) != 3:
        return UNSET
    if currency not in _zero_decimal():
        return True
    return amount == amount.to_integral_value()


def _settles_after_trade(args: list[Any]) -> Any:
    """Settlement on or after the trade date.

    The cheapest possible test and one that finds real breaks: a settlement date
    before its trade date is almost always a date parsed in the wrong order, and
    a system that accepted it has been silently mis-ageing positions.
    """
    trade, settlement = _text(args[0]), _text(args[1])
    if not trade or not settlement:
        return UNSET
    return settlement >= trade


def _sign_matches_side(args: list[Any]) -> Any:
    """Signed quantity agreeing with the stated side.

    ``BUY`` is positive and ``SELL`` negative, which is a *convention* and not a
    law — some books carry both as positive and hold the direction only in the
    side. So this is a control an estate opts into rather than one Γ generates
    everywhere, and the reason it exists is that a book mixing the two
    conventions nets to a position nobody holds.
    """
    side, quantity = _text(args[0]).upper(), _decimal(args[1])
    if quantity is None or side not in ("BUY", "SELL", "B", "S"):
        return UNSET
    if quantity == 0:
        # Zero has no sign, and a zero-quantity row is a different finding.
        return UNSET
    return (quantity > 0) if side.startswith("B") else (quantity < 0)


def _same_country(args: list[Any]) -> Any:
    """Two ISO 3166 alpha-2 codes agreeing, wherever they came from."""
    first, second = _text(args[0]).upper(), _text(args[1]).upper()
    if len(first) != 2 or len(second) != 2:
        return UNSET
    return first == second


def _iban_country(args: list[Any]) -> Any:
    iban = _text(args[0]).upper()
    return iban[:2] if len(iban) >= 2 else UNSET


def _bic_country(args: list[Any]) -> Any:
    bic = _text(args[0]).upper()
    return bic[4:6] if len(bic) >= 6 else UNSET


def _isin_country(args: list[Any]) -> Any:
    """The ISIN's issuing country prefix.

    ``XS`` is not a country: it is the Eurobond prefix, and a control comparing
    an ISIN prefix to an issuer's jurisdiction has to allow for it or it fires
    on every Eurobond in the book.
    """
    isin = _text(args[0]).upper()
    return isin[:2] if len(isin) >= 2 else UNSET


BANKING_FUNCTIONS: tuple[Function, ...] = (
    Function(
        name="IBAN_BIC_CONSISTENT",
        summary=(
            "Whether an IBAN and a BIC name the same country. Both are valid "
            "individually when they disagree."
        ),
        arity=(2, 2),
        returns=BOOLEAN,
        argument_types=(TEXT, TEXT),
        sql=(
            # NULL, not a verdict, when either identifier is too short to carry
            # a country — exactly where `_iban_bic_consistent` returns UNSET.
            # The template used to answer `'' = ''` with TRUE, so a row with two
            # empty identifiers passed a consistency check on the strength of
            # having nothing to compare.
            "(CASE WHEN LENGTH({0}) < 2 OR LENGTH({1}) < 6 THEN NULL "
            "ELSE SUBSTR(UPPER({0}), 1, 2) = SUBSTR(UPPER({1}), 5, 2) END)"
        ),
        evaluate=_iban_bic_consistent,
    ),
    Function(
        name="MINOR_UNITS_OK",
        summary=(
            "Whether an amount's scale suits its currency. JPY has no minor "
            "unit, so 1050.75 JPY is a number no yen amount can take."
        ),
        arity=(2, 2),
        returns=BOOLEAN,
        argument_types=(NUMBER, TEXT),
        # The zero-decimal list is inlined at registration rather than joined
        # at runtime: it is seventeen codes that change once a decade, and a
        # join would make every row's check depend on a second table being
        # present in whatever schema the control runs against.
        sql=(
            # The malformed-input guard comes first, as it does in
            # `_minor_units_ok`: a two-letter code such as 'JP' is not a
            # currency, and the original template fell through to its ELSE and
            # answered TRUE — so a mistyped currency made the check pass.
            "(CASE WHEN {0} IS NULL OR LENGTH({1}) <> 3 THEN NULL "
            "WHEN UPPER({1}) IN (" + ", ".join(f"'{c}'" for c in _zero_decimal()) + ") "
            "THEN {0} = CAST({0} AS INTEGER) ELSE 1 = 1 END)"
        ),
        evaluate=_minor_units_ok,
    ),
    Function(
        name="SETTLES_AFTER_TRADE",
        summary="Whether a settlement date falls on or after its trade date.",
        arity=(2, 2),
        returns=BOOLEAN,
        argument_types=(TEMPORAL, TEMPORAL),
        sql=(
            "(CASE WHEN {0} IS NULL OR {1} IS NULL OR LENGTH({0}) = 0 "
            "OR LENGTH({1}) = 0 THEN NULL ELSE {1} >= {0} END)"
        ),
        evaluate=_settles_after_trade,
    ),
    Function(
        name="SIGN_MATCHES_SIDE",
        summary=(
            "Whether a signed quantity agrees with its side. A convention, not "
            "a law: a book mixing both nets to a position nobody holds."
        ),
        arity=(2, 2),
        returns=BOOLEAN,
        argument_types=(TEXT, NUMBER),
        sql=(
            # Matched on the whole side, not its first letter. The original
            # tested `SUBSTR({0}, 1, 1) = 'B'`, so 'BORROW' was read as a buy
            # and a securities-lending row was judged against an equity
            # convention. `_sign_matches_side` accepts BUY/SELL/B/S and nothing
            # else, and this now accepts the same four.
            "(CASE WHEN {1} IS NULL OR {1} = 0 THEN NULL "
            "WHEN UPPER({0}) IN ('BUY', 'B') THEN {1} > 0 "
            "WHEN UPPER({0}) IN ('SELL', 'S') THEN {1} < 0 "
            "ELSE NULL END)"
        ),
        evaluate=_sign_matches_side,
    ),
    Function(
        name="SAME_COUNTRY",
        summary="Whether two ISO 3166 alpha-2 codes agree.",
        arity=(2, 2),
        returns=BOOLEAN,
        argument_types=(TEXT, TEXT),
        sql=(
            # Alpha-2, as the name says. 'GBR' = 'GBR' is not two countries
            # agreeing, it is two alpha-3 codes in a field that expects alpha-2
            # — which `_same_country` reports as UNSET and this answered TRUE.
            "(CASE WHEN LENGTH({0}) <> 2 OR LENGTH({1}) <> 2 THEN NULL "
            "ELSE UPPER({0}) = UPPER({1}) END)"
        ),
        evaluate=_same_country,
    ),
    Function(
        name="IBAN_COUNTRY",
        summary="The country an IBAN names, from its first two characters.",
        arity=(1, 1),
        returns=TEXT,
        argument_types=(TEXT,),
        # TRIM, as the reference does: a padded identifier is read without
        # its padding. Without it the two disagreed on ' padded ' (found when
        # the packs' functions were tested with the packs installed).
        sql="(CASE WHEN LENGTH(TRIM({0})) < 2 THEN NULL ELSE SUBSTR(UPPER(TRIM({0})), 1, 2) END)",
        evaluate=_iban_country,
    ),
    Function(
        name="BIC_COUNTRY",
        summary="The country a BIC names, from its fifth and sixth characters.",
        arity=(1, 1),
        returns=TEXT,
        argument_types=(TEXT,),
        sql="(CASE WHEN LENGTH(TRIM({0})) < 6 THEN NULL ELSE SUBSTR(UPPER(TRIM({0})), 5, 2) END)",
        evaluate=_bic_country,
    ),
    Function(
        name="ISIN_COUNTRY",
        summary=(
            "An ISIN's issuing prefix. XS is the Eurobond prefix and not a "
            "country, so a jurisdiction comparison must allow for it."
        ),
        arity=(1, 1),
        returns=TEXT,
        argument_types=(TEXT,),
        # TRIM, as the reference does: a padded identifier is read without
        # its padding. Without it the two disagreed on ' padded ' (found when
        # the packs' functions were tested with the packs installed).
        sql="(CASE WHEN LENGTH(TRIM({0})) < 2 THEN NULL ELSE SUBSTR(UPPER(TRIM({0})), 1, 2) END)",
        evaluate=_isin_country,
    ),
)


def install(registry: FunctionRegistry | None = None) -> FunctionRegistry:
    """Add the banking functions to a registry.

    Explicit, like the calendars and for the same reason: a function that exists
    because a module was imported is one whose availability depends on import
    order, and a control that compiles in one process and refuses in another is
    the worst kind of intermittent.
    """
    from prama.pql.library import FUNCTIONS

    target = registry if registry is not None else FUNCTIONS
    for function in BANKING_FUNCTIONS:
        target.register(function)
    return target


__all__ = ["BANKING_FUNCTIONS", "install"]
