<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Reconciliation and breaks

A reconciliation checks that two datasets agree: a subledger and the general ledger, positions
and trades. It is declared, not built: a *reconciles-with* relationship, or a `RECONCILE` control
in PQL, and Prama's matching engine does the rest.

## The results

**Assurance → Reconciliation** lists every reconciliation with its latest result: the match rate
and the breaks that need a person. Open one for its break queue.

## Working the breaks

The workbench orders breaks by **what needs a person, not by size**. A large timing break clears
itself the next day; a small genuine difference is somebody's missing trade. Each break says what
kind it is (a *genuine difference*, *missing from the right*, *present only on the right*), the two
values, and how they were compared (converted currencies, totals when a key repeats).

- **Assign** it to whoever owns the fix.
- **Note** what you found.
- **Accept** it only with a reason: an acceptance nobody explained cannot be defended when somebody
  asks about it a year later.

**Include cleared** shows what matched or cleared, to check the engine's decisions.

From Python: `client.reconciliation.list()`, `client.breaks.workbench(definition)`, and
`client.reconciliation.certify(definition)` for the period-end certificate.

## Go deeper

- [SDK: reconciliation](../../../../docs/sdk/reconciliation.md): reconciliations, the workbench and the certificate.
- [Execution](../../../../docs/architecture/execution.md): how a reconciliation runs.
