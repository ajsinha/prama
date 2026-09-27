# QA round 4 — state at 2026-09-16, resume from here

Written before a machine reboot. Everything below is committed and pushed;
`main` and `develop` are identical and match the remote.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

---

## Where things stand

| | |
|---|---|
| `main` = `develop` = `origin/*` | `4f0c627` |
| Gate | **5,182 passed, 96 skipped, 2 xfailed** — `ruff check`, `ruff format --check`, `mypy src` all clean |
| Findings this round | `Q-87` … `Q-115`, plus one recorded **not** a defect (`BE-132`) |
| Drills completed | 27 |
| Sole author | `ajsinha <ajsinha@gmail.com>`; zero assistant trailers |

**To confirm on resume** (about ten minutes, and it is the whole gate):

```bash
cd ~/PycharmProjects/prama
uv sync --extra dev            # only if the venv did not survive
python3 scripts/sync_test_counts.py --write
```

That script **runs the suite and refuses to write a number from a red run**, so a
clean exit *is* a green gate. Running `pytest` separately first doubles the cost
for nothing — about 18 minutes a batch, which is how the first half of this
session was spent.

---

## The working method, which should not change

For each defect, in this order:

1. **Reproduce it first.** Four times this round a triage description was wrong
   about the mechanism while right that something was broken (`Q-87`'s race,
   `Q-103`'s "silent" divergence, `Q-105`'s INDETERMINATE, `Q-115`'s severity).
2. **Read the signature before writing against it.** Five invented interfaces
   this round — `Generator`, `derive_metrics`, `ControlPlan(control_id=…)`,
   `insert_rows(dialect=…)`, `HAS FUNCTIONAL DEPENDENCY`. Each cost a red
   herring.
3. **Write the counterfactual and confirm it fails *for the stated reason*.**
   Not merely that it fails. One case this round passed the counterfactual
   because the old message happened to contain the same word.
4. **Include a control**, so the repair cannot be satisfied by refusing
   everything.
5. Record the finding in `qa/findings.md`, including what turned out **not** to
   be a defect.
6. Full gate, then commit, then the drill — every batch, not at the end.

### The drill

Use a detached worktree; never `git checkout main` in the live tree.

```bash
git push origin develop
git worktree add /tmp/mainwt main
git -C /tmp/mainwt merge --no-ff develop -m "Merge <ids> into main: <summary>"
git -C /tmp/mainwt push origin main
git merge --ff-only main && git push origin develop
git worktree remove /tmp/mainwt && git worktree prune
```

---

## What the round found, and what it means

29 findings cluster into five shapes. The counts are the argument for what to do
next:

| Count | Shape | Guarded now? |
|---|---|---|
| 8 | A bare exception escaped the error taxonomy | **Yes** — `tests/architecture/test_the_taxonomy_holds_at_the_boundary.py` |
| 7 | A check could not reach what it described | Partly (`test_nothing_is_silently_untracked.py`) |
| 5 | The same question answered twice, differently | No |
| 4 | A restated fact drifted | Partly (`scripts/sync_test_counts.py`) |
| 3 | An input the code never considered | No |

**The single most useful thing done this round** was noticing that the largest
cluster was one rule with no guard. `CLAUDE.md` states it; `test_layering.py`
has twenty-five tests enforcing it, every one an import or text scan, and **none
asserts what a function raises**. The new boundary guard found seven more sites
in seconds. Building the guard beat fixing the ninth instance by hand.

**`Q-115` is the one to remember.** A `Decimal` money threshold was emitted
quoted, so `9.0 > 10.0` compared lexically and was *true* on DuckDB and SQLite —
a control reading `amount > 10.00` passed rows of nine pounds and reported a
verdict. It is the only finding of the round that produced a **wrong answer on
real data**; every other one crashed, cried wolf, or read badly. The severity was
inverted from the noise.

---

## Next, in the order I would take it

### 1 · Two more guards, before more instances — **built 2026-09-27** (differential guard → Q-122; vacuous lint as a ratchet, 33 tests baselined for review)

The boundary guard paid for itself immediately. Two more are worth building, and
neither exists:

- **A differential guard between the Excel surface and the PQL parser.** `Q-112`
  found them disagreeing about `a.b`; the regression pins that one case.
  Generating equivalent inputs for both and requiring the same AST would cover
  the class. This is the "same question answered twice" cluster, which has no
  guard at all and is five findings deep.
- **A vacuous-assertion guard.** The second cluster is tests and checks that pass
  because they reach nothing. `Q-109` (a fixture typing every column `unknown`)
  and `Q-98` (a set of one answer counted as unanimous) are the same defect in
  test and in product. A lint over the regression suite for assertions on
  emptiness with no established non-empty case would find more. Expect noise;
  scope it narrowly or it gets disabled — which is what `Q-114` is about.

### 2 · Remaining triage batches

Language stack — done: `C4 C6 C7 C8 C11 C12 C13 C15 C18 C19`.
**Left: `C2 C5 C14 C16 C17`.** (2026-09-27: `C1` → Q-117, `C22` → Q-118, `C23` → Q-119, `C9` → Q-120, `C20` → Q-121.)

Pick up with:

- **`C9`** — `SqlCompiler` carries the current source table as mutable instance
  state (`BE-034`, `BE-037`). A compiler with per-call state that outlives the
  call is a correctness risk under any reuse.
- **`C22`** — `%g` formatting loses precision on render (`PQL-141` P1). Same
  family as `Q-115`: a number quietly changing on the way through.
- **`C23`** — the type checker does not walk every expression-bearing field of a
  control. Coverage gap in the checker `Q-108` just repaired.
- **`C20`** — unbounded recursion reachable from an HTTP endpoint. Bounded
  refusal rather than `RecursionError`. Security-adjacent.
- **`C1`** — `reference._arithmetic` uses `float` where `library._number` uses
  `Decimal`. **This is `Q-115`'s sibling and may be more of the same class**; it
  is also the unresolved half of `Q-78`. Worth doing early now that `Q-115` has
  shown what the class costs.

Data stack — `C1` (the taxonomy cluster) is largely closed by the boundary
guard; the rest of that file is untouched. **`C4`** was taken first and is closed as Q-116 (2026-09-27): two verifiers disagreeing is the evidence ledger's whole credibility.

Interface stack: `CLI-081` and `CLI-185` were never reproduced in round 3 and
remain open.

### 3 · The 184-case one-off tail

77 of them P1. Not yet triaged into batches.

### 4 · Then the full QA regression

Round 5 over the 4,660-case catalogue, once the batches above are in. Round 4's
own numbers, for comparison: round 3 was 90.1% with zero genuine regressions;
round 4 was 90.3% with three, two of them mine.

---

## Open questions that are yours, not mine

- **`Q-101`: "Eleven waves are complete"** in `README.md`. `docs/19` disagrees
  with itself — its wave map lists ten waves and the document has eleven
  sections, and only Waves 1 and 2 carry `**COMPLETE**` in their headings. Wave
  completion is a judgement about scope; I corrected the connector claim beside
  it (which `19 §W3.11` settles) and deliberately left this one.
- **`Q-64`** freshness execution strategy; **`Q-65`**'s real half (incidents need
  parents); **`Q-78`**'s interpreter half (see `C1` above).
- **`BE-075`** catastrophic regex backtracking is recorded as *not fixed*.
  Static ReDoS detection is not reliable; it needs a runtime bound. The
  regression asserts what is true today so that adding one makes a test fail and
  somebody has to come back and say so.

---

## Two environment notes

- **The machine was under load average 50** for part of this session (an
  external Java process and rustc builds, not Prama). It cost two false failures
  and about an hour. Both tests were repaired to measure what they claim —
  `Q-110` waits by connecting rather than sleeping, `Q-111` skips when the host
  gave the process no CPU — so the same load should no longer produce a red run.
  If the suite takes 30 minutes instead of 9, check `uptime` before believing a
  failure.
- The `prama` console script must be on `PATH`; several regressions shell out to
  it and skip loudly if it is absent.
