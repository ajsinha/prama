<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# Troubleshooting

The runbook is for when Prama is running and something is wrong. This is for
when you are trying to make it work in the first place, and for the errors that
mean something other than what they appear to. Why most failures are refusals,
each with a remedy, is in [Operations](README.md#the-shape-of-a-prama-incident).

---

## Errors that mean something other than they say

### `no such file` from `prama control check`

Check the path, then check you are not passing a *directory*. `check` takes one
PQL file. A suite spread over several files is checked by passing each, and the
gate script does that in a loop.

### `there is already a tenant called …`

You created it before, probably against a different database than you think.
Prama reads `database.sqlite.path` from configuration; the default is
`data/prama.db` relative to the working directory. `prama tenant list` shows
what the database you are actually pointed at contains.

The environment variable is `PRAMA_DATABASE__SQLITE__PATH` — double underscores
between path segments. `PRAMA_DATABASE__PATH` is not a setting and is silently
ignored, which is exactly how you end up writing to the wrong database and
concluding the product is broken.

### `no tenant to export` from `prama lsp catalogue`

Pass `--tenant`, or set `tenancy.default_tenant`. The catalogue is an estate's
schemas, and there is no such thing as an estate without a tenant.

### `the vault secret provider is not usable in this deployment`

Registered but unconfigured, which is not the same as absent. The message names
what is missing — an address, a token reference, or both. A Vault token is
itself a credential, so it is given as a reference (`env://VAULT_TOKEN`) and
never as a literal.

### `single sign-on needs the 'sso' extra`

A refusal, not a fallback. Verifying an ID token's signature needs real
asymmetric cryptography, and a deployment that cannot verify signatures must
refuse to do SSO rather than do it weakly.

```bash
pip install -e ".[sso]"
```

### `enable.auto.commit is set, and this transport cannot honour it`

Deliberate. Auto-commit commits on a timer from a background thread with no idea
whether enforcement happened — a message marked done that was never checked and
will never be redelivered. Remove the setting rather than working around it.

---

## Things that look like bugs and are not

### A control refuses to compile on one engine

`A function an engine cannot express is refused, never approximated.` SQLite has
no exact numeric type, so `ROUND` is refused there rather than silently rounding
a float — which would give a different answer from PostgreSQL for the same
control, and nothing would notice.

`prama control functions` shows the coverage. The fix is to run that control
where it means something, not to make it compile everywhere.

### An import took on fewer checks than the contract promised

Read the list of refusals; it names each one. A text quality rule is prose and
becomes no control; raw SQL bypasses the IR and cannot be replayed; an engine
Prama has no importer for is refused rather than run.

A contract promising eleven checks and importing six is a conversation with the
producer, and the six that did import are the ones that mean something.

### `prama pack recognise` names no concept

Also deliberate. Position, Balance and Exposure all carry an amount, a currency
and an as-of date; a matcher that counted overlapping properties would call one
table all three. The refusal says what such a table usually is instead.

### The assistant will not change anything

It cannot. No tool in its registry mutates, and a mutating tool cannot be
registered. Everything it produces is a proposal on the approval queue.

---

## Environment

### Which Python is actually running

```bash
.venv/bin/python -V
readlink -f .venv/bin/python
```

It should resolve under `~/.local/share/uv/python/`, not `/usr/bin`. If it does
not, rebuild the venv as [the runbook](runbook.md#the-interpreter-is-missing)
says.

### Optional extras and what needs them

| Extra | Needed for | Symptom without it |
|---|---|---|
| `serve` | `prama serve`, the console | uvicorn not found |
| `postgres` | PostgreSQL as the platform database or a source | driver import fails |
| `sso` | OIDC sign-in, customer-managed keys | a named refusal, never a fallback |
| `kafka` | the Kafka stream transport | a named refusal |
| `rest` | the REST connector | a named refusal |
| `audit` | the axe-core accessibility suite | those tests skip loudly |
| `fast` | orjson | nothing; it is a speed-up |

A missing extra always produces a **named** refusal. If you are getting an
`ImportError` traceback instead, that is a defect.

### Running the suite with real services

Optional, and described with the gate in
[CONTRIBUTING.md](../../CONTRIBUTING.md#the-loop).

---

## Getting a useful bug report out of a failure

1. `prama version` — the version constant is the only authority; every other
   version string in the repository is a copy.
2. The **full** error, including the `next:` line. The remedy is usually the
   most diagnostic part.
3. `prama config show` — secrets are redacted, so this is safe to paste.
4. For a control: the output of `prama control explain` on it, which is the
   control as a sentence.
5. For evidence: the manifest, which is small, rather than the bundle.
