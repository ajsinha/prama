"""An importer for a rules spreadsheet: the worked example of docs/developer/importers.md.

Nobody adopts a data quality platform on an empty estate, and the commonest
estate is not dbt: it is a spreadsheet, saved as CSV, with one rule per row:

    dataset,column,rule,value
    trades,trade_id,not null,
    trades,trade_id,unique,
    trades,ccy,one of,USD|EUR|GBP
    trades,notional,minimum,0
    trades,book,looks right,

Four rules have a meaning that is certain, and come across. ``looks right`` has
none, and is reported by name as not having come across, rather than guessed at.
Every imported control carries a ``BECAUSE`` naming the row it came from.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation
from typing import Any

from prama.importers.spi import Collector, Importer, ImportResult, because, quote

#: The same caveat the dbt importer attaches: Prama counts a blank as a violation.
BLANKS = (
    "A blank counts as a violation here, as it does everywhere in Prama. The sheet "
    "did not say whether a blank was allowed; add TREAT UNKNOWN AS PASS if it is."
)


class RulesSheetImporter(Importer):
    """Reads a ``dataset,column,rule,value`` CSV."""

    format_name = "rules spreadsheet (CSV)"

    def _parse(self, text: str) -> Any:
        return list(csv.DictReader(io.StringIO(text)))

    def read(self, document: Any) -> ImportResult:
        out = Collector(self.format_name)
        for line, row in enumerate(document or [], start=2):
            dataset = (row.get("dataset") or "").strip()
            column = (row.get("column") or "").strip()
            rule = (row.get("rule") or "").strip().lower()
            value = (row.get("value") or "").strip()
            origin = f"rules sheet row {line} ({dataset}.{column}: {rule or 'no rule'})"
            if not dataset or not column:
                out.unmapped(origin, "the row names no dataset or no column", dataset=dataset)
                continue
            self._rule(out, dataset, column, rule, value, origin)
        return out.result()

    def _rule(
        self, out: Collector, dataset: str, column: str, rule: str, value: str, origin: str
    ) -> None:
        target = f"{dataset}.{column}"
        if rule in ("not null", "mandatory", "required"):
            out.control(f"CHECK {target} IS NOT NULL {because(origin)}")
        elif rule == "unique":
            out.control(
                f"CHECK {dataset} HAS UNIQUE KEY ({column}) {because(origin)}",
                caveat=(
                    "The sheet says this column alone is distinct. If the dataset's "
                    "declared grain is wider, this control is weaker than the grain."
                ),
            )
        elif rule == "one of" and value:
            allowed = ", ".join(quote(v.strip()) for v in value.split("|") if v.strip())
            out.control(f"CHECK {target} IN ({allowed}) {because(origin)}", caveat=BLANKS)
        elif rule == "minimum" and _is_number(value):
            out.control(f"CHECK {target} >= {value} {because(origin)}", caveat=BLANKS)
        else:
            # Never guessed. An approximated control passes review because it
            # looks like the others, and then quietly checks something else.
            out.unmapped(
                origin,
                f"no Prama construct is certain to mean {rule!r} with value {value!r}",
                remedy="Write this control by hand in PQL; the rest of the import is unaffected.",
                dataset=dataset,
            )


def _is_number(text: str) -> bool:
    try:
        Decimal(text)
    except InvalidOperation:
        return False
    return bool(text)
