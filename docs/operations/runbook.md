<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# Runbook

What to do when Prama is running and something is wrong. Written for whoever is
on call, which means: the answer first, the reasoning after it.

A note on what this product does when it fails. Prama's whole thesis is that a
control's verdict must be defensible, so almost every failure mode here is a
**refusal** rather than a wrong answer. That is deliberate, and it changes the
shape of an incident: the common page is "Prama will not do something", not
"Prama did something wrong". A refusal with a reason is working as designed even
at three in the morning.

---

## 1. It will not start

### `security.session_secret is empty`

**Working as designed.** A fresh clone refuses to boot rather than starting with
a signing key that is in everybody's Git history.

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Put it in `config/application.local.yaml`, which is git-ignored:

```yaml
security:
  session_secret: "the value you just generated"
```

Or set `PRAMA_SECURITY__SESSION_SECRET` in the environment. `run_prama_web.py
--init-secret` does both steps for a development machine.

**Do not** put it in `config/application.yaml`. That file is tracked, and the
pre-commit hook refuses a non-empty secret in it.

### `the live schema has drifted`

`prama db verify` compares the database against `schema/<dialect>.sql` and fails
loudly rather than repairing anything. **There are no migrations in this
product**, by design: a schema that silently changed under running controls is
how evidence stops meaning what it said.

The message names what differs. Decide which is right — the file or the database
— and make the other match deliberately. `prama db init` applies the schema file
idempotently and will not drop or alter an existing column.

### The interpreter is missing

The venv is built from a standalone CPython under `~/.local/share/uv/python/`,
not from `/usr/bin`. An OS upgrade that removes the system Python does not touch
it. If the venv is broken anyway:

```bash
uv python install 3.13
uv venv --python 3.13
uv pip install -e ".[dev,serve,postgres,fast,audit,sso,kafka,rest]"
```

---

## 2. Controls are failing that should not be

### Everything on one dataset went red at once

Look at the **source**, not the controls. Forty controls failing together is
almost always one upstream event: a feed that did not arrive, a schema change, a
truncated load. `prama connect health <source>` and the dataset's arrival
control answer this faster than reading forty failures.

### A control fails and the data looks right

Check whether the verdict is `fail` or **`not_established`**. They are different
and Prama keeps them apart on purpose:

| Verdict | Meaning | What to do |
|---|---|---|
| `pass` | The control ran and found nothing | — |
| `fail` | The control ran and found violations | Triage the exceptions |
| `not_established` | The control could not reach a verdict | Fix the *control's* inputs, not the data |
| `error` | The run itself failed | Look at the engine, the connection, the plan |

`not_established` is the one people misread. A screen that could not run, a
sample with no rows, a lower bound of zero that was never confirmed — none of
those is a pass, and none is a data defect.

### A control passes and the data is wrong

Two likely causes, in order.

**The control is narrower than you think.** `prama control explain <file>` prints
each control as a sentence. Read it aloud; most of these are a `WHERE` clause
nobody remembered.

**Unknowns are being tolerated.** Prama's default is that an unknown counts as a
violation. If the control says `TREAT UNKNOWN AS PASS`, it was told not to care,
and that phrase is in the control's text precisely so this conversation is short.

---

## 3. Evidence and audit

### An auditor wants to verify a bundle

They do not need Prama, and that is the point.

```bash
python3 scripts/verify_evidence.py /path/to/bundle
```

It imports nothing from this product and nothing outside the standard library.
Exit **0** every check passed, **1** a check failed, **2** the bundle could not be
read — the last two are different findings and the third code exists so a script
can tell a broken transfer from a broken claim.

**What a green result does not mean:** the records have not been altered since
they were written. It does not say they were right when they were written. A
false record, honestly written and correctly chained, verifies exactly like a
true one.

### The chain does not verify

The script names which record and which check. Then:

- **Content hash wrong on one record** — that record was edited after the fact.
- **Link wrong** — a record was inserted, removed or reordered.
- **Manifest count wrong** — the file is truncated. This is what archives
  actually suffer, and the remaining chain is perfectly valid without it.
- **Merkle root wrong** — the manifest does not describe these records.

A tombstoned record is not a failure: its content was erased under a right-to-
erasure request and only its place in the chain can be checked. The script says
so explicitly rather than counting it as a pass.

---

## 4. Streaming and in-flight enforcement

### The pipeline stopped

Almost certainly a **full dead letter**, and stopping is correct. A pipeline that
kept going would be dropping messages to enforce a rule about data quality,
which is the worst trade in the product.

The report says how far it got. Offsets are committed only through the last
message that was actually enforced, so the broker redelivers the rest — nothing
is lost, and restarting after draining the dead letter resumes exactly there.

### Messages are being enforced twice

Expected, and stated: this is **at-least-once**. Committing after enforcement
means a crash between the two replays the batch. Duplicate evidence is a
reconciliation problem; lost data is not one anybody can solve afterwards.
Nothing here claims exactly-once, because without a transaction spanning the
broker *and* the dead letter nothing can deliver it.

### The consumer group never advances

Check that nothing has set `enable.auto.commit`. The transport refuses it at
construction — it commits on a timer with no idea whether enforcement happened —
but a second consumer in the same group configured elsewhere will do it.

---

## 5. Residency and egress

### A report, export or alert was refused

Read the message: it names the tenant's rule, the data's jurisdiction, and the
destination that broke it. Three shapes:

- **Destination outside the rule** — send it somewhere inside, or change the rule
  if the obligation changed.
- **Undeclared jurisdiction** — the dataset does not say where it belongs.
  Undeclared is *not* unrestricted; declare it. This will block work, which is
  the deliberate cost of the only safe direction.
- **Unstated destination** — a movement with no destination cannot be checked,
  and a check that cannot be made is a refusal.

### An alert was withheld from everybody

By design. An alert delivered to some recipients and silently withheld from
others is worse than either, because the ones who got it assume everyone did.
The dispatch names which channel failed residency.

---

## 6. Performance

### A run is slower than it was

In likelihood order:

1. **Fusion stopped applying.** `prama control compile <file> --fuse` shows the
   grouping. A control that gained an incompatible clause drops out of its scan
   group and runs alone.
2. **Pushdown was lost.** `prama control functions` shows which functions run on
   which engine. A function an engine cannot express is refused, not
   approximated — but a control rewritten to avoid the refusal may now be
   evaluating locally over the whole table.
3. **The source got bigger.** Boring and usually correct.

### A read takes minutes against an API

The REST connector honours `Retry-After` and reports how long it waited. A read
that took eleven minutes because the server asked for it is explained rather
than mysterious. If it stopped early, `last_read_truncated` says so — and a
truncated read is a data finding, not a performance one.

---

## 7. When to page a human

| Symptom | Who |
|---|---|
| A refusal with a clear remedy | Nobody. Follow the remedy. |
| Schema drift reported | The team that owns the schema file |
| Evidence chain broken | Security. This is a tamper finding until proven otherwise. |
| Dead letter full | The data owner for the stream, then the platform |
| Residency refusal | The tenant's data-protection owner |
| `not_established` across many controls | Platform: something is not running, not something wrong with data |

---

## 8. What this runbook does not cover

Kubernetes operator behaviour on a real cluster, an air-gapped install, and
cloud KMS key rotation. All three are implemented and **none has been exercised
against the real thing** — see `docs/19` and `deploy/README.md`, which say so in
those words rather than leaving it to be discovered here.
