<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Accounts, roles and sign-in

## Signing in

Sign in at **/sign-in** with a username and password. Every failure gives the same message —
"those details did not work" — whether the username is unknown, the password is wrong or the account
is disabled, so the form cannot be used to discover who has an account.

A **single-tenant** deployment can set `tenancy.default_tenant`; the console then opens without
signing in. That fallback has no account, so **My account** and **My API keys** still ask you to sign in.

## Your account

The user menu (top right) holds:

- **My account** — your name, roles, and the scopes those roles give you, re-read on every request.
- **My API keys** — see [API keys](/help/api-keys).
- **Change password** — needs your current password. Length is the only rule. Changing it signs out every
  *other* session you have; this one stays signed in.

## Roles

There are four built-in roles. Scopes are listed on **My account**.

| Role | Purpose |
|---|---|
| `admin` | Everything, including managing people and keys. |
| `owner` | The business owner: declares datasets, approves controls, signs attestations. |
| `steward` | Works incidents and breaks; proposes controls but does not approve them. |
| `auditor` | Reads everything and changes nothing. |

The split that matters is **proposing** a control versus **approving** it; they are separate scopes.

## Administration

An administrator manages people at **People & roles** (user menu → *People & roles*, or `/admin/users`):

- **Add a person** — username, name, email, kind (human or service), an initial password, and roles.
- **Set roles** — tick and save. Removing a role takes effect immediately: the person's existing sessions
  end, because any change to an account invalidates sessions issued before it.
- **Reset a password** — sets a new one; the person's sessions end.
- **Disable / enable** — disabling ends every session at once. This is how someone is offboarded.

Nobody is deleted: evidence and attestations name the person who acted, and a record pointing at
someone who no longer exists answers nothing. An administrator cannot disable themselves or remove
their own `admin` role, so an estate cannot lock out its last administrator.

Every change here is written to the audit log.

The same operations exist on the command line:

```bash
prama principal create alice --role owner
prama principal list
prama principal roles
```

## Go deeper

- [Platform: security](../../../../docs/architecture/platform.md#security): how identity, roles and scopes are enforced.
- [Security, governance and compliance](../../../../docs/corpus/13-security-governance-compliance.md): the design and its requirements.
