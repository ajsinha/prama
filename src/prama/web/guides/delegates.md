<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# DQ delegates: your own Python checks

Some checks are code: a settlement cycle that depends on a market calendar, a first-digit (Benford)
test over a ledger, a scoring rule only your firm uses. A **delegate** is that code, written as a
Python class, registered under a name, and used from PQL like any other assertion:

```pql
CHECK trade_blotter USING DELEGATE 'acme.settlement_cycle@1' (us_cycle = 1, eu_cycle = 2)
  WHERE status = 'booked'
  SEVERITY critical
  BECAUSE 'a trade that settles off-cycle is a failed settlement'
```

## The delegate measures, Prama decides

A delegate returns **counts**: how many rows (or findings) it scanned and how many violate, plus
named observations such as `mad` or `late_settlements`. The control's threshold turns those
counts into a verdict, in the same code that judges every other control. `BELOW 0.1%`,
`AT MOST 5 ROWS` and the default of no violations all work as usual. A delegate that could not
establish anything (too few rows for a statistical test) produces **indeterminate**, never a
pass.

## Writing one

```python
from prama.delegates import DqDelegate, Measurement, Parameter


class OverLimit(DqDelegate):
    name = "acme.over_limit"  # what PQL names
    version = "1"  # pinned from PQL as 'acme.over_limit@1'
    requires = ("payment_id", "amount")  # the only columns fetched
    parameters = (Parameter("limit", "number", 5000),)
    unit = "rows"  # or "findings"
    summary = "no single payment exceeds the limit"

    def measure(self, rows, params):
        scanned = violating = 0
        for row in rows:
            scanned += 1
            try:
                violating += float(row["amount"]) > params["limit"]
            except (TypeError, ValueError):
                violating += 1  # an unreadable amount is a violation, not a crash
        return Measurement(scanned=scanned, violating=violating)
```

Rows arrive as **JSON values**. A date is ISO-8601 text and a decimal is a number, whichever
engine the data came from.

## What Prama refuses, and when

| Rule | Checked | Why |
|---|---|---|
| No clock, network, filesystem, subprocess or model | By scanning the source **before import** | A verdict that depends on when or where it ran cannot be replayed |
| Same answer twice on the same probe rows | At admission | Hidden state makes evidence irreproducible |
| No exception on nulls, blanks or an empty dataset | At admission | The first blank in production would take the control down |
| Counts are whole numbers; violations never exceed the rows scanned | Every run | A measurement that cannot be judged is an error, not a verdict |
| Too many rows | Every run | Refused, never silently truncated |

Every evidence record names the delegate, its version and a **hash of its source**. If you edit
the delegate, the hash changes, so you can always tell what produced a verdict.

## Where delegates come from: configuration

Each host (the server, and every remote agent beside the data) reads **its own** `delegates:`
section and runs only what that section admits:

```yaml
delegates:
  paths: [/opt/acme/delegates]   # directories of .py files, scanned before import
  entry_points: true             # and installed packages advertising prama.delegates
  disabled: []
  sandbox: true                  # a resource-limited subprocess per run
  timeout: 120
  max_rows: 5000000
```

A remote agent advertises the delegates it admitted, as `name@version`. The control plane assigns
a delegate control only to an agent that has that delegate, at the pinned version. Any other
agent is reported as unable to run it, with the reason. The rows stay in the agent's zone, and
only the counts and the verdict travel.

## Uploading one through the console

User menu → **Delegates** → choose the `.py` file → **Upload and vet**.

1. **Vetting.** Prama runs the conformance kit on it in a sandbox. If anything fails, you are
   told why and nothing is stored.
2. **Approval.** Someone **other than you** who holds control-approval rights reads the source
   and the vetting findings on the same page, then approves or rejects it.
3. **Running it.** Once approved, controls can name it. It always runs in the sandbox, from the
   exact bytes that were approved.
4. **Retiring it.** Retire it to stop it running. To change a delegate, raise its `version` and
   upload it again; a version is never edited in place.

A remote agent gets approved uploads with
`prama delegate pull --server https://prama.example --out /opt/prama/delegates`, where the output
directory is in that agent's `delegates.paths`.

## Large inputs

Rows are read from the database in batches (`delegates.batch_rows`) and handed to `measure` as a
lazy iterator, so a streaming delegate holds one row at a time. Loop over `rows` **once**. A
second loop sees nothing, and the test kit fails a delegate that tries.

## Testing it in your own CI

```python
from prama.delegates.testkit import Case, check_delegate


def test_over_limit_conforms():
    report = check_delegate(
        "delegates/over_limit.py",
        cases=[Case("one over", rows=[{"payment_id": 1, "amount": 9000}], violating=1)],
    )
    assert report.ok, report.render()
```

or `prama delegate check delegates/ --cases cases.json`, which exits 1 when anything fails.

## Trying one out

```bash
prama delegate list                              # admitted, and refused with the reason
prama delegate scan ./my_delegates               # vet files without importing them
prama delegate test acme.over_limit --rows sample.csv --param limit=5000
```

Case study 5 (`case-studies/05-dq-delegates`) runs two delegates: one on the control plane, and
one on a remote agent in a PCI zone.
