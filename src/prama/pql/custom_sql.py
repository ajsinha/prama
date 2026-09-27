"""What a CUSTOM SQL check may contain: one read-only query with a known result shape.

Checked when the control is parsed, not when it runs, so a control that would
write, lock or run a procedure never becomes a control at all. The check reads
the SQL's syntax tree (sqlglot) rather than searching its text: a keyword
search refuses `SELECT 'DROP'` and admits a write hidden in a construct it does
not know.

The rules, and the failure each prevents:

* **One statement.** `SELECT …; DELETE …` is two, and the second is the payload.
* **A query at the root.** A SELECT, a UNION of SELECTs, or a WITH ending in a
  SELECT, and no `SELECT … INTO`, which creates a table.
* **No writing or session construct anywhere in the tree,** including inside a
  CTE: INSERT, UPDATE, DELETE, MERGE, CREATE, DROP, ALTER, TRUNCATE, GRANT,
  COPY, SET, CALL/EXEC, transactions, and anything sqlglot could not classify
  (it parses those as an opaque command).
* **A `violating_rows` column.** The threshold reads it, so a query without it
  could only ever be INDETERMINATE: a control that looks present and says
  nothing. `scanned_rows` is optional; a rate threshold needs it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re

#: What `{{ dataset }}` is replaced with while checking. Any identifier works;
#: the real, quoted table name is put in at compile time.
PLACEHOLDER = "__prama_dataset__"

_DATASET = re.compile(r"\{\{\s*dataset\s*\}\}")

#: sqlglot expression classes that are not reading, by name so that a sqlglot
#: release renaming one fails loudly here rather than admitting it.
_FORBIDDEN = (
    "Insert",
    "Update",
    "Delete",
    "Merge",
    "Create",
    "Drop",
    "Alter",
    "TruncateTable",
    "Grant",
    "Copy",
    "Set",
    "Command",
    "Transaction",
    "Commit",
    "Rollback",
    "Into",
    "LoadData",
    "Use",
    "Pragma",
)


def with_dataset(sql: str, table: str) -> str:
    """The SQL with `{{ dataset }}` replaced by *table*, already quoted by the caller."""
    return _DATASET.sub(table, sql)


def check_sql(sql: str) -> str:
    """Why *sql* cannot be a custom check, or an empty string when it can."""
    import sqlglot
    from sqlglot import exp
    from sqlglot.errors import ParseError

    if not sql.strip():
        return "the query is empty"
    try:
        statements = [s for s in sqlglot.parse(with_dataset(sql, PLACEHOLDER)) if s is not None]
    except ParseError as exc:
        return f"it is not SQL this parser can read ({str(exc).splitlines()[0]})"
    if len(statements) != 1:
        return f"it has {len(statements)} statements; a check is exactly one query"
    (tree,) = statements
    if not isinstance(tree, exp.Query):
        return f"it is a {tree.key.upper()} statement, not a query"
    forbidden = tuple(getattr(exp, name) for name in _FORBIDDEN if hasattr(exp, name))
    for node in tree.walk():
        if isinstance(node, forbidden):
            return f"it contains {node.key.upper()}, and a check may only read"
    names = {name.lower() for name in tree.named_selects}
    if "violating_rows" not in names:
        return "it does not return a column named violating_rows"
    return ""
