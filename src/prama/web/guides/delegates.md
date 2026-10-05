<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# DQ delegates: your own Python checks

Some checks are code: a settlement cycle that depends on a market calendar, a Benford test over a
ledger, a scoring rule only your firm uses. A **delegate** is that code, a Python class registered
under a name and used from PQL like any other assertion. The page is **Controls → Delegates**
(`/delegates`); writing one is in the developer guide, and this page is about using one.

```pql
CHECK trade_blotter USING DELEGATE 'acme.settlement_cycle@1' (us_cycle = 1, eu_cycle = 2)
  WHERE status = 'booked'
  SEVERITY critical
  BECAUSE 'a trade that settles off-cycle is a failed settlement'
```

**The delegate measures; Prama decides.** It returns counts (rows scanned, rows violating, named
observations), and the control's threshold (`BELOW 0.1%`, `AT MOST 5 ROWS`, or none) turns them into
a verdict like any other control's. A delegate that could establish nothing produces
**indeterminate**, never a pass.

## To upload a delegate

1. On **Delegates**, choose the `.py` file and press **Upload and vet**. Prama runs the conformance
   kit on it in a sandbox; if anything fails you are told why and nothing is stored.
2. Somebody **other than you** who may approve controls reads the source and the vetting findings
   on the same page, and presses **Approve** or **Reject**. It waits in their queue meanwhile.
3. Once approved, controls can name it. It always runs in the sandbox, from the exact bytes approved.

## To change or retire one

Press **Retire** to stop it running. To change it, raise its `version` and upload again; a version is
never edited in place.

## To run it on a remote agent

Copy the approved uploads into a directory listed in that agent's `delegates.paths`:

```bash
prama delegate pull --server https://prama.example --out /opt/prama/delegates
```

## To try one before uploading

```bash
prama delegate list                              # admitted on this host, and refused with the reason
prama delegate scan ./my_delegates               # vet files without importing them
prama delegate test acme.over_limit --rows sample.csv --param limit=5000
```

Case study 5 (`case-studies/05-dq-delegates`) runs two: one on the control plane, and one on a remote
agent in a PCI zone.

## Go deeper

- [Execution](../../../../docs/architecture/execution.md#delegates-when-the-check-is-code): where a delegate runs, and how its counts are judged.
- [Writing a DQ delegate](../../../../docs/developer/delegates.md): the interface, the refusals, configuration and testing.
- [DQ delegates: design](../../../../docs/design/dq-delegates.md): why the delegate measures and Prama decides.
