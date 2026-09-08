"""Importing SodaCL checks.

SodaCL is a small language of its own inside YAML — ``missing_count(x) = 0``,
``duplicate_count(a, b) = 0``, ``invalid_percent(ccy) < 2 %`` — rather than a
structured document. So this reads the forms that are common in practice and
refuses the rest by name.

That refusal is deliberate and is not laziness. A partial parser that fell back
to "close enough" on an unfamiliar check would import something plausible, and
a plausible control is worse than a missing one: the missing one is on the
report somebody reads before signing off the migration, and the plausible one
is not.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re
from typing import Any

from prama.importers.spi import Collector, Importer, ImportResult, because, quote

#: ``checks for positions_eod:`` — the block header naming a dataset.
_HEADER = re.compile(r"^checks\s+for\s+(?P<dataset>[^\s:]+)", re.IGNORECASE)

#: ``metric(args) <op> <value>``, the shape of most SodaCL checks.
_METRIC = re.compile(
    r"^(?P<metric>[a-z_]+)"
    r"(?:\((?P<args>[^)]*)\))?"
    r"\s*(?P<operator><=|>=|<>|!=|=|<|>)\s*"
    r"(?P<value>[^%\s]+)\s*(?P<percent>%)?$",
    re.IGNORECASE,
)

#: ``row_count between 100 and 200``.
_BETWEEN = re.compile(
    r"^(?P<metric>[a-z_]+)(?:\((?P<args>[^)]*)\))?\s+between\s+"
    r"(?P<low>\S+)\s+and\s+(?P<high>\S+)$",
    re.IGNORECASE,
)

#: ``values in (account_id) must exist in accounts (account_id)``.
_REFERENCE = re.compile(
    r"^values\s+in\s+\((?P<column>[^)]+)\)\s+must\s+exist\s+in\s+"
    r"(?P<target>\S+)\s*\((?P<target_column>[^)]+)\)$",
    re.IGNORECASE,
)

#: Metrics whose meaning is a count of violating rows, so ``= 0`` is the
#: ordinary strict threshold and anything else is a tolerance.
COUNT_METRICS: frozenset[str] = frozenset({"missing_count", "invalid_count", "duplicate_count"})
PERCENT_METRICS: frozenset[str] = frozenset(
    {"missing_percent", "invalid_percent", "duplicate_percent"}
)


class SodaImporter(Importer):
    """Reads a SodaCL ``checks.yml``."""

    format_name = "SodaCL"

    def read(self, document: Any) -> ImportResult:
        out = Collector(self.format_name)
        if not isinstance(document, dict):
            out.unmapped("the file", "this is not a SodaCL checks file")
            return out.result()
        for header, checks in document.items():
            match = _HEADER.match(str(header))
            if match is None:
                out.unmapped(
                    str(header),
                    "only 'checks for <dataset>' blocks are imported",
                    remedy=(
                        "Filters, for-each blocks and configuration are declared "
                        "elsewhere in Prama and are not controls."
                    ),
                )
                continue
            dataset = match.group("dataset")
            for check in checks or []:
                self._check(out, dataset, check)
        return out.result()

    # -- one check ---------------------------------------------------------

    def _check(self, out: Collector, dataset: str, check: Any) -> None:
        text, options = _split(check)
        if not text:
            out.unmapped(str(check), "this check has no readable form", dataset=dataset)
            return
        origin = f"SodaCL check '{text}' on {dataset}"
        if _REFERENCE.match(text):
            self._reference(out, dataset, text, origin)
            return
        between = _BETWEEN.match(text)
        if between:
            self._between(out, dataset, between, origin)
            return
        metric = _METRIC.match(text)
        if metric:
            self._metric(out, dataset, metric, options, origin)
            return
        out.unmapped(
            text,
            "this check's form is not one Prama recognises",
            dataset=dataset,
            remedy=(
                "Read what it asserts and write the control. Prama will not "
                "approximate it: a plausible control passes review and then checks "
                "something else."
            ),
        )

    def _reference(self, out: Collector, dataset: str, text: str, origin: str) -> None:
        match = _REFERENCE.match(text)
        assert match is not None
        out.control(
            f"CHECK {dataset}.{match.group('column').strip()} REFERENCES "
            f"{match.group('target')}.{match.group('target_column').strip()} "
            f"{because(origin)}"
        )

    def _between(self, out: Collector, dataset: str, match: re.Match[str], origin: str) -> None:
        metric = match.group("metric").lower()
        if metric != "row_count":
            out.unmapped(
                match.group(0),
                f"a between-range on {metric} has no direct PQL form",
                dataset=dataset,
            )
            return
        out.control(
            f"CHECK {dataset} HAS ROW COUNT BETWEEN {match.group('low')} "
            f"AND {match.group('high')} {because(origin)}"
        )

    def _metric(
        self,
        out: Collector,
        dataset: str,
        match: re.Match[str],
        options: dict[str, Any],
        origin: str,
    ) -> None:
        metric = match.group("metric").lower()
        column = (match.group("args") or "").strip()
        operator = match.group("operator")
        value = match.group("value")
        percent = bool(match.group("percent")) or metric in PERCENT_METRICS

        if metric == "freshness":
            self._freshness(out, dataset, operator, value, origin)
            return
        if metric == "row_count":
            self._row_count(out, dataset, operator, value, origin)
            return
        if not column:
            out.unmapped(match.group(0), f"{metric} names no column", dataset=dataset)
            return
        base = metric.replace("_percent", "").replace("_count", "")
        threshold = _threshold(operator, value, percent=percent)
        if threshold is None:
            out.unmapped(
                match.group(0),
                f"'{operator} {value}' is a lower bound on failures, which asserts "
                f"that data is broken rather than that it is sound",
                dataset=dataset,
            )
            return
        if base == "missing":
            out.control(
                f"CHECK {dataset}.{column} IS NOT NULL {threshold} {because(origin)}".strip()
            )
            return
        if base == "duplicate":
            columns = ", ".join(part.strip() for part in column.split(","))
            out.control(f"CHECK {dataset} HAS UNIQUE KEY ({columns}) {because(origin)}")
            return
        if base == "invalid":
            self._invalid(out, dataset, column, options, threshold, origin)
            return
        out.unmapped(
            match.group(0),
            f"{metric} has no equivalent control yet",
            dataset=dataset,
            remedy="Raise it as a gap rather than approximating it.",
        )

    def _freshness(
        self, out: Collector, dataset: str, operator: str, value: str, origin: str
    ) -> None:
        """``freshness(as_of) < 1d`` — a real control, not a failure count.

        Handled apart from the metric table because its threshold is a
        duration, and reporting it through the count logic produced an
        explanation that was simply untrue: it called a legitimate freshness
        bound "a lower bound on failures". A wrong reason on an import report
        is worse than no reason, since the report is what somebody signs off.
        """
        if operator not in ("<", "<="):
            out.unmapped(
                f"freshness {operator} {value}",
                "freshness states how stale the data may be, so only an upper bound has a meaning",
                dataset=dataset,
            )
            return
        minutes = _duration_minutes(value)
        if minutes is None:
            out.unmapped(
                f"freshness {operator} {value}",
                f"{value!r} is not a duration Prama can read",
                dataset=dataset,
                remedy="Durations are written like 30m, 4h or 1d.",
            )
            return
        out.control(
            f"CHECK {dataset} IS FRESH WITHIN {minutes} MINUTES {because(origin)}",
            caveat=(
                "SodaCL measures staleness from now; Prama measures it against a "
                "declared arrival time, which is not stated here. Add "
                "OF '06:30' CALENDAR '...' once the feed's window is declared."
            ),
        )

    def _row_count(
        self, out: Collector, dataset: str, operator: str, value: str, origin: str
    ) -> None:
        try:
            count = int(float(value))
        except ValueError:
            out.unmapped(
                f"row_count {operator} {value}",
                f"{value!r} is not a count",
                dataset=dataset,
            )
            return
        # A row count is a whole number, so an exclusive bound is exactly an
        # inclusive one on the next integer. Rewriting it that way is an
        # identity rather than an approximation — and it avoids emitting
        # "AT LEAST 0", which asserts nothing at all and which the linter
        # would rightly report as a control that can never fire.
        bounds = {
            ">": ("AT LEAST", count + 1),
            ">=": ("AT LEAST", count),
            "<": ("AT MOST", count - 1),
            "<=": ("AT MOST", count),
        }
        if operator not in bounds:
            out.unmapped(
                f"row_count {operator} {value}",
                "an exact row count is almost never what somebody means",
                dataset=dataset,
                remedy=f"Write a range: HAS ROW COUNT BETWEEN {value} AND {value}.",
            )
            return
        bound, limit = bounds[operator]
        out.control(f"CHECK {dataset} HAS ROW COUNT {bound} {limit} {because(origin)}")

    def _invalid(
        self,
        out: Collector,
        dataset: str,
        column: str,
        options: dict[str, Any],
        threshold: str,
        origin: str,
    ) -> None:
        values = options.get("valid values")
        if values:
            rendered = ", ".join(quote(v) for v in values)
            out.control(
                f"CHECK {dataset}.{column} IN ({rendered}) {threshold} {because(origin)}".strip()
            )
            return
        pattern = options.get("valid regex")
        if pattern:
            out.control(
                f"CHECK {dataset}.{column} MATCHES /{pattern}/ {threshold} "
                f"{because(origin)}".strip()
            )
            return
        low, high = options.get("valid min"), options.get("valid max")
        if low is not None and high is not None:
            out.control(
                f"CHECK {dataset}.{column} BETWEEN {quote(low)} AND {quote(high)} "
                f"{threshold} {because(origin)}".strip()
            )
            return
        out.unmapped(
            f"invalid check on {dataset}.{column}",
            "the check does not say what makes a value valid",
            dataset=dataset,
            remedy=(
                "Soda takes validity from a column configuration elsewhere in the "
                "scan. Bring that definition across with the check."
            ),
        )


def _split(check: Any) -> tuple[str, dict[str, Any]]:
    """A SodaCL check as (text, options), in either of its forms."""
    if isinstance(check, str):
        return check.strip(), {}
    if isinstance(check, dict) and len(check) == 1:
        text, options = next(iter(check.items()))
        return str(text).strip().rstrip(":"), options if isinstance(options, dict) else {}
    return "", {}


def _threshold(operator: str, value: str, *, percent: bool) -> str | None:
    """SodaCL's threshold as a PQL one, or None when it cannot be one.

    ``> 0`` on a failure count asserts that the data *is* broken. That is a
    legitimate thing to write in a test suite and a strange thing to want in a
    control estate, so it is reported rather than inverted into something
    nobody wrote.
    """
    if operator in (">", ">=", "<>", "!="):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    if number == 0 and not percent:
        return ""  # the strict default
    if percent:
        return f"BELOW {number:g}%"
    return f"AT MOST {number:g} ROWS"


def _duration_minutes(value: str) -> int | None:
    """``30m``, ``4h``, ``1d`` as minutes."""
    text = value.strip().lower()
    units = {"m": 1, "min": 1, "h": 60, "hr": 60, "d": 1440}
    for suffix, factor in sorted(units.items(), key=lambda p: -len(p[0])):
        if text.endswith(suffix):
            try:
                return int(float(text[: -len(suffix)]) * factor)
            except ValueError:
                return None
    return None
