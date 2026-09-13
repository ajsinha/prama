"""ODCS quality blocks, and which of them can become a control.

A contract's ``quality`` blocks are the closest thing ODCS has to Prama's
controls, and importing them is where a contract stops being a document and
starts being enforceable. The work is almost entirely in refusing the ones that
cannot be.

ODCS v3 has four kinds of quality block and they are not equivalent:

``library``
    A named rule — ``nullCount``, ``duplicateCount``, ``validValues`` — with a
    threshold. These map to PQL, and this module maps them.

``text``
    Prose. "Orders should look sensible." There is no executable content, and
    importing it as a control would produce a control that checks nothing while
    appearing on a coverage report as though it did. **Refused, and reported.**

``sql``
    A SQL query the producer wrote. It is engine-specific, it bypasses the IR,
    the reference interpreter cannot check it, and its meaning is not part of a
    plan id — so a control built from it cannot be replayed or compared across
    engines, which is most of what a control is for here. **Refused, with the
    query preserved** so somebody can rewrite it as PQL rather than hunt for it.

``custom``
    An implementation for a named engine. Where that engine is one Prama already
    imports — SodaCL, Great Expectations — the block is *routed* to that
    importer rather than reimplemented here. Where it is not, it is refused by
    name.

**The threshold is the rule, not decoration.** ``duplicateCount`` with
``mustBeLessThan: 10`` is not "no duplicates": it is a control that tolerates
nine. Importing it as a strict uniqueness check makes a contract the producer
satisfies fail against a consumer who imported it, which is worse than not
importing at all. PQL expresses this as ``AT MOST 9 ROWS``, and a rule whose
threshold cannot be expressed is refused rather than tightened.

**Nothing is invented.** A block with no threshold where the rule needs one, a
comparator ODCS defines and PQL cannot express, a rule name not in the mapping —
each is refused by name, so a reader sees what a contract promised and Prama did
not take on.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any, Final

__all__ = [
    "LIBRARY_RULES",
    "QualityImport",
    "Rule",
    "controls_from",
]


@dataclasses.dataclass(frozen=True, slots=True)
class Rule:
    """One library rule, and how it becomes PQL."""

    #: The ODCS rule name, as written in a contract.
    name: str
    #: What the control asserts, as a PQL predicate with ``{column}``.
    predicate: str
    dimension: str
    #: Whether the rule counts *violations* (so a threshold is a tolerance) or
    #: describes the population (so a threshold is the assertion itself).
    counts_violations: bool = True
    #: Rules where a threshold makes no sense, so one being present is a
    #: contradiction worth reporting rather than ignoring.
    forbids_threshold: bool = False
    note: str = ""


#: The ODCS library rules that map. Deliberately short: a rule here is one
#: somebody checked, and a long list assembled from a specification would be a
#: list of mappings nobody has read.
LIBRARY_RULES: Final[tuple[Rule, ...]] = (
    Rule("nullCount", "{column} IS NOT NULL", "completeness"),
    Rule("nullPercent", "{column} IS NOT NULL", "completeness"),
    Rule("missingCount", "{column} IS NOT NULL", "completeness"),
    Rule("duplicateCount", "{column} IS UNIQUE", "uniqueness"),
    Rule("duplicatePercent", "{column} IS UNIQUE", "uniqueness"),
    Rule("uniqueCount", "{column} IS UNIQUE", "uniqueness"),
    Rule(
        "validValues",
        "{column} IN ({values})",
        "validity",
        note="needs a validValues list on the block",
    ),
    Rule("invalidCount", "{column} IN ({values})", "validity"),
    Rule(
        "rowCount",
        "HAS ROW COUNT BETWEEN {minimum} AND {maximum}",
        "completeness",
        counts_violations=False,
        forbids_threshold=True,
        note="a population claim, not a violation count",
    ),
    Rule(
        "freshness",
        "IS FRESH WITHIN {window}",
        "timeliness",
        counts_violations=False,
        forbids_threshold=True,
    ),
    Rule(
        "pattern",
        "{column} MATCHES /{pattern}/",
        "validity",
        note="needs a pattern on the block",
    ),
)

_BY_NAME: Final = {rule.name.lower(): rule for rule in LIBRARY_RULES}

#: Engines whose quality blocks Prama can route to an existing importer rather
#: than reimplement. Derived from what `prama control import` already accepts.
ROUTABLE_ENGINES: Final[dict[str, str]] = {
    "soda": "SodaCL — import it with `prama control import --from soda`",
    "sodacl": "SodaCL — import it with `prama control import --from soda`",
    "greatexpectations": (
        "Great Expectations — import it with `prama control import --from great_expectations`"
    ),
    "great_expectations": (
        "Great Expectations — import it with `prama control import --from great_expectations`"
    ),
    "dbt": "dbt tests — import it with `prama control import --from dbt`",
}


@dataclasses.dataclass(frozen=True, slots=True)
class QualityImport:
    """Controls that came across, and every block that did not."""

    controls: tuple[str, ...] = ()
    #: ``(what it was, why it did not import)``. Never a bare count: a contract
    #: promising eleven checks and yielding four is a conversation with the
    #: producer, and it needs the seven named.
    refused: tuple[tuple[str, str], ...] = ()
    #: Blocks another importer should take. Named so the work is routed rather
    #: than lost.
    routed: tuple[tuple[str, str], ...] = ()

    @property
    def offered(self) -> int:
        return len(self.controls) + len(self.refused) + len(self.routed)

    @property
    def is_complete(self) -> bool:
        return not self.refused and not self.routed

    def describe(self) -> str:
        if not self.offered:
            return "the contract states no quality rules"
        parts = [f"{len(self.controls)} of {self.offered} quality rule(s) became controls"]
        if self.routed:
            parts.append(
                f"{len(self.routed)} belong to another importer: "
                + "; ".join(f"{what} — {why}" for what, why in self.routed)
            )
        if self.refused:
            parts.append(
                f"{len(self.refused)} did not import: "
                + "; ".join(f"{what} — {why}" for what, why in self.refused)
            )
        return ". ".join(parts) + "."

    def to_dict(self) -> dict[str, Any]:
        return {
            "controls": list(self.controls),
            "offered": self.offered,
            "refused": [{"rule": what, "why": why} for what, why in self.refused],
            "routed": [{"rule": what, "to": why} for what, why in self.routed],
            "complete": self.is_complete,
            "message": self.describe(),
        }


def controls_from(contract: Mapping[str, Any], *, dataset: str = "") -> QualityImport:
    """Every quality block in a contract, as PQL or as a stated refusal."""
    schemas = contract.get("schema") or []
    if not schemas:
        return QualityImport()
    schema = schemas[0]
    name = dataset or str(schema.get("name") or contract.get("dataProduct") or "")

    controls: list[str] = []
    refused: list[tuple[str, str]] = []
    routed: list[tuple[str, str]] = []

    # Dataset-level blocks first, then per column. Order matters only for
    # readability, and a reader looks for the table's own rules first.
    _absorb(schema.get("quality"), name, "", controls, refused, routed)
    for column in schema.get("properties") or []:
        _absorb(
            column.get("quality"),
            name,
            str(column.get("name", "")),
            controls,
            refused,
            routed,
        )

    return QualityImport(controls=tuple(controls), refused=tuple(refused), routed=tuple(routed))


def _absorb(
    blocks: Any,
    dataset: str,
    column: str,
    controls: list[str],
    refused: list[tuple[str, str]],
    routed: list[tuple[str, str]],
) -> None:
    if not isinstance(blocks, Sequence) or isinstance(blocks, str):
        return
    for block in blocks:
        if not isinstance(block, Mapping):
            continue
        where = f"{dataset}.{column}" if column else dataset
        kind = str(block.get("type", "library")).lower()

        if kind == "text":
            refused.append(
                (
                    f"{where}: a text rule",
                    "it is prose with no executable content, and a control built "
                    "from it would check nothing while appearing on a coverage "
                    "report as though it did",
                )
            )
            continue

        if kind == "sql":
            query = str(block.get("query", "")).strip()
            refused.append(
                (
                    f"{where}: a SQL rule",
                    "raw SQL bypasses the IR, so the reference interpreter cannot "
                    "check it and it cannot be replayed or compared across "
                    f"engines. Rewrite it as PQL: {_shorten(query)}",
                )
            )
            continue

        if kind == "custom":
            engine = str(block.get("engine", "")).lower().replace("-", "_")
            destination = ROUTABLE_ENGINES.get(engine)
            if destination:
                routed.append((f"{where}: a custom rule for {engine}", destination))
            else:
                refused.append(
                    (
                        f"{where}: a custom rule for {engine or 'an unnamed engine'}",
                        "Prama has no importer for it, and running somebody else's "
                        "implementation would put a control in the estate that this "
                        "product cannot explain or replay",
                    )
                )
            continue

        _library(block, dataset, column, where, controls, refused)


def _library(
    block: Mapping[str, Any],
    dataset: str,
    column: str,
    where: str,
    controls: list[str],
    refused: list[tuple[str, str]],
) -> None:
    name = str(block.get("rule", "")).strip()
    rule = _BY_NAME.get(name.lower())
    if rule is None:
        refused.append(
            (
                f"{where}: {name or 'an unnamed rule'}",
                "not a library rule Prama maps. "
                f"Mapped: {', '.join(sorted(r.name for r in LIBRARY_RULES))}",
            )
        )
        return

    if "{column}" in rule.predicate and not column:
        refused.append((f"{where}: {name}", "this rule is about a column and the block names none"))
        return

    predicate, problem = _render(rule, block, column)
    if problem:
        refused.append((f"{where}: {name}", problem))
        return

    threshold, problem = _threshold(rule, block)
    if problem:
        refused.append((f"{where}: {name}", problem))
        return

    controls.append(
        f"CHECK {dataset}{'.' if column and '{column}' in rule.predicate else ' '}"
        f"{predicate}{threshold} "
        f"SEVERITY major DIMENSION {rule.dimension} "
        f"BECAUSE 'the data contract states {name}'"
    )


def _render(rule: Rule, block: Mapping[str, Any], column: str) -> tuple[str, str]:
    predicate = rule.predicate.replace("{column}", column)

    if "{values}" in predicate:
        values = block.get("validValues") or block.get("values")
        if not isinstance(values, Sequence) or isinstance(values, str) or not values:
            return "", "the rule needs a validValues list and the block carries none"
        rendered = ", ".join(_literal(v) for v in values)
        predicate = predicate.replace("{values}", rendered)

    if "{pattern}" in predicate:
        pattern = block.get("pattern") or block.get("mustMatch")
        if not pattern:
            return "", "the rule needs a pattern and the block carries none"
        if "/" in str(pattern):
            # PQL delimits a pattern with slashes, and escaping is a decision
            # somebody should make deliberately rather than have guessed here.
            return "", f"the pattern contains a '/', which PQL uses as its delimiter: {pattern}"
        predicate = predicate.replace("{pattern}", str(pattern))

    if "{minimum}" in predicate:
        # Strict bounds are converted, not borrowed. `HAS ROW COUNT BETWEEN` is
        # inclusive on both ends, and `mustBeLessThan: 1200000` means a maximum
        # of 1,199,999 — so copying the number straight in accepted a row count
        # the contract forbids (QA finding CTR-029). `_threshold` in this same
        # module already makes exactly this adjustment; the row-count branch
        # did not, which is how one file came to be right and wrong about the
        # same word.
        low, low_error = _inclusive(block, "mustBeGreaterOrEqualTo", "mustBeGreaterThan", +1)
        if low_error:
            return "", low_error
        high, high_error = _inclusive(block, "mustBeLessOrEqualTo", "mustBeLessThan", -1)
        if high_error:
            return "", high_error
        between = block.get("mustBeBetween")
        if isinstance(between, Sequence) and not isinstance(between, str) and len(between) == 2:
            low, high = between[0], between[1]
        if low is None or high is None:
            return "", "a row-count rule needs both a minimum and a maximum"
        predicate = predicate.replace("{minimum}", str(low)).replace("{maximum}", str(high))

    if "{window}" in predicate:
        window = block.get("mustBeLessThan") or block.get("window")
        if window is None:
            return "", "a freshness rule needs a window"
        # The unit is read, not assumed. `4` with a unit of hours became
        # `WITHIN 4 day` — a window twenty-four times longer than the contract
        # states, in the direction that lets stale data pass (QA finding
        # CTR-031). An unrecognised unit is refused rather than guessed,
        # because a freshness control that is wrong by a factor is worse than
        # one that was never generated.
        unit = str(block.get("unit", "day")).strip().lower().rstrip("s") or "day"
        if unit not in _FRESHNESS_UNITS:
            return "", (
                f"the freshness unit {block.get('unit')!r} is not one PQL expresses. "
                f"Use one of: {', '.join(sorted(_FRESHNESS_UNITS))}"
            )
        predicate = predicate.replace("{window}", f"{window} {unit}")

    return predicate, ""


#: Units `IS FRESH WITHIN` accepts, singular. Kept beside the mapping that
#: needs them so a unit PQL stops supporting shows up here as a refusal rather
#: than as a control that does not parse.
_FRESHNESS_UNITS: frozenset[str] = frozenset({"minute", "hour", "day"})


def _inclusive(
    block: Mapping[str, Any], inclusive_key: str, strict_key: str, adjust: int
) -> tuple[Any, str]:
    """A bound as an inclusive integer, whichever way the contract stated it.

    ODCS has both spellings and they differ by one. Reading the strict one as
    inclusive widens or narrows the control by a row — always in the direction
    that accepts data the contract rejects, because the strict bound is the
    tighter of the two.
    """
    if inclusive_key in block:
        return block[inclusive_key], ""
    if strict_key not in block:
        return None, ""
    value = block[strict_key]
    if not isinstance(value, int) or isinstance(value, bool):
        return None, (
            f"{strict_key} is {value!r}; a strict row-count bound has to be a whole "
            "number, because the inclusive equivalent is one away from it"
        )
    return value + adjust, ""


def _threshold(rule: Rule, block: Mapping[str, Any]) -> tuple[str, str]:
    """The tolerance clause, or a refusal.

    ``mustBeLessThan: 10`` on a violation count means *nine are acceptable*, and
    PQL's ``AT MOST`` is inclusive — so the strictly-less-than form is one
    lower. Getting that wrong by one makes a contract the producer satisfies
    fail for the consumer who imported it.
    """
    if rule.forbids_threshold:
        return "", ""
    if not rule.counts_violations:
        return "", ""

    percent = str(rule.name).lower().endswith("percent")

    if "mustBe" in block:
        value = block["mustBe"]
        if value not in (0, 0.0):
            return "", (
                f"mustBe: {value} is an exact count, and a control asserts a bound "
                "rather than an equality — a population that happens to have "
                "fewer violations would fail"
            )
        return (" AT MOST 0 ROWS" if not percent else " BELOW 0%"), ""

    for key, adjust in (("mustBeLessOrEqualTo", 0), ("mustBeLessThan", -1)):
        if key in block:
            value = block[key]
            if not isinstance(value, int | float):
                return "", f"{key} is {value!r}, which is not a number"
            if percent:
                bound = float(value) + (0 if adjust == 0 else -0.0)
                if adjust == -1:
                    # A strict bound on a rate has no representable predecessor,
                    # so it is reported rather than silently made inclusive.
                    return "", (
                        f"{key}: {value} is a strict bound on a percentage, and PQL's "
                        "BELOW is inclusive — importing it would accept a value the "
                        "contract forbids"
                    )
                return f" BELOW {bound:g}%", ""
            bound = int(value) + adjust
            if bound < 0:
                return "", f"{key}: {value} leaves no acceptable violations and no room below"
            return f" AT MOST {bound} ROWS", ""

    for key in ("mustBeGreaterThan", "mustBeGreaterOrEqualTo", "mustNotBe", "mustBeBetween"):
        if key in block:
            return "", (
                f"{key} on a violation count asks for *at least* that many failures, "
                "which is not something a control can assert"
            )

    # No threshold at all: the strictest reading, and the one a contract without
    # a number means.
    return (" AT MOST 0 ROWS" if not percent else " BELOW 0%"), ""


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _shorten(text: str, width: int = 60) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[: width - 1] + "…"
