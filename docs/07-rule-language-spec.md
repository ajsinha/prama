<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 07 — PQL: The Prama Quality Language

**Status:** Draft specification v0.9
**Goal:** one declarative language in which a business rule, a statistical monitor, a
reconciliation, and a contract clause are all the same kind of object — readable by a controller,
reviewable by an auditor, executable on any engine.

---

## As built

The language, its type checker, its linter, its formatter, a plain-language
renderer and a language server all exist: `prama.pql`, with lowering to a typed
engine-neutral IR in `prama.ir` and per-dialect SQL in `prama.backend`.

Twenty-five functions are catalogued, each carrying its per-dialect lowering,
its **required** reference implementation, its unknown-propagation rule and its
stated divergence from Excel. A function without a reference implementation does
not construct, which is what stops the compiler and its independent check from
drifting apart. Every one is executed on DuckDB, SQLite and — when a DSN is set
— a real PostgreSQL, and required to agree with its own reference.

An unknown function name is refused at type-check time rather than passed
through to SQL. A function an engine cannot express is refused, never
approximated. A volatile function is refused by name, and the reason given is
replay rather than capability.

The Excel front end (`prama.pql.excel`) is a precedence-climbing parser
producing the *same* AST — no second IR and no second evaluator — and it claims
Excel **familiarity**, never Excel **compatibility**. Every divergence is
declared on the function and printed by `prama control explain`.

**Not built:** nothing in this specification is outstanding. The open question
is §11's — whether ≥95% of real design-partner controls express in the portable
subset — and that needs design partners, not code.

---

## 1. Design goals and non-goals

| Goal | Consequence |
|---|---|
| **Readable by a non-programmer** | English-like keywords; no boilerplate; every rule has a generated plain-language rendering |
| **Writable by a machine** | Small, regular grammar suitable for constrained LLM decoding; every construct is template-able |
| **Engine-neutral** | No SQL dialect leaks into the surface language; the IR is the portability contract |
| **Total and analysable** | No unbounded loops, no side effects, no I/O; every program's cost is statically estimable |
| **Compositional** | Assertions, scopes, and expressions compose; libraries and packs are just PQL |
| **Evidence-producing** | Every assertion declares what evidence it yields; nothing executes without producing a record |
| **Business-anchored** | Rules reference *business attributes and relationships*, not physical columns |

**Non-goals.** PQL is not a transformation language (it cannot write data), not Turing-complete,
not a query language for ad-hoc analysis, and not a replacement for SQL — arbitrary SQL is
supported as a first-class escape hatch (`§8`) but is a *contained* construct, not the substrate.

---

## 2. Two surfaces, one language

PQL has a **YAML surface** (for bulk authoring, GitOps, packs, and machine generation) and an
**expression surface** (for the editor, chat, and inline readability). They parse to the same AST.
The UI's no-code builder emits the YAML surface; the "show me the PQL" toggle displays either.

**Expression surface:**
```pql
CHECK positions_eod.notional_amount IS NOT NULL
  WHERE trade_status = 'ACTIVE'
  SEVERITY critical
  BECAUSE "Notional is a CDE for the FRTB return"
```

**YAML surface (identical AST):**
```yaml
check:
  on: positions_eod.notional_amount
  assert: not_null
  where: "trade_status = 'ACTIVE'"
  severity: critical
  because: "Notional is a CDE for the FRTB return"
```

**Generated plain-language rendering (always available, never authored):**
> *Every active position must have a notional amount. Failures are critical because notional is a
> critical data element for the FRTB return.*

---

## 3. Core grammar (abridged EBNF)

```ebnf
program        = { import | define | control | suite | monitor | reconciliation | contract } ;

control        = "CHECK" target assertion { modifier } ;
target         = qualified_name | "(" expression ")" | dataset_ref ;
assertion      = predicate_assert | aggregate_assert | relation_assert | custom_assert ;

modifier       = where_clause | foreach_clause | when_clause | tolerance_clause
               | severity_clause | dimension_clause | because_clause | evidence_clause
               | schedule_clause | scope_clause | owner_clause | on_fail_clause ;

where_clause     = "WHERE" expression ;
foreach_clause   = "FOR EACH" attribute_list [ "HAVING" expression ] ;
when_clause      = "WHEN" temporal_expression ;          (* activation condition *)
tolerance_clause = "WITHIN" quantity [ "OR" percentage ] ;
severity_clause  = "SEVERITY" ( "info"|"warning"|"minor"|"major"|"critical" ) ;
dimension_clause = "DIMENSION" dimension { "," dimension } ;
because_clause   = "BECAUSE" string ;
evidence_clause  = "EVIDENCE" ( "counts" | "samples" [ "(" int ")" ] | "full" ) ;
on_fail_clause   = "ON FAIL" ( "alert" | "block" | "quarantine" [ "TO" ref ] | "tag" ) ;

monitor        = "MONITOR" metric_expr "ON" target { monitor_modifier } ;
monitor_modifier = "BASELINE" baseline_spec | "SEASONALITY" season_spec
               | "SENSITIVITY" sensitivity_spec | "BUDGET" budget_spec | modifier ;

reconciliation = "RECONCILE" dataset_ref "AGAINST" dataset_ref
                 "ON" match_spec { recon_modifier } ;
recon_modifier = "COMPARING" attribute_list | "NORMALISING" normalisation_list
               | "WITHIN" tolerance | "OFFSET" interval | "CLASSIFY" break_rules | modifier ;

suite          = "SUITE" identifier "{" { control | monitor | reconciliation } "}" ;
define         = "DEFINE" identifier "(" params ")" "AS" ( assertion | expression ) ;
import         = "IMPORT" pack_ref [ "AS" identifier ] ;
```

---

## 4. Assertion catalogue

### 4.1 Column / attribute predicates
```pql
IS NOT NULL | IS NULL | IS UNIQUE
IN <set> | NOT IN <set> | IN CODELIST <ref>
BETWEEN a AND b | > x | >= x | < x | <= x | = x | <> x
MATCHES /regex/ | HAS FORMAT <named_format> | HAS LENGTH BETWEEN a AND b
IS OF TYPE <type> | HAS PRECISION p SCALE s
IS VALID <semantic_type>            -- ISIN, LEI, IBAN, BIC, CUSIP, SEDOL, UUID, email …
IS INCREASING | IS DECREASING | IS NON DECREASING
IS IN CALENDAR <calendar> | IS BUSINESS DAY
HAS DISTINCT COUNT BETWEEN a AND b
HAS NULL RATE BELOW p
```

### 4.2 Dataset-level assertions
```pql
CHECK positions_eod HAS ROW COUNT BETWEEN 900000 AND 1200000
CHECK positions_eod IS FRESH WITHIN 4 HOURS OF '06:30' ON BUSINESS DAYS CALENDAR 'TARGET2'
CHECK positions_eod HAS UNIQUE KEY (account_id, instrument_id, as_of_date)
CHECK positions_eod CONFORMS TO SCHEMA OF CONTRACT 'positions@3.1.0'
CHECK positions_eod HAS NO DUPLICATE ROWS
CHECK positions_eod HAS PARTITIONS FOR EVERY BUSINESS DAY SINCE '2024-01-01'
CHECK positions_feed MATCHES TRAILER RECORD COUNT
```

### 4.3 Multi-column / relational
```pql
CHECK positions_eod SATISFIES account_id DETERMINES legal_entity_id        -- FD
CHECK trades SATISFIES NOT (side = 'BUY' AND quantity < 0)                 -- DC
CHECK positions_eod.account_id REFERENCES accounts.account_id              -- RI
CHECK SUM(exposure) BY counterparty <= limits.approved_limit               -- aggregate
CHECK positions_eod FOR EACH legal_entity HAVING COUNT(*) > 100            -- segmented
      HAS NULL RATE OF lei BELOW 0.001
```

### 4.4 Temporal
```pql
CHECK balances AS OF today
      SATISFIES opening_balance + SUM(movements) = closing_balance WITHIN 0.01
CHECK positions_eod COMPARED TO PREVIOUS BUSINESS DAY
      HAS ROW COUNT CHANGE WITHIN 15%
CHECK reference_rates HAS NO GAPS IN effective_date OVER BUSINESS DAYS
```

### 4.5 Monitors (statistical, calibrated)
```pql
MONITOR row_count ON positions_eod
  SEASONALITY daily, weekly, month_end CALENDAR 'TARGET2'
  BASELINE rolling(90 days)
  SENSITIVITY budget(false_alarms <= 2 per month)
  SEVERITY major

MONITOR distribution(notional_amount) ON positions_eod
  FOR EACH currency
  TEST wasserstein
  BASELINE rolling(30 days)
  SENSITIVITY fdr(0.05)

MONITOR arrival_time ON positions_feed
  EXPECTED '06:30' CALENDAR 'TARGET2'
  SENSITIVITY budget(false_alarms <= 1 per quarter)
```
Every `MONITOR` yields a **conformal p-value**, and `SENSITIVITY` is declared in *operational*
terms — an alert budget or an FDR level — never as an opaque "medium". See
[08](08-ai-ml-capabilities.md) §4.

### 4.6 Reconciliation
```pql
RECONCILE subledger AGAINST general_ledger
  ON (account_code, cost_centre, accounting_date)
  COMPARING amount
  NORMALISING amount TO reporting_currency USING rates FROM 'ECB' AS OF accounting_date
  WITHIN 1.00 EUR OR 0.001%
  OFFSET general_ledger BY 1 BUSINESS DAY
  CLASSIFY
    missing_in_b   WHEN b IS NULL
    missing_in_a   WHEN a IS NULL
    fx_difference  WHEN ABS(a.amount - b.amount) <= fx_tolerance(a.currency)
    timing         WHEN EXISTS b AT accounting_date + 1
    value_break    OTHERWISE
  SEVERITY critical
  ON FAIL alert TO 'finance-control'
```

### 4.7 Entity resolution
```pql
RESOLVE counterparties_crm AGAINST counterparties_trading AS parties
  BLOCK ON soundex(legal_name), country
  COMPARE legal_name USING jaro_winkler,
          lei USING exact,
          address USING token_set,
          incorporation_date USING date_proximity(30 days)
  MODEL fellegi_sunter
  THRESHOLD match >= 0.95, review >= 0.80
  CHECK NO DUPLICATE parties WITHIN counterparties_crm
```

### 4.8 Contract conformance
```pql
CONTRACT 'odcs://positions@3.1.0' ENFORCE schema, quality, sla
  ON FAIL block
```

---

## 5. Scopes, binding, and selectors

The most important expressiveness feature: **rules bind to business meaning, not to columns.**

```pql
-- every attribute mapped to the Instrument.ISIN concept property, estate-wide
CHECK CONCEPT Instrument.ISIN IS VALID isin
  SEVERITY major
  DIMENSION validity
  BECAUSE "ISO 6166 conformance is required wherever an instrument is identified"

-- every CDE in a domain must have an owner and a completeness control
CHECK EVERY ATTRIBUTE WHERE is_cde AND domain = 'Credit Risk'
  HAS NULL RATE BELOW 0.005

-- apply to every dataset carrying a declared relationship of a given type
CHECK EVERY RELATIONSHIP OF TYPE reconciles_with IN DOMAIN 'Finance'
  IS SATISFIED
```

Selector dimensions: semantic type, concept property, tag/classification, criticality tier, domain,
owner, naming pattern, physical dialect, dataset lifecycle state, and pack membership. Selector
expansion is materialised, versioned, and shown to the author before approval — an author always
sees *exactly which assets* a selector rule will touch, and is alerted when the expansion changes.

---

## 6. Semantics

### 6.1 The evaluation model

A control is a function
`C : (Scope, Snapshot) → (Verdict, Metrics, Evidence)` where:

- **Scope** = a set of records identified by a dataset binding, a filter, a segmentation, and a
  temporal window.
- **Snapshot** = an immutable identifier of the data state (Iceberg/Delta version, DB SCN/LSN,
  file digest set, Kafka offset range). Where a source cannot provide one, the evidence records
  that the snapshot is *approximate* — the platform never pretends otherwise.
- **Verdict** ∈ {pass, fail, error, skipped, indeterminate}. `indeterminate` is a first-class
  outcome (e.g. sample size insufficient for the declared confidence); it is never silently mapped
  to pass.
- **Metrics** = the named quantities computed (violation count, rate, aggregates), all persisted to
  the metric history.
- **Evidence** = the immutable record (§ [13](13-security-governance-compliance.md) §6).

### 6.2 Three-valued logic and nulls

PQL uses SQL three-valued logic inside expressions, but **assertion outcomes are explicit about
unknowns**: a predicate that evaluates to `UNKNOWN` for a row counts as a *violation* unless the
assertion declares `TREAT UNKNOWN AS pass`. This inverts the SQL default deliberately: silence
about unknowns is the most common source of false confidence in production DQ suites.

### 6.3 Thresholds

Every assertion has a pass condition over its metrics. Defaults: zero violations for structural
assertions; a declared rate for statistical ones. Thresholds may be absolute (`AT MOST 5 ROWS`),
relative (`BELOW 0.1%`), monetary (`WITHIN 1000 EUR`), or statistical (`WITHIN 3 SIGMA` — which is
compiled into a calibrated monitor, not a naive z-test).

### 6.4 Determinism

Given the same IR hash, snapshot, and engine, a control must produce an identical verdict. All
sampling is seeded and recorded. Non-deterministic constructs (`RANDOM`, `CURRENT_TIMESTAMP` inside
expressions) are rejected at compile time; temporal context is injected explicitly as a parameter.

---

## 7. The Intermediate Representation

The IR is a typed, engine-neutral logical plan — the portability contract and the artefact third
parties may target (`FR-EXT-010`).

```json
{
  "ir_version": "1.0",
  "id": "ir:sha256:9c4f…",
  "assertion": {
    "kind": "predicate",
    "predicate": {"op":"is_not_null","arg":{"col":"notional_amount"}},
    "unknown_policy": "violation"
  },
  "scope": {
    "dataset": "ds:positions_eod",
    "binding": "bind:snowflake/RISK.POSITIONS_EOD",
    "filter": {"op":"eq","args":[{"col":"trade_status"},{"lit":"ACTIVE"}]},
    "segment_by": [],
    "temporal": {"as_of":"$business_date","window":null}
  },
  "metrics": [
    {"name":"violating_rows","agg":"count_if","expr":{"op":"not", "arg":"$predicate"}},
    {"name":"scanned_rows","agg":"count"}
  ],
  "threshold": {"metric":"violating_rows","op":"<=","value":0},
  "evidence": {"level":"samples","max_samples":50,"masking":"policy:pii-default"},
  "cost_hint": {"scan":"full","fusable":true,"partition_pruning":["as_of_date"]},
  "provenance": {
    "source":"declaration",
    "declared_by":"rel:R-4471",
    "pql_hash":"sha256:1a7b…",
    "authored_by":"user:jsmith","approved_by":"user:aroy","version":7
  }
}
```

**Compilation targets and the capability matrix.** Each backend declares its capabilities
(window functions, `QUALIFY`, regex flavour, approximate distinct, sampling clause, JSON path,
decimal precision). The compiler chooses a strategy per capability; where a target genuinely cannot
express a construct, compilation fails *at authoring time* with a clear message — never silently
degrades. Fallback to a supported backend (e.g. pull a bounded slice into Arrow/DuckDB) is an
explicit, cost-visible choice made by the author.

**Conformance suite.** A corpus of PQL programs plus golden results is executed on every supported
backend in CI. A backend that disagrees with the reference interpreter on any program fails the
release (`NFR-TST-002`, `NFR-POR-003`).

---

## 7a. The expression layer — formulas and function calls

> Implemented in Wave 11. `prama.pql.functions` (the catalogue), `prama.pql.library`
> (what ships), `prama.pql.excel` (the surface), `prama.classify.plugins` (third-party
> validators).

### 7a.1 The function catalogue

Every function the language has is **declared once**, carrying its per-engine lowering,
its reference implementation, its unknown-propagation rule, its pushdown requirement and
its stated divergence from a spreadsheet. Three rules follow, and each is enforced by
test rather than convention:

| Rule | Why |
|---|---|
| **No function without a reference implementation.** | It is a required field, so one cannot be added without it. A corpus then runs every function's SQL against its own reference implementation and requires agreement. |
| **A function an engine cannot express is refused.** | Never approximated. The same control would otherwise mean two things on two engines, and nothing would notice. |
| **A function that cannot replay does not exist.** | `NOW`, `TODAY`, `RAND`, `INDIRECT`, `OFFSET` are refused by name. Evidence that cannot be re-derived is not evidence. |

Before the catalogue, an unrecognised name passed straight through to SQL — `NONSENSE_FN(b)`
parsed, lowered, received a plan id and compiled to `WHERE (NONSENSE_FN("b") > 1)` — while
the reference interpreter returned `UNKNOWN` for the same expression. **The compiler and the
independent check that exists to catch the compiler being wrong disagreed silently.**

### 7a.2 The Excel-familiar surface

```pql
CHECK trade_blotter
  SATISFIES EXCEL '=AND([quantity] > 0, [notional] = [quantity] * [price])'
  SEVERITY critical DIMENSION consistency
  BECAUSE 'the notional is the quantity times the price'
```

`EXCEL` is an explicit marker, not a sniffed one: `=` means equality in a formula and nothing
in PQL, and a parser guessing between the two would occasionally guess wrong on a control that
then means something its author did not write. What it produces is an ordinary
`ExpressionAssertion` over the **same** AST — there is no Excel IR, no Excel evaluator and no
Excel path in the compiler. The formula as typed is kept on the assertion so
`parse(render(x)) == x` holds for both surfaces.

Columns are `[bracketed]` or bare. There are no `A1` references: this is a formula over a named
dataset, not a grid.

### 7a.3 Familiarity, never compatibility

Saying "we accept Excel formulas" makes every reader expect `VLOOKUP`, `IFERROR` and
`"1" + 1 = 2`. The moment one behaves differently — silently — the trust the product is built
on is gone. So the differences are **declared on the function** and printed by
`control explain`:

| Prama | Excel | Why |
|---|---|---|
| No implicit coercion; `TRUE` is not `1` | `"1" + 1 = 2`, `TRUE + 1 = 2` | A control that silently reinterprets its data has a verdict nobody can reason about |
| A blank is `UNKNOWN`, and unknown is a **violation** | Blank is `0` in arithmetic, `""` in concatenation | The inversion of SQL's default that the whole language rests on |
| No error values; `IFERROR` does not exist | `#DIV/0!`, `#VALUE!` propagate by their own rules | A failed computation is UNKNOWN, which is a violation rather than something to swallow |
| `IF` with an undetermined condition is undetermined | Takes the FALSE branch | Choosing a branch invents an answer, and the branch it invents is the one that passes |
| `ISBLANK("")` is true | False for a cell holding an empty string | In a database an empty string and a NULL are the same defect wearing two hats |
| `ROUND` is half away from zero, on an exact type | Half away from zero, on a float | A settlement system rounds this way. Several engines default to half-to-even |
| Dates are ISO-8601 text | Serial numbers, with the 1900 leap-year bug | No serial number, no bug, and no arithmetic on dates that silently means days |
| `^` is refused | Exponentiation | The engines disagree about precision and about a fractional exponent of a negative |
| `MIN`/`MAX` of an unknown is unknown | Ranges skip blanks | Skipping a missing value makes a minimum a statement about the rows that happened to be populated |

**`ROUND` is refused on SQLite.** SQLite has no exact numeric type — every number is a double,
so `2.675` is already `2.67499…` before `ROUND` sees it and no template can recover the intended
value. A penny is exactly the size of error a hash total exists to detect.

### 7a.4 Performance is pushdown, not parsing

Parsing is never the bottleneck: a control is parsed once and content-addressed, and the plan is
cached by hash. The decision that matters is whether an expression **compiles to SQL that runs
inside the engine** or falls back to row-by-row evaluation — a hundredfold difference on the
scans these run against. The catalogue exists so that the common functions push down and the
fallback is loud.

### 7a.5 Third-party validators, not arbitrary code

There is deliberately **no `PYTHON("…")` escape hatch**. It would break replay (arbitrary code
can read a clock), break versioning (the code is part of a control's meaning and not of its
hash), remove the reference interpreter's ability to check the compiler, and become the place
every hard control goes until the declarative core is decoration around a pile of Python.

What is supported is what already worked: a `SemanticValidator` with a SQL **screen** and a
Python **residual**, which is how `ISIN` and `LEI` have always been checked. The PQL surface does
not change — `IS VALID 'my_scheme'` — and a distribution advertises one through the
`prama.classify.validators` entry point.

The contract is enforced, not documented:

- **Purity.** No clock, no network, no filesystem, no model. Checked by scanning the module's
  source — *before it is imported*, because importing runs its top-level code, so a gate that had
  to import the thing it was gating would already have run it.
- **Determinism.** Run twice on the same probes, including an empty string, and required to give
  the same answer. A validator that raises on a blank raises on the first blank in production.
- **Identity.** A hash of the implementation is folded into the plan id of every control that
  names it, so editing a validator changes the control's identity rather than silently changing
  what last month's evidence meant.
- **`CON-007`.** A plugin importing a model client is refused: a model output would otherwise
  determine a pass or fail verdict on data.

A Python check is a **residual over rows a screen has already narrowed**, never a scan. A per-row
Python predicate over a billion rows is not viable, and making that structural rather than
advisory is what keeps the design honest.

---

## 8. Escape hatches, contained

```pql
CHECK CUSTOM SQL """
  SELECT COUNT(*) AS violating_rows
  FROM {{ dataset }}
  WHERE settlement_date < trade_date
""" ASSERT violating_rows = 0
  ENGINE snowflake, databricks           -- explicitly declares portability limits
  COST high
```
Custom SQL is: read-only (enforced by parse-level rejection of DDL/DML), parameterised, resource-
limited, required to return a declared metric shape, tagged with the engines it is valid for, and
marked in the UI as non-portable. Custom Python/UDF checks are supported in the Spark and Arrow
backends under the same contract, in a sandbox with no network access.

---

## 9. Libraries, packs, and reuse

```pql
IMPORT pack 'prama/banking@2.1.0' AS bank
IMPORT pack 'acme/credit-risk@0.4.2' AS acme

DEFINE valid_counterparty(lei_attr, as_of) AS
  lei_attr IS VALID lei
  AND lei_attr IN CODELIST bank.gleif_active AS OF as_of

CHECK exposures.counterparty_lei SATISFIES valid_counterparty(exposures.counterparty_lei, $business_date)
  SEVERITY critical
  DIMENSION validity, accuracy
```
Packs are versioned, signed bundles (`FR-PCK-001`). Definitions are pure and hermetic; a pack may
not perform I/O other than through declared code-list and reference-data references, which are
themselves versioned so that a control executed in March replays identically in November.

---

## 10. Worked example — one business declaration to a running control estate

**What the business owner declares** (in the UI, no PQL typed):

> *"Daily Positions EOD. Owner: Head of Market Risk Data. Tier 1. One row per account per
> instrument per business day. Arrives by 06:30 on TARGET2 business days. Volume tracks trading
> days, 3× at month-end. `notional_amount` is a CDE for FRTB, in trade currency.
> It reconciles with the General Ledger on (account, cost centre) in EUR to within €1, one day in
> arrears. It derives from the Murex trade store."*

**What Prama generates** (proposed, backtested, shown with estimated alert volumes, approved once):

```pql
SUITE positions_eod_core {
  CHECK positions_eod HAS UNIQUE KEY (account_id, instrument_id, as_of_date)
    SEVERITY critical DIMENSION uniqueness
    BECAUSE "Declared grain: one row per account per instrument per business day"

  CHECK positions_eod IS FRESH WITHIN 0 MINUTES OF '06:30' CALENDAR 'TARGET2'
    SEVERITY major DIMENSION timeliness BECAUSE "Declared arrival window"

  MONITOR row_count ON positions_eod
    SEASONALITY daily, weekly, month_end CALENDAR 'TARGET2'
    SENSITIVITY budget(false_alarms <= 2 per month)
    BECAUSE "Declared volume driver: trading days, 3x at month-end"

  CHECK positions_eod.notional_amount IS NOT NULL
    SEVERITY critical DIMENSION completeness
    BECAUSE "CDE for FRTB return"

  CHECK positions_eod.currency IN CODELIST iso4217
    SEVERITY major DIMENSION validity
    BECAUSE "notional_amount declared as denominated in currency"

  CHECK positions_eod.account_id REFERENCES accounts.account_id
    SEVERITY major DIMENSION consistency
    BECAUSE "Relationship R-4471: positions_eod REFERENCES accounts"

  RECONCILE positions_eod AGAINST general_ledger
    ON (account_code, cost_centre)
    COMPARING amount
    NORMALISING amount TO 'EUR' USING rates FROM 'ECB' AS OF accounting_date
    WITHIN 1.00 EUR
    OFFSET general_ledger BY 1 BUSINESS DAY
    SEVERITY critical DIMENSION accuracy
    BECAUSE "Relationship R-4472: positions_eod RECONCILES_WITH general_ledger"

  CHECK positions_eod DERIVES FROM murex_trades
    PRESERVING SUM(notional_amount) BY currency WITHIN 0.01%
    SEVERITY major DIMENSION accuracy
    BECAUSE "Relationship R-4473: positions_eod DERIVES_FROM murex_trades"
}
```

Eight production controls, a reconciliation with break workflow, and a calibrated volume monitor —
from one screen of business declarations, with no SQL written and every control carrying the
sentence that justifies it.

---

## 11. Tooling

- **Editor**: syntax highlighting, schema- and glossary-aware autocomplete, inline type/dialect
  errors, cost estimate, hover documentation, one-click backtest, and a live plain-language
  rendering pane.
- **Formatter**: canonical formatting so diffs are semantic (`prama fmt`).
- **Linter**: subsumption, redundancy, contradiction, never-fires, always-fires, unbounded cost,
  missing `BECAUSE`, missing dimension, non-portable construct without justification.
- **CLI**: `prama compile | test | run | plan | fmt | lint | import | export | diff`.
- **CI action**: fail the build on lint errors, contract violations, or coverage regression.
- **LSP server** so any IDE gets the same experience.
- **Language reference** generated from the grammar, with an executable example per construct.

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
