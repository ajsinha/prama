<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# Reconciliation and breaks from Python

`client.reconciliation` lists reconciliations and what their last run found, and
issues the period-end certificate. `client.breaks` is the break workbench: each
reconciliation's breaks in the order they should be worked, and the three things
a person does about one — assign it, explain it, accept it.

A reconciliation is a `RECONCILE` control. It runs the way every control runs, and
nothing here runs one. What these namespaces return is what a run recorded: the
latest evidence record, and the break queue the run filled.

## What ran, and what it found

```python
import prama_sdk as prama

client = prama.connect()
listed = client.reconciliation.list()
for item in listed["reconciliations"]:
    latest = item["latest"]                      # None until it has run
    print(item["definition"], latest and latest["verdict"], latest and latest["match_rate"])
```

Each item carries the control (`control_id`, `identity`, `pql`, `status`), the
`definition` its breaks are filed under (`"positions against ledger"`), the latest
result, and `breaks`, a count per state with cleared breaks included. A
reconciliation that ran and cleared everything still appears; an empty queue is not
the same thing as a reconciliation that never ran.

`match_rate` is the share of rows on both sides that found a partner. It is `None`,
not `1.0`, when neither side had rows: a reconciliation over nothing has not
matched anything. `breaks_needing_a_person` is the count the verdict was judged on;
timing differences that clear themselves are not in it.

`listed["unowned_queues"]` names break queues with no RECONCILE control behind
them — a reconciliation since retired, for instance. They are listed so they can be
found and worked.

```python
one = client.reconciliation.get(control_id, history=10)
one["history"]                                   # the last ten results, newest first
```

## The workbench

```python
bench = client.breaks.workbench("positions against ledger")
for row in bench["rows"]:
    print(row["kind"], row["key"], row["difference"], row["because"])
```

Rows are ordered by kind, then age, then key — never by size. A genuine difference
comes before a missing row, which comes before a rounding difference, and timing
differences come last because they clear themselves. Each row carries:

- `because`: the engine's own, deterministic reason for the classification, and
  `normalisation`: what was done to each amount before they were compared. No model
  writes either.
- `age_days`, measured from when the break first appeared. A break re-detected for
  forty days is forty days old.
- `is_configuration`: sign, duplicate and FX breaks, which are usually somebody's
  setup, not the data. `bench["configuration"]` lists their ids.
- `is_stale`: open for thirty days or more. `bench["stale"]` lists them.

`show="all"` adds breaks that have cleared. By default the workbench shows open and
accepted breaks; `cleared_count` says how many have cleared, because "forty cleared
since yesterday" and "nothing changed" leave the same queue length.

## Working a break

```python
client.breaks.assign(break_id, "ops-equities")
client.breaks.explain(break_id, "late booking on the 30th; reverses on the 2nd")
client.breaks.accept(break_id, "known timing item, reverses on the 2nd")
```

Each call returns the break as it now stands, with its trail in `comments`. Every
action appends to the trail; nothing rewrites it. An acceptance needs a reason, and
one without is refused with `prama.ValidationError`. An accepted break stays on the
workbench and stays outstanding: accepting a difference carries it, it does not make
the two sides agree, and the next run still counts it.

These need `break:write` (the `steward` role has it); reading needs `break:read`.
A break from another estate is `prama.NotFoundError`, never a refusal that confirms
it exists.

## The certificate

```python
cert = client.reconciliation.certify("positions against ledger", period_end="2026-09-30")
print(cert["markdown"])
cert["outstanding_total"], cert["accepted_total"], cert["unexplained_total"], cert["content_hash"]
```

A statement of what was outstanding, signed by you, over the queue as it stands and
the match rate the latest run recorded. It names the residue and separates the part
somebody accepted from the part nobody has explained. It is refused when no run has
recorded a match rate. It needs `attestation:sign`, and it is returned, not stored:
keep the document, and the `content_hash` it carries, where the period's close is
filed.

---

<div align="center">
<img src="../assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../../LICENSE">LICENSE</a> and <a href="../../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
