<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Declaring the estate

Everything in Prama starts from what a business owner says about their data. You never write SQL
here: you answer questions about a dataset, and Prama derives the controls from your answers.

## Declare a dataset

**Estate → Declarations → Declare a dataset.** The form asks what an owner would be asked:

| Question | What it becomes |
|---|---|
| *What is it called?* · *What is it?* · *What is it used for?* | The dataset's name and meaning, shown everywhere it appears |
| *What kind of thing is it?* | Its shape: a table, a feed, a report |
| *What does one row represent?* · *…and which attributes are those?* | Its **grain**: the columns that identify one row, and so a uniqueness control |
| *How much does a defect matter?* | Its **tier**, from 1 (regulatory) to 4 |

The tier decides who must agree. A **Tier 1** declaration is held until somebody other than its
author approves it; **Tier 2** waits for a reviewer; **Tier 3 and 4** take effect at once.

Then add its attributes on the dataset's page, marking the **critical data elements**: they carry
the strictest controls.

## Relate two datasets

**Estate → Relationships → Declare a relationship**, or switch on **Relate two datasets** on the
estate map. Say which two datasets, how many to how many, which columns line them up, and which
value should agree (with a tolerance, and a currency where it matters). A *reconciles-with*
relationship becomes a reconciliation; the defects it finds are ones neither dataset could show
alone.

Relationships Prama proposes wait on the same page for **Confirm** or **Reject**; the controls
derived from them are held until they are confirmed.

## What you get back

- **Proposals**: the controls your declarations imply, waiting for you to accept them
  ([Working with controls](controls.md)).
- **Coverage gaps**: what the estate still cannot answer for. The four counts on the estate map
  show the size of it.

From Python, the same thing is `client.datasets.declare(...)`, `client.datasets.add_attribute(...)`
and `client.derive.dataset(...)`.

## Go deeper

- [The semantic layer](../../../../docs/architecture/semantic-layer.md): what a declaration is, and where it is kept.
- [The Python SDK](../../../../docs/sdk/README.md): declaring an estate from a script.
- [The business semantic layer](../../../../docs/corpus/03-business-semantic-layer.md): why the business, not the warehouse, is the starting point.
