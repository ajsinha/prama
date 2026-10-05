<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Metadata, business context and rules

What each dataset and attribute means to the business, the fields your firm records about them, and
the rules those fields imply. The page is **Estate → Metadata** (`/metadata`): the index finds data
and shows where meaning diverges, and each declared dataset has a page of its own.

## To describe a dataset or attribute

On the dataset's page, write its **business context** (who uses it, for what, and what to watch out
for) and press **Save context**. It is saved as an amendment of the declaration, so earlier versions
are kept, and it is the text that finding data by meaning reads.

## To record metadata fields

1. Install a starter template, or write your own in YAML on the index page (**Save template**):

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

2. On a dataset's page, fill in the fields and press **Save metadata**. Each value is checked against
   its field's kind, and a changed value closes the previous one rather than overwriting it.

A rule's PQL may use `{{ dataset }}` and `{{ attribute }}` (the names), `{{ value }}` (a number),
`{{ text }}` (a quoted string), `{{ values }}` (`('a', 'b')`), `{{ pattern }}` (`/…/`) and
`{{ columns }}` (`a, b`, checked as identifiers). Values only ever reach PQL as literals of their
kind, so metadata cannot change what a rule checks.

## To turn metadata into controls

When a value satisfies a rule's `when`, the rule is rendered into PQL and offered on **Proposals**,
like every control Prama derives: `mandatory` set to *yes* proposes a not-null check,
`allowed_values` an `IN` check, a dataset's `key` a unique-key check. A person accepts it, and it runs.

To write a rule yourself, use **Propose rule** on the dataset's page. It is recorded as proposed, and
another person approves it on **Controls** before it runs.

## To find the dataset fit for a purpose

Describe what you need the data for in the search on the index page (**Find**), or with
`prama metadata ask "convert trade amounts to USD"`. Prama ranks **datasets**, not rows, by how well
their owners' descriptions fit, and names the attributes that best match. The page says which
ranking it used: meaning-based with an `embed` model configured, word-based (BM25) without, and
explained by a `discover` model if one exists. It never reads the data itself, so the better the
owners describe their data, the better it works.

## To see where one meaning is held in several places

The index page (and `prama metadata correlate`) groups attributes bound to the same concept property
or glossary term, and shows:

- **Reference checks** it proposes, when exactly one dataset is keyed by that meaning
  (`CHECK trades.counterparty_lei REFERENCES counterparties.lei`). If nobody owns the meaning, or two
  datasets claim it, nothing is proposed: that is a question, not a check.
- **Held inconsistently**: the same meaning with a different semantic type, sensitivity, CDE mark,
  allowed values or pattern. These are findings for a steward, not controls.

## To see which datasets matter most

Import the warehouse's query history, and the index lists the busiest datasets with the fewest
controls first, and the used-but-undeclared ones separately:

```bash
prama usage import snowflake --query        # prints the export query to run
prama usage import snowflake history.json   # or bigquery / databricks
prama usage priorities
```

Usage orders the work and does nothing else: no quality score reads it.

## To discuss a dataset

Use the **Discussion** section at the foot of a dataset's page: see [Discussion and your queue](/help/queue).

## From the command line

```bash
prama metadata template install data-quality-attribute
prama metadata set trades.account_id mandatory=yes source_system=Murex
prama metadata context trades --text "Executed trades booked by the desks."
prama metadata show trades
prama metadata find "settlement currency"
```

Programs read the same at `GET /api/v1/metadata/{dataset}` and `GET /api/v1/metadata/search?q=…`.

## Go deeper

- [The semantic layer](../../../../docs/architecture/semantic-layer.md#metadata-business-context-and-the-glossary): how metadata becomes proposals, and [how data is found by meaning](../../../../docs/architecture/semantic-layer.md#finding-data-by-meaning).
