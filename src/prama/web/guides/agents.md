<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Steward agents

A **steward** is a persistent AI agent that works on goals over time. It reads the estate,
thinks through the model gateway, and **proposes**. People decide.

## What a steward can and cannot do

| Can | Cannot, ever |
|---|---|
| Read declarations, controls, incidents, evidence, reports | Approve or activate a control |
| Call models through the gateway, under its own identity | Confirm or reject lineage |
| Re-read a code source's lineage | Sign an attestation |
| Leave notes and propose | Administer people, keys or settings |

Each steward is a service account with a **human sponsor** and a key that expires after 30 days.
Its model calls are costed, budgeted, redacted and recorded under its own name, so a budget can be
set for it like for anybody. A build test fails if the steward code ever calls a function that
approves, confirms, signs or activates.

## Goals

On the **Agents** page (user menu → Agents), create a steward and give it goals, each with a
schedule such as `6h` or `1d`, or none to run only on request:

- **Summarise what is failing.** A plain-language brief for a data owner (uses the `summarise`
  model profile, if one exists).
- **Re-read a git code source's lineage.** Runs the code intake again, including the checked model
  pass, so new lineage and new proposals appear.
- **Report the checks lineage implies.** How many lineage-derived proposals are waiting.

## The kill switch

- **Pause:** no new tasks.
- **Stop:** open tasks are cancelled.
- **Revoke:** the steward's key is revoked and its account disabled, so nothing it holds works
  anymore. A revoked steward stays revoked.
