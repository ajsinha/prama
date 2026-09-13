"""Deterministic validators for semantic types.

The first and most important layer of the inference cascade (`FR-PRF-004`), and
the only one that is allowed to produce a verdict. An ISIN either satisfies its
check digit or it does not; no model is consulted, no confidence is attached,
and the answer is the same in March and in November.

**Two-stage validation, and why it is not an optimisation.** Most of these
checks are arithmetic a SQL engine cannot perform faithfully — Luhn over a
letter-expanded string, mod-97 over a 35-digit integer. The tempting move is to
compile the semantic type to its regular expression and call the result an ISIN
check. That is exactly the failure this codebase exists to prevent:
``GB0000000000`` passes every ISIN regex ever written and is not an ISIN, so the
control would be green on a column of fabricated identifiers.

So a validator declares what it *is*. A ``PATTERN`` or ``CODELIST`` validator is
complete in SQL. An ``ALGORITHM`` validator publishes a **screen** — a necessary
condition, cheap and engine-expressible, that no valid value can fail — and the
rows that survive the screen are checked exactly. The screen alone is never
allowed to report a pass, and :meth:`SemanticValidator.screen_is_complete` is
how a caller finds that out rather than assuming it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import abc
import dataclasses
import enum
import re
from typing import ClassVar, Final

from prama.core.errors import ValidationError

# ---------------------------------------------------------------------------
# What a validator is, and how much of it a database can do
# ---------------------------------------------------------------------------


class Expressibility(enum.Enum):
    """How completely an engine can perform this check on its own."""

    #: A regular expression is the entire check.
    PATTERN = "pattern"
    #: Membership in a finite, as-of addressable set.
    CODELIST = "codelist"
    #: Arithmetic the engine cannot do faithfully; needs the screen plus a pass
    #: over the surviving values.
    ALGORITHM = "algorithm"

    @property
    def complete_in_sql(self) -> bool:
        return self is not Expressibility.ALGORITHM


@dataclasses.dataclass(frozen=True, slots=True)
class Judgement:
    """The outcome of validating one value.

    Carries the reason, because "invalid ISIN" on a stewardship queue of four
    thousand rows is not a finding anybody can act on, whereas "check digit is 7,
    should be 4" is a typo somebody can fix in ten seconds.
    """

    valid: bool
    reason: str = ""
    #: Set when the value failed the cheap screen rather than the algorithm.
    #: Worth distinguishing: a screen failure is usually the wrong column
    #: entirely, an algorithm failure is usually one bad value.
    failed_screen: bool = False

    def __bool__(self) -> bool:
        return self.valid


VALID: Final = Judgement(valid=True)


class SemanticValidator(abc.ABC):
    """A named, deterministic test for membership of a semantic type.

    Registered by name and referenced from PQL as ``IS VALID 'isin'``. Concrete
    subclasses are the catalogue; nothing outside this package names one.
    """

    #: The name used in PQL and in an attribute declaration.
    name: ClassVar[str] = ""
    #: How a person refers to it.
    label: ClassVar[str] = ""
    #: The standard that defines it, quoted in the generated control's reason.
    #: An identifier check that cannot name its authority is folklore.
    authority: ClassVar[str] = ""
    expressibility: ClassVar[Expressibility] = Expressibility.ALGORITHM
    #: A regular expression every valid value satisfies. For PATTERN validators
    #: this is the whole check; otherwise it is a necessary condition only.
    screen_pattern: ClassVar[str] = ""
    #: What the algorithm establishes that the shape does not. Lives here
    #: rather than in the generator because it is knowledge about the type: a
    #: generated sentence saying "the check digit is part of the standard"
    #: under an ISO 8601 date control is wrong, and it is wrong precisely
    #: because whoever wrote it did not have the type in front of them.
    beyond_shape: ClassVar[str] = "a value of the right shape can still fail it"

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if cls.screen_pattern:
            cls._screen = re.compile(cls.screen_pattern)

    _screen: ClassVar[re.Pattern[str] | None] = None

    @property
    def screen_is_complete(self) -> bool:
        """Whether passing the screen is sufficient, not merely necessary.

        The question a compiler must ask before it emits a regex and calls the
        job done.
        """
        return self.expressibility.complete_in_sql

    def screen(self, value: str) -> bool:
        """The cheap necessary condition. Never sufficient for an ALGORITHM."""
        if self._screen is None:
            return True
        return self._screen.match(value) is not None

    def judge(self, value: str | None) -> Judgement:
        """Validate one value, with a reason when it fails.

        A null is *not* invalid. Whether a missing value is acceptable is a
        completeness question that the attribute's optionality already answers;
        conflating the two would make every nullable identifier column fail its
        format control, and the format control would be turned off.
        """
        if value is None:
            return VALID
        text = value.strip()
        if not text:
            return VALID
        if not self.screen(text):
            return Judgement(
                valid=False,
                reason=self.screen_failure(text),
                failed_screen=True,
            )
        return self.check(text)

    def screen_failure(self, value: str) -> str:
        return f"{value!r} is not shaped like {self.label or self.name}"

    @abc.abstractmethod
    def check(self, value: str) -> Judgement:
        """Validate a value already known to pass the screen."""

    def describe(self) -> str:
        """The sentence a generated control carries as its reason."""
        authority = f" ({self.authority})" if self.authority else ""
        return f"a well-formed {self.label or self.name}{authority}"


class PatternValidator(SemanticValidator):
    """A validator whose screen is the whole test."""

    expressibility: ClassVar[Expressibility] = Expressibility.PATTERN

    def check(self, value: str) -> Judgement:  # noqa: ARG002 — the screen was the test
        return VALID


# ---------------------------------------------------------------------------
# Alphanumeric expansion, shared by every ISO identifier scheme
# ---------------------------------------------------------------------------


#: A=10 … Z=35. ISO 6166, ISO 17442 and ISO 13616 all use this, which is why it
#: is written once here rather than three times slightly differently.
def _expand(value: str) -> str:
    out: list[str] = []
    for character in value:
        if character.isdigit():
            out.append(character)
        else:
            out.append(str(ord(character.upper()) - 55))
    return "".join(out)


def _mod97(digits: str) -> int:
    """``int(digits) % 97`` without building a 400-digit integer.

    An IBAN expands to about 40 digits and an arbitrary-precision int would be
    fine; this stays chunked anyway because the same routine is used on batches
    of millions of values and the allocation is the whole cost.
    """
    remainder = 0
    for index in range(0, len(digits), 7):
        remainder = int(str(remainder) + digits[index : index + 7]) % 97
    return remainder


def _luhn_ok(digits: str) -> bool:
    total, double = 0, False
    for character in reversed(digits):
        value = ord(character) - 48
        if double:
            value *= 2
            if value > 9:
                value -= 9
        total += value
        double = not double
    return total % 10 == 0


def _luhn_check_digit(digits: str) -> int:
    """The digit that would make ``digits + d`` satisfy Luhn."""
    total, double = 0, True
    for character in reversed(digits):
        value = ord(character) - 48
        if double:
            value *= 2
            if value > 9:
                value -= 9
        total += value
        double = not double
    return (10 - total % 10) % 10


# ---------------------------------------------------------------------------
# Securities identifiers
# ---------------------------------------------------------------------------


class IsinValidator(SemanticValidator):
    """ISO 6166. Two-letter country, nine alphanumerics, one check digit."""

    name = "isin"
    label = "ISIN"
    authority = "ISO 6166"
    beyond_shape = (
        "the check digit is part of the standard, so a value with an ISIN's shape "
        "and the wrong final digit is not an ISIN"
    )
    screen_pattern = r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$"

    def check(self, value: str) -> Judgement:
        expected = _luhn_check_digit(_expand(value[:11]))
        actual = int(value[11])
        if expected == actual:
            return VALID
        return Judgement(
            valid=False,
            reason=(
                f"check digit is {actual}, should be {expected} — "
                f"{value[:11]}{expected} would be valid"
            ),
        )


class SedolValidator(SemanticValidator):
    """A UK/Ireland SEDOL: six alphanumerics and a weighted check digit."""

    name = "sedol"
    label = "SEDOL"
    authority = "London Stock Exchange"
    #: Vowels are excluded by the scheme, which is a genuine part of the check
    #: rather than a nicety: it is what stops a SEDOL being confused with a
    #: truncated ticker.
    beyond_shape = "the weighted check digit is part of the standard"
    screen_pattern = r"^[0-9BCDFGHJKLMNPQRSTVWXYZ]{6}[0-9]$"

    _WEIGHTS: ClassVar[tuple[int, ...]] = (1, 3, 1, 7, 3, 9)

    def check(self, value: str) -> Judgement:
        total = sum(
            weight * (int(char) if char.isdigit() else ord(char) - 55)
            for weight, char in zip(self._WEIGHTS, value[:6], strict=True)
        )
        expected = (10 - total % 10) % 10
        actual = int(value[6])
        if expected == actual:
            return VALID
        return Judgement(valid=False, reason=f"check digit is {actual}, should be {expected}")


class CusipValidator(SemanticValidator):
    """A North American CUSIP: eight characters and a modified-Luhn digit."""

    name = "cusip"
    label = "CUSIP"
    authority = "ANSI X9.6"
    beyond_shape = "the check digit is part of the standard"
    screen_pattern = r"^[A-Z0-9*@#]{8}[0-9]$"

    def check(self, value: str) -> Judgement:
        total = 0
        for index, character in enumerate(value[:8]):
            if character.isdigit():
                figure = int(character)
            elif character == "*":
                figure = 36
            elif character == "@":
                figure = 37
            elif character == "#":
                figure = 38
            else:
                figure = ord(character) - 55
            if index % 2:
                figure *= 2
            total += figure // 10 + figure % 10
        expected = (10 - total % 10) % 10
        actual = int(value[8])
        if expected == actual:
            return VALID
        return Judgement(valid=False, reason=f"check digit is {actual}, should be {expected}")


class FigiValidator(SemanticValidator):
    """An OpenFIGI identifier: twelve characters, Luhn-checked."""

    name = "figi"
    label = "FIGI"
    authority = "OMG FIGI"
    #: The scheme forbids vowels in the first two characters and reserves the
    #: third as 'G'. Both are in the screen because both are cheap and both
    #: reject the overwhelming majority of wrong-column values.
    beyond_shape = "the check digit is part of the standard"
    screen_pattern = r"^[BCDFGHJKLMNPQRSTVWXYZ]{2}G[A-Z0-9]{8}[0-9]$"

    def check(self, value: str) -> Judgement:
        total = 0
        for index, character in enumerate(value[:11]):
            figure = int(character) if character.isdigit() else ord(character) - 55
            if index % 2:
                figure *= 2
            total += figure // 10 + figure % 10
        expected = (10 - total % 10) % 10
        actual = int(value[11])
        if expected == actual:
            return VALID
        return Judgement(valid=False, reason=f"check digit is {actual}, should be {expected}")


# ---------------------------------------------------------------------------
# Entity and account identifiers
# ---------------------------------------------------------------------------


class LeiValidator(SemanticValidator):
    """ISO 17442. Twenty characters whose mod-97 residue is 1."""

    name = "lei"
    label = "LEI"
    authority = "ISO 17442"
    #: Eighteen alphanumerics and two check digits, and deliberately nothing
    #: more. ISO 17442 reserves characters 5-6 as "00", and screening on that
    #: is tempting because it would tell an LEI from an internal party key of
    #: the same width almost for free. It is also wrong: LEIs issued in the
    #: interim CICI era predate the reservation and carry letters there —
    #: ``HWUPKR0MPOU8FGXBT394`` and ``7LTWFZYICNSX8D621K86`` are both live and
    #: both verify. A screen that rejected them would report a violation on
    #: perfectly good reference data, which is the one thing a necessary
    #: condition must never do.
    beyond_shape = "the two trailing check characters are part of ISO 17442"
    screen_pattern = r"^[A-Z0-9]{18}[0-9]{2}$"

    def check(self, value: str) -> Judgement:
        if _mod97(_expand(value)) == 1:
            return VALID
        return Judgement(
            valid=False,
            reason=f"the two trailing check characters do not verify against {value[:18]}",
        )


class IbanValidator(SemanticValidator):
    """ISO 13616. Country, check digits, then a national account number."""

    name = "iban"
    label = "IBAN"
    authority = "ISO 13616"
    beyond_shape = (
        "the check digits and the country-specific length are both part of ISO 13616, "
        "and a truncated account number verifies by luck once in ninety-seven times"
    )
    screen_pattern = r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$"

    #: Length is country-specific and is part of the standard, not a hint. A
    #: German IBAN of 21 characters is invalid however well it verifies, and
    #: omitting this check accepts a truncated account number whose mod-97
    #: happens to land on 1 once in 97 times.
    LENGTHS: ClassVar[dict[str, int]] = {
        "AD": 24,
        "AE": 23,
        "AL": 28,
        "AT": 20,
        "AZ": 28,
        "BA": 20,
        "BE": 16,
        "BG": 22,
        "BH": 22,
        "BR": 29,
        "BY": 28,
        "CH": 21,
        "CR": 22,
        "CY": 28,
        "CZ": 24,
        "DE": 22,
        "DK": 18,
        "DO": 28,
        "EE": 20,
        "EG": 29,
        "ES": 24,
        "FI": 18,
        "FO": 18,
        "FR": 27,
        "GB": 22,
        "GE": 22,
        "GI": 23,
        "GL": 18,
        "GR": 27,
        "GT": 28,
        "HR": 21,
        "HU": 28,
        "IE": 22,
        "IL": 23,
        "IS": 26,
        "IT": 27,
        "JO": 30,
        "KW": 30,
        "KZ": 20,
        "LB": 28,
        "LC": 32,
        "LI": 21,
        "LT": 20,
        "LU": 20,
        "LV": 21,
        "LY": 25,
        "MC": 27,
        "MD": 24,
        "ME": 22,
        "MK": 19,
        "MR": 27,
        "MT": 31,
        "MU": 30,
        "NL": 18,
        "NO": 15,
        "PK": 24,
        "PL": 28,
        "PS": 29,
        "PT": 25,
        "QA": 29,
        "RO": 24,
        "RS": 22,
        "SA": 24,
        "SC": 31,
        "SE": 24,
        "SI": 19,
        "SK": 24,
        "SM": 27,
        "ST": 25,
        "SV": 28,
        "TL": 23,
        "TN": 24,
        "TR": 26,
        "UA": 29,
        "VA": 22,
        "VG": 24,
        "XK": 20,
    }

    def check(self, value: str) -> Judgement:
        country = value[:2]
        expected_length = self.LENGTHS.get(country)
        if expected_length is None:
            return Judgement(
                valid=False,
                reason=f"{country} does not issue IBANs, or is not a country code",
            )
        if len(value) != expected_length:
            return Judgement(
                valid=False,
                reason=(
                    f"a {country} IBAN is {expected_length} characters; this one is {len(value)}"
                ),
            )
        if _mod97(_expand(value[4:] + value[:4])) == 1:
            return VALID
        return Judgement(valid=False, reason="the check digits do not verify")


class BicValidator(PatternValidator):
    """ISO 9362. No check digit exists — the shape is the whole standard."""

    name = "bic"
    label = "BIC"
    authority = "ISO 9362"
    screen_pattern = r"^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$"


class MicValidator(PatternValidator):
    """ISO 10383 market identifier. Four uppercase alphanumerics."""

    name = "mic"
    label = "MIC"
    authority = "ISO 10383"
    screen_pattern = r"^[A-Z0-9]{4}$"


class AbaRoutingValidator(SemanticValidator):
    """A US ABA routing transit number: nine digits, weighted 3-7-1."""

    name = "aba_routing"
    label = "ABA routing number"
    authority = "ABA"
    beyond_shape = "the weighted checksum is part of the standard"
    screen_pattern = r"^[0-9]{9}$"

    _WEIGHTS: ClassVar[tuple[int, ...]] = (3, 7, 1, 3, 7, 1, 3, 7, 1)

    def check(self, value: str) -> Judgement:
        total = sum(w * int(d) for w, d in zip(self._WEIGHTS, value, strict=True))
        if total % 10 == 0:
            return VALID
        return Judgement(valid=False, reason="the weighted checksum does not verify")


# ---------------------------------------------------------------------------
# Trade and product identifiers
# ---------------------------------------------------------------------------


class UtiValidator(PatternValidator):
    """A Unique Transaction Identifier: LEI-prefixed, up to 52 characters."""

    name = "uti"
    label = "UTI"
    authority = "CPMI-IOSCO"
    screen_pattern = r"^[A-Z0-9]{20}[A-Z0-9]{1,32}$"


class UpiValidator(PatternValidator):
    """A Unique Product Identifier: twelve alphanumerics from ANNA-DSB."""

    name = "upi"
    label = "UPI"
    authority = "ISO 4914"
    screen_pattern = r"^[A-Z0-9]{12}$"


class GtinValidator(SemanticValidator):
    """GTIN-8/12/13/14: alternating 3-1 weights over a digit string."""

    name = "gtin"
    label = "GTIN"
    authority = "GS1"
    beyond_shape = "the check digit is part of the standard"
    screen_pattern = r"^([0-9]{8}|[0-9]{12}|[0-9]{13}|[0-9]{14})$"

    def check(self, value: str) -> Judgement:
        body, actual = value[:-1], int(value[-1])
        # The 3-weight lands on the rightmost body digit whatever the length,
        # so the parity is taken from the end rather than the start.
        total = sum(
            int(digit) * (3 if index % 2 == 0 else 1) for index, digit in enumerate(reversed(body))
        )
        expected = (10 - total % 10) % 10
        if expected == actual:
            return VALID
        return Judgement(valid=False, reason=f"check digit is {actual}, should be {expected}")


class NpiValidator(SemanticValidator):
    """A US National Provider Identifier: Luhn over the 80840-prefixed number."""

    name = "npi"
    label = "NPI"
    authority = "CMS"
    beyond_shape = "the Luhn check digit is part of the standard"
    screen_pattern = r"^[0-9]{10}$"

    def check(self, value: str) -> Judgement:
        if _luhn_ok("80840" + value):
            return VALID
        return Judgement(valid=False, reason="the Luhn check digit does not verify")


class CreditCardValidator(SemanticValidator):
    """A payment card number. Present so it can be *found*, not so it is used.

    Detecting one is usually a discovery that cardholder data is somewhere it
    was not supposed to be, which is a sensitivity finding rather than a
    correctness one.
    """

    name = "card_number"
    label = "payment card number"
    authority = "ISO/IEC 7812"
    beyond_shape = "the Luhn check digit is part of the standard"
    screen_pattern = r"^[0-9]{12,19}$"

    def check(self, value: str) -> Judgement:
        if _luhn_ok(value):
            return VALID
        return Judgement(valid=False, reason="the Luhn check digit does not verify")


# ---------------------------------------------------------------------------
# Shape-only types
# ---------------------------------------------------------------------------


class EmailValidator(PatternValidator):
    name = "email"
    label = "email address"
    authority = "RFC 5322 (practical subset)"
    #: Deliberately not RFC 5322 in full. The complete grammar accepts quoted
    #: strings and comments that no mail system in this decade will deliver to,
    #: and a validator that accepts them reports a clean column that bounces.
    _LABEL = r"[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?"
    screen_pattern = rf"^[^@\s]{{1,64}}@{_LABEL}(\.{_LABEL})+$"


class UuidValidator(PatternValidator):
    name = "uuid"
    label = "UUID"
    authority = "RFC 4122"
    screen_pattern = (
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )


class UlidValidator(PatternValidator):
    name = "ulid"
    label = "ULID"
    authority = "ULID specification"
    #: Crockford base32: I, L, O and U are excluded to survive transcription.
    screen_pattern = r"^[0-7][0-9ABCDEFGHJKMNPQRSTVWXYZ]{25}$"


class Iso8601DateValidator(SemanticValidator):
    """A calendar date, as text. Rejects 2026-02-30 as well as 2026-13-01."""

    name = "iso_date"
    label = "ISO 8601 date"
    authority = "ISO 8601"
    beyond_shape = (
        "a date can have the right shape and not exist — 2026-02-30 is the case this catches"
    )
    screen_pattern = r"^\d{4}-\d{2}-\d{2}$"

    _LENGTHS: ClassVar[tuple[int, ...]] = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

    def check(self, value: str) -> Judgement:
        year, month, day = int(value[:4]), int(value[5:7]), int(value[8:])
        if not 1 <= month <= 12:
            return Judgement(valid=False, reason=f"there is no month {month}")
        limit = self._LENGTHS[month - 1]
        if month == 2 and not (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)):
            limit = 28
        if not 1 <= day <= limit:
            return Judgement(valid=False, reason=f"{value[:7]} has {limit} days, not {day}")
        return VALID


class HexColourValidator(PatternValidator):
    name = "hex_colour"
    label = "hex colour"
    screen_pattern = r"^#?[0-9a-fA-F]{6}$"


class Ipv4Validator(SemanticValidator):
    name = "ipv4"
    label = "IPv4 address"
    authority = "RFC 791"
    beyond_shape = (
        "an octet above 255, or one with a leading zero that routes differently in "
        "different resolvers, has the right shape and is not an address"
    )
    screen_pattern = r"^\d{1,3}(\.\d{1,3}){3}$"

    def check(self, value: str) -> Judgement:
        for octet in value.split("."):
            if int(octet) > 255:
                return Judgement(valid=False, reason=f"{octet} is not an octet")
            if len(octet) > 1 and octet[0] == "0":
                # A leading zero is read as octal by some resolvers and as
                # decimal by others, so the same string routes two ways. That
                # is a defect wherever it appears, not a formatting nicety.
                return Judgement(
                    valid=False, reason=f"octet {octet} has a leading zero and is ambiguous"
                )
        return VALID


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ValidatorRegistry:
    """Every deterministic validator, by name.

    A registry rather than a module-level dict so a deployment can add a
    national identifier scheme without editing this file, and so the set can be
    enumerated for the UI and for the conformance suite.
    """

    def __init__(self) -> None:
        self._validators: dict[str, SemanticValidator] = {}

    def register(self, validator: SemanticValidator) -> None:
        if not validator.name:
            raise ValidationError(
                f"{type(validator).__name__} has no name",
                remedy="Set the class-level `name`; it is how PQL refers to the type.",
            )
        existing = self._validators.get(validator.name)
        if existing is not None and type(existing) is not type(validator):
            raise ValidationError(
                f"two different validators claim the name {validator.name!r}",
                remedy=(
                    "Rename one. A control saying IS VALID 'lei' must mean exactly "
                    "one thing, or the same control changes meaning on a different node."
                ),
                context={"name": validator.name},
            )
        self._validators[validator.name] = validator

    def get(self, name: str) -> SemanticValidator:
        try:
            return self._validators[name]
        except KeyError:
            raise ValidationError(
                f"no validator named {name!r}",
                remedy=(
                    "Known types: " + ", ".join(sorted(self._validators)) + ". "
                    "An unknown semantic type would compile to a check that passes "
                    "everything, so it is refused here instead."
                ),
                context={"requested": name},
            ) from None

    def find(self, name: str) -> SemanticValidator | None:
        """A validator by name, however the author capitalised it.

        Case-insensitive because PQL is written in upper case and these are
        registered in lower. `IS VALID ISIN` — the spelling in two of the
        parser's own remedies, and the one anybody would write — resolved to
        nothing, so the error message told an author to type something that
        does not work (QA finding PQL-075).

        A semantic type is a name a person chooses, not an identifier a machine
        mints, and `isin` and `ISIN` are the same name.
        """
        found = self._validators.get(name)
        if found is not None:
            return found
        return self._validators.get(name.strip().lower())

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._validators))

    def __contains__(self, name: object) -> bool:
        if name in self._validators:
            return True
        return isinstance(name, str) and name.strip().lower() in self._validators

    def __len__(self) -> int:
        return len(self._validators)


def default_registry() -> ValidatorRegistry:
    registry = ValidatorRegistry()
    for validator in (
        IsinValidator(),
        SedolValidator(),
        CusipValidator(),
        FigiValidator(),
        LeiValidator(),
        IbanValidator(),
        BicValidator(),
        MicValidator(),
        AbaRoutingValidator(),
        UtiValidator(),
        UpiValidator(),
        GtinValidator(),
        NpiValidator(),
        CreditCardValidator(),
        EmailValidator(),
        UuidValidator(),
        UlidValidator(),
        Iso8601DateValidator(),
        HexColourValidator(),
        Ipv4Validator(),
    ):
        registry.register(validator)
    return registry


#: The process-wide registry. A module-level instance because the catalogue is
#: static and building it per call would dominate the cost of validating a
#: column of ten million values.
REGISTRY: Final = default_registry()
