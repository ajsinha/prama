"""A labelled defect corpus (``docs/15 §2.1``).

A benchmark is only as honest as the thing it plants. This builds a table, puts
a known number of known defects into it at known places, and hands back both
the damaged table and the label set — so a detector's score is computed against
what was actually done rather than against what the generator meant to do.

Two decisions shape everything here.

**The defect is what changed, not what was written.** A "sign flip" that lands
on a row whose value is already negative changes nothing, and crediting a
detector for finding it would be crediting it for finding a defect that is not
there. Every injector reports the rows it actually altered, and rows where the
intended change was a no-op are dropped from the labels. This is the difference
between a corpus that measures detection and one that flatters it.

**The seed is part of the corpus.** Same seed, same corpus, byte for byte —
otherwise a result cannot be reproduced and a regression cannot be
distinguished from a reroll. :func:`build` takes the seed as an argument and
has no default, because a default seed is a seed nobody records.

Scale is deliberately modest. This runs in a test suite. ``docs/15`` describes
S/M/L at 10⁶ to 10¹⁰ rows against real openly-licensed datasets, and none of
that is here: what is here is the taxonomy, the injectors and the labelling
discipline, which is the part that has to be right before scale is worth
buying.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
import random
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from typing import Any, Final

from prama.bench.scoring import Defect

__all__ = [
    "CLASSES",
    "Corpus",
    "DefectClass",
    "Difficulty",
    "Family",
    "Row",
    "Scenario",
    "build",
    "classes_of",
]

Row = dict[str, Any]


class Family(enum.Enum):
    """The six families of ``docs/15 §2.1``."""

    STRUCTURAL = "structural"
    CONTENT = "content"
    STATISTICAL = "statistical"
    RELATIONAL = "relational"
    TEMPORAL = "temporal"
    SEMANTIC = "semantic"


class Difficulty(enum.Enum):
    """How much machinery a defect needs before it can be seen.

    The tiers are the argument. A tool that finds every *obvious* defect and no
    *subtle* one has a different problem from a tool that finds a few of each,
    and an aggregate score reports them identically.
    """

    #: Any tool finds it.
    OBVIOUS = "obvious"
    #: Needs a rule or a monitor.
    ORDINARY = "ordinary"
    #: Needs seasonality, segmentation, or a declared relationship.
    SUBTLE = "subtle"
    #: Co-occurs with a legitimate change. Tests false-positive discipline
    #: rather than sensitivity: the tool that alerts on both is worse than the
    #: tool that alerts on neither.
    ADVERSARIAL = "adversarial"


@dataclasses.dataclass(frozen=True, slots=True)
class DefectClass:
    """One class of defect, and how to plant it."""

    name: str
    family: Family
    difficulty: Difficulty
    column: str
    #: Alters one row in place. Returns whether it actually changed anything —
    #: a no-op is not a defect, and labelling it as one credits a detector for
    #: finding something that is not there.
    inject: Callable[[Row, random.Random], bool] = dataclasses.field(repr=False)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "family": self.family.value,
            "difficulty": self.difficulty.value,
            "column": self.column,
            "description": self.description,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Scenario:
    """One defect class, in its own window.

    Each class gets a window to itself, and this is not cosmetic. ``docs/15
    §3.1`` scores a detection on dataset, column *and* window: six classes that
    all damage ``amount`` in one window share a locus, so a single alert on
    ``amount`` would be credited with finding all six. Separating them is what
    makes recall mean what it says.
    """

    defect_class: str
    window: str
    clean: tuple[Row, ...]
    rows: tuple[Row, ...]
    #: The rows the injector actually altered. A no-op is not a defect.
    damaged_rows: tuple[int, ...]
    defect: Defect | None

    @property
    def planted_anything(self) -> bool:
        return self.defect is not None


@dataclasses.dataclass(frozen=True, slots=True)
class Corpus:
    """A set of scenarios and the truth about what was done to each."""

    dataset: str
    scenarios: tuple[Scenario, ...]
    seed: int
    #: Classes asked for that planted nothing, and why. Never silent: a class
    #: that quietly plants nothing turns into recall a detector is credited
    #: with never having to earn.
    barren: tuple[tuple[str, str], ...] = ()

    @property
    def defects(self) -> tuple[Defect, ...]:
        return tuple(s.defect for s in self.scenarios if s.defect is not None)

    @property
    def planted(self) -> int:
        return len(self.defects)

    @property
    def rows(self) -> tuple[Row, ...]:
        """Every damaged row across every scenario."""
        return tuple(row for scenario in self.scenarios for row in scenario.rows)

    @property
    def clean(self) -> tuple[Row, ...]:
        return tuple(row for scenario in self.scenarios for row in scenario.clean)

    def of_family(self, family: Family) -> tuple[Defect, ...]:
        return tuple(d for d in self.defects if d.family == family.value)

    def of_difficulty(self, difficulty: Difficulty) -> tuple[Defect, ...]:
        return tuple(d for d in self.defects if d.difficulty == difficulty.value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "seed": self.seed,
            "scenarios": len(self.scenarios),
            "rows_per_scenario": len(self.scenarios[0].rows) if self.scenarios else 0,
            "planted": self.planted,
            "by_family": {
                family.value: len(self.of_family(family))
                for family in Family
                if self.of_family(family)
            },
            "by_difficulty": {
                tier.value: len(self.of_difficulty(tier))
                for tier in Difficulty
                if self.of_difficulty(tier)
            },
            "barren": [{"class": name, "reason": why} for name, why in self.barren],
        }


# -- the injectors ---------------------------------------------------------
#
# Each returns True only if the row genuinely changed. Several of them can
# legitimately do nothing on a given row, and that is the case worth getting
# right: `_sign_flip` on a negative amount, `_truncate` on a short string,
# `_retype` on a value that already reads as text.


def _null_out(row: Row, column: str) -> bool:
    if row[column] is None:
        return False
    row[column] = None
    return True


def _drop_column(row: Row, column: str) -> bool:
    return row.pop(column, _MISSING) is not _MISSING


_MISSING: Final = object()


def _rename_column(row: Row, column: str, to: str) -> bool:
    if column not in row:
        return False
    row[to] = row.pop(column)
    return True


def _retype(row: Row, column: str) -> bool:
    """A number arriving as text. Reads correctly and sorts wrongly."""
    if isinstance(row[column], str) or row[column] is None:
        return False
    row[column] = str(row[column])
    return True


def _duplicate_key(row: Row, _: random.Random) -> bool:
    """Break the grain by pointing this row's key at its neighbour's."""
    row["account_id"] = "ACC-000001"
    return True


def _out_of_domain(row: Row, _: random.Random) -> bool:
    if row["currency"] == "ZZZ":
        return False
    row["currency"] = "ZZZ"
    return True


def _format_violation(row: Row, _: random.Random) -> bool:
    if not isinstance(row["iban"], str) or row["iban"].startswith("!!"):
        return False
    row["iban"] = "!!" + row["iban"][2:]
    return True


def _check_digit(row: Row, _: random.Random) -> bool:
    """Structurally perfect, arithmetically wrong. Only the algorithm sees it."""
    iban = row["iban"]
    if not isinstance(iban, str) or len(iban) < 4:
        return False
    wrong = "01" if iban[2:4] != "01" else "02"
    row["iban"] = iban[:2] + wrong + iban[4:]
    return True


def _scale_error(row: Row, _: random.Random) -> bool:
    """The hundred-times error: minor units read as major."""
    if row["amount"] is None:
        return False
    row["amount"] = round(row["amount"] * 100, 2)
    return True


def _sign_flip(row: Row, _: random.Random) -> bool:
    amount = row["amount"]
    if amount is None or amount <= 0:
        # Flipping an already-negative amount changes its meaning too, but the
        # corpus plants a *credit read as a debit*, and this row is already a
        # debit. Labelling it would credit a detector for nothing.
        return False
    row["amount"] = -amount
    return True


def _truncate(row: Row, _: random.Random) -> bool:
    name = row["party_name"]
    if not isinstance(name, str) or len(name) <= 4:
        return False
    row["party_name"] = name[:4]
    return True


def _encoding_corruption(row: Row, _: random.Random) -> bool:
    name = row["party_name"]
    if not isinstance(name, str) or "Ã" in name:
        return False
    row["party_name"] = name.replace("e", "Ã©", 1)
    return True


def _distribution_shift(row: Row, rng: random.Random) -> bool:
    if row["amount"] is None:
        return False
    row["amount"] = round(row["amount"] * rng.uniform(3.0, 4.0), 2)
    return True


def _new_category(row: Row, _: random.Random) -> bool:
    if row["product"] == "STRUCTURED":
        return False
    row["product"] = "STRUCTURED"
    return True


def _category_disappears(row: Row, _: random.Random) -> bool:
    """A category that stops arriving. Invisible row by row."""
    if row["product"] != "SAVINGS":
        return False
    row["product"] = "CURRENT"
    return True


def _heaping(row: Row, _: random.Random) -> bool:
    """Values piling on round numbers — the signature of hand entry."""
    if row["amount"] is None or row["amount"] == 1000.0:
        return False
    row["amount"] = 1000.0
    return True


def _outlier(row: Row, _: random.Random) -> bool:
    if row["amount"] is None:
        return False
    row["amount"] = 9_999_999.99
    return True


def _orphan_key(row: Row, _: random.Random) -> bool:
    if row["counterparty_id"] == "CPTY-MISSING":
        return False
    row["counterparty_id"] = "CPTY-MISSING"
    return True


def _broken_dependency(row: Row, _: random.Random) -> bool:
    """The country no longer follows from the IBAN. Both fields stay valid."""
    iban = row["iban"]
    if not isinstance(iban, str):
        return False
    row["country"] = "JP" if iban[:2] != "JP" else "GB"
    return True


def _aggregate_mismatch(row: Row, _: random.Random) -> bool:
    if row["amount"] is None:
        return False
    row["control_total"] = round(row["amount"] + 0.01, 2)
    return True


def _duplicate_entity(row: Row, _: random.Random) -> bool:
    """The same party under a second spelling — one entity, two rows."""
    name = row["party_name"]
    if not isinstance(name, str) or name.endswith(" LTD"):
        return False
    row["party_name"] = name + " LTD"
    return True


def _late_arrival(row: Row, _: random.Random) -> bool:
    """The right data in the wrong period.

    Dated relative to the row's own window rather than to a fixed date: a fixed
    date is a no-op for whichever scenario happens to fall on it, and a defect
    class that silently plants nothing in one run and something in the next is
    not a benchmark.
    """
    if row["value_date"] != row["window"]:
        return False
    row["value_date"] = "2025-11-15"
    return True


def _stale_value(row: Row, _: random.Random) -> bool:
    """A frozen feed. Every value plausible, none of them today's."""
    if row["rate"] == 1.0:
        return False
    row["rate"] = 1.0
    return True


def _out_of_order(row: Row, _: random.Random) -> bool:
    """A sequence that runs backwards: booked after it settled."""
    if row["booking_date"] > row["value_date"]:
        return False
    row["booking_date"] = "2026-12-01"
    return True


def _plausible_but_wrong(row: Row, rng: random.Random) -> bool:
    """The discriminating family.

    Passes every format check, every range check and every code list. Only a
    declared relationship — this amount against that control total, this
    currency against that IBAN's country — can see it.
    """
    if row["amount"] is None:
        return False
    row["amount"] = round(row["amount"] + rng.uniform(0.02, 0.09), 2)
    return True


def _mislabelled_category(row: Row, _: random.Random) -> bool:
    if row["product"] != "CURRENT":
        return False
    row["product"] = "SAVINGS"
    return True


def _silent_rule_violation(row: Row, _: random.Random) -> bool:
    """A settlement date before its trade date. Both dates are real dates."""
    if row["value_date"] < row["booking_date"]:
        return False
    row["value_date"], row["booking_date"] = row["booking_date"], row["value_date"]
    return True


def _legitimate_change_with_defect(row: Row, _: random.Random) -> bool:
    """The adversarial tier: a real corporate action *and* a real defect.

    The tool that alerts on the whole window is not detecting anything; it is
    reacting to the change. The tool that suppresses the window because a
    change was announced misses the defect inside it.
    """
    if row["amount"] is None:
        return False
    row["product"] = "MERGED-ENTITY"
    row["amount"] = round(row["amount"] * 2, 2)
    return True


CLASSES: Final[tuple[DefectClass, ...]] = (
    # -- structural --------------------------------------------------------
    DefectClass(
        "column-nulled",
        Family.STRUCTURAL,
        Difficulty.OBVIOUS,
        "amount",
        lambda row, _: _null_out(row, "amount"),
        "a nullability change arriving as nulls",
    ),
    DefectClass(
        "column-removed",
        Family.STRUCTURAL,
        Difficulty.OBVIOUS,
        "product",
        lambda row, _: _drop_column(row, "product"),
        "the column stops arriving",
    ),
    DefectClass(
        "column-renamed",
        Family.STRUCTURAL,
        Difficulty.OBVIOUS,
        "party_name",
        lambda row, _: _rename_column(row, "party_name", "partyName"),
        "same data, a name nothing downstream binds to",
    ),
    DefectClass(
        "column-retyped",
        Family.STRUCTURAL,
        Difficulty.ORDINARY,
        "amount",
        lambda row, _: _retype(row, "amount"),
        "a number arriving as text; reads right, sorts wrong",
    ),
    DefectClass(
        "grain-violation",
        Family.STRUCTURAL,
        Difficulty.ORDINARY,
        "account_id",
        _duplicate_key,
        "two rows at a grain declared unique",
    ),
    # -- content -----------------------------------------------------------
    DefectClass(
        "out-of-domain",
        Family.CONTENT,
        Difficulty.OBVIOUS,
        "currency",
        _out_of_domain,
        "a value outside the code list",
    ),
    DefectClass(
        "format-violation",
        Family.CONTENT,
        Difficulty.OBVIOUS,
        "iban",
        _format_violation,
        "fails the pattern outright",
    ),
    DefectClass(
        "check-digit-failure",
        Family.CONTENT,
        Difficulty.ORDINARY,
        "iban",
        _check_digit,
        "structurally perfect, arithmetically wrong",
    ),
    DefectClass(
        "scale-error",
        Family.CONTENT,
        Difficulty.SUBTLE,
        "amount",
        _scale_error,
        "minor units read as major: the hundred-times error",
    ),
    DefectClass(
        "sign-flip",
        Family.CONTENT,
        Difficulty.SUBTLE,
        "amount",
        _sign_flip,
        "a credit read as a debit",
    ),
    DefectClass(
        "truncation",
        Family.CONTENT,
        Difficulty.ORDINARY,
        "party_name",
        _truncate,
        "a field cut to a shorter target column",
    ),
    DefectClass(
        "encoding-corruption",
        Family.CONTENT,
        Difficulty.OBVIOUS,
        "party_name",
        _encoding_corruption,
        "UTF-8 read as Latin-1",
    ),
    # -- statistical -------------------------------------------------------
    DefectClass(
        "distribution-shift",
        Family.STATISTICAL,
        Difficulty.ORDINARY,
        "amount",
        _distribution_shift,
        "the same column, a different distribution",
    ),
    DefectClass(
        "new-category",
        Family.STATISTICAL,
        Difficulty.ORDINARY,
        "product",
        _new_category,
        "a value nobody declared",
    ),
    DefectClass(
        "category-disappearance",
        Family.STATISTICAL,
        Difficulty.SUBTLE,
        "product",
        _category_disappears,
        "a category stops arriving; invisible row by row",
    ),
    DefectClass(
        "heaping",
        Family.STATISTICAL,
        Difficulty.SUBTLE,
        "amount",
        _heaping,
        "values piling on round numbers",
    ),
    DefectClass(
        "outlier",
        Family.STATISTICAL,
        Difficulty.OBVIOUS,
        "amount",
        _outlier,
        "a value far outside the range",
    ),
    # -- relational --------------------------------------------------------
    DefectClass(
        "orphan-foreign-key",
        Family.RELATIONAL,
        Difficulty.ORDINARY,
        "counterparty_id",
        _orphan_key,
        "points at a row that is not there",
    ),
    DefectClass(
        "broken-dependency",
        Family.RELATIONAL,
        Difficulty.SUBTLE,
        "country",
        _broken_dependency,
        "country no longer follows from IBAN; both stay valid",
    ),
    DefectClass(
        "aggregate-mismatch",
        Family.RELATIONAL,
        Difficulty.SUBTLE,
        "control_total",
        _aggregate_mismatch,
        "the stated total and the sum disagree by a penny",
    ),
    DefectClass(
        "duplicate-entity",
        Family.RELATIONAL,
        Difficulty.SUBTLE,
        "party_name",
        _duplicate_entity,
        "one party, two spellings, two rows",
    ),
    # -- temporal ----------------------------------------------------------
    DefectClass(
        "late-arrival",
        Family.TEMPORAL,
        Difficulty.ORDINARY,
        "value_date",
        _late_arrival,
        "the right data in the wrong period",
    ),
    DefectClass(
        "stale-values",
        Family.TEMPORAL,
        Difficulty.SUBTLE,
        "rate",
        _stale_value,
        "a frozen feed; every value plausible, none current",
    ),
    DefectClass(
        "out-of-order",
        Family.TEMPORAL,
        Difficulty.ORDINARY,
        "booking_date",
        _out_of_order,
        "a sequence that runs backwards",
    ),
    # -- semantic ----------------------------------------------------------
    DefectClass(
        "plausible-but-wrong",
        Family.SEMANTIC,
        Difficulty.SUBTLE,
        "amount",
        _plausible_but_wrong,
        "passes every format and range check",
    ),
    DefectClass(
        "mislabelled-category",
        Family.SEMANTIC,
        Difficulty.SUBTLE,
        "product",
        _mislabelled_category,
        "a real category, on the wrong row",
    ),
    DefectClass(
        "silent-rule-violation",
        Family.SEMANTIC,
        Difficulty.SUBTLE,
        "value_date",
        _silent_rule_violation,
        "settlement before trade; both are real dates",
    ),
    DefectClass(
        "legitimate-change-with-defect",
        Family.SEMANTIC,
        Difficulty.ADVERSARIAL,
        "amount",
        _legitimate_change_with_defect,
        "a real corporate action and a real defect in one window",
    ),
)


def classes_of(family: Family | None = None) -> tuple[DefectClass, ...]:
    if family is None:
        return CLASSES
    return tuple(c for c in CLASSES if c.family is family)


def _base_row(index: int, rng: random.Random, window: str) -> Row:
    return {
        "window": window,
        "account_id": f"ACC-{index:06d}",
        "counterparty_id": f"CPTY-{rng.randrange(1, 50):04d}",
        "party_name": rng.choice(("Acme Holdings", "Belmont Trading", "Cedar Finance")),
        "iban": f"GB29NWBK6016{index:010d}",
        "country": "GB",
        "currency": rng.choice(("GBP", "EUR", "USD")),
        "product": rng.choice(("CURRENT", "SAVINGS", "LOAN")),
        "amount": round(rng.uniform(10.0, 5_000.0), 2),
        "control_total": 0.0,
        "rate": round(rng.uniform(0.9, 1.4), 4),
        "value_date": window,
        "booking_date": "2025-12-31",
    }


def build(
    *,
    seed: int,
    rows: int = 200,
    rate: float = 0.05,
    dataset: str = "payments",
    classes: Sequence[DefectClass] | None = None,
) -> Corpus:
    """Build a corpus. The seed has no default, because a default is not recorded.

    ``rate`` is the share of rows the class *attempts* to damage, not a hit
    rate: an injector that finds nothing to change on a row plants nothing
    there, and the labels follow what happened rather than what was intended.

    One window per class, dated sequentially from 2026-01-01.
    """
    # `ValueError`, which is what Python means by "right type, wrong value" —
    # and what a benchmark script driving this module would write `except` for.
    #
    # This briefly raised the Prama taxonomy instead, so that `prama bench run`
    # would print a typed refusal rather than a stack trace (QA `Q-68`). That
    # fixed the terminal and broke the library: `ValidationError` is not a
    # `ValueError`, so every `except ValueError` around this call stopped
    # catching, which `BCH-015`/`BCH-016` caught and `Q-77` records. The CLI now
    # translates at its own boundary instead, so both contracts hold.
    if not 0 < rate <= 1:
        raise ValueError(f"rate must be a share of rows in (0, 1], got {rate}")
    if rows < 1:
        raise ValueError(f"a corpus needs rows, got {rows}")

    chosen = tuple(classes) if classes is not None else CLASSES
    rng = random.Random(seed)
    per_class = max(1, int(rows * rate))

    scenarios: list[Scenario] = []
    barren: list[tuple[str, str]] = []

    for ordinal, entry in enumerate(chosen):
        window = _window(ordinal)
        clean = tuple(_base_row(i, rng, window) for i in range(rows))
        for row in clean:
            row["control_total"] = row["amount"]
        damaged = [dict(row) for row in clean]

        touched: list[int] = []
        for index in rng.sample(range(rows), k=min(per_class, rows)):
            if entry.inject(damaged[index], rng):
                touched.append(index)

        defect: Defect | None = None
        if touched:
            defect = Defect(
                dataset=dataset,
                column=entry.column,
                window=window,
                family=entry.family.value,
                difficulty=entry.difficulty.value,
                note=f"{entry.name}, {len(touched)} row(s)",
            )
        else:
            barren.append(
                (
                    entry.name,
                    "no sampled row could carry it; nothing was planted and nothing is labelled",
                )
            )

        scenarios.append(
            Scenario(
                defect_class=entry.name,
                window=window,
                clean=clean,
                rows=tuple(damaged),
                damaged_rows=tuple(sorted(touched)),
                defect=defect,
            )
        )

    return Corpus(
        dataset=dataset,
        scenarios=tuple(scenarios),
        seed=seed,
        barren=tuple(barren),
    )


def _window(ordinal: int) -> str:
    """A distinct window per class, dated sequentially."""
    day = date(2026, 1, 1) + timedelta(days=ordinal)
    return day.isoformat()
