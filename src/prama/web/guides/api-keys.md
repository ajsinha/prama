<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# API keys

A program (a script, the SDK, a CI job) calls the REST API under `/api/v1` with an API key. You mint
your own under **My API keys** in the user menu; an administrator sees every key in the estate under
**Admin → All API keys** (`/admin/keys`).

```bash
curl -H "Authorization: Bearer pk_live_…" http://127.0.0.1:5900/api/v1/health
```

## To create a key

1. Open **My API keys**.
2. Name the key after the program that will use it.
3. Choose an expiry: 90 days by default, at most 365.
4. Tick its scopes, and create it.
5. Copy the key from the page. **It is shown once**: only its prefix and a hash are stored. If you
   lose it, revoke it and create another.

## To revoke a key

Press **Revoke** beside it, on **My API keys** or, as an administrator, on **All API keys**. It stops
working at once. Revoked keys stay listed, because "which keys has this person ever had" is the
question an access review asks.

## What to know

- **A key can never do more than you can.** Only the scopes you hold are offered, and the server
  refuses anything else as well.
- **A key with no scopes does nothing.** An empty list means "nothing", never "everything".
- **A disabled person's keys stop with them.**

Every creation and revocation is written to the audit log. From the command line:

```bash
prama apikey create nightly --principal alice --scope report:read --expires-in-days 30
prama apikey list
prama apikey revoke pk_live_abcd
```

## Go deeper

- [Platform: security](../../../../docs/architecture/platform.md#security): how a key's scopes are bounded by its holder's roles.
- [The Python SDK](../../../../docs/sdk/README.md): what a key is for: scripting Prama.
