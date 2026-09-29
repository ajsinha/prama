<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# Data contracts from Python

`client.contracts` does what `prama contract` does, over the API: read an ODCS
contract, export a declared dataset as one, check rows against one, and diff two
versions of a dataset.

A file argument can be a path (its suffix says the format: `.json`, `.jsonl`,
`.csv`, `.yaml`), Python rows or a document (sent as JSON), or `(filename, bytes)`.

## The gate

```python
import prama.sdk as prama

client = prama.connect()
result = client.contracts.check("contracts/positions.yaml", "build/positions.csv")
if result["breached"]:
    raise SystemExit(3)
```

`prama contract check` exits 3 on a breach. Here a breach is a result, not an
exception: `breached` is the gate, and the reasons are in `missing_columns`,
`mandatory_with_nulls` and `unexpected_columns`. A new column is a breach unless
`allow_additions=True`: a removed column breaks every consumer and an added one
breaks none.

A file with no rows is never a pass: `checked` is `False` and `breached` is `True`,
because a check over nothing has established nothing.

A check that cannot be made raises instead — a contract with no schema, rows that do
not parse — as `prama.ValidationError`. That keeps "your change broke the contract"
apart from "the checker fell over", which is what the CLI's exit 1 and exit 3 do.

Checking, reading and diffing need `contract:check`, which the `owner` and `steward`
roles hold. It permits nothing else, so a CI key can hold it alone.

## What changed

```python
d = client.contracts.diff("before.csv", "after.csv", key=["trade_id"], ignore=["loaded_at"])
d["added"], d["removed"], d["changed"], d["columns_that_changed"], d["changed_examples"]
```

Rows are matched by `key`. Without one the diff is a membership comparison and says
so (`comparable` is `False`): nothing says which row is which, so no row "changed".
Examples are capped; the counts are not.

## Reading and writing contracts

```python
read = client.contracts.read("positions.odcs.yaml")
read["dataset"]["attributes"], read["ignored"], read["defaulted"], read["quality"]["controls"]

document = client.contracts.export("positions_eod")      # a declared dataset, by slug
```

`read` stores nothing. It returns the declaration the contract describes, what did
not come across (`ignored`), the facts Prama needs that the contract does not carry
(`defaulted`), and its quality blocks as PQL controls, with the ones that could not
be translated and why. Declaring the dataset is `client.datasets.declare`.
