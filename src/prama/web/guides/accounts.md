<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Accounts, roles and sign-in

Who can sign in, and what each person may do. You manage your own account from the user menu
(the avatar, top right); an administrator manages everybody under **Admin → People & roles**
(`/admin/users`).

## To sign in

1. Open **/sign-in** and enter your username and password.
2. If the estate has more than one tenant, choose which.

Every failure says the same thing, "Those details did not work.", whether the username is unknown,
the password wrong or the account disabled, so the form cannot reveal who has an account. A
single-tenant deployment that sets `tenancy.default_tenant` opens the console without signing in;
that fallback has no account, so **My account** and **My API keys** still ask you to sign in.

## To look after your own account

- **My account** shows your name, roles, and the scopes those roles give you.
- **Change password** needs your current password; length is the only rule. It signs out every
  *other* session you have and keeps this one.
- **My API keys** mints keys for programs: see [API keys](/help/api-keys).

## To add a person, or change what they may do

On **People & roles**:

1. **Add a person**: username, name, email, kind (human or service), an initial password, and roles.
2. **Set roles**: tick and save. The change takes effect at once; the person's existing sessions end.
3. **Reset a password**: the person's sessions end.
4. **Disable**: every session and API key the person holds stops working at once. This is how
   somebody is offboarded.

The four built-in roles are `admin` (everything, including people and keys), `owner` (declares
datasets, approves controls, signs attestations), `steward` (works incidents and breaks, proposes
controls but does not approve them) and `auditor` (reads everything, changes nothing). Proposing a
control and approving it are separate scopes.

## What it refuses

- **Deleting anybody.** Evidence and attestations name the person who acted, so people are disabled,
  never deleted.
- **Locking out the last administrator.** You cannot disable yourself or remove your own `admin` role.

Every change here is written to the audit log. The same operations are on the command line:

```bash
prama principal roles                      # what each built-in role may do
prama principal create alice --role owner  # the password is prompted for
prama principal list
```

## Go deeper

- [Platform: security](../../../../docs/architecture/platform.md#security): how identity, roles and scopes are enforced.
- [Security, governance and compliance](../../../../docs/corpus/13-security-governance-compliance.md): the design and its requirements.
