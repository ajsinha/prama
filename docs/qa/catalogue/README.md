# The QA catalogue

Every part of Prama, enumerated as test cases, written from the code and the
documentation rather than from memory. Round 1 covered five *surfaces* — the
CLI, the console, the API, installation, and the data path — and found 170
failures in 1,014 cases. This catalogue covers the **42 packages**, which is a
different question: round 1 asked "does the product work when you use it", and
this asks "is there any part of it nobody has looked at".

## Scope

| | |
|---|---|
| Packages | 42 under `src/prama/` |
| Source | ~91,000 lines |
| Target | ≥ 1,000 cases, and as many more as the code deserves |

## The format

Every case, without exception:

```
### PQL-042 · A control with no BECAUSE is refused
- **Area:** `pql/parser.py::Parser._control`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `CHECK t.a IS NOT NULL`
- **Expected:** `PqlSyntaxError`, naming the missing clause, with a remedy
- **Why:** a control nobody justified is one nobody can review, and the
  language refuses it on purpose
```

- **Type** is one of: `functional`, `boundary`, `negative`, `security`,
  `concurrency`, `performance`, `contract`, `regression`, `documentation`.
- **Priority**: `P1` it must work for the product to be usable · `P2` it must
  work for the product to be trusted · `P3` it should work.
- **Why** is not optional. A case whose reason cannot be stated is a case
  nobody will maintain, and the first thing dropped when it goes red.

## The rules these were written under

- **Derived from the code, not imagined.** Every case names the module or
  function it exercises. A case that cannot name one is describing a feature
  that may not exist.
- **Every public entry point gets at least three**: the happy path, a boundary,
  and a refusal. Most deserve more.
- **Every documented claim gets one.** A docstring saying "this never returns a
  stale value" is a test case; that is how findings C5, C9, H4 and T3 were
  found, each being a claim the code did not keep.
- **Every `remedy=` gets one that follows it literally.** Three shipped
  remedies have named commands that did not exist.
- **Nothing is executed here.** Authoring and running are separate passes on
  purpose: a case written while watching the product behave is a description of
  the behaviour, not a test of it.

## Files

One per area. The prefix is the case-id namespace, so ids never collide across
files.
