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

## Suggested descriptions

The goal kind `curation.describe` asks a model to draft a description for every dataset that has
none. The model needs a profile for the purpose `curate` on the Models page. The drafts wait under
**Suggested descriptions**. **Accept** amends the dataset with you as its author. **Reject** throws
the draft away. Either way, nothing changes until a person decides. A draft for a dataset that has
been described since is set aside, not applied.

## Asking before acting

Tick **ask me before each run** on a goal, and each scheduled task waits under **Waiting for
your approval** on the Agents page until someone grants or denies it. Granting lets the agent
take that one action. It never approves a control: anything the agent proposes still goes to the
Proposals queue.

## Running a steward as its own process

Tick **done by the agent's own process** on a goal, and its tasks are queued for a steward that
runs elsewhere, anywhere that can reach Prama over HTTPS (Prama never calls out). With the key
shown when the steward was created:

```text
POST /api/v1/agents/claim                   {"most": 1}             -> tasks, each with a fencing_token
POST /api/v1/agents/tasks/{id}/heartbeat    {"fencing_token": n}    -> "continue" or "cancel"
POST /api/v1/agents/tasks/{id}/ask          {"fencing_token": n, "action": {...}, "justification": "..."}
POST /api/v1/agents/tasks/{id}/result       {"fencing_token": n, "state": "succeeded", "output": {...}}
```

The agent does its thinking through `POST /api/v1/llm/chat` with the same key, so it never holds a
provider credential. A claim is a five-minute lease that each heartbeat renews. If the agent
vanishes, the task goes back to the queue with a new token, and the old holder's late result is
refused (HTTP 409), so two copies of an agent cannot both write a task's outcome.

## The kill switch

- **Pause:** no new tasks.
- **Stop:** open tasks are cancelled.
- **Revoke:** the steward's key is revoked and its account disabled, so nothing it holds works
  anymore. A revoked steward stays revoked.

## Go deeper

- [Intelligence](../../../../docs/architecture/intelligence.md): the model gateway, and how AI is kept from adjudicating.
- [Steward agents: design](../../../../docs/design/code-lineage-and-steward-agents.md): why stewards may read and propose, and nothing more.
