<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# Evidence and assurance from Python

Everything a run leaves behind, and everything built on it: the evidence ledger, the
incidents it implies, the scores derived from it, attestations signed against it, and the
print packs. Six namespaces:

| Namespace | What it is | Scope it needs |
|---|---|---|
| `client.evidence` | The hash-chained ledger: list, verify, compare, anchor, export | `evidence:read` (anchoring: `admin`) |
| `client.incidents` | Controls whose latest record is not a pass, and the discussion on them | `incident:read` (commenting: `comment:write`) |
| `client.scorecards` | Scores per dataset and for the estate, by dimension | `report:read` |
| `client.attestations` | The register, drafts, signing, the attestation pack | `attestation:read` (signing: `attestation:sign`) |
| `client.reports` | The declaration and control packs, as HTML or JSON | `report:read` |
| `client.estate` | Also: export the declared estate as YAML, and diff files against it | `declaration:read` (diff: `declaration:write`) |

The examples use the synchronous client. With `AsyncClient` every call is the same, awaited.

```python
import prama.sdk as prama

client = prama.connect()          # server and credentials from application.yaml
```

Nothing here decides a verdict. The executor recorded it; these calls read it, check the
chain still holds, and package it for someone outside Prama.

## The ledger

```python
failures = client.evidence.list(verdict="fail", since="2026-09-01")["items"]
for record in failures:
    print(record["sequence"], record["control_id"], record["dataset"], record["claim"])

record = client.evidence.get(failures[0]["sequence"])
latest = client.evidence.latest()            # {control_id: its current record}
```

Filters are `control_id`, `dataset`, `verdict`, `run_id`, `since`, `until` (ISO-8601,
inclusive, on `finished_at`), `limit` and `offset`. Records come back newest first. Each
carries its stored hashes and a `claim`: the verdict at the width it was established.
`pass over the rows examined` after an incremental run doesn't mean the dataset passed.

`client.evidence.status()` tells *nothing has run* (`no_runs`) apart from *looked and
found nothing* (`observed`). It also counts runs that started and never reported, whose
controls have no verdict at all. `client.evidence.runs()` and `client.evidence.run(id)`
show executions and the records each one wrote.

### Is the chain intact?

```python
check = client.evidence.verify()
assert check["intact"], check["breaches"]
print(check["records"], check["merkle_root"])
```

Verification reads the hashes **as stored** and recomputes them from the stored content.
A row edited under the database fails with a `content` breach. A record swapped in whole
fails the link check.

### An auditor's bundle

```python
import io, zipfile

zipped = client.evidence.export()            # bytes
zipfile.ZipFile(io.BytesIO(zipped)).extractall("bundle")
```

```bash
python3 scripts/verify_evidence.py bundle/   # exit 0: intact; 1: a check failed
```

The zip holds the same three files `prama evidence export` writes: `manifest.json`,
`evidence.ndjson` and `anchors.json`. The verifier imports nothing from Prama.

The export is **refused** (`ConflictError`) when the stored chain doesn't verify. The
bundle recomputes each record's hashes on the way out, so exporting a tampered chain would
give the auditor a bundle that verifies cleanly and hides the tampering. Investigate the
breaches first. An empty ledger raises `NotFoundError`.

### Anchoring

```python
receipt = client.evidence.anchor()           # needs the admin scope
print(receipt["status"], receipt["authority"], receipt["witnessed_at"])
client.evidence.anchors()                    # every attempt, failures included
```

Anchoring sends the chain head to the time-stamp authority set in `evidence.anchor`.
It's idempotent: an already-anchored head isn't sent again. If the witness can't be
reached, the answer is `status: "failed"` with the reason, not an exception, because the
evidence is already written. With anchoring off it raises `ValidationError` saying so.

### Did the answer move?

```python
diff = client.evidence.compare(original=41)          # against the control's newest record
diff = client.evidence.compare(original=41, replayed=57)
print(diff["cause"], diff["summary"])
```

`cause` says why two records of a control differ: `data_changed`, `control_changed`,
`engine_changed`, `parameters_changed`, `snapshot_not_exact`, `coverage_changed` or
`unexplained`. It's `identical` or `stable` when they don't differ. `escalate` is true when
the cause is one that should never happen.

## Incidents

```python
for incident in client.incidents.list(verdict="fail")["items"]:
    print(incident["control_id"], incident["dataset"], incident["detail"])

one = client.incidents.get(control_id)
print(one["sentence"])                       # the control, as a data owner reads it
print(one["sample"]["description"])          # which failing rows are held, and how many
client.incidents.comment(control_id, "@bo is the upstream feed late again?")
```

An incident is a control whose **latest** record isn't a pass. There's one per control,
not one per run. There's no separate incident record to assign or close: when the control
passes again, the incident goes, and the ledger keeps the history. People work an incident
by discussing it, and a mention reaches that person's queue (`client.comments.queue()`).

`began` is blank when the failure started before the oldest record held. A date there
would really be "the oldest run we still have", which isn't the same thing.

## Scorecards

```python
cards = client.scorecards.list()
for card in cards["scores"]:
    print(card["subject"], round(card["value"], 3), card["coverage"], card["not_run"])
    for part in card["components"]:
        print("  ", part["dimension"], part["description"])

client.scorecards.get("trades")
client.scorecards.estate()
```

Scores come from each control's latest record. The whole ledger would weight an hourly
control sixty times as heavily as a daily one. A control that couldn't run is counted in
`not_run` and lowers `coverage`, rather than scoring as a zero or a one. `decomposed` is
false when some records predate evidence format 1.1 and carry no dimension of their own.

## Attestations

```python
draft = client.attestations.draft(scope="the estate", start="2026-09-01", end="2026-10-01")
print(draft["summary"], draft["coverage"])

signed = client.attestations.sign(
    "Ada Lovelace",
    "I reviewed the estate's controls for September.",
    "2026-09-01", "2026-10-01",
    dispositions={control_id: "Upstream feed corrected on the 3rd; see INC-114."},
)
assert signed["intact"] and signed["sealed"]
open("attestation.html", "wb").write(client.attestations.pack(signed["id"]))
```

The caller doesn't supply the numbers. Coverage, exceptions and the evidence root are
derived from the ledger when the attestation is signed. The signer's identity is the key's
principal. A correction is a new signature with `supersedes=` and `supersedes_because=`.
The earlier one leaves `list()` and stays in `history(scope)`.

Periods compare against `finished_at` as text, so an `end` of `2026-09-30` excludes records
finished *during* the 30th. To include a whole day, end the period on the day after.

## Reports

```python
client.reports.list()
open("declarations.html", "wb").write(client.reports.declarations())
content = client.reports.controls(as_json=True)      # what the pack is rendered from
```

The packs are standalone HTML with their styles inlined. To get a PDF, print one from a
browser: Prama has no server-side PDF renderer.

## The estate as files

```python
from pathlib import Path

files = client.estate.export()["files"]              # {"datasets/trades.yaml": "...", ...}
for path, text in files.items():
    target = Path("prama") / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)

on_disk = {str(p.relative_to("prama")): p.read_text() for p in Path("prama").rglob("*.yaml")}
drift = client.estate.diff(on_disk)
print(drift["summary"])
```

These are the same operations as `prama estate export` and `prama estate diff`. The diff
reports disagreement in both directions and never resolves it. Writing files back into the
store isn't an operation: that's a governed change and goes through approval.
`client.estate.maturity()` scores how much of the estate has been described.
