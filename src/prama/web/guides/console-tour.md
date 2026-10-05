<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# A tour of the console

Where everything is. The top bar has four menus, in the order the work runs: **Estate** (see the data
and say what it means), **Controls** (state them and run them), **Assurance** (what broke, and what
held) and **Help**; an administrator also sees **Admin**. Each menu opens a panel of titled columns
with a line under every page saying what it is for. To the right are a search box that finds data by
its business meaning, your queue, **About this page** (the question mark), row density, the theme, and
your user menu.

| Menu | Page | What it is for |
|---|---|---|
| Estate | **Estate map** | Every dataset and how it connects, with the gaps: data nobody has declared or controlled. |
| Estate | **Lineage** | Where a column comes from and what a defect in it reaches. [Guide](/help/lineage). |
| Estate | **Declarations** | What a dataset *means*, in the business's words, with an owner and a version. |
| Estate | **Relationships** | Keys that join datasets. A discovered link is used only once somebody confirms it. |
| Estate | **Metadata**, **Glossary** | Business context, your own fields and terms; the rules they imply go to Proposals. [Guide](/help/metadata). |
| Controls | **Controls** | Checks written in PQL; the studio parses, type-checks, explains, compiles and previews them. |
| Controls | **Rule builder** | A control from a form, for somebody who does not write PQL. |
| Controls | **Proposals** | Controls suggested by a person, a profile, metadata, lineage or a model, waiting for a human. |
| Controls | **Schedule** | When each suite runs, and the last run. |
| Controls | **Delegates** | Python checks admitted to run as controls. [Guide](/help/delegates). |
| Controls | **Code intake** | Application code, read for its lineage. [Guide](/help/code). |
| Assurance | **Incidents** | Failed controls, grouped, owned and worked. |
| Assurance | **Reconciliation** | Breaks between two systems that should agree, keyed and explained. |
| Assurance | **Scorecards** | Quality by dimension, derived from evidence; nothing is typed in by hand. |
| Assurance | **Evidence** | The append-only, hash-chained ledger of every verdict. |
| Assurance | **Attestations** | An owner signing for what the evidence shows over a period. |
| Assurance | **Reports** | PDF and HTML reports built from the same evidence. |
| Admin | **People & roles**, **All API keys** | Who can sign in, and every key. [Guide](/help/accounts). |
| Admin | **Models**, **Agents** | Language models and steward agents. [Models](/help/models), [Agents](/help/agents). |

## To get from nothing to a running control

1. Open **Estate → Estate map** to see what Prama knows about.
2. Declare a dataset under **Declarations**, or accept a proposal under **Proposals**.
3. Write or accept a control under **Controls** and preview it. At Tier 1, somebody other than its
   author activates it.
4. Once it runs, its verdicts appear under **Evidence**, and failures under **Incidents**.

An empty console has nothing to report because nothing has run; a case study (**Help → Case
studies**) fills it with a realistic estate.

## To find out what a page is for

Press **About this page** (the question mark in the top bar): what the page shows, what to know before
using it, and which permission it needs. It links to the guide that is the full account.

## What you may open

That depends on your roles; see [Accounts, roles and sign-in](/help/accounts). A page you may not use
answers **403** rather than hiding, so a missing permission is visible, not mysterious.

## Go deeper

- [How Prama fits together](../../../../docs/architecture/README.md): every component, and the life of a control end to end.
- [Developer guides](../../../../docs/developer/README.md): extending Prama: connectors, functions, providers and the rest.
