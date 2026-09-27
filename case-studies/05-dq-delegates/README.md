# Case study 5 — DQ delegates

<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt;. All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.</sub>

---

Acme Markets has two checks that PQL cannot express. Its engineers write both as **delegates**:
Python classes, named from PQL and judged by Prama.

```bash
python run.py                 # build, run, serve the console on :8805
python run.py --no-serve      # build, run, print, stop
```

## The two delegates (`acme_delegates/`)

| Delegate | Counts | Why it is code |
|---|---|---|
| `acme.settlement_cycle` | rows | Settlement is *N business days* after trading, on each market's own calendar: US T+1 since May 2024, EU T+2 on TARGET2 days, UK T+2. |
| `acme.benford_first_digit` | findings | Whether amounts' leading digits follow Benford's law is a property of the whole distribution, tested digit by digit. |

A third file, `rejected/live_fx.py`, fetches FX rates from the internet when it is imported.
Prama refuses it **from its source, before importing it**, so that download never happens.

## What is planted

| Dataset | Rows | Defect |
|---|---:|---|
| trade_blotter | 23 | US trades booked T+2 by a desk system never moved to T+1 |
| trade_blotter | 9 | EU trades set to settle on 1 May, a TARGET2 closing day |
| trade_blotter | 4 | settlement date written `31/04/2026` |
| payments_ledger | 350 | invented invoices between 4,000 and 4,990, under a 5,000 approval limit |

`receipts_ledger` carries no defects. It is the control case that shows the Benford test can pass.

## What the run shows

**The same question, asked two ways**, over 1,599 trades:

| Control | Verdict | Violations |
|---|---|---:|
| `SATISFIES EXCEL '=[settlement_date] >= [trade_date]'` | pass | 0 |
| `USING DELEGATE 'acme.settlement_cycle@1'` | **fail** | **36** (23 late, 9 early, 4 unreadable) |

Every planted trade settles after it trades, so the column comparison passes all of them. The
delegate finds exactly the 36 that were planted.

**On a remote agent.** The payments ledger lives in a PCI zone that the control plane cannot
reach, and the run summary counts its controls as "on another source".

- **Without the delegate.** An agent in `eu-frankfurt` that has no delegates configured is
  reported as unable to take the control, with the reason and the remedy.
- **With it.** The agent in `pci-zone` has its own `delegates:` configuration. It advertises
  `acme.benford_first_digit@1` and runs the check beside the data.
- **The result.** FAIL, with first digits 1 and 4 departing from Benford's law. MAD is 0.0176,
  where Nigrini's nonconformity band starts at 0.015, and 4s make up 17.6% of amounts against
  Benford's 9.7%.
- **Where the rows go.** Ten example payments are kept in the zone, and none are sent to the
  control plane.

The clean receipts ledger passes the same test, with MAD 0.0034.

## Where the verdict comes from

A delegate returns counts. The control's threshold turns them into a verdict, in the same code
that judges every other control. Every evidence record names the delegate, its version and a
hash of its source. Edit the settlement calendar and the hash changes, so later evidence is
visibly produced by a different rule.

See `docs/design/dq-delegates.md` for the design, and the **DQ delegates** guide in the console
Help.
