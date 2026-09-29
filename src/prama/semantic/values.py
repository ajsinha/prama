"""The vocabulary of a declaration.

These are the words a business owner uses about their data, given precise
enough meaning to compile. Every one of them is a *control generator*: declaring
a grain produces a uniqueness control, declaring a rhythm produces a freshness
control and a seasonality-aware volume monitor, declaring a value domain
produces a membership control (docs/03 §5).

They are immutable value objects rather than rows: two grains with the same
attributes are the same grain, they carry no identity, and they can be compared,
hashed and embedded in an evidence record without ceremony.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
import re
from typing import Any

from prama.core.errors import ValidationError

_IDENT = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_TIME_OF_DAY = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class Criticality(enum.IntEnum):
    """How much a defect here matters.

    Ordered, so that ``>=`` is meaningful in policy: Tier 1 attracts mandatory
    attestation, elevated severity floors, longer evidence retention and a
    higher re-examination cadence.
    """

    TIER_1 = 1  # regulatory or financial reporting; a defect is reportable
    TIER_2 = 2  # material to risk or operations
    TIER_3 = 3  # important to a business function
    TIER_4 = 4  # informational

    @property
    def label(self) -> str:
        return {
            1: "Tier 1 — Regulatory",
            2: "Tier 2 — Material",
            3: "Tier 3 — Business",
            4: "Tier 4 — Informational",
        }[int(self)]


#: How the console and the print packs name each tier, short enough for a badge.
TIER_LABELS: dict[int, str] = {
    1: "Tier 1 · regulatory",
    2: "Tier 2 · material",
    3: "Tier 3 · operational",
    4: "Tier 4 · informational",
}


class Sensitivity(enum.Enum):
    """What may be shown, and to whom.

    Drives masking everywhere a value could surface — samples, alerts, exports,
    chat prompts — rather than at each call site.
    """

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    PII = "pii"
    MNPI = "mnpi"  # material non-public information
    RESTRICTED = "restricted"

    @property
    def masked_by_default(self) -> bool:
        return self in (Sensitivity.PII, Sensitivity.MNPI, Sensitivity.RESTRICTED)

    @property
    def may_reach_external_model(self) -> bool:
        """Whether a value of this class may ever enter a hosted LLM prompt."""
        return self in (Sensitivity.PUBLIC, Sensitivity.INTERNAL)


class Temporality(enum.Enum):
    """What one record's relationship to time is.

    Chosen because each shape implies different controls: a snapshot needs
    partition completeness, an event stream needs ordering and late-arrival
    tolerance, an as-of-dated set needs a bitemporal roll-forward.
    """

    SNAPSHOT = "snapshot"  # a full picture as at a moment
    APPEND_ONLY = "append_only"  # facts accumulate, nothing changes
    EVENT_STREAM = "event_stream"  # ordered events, possibly late
    SLOWLY_CHANGING = "slowly_changing"  # dimension with validity periods
    AS_OF_DATED = "as_of_dated"  # bitemporal: valid time and knowledge time
    MUTABLE = "mutable"  # overwritten in place; the hardest to control


class Authoritativeness(enum.Enum):
    """Whether this is the source of a fact, or a copy of one.

    A replica's independent quality score is misleading: it is only ever as good
    as its origin, and its real controls are parity and staleness.
    """

    GOLDEN_SOURCE = "golden_source"
    DERIVED = "derived"
    REPLICA = "replica"
    EXTRACT = "extract"
    VENDOR_SUPPLIED = "vendor_supplied"
    UNKNOWN = "unknown"

    @property
    def is_copy(self) -> bool:
        return self in (Authoritativeness.REPLICA, Authoritativeness.EXTRACT)


class LifecycleState(enum.Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"

    @property
    def is_live(self) -> bool:
        return self in (LifecycleState.ACTIVE, LifecycleState.DEPRECATED)


class Optionality(enum.Enum):
    MANDATORY = "mandatory"
    CONDITIONAL = "conditional"  # mandatory when a stated condition holds
    OPTIONAL = "optional"


class ValueDomainKind(enum.Enum):
    CODELIST = "codelist"
    RANGE = "range"
    PATTERN = "pattern"
    FREE_TEXT = "free_text"
    BOOLEAN_FLAG = "boolean_flag"


@dataclasses.dataclass(frozen=True, slots=True)
class Grain:
    """What one record represents.

    The single most valuable sentence a business owner can write, because it
    determines uniqueness, duplication, completeness and the meaning of a row
    count — four controls from one declaration.
    """

    #: Business attribute names, in the order a human would say them.
    attributes: tuple[str, ...]
    #: The sentence as written, kept verbatim: it is what appears in the
    #: generated control's BECAUSE clause and in the attestation report.
    statement: str = ""

    def __post_init__(self) -> None:
        if not self.attributes:
            raise ValidationError(
                "a grain must name at least one attribute",
                remedy=(
                    "Answer 'what does one row represent?' — for example "
                    "'one position per account per instrument per business day'."
                ),
            )
        for name in self.attributes:
            _require_identifier(name, "grain attribute")
        if len(set(self.attributes)) != len(self.attributes):
            raise ValidationError(
                "a grain repeats an attribute",
                remedy="Each attribute may appear once in the grain.",
                context={"attributes": list(self.attributes)},
            )

    @property
    def arity(self) -> int:
        return len(self.attributes)

    def render(self) -> str:
        """Plain-language rendering, used when no statement was written."""
        if self.statement:
            return self.statement
        return "one record per " + " per ".join(a.replace("_", " ") for a in self.attributes)

    def to_dict(self) -> dict[str, Any]:
        return {"attributes": list(self.attributes), "statement": self.statement}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Grain:
        return cls(
            attributes=tuple(data.get("attributes", ())),
            statement=data.get("statement", ""),
        )


class Frequency(enum.Enum):
    CONTINUOUS = "continuous"
    INTRADAY = "intraday"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    AD_HOC = "ad_hoc"


@dataclasses.dataclass(frozen=True, slots=True)
class Rhythm:
    """When data is expected, and how much of it.

    ``volume_drivers`` is prior knowledge no detector should have to rediscover.
    A business owner saying "three times normal at month-end" is worth more than
    a year of history, and it is available on day one.
    """

    frequency: Frequency = Frequency.DAILY
    #: ``HH:MM`` in the calendar's timezone; the cut-off by which data must arrive.
    arrival_by: str | None = None
    #: A named business calendar, e.g. TARGET2, SIFMA. Absent means every day.
    calendar: str | None = None
    #: Tolerance around the cut-off before lateness is an incident, in seconds.
    lateness_tolerance_seconds: float = 0.0
    expected_volume_min: int | None = None
    expected_volume_max: int | None = None
    #: Named, declared causes of legitimate variation: "month_end", "trading_days".
    volume_drivers: tuple[str, ...] = ()
    #: The column that records when each row arrived: a load or ingestion
    #: timestamp. Freshness is measured on it. Without it, a table carries no
    #: record of when it was loaded, so a freshness control would have nothing
    #: to read, and none is generated (the reason is given instead).
    arrival_column: str | None = None

    def __post_init__(self) -> None:
        if self.arrival_by is not None and not _TIME_OF_DAY.match(self.arrival_by):
            raise ValidationError(
                f"arrival time {self.arrival_by!r} is not HH:MM",
                remedy="Use a 24-hour time such as 06:30.",
                context={"arrival_by": self.arrival_by},
            )
        if (
            self.expected_volume_min is not None
            and self.expected_volume_max is not None
            and self.expected_volume_min > self.expected_volume_max
        ):
            raise ValidationError(
                "expected minimum volume exceeds the maximum",
                remedy="Swap the two bounds, or leave one unset.",
                context={"min": self.expected_volume_min, "max": self.expected_volume_max},
            )

    @property
    def has_arrival_expectation(self) -> bool:
        return self.arrival_by is not None

    def render(self) -> str:
        parts = [self.frequency.value.replace("_", " ")]
        if self.arrival_by:
            parts.append(f"by {self.arrival_by}")
        if self.calendar:
            parts.append(f"on {self.calendar} business days")
        if self.expected_volume_min is not None or self.expected_volume_max is not None:
            lo = self.expected_volume_min if self.expected_volume_min is not None else "?"
            hi = self.expected_volume_max if self.expected_volume_max is not None else "?"
            parts.append(f"({lo} to {hi} records)")
        return ", ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frequency": self.frequency.value,
            "arrival_by": self.arrival_by,
            "calendar": self.calendar,
            "lateness_tolerance_seconds": self.lateness_tolerance_seconds,
            "expected_volume_min": self.expected_volume_min,
            "expected_volume_max": self.expected_volume_max,
            "volume_drivers": list(self.volume_drivers),
            # Only when declared, so a rhythm without one serialises (and
            # hashes) exactly as it did before the field existed.
            **({"arrival_column": self.arrival_column} if self.arrival_column else {}),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rhythm:
        return cls(
            frequency=Frequency(data.get("frequency", "daily")),
            arrival_by=data.get("arrival_by"),
            calendar=data.get("calendar"),
            lateness_tolerance_seconds=float(data.get("lateness_tolerance_seconds", 0.0)),
            expected_volume_min=data.get("expected_volume_min"),
            expected_volume_max=data.get("expected_volume_max"),
            arrival_column=data.get("arrival_column") or None,
            volume_drivers=tuple(data.get("volume_drivers", ())),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class ValueDomain:
    """The set of values an attribute may take.

    A code list reference is *as-of addressable*, so a control executed in March
    against the March ISO 4217 list replays identically in November. A domain
    that silently tracks "latest" is not replayable, and therefore is not
    evidence.
    """

    kind: ValueDomainKind = ValueDomainKind.FREE_TEXT
    codelist_ref: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    pattern: str | None = None
    allowed_values: tuple[str, ...] = ()
    case_sensitive: bool = True

    def __post_init__(self) -> None:
        if self.kind is ValueDomainKind.CODELIST and not (self.codelist_ref or self.allowed_values):
            raise ValidationError(
                "a code-list domain needs either a codelist reference or explicit values",
                remedy="Reference a registered code list, or list the permitted values.",
            )
        if self.kind is ValueDomainKind.PATTERN and not self.pattern:
            raise ValidationError(
                "a pattern domain needs a pattern",
                remedy="Supply a regular expression, or choose a different domain kind.",
            )
        if self.kind is ValueDomainKind.RANGE and self.minimum is None and self.maximum is None:
            raise ValidationError(
                "a range domain needs at least one bound",
                remedy="Supply a minimum, a maximum, or both.",
            )
        if self.pattern is not None:
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise ValidationError(
                    f"value-domain pattern is not a valid regular expression: {exc}",
                    remedy="Correct the expression; it is compiled at declaration time on purpose.",
                    context={"pattern": self.pattern},
                    cause=exc,
                ) from exc

    @property
    def is_constrained(self) -> bool:
        """Whether this domain can generate a membership or bound control."""
        return self.kind is not ValueDomainKind.FREE_TEXT

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "codelist_ref": self.codelist_ref,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "pattern": self.pattern,
            "allowed_values": list(self.allowed_values),
            "case_sensitive": self.case_sensitive,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValueDomain:
        return cls(
            kind=ValueDomainKind(data.get("kind", "free_text")),
            codelist_ref=data.get("codelist_ref"),
            minimum=data.get("minimum"),
            maximum=data.get("maximum"),
            pattern=data.get("pattern"),
            allowed_values=tuple(data.get("allowed_values", ())),
            case_sensitive=bool(data.get("case_sensitive", True)),
        )


def _require_identifier(value: str, what: str) -> None:
    if not _IDENT.match(value or ""):
        raise ValidationError(
            f"{what} {value!r} is not a valid business identifier",
            remedy=(
                "Use lower case letters, digits and underscores, starting with a letter — "
                "for example account_id."
            ),
            context={what: value},
        )
