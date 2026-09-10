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

docker run -d --name prama -p 8080:8080 -v /srv/prama-data:/data \
  -e PRAMA_SECURITY__SESSION_SECRET=... \
  -e PRAMA_TENANCY__DEFAULT_TENANT=01M2... \
  prama:0.1.0
```

Then **http://localhost:8080/estate**.

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
