"""Importing dbt tests.

The largest installed base of data tests in the world, and the one most people
arrive with. A dbt ``schema.yml`` declares tests against models and columns:
``unique``, ``not_null``, ``accepted_values``, ``relationships``, plus whatever
``dbt_utils`` and a dozen other packages add.

Two differences from dbt matter enough to state on every import, because they
change what a control means rather than how it is written.

**dbt's ``unique`` is not Prama's unique key.** ``unique`` on a column asserts
that column alone is distinct; a declared grain of three columns is a
``dbt_utils.unique_combination_of_columns`` if somebody installed that package
and a comment if they did not. Both are imported, and the difference is kept.

**dbt's tests are silent about nulls.** ``accepted_values`` passes a null,
because SQL's ``IN`` is unknown for a null and dbt counts only rows that are
definitely failing. Prama counts an unknown as a violation. So an imported
``accepted_values`` will find rows dbt never reported — which is the point of
migrating, and is also a surprise if nobody says it in advance. Every such
import carries the caveat.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.importers.spi import Collector, Importer, ImportResult, because, quote

#: Tests that map exactly, by name.
DIRECT: frozenset[str] = frozenset({"unique", "not_null"})

#: Tests whose dbt spelling differs between packages but whose meaning is one
#: thing. Keyed by the last segment, so ``dbt_utils.expression_is_true`` and a
#: bare ``expression_is_true`` are the same test.
KNOWN: frozenset[str] = frozenset(
    {
        "unique",
        "not_null",
        "accepted_values",
        "relationships",
        "unique_combination_of_columns",
        "expression_is_true",
        "not_null_proportion",
        "accepted_range",
    }
)

#: The nulls caveat, stated once and attached wherever it applies.
NULL_CAVEAT = (
    "dbt lets a null pass this test, because SQL's comparison is unknown for a "
    "null and dbt counts only rows that definitely fail. Prama counts an unknown "
    "as a violation, so this control will find rows dbt never reported. Add "
    "TREAT UNKNOWN AS PASS to keep dbt's behaviour exactly."
)


class DbtImporter(Importer):
    """Reads a dbt ``schema.yml``."""

    format_name = "dbt"

    def read(self, document: Any) -> ImportResult:
        collector = Collector(self.format_name)
        if not isinstance(document, dict):
            collector.unmapped(
                "the file", "this is not a dbt schema file", remedy="Point at a schema.yml."
            )
            return collector.result()
        for section in ("models", "sources", "seeds", "snapshots"):
            for model in document.get(section) or []:
                self._model(collector, model, section)
        return collector.result()

    # -- one model ---------------------------------------------------------

    def _model(self, out: Collector, model: Any, section: str) -> None:
        if not isinstance(model, dict) or not model.get("name"):
            return
        name = str(model["name"])
        if section == "sources":
            # A source declares tables beneath it; each is a dataset.
            for table in model.get("tables") or []:
                self._model(out, table, "models")
            return
        for test in model.get("tests") or model.get("data_tests") or []:
            self._model_test(out, name, test)
        for column in model.get("columns") or []:
            self._column(out, name, column)

    def _column(self, out: Collector, dataset: str, column: Any) -> None:
        if not isinstance(column, dict) or not column.get("name"):
            return
        name = str(column["name"])
        for test in column.get("tests") or column.get("data_tests") or []:
            self._column_test(out, dataset, name, test)

    # -- one test ----------------------------------------------------------

    def _column_test(self, out: Collector, dataset: str, column: str, test: Any) -> None:
        kind, options = _split(test)
        origin = f"dbt test {kind} on {dataset}.{column}"
        target = f"{dataset}.{column}"
        if kind == "not_null":
            out.control(f"CHECK {target} IS NOT NULL {because(origin)}")
            return
        if kind == "unique":
            out.control(
                f"CHECK {dataset} HAS UNIQUE KEY ({column}) {because(origin)}",
                caveat=(
                    "dbt's `unique` asserts this column alone is distinct. If the "
                    "declared grain is wider, the control is weaker than the grain "
                    "and will not catch a duplicate on the full key."
                ),
            )
            return
        if kind == "accepted_values":
            values = options.get("values") or []
            if not values:
                out.unmapped(
                    origin,
                    "the test lists no values",
                    dataset=dataset,
                    remedy="Give the permitted values, or drop the test.",
                )
                return
            rendered = ", ".join(quote(v) for v in values)
            out.control(
                f"CHECK {target} IN ({rendered}) {because(origin)}",
                caveat=NULL_CAVEAT,
            )
            return
        if kind == "relationships":
            self._relationship(out, dataset, column, options, origin)
            return
        if kind == "accepted_range":
            self._range(out, dataset, column, options, origin)
            return
        if kind == "not_null_proportion":
            self._proportion(out, dataset, column, options, origin)
            return
        self._refuse(out, kind, origin, dataset)

    def _model_test(self, out: Collector, dataset: str, test: Any) -> None:
        kind, options = _split(test)
        origin = f"dbt test {kind} on {dataset}"
        if kind == "unique_combination_of_columns":
            columns = options.get("combination_of_columns") or []
            if not columns:
                out.unmapped(origin, "the test names no columns", dataset=dataset)
                return
            out.control(
                f"CHECK {dataset} HAS UNIQUE KEY ({', '.join(map(str, columns))}) {because(origin)}"
            )
            return
        if kind == "expression_is_true":
            expression = options.get("expression")
            if not expression:
                out.unmapped(origin, "the test carries no expression", dataset=dataset)
                return
            out.control(
                f"CHECK {dataset} SATISFIES {expression} {because(origin)}",
                caveat=(
                    "The expression was carried across unchanged. It was written for "
                    "dbt's warehouse dialect and has not been checked against the "
                    "engine this control will run on."
                ),
            )
            return
        self._refuse(out, kind, origin, dataset)

    def _relationship(
        self, out: Collector, dataset: str, column: str, options: dict, origin: str
    ) -> None:
        target = str(options.get("to") or "")
        field = str(options.get("field") or "")
        resolved = _dereference(target)
        if not resolved or not field:
            out.unmapped(
                origin,
                "the test does not name both a target model and a field",
                dataset=dataset,
            )
            return
        out.control(
            f"CHECK {dataset}.{column} REFERENCES {resolved}.{field} {because(origin)}",
            caveat=(
                "dbt's relationships test ignores nulls; Prama counts a null "
                "reference as a violation. Add TREAT UNKNOWN AS PASS if a missing "
                "reference is genuinely permitted."
            ),
        )

    def _range(self, out: Collector, dataset: str, column: str, options: dict, origin: str) -> None:
        low, high = options.get("min_value"), options.get("max_value")
        if low is None or high is None:
            out.unmapped(
                origin,
                "a one-sided range has no PQL form yet",
                dataset=dataset,
                remedy=(
                    f"Write it as a comparison: CHECK {dataset}.{column} > "
                    f"{low if low is not None else high}."
                ),
            )
            return
        inclusive = options.get("inclusive", True)
        if not inclusive:
            out.unmapped(
                origin,
                "an exclusive range would change which rows fail",
                dataset=dataset,
                remedy="Write it as two comparisons, or widen the bounds by one unit.",
            )
            return
        out.control(
            f"CHECK {dataset}.{column} BETWEEN {quote(low)} AND {quote(high)} {because(origin)}",
            caveat=NULL_CAVEAT,
        )

    def _proportion(
        self, out: Collector, dataset: str, column: str, options: dict, origin: str
    ) -> None:
        at_least = options.get("at_least")
        if at_least is None:
            out.unmapped(origin, "the test states no proportion", dataset=dataset)
            return
        tolerated = round((1.0 - float(at_least)) * 100, 6)
        out.control(
            f"CHECK {dataset}.{column} IS NOT NULL BELOW {tolerated:g}% {because(origin)}",
            caveat=(
                f"dbt states the proportion that must be present ({at_least}); Prama "
                f"states the proportion that may be missing ({tolerated:g}%). The same "
                f"threshold, read from the other end."
            ),
        )

    @staticmethod
    def _refuse(out: Collector, kind: str, origin: str, dataset: str) -> None:
        if kind in KNOWN:
            out.unmapped(
                origin,
                "this test is known but not on a column that supports it",
                dataset=dataset,
            )
            return
        out.unmapped(
            origin,
            "this is a custom or package test whose meaning Prama cannot know",
            dataset=dataset,
            remedy=(
                "Read what it asserts and write the equivalent control. Prama will not "
                "guess: an approximated control passes review and then checks something "
                "else."
            ),
        )


def _split(test: Any) -> tuple[str, dict[str, Any]]:
    """A dbt test as (name, options), whichever of its two forms it is in."""
    if isinstance(test, str):
        return _base(test), {}
    if isinstance(test, dict) and len(test) == 1:
        name, options = next(iter(test.items()))
        return _base(str(name)), options if isinstance(options, dict) else {}
    return "", {}


def _base(name: str) -> str:
    """``dbt_utils.accepted_range`` and ``accepted_range`` are one test."""
    return name.rsplit(".", 1)[-1]


def _dereference(target: str) -> str:
    """``ref('accounts')`` and ``source('raw', 'accounts')`` to a dataset name."""
    text = target.strip()
    if text.startswith(("ref(", "source(")):
        inner = text[text.index("(") + 1 : text.rindex(")")]
        parts = [p.strip().strip("\"'") for p in inner.split(",")]
        return parts[-1] if parts else ""
    return text.strip("\"'")
