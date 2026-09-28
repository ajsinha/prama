# Case study 7 — governance from metadata

<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt;. All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.</sub>

---

Three datasets (customers, accounts and payments) are declared with **no quality rules at all**:
names and descriptions only. Their owners then do what owners do in a catalogue:

- they write the **business context** of each dataset;
- they fill in **metadata fields**: mandatory, unique, allowed values, minimum and key;
- they bind two columns to the **glossary term** *LEI*.

Every control that then runs came from that metadata, or from Prama noticing that two columns
mean the same thing. **Not one line of PQL is written by hand.** At the end, a question in plain
words finds the dataset fit for a purpose.

```bash
cd case-studies/07-metadata-governance
python run.py                 # build, run, and serve the console on :8807
python run.py --no-serve      # build and run, then stop
```

## What the owners say

| On | Metadata |
|---|---|
| `customers.segment` | allowed values `RETAIL, SME, CORPORATE`; mandatory |
| `customers.lei` | mandatory; unique; not PII |
| `accounts.customer_lei` | mandatory; PII |
| `payments.amount` | minimum `0`; mandatory |
| `customers`, `accounts` | key `customer_id`, `account_id`; source system |

Both `customers.lei` and `accounts.customer_lei` are bound to the glossary term **LEI**.

## What that implies

Each field of the starter template `data-quality-attribute` carries a rule, so the values above
propose their checks. For example:

```pql
CHECK customers.segment IN ('RETAIL', 'SME', 'CORPORATE') DIMENSION validity
CHECK payments.amount >= 0 DIMENSION validity
CHECK accounts.customer_lei IS NOT NULL DIMENSION completeness
```

**Correlation** adds one more check. Both LEI columns mean the same thing, and `customers.lei` is
declared unique, so customers own that meaning:

```pql
CHECK accounts.customer_lei REFERENCES customers.lei DIMENSION integrity
```

It also reports a **"held inconsistently"** finding: the same identifier is marked PII in one
dataset and not in the other. That is a finding for a steward, not a check, because which side is
right is a business decision.

A reviewer accepts the proposals, and they run.

## What is planted, and what is found

| Planted | Rows | Found by | Result |
|---|---:|---|---|
| Segment `'SME '` with a trailing space | 6 | allowed values | **6 of 40** |
| Account with no customer LEI | 4 | mandatory | **4 of 200** |
| Account owned by an LEI no customer has | 3 | the correlated reference | **7 of 200** |
| Negative payment amount | 5 | minimum | **5 of 1,200** |

The reference check counts **7**: the 3 orphan LEIs and the 4 accounts with no LEI at all. Under
Prama's default, an unknown (null) value counts as a violation, because an account that names
nobody does not reference a customer. Write `TREAT UNKNOWN AS PASS` on the check if nulls should
be left to the mandatory check alone.

## Which dataset is fit for a purpose?

The questions are answered from the owners' own descriptions, not from the data:

- *"who is the customer and where are they registered, for sanctions screening"* returns
  **Customers**, matching `legal_name`, `customer_id` and `lei`.
- *"outgoing payment amounts"* returns **Payments**, matching `payment_id` and `amount`.

The run uses word relevance (BM25). With a model configured for the purpose `embed`, the same
question is answered by meaning.

## Files

| File | What it is |
|---|---|
| `run.py` | Builds the warehouse, declares the estate, applies the owners' metadata, runs |
| `workspace/warehouse.db` | Customers, accounts and payments: the data being checked |
