# QA

A QA pass that is **not** the unit suite. `pytest` has 4,666 tests and they are
good at what they cover; the two release blockers found on 2026-09-12 — a
sign-in page that redirected to itself, and `tenant create` printing a command
that `principal create` refused — were both invisible to every one of them.

Both were the same shape: two components each correct on its own, disagreeing at
the seam, in the configuration a real deployment uses and no fixture did.

So this pass is black-box and operator-shaped. It drives the product the way a
person does — the CLI, the console in a browser, the HTTP API, a clean install —
and records what happened rather than what should have.

## What is here

| File | What it is |
|---|---|
| `test-cases.md` | Every case, numbered, with preconditions, steps and the expected result. Written **before** execution. |
| `log.md` | The execution log: every case, its actual result, verbatim output where it matters. |
| `findings.md` | What failed, ranked, with a reproduction. |

## The rules this pass runs under

- **A case is written before it is run.** A test case invented to describe what
  the product did is not a test case, it is a changelog.
- **Actual output is recorded verbatim.** "Worked as expected" is not a result.
- **A case that could not be run says so**, and why, rather than being dropped.
  A plan with 200 cases and 40 silently skipped reads as 200 passed.
- **No source is modified during the pass.** Finding and fixing in one motion
  loses the finding.
