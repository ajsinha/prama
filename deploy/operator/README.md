<!--
Prama — the Kubernetes Operator.
Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary. No licence is granted except by separate written agreement.
-->

# The Operator (W10.6)

An operator is two things wearing one name: **a control loop** that talks to
Kubernetes, and **a decision** about what should happen. They are built and
verified separately here, because only one of them can be.

| | Status |
|---|---|
| `PramaEstate` CRD — schema, required fields, printer columns | ✅ written; validates as OpenAPI v3 |
| The **reconciliation decision** — `prama.integrate.operator` | ✅ built and tested (21 tests) |
| The **control loop** — watch, apply, update status | ❌ **not built** |
| Installed and reconciling on a cluster | ❌ **not verified** — no cluster available |

The decision is the half where an operator is dangerous, so it is the half that
exists. The loop is plumbing: it watches, calls `plan()`, applies what the plan
says, and writes the conditions the plan already computes.

---

## What the decision refuses to do

Each of these is something the *obvious* reconciler does, and a bank would not
accept any of them.

**Drift is reported, never resolved.** The Kubernetes instinct is that desired
state wins. Applied here it silently overwrites a declaration a business owner
made in the console — the one place this product insists a human states meaning.
A dataset the operator did not declare, which now differs, becomes a
`CONFLICT` on the resource's status for somebody to settle. The operator will
amend what it declared itself, because its own earlier output is not a person's
statement.

**Nothing is ever deleted.** A dataset dropped from a manifest is `ORPHANED` and
left alone. A manifest that stopped mentioning something is not the business
retiring it — and deleting would take that dataset's controls and its evidence
with it. There is no delete verb in the vocabulary to reach for.

**A declaration is not an approval.** The CRD carries no field that could
approve a control, suppress one, or set a verdict — a test asserts those words
do not appear in it. A cluster admin with `kubectl` must not be able to make a
control pass; that is exactly what an estate's approval workflow exists to
prevent, and a CRD field would route around it entirely.

**A partial reconcile is not `Ready`.** Twelve of forty datasets applied leaves
twenty-eight in a state nobody knows. "Planned but not applied" is also its own
condition, distinct from "applied and everything succeeded" — conflating them
reports `Ready` on a reconcile that never ran.

---

## What the loop would have to add

```
watch PramaEstate
  → read the estate from the store
  → plan(spec, stored)          # already built and tested
  → apply plan.writes
  → status.conditions = plan.conditions(generation, applied)
```

Nothing in that sequence is a decision; every decision is already made and
tested. What it needs is a cluster to run against, and an operator whose
reconcile loop has never run is not one anybody should install.

---

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
