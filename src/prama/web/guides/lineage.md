<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Lineage

Prama keeps column-level lineage: which column feeds which, how (copied, cast, computed,
aggregated, used as a filter), and how that is known.

## Scanning SQL

```bash
prama lineage scan etl/ --source warehouse              # every .sql file under etl/
prama lineage scan procs/ --source finrep --dialect tsql
```

SQL is read with a real parser that understands about twenty dialects. It follows a column through
CTEs and subqueries to the table it came from. A statement the parser cannot read is handled by a
simpler pattern reader, and its edges are marked **inferred** for a person to check.

## How an edge is known

| Status | Meaning |
|---|---|
| **parsed** | Produced by the SQL parser from code it fully understood. |
| **inferred** | Produced by the pattern reader, or later by a model. Needs a person. |
| **confirmed** | A person agreed. |
| **rejected** | A person disagreed. It stays rejected however often a scan finds it again. |

Re-scanning refreshes edges rather than duplicating them. An edge a source stops producing is
closed, not deleted: "this report was fed by that column until Tuesday" is lineage too.

## Impact

```bash
prama lineage impact raw.trades.notional
```

Lists everything a defect in that column reaches, ranked by how much of the defect survives each
hop. An aggregate carries least. The **Lineage** page draws the same thing.

## Gaps

```bash
prama lineage gaps
```

Every statement a scan could not fully read is listed with the reason. A partial graph whose gaps
are visible is worth more than a complete-looking one whose gaps are not.
