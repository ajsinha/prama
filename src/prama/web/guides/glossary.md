<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# The business glossary

The **Glossary** page (main navigation) lists the terms your business uses: what each one means,
what else it is called, who stewards it, and what it names in the estate.

## Bringing in the glossary you already have

```bash
prama glossary import terms.json --from alation      # /integration/v2/term/ output
prama glossary import assets.json --from collibra    # /rest/2.0/assets, Business Terms
```

Each import lists everything it did **not** bring across, and why. A term with no name is left
out. A Collibra asset that is not a Business Term is left out. Nothing is guessed.
Re-importing updates terms rather than duplicating them. A term whose name or synonym matches a
declared concept is bound to that concept automatically, and the binding is marked *name match*.

## Binding a term

A term can name a **concept**, a **dataset** or an **attribute** (`dataset.column`). Bind it on
the Glossary page or with `prama glossary bind Exposure --concept Exposure`. A term bound to a
concept reaches every control derived from that concept.

## Lineage from Manta or Alation

```bash
prama lineage import manta-export.json --from manta
prama lineage import lineage.json --from alation
prama lineage conflicts          # where their lineage and Prama's own parse disagree
```

Imported edges are stored as `imported:<vendor>`, beside Prama's own parse and never replacing
it. When the two name different sources for the same column, the Lineage page lists the
disagreement so that a person can look. An Alation lineage object with several sources *and*
several targets does not say which feeds which, so it is left out rather than guessed.
