# QA round 1 — consolidated log

**Date:** 2026-09-12 · **Tree:** `develop`, from `e2e13c9` · **Method:** five
black-box passes run in parallel, cases written before execution.

## Coverage

| Surface | Cases | Passed | Failed | Blocked | Not run | Detail |
|---|---:|---:|---:|---:|---:|---|
| CLI | 316 | 256 | 58 | 1 | 1 | [`cases-cli.md`](cases-cli.md) · [`log-cli.md`](log-cli.md) |
| Console (real browser) | 172 | 148 | 20 | 0 | 4 | [`cases-console.md`](cases-console.md) · [`log-console.md`](log-console.md) |
| HTTP API | 272 | 221 | 50 | 1 | 0 | [`cases-api.md`](cases-api.md) · [`log-api.md`](log-api.md) |
| Install & operate | 134 | 110 | 23 | 1 | 0 | [`cases-operate.md`](cases-operate.md) · [`log-operate.md`](log-operate.md) |
| Data path | 120 | 101 | 19 | 0 | 0 | [`cases-datapath.md`](cases-datapath.md) · [`log-datapath.md`](log-datapath.md) |
| **Total** | **1,014** | **836** | **170** | **3** | **5** | |

The per-surface logs are the record. This file is the index and the remediation
state; [`findings.md`](findings.md) ranks what failed.

## Why this pass existed

`pytest` was at 4,666 tests and green. Two release blockers had been found the
same morning by standing the product up by hand — a sign-in page that redirected
to itself, and `tenant create` printing a command `principal create` refused.
Neither was visible to any of those tests, and both were the same shape: **two
components each correct on its own, disagreeing at the seam, in the
configuration a real deployment uses and no fixture did.**

So the brief for every agent included one instruction that turned out to matter
more than the rest: **do not set `tenancy.default_tenant`.** Every console
fixture in the repository sets it, it is the pre-authentication path, and it
grants the wildcard. It is why 4,666 tests passed over a locked door.

## What the pass cost to trust

Three things are worth recording about the conditions, because they bear on how
much weight the numbers carry.

**The tree moved underneath it.** Remediation began while three agents were
still running, so two console 500s and one data-path 500 were traced to stale
bytecode and a mid-run `HEAD` change. Each was re-confirmed against a settled
tree before being counted; the ones that did not reproduce are recorded as
artefacts, not defects. The agents flagged this themselves rather than being
caught at it.

**One agent killed another's servers.** A `pkill`-by-port sweep in the operate
pass took down the console and data-path servers mid-run. Nothing was lost, both
restarted, and it is in the log.

**Chromium was not installed**; the console pass drove the system Google Chrome
through `channel="chrome"`. `pytest tests/web/test_axe.py` fails on this machine
for the same reason — which is itself a finding about the documented setup.

## Verification before remediation

Every finding acted on below was reproduced by hand first. Two did not survive
that, and both are recorded in `findings.md` with what was actually true:

- The console pass diagnosed "nobody can sign in" as a missing tenant field.
  That was one of **two** independent causes; the other was a piped password
  that was not the password piped. Either alone locks the door.
- The `H4` tombstone finding from the earlier adversarial review was
  **overstated** — in a sealed bundle the manifest digest does catch the tamper.
  The record-level gap was real and is fixed; the demonstration was not.

## Remediation state

| # | Finding | Severity | State |
|---|---|---|---|
| Q-01 | A piped password is not the password piped; the account is created and unusable | **Blocker** | **Fixed** |
| Q-02 | The console cannot be signed into at all without `tenancy.default_tenant` | **Blocker** | **Fixed** |
| Q-03 | The sign-in page claims nobody exists while principals do | **Blocker** | **Fixed** |
| Q-04 | Four by-parent DAO reads return another tenant's rows in full (API F-02) | **Critical** | **Fixed** |
| Q-05 | All four case studies crash; nothing under `tests/` exercised them | **Blocker** | **Fixed** |
| Q-06 | `prama apikey` does not exist, so the HTTP API cannot be authenticated to | **Blocker** | **Fixed** |
| Q-07 | `prama validators scan` named in a docstring and never built | Low | **Fixed** |

Everything below this line is open, and ranked in `findings.md`.
