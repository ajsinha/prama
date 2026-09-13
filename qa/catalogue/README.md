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

---

## The index

**4,660 cases** across 7 files and 173 sections. Every case carries all
seven fields, and no id is used twice.

| File | Cases | Sections | Id prefixes | P1 | P2 | P3 |
|---|---:|---:|---|---:|---:|---:|
| [`dataplane.md`](dataplane.md) | 540 | 28 | `CON-`, `EXE-`, `PRO-`, `SCH-` | 305 | 212 | 23 |
| [`domain.md`](domain.md) | 680 | 22 | `PCK-`, `CLS-`, `RCN-`, `LIN-`, `CTR-`, `IMP-`, `INT-` | 424 | 239 | 17 |
| [`interfaces.md`](interfaces.md) | 657 | 22 | `CLI-`, `UI-`, `API-`, `AGT-`, `AST-`, `LSP-`, `MCP-` | 316 | 292 | 49 |
| [`language.md`](language.md) | 629 | 23 | `PQL-`, `BE-`, `IR-` | 369 | 223 | 37 |
| [`platform.md`](platform.md) | 1,058 | 30 | `CFG-`, `DB-`, `MON-`, `RPT-`, `OPS-`, `INC-`, `BCH-` | 579 | 394 | 85 |
| [`semantic.md`](semantic.md) | 600 | 24 | `SEM-`, `DER-`, `PRP-`, `MIN-`, `IND-`, `ER-` | 308 | 253 | 39 |
| [`trust.md`](trust.md) | 496 | 24 | `SEC-`, `EVD-`, `CAL-`, `SCR-` | 252 | 192 | 52 |
| **Total** | **4,660** | **173** | | **2553** | **1805** | **302** |

### What each file covers

- **`language.md`** — PQL: lexer, parser, types, lint, formatter, Excel surface, the
  lowering to IR, and both backends (SQL per dialect, and the reference interpreter
  the conformance suite compares against).
- **`semantic.md`** — declarations, the thirteen relationship kinds, tolerance, approval
  policy, conflict and maturity, the Γ generator, proposals, induction, mining and
  entity resolution.
- **`dataplane.md`** — connectors, profiling, execution, fusion, sampling, streaming and
  the spool.
- **`trust.md`** — the evidence ledger, hash chaining and Merkle roots, attestation,
  scoring, bitemporality, redaction, authentication, authorisation and tenant isolation.
- **`domain.md`** — the banking pack, classification, reconciliation, lineage, contracts
  and the importers.
- **`platform.md`** — configuration, core services, the database layer and every DAO,
  monitoring, incidents, reporting, the benchmark corpus, and deployment.
- **`interfaces.md`** — the CLI, the HTTP API, the web console, the MCP server and the
  language server.
