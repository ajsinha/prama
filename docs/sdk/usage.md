<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# Dataset usage from Python

`client.usage` records how often each dataset is read, from a warehouse's own query
history, and says what to work on first. It is a priority signal and nothing more:
usage orders a list and is never an input to a quality score, because a popular
dataset is not a better one.

## Importing query history

```python
import prama_sdk as prama

client = prama.connect()
print(client.usage.export_query("snowflake")["query"])   # run this in the warehouse
client.usage.import_history("snowflake", "access_history.json")
# {"warehouse": "snowflake", "rows": 18234, "dataset_days": 412}
```

`snowflake`, `bigquery` and `databricks` are read, each from the columns its export
query returns. The file is a JSON list or a `.csv`; Python rows work too. Importing
the same days again replaces them rather than adding to them. Importing needs
`declaration:write`.

## Reading it back

```python
client.usage.daily(days=7)                        # per dataset, day and source
client.usage.daily(dataset="prod.mart.trades")    # one dataset, as the warehouse names it
client.usage.coaccess(days=30)                    # pairs read by the same query
```

`daily` has one row per dataset, day and source: queries, and distinct readers that
day. `coaccess` lists pairs of datasets read together, busiest first — a hint that
they are related, not a statement that they are.

## Priorities

```python
ranked = client.usage.priorities(days=30)
for row in ranked["datasets"]:
    print(row["slug"], row["queries"], row["controls"], row["failing"])
ranked["undeclared"]                              # used, but nobody has declared them
```

Most used first; among equally used datasets, the one with fewer active controls
first. Datasets the warehouse reads that nobody has declared are listed separately,
because the first thing they need is a declaration. This needs `report:read`.

---

<div align="center">
<img src="../assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../../LICENSE">LICENSE</a> and <a href="../../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
