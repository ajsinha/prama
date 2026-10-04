<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# A tour of the console

The top bar has four menus, in the order the work runs: **Estate** (see the data and say what it
means), **Controls** (state them and run them), **Assurance** (what broke, and what held) and **Help**.
An administrator also sees **Admin**. Each menu opens a panel of titled columns, with a line under every
page saying what it is for. To the right: a search box that finds data by its business meaning, your
queue, row density, the theme, and your user menu.

| Menu | Page | What it is for |
|---|---|---|
| Estate | **Estate map** | The map of datasets and how they connect, with gaps: data nobody has declared or controlled. |
| Estate | **Lineage** | Where a column comes from and what a defect in it reaches, parsed from ETL SQL. |
| Estate | **Declarations** | What a dataset, attribute or concept *means*, in the business's words, with an owner and a version. |
| Estate | **Relationships** | Declared and discovered links between datasets. A discovered link is only used once somebody confirms it. |
| Estate | **Metadata**, **Glossary** | Business context and terms; the rules they imply go to Proposals. |
| Controls | **Controls** | Checks written in PQL. The studio parses, type-checks, explains, compiles and previews them. |
| Controls | **Proposals** | Controls that were suggested (by a person, a profile or a model) and are waiting for a human to accept or reject them. |
| Controls | **Rule builder** | A control from a form, for somebody who does not write PQL. |
| Controls | **Schedule**, **Delegates**, **Code intake** | When suites run; admitted Python checks; controls read out of existing DQ code. |
| Assurance | **Incidents** | Failed controls, grouped for triage. |
| Assurance | **Reconciliation** | Breaks between two systems that should agree, keyed and explained. |
| Assurance | **Scorecards** | Quality scores derived from evidence. Nothing here is typed in by hand. |
| Assurance | **Evidence** | The append-only, hash-chained ledger of every run. |
| Assurance | **Attestations** | An owner signing that a dataset met its controls over a period. |
| Assurance | **Reports** | PDF and HTML reports built from the same evidence. |

## Where to start

1. Open **Estate → Estate map** to see what Prama knows about.
2. Declare a dataset under **Declarations**, or accept a proposal under **Proposals**.
3. Write or accept a control under **Controls**, preview it, and ask an owner to approve it.
4. Once it runs, its verdicts appear under **Evidence**, and failures under **Incidents**.

## Who may do what

What you can open depends on your roles; see [Accounts, roles and sign-in](/help/accounts). A page you
may not use answers **403** rather than hiding, so a missing permission is visible, not mysterious.

## Go deeper

- [How Prama fits together](../../../../docs/architecture/README.md): every component, and the life of a control end to end.
- [Developer guides](../../../../docs/developer/README.md): extending Prama: connectors, functions, providers and the rest.
