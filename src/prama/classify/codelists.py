"""Reference code lists, addressable as of a date.

A membership control is only as replayable as the list behind it. ISO 4217
retired ``SLL`` for ``SLE`` in 2022 and ``ZWL`` for ``ZWG`` in 2024; a control
that resolves "the currency list" to whatever is current today reports last
year's perfectly correct data as invalid, and the evidence from last year
cannot be reproduced. So a list is a **dated snapshot**, and resolution takes
the date the control ran.

This is the same discipline as the plan cache: the artefact a verdict was
computed against has to still be obtainable, or the verdict is an assertion
rather than evidence.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import Final

from prama.core.errors import ValidationError


def _codes(block: str) -> frozenset[str]:
    """Read a whitespace-separated block of codes.

    The lists below are written as blocks rather than as quoted list literals
    on purpose: a hundred and eighty currency codes in quotes is unreadable,
    and — more to the point — undiffable, so a code silently added or dropped
    in a review would not stand out. In a block, it does.
    """
    return frozenset(block.split())


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class CodeListVersion:
    """One dated state of a code list."""

    #: The day this state took effect. A control that ran before it resolves to
    #: the previous state.
    effective_from: date
    codes: frozenset[str]
    #: Where it came from, so a disputed membership can be settled by looking
    #: at the source rather than at Prama.
    source: str = ""
    note: str = ""

    def __contains__(self, code: object) -> bool:
        return code in self.codes

    def __len__(self) -> int:
        return len(self.codes)


@dataclasses.dataclass(frozen=True, slots=True)
class CodeList:
    """A named list and every state of it Prama knows about."""

    name: str
    label: str
    authority: str
    versions: tuple[CodeListVersion, ...]
    case_sensitive: bool = True

    def __post_init__(self) -> None:
        if not self.versions:
            raise ValidationError(
                f"code list {self.name!r} has no versions",
                remedy="A list with no state cannot answer a membership question.",
            )
        dates = [v.effective_from for v in self.versions]
        if dates != sorted(dates):
            raise ValidationError(
                f"code list {self.name!r} has versions out of order",
                remedy="Order versions oldest first; resolution walks them forward.",
                context={"name": self.name},
            )

    def as_of(self, when: date | None = None) -> CodeListVersion:
        """The state in force on *when*, defaulting to the newest known.

        Resolving to the newest is right for authoring a control and wrong for
        replaying one, which is why the caller passes the date rather than the
        list guessing.
        """
        if when is None:
            return self.versions[-1]
        chosen = None
        for version in self.versions:
            if version.effective_from <= when:
                chosen = version
            else:
                break
        if chosen is None:
            raise ValidationError(
                f"code list {self.name!r} has no state as of {when.isoformat()}",
                remedy=(
                    f"The earliest state Prama holds begins "
                    f"{self.versions[0].effective_from.isoformat()}. A control cannot be "
                    "replayed against a list that did not exist; record the list as of "
                    "that date, or accept that this run is not reproducible and say so."
                ),
                context={"name": self.name, "requested": when.isoformat()},
            )
        return chosen

    def contains(self, code: str, *, when: date | None = None) -> bool:
        version = self.as_of(when)
        return (code if self.case_sensitive else code.upper()) in version.codes

    @property
    def latest(self) -> CodeListVersion:
        return self.versions[-1]


# ---------------------------------------------------------------------------
# ISO 4217 — currencies
# ---------------------------------------------------------------------------

#: Codes in force before the 2022 Sierra Leone redenomination. Held because
#: trades booked in 2021 are still reported on, and reporting them against
#: today's list would manufacture a violation on data that was correct.
_ISO4217_2021: Final = _codes(
    """AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND
    BOB BOV BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC
    CUC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD
    GNF GTQ GYD HKD HNL HRK HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS
    KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT
    MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK
    PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLL SOS SRD
    SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD USN UYI
    UYU UYW UZS VED VES VND VUV WST XAF XAG XAU XBA XBB XBC XBD XCD XDR XOF XPD
    XPF XPT XSU XTS XUA XXX YER ZAR ZMW ZWL"""
)

#: 2022: SLE replaces SLL (SLL remains valid through the transition); 2023:
#: Croatia adopts the euro and HRK is withdrawn.
_ISO4217_2023: Final = (_ISO4217_2021 | {"SLE"}) - {"HRK", "CUC"}

#: 2024: ZWG (Zimbabwe Gold) replaces ZWL. 2025: XCG (Caribbean guilder)
#: replaces ANG. Both transitions ran with the outgoing code still accepted for
#: a period, which is why the outgoing code is not removed in the same step —
#: removing it early is how a correct payment file gets rejected.
_ISO4217_2024: Final = (_ISO4217_2023 | {"ZWG"}) - {"ZWL"}
_ISO4217_2025: Final = (_ISO4217_2024 | {"XCG"}) - {"ANG"}

ISO_4217: Final = CodeList(
    name="iso4217",
    label="ISO 4217 currency code",
    authority="ISO",
    versions=(
        CodeListVersion(
            effective_from=date(2021, 1, 1),
            codes=_ISO4217_2021,
            source="ISO 4217 list one",
        ),
        CodeListVersion(
            effective_from=date(2023, 1, 1),
            codes=_ISO4217_2023,
            source="ISO 4217 list one",
            note="SLE added for Sierra Leone; HRK withdrawn on euro adoption",
        ),
        CodeListVersion(
            effective_from=date(2024, 4, 5),
            codes=_ISO4217_2024,
            source="ISO 4217 list one",
            note="ZWG replaces ZWL",
        ),
        CodeListVersion(
            effective_from=date(2025, 3, 31),
            codes=_ISO4217_2025,
            source="ISO 4217 list one",
            note="XCG replaces ANG",
        ),
    ),
)

# ---------------------------------------------------------------------------
# ISO 3166-1 — countries
# ---------------------------------------------------------------------------

_ISO3166_ALPHA2: Final = _codes(
    """AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI
    BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO
    CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO
    FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT
    HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY
    KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP
    MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE
    PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH
    SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO
    TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM
    ZW"""
)

ISO_3166: Final = CodeList(
    name="iso3166",
    label="ISO 3166-1 alpha-2 country code",
    authority="ISO",
    versions=(
        CodeListVersion(
            effective_from=date(2021, 1, 1),
            codes=_ISO3166_ALPHA2,
            source="ISO 3166-1 alpha-2",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Small operational lists that generate real controls
# ---------------------------------------------------------------------------

ISO_4217_MINOR_UNITS: Final = CodeList(
    name="zero_decimal_currencies",
    label="currency with no minor unit",
    authority="ISO 4217 list one",
    versions=(
        CodeListVersion(
            effective_from=date(2021, 1, 1),
            # A precision control that rounds JPY to two places is wrong in a
            # way nobody notices until a reconciliation breaks by a yen.
            codes=_codes(
                """BIF CLP DJF GNF ISK JPY KMF KRW PYG RWF UGX UYI VND VUV XAF
                XOF XPF"""
            ),
            source="ISO 4217 list one, minor unit 0",
        ),
    ),
)

SIDE: Final = CodeList(
    name="trade_side",
    label="trade side",
    authority="Prama convention",
    versions=(
        CodeListVersion(
            effective_from=date(2021, 1, 1),
            codes=frozenset({"BUY", "SELL"}),
        ),
    ),
    case_sensitive=False,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class CodeListRegistry:
    """Every code list Prama can resolve, by name."""

    def __init__(self) -> None:
        self._lists: dict[str, CodeList] = {}

    def register(self, code_list: CodeList) -> None:
        self._lists[code_list.name] = code_list

    def get(self, name: str) -> CodeList:
        try:
            return self._lists[name]
        except KeyError:
            raise ValidationError(
                f"no code list named {name!r}",
                remedy=(
                    "Known lists: " + ", ".join(sorted(self._lists)) + ". "
                    "An unresolved list would compile to a membership test against "
                    "nothing, so it is refused here."
                ),
                context={"requested": name},
            ) from None

    def find(self, name: str) -> CodeList | None:
        return self._lists.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._lists))

    def resolve(self, when: date | None = None) -> dict[str, tuple[str, ...]]:
        """Every list flattened for the lowering pass, as of one date.

        The IR wants values, not references, because a plan has to mean one
        fixed thing — see ``prama.ir.lower``. Producing them here keeps the
        as-of decision in one place instead of at every call site.
        """
        return {
            name: tuple(sorted(code_list.as_of(when).codes))
            for name, code_list in self._lists.items()
        }

    def __len__(self) -> int:
        return len(self._lists)

    def __contains__(self, name: object) -> bool:
        return name in self._lists


def default_registry() -> CodeListRegistry:
    registry = CodeListRegistry()
    for code_list in (ISO_4217, ISO_3166, ISO_4217_MINOR_UNITS, SIDE):
        registry.register(code_list)
    return registry


REGISTRY: Final = default_registry()
