<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# API keys

A program uses an API key to call the REST API under `/api/v1`:

```bash
curl -H "Authorization: Bearer pk_live_…" http://127.0.0.1:5900/api/v1/health
```

## Creating a key

Open **My API keys** from the user menu. Give the key a name that says which program uses it, choose an
expiry (90 days by default, at most 365), and tick its scopes.

- **A key can never do more than you can.** Only the scopes you hold are offered, and anything else is
  refused on the server as well.
- **A key with no scopes does nothing.** An empty list means "nothing", never "everything".
- **The key is shown once**, on the page that created it. Only its prefix and a hash are stored, so it
  cannot be shown again. If you lose it, revoke it and create another.

## Revoking

Press **Revoke** beside the key. It stops working at once. Revoked keys stay listed, because "which keys
has this person ever had" is the question an access review asks.

An administrator sees every key in the estate at **All API keys** (`/admin/keys`) and can revoke any of them.

## From the command line

```bash
prama apikey create nightly --principal alice --scope report:read --expires-in-days 30
prama apikey list
prama apikey revoke pk_live_abcd
```

Every creation and revocation is written to the audit log.

## Go deeper

- [Platform: security](../../../../docs/architecture/platform.md#security): how a key's scopes are bounded by its holder's roles.
- [The Python SDK](../../../../docs/sdk/README.md): what a key is for: scripting Prama.
