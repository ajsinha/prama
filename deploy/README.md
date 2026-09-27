<!--
Prama — deployment.
Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary. No licence is granted except by separate written agreement.
-->

# Deploying Prama

Two shapes, and the difference between them matters more than either.

| | For | Database |
|---|---|---|
| **The all-in-one image** | Evaluation, a demo, one team | SQLite inside the container |
| **The Helm chart** | Anything a bank runs | PostgreSQL, outside the pod |

---

## The operator's control loop

`prama.integrate.operator` decides what reconciling a `PramaEstate` should do;
`prama.integrate.controller` applies it. The cluster is behind a two-method seam
(`ResourceClient`, `DeclarationStore`) with an in-memory implementation, so the
loop's behaviour is testable and only its plumbing is not.

What the loop guarantees, each because the obvious reconciler does something a
bank would not accept:

- **Status is written on every path, including the failing ones.** A reconcile
  that hit a conflict and wrote nothing leaves the resource looking untouched,
  and the operator appears not to be running. The status is the only thing a
  user sees.
- **`observedGeneration` comes from what was read at the top.** The manifest can
  change mid-reconcile, and a `Ready` about "whichever version is current when
  the write lands" is a statement nobody can point at.
- **A failed write stops the batch and reports how far it got.** Twelve of forty
  applied *and stated as twelve* is recoverable; twelve reported as forty is
  not. A later pass picks up where it stopped.
- **A terminating resource is left alone.** Its finalizers are somebody else's
  business, and writing status onto something going away does nothing at best
  and blocks the deletion at worst.
- **Neither seam offers a delete.** "This operator never removes anything" is a
  property of the interface rather than of the loop remembering not to.
- **Nothing is retried here.** A retry policy belongs to the client, which knows
  whether the API server was unreachable or the request was rejected — and
  Kubernetes already backs off the outer loop.

Idempotence is asserted across two passes rather than assumed, which is what the
in-memory cluster is for.

### Not verified here

**No API server has been contacted.** There is no cluster on this machine — no
kind, no k3d, no kubectl — and a test asserts the module imports no Kubernetes
client. What is verified is every decision and every failure path; what is not
is that a real API server accepts the status subresource writes as shaped.

## Signing an offline bundle

Two signatures, and they answer different questions.

```bash
# on the connected machine
openssl genpkey -algorithm ed25519 -out publisher.pem
openssl pkey -in publisher.pem -pubout -out publisher.pub

prama bundle seal ./offline --sign-with publisher.pem

# on the air-gapped host, which has publisher.pub and nothing else
prama bundle verify ./offline --publisher-key publisher.pub
```

The **HMAC seal** says the bundle was sealed by a holder of this deployment's
key, and nothing at all to anybody who does not hold it. The **Ed25519
signature** is the one that survives leaving the building: the receiving host
verifies it with the public half alone, which is what an auditor asks about an
artefact that arrived on a disk.

A failing seal alongside a holding publisher signature is **not a finding** —
it is the normal air-gapped case, where the receiver never had the sender's HMAC
key. A failing *publisher* signature is disqualifying on its own, whatever the
seal says: somebody signed the bundle and it was not who the key says.

`verify` exits **3** on a bundle that must not be installed and **1** on a check
that could not be made. A bundle carrying a signature with no key given to check
it against exits 3: an unverifiable signature reported as nothing would read as
an unsigned bundle, which is a different and lesser problem.

### Verified here

Sealed on this machine with a generated Ed25519 key and verified on a simulated
air-gapped host — a different `session_secret`, so the HMAC seal legitimately
failed while the publisher signature held. Tampering (a wheel replaced after
sealing), a wrong publisher key, and a signature with no key given were each
refused with exit 3.

### Not verified here

**Container image signing.** Signing the OCI image needs `cosign` and a
registry; neither is installed on this machine and neither has been exercised.
What is signed above is the offline *bundle*, which is a different artefact.

**A genuinely air-gapped run.** This machine has a network. The verification
above proves the receiving side needs no secret material beyond the public key,
which is the property that matters, but nobody has carried this to a host with
no route out and installed from it.

## What has been verified, and what has not

Stated first, because deployment artefacts are where "it builds" is routinely
mistaken for "it works".

| | |
|---|---|
| The image **builds** | ✅ verified |
| The image **runs**, applies its schema, creates a tenant, serves the console (HTTP 200) and reports `healthy` | ✅ verified |
| The image **refuses to start without a session secret** (exit 1) | ✅ verified |
| The image runs as **uid 10001, not root** | ✅ verified |
| The chart **lints** and **renders** to valid Kubernetes manifests | ✅ verified |
| The chart **refuses** a missing secret, and SQLite with more than one replica | ✅ verified |
| The rendered pod keeps non-root, read-only root filesystem, all capabilities dropped | ✅ verified, by `tests/deploy/` |
| The chart **installed on a real cluster** | ❌ **not verified** — no cluster was available |
| The Operator's **CRD and reconciliation decision** | ✅ built and tested — see `deploy/operator/README.md` |
| The Operator's **control loop** | ❌ not built — needs a cluster |
| The offline bundle: seal, verify, SBOM | ✅ verified — `prama bundle` |
| An air-gapped install run end to end | ❌ not verified — this machine has a network |

`tests/deploy/test_helm_chart.py` renders the chart on every test run and
asserts the security properties, because a `securityContext` block deleted to
make a pod start on somebody's cluster looks like a whitespace change in review.
It **skips loudly** when helm is absent rather than passing quietly.

---

## The all-in-one image

```bash
docker build -f deploy/Dockerfile -t prama:0.1.0 .

mkdir -p /srv/prama-data
docker run --rm -v /srv/prama-data:/data \
  -e PRAMA_SECURITY__SESSION_SECRET="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  prama:0.1.0 db init

docker run --rm -v /srv/prama-data:/data -e PRAMA_SECURITY__SESSION_SECRET=... \
  prama:0.1.0 tenant create acme-bank --name "Acme Bank"

docker run -d --name prama -p 5900:5900 -v /srv/prama-data:/data \
  -e PRAMA_SECURITY__SESSION_SECRET=... \
  -e PRAMA_TENANCY__DEFAULT_TENANT=01M2... \
  prama:0.1.0
```

Then **http://localhost:5900/estate**.

**It is not the production shape, and that is not a caveat to be worked
around.** A control plane holding its own database inside its own container has
nowhere to fail over to, and the evidence ledger — the thing an auditor asks to
see — lives on one volume on one host.

**There is no default secret in the image.** It refuses to start without one,
exactly as a source checkout does. An image that generated its own would mean
every deployment that skipped the documentation runs on a key baked into a
public layer.

---

## The Helm chart

```bash
kubectl create secret generic prama-session \
  --from-literal=session-secret="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"

helm install prama deploy/helm/prama \
  --set existingSecret=prama-session \
  --set database.postgres.host=postgres.data.svc \
  --set database.postgres.existingSecret=prama-postgres
```

### Two things it refuses to install

Both produce a deployment that looks installed and is wrong, which is why they
fail at `helm install` rather than at three in the morning:

- **No session secret.** There is no generated fallback. A chart that invents
  one produces an installation whose sessions are forgeable by anyone who can
  read the release.
- **SQLite with more than one replica.** Two pods writing one file interleave.
  This is the configuration somebody reaches for to get an HA tick, and it is
  corruption rather than availability.

### Upgrades are not automatic, by design

**Prama has no migrations.** `schema/sqlite.sql` and `schema/postgres.sql` are
the authority. Before an upgrade that changes the schema:

```bash
kubectl exec deploy/prama -- prama db verify
```

`db verify` reports drift and never repairs it. A chart that upgraded silently
would leave a schema nobody was told had diverged — and the whole basis for
trusting a verdict is that the database matches the file the controls were
compiled against.

---

## What is missing

**The Operator and CRDs (W10.6)** — a `PramaEstate` custom resource reconciled
into declarations and controls. Not built. It needs a cluster to develop
against, and an operator written without one is an operator whose reconcile loop
has never run.

**The signed offline bundle (W10.8)** — an air-gapped install: images, chart,
wheels and a local model, with a signature and a verification step. Not built.
Its acceptance criterion in `docs/19` is *"air-gapped install verified end to
end with a local model and no egress whatsoever"*, and that cannot be claimed
from a machine with a network.

Both are listed rather than approximated, because a half-built operator that
reconciles nothing is worse than none: it looks like a supported path.

---

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
