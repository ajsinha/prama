<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Steward agents

A **steward** is an AI agent that works on goals over time: it reads the estate, thinks through the
model gateway under its own identity, and **proposes**. People decide. Stewards live under
**Admin → Agents** (`/agents`). A steward is not a fleet agent, which runs controls beside the data
and has no model at all.

## To create a steward and give it goals

1. On **Agents**, create a steward. It becomes a service account with a **human sponsor** and a key
   that expires after 30 days.
2. **Add goal**, choosing its kind and a schedule such as `6h` or `1d`, or none to run only on
   request (**Run now**):
   - **Summarise what is failing**: a plain-language brief for a data owner (the `summarise` model
     profile, if one exists).
   - **Re-read a git code source's lineage**: runs code intake again, so new lineage and new
     proposals appear.
   - **Report the checks lineage implies**: how many lineage-derived proposals are waiting.
   - **Draft descriptions** (`curation.describe`): a description for every dataset that has none,
     using the `curate` model profile.

## To review what it drafted

Drafted descriptions wait under **Suggested descriptions**. **Accept** amends the dataset with you as
its author; **Reject** discards the draft. A draft for a dataset that has been described since is set
aside, not applied.

## To make it ask first

Tick **ask me before each run** on a goal. Each scheduled task then waits under **Waiting for your
approval** until somebody grants or denies it. Granting lets the agent take that one action; anything
it proposes still goes to **Proposals**.

## To run a steward as its own process

Tick **done by the agent's own process** on a goal. Its tasks are queued for a steward running
anywhere that can reach Prama over HTTPS (Prama never calls out), which claims them with the key
shown when the steward was created:

```text
POST /api/v1/agents/claim                   {"most": 1}             -> tasks, each with a fencing_token
POST /api/v1/agents/tasks/{id}/heartbeat    {"fencing_token": n}    -> "continue" or "cancel"
POST /api/v1/agents/tasks/{id}/ask          {"fencing_token": n, "action": {...}, "justification": "..."}
POST /api/v1/agents/tasks/{id}/result       {"fencing_token": n, "state": "succeeded", "output": {...}}
```

It thinks through `POST /api/v1/llm/chat` with the same key, so it never holds a provider credential.
A claim is a five-minute lease that each heartbeat renews; if the agent vanishes the task is handed on
with a new token, and the old holder's late result is refused (HTTP 409).

## To stop a steward

| Button | Effect |
|---|---|
| **Pause** | No new tasks. **Resume** undoes it. |
| **Stop** | Open tasks are cancelled. |
| **Revoke** | The key is revoked and the account disabled. A revoked steward stays revoked. |

## What it can never do

Approve or activate a control, confirm or reject lineage, sign an attestation, or administer people,
keys or settings. That is fixed in the steward's identity, not its prompt, and a build test fails if
the steward code ever calls a function that approves, confirms, signs or activates. Its model calls
are costed, budgeted and recorded under its own name.

## Go deeper

- [Lineage and code: steward agents](../../../../docs/architecture/lineage-and-code.md#steward-agents): the identity that bounds a steward, and the protocol.
- [Intelligence](../../../../docs/architecture/intelligence.md): the model gateway, and how AI is kept from adjudicating.
- [Steward agents: design](../../../../docs/design/code-lineage-and-steward-agents.md): why stewards may read and propose, and nothing more.
