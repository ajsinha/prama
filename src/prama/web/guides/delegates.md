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

Writing, configuring and testing a delegate (the interface, what Prama refuses and when, the
`delegates:` settings, entry points, and the conformance kit for your own CI) is in the developer
guide, [Writing a DQ delegate](../../../../docs/developer/delegates.md). This page is about
using one in the console.

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

## Trying one out

```bash
prama delegate list                              # admitted, and refused with the reason
prama delegate scan ./my_delegates               # vet files without importing them
prama delegate test acme.over_limit --rows sample.csv --param limit=5000
```

Case study 5 (`case-studies/05-dq-delegates`) runs two delegates: one on the control plane, and
one on a remote agent in a PCI zone.

## Go deeper

- [Execution](../../../../docs/architecture/execution.md): where a delegate runs, and how its counts are judged.
- [Writing a DQ delegate](../../../../docs/developer/delegates.md): the interface, the refusals, configuration and testing.
- [DQ delegates: design](../../../../docs/design/dq-delegates.md): why the delegate measures and Prama decides.
