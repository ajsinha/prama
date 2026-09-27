<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# A tour of the console

The console's navigation follows the order the work runs in: look at the estate, say what it means,
state the controls, deal with what broke, agree the numbers, then report.

| Area | What it is for |
|---|---|
| **Estate** | The map of datasets and how they connect, with gaps: data nobody has declared or controlled. |
| **Declarations** | What a dataset, attribute or concept *means*, in the business's words, with an owner and a version. |
| **Relationships** | Declared and discovered links between datasets. A discovered link is only used once somebody confirms it. |
| **Controls** | Checks written in PQL. The studio parses, type-checks, explains, compiles and previews them. |
| **Proposals** | Controls that were suggested (by a person, a profile or a model) and are waiting for a human to accept or reject them. |
| **Incidents** | Failed controls, grouped for triage. |
| **Reconciliation** | Breaks between two systems that should agree, keyed and explained. |
| **Scorecards** | Quality scores derived from evidence. Nothing here is typed in by hand. |
| **Evidence** | The append-only, hash-chained ledger of every run. |
| **Attestations** | An owner signing that a dataset met its controls over a period. |
| **Reports** | PDF and HTML reports built from the same evidence. |

## Where to start

1. Open **Estate** to see what Prama knows about.
2. Declare a dataset under **Declarations**, or accept a proposal under **Proposals**.
3. Write or accept a control under **Controls**, preview it, and ask an owner to approve it.
4. Once it runs, its verdicts appear under **Evidence**, and failures under **Incidents**.

## Who may do what

What you can open depends on your roles; see [Accounts, roles and sign-in](/help/accounts). A page you
may not use answers **403** rather than hiding, so a missing permission is visible, not mysterious.
