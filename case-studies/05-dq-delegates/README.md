# Case study 5 — DQ delegates

<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt;. All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.</sub>

---

Acme Markets has two checks that PQL cannot express. Its engineers write both as **delegates**:
Python classes, named from PQL and judged by Prama.

## Run it

The study is a client of **your** Prama server. It talks to it only through the SDK
(`prama.sdk`), and it does not start a server or a console of its own.

```bash
prama serve                                   # or python run_prama_web.py, if not running already
cd case-studies/05-dq-delegates
python run.py                                 # the server config/application.yaml names
python run.py --config other.yaml             # another server: the one other.yaml describes
python run.py --username ada --password …     # as somebody else (default: the dev admin)
```

Each run creates an estate of its own, named `acme-ops-<timestamp>`, so a rerun starts clean and
earlier evidence stays as it was. The data being checked (a DuckDB catalogue of views over CSV
files) is built under `workspace/`. The server reads it itself, so `case-studies/` must be under
the server's `runs.roots`. The shipped `config/application.yaml` already includes it.

### What the server needs for delegates: nothing beyond that

The delegates reach the server the way a bank's engineers would send them, **uploaded over the
SDK and approved by a second person**:

1. `client.delegates.upload(path)` sends each file. The server vets it in its sandbox before any
   import: the pre-import scan, the determinism and robustness probes, and a one-pass and a
   streaming run. It is then proposed.
2. The uploader tries `client.delegates.approve(...)` and is refused: *the uploader cannot
   approve their own delegate*.
3. The study creates a second administrator (`client.principals.create("reviewer",
   roles=["admin"], password=…)`), who signs in to the run's estate
   (`prama.sdk.connect(..., tenant=<estate slug>)`) and approves it.
4. When a run starts, the server writes each approved upload to `delegates.upload_dir` (default
   `data/delegates`, relative to where the server runs). The file is content-addressed and runs
   only in the sandbox, which re-hashes it before importing it.

No `delegates:` section is needed in the server's configuration for this. The alternative, a
`delegates.paths` directory on the server's own disk, is what an operator would use for
delegates that ship with the installation. It does **not** work for runs at present: see *What
converting to the SDK found*, below.

## The two delegates (`acme_delegates/`)

| Delegate | Counts | Why it is code |
|---|---|---|
| `acme.settlement_cycle` | rows | Settlement is *N business days* after trading, on each market's own calendar: US T+1 since May 2024, EU T+2 on TARGET2 days, UK T+2. |
| `acme.benford_first_digit` | findings | Whether amounts' leading digits follow Benford's law is a property of the whole distribution, tested digit by digit. |

A third file, `rejected/live_fx.py`, fetches FX rates from the internet when it is imported.
Its upload is refused **from its source, before it is imported**, so that download never happens:

```
REFUSED   live_fx.py
          live_fx.py was refused: vetted before import: urllib.request — a network call makes
          a control unreplayable and leaks the data
```

## What is planted

| Dataset | Rows | Defect |
|---|---:|---|
| trade_blotter | 23 | US trades booked T+2 by a desk system never moved to T+1 |
| trade_blotter | 9 | EU trades set to settle on 1 May, a TARGET2 closing day |
| trade_blotter | 4 | settlement date written `31/04/2026` |
| payments_ledger | 350 | invented invoices between 4,000 and 4,990, under a 5,000 approval limit |

`receipts_ledger` carries no defects. It is the control case that shows the Benford test can pass.

## What the run shows

The controls are written as PQL and checked, explained and compiled by the server
(`client.pql.check`, `explain`, `compile`) before they are declared. Γ derives 7, 5 and 4
controls from the three declarations, and the study adds four of its own.

**The same question, asked two ways**, over 1,599 trades:

| Control | Verdict | Violations |
|---|---|---:|
| `SATISFIES EXCEL '=[settlement_date] >= [trade_date]'` | pass | 0 |
| `USING DELEGATE 'acme.settlement_cycle@1'` | **fail** | **36** (23 late, 9 early, 4 unreadable) |

Every planted trade settles after it trades, so the column comparison passes all of them. The
delegate finds exactly the 36 that were planted, and the evidence record names the delegate,
its version and the SHA-256 of the approved upload.

The server's pass covers `trade_blotter` and `receipts_ledger`. It reports **14 controls: 13
pass, 1 fail, 6 on another source**, and the evidence chain (14 records) verifies. The clean
receipts ledger passes the Benford test, with MAD 0.0034.

**The payments ledger, in the PCI zone.** The control plane cannot read it, so the server's run
counts its controls as "on another source" and claims nothing about it. The check belongs on an
agent inside the zone, with its own `delegates:` configuration, so that the rows never leave.
**The SDK cannot drive that agent** (see below), so the study says so and does the one thing the
SDK can do: a **try-out** (`client.delegates.test("acme.benford_first_digit@1", rows,
min_rows=300)`) of the approved delegate in the server's sandbox:

- **The result.** FAIL, with first digits 1 and 4 departing from Benford's law. MAD is 0.0176,
  where Nigrini's nonconformity band starts at 0.015, and 4s make up 17.6% of amounts against
  Benford's 9.7%. These are the same numbers the in-zone agent reported before the conversion.
- **What it is not.** A try-out records **no evidence**, so the 350 invented invoices do not
  appear under FOUND. It also sends the payment rows to the control plane: acceptable for a
  study's synthetic data, and exactly what a real PCI zone forbids.

## What changed in the conversion to the SDK

| | Before (in-process) | After (SDK, against a running server) |
|---|---|---|
| How delegates reached the host | `host_from_config` over `acme_delegates/`, in the study's process | uploaded, vetted in the server's sandbox, approved by a second administrator |
| Settlement cycle | ran as written; the README's 36. At the commit before this one it did **not** run: the in-process host lost its delegates (see below) | **fail, 36 violations**, from the server's run |
| Benford on receipts | as above | **pass, MAD 0.0034** |
| Benford on payments | an in-process `prama.agent.Agent` in `pci-zone`: FAIL, MAD 0.0176, samples kept in the zone | a sandboxed try-out on the server: FAIL, MAD 0.0176, no evidence, rows crossed the boundary |
| "An agent without the delegate cannot take the control" | shown with `prama.agent.fits` | not shown: no API for it |
| The engine's part of the settlement control | `SELECT trade_id, market, trade_date, settlement_date FROM trade_blotter` | `client.pql.compile` gives `SELECT * FROM "trade_blotter"`; a run narrows it to the columns the delegate reads |

## What converting to the SDK found

- **The data-plane agent has no API.** `prama.agent` (`Agent`, `Assignment`, `fits`, residency
  policy) is an in-process library. No HTTP endpoint enrols an agent, assigns it a control, or
  receives its evidence. (`client.agents` covers *steward* agents, a different thing.) So a
  client of the server cannot demonstrate residency, which is the point of section 4b. The
  study reports this rather than reaching past the SDK.
- **Configured delegates are dropped when a run starts.** A run calls `adopt_uploads`, which
  calls `DelegateRegistry.drop_uploads()` to forget retired uploads. That drops every entry
  marked `sandbox_only`. But delegates from `delegates.paths`, admitted through the sandbox
  (`_adopt_vetted`), are also `sandbox_only`. So every configured delegate is removed from the
  host before the controls run, and they error with *the delegate … is not installed on this
  host*. The pre-conversion study, run from the commit before this one, shows exactly that: both
  delegate controls could not run. This is why the converted study uploads its delegates, which
  are adopted afresh on every pass. The fix belongs in `src/prama/delegates/registry.py`:
  `drop_uploads` should drop only entries whose origin is an upload.
- **`pql.compile` cannot know a delegate's columns.** For a `USING DELEGATE` control it returns
  `SELECT *`, while a run fetches only the delegate's `requires`. The compile output is not the
  query that runs.

## Where the verdict comes from

A delegate returns counts. The control's threshold turns them into a verdict, in the same code
that judges every other control. Every evidence record names the delegate, its version and a
hash of its source. Edit the settlement calendar and the hash changes, so later evidence is
visibly produced by a different rule.

See `docs/design/dq-delegates.md` for the design, and the **DQ delegates** guide in the console
Help.
