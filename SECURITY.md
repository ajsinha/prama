<img src="docs/assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# Security

## Reporting a vulnerability

Email **ajsinha@gmail.com** with `PRAMA SECURITY` in the subject. Include what
you found, how to reproduce it, and what you think the impact is.

Please do not open a public issue for a security problem. This repository is
proprietary and there is no public issue tracker, but the principle stands for
any channel that is not private.

You will get an acknowledgement. If the finding is real you will be told what is
being done about it and when; if it is not, you will be told why, with enough
detail to disagree.

---

## What Prama holds, and what it does not

Knowing this makes an impact assessment much faster.

**Prama does not store credentials.** Connection records hold a *reference* —
`env://ACME_DB_PASSWORD`, `vault://secret/data/prama/db#password` — and the
value is resolved at the point of use. The pre-commit hook refuses a non-empty
secret in a tracked configuration file, and connector configuration schemas mark
their secret fields so a value pasted into one is rejected rather than saved.

**Prama does store samples of failing rows**, because a finding nobody can see
is a finding nobody acts on. Sample retention is bounded, masking is applied by
classification, and the evidence record carries a digest rather than the rows
once they expire.

**Prama's evidence ledger is append-only and hash-chained.** Nothing in the
system mutates or deletes a record. Erasure is by tombstone with the chain
intact, so a right-to-erasure request does not create a hole somebody could hide
in.

---

## Guarantees enforced by the build

These are not review conventions; they fail the build.

| Guarantee | Enforced by |
|---|---|
| No model output determines a verdict on data (`CON-007`) | Import scan in `tests/architecture/test_layering.py` |
| Only `prama.db` may import SQLAlchemy | The same scan |
| Every place data leaves is registered and residency-checked | `tests/architecture/test_egress.py`, with the module list derived from imports |
| No DAO reaches another tenant's rows | 22 tests scanning DAOs by method signature |
| Validator plugins are pure — no clock, no socket, no model | Source scanning at registration, with the implementation hash folded into the plan id |
| The assistant cannot mutate anything | No mutating tool can be registered |
| No secret in tracked configuration | `.githooks/pre-commit` |

The plugin hash detail matters for supply chain: editing a validator's code
changes the identity of every control that used it, rather than silently
changing what past evidence meant.

---

## Cryptography

| Use | Algorithm | What it establishes |
|---|---|---|
| Evidence chain | SHA-256 over canonical JSON | The records have not been altered since they were written |
| Merkle root | SHA-256, odd nodes promoted not duplicated | One short string standing for a period's evidence |
| Attestation seal, bundle seal | HMAC-SHA256 | Sealed by a holder of the deployment's key — **and nothing to anybody else** |
| Bundle provenance | Ed25519 | Signed by the publisher, verifiable with the public half alone |
| ID tokens | RS256/384/512, ES256 only | The token came from the identity provider |
| Customer-managed keys | AES-256-GCM, data key wrapped by the customer's key | Prama cannot read it once the key is revoked |

Two deliberate refusals worth stating.

**Odd Merkle nodes are promoted, not duplicated.** Duplicating is the
well-known construction that lets two different sets produce the same root, and
a root that can be forged is not worth publishing.

**Symmetric algorithms are refused for ID tokens at any strength.** With a public
verification key an HMAC algorithm makes the signature forgeable by anyone; the
accepted set is fixed by configuration and compared against, never read from the
token.

---

## What a green verification does **not** mean

`scripts/verify_evidence.py` prints this on success, and it is worth repeating
here because success is where the overstatement happens:

> This says the records have not been altered since they were written, and that
> this file is the one the manifest describes. It does not say the records are
> true: a false record, honestly written and correctly chained, produces a
> bundle that verifies exactly like this one.

Chain integrity answers *has this been altered since it was written*, not *was it
right when it was written*. The second question is what controls, replay and the
two-stage engine are for.

---

## Known unverified areas

Implemented, and **never exercised against the real thing**. Each is stated in
the module that implements it, and a test asserts the statement is still there.

| Area | What has not been done |
|---|---|
| Customer-managed keys | No cloud KMS — AWS, Azure or GCP — has been exercised |
| Vault secret provider | Not run against a live Vault server |
| Kubernetes operator | Has not met a real API server |
| Air-gapped install | This machine has a network; no disconnected install has been performed |
| OCI image signing | Needs cosign and a registry; neither has been used |
| Screen-reader accessibility | Automated axe-core passes with zero critical findings; **a person with a screen reader has not tested it** |
| Snowflake connector | Written against documented behaviour; **no warehouse has ever answered it** |

None of these is presented as done anywhere in the corpus. `docs/19` tracks each.

---

## Dependencies

Every requirement in `pyproject.toml` is a `>=` with no ceiling, which is a
deliberate trade: security fixes arrive without intervention. **`uv.lock` pins
what that resolved to** — 62 packages across every extra — so a rebuild is
reproducible even though the declaration is not pinned. The gate runs
`uv lock --check`, which fails if the lock no longer describes the project: a
lock that has drifted is worse than none, because it looks like a reproducible
build and is not one.

Updating a dependency is therefore a visible act. `uv lock` changes a tracked
file, and the diff says exactly which versions moved.

`prama bundle sbom` lists what is actually installed, not what was asked for.
