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
