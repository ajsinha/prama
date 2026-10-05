<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# The business glossary

The terms your business uses: what each means, what else it is called, who stewards it, and what it
names in the estate. The page is **Estate → Glossary** (`/glossary`). A term bound to an attribute
carries its meaning into derivation and into finding data by meaning.

## To bring in the glossary you already have

```bash
prama glossary import terms.json --from alation      # /integration/v2/term/ output
prama glossary import assets.json --from collibra    # /rest/2.0/assets, Business Terms
```

Each import lists everything it did **not** bring across, and why: a term with no name, a Collibra
asset that is not a Business Term. Re-importing updates terms rather than duplicating them. A term
whose name or synonym matches a declared concept is bound to it automatically, marked *name match*.

## To bind a term

A term can name a **concept**, a **dataset** or an **attribute** (`dataset.column`). Bind it on the
Glossary page, or:

```bash
prama glossary bind Exposure --concept Exposure
prama glossary bind "Settlement currency" --attribute trades.settle_ccy
```

A term bound to a concept reaches every control derived from that concept.

## To bring in lineage from Manta or Alation

```bash
prama lineage import manta-export.json --from manta
prama lineage import lineage.json --from alation
prama lineage conflicts          # where their lineage and Prama's own parse disagree
```

Imported edges are kept as `imported:<vendor>`, beside Prama's own parse and never replacing it.
Where the two name different sources for one column, **Lineage** lists the disagreement for a
person. An Alation lineage object with several sources *and* several targets does not say which
feeds which, so it is left out rather than guessed.

## Go deeper

- [The semantic layer](../../../../docs/architecture/semantic-layer.md#metadata-business-context-and-the-glossary): what a term binds to.
- [Writing an importer](../../../../docs/developer/importers.md): bringing in another catalogue's glossary or lineage.
