"""Importing a Great Expectations suite.

GE suites are JSON, which makes them the easiest of the three to read and the
hardest to read *honestly*. The expectation vocabulary is large, several
expectations look alike and differ in one keyword argument, and a handful mean
something subtly different from their name.

Three of those differences are worth stating, because each would otherwise
change a control's meaning without changing its appearance.

**``mostly`` is a tolerance, and it is stated from the other end.** GE's
``mostly: 0.99`` means 99% must pass; Prama's ``BELOW 1%`` means 1% may fail.
The same threshold, and easy to invert by accident.

**GE ignores nulls in most value expectations.**
``expect_column_values_to_be_in_set`` passes a null unless the suite also
expects the column to be non-null. Prama counts an unknown as a violation, so
an imported expectation finds rows GE never reported.

**``expect_column_values_to_be_unique`` is per column.** A three-column grain
is ``expect_compound_columns_to_be_unique``, and importing the first as though
it were the second would silently weaken the control.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
from typing import Any

from prama.importers.spi import Collector, Importer, ImportResult, because, quote

NULL_CAVEAT = (
    "Great Expectations ignores nulls in this expectation; Prama counts an "
    "unknown as a violation. This control will find rows the suite never "
    "reported. Add TREAT UNKNOWN AS PASS to keep the original behaviour."
)


class GreatExpectationsImporter(Importer):
    """Reads a Great Expectations expectation suite."""

    format_name = "Great Expectations"

    def read(self, document: Any) -> ImportResult:
        out = Collector(self.format_name)
        if not isinstance(document, dict):
            out.unmapped("the file", "this is not an expectation suite")
            return out.result()
        dataset = str(
            document.get("expectation_suite_name") or document.get("data_asset_name") or "dataset"
        ).split(".")[-1]
        for expectation in document.get("expectations") or []:
            self._expectation(out, dataset, expectation)
        return out.result()

    def _parse(self, text: str) -> Any:
        return json.loads(text)

    # -- one expectation ---------------------------------------------------

    def _expectation(self, out: Collector, dataset: str, expectation: Any) -> None:
        if not isinstance(expectation, dict):
            return
        kind = str(expectation.get("expectation_type") or "")
        options = expectation.get("kwargs") or {}
        origin = f"Great Expectations {kind} on {dataset}"
        column = str(options.get("column") or "")
        threshold, note = _tolerance(options.get("mostly"))
        target = f"{dataset}.{column}"

        if kind == "expect_column_values_to_not_be_null":
            out.control(
                f"CHECK {target} IS NOT NULL {threshold} {because(origin)}".replace("  ", " "),
                caveat=note,
            )
            return
        if kind == "expect_column_values_to_be_null":
            out.control(
                f"CHECK {target} IS NULL {threshold} {because(origin)}".replace("  ", " "),
                caveat=note,
            )
            return
        if kind == "expect_column_values_to_be_unique":
            out.control(
                f"CHECK {dataset} HAS UNIQUE KEY ({column}) {because(origin)}",
                caveat=(
                    "This expectation is per column. If the declared grain is wider, "
                    "the control is weaker than the grain and will not catch a "
                    "duplicate on the full key."
                ),
            )
            return
        if kind == "expect_compound_columns_to_be_unique":
            columns = options.get("column_list") or []
            if not columns:
                out.unmapped(origin, "the expectation names no columns", dataset=dataset)
                return
            out.control(
                f"CHECK {dataset} HAS UNIQUE KEY ({', '.join(map(str, columns))}) {because(origin)}"
            )
            return
        if kind == "expect_column_values_to_be_in_set":
            self._in_set(out, dataset, column, options, threshold, origin)
            return
        if kind == "expect_column_values_to_not_be_in_set":
            self._not_in_set(out, dataset, column, options, threshold, origin)
            return
        if kind == "expect_column_values_to_be_between":
            self._between(out, dataset, column, options, threshold, origin)
            return
        if kind == "expect_column_value_lengths_to_be_between":
            self._length(out, dataset, column, options, threshold, origin)
            return
        if kind == "expect_column_value_lengths_to_equal":
            length = options.get("value")
            if length is None:
                out.unmapped(origin, "the expectation states no length", dataset=dataset)
                return
            out.control(
                f"CHECK {target} HAS LENGTH BETWEEN {length} AND {length} "
                f"{threshold} {because(origin)}".replace("  ", " "),
                caveat=NULL_CAVEAT,
            )
            return
        if kind == "expect_column_values_to_match_regex":
            pattern = options.get("regex")
            if not pattern:
                out.unmapped(origin, "the expectation states no pattern", dataset=dataset)
                return
            out.control(
                f"CHECK {target} MATCHES /{pattern}/ {threshold} {because(origin)}".replace(
                    "  ", " "
                ),
                caveat=NULL_CAVEAT,
            )
            return
        if kind == "expect_table_row_count_to_be_between":
            self._row_count(out, dataset, options, origin)
            return
        if kind == "expect_table_row_count_to_equal":
            value = options.get("value")
            if value is None:
                out.unmapped(origin, "the expectation states no count", dataset=dataset)
                return
            out.control(
                f"CHECK {dataset} HAS ROW COUNT BETWEEN {value} AND {value} {because(origin)}"
            )
            return
        out.unmapped(
            origin,
            "this expectation has no equivalent control yet",
            dataset=dataset,
            remedy=(
                "Read what it asserts and write the control. Prama will not guess: "
                "several expectations differ from one another by a single keyword "
                "argument, and the wrong one looks exactly as convincing."
            ),
        )

    # -- shapes ------------------------------------------------------------

    def _in_set(
        self,
        out: Collector,
        dataset: str,
        column: str,
        options: dict,
        threshold: str,
        origin: str,
    ) -> None:
        values = options.get("value_set")
        if not values:
            out.unmapped(origin, "the expectation lists no values", dataset=dataset)
            return
        rendered = ", ".join(quote(v) for v in values)
        out.control(
            f"CHECK {dataset}.{column} IN ({rendered}) {threshold} {because(origin)}".replace(
                "  ", " "
            ),
            caveat=NULL_CAVEAT,
        )

    def _not_in_set(
        self,
        out: Collector,
        dataset: str,
        column: str,
        options: dict,
        threshold: str,
        origin: str,
    ) -> None:
        values = options.get("value_set")
        if not values:
            out.unmapped(origin, "the expectation lists no values", dataset=dataset)
            return
        rendered = ", ".join(quote(v) for v in values)
        out.control(
            f"CHECK {dataset}.{column} NOT IN ({rendered}) {threshold} {because(origin)}".replace(
                "  ", " "
            ),
            caveat=NULL_CAVEAT,
        )

    def _between(
        self,
        out: Collector,
        dataset: str,
        column: str,
        options: dict,
        threshold: str,
        origin: str,
    ) -> None:
        low, high = options.get("min_value"), options.get("max_value")
        if low is None or high is None:
            out.unmapped(
                origin,
                "a one-sided range has no BETWEEN form",
                dataset=dataset,
                remedy=(
                    f"Write it as a comparison: "
                    f"CHECK {dataset}.{column} > {low if low is not None else high}."
                ),
            )
            return
        if options.get("strict_min") or options.get("strict_max"):
            out.unmapped(
                origin,
                "an exclusive bound would change which rows fail",
                dataset=dataset,
                remedy="Write it as two comparisons, or adjust the bound by one unit.",
            )
            return
        out.control(
            f"CHECK {dataset}.{column} BETWEEN {quote(low)} AND {quote(high)} "
            f"{threshold} {because(origin)}".replace("  ", " "),
            caveat=NULL_CAVEAT,
        )

    def _length(
        self,
        out: Collector,
        dataset: str,
        column: str,
        options: dict,
        threshold: str,
        origin: str,
    ) -> None:
        low, high = options.get("min_value"), options.get("max_value")
        if low is None or high is None:
            out.unmapped(origin, "a one-sided length has no BETWEEN form", dataset=dataset)
            return
        out.control(
            f"CHECK {dataset}.{column} HAS LENGTH BETWEEN {low} AND {high} "
            f"{threshold} {because(origin)}".replace("  ", " "),
            caveat=NULL_CAVEAT,
        )

    def _row_count(self, out: Collector, dataset: str, options: dict, origin: str) -> None:
        low, high = options.get("min_value"), options.get("max_value")
        if low is not None and high is not None:
            out.control(f"CHECK {dataset} HAS ROW COUNT BETWEEN {low} AND {high} {because(origin)}")
            return
        if low is not None:
            out.control(f"CHECK {dataset} HAS ROW COUNT AT LEAST {low} {because(origin)}")
            return
        if high is not None:
            out.control(f"CHECK {dataset} HAS ROW COUNT AT MOST {high} {because(origin)}")
            return
        out.unmapped(origin, "the expectation states no bound", dataset=dataset)


def _tolerance(mostly: Any) -> tuple[str, str]:
    """GE's ``mostly`` as a PQL threshold, and the caveat that goes with it.

    A `mostly` that cannot be read is *reported*, not dropped. Returning no
    threshold made the imported control stricter than the one it came from —
    `mostly: high` became a control tolerating nothing — with no caveat and no
    unmapped entry, so the import looked complete (QA finding IMP-046).

    Stricter is not safer here. A control nobody asked for fails on data the
    source suite accepted, and the first person to see it has no way to know
    the tolerance was lost in translation.
    """
    if mostly is None:
        return "", ""
    try:
        proportion = float(mostly)
    except (TypeError, ValueError):
        return "", (
            f"'mostly: {mostly!r}' could not be read as a proportion, so no tolerance "
            "was applied. The imported control is stricter than the one it came "
            "from: check what the original meant."
        )
    if proportion >= 1.0:
        return "", ""
    tolerated = round((1.0 - proportion) * 100, 6)
    return (
        f"BELOW {tolerated:g}%",
        f"'mostly: {mostly}' means {proportion:.0%} must pass; Prama states the "
        f"same threshold as {tolerated:g}% may fail. Read from the other end.",
    )
