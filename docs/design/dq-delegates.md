<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# DQ delegates

**Status:** built (Wave 18). Code: `src/prama/delegates/`. User guide:
`src/prama/web/guides/delegates.md`. Worked example: `case-studies/05-dq-delegates/`.

## The problem

Some data quality checks are code, and pretending otherwise makes PQL worse:

- **Business-day arithmetic across market calendars.** The US moved to T+1 on 28 May 2024.
- **Distribution tests.** Benford, drift or a chi-square have no row to point at.
- **Proprietary scoring**, which a bank will not describe in a rule language at all.

`docs/07` §7a.5 rejects an inline `PYTHON("…")` escape hatch, for four reasons:

1. It breaks replay.
2. It breaks versioning.
3. It stops the reference interpreter checking the compiler.
4. It becomes the place every hard control goes.

A delegate keeps those four properties, because it is not inline code. It is a **named,
registered, vetted class behind an interface**. This is the same shape as `SemanticValidator`,
applied to a whole dataset rather than one value.

## Shape

```
PQL   CHECK trades USING DELEGATE 'acme.settlement_cycle@1' (us_cycle = 1) BELOW 0.1%
AST   DelegateAssertion(delegate, parameters)             prama/pql/ast.py
IR    assertion_kind "delegate", detail {delegate, version, parameters};
      metrics scanned_rows, violating_rows                 prama/ir/lower.py
SQL   SELECT <requires> FROM <table> WHERE <filter>       prama/backend/sql.py (_rows)
Host  canonical JSON rows → sandboxed measure() → checked Measurement
                                                           prama/delegates/host.py
Judge the shared threshold; judge() in prama/backend/execute.py, unchanged
```

### Decisions, and why

- **A delegate measures; it never decides.** `measure()` returns counts, and the verdict comes
  from the control's threshold in the shared judging code. A delegate therefore cannot decide
  pass or fail, which is CON-007's rule for models extended to user code.
- **`unit` is `rows` or `findings`.** Benford reports digits that depart from the law, not rows. A
  rate threshold on findings is refused at run time, because "findings per row" is not a quantity
  anybody means.
- **`established=False` gives INDETERMINATE.** When a delegate reports that its result is not
  established, the host drops `violating_rows`. The shared rule then answers "missing metric →
  INDETERMINATE"; there is no special case for delegates.
- **The plan id covers name, pin and parameters, but not the implementation hash.** The delegate
  may be installed only on the agent beside the data, so the control plane cannot know its hash.
  Each **evidence record** carries `delegate`, `delegate_hash`, `delegate_origin` and
  `delegate_unit` instead, and a version pin (`@1`) is enforced where the delegate runs.
- **Rows are canonical JSON** in both sandboxed and in-process runs. Engines return different
  Python types for the same column. Without this, a delegate could answer differently on DuckDB
  and PostgreSQL, and switching the sandbox off for tests would change what it sees.
- **The engine fetches only `requires`**, filtered by the control's `WHERE`. If the control plane
  does not have the delegate, it fetches every column, but only inside the agent's zone.
- **Oversized input is refused, not truncated** (`delegates.max_rows`). A truncated scan reported
  as the whole dataset would be a pass nobody earned.
- **No `FOR EACH` segmentation.** A delegate returns one measurement. Write one control per segment
  with `WHERE`, or segment inside the delegate.
- **Not fused.** The scan fuser skips delegate plans, because there is no SQL metric to share a
  scan with. `prama control compile --fuse` lists them separately.

## Admission (`prama/delegates/registry.py`)

1. **Pre-import scan** of each file in `delegates.paths`, using the validator plugins' scanner
   (`prama.classify.plugins.scan_source`). It refuses clock, network, filesystem, subprocess,
   dynamic import, `exec`/`eval` and model clients. A refused file is never imported, so its
   top-level code never runs. Entry-point distributions are scanned through `forbidden_imports`
   after loading, as validators are.
2. **Determinism and robustness probes:** empty input, all-null rows, and odd values (blank,
   zero, negative, an impossible date, 64 characters, non-ASCII). Each is run twice, and both
   answers must match and be judgeable.
3. **Source hash** of the class (`implementation_hash`), recorded on evidence.

A refusal is loud, and it does not stop the other delegates loading. `prama delegate list` shows
each refusal with its reason.

## Sandbox (`prama/delegates/worker.py`)

`python -m prama.delegates.worker` runs with rlimits on CPU seconds, address space, open files and
core dumps, via `prama.codeintake.worker.limit_resources`. It re-scans a path delegate before
importing it, because the file may have changed since admission. The request goes in on stdin and
the answer comes out on stdout.

**What the sandbox does not do.** It does not isolate the network at the OS level. Network access
is refused by the source scan. A deployment that needs kernel-level isolation should run agents
under the operator's own network namespaces or seccomp profile.

## Remote agents

`Agent(..., delegates=host_from_config(agent_config))`.

- **Advertising:** the agent advertises `AgentCapabilities.delegates` (`name@version`), derived
  from what its own configuration admitted. Nothing is typed by hand.
- **Assignment:** `fits()` makes a delegate control unassignable to an agent without that delegate
  or pinned version, and gives the reason and the remedy.
- **Building work:** `Assignment.for_plan` compiles the row fetch on the control plane, since
  agents never compile.
- **On the agent:** it runs `DelegateHost.measure_plan`, the same function the control plane
  calls, then judges with the shared threshold. Its residency policy decides what happens to the
  samples.

## Not built yet

- **Delegates uploaded through the console** (tier 2). This would need content-addressed storage,
  the same gate, and the proposal and approval queue.
- **Arrow batch streaming** in place of row dictionaries, for very large inputs.
- **A conformance kit** that a delegate author runs in their own CI.
- **`CHECK CUSTOM SQL`** (`docs/07` §8), which remains unbuilt.
