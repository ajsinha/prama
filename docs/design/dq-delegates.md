<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# DQ delegates

**Status:** built (Wave 18). Code: `src/prama/delegates/`. User guide:
`src/prama/web/guides/delegates.md`. Worked example: `case-studies/05-dq-delegates/`.

## The problem

Some data quality checks are code, and pretending otherwise makes PQL worse:

- **Business-day arithmetic across market calendars.** The US moved to T+1 on 28 May 2024.
- **Distribution tests.** Benford, drift or a chi-square have no row to point at.
- **Proprietary scoring**, which a bank will not describe in a rule language at all.

`docs/corpus/07` §7a.5 rejects an inline `PYTHON("…")` escape hatch, for four reasons:

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
   (`prama_kernel.plugins.scan_source`). It refuses clock, network, filesystem, subprocess,
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
core dumps, via `prama_kernel.delegates.limits.limit_resources`. It re-scans a path delegate before
importing it, because the file may have changed since admission. The request goes in on stdin and
the answer comes out on stdout.

**Isolation, in layers** (`prama_kernel.delegates.sandbox.isolation_in_force` names what applied, and the
evidence records it as `delegate_isolation`):

- **Clean environment.** The worker gets an allowlist (`LANG`, `PATH`, a private `HOME` and `TMPDIR`,
  and `PYTHONPATH` when set). It does not inherit the server's environment, so DSNs and API keys are not
  there to read.
- **Network namespace.** Where the host allows unprivileged user namespaces (probed once), the worker
  runs under `unshare --net --map-root-user`: a network stack with nothing in it.
- **Audit hook** (PEP 578, `worker.seal`). Installed before the delegate is imported and not removable.
  It refuses socket, subprocess, `exec`, `fork`, `posix_spawn`, `ctypes` and `sys.addaudithook` events.
  This is an in-process check, not a boundary against native code already loaded.
- **One deadline over both pipes.** The host multiplexes the worker's stdin and stdout with
  `selectors` under a single deadline. Before this, the deadline covered only the reply, so a delegate
  that slept (using no CPU, so the CPU limit never fired) held the host for ever.
- **The admission scan** now also refuses `import builtins`, interpreter-internals attributes
  (`__self__`, `__subclasses__`, `__globals__`, …) and `getattr` with a computed name.
  `getattr(len.__self__, "__imp" + "ort__")` had been admitted.

`tests/delegates/test_sandbox.py` exercises each layer with a delegate that passes admission and
misbehaves only when a control asks it to.

**Admission is sandboxed too.** With `delegates.sandbox: true` (the default), the server never
imports delegate code:

- **Configured delegates.** Each configured file, and the installed entry points together, is
  scanned, imported and probed by its own sandboxed worker (`python -m prama.delegates.vet
  --admit`, sealed before the import). The server registers a stand-in from the description, with the
  real implementation hash, so the evidence is the same as it would be in process.
- **Failures stay local.** A delegate that hangs or crashes its admission is refused alone, and the
  others still load.
- **Uploads** are vetted by the same launcher (`prama_kernel.delegates.sandbox.run_isolated`).
- **Development mode.** `delegates.sandbox: false` imports and probes in process, as before.

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

## Streaming (large inputs)

The engine's cursor is read in batches (`delegates.batch_rows`, via `fetchmany`; an executor
exposes `execute.batches(sql, size)`). The delegate receives a **lazy iterator**.

- **Sandboxed:** rows cross to the worker as JSON lines through a pipe. The pipe's fixed buffer
  is the bound on memory: the cursor is not read faster than the delegate consumes.
- **Row ceiling:** rows are counted while they stream. Past `delegates.max_rows`, the stream
  stops and the run is refused. It is also refused afterwards if the delegate swallowed the stop,
  because a truncated input must not be believed.
- **Memory:** a delegate that calls `list(rows)` still works, using the memory it asked for,
  within its own limits.
- **Import integrity:** the worker imports exactly the bytes it hashed. A file whose SHA-256 no
  longer matches the one taken at admission is refused.

## The conformance kit (`prama.delegates.testkit`)

Authors run this in their own CI, as `check_delegate(path, cases=[Case(...)])` in pytest or as
`prama delegate check path --cases cases.json` (exit 1 on any failure). It checks:

1. the pre-import scan;
2. admission;
3. that parameter defaults match their kinds;
4. **one pass**: a one-shot iterator and a list give the same answer, because a delegate that
   iterates twice sees nothing the second time once Prama streams to it;
5. streaming N synthetic rows through the real, sandboxed host;
6. the author's own cases (`scanned`, `violating`, `established`, and a subset of
   observations).

## Console uploads (`prama/delegates/uploads.py`)

The flow is received → vetted → proposed → approved (four eyes) → adopted.

- **Received.** One `.py` file of at most 256 KB, in UTF-8.
- **Vetted.** The full conformance kit runs in a resource-limited subprocess
  (`python -m prama.delegates.vet`). The file must hold exactly one delegate. The server process
  never imports uploaded code, not even to vet it. A refusal is shown to the uploader and not
  stored.
- **Proposed.** The upload is stored in `dq_delegate_upload`, with its source, SHA-256, vetted
  description and findings.
- **Approved.** Approval needs `control:approve`, and the approver must not be the uploader. A
  version is immutable: fix a rejected upload and raise its version.
- **Adopted** at the start of each control-plane run (`DelegateHost.adopt_uploads`), and again
  from scratch on every pass, so a retired upload stops running:
  - the source is written to `delegates.upload_dir/<tenant>/<sha256>/`;
  - it is registered from its stored description without being imported, as `sandbox_only`;
  - the worker re-hashes the file before importing it, so a file tampered with on disk is
    refused;
  - a configured delegate of the same name takes precedence.
- **Remote agents.** An agent receives approved uploads through `GET /api/v1/delegates/uploads`
  and `…/{id}/source` (`control:read`), or `prama delegate pull --server … --out <its
  delegates.paths>`. Hashes are verified on arrival, and the agent vets each file again when it
  loads it.

## Not built yet

- **Arrow record batches** in place of JSON-line row dictionaries, for speed on very wide tables.
