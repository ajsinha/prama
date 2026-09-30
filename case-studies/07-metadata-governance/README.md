# Case study 7 — governance from metadata

<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt;. All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.</sub>

---

Three datasets (customers, accounts and payments) are declared with **no quality rules at all**:
names and descriptions only. Their owners then do what owners do in a catalogue:

- they write the **business context** of each dataset;
- they fill in **metadata fields**: mandatory, unique, allowed values, minimum and key;
- they bind two columns to the **glossary term** *LEI*, which comes from the bank's catalogue
  (an Alation export, imported).

Every control that then runs came from that metadata, or from Prama noticing that two columns
mean the same thing. **Not one line of PQL is written by hand.** At the end, a question in plain
words finds the dataset fit for a purpose.

## Run it

The study is a client of **your** Prama. It talks to the server `config/application.yaml`
describes, through the SDK (`prama_sdk`), and starts no server of its own. Start Prama first
(`prama serve`), then:

```bash
cd case-studies/07-metadata-governance
python run.py                                  # the server config/application.yaml names
python run.py --config /path/to/other.yaml     # another server
python run.py --username ada --password …      # as somebody else (default: the dev admin)
```

The server reads the warehouse itself, so `case-studies/` must be under its `runs.roots` (the
shipped configuration has it). Each run creates an estate of its own, named with the time it
started (`acme-retail-YYYYMMDD-HHMMSS`), so a rerun starts clean and earlier evidence stays. At
the end the run prints where to look in the console you already have open.

Everything the owners do goes through the SDK: `client.metadata.install_starter`, `set_context`
and `set`; `client.glossary.import_export` and `bind`; `client.metadata.proposals` and
`correlation` for what that implies; `client.proposals.accept` for the reviewer; and
`client.metadata.ask` for the question at the end.

## What the owners say

| On | Metadata |
|---|---|
| `customers.segment` | allowed values `RETAIL, SME, CORPORATE`; mandatory |
| `customers.lei` | mandatory; unique; not PII |
| `accounts.customer_lei` | mandatory; PII |
| `payments.amount` | minimum `0`; mandatory |
| `customers`, `accounts` | key `customer_id`, `account_id`; source system |

Both `customers.lei` and `accounts.customer_lei` are bound to the glossary term **LEI**. The term
arrives the way a bank's terms usually do, from its catalogue: the study imports a one-term Alation
export (`client.glossary.import_export("alation", …)`). The API has no call that adds a single term
by hand. Import is the only way a term enters the glossary, and the study says so rather than
reaching past the SDK.

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

A reviewer accepts the proposals, and they run: 10 controls, all active.

The run then reads the metadata queue back rather than assuming it emptied, and it has not:

```
10 accepted and active; the metadata queue still lists 9, of which 9 are already active controls.
The proposal queue lists 15, of which 9 are already active controls.
  waiting  CHECK accounts.account_id IS NOT NULL   (grain.completeness)
  ...      (six in all: the declared grain of each dataset, not null and unique)
! The queue re-offers accepted proposals: it compares a hash of the proposed
  text with the stored control's hash of its rendered form, and they never match.
```

- **Six proposals come from the declared grain (Γ).** The study runs only what the metadata
  implies, so it leaves them for a reviewer and prints them.
- **Nine proposals are already active.** They are the nine metadata proposals, listed again on
  both `client.metadata.proposals()` and the proposal queue (`client.proposals.list()`). This is
  a defect in Prama, found by this study and not yet fixed.

`GET /metadata/proposals` drops a proposal once a control with its identity has the same content
hash, but the two hashes are computed differently:

- The proposed text is hashed with SHA-256.
- The stored control is hashed from its rendered form, with a different function. For example,
  `CHECK customers.lei IS NOT NULL\n  SEVERITY major\n  DIMENSION completeness`.

The hashes never match, so a reviewer is asked again about every metadata proposal they have
already accepted. The correlated reference is not affected, because the queue drops it by
identity.

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

The question is asked with `client.metadata.ask`. With no model configured, the answer is ranked
by word relevance (BM25), and the run prints `ranked by relevance`. With a model configured for the
purpose `embed`, the same question is answered by meaning. With a `discover` model, the candidates
are also re-ranked and explained, and the run prints `ranked by model`.

## Files

| File | What it is |
|---|---|
| `run.py` | Builds the warehouse, then declares the estate, applies the owners' metadata and runs it, through the SDK |
| `workspace/warehouse.db` | Customers, accounts and payments: the data being checked |
