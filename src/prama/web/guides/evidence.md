<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Evidence, incidents and sign-off

Every verdict a control produces is recorded in the evidence ledger, chained to the one before it.
Everything on these pages is read from that ledger, never typed in.

## What is wrong now

**Assurance → Incidents** has one row per failing control, not one per run. Open one to see what
the control says, its PQL, the rows that failed, its history, and what feeds the data upstream,
from the lineage store.

## How good is it

**Assurance → Scorecards** gives a score per dataset with **How this was derived**: computed from
the latest verdicts, weighted by criticality. A dataset with no evidence has no score, not a good
one.

## Is the record intact

**Assurance → Evidence** recomputes the chain when it opens: **chain verified**, its head, and the
Merkle root that stands for all of it. To let somebody check it without trusting Prama:

```bash
prama evidence export bundle/                 # records and anchor receipts
python3 scripts/verify_evidence.py bundle/    # standard library only
prama evidence anchor                         # time-stamp the chain head outside Prama
```

## Signing off

**Assurance → Attestations → Sign an attestation** shows *what the evidence says* before anybody signs: the
coverage and verdicts behind the statement. Say *what you are attesting to* and *who is signing*,
then **Sign it**. The signed attestation records whether it is still intact, and its **pack** is
the artefact that leaves the building.

**Assurance → Reports** has the two packs an auditor asks for: the **declaration pack** (what the
business says its data is) and the **control pack** (every control, why it exists, and the SQL it
becomes).

## Go deeper

- [Evidence and assurance](../../../../docs/architecture/evidence-and-assurance.md): the ledger, scores, incidents and alerts.
- [SDK: evidence and assurance](../../../../docs/sdk/evidence.md): the same, from Python.
- [Security, governance and compliance](../../../../docs/corpus/13-security-governance-compliance.md): why the ledger is built this way.
