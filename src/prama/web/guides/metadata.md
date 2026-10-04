<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Metadata, business context and rules

Every declared dataset has a page under **Metadata** (main navigation). A dataset can be a
database table, a feed or anything else you have declared. Its page gathers three things for the
dataset and for each of its attributes.

## Business context

What the dataset or the attribute **means to the business**, in the owner's words: who uses it,
for what, and what to watch out for. It is saved as an amendment of the declaration, so every
earlier version is kept. It is also the text the **Find data** search reads. Later, an assistant
will read it to find data of interest.

## Metadata fields: yours, typed, and versioned

A **template** is a set of fields for datasets or for attributes, such as source system, retention
class, golden source, allowed values or report line. Install the starters or write your own in
YAML:

```yaml
name: finance
applies_to: attribute
fields:
  - name: report_line
    kind: text          # text, longtext, number, flag, choice, list, day, columns
  - name: mandatory
    kind: flag
    rules:
      - when: "true"
        pql: "CHECK {{ dataset }}.{{ attribute }} IS NOT NULL"
```

Each value is checked against its field's kind. A changed value closes the previous one rather
than overwriting it, so the history is kept.

## Rules that grow from metadata

A field can carry **rules**. Once a value satisfies a rule's `when`, the rule is rendered into PQL
and offered on the **Proposals** page, like every control Prama derives. A person accepts it, and
it runs. Setting `mandatory` to *yes* proposes a not-null check. `allowed_values` proposes an
`IN` check, and a dataset's `key` proposes a unique-key check.

Values reach PQL only as literals of their kind. A value such as `x') OR (1=1` stays a string
inside quotes, so metadata cannot change what a rule checks.

| Placeholder | Becomes |
|---|---|
| `{{ dataset }}`, `{{ attribute }}` | the names |
| `{{ value }}` | a number (number fields) |
| `{{ text }}` | a quoted string |
| `{{ values }}` | `('a', 'b')` (list fields) |
| `{{ pattern }}` | `/…/` |
| `{{ columns }}` | `a, b`, checked as identifiers (columns fields) |

## Which dataset is fit for a purpose

Describe what you need the data for, on the Metadata page or with `prama metadata ask "…"`, for
example *"convert trade amounts to USD"*. Prama ranks the **datasets** by how well they fit.

- **Each dataset's profile is searched.** That is its name, description, purpose, business
  context, metadata, glossary terms, and every attribute's name, definition and context. The
  better the owners describe their data, the better this works.
- **Embeddings.** With a model configured for the purpose **`embed`** (Models page; for example
  `nomic-embed-text` on Ollama), the search matches by meaning, so "amount at risk" can find
  "exposure". Profiles are embedded once and again only when they change.
- **Relevance (BM25).** Without an embedding model, a deterministic word-based ranking is used.
  The page always says which ranking was used.
- **Evidence.** Each result names the attributes that best match your purpose.
- **Explanation.** With a model configured for **`discover`**, the best candidates are also
  explained and re-ordered. That model can only choose among real datasets.

This searches what the data **is**, as its owners describe it. It never reads the data itself.

## Same meaning, across datasets

When two attributes in different datasets are bound to the same **concept property** or the
same **glossary term**, Prama treats them as the same thing. The Metadata page and
`prama metadata correlate` show three things:

- **The groups:** which attributes share a meaning, and the signal that says so. A shared
  semantic type, such as two currency columns, groups them for consistency only, because every
  table has a currency.
- **Reference checks.** When exactly one dataset is keyed by that meaning, every other member
  should reference it: `CHECK trades.counterparty_lei REFERENCES counterparties.lei`. The check is
  proposed on the Proposals page. If nobody owns the meaning, or two datasets claim it, no check
  is proposed: that is a question, not a check.
- **Held inconsistently:** the same meaning with a different semantic type, sensitivity, CDE
  mark, allowed values or pattern, or described in one place but not another. These are findings
  for a steward, not controls, because which side is right is a business decision.

## Writing a rule directly

On the dataset's page, write a rule in PQL about the dataset or any attribute. It is recorded as
**proposed**, and another person approves it on **Controls** before it runs.

## From the command line

```bash
prama metadata template install data-quality-attribute
prama metadata set trades.account_id mandatory=yes source_system=Murex
prama metadata context trades --text "Executed trades booked by the desks."
prama metadata show trades
prama metadata find "settlement currency"
```

The same information is available to programs at `GET /api/v1/metadata/{dataset}` and
`GET /api/v1/metadata/search?q=…`.

## Most used, least controlled

Import the warehouse's query history, and the Metadata page lists the busiest datasets with the
fewest controls first. Datasets that are used but not declared are listed separately:

```bash
prama usage import snowflake --query        # prints the export query to run
prama usage import snowflake history.json   # or bigquery / databricks
prama usage priorities
```

Usage orders the work and does nothing else. No quality score reads it, and a test holds that:
a popular dataset is not a better one.

## Go deeper

- [The semantic layer](../../../../docs/architecture/semantic-layer.md#metadata-business-context-and-the-glossary): how metadata becomes proposals, and how data is found by meaning.
