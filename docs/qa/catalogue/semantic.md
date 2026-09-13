# The business semantic layer, and everything derived from it

`prama.semantic` · `prama.derive` · `prama.propose` · `prama.induce` ·
`prama.mine` · `prama.er` · `prama.learn`

The conceptual heart of the product: `docs/03-business-semantic-layer.md` is the
design, this is the enumeration of what the code does with it. Written from the
source, not from the documents — where the two disagree, both get a case and the
disagreement is the finding.

Read `README.md` in this directory for the format and the rules. Ids never
collide across files; the prefixes here are `SEM-`, `DER-`, `PRP-`, `IND-`,
`MIN-`, `ER-`. The learning loop (`prama.learn`) is catalogued under `PRP-`,
because what it learns from and what it re-ranks are proposals.

## What is measured, and where nobody has looked

`tests/semantic/` holds exactly two files — `test_gitops.py` and
`test_services.py`. There is no unit test file for `values.py`,
`relationships.py`, `policy.py`, `conflict.py` or `maturity.py`, which between
them hold every declaration validator, the thirteen relationship kinds, the
tolerance arithmetic, the approval policy and the estate score. `Tolerance` is
the module that shipped the wrong comparison for four waves (finding C2), and it
is in that untested set. The cases below weight it accordingly.

## Summary

| Area | Cases | P1 | P2 | P3 |
|---|---:|---:|---:|---:|
| `semantic/values.py` — the vocabulary of a declaration | 36 | 10 | 19 | 7 |
| `semantic/relationships.py` — the thirteen kinds | 33 | 8 | 23 | 2 |
| `semantic/relationships.py::Tolerance` — the convention that was wrong once | 28 | 14 | 8 | 6 |
| `semantic/policy.py` — criticality and maker-checker | 12 | 8 | 3 | 1 |
| `semantic/conflict.py` — two datasets claiming one meaning | 18 | 5 | 9 | 4 |
| `semantic/maturity.py` — the estate score and what to do next | 19 | 2 | 11 | 6 |
| `semantic/services/base.py` — slugs and the audit obligation | 8 | 2 | 6 | 0 |
| `semantic/services/datasets.py` — declaring, amending, correcting | 22 | 13 | 8 | 1 |
| Bitemporality — amend, correct, and replaying a belief | 19 | 12 | 6 | 1 |
| `semantic/services/graph.py` — concepts, journeys, connections, bindings | 29 | 11 | 17 | 1 |
| `semantic/services/estate.py` — the estate as a whole | 7 | 3 | 4 | 0 |
| `semantic/gitops.py` — the estate as reviewable files | 30 | 14 | 16 | 0 |
| `derive/declaration.py` and `derive/persisted.py` — Γ's input | 14 | 5 | 9 | 0 |
| `derive/generator.py` — Γ, from declarations to controls | 64 | 44 | 19 | 1 |
| `derive/relationships.py` — Γ for the thirteen kinds | 29 | 11 | 18 | 0 |
| `derive/coverage.py` — what is protected, and what only looks it | 17 | 7 | 9 | 1 |
| `derive/suggestions.py` — inferred, and never confirmed by inference | 12 | 6 | 4 | 2 |
| `propose/` — the single mutation channel | 53 | 33 | 18 | 2 |
| `learn/` — the loop, and whether it helped | 14 | 8 | 5 | 1 |
| `induce/` — rules a model proposed, none of which reaches a person unchecked | 48 | 28 | 18 | 2 |
| `mine/` — what the data obeys, offered as candidates | 60 | 46 | 14 | 0 |
| `er/match.py` — deciding whether two records are one thing | 28 | 18 | 9 | 1 |
| **Total** | **600** | **308** | **253** | **39** |

By type: functional 171 · boundary 185 · negative 85 · contract 82 · regression 28 · security 27 · documentation 18 · performance 3 · concurrency 1.

Id prefixes: `SEM-` the declaration model and its services, `DER-` the Γ
generator and coverage, `PRP-` the proposal queue, ranking and the learning
loop, `IND-` induction from models, documents and examples, `MIN-` mining,
`ER-` entity resolution.

---

## `semantic/values.py` — the vocabulary of a declaration

### SEM-001 · A grain naming one attribute is accepted
- **Area:** `semantic/values.py::Grain.__post_init__`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `Grain(attributes=("account_id",), statement="one row per account")`
- **Expected:** constructed; `arity == 1`; `render()` returns the statement
- **Why:** the single most generative declaration in the product — four controls
  follow from it, and if it cannot be built nothing downstream exists

### SEM-002 · A grain naming no attribute is refused
- **Area:** `semantic/values.py::Grain.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `Grain(attributes=())`
- **Expected:** `ValidationError`, remedy quoting "what does one row represent?"
  with a worked example
- **Why:** an empty grain would generate `HAS UNIQUE KEY ()`, which parses and
  asserts nothing

### SEM-003 · A grain that repeats an attribute is refused
- **Area:** `semantic/values.py::Grain.__post_init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `Grain(attributes=("account_id", "account_id"))`
- **Expected:** `ValidationError` "a grain repeats an attribute", context listing
  the attributes
- **Why:** a duplicated key column is a typo that silently weakens the
  uniqueness control it generates

### SEM-004 · A grain attribute that is not a business identifier is refused
- **Area:** `semantic/values.py::_require_identifier`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** each of `"Account ID"`, `"ACCOUNT_ID"`, `"1st_leg"`, `"_hidden"`,
  `""`, `"account-id"`
- **Expected:** `ValidationError` naming the offending value, remedy giving the
  `account_id` form
- **Why:** the name is interpolated straight into generated PQL; anything the
  parser refuses must be refused here instead of at three in the morning

### SEM-005 · A 63-character grain attribute is the boundary
- **Area:** `semantic/values.py::_IDENT`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** a name of 63 characters, then one of 64
- **Expected:** 63 accepted, 64 refused
- **Why:** the pattern is `[a-z][a-z0-9_]{0,62}` and nothing else states the
  limit; a silent truncation elsewhere would produce a control on the wrong
  column

### SEM-006 · A grain with no statement renders a sentence
- **Area:** `semantic/values.py::Grain.render`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `Grain(("account_id", "business_date")).render()`
- **Expected:** `one record per account id per business date` — underscores
  replaced, joined with "per"
- **Why:** this string is the BECAUSE clause of every control the grain
  generates, and it is read by a business owner

### SEM-007 · A written statement is reproduced verbatim
- **Area:** `semantic/values.py::Grain.render`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** a statement containing punctuation, a currency symbol and a
  non-ASCII character
- **Expected:** returned byte for byte, unnormalised
- **Why:** the docstring says it is "kept verbatim: it is what appears in the
  generated control's BECAUSE clause and in the attestation report" —
  paraphrasing replaces the business's language with ours

### SEM-008 · A grain round-trips through `to_dict`/`from_dict`
- **Area:** `semantic/values.py::Grain.to_dict`, `Grain.from_dict`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** build, serialise, deserialise, compare
- **Expected:** equal, with `attributes` still a tuple and the order preserved
- **Why:** this is the form stored in `grain_json` and exported to Git; order
  determines the generated key's column order

### SEM-009 · `Grain.from_dict({})` refuses rather than producing an empty grain
- **Area:** `semantic/values.py::Grain.from_dict`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `Grain.from_dict({})` and `Grain.from_dict({"statement": "x"})`
- **Expected:** `ValidationError` from `__post_init__`, not a silently empty grain
- **Why:** a hand-edited YAML file or a corrupt JSON column reaches this
  constructor directly

### SEM-010 · Two grains with the same attributes are equal and hashable
- **Area:** `semantic/values.py::Grain`
- **Type:** contract
- **Priority:** P3
- **Precondition:** none
- **Steps:** build two identical grains with different statements; compare and
  hash
- **Expected:** the module docstring claims "two grains with the same attributes
  are the same grain" — verify whether `statement` participates in equality, and
  record which is true
- **Why:** the claim is load-bearing for embedding a grain in an evidence record;
  if `statement` participates, the claim as written is false

### SEM-011 · A rhythm defaults to daily with no expectations
- **Area:** `semantic/values.py::Rhythm`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `Rhythm()`
- **Expected:** `frequency == DAILY`, `arrival_by is None`,
  `has_arrival_expectation is False`, `lateness_tolerance_seconds == 0.0`
- **Why:** the default decides whether Γ emits a freshness control for a dataset
  nobody has described

### SEM-012 · `arrival_by` accepts a 24-hour time
- **Area:** `semantic/values.py::Rhythm.__post_init__`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `"06:30"`, `"00:00"`, `"23:59"`
- **Expected:** all accepted
- **Why:** the cut-off is the input to the timeliness control and the calendar
  lookup

### SEM-013 · `arrival_by` refuses everything that is not `HH:MM`
- **Area:** `semantic/values.py::_TIME_OF_DAY`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `"6:30"`, `"24:00"`, `"23:60"`, `"06:30:00"`, `"6.30am"`, `"0630"`,
  `" 06:30"`
- **Expected:** `ValidationError` for each, remedy naming `06:30`
- **Why:** a mis-parsed cut-off produces a freshness control that is late by
  hours or never fires

### SEM-014 · Expected minimum volume above the maximum is refused
- **Area:** `semantic/values.py::Rhythm.__post_init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `Rhythm(expected_volume_min=100, expected_volume_max=10)`
- **Expected:** `ValidationError`, remedy "swap the two bounds, or leave one
  unset", context carrying both
- **Why:** an inverted range generates a row-count control that can never pass

### SEM-015 · Equal volume bounds are accepted
- **Area:** `semantic/values.py::Rhythm.__post_init__`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** `expected_volume_min == expected_volume_max == 5000`
- **Expected:** accepted; Γ emits `HAS ROW COUNT BETWEEN 5000 AND 5000`
- **Why:** a fixed-size extract is a real declaration and the comparison is `>`,
  not `>=`

### SEM-016 · A negative lateness tolerance is accepted unchecked
- **Area:** `semantic/values.py::Rhythm.__post_init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `Rhythm(arrival_by="06:30", lateness_tolerance_seconds=-3600)`
- **Expected:** currently constructs; Γ then emits
  `tolerance_minutes = int(-3600 // 60) == -60`
- **Why:** a negative grace period is a control that demands data an hour before
  its declared cut-off, and nothing refuses it

### SEM-017 · A negative expected volume is accepted unchecked
- **Area:** `semantic/values.py::Rhythm.__post_init__`
- **Type:** negative
- **Priority:** P3
- **Precondition:** none
- **Steps:** `Rhythm(expected_volume_min=-1)`
- **Expected:** currently constructs; a row count can never be negative
- **Why:** a bound that cannot be breached is a control that cannot fail

### SEM-018 · `Rhythm.render` reads as a sentence at every level of completeness
- **Area:** `semantic/values.py::Rhythm.render`
- **Type:** functional
- **Priority:** P3
- **Precondition:** none
- **Steps:** frequency only; frequency + arrival; + calendar; + both volume
  bounds; + only a minimum
- **Expected:** `daily, by 06:30, on TARGET2 business days, (1000 to 5000
  records)`; a missing bound renders as `?`
- **Why:** it appears on the estate map and in the attestation pack

### SEM-019 · A rhythm round-trips, including volume drivers
- **Area:** `semantic/values.py::Rhythm.to_dict`, `Rhythm.from_dict`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** drivers `("month_end", "trading_days")`, serialise, reload
- **Expected:** equal, order preserved, tuple type restored
- **Why:** drivers are the prior knowledge a seasonal baseline is built from;
  losing them silently degrades the monitor to a fixed threshold

### SEM-020 · `Rhythm.from_dict` with an unknown frequency raises the wrong error
- **Area:** `semantic/values.py::Rhythm.from_dict`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `Rhythm.from_dict({"frequency": "fortnightly"})`
- **Expected:** currently a bare `ValueError` from the enum, not a
  `ValidationError` with a remedy listing the eight valid frequencies
- **Why:** this is the constructor a hand-edited GitOps file reaches; the error
  contract says every refusal carries a remedy

### SEM-021 · A code-list domain needs a reference or explicit values
- **Area:** `semantic/values.py::ValueDomain.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `ValueDomain(kind=CODELIST)` with neither field
- **Expected:** `ValidationError` naming both ways to satisfy it
- **Why:** an empty code list compiles to `IN ()`, which fails every row

### SEM-022 · A code-list domain with values only is accepted
- **Area:** `semantic/values.py::ValueDomain.__post_init__`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `allowed_values=("BUY", "SELL")` with no `codelist_ref`
- **Expected:** accepted; `is_constrained is True`
- **Why:** the two-value enumeration is the commonest declaration a business
  owner makes without help

### SEM-023 · A pattern domain with no pattern is refused
- **Area:** `semantic/values.py::ValueDomain.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `ValueDomain(kind=PATTERN)`
- **Expected:** `ValidationError`, remedy offering a different domain kind
- **Why:** the alternative is `MATCHES /None/` — see DER-057, the artefact this
  codebase exists to refuse

### SEM-024 · An invalid regular expression is refused at declaration time
- **Area:** `semantic/values.py::ValueDomain.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `pattern="[unclosed"`
- **Expected:** `ValidationError` quoting the `re.error`, `cause` chained,
  remedy saying it is compiled at declaration time on purpose
- **Why:** the docstring claims compilation happens here; a pattern that only
  fails at execution fails inside a scheduled run

### SEM-025 · A range domain with neither bound is refused
- **Area:** `semantic/values.py::ValueDomain.__post_init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `ValueDomain(kind=RANGE)`
- **Expected:** `ValidationError`, remedy "supply a minimum, a maximum, or both"
- **Why:** an unbounded range constrains nothing while reporting as constrained

### SEM-026 · A range domain with only one bound is accepted
- **Area:** `semantic/values.py::ValueDomain.__post_init__`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** minimum only, then maximum only
- **Expected:** both accepted; Γ emits `>=` and `<=` respectively (DER-055)
- **Why:** "never negative" is a one-sided declaration and the commonest kind

### SEM-027 · An inverted range is accepted unchecked
- **Area:** `semantic/values.py::ValueDomain.__post_init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `ValueDomain(kind=RANGE, minimum=100, maximum=1)`
- **Expected:** currently constructs; Γ emits `BETWEEN 100 AND 1`, which no row
  satisfies
- **Why:** `Rhythm` refuses exactly this shape for volume bounds and
  `ValueDomain` does not — one of the two is wrong

### SEM-028 · `case_sensitive` is declared and never consulted
- **Area:** `semantic/values.py::ValueDomain.case_sensitive`
- **Type:** documentation
- **Priority:** P3
- **Precondition:** none
- **Steps:** declare `allowed_values=("BUY",)` with `case_sensitive=False`; grep
  every consumer of the field
- **Expected:** the field is serialised, compared in `conflict._domain_signature`
  only through the values, and reaches no generated control — a lower-case
  `buy` fails the membership check regardless
- **Why:** a declaration that has no effect is a declaration somebody relies on

### SEM-029 · `ValueDomain` round-trips, with `allowed_values` still a tuple
- **Area:** `semantic/values.py::ValueDomain.from_dict`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** serialise a code-list domain, reload, compare types
- **Expected:** `kind` is the enum again and `allowed_values` is a tuple
- **Why:** `derive/persisted.py::_value_domain` exists because
  `ValueDomain(**payload)` leaves `kind` a string and breaks `is_constrained`
  for every attribute — this is the same hazard one layer up

### SEM-030 · `Criticality` is ordered and comparison is meaningful
- **Area:** `semantic/values.py::Criticality`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** `Criticality.TIER_1 < Criticality.TIER_4`; `int(TIER_1) == 1`
- **Expected:** true; the docstring's claim that `>=` is meaningful in policy
  holds, noting the inversion — Tier 1 is the *most* critical and the *lowest*
  number
- **Why:** every severity floor, approval rule and utility score reads this
  ordering, and the inversion is the easy mistake

### SEM-031 · Every criticality tier has a label
- **Area:** `semantic/values.py::Criticality.label`
- **Type:** functional
- **Priority:** P3
- **Precondition:** none
- **Steps:** read `.label` for all four
- **Expected:** four strings, no `KeyError`
- **Why:** the dict lookup is unguarded and the label reaches the console

### SEM-032 · An out-of-range criticality is refused
- **Area:** `semantic/values.py::Criticality`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `Criticality(0)`, `Criticality(5)`
- **Expected:** `ValueError`
- **Why:** the service layer takes `criticality: int = 4` untyped and passes it
  to the policy, which does its own `int()` — see SEM-126

### SEM-033 · Sensitivity decides masking for all six classes
- **Area:** `semantic/values.py::Sensitivity.masked_by_default`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** read the property for each of public, internal, confidential, pii,
  mnpi, restricted
- **Expected:** true for pii, mnpi, restricted only — confidential is **not**
  masked
- **Why:** it drives `evidence_for` (DER-029) and every sample surface; the
  confidential exclusion is the surprising one and needs pinning

### SEM-034 · Only public and internal values may reach a hosted model
- **Area:** `semantic/values.py::Sensitivity.may_reach_external_model`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** read the property for all six
- **Expected:** true for public and internal only; confidential is refused
- **Why:** this is the residency-adjacent gate on prompt content; a permissive
  answer here sends MNPI to a third party

### SEM-035 · `Authoritativeness.is_copy` excludes `DERIVED`
- **Area:** `semantic/values.py::Authoritativeness.is_copy`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** read `.is_copy` for all six members
- **Expected:** true for `REPLICA` and `EXTRACT` only
- **Why:** `is_copy` gates the whole `_from_authoritativeness` rule (DER-063); a
  derived dataset is a computation, not a copy, and demoting its score would be
  wrong

### SEM-036 · `LifecycleState.is_live` includes `DEPRECATED`
- **Area:** `semantic/values.py::LifecycleState.is_live`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** read for all four
- **Expected:** true for `ACTIVE` and `DEPRECATED`; false for `PROPOSED` and
  `RETIRED`
- **Why:** a deprecated dataset is still being read and still needs controls;
  `DatasetDeclaration.is_live` uses a different rule (`== "active"`) and the two
  disagree — see DER-006

---

## `semantic/relationships.py` — the thirteen kinds

### SEM-037 · `REFERENCES` declared with a match key
- **Area:** `semantic/relationships.py::RelationshipDeclaration`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two declared datasets
- **Steps:** kind `REFERENCES`, `match_keys=(MatchKey("counterparty_id"),)`
- **Expected:** constructed; `generates == ("referential_integrity",
  "orphan_monitor", "key_coverage")`; `render()` begins "records here point at
  records there"
- **Why:** the one cross-dataset shape PQL can already run, and the control
  families must match the docs/03 §2.4 table

### SEM-038 · `RECONCILES_WITH` declared with keys, compare and tolerance
- **Area:** `semantic/relationships.py::RelationshipDeclaration`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two declared datasets
- **Steps:** keys `(account_id, cost_centre)`, compare `("amount",)`, tolerance
  1.00 EUR, offset 1 TARGET2 business day
- **Expected:** constructed; `render()` is the full sentence including "within 1
  EUR" and "the second lags by 1 business day (TARGET2)"
- **Why:** the worked example in docs/03 §2.4 — "no SQL was written by anyone"
  starts here

### SEM-039 · `DERIVES_FROM` declared
- **Area:** `semantic/relationships.py::RelationshipDeclaration`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two declared datasets
- **Steps:** kind `DERIVES_FROM` with keys and a tolerance
- **Expected:** constructed; generates `aggregate_parity`, `trust_edge`,
  `impact_path`; `carries_trust is True`
- **Why:** it is both a check and a trust edge, and the edge is what impact
  analysis walks

### SEM-040 · `FEEDS` declared without match keys
- **Area:** `semantic/relationships.py::RelationshipKind.requires_match_keys`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two declared datasets
- **Steps:** kind `FEEDS`, no match keys, no tolerance
- **Expected:** constructed — `FEEDS` is one of the three kinds that do not
  require keys
- **Why:** "the front office delivers into the warehouse" is a statement about
  a process, and demanding a join key for it would block the declaration that
  makes business lineage possible

### SEM-041 · `MIRRORS` declared
- **Area:** `semantic/relationships.py::RelationshipDeclaration`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two declared datasets
- **Steps:** kind `MIRRORS` with keys and compare, no tolerance
- **Expected:** constructed — `MIRRORS` does not require a tolerance; generates
  `row_count_parity`, `content_parity`, `staleness`
- **Why:** a replica is supposed to be identical; asking what difference is
  acceptable invites an answer that disables the control

### SEM-042 · `AGGREGATES` declared
- **Area:** `semantic/relationships.py::RelationshipKind.requires_tolerance`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two declared datasets
- **Steps:** kind `AGGREGATES` with keys and a tolerance
- **Expected:** constructed; generates `rollup_parity`, `trust_edge`
- **Why:** a roll-up compares sums, and sums of floats never agree exactly

### SEM-043 · `ENRICHES` declared
- **Area:** `semantic/relationships.py::RelationshipDeclaration`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two declared datasets
- **Steps:** kind `ENRICHES` with one match key
- **Expected:** constructed; generates `enrichment_coverage`, `provenance`;
  `carries_trust is True`
- **Why:** enrichment moves data, so a defect in the reference source reaches
  the enriched rows

### SEM-044 · `SUPERSEDES` declared without match keys
- **Area:** `semantic/relationships.py::RelationshipKind.requires_match_keys`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two declared datasets
- **Steps:** kind `SUPERSEDES`, no keys
- **Expected:** constructed at the declaration layer
- **Why:** the declaration permits it and Γ then refuses it as unsatisfiable
  (DER-092) — record which layer should hold the rule

### SEM-045 · `SAME_ENTITY_AS` declared
- **Area:** `semantic/relationships.py::RelationshipDeclaration`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two declared datasets
- **Steps:** kind `SAME_ENTITY_AS` with keys and compare `("lei",)`
- **Expected:** constructed; `is_directional is False`; generates
  `entity_resolution`, `duplicate_detection`, `identifier_consistency`
- **Why:** swapping the two sides must not change the meaning, and the
  generated identifier-consistency comparison depends on it

### SEM-046 · `TEMPORAL_SUCCESSOR` declared
- **Area:** `semantic/relationships.py::RelationshipDeclaration`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two declared datasets
- **Steps:** kind `TEMPORAL_SUCCESSOR`, keys, tolerance absent
- **Expected:** constructed — it does not require a tolerance at the declaration
  layer, though `ComparisonKind.ROLL_FORWARD.needs_tolerance` is true (DER-094)
- **Why:** the two layers disagree about the same relationship, and the
  disagreement decides whether a roll-forward is offered or refused

### SEM-047 · `PARENT_OF` declared without match keys
- **Area:** `semantic/relationships.py::RelationshipKind.requires_match_keys`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two declared datasets
- **Steps:** kind `PARENT_OF`, no keys
- **Expected:** constructed here; Γ returns `Unsatisfiable
  parent_of.orphan_node` naming the missing parent pointer (DER-084)
- **Why:** the same inconsistency as SEM-044, on the kind a user is most likely
  to draw on the estate map without thinking about keys

### SEM-048 · `MUTUALLY_EXCLUSIVE` declared
- **Area:** `semantic/relationships.py::RelationshipDeclaration`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two declared datasets
- **Steps:** kind `MUTUALLY_EXCLUSIVE` with one match key
- **Expected:** constructed; `carries_trust is False`; `is_directional is False`;
  generates `overlap_detection` only
- **Why:** a statement about populations, not a channel a defect travels along —
  propagating trust here would invent a dependency that does not exist

### SEM-049 · `TOGETHER_COMPLETE` declared
- **Area:** `semantic/relationships.py::RelationshipDeclaration`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two declared datasets
- **Steps:** kind `TOGETHER_COMPLETE` with one match key
- **Expected:** constructed; generates `population_completeness`
- **Why:** docs/03 "As built" says this and `RECONCILES_WITH` are declarations
  and not control syntax — the declaration must therefore carry everything the
  comparison needs

### SEM-050 · A relationship joining a dataset to itself is refused
- **Area:** `semantic/relationships.py::RelationshipDeclaration.__post_init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `from_dataset_id == to_dataset_id`
- **Expected:** `ValidationError`, remedy directing the user to a control
- **Why:** a self-join reconciliation compares a table with itself and always
  agrees

### SEM-051 · A kind that requires keys is refused without them
- **Area:** `semantic/relationships.py::RelationshipDeclaration.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** each of the ten kinds where `requires_match_keys` is true, with
  `match_keys=()`
- **Expected:** `ValidationError` for all ten, message quoting the kind's own
  `prompt` so the refusal is in business language
- **Why:** without keys every row on the left matches every row on the right,
  and the comparison reports a clean result over any two datasets

### SEM-052 · `requires_tolerance` is true for exactly three kinds
- **Area:** `semantic/relationships.py::RelationshipKind.requires_tolerance`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** read the property for all thirteen
- **Expected:** true for `RECONCILES_WITH`, `AGGREGATES`, `DERIVES_FROM` only
- **Why:** these are the kinds that compare *values*; a comparison with no
  materiality breaks on the first rounding difference and is switched off within
  the week

### SEM-053 · A `RECONCILES_WITH` with no tolerance is refused
- **Area:** `semantic/relationships.py::RelationshipDeclaration.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** keys and compare present, `tolerance=None`
- **Expected:** `ValidationError` "needs a tolerance", remedy giving `1.00 EUR`
- **Why:** the brief's own example — a `reconciles_with` needs a tolerance, and
  the refusal must name what is missing rather than defaulting to zero

### SEM-054 · A `RECONCILES_WITH` with no compared attribute is refused
- **Area:** `semantic/relationships.py::RelationshipDeclaration.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** keys and tolerance present, `compare=()`
- **Expected:** `ValidationError` "a reconciliation needs at least one attribute
  to compare"
- **Why:** a reconciliation that compares nothing reports a clean reconciliation

### SEM-055 · An `AGGREGATES` with no compared attribute is accepted here
- **Area:** `semantic/relationships.py::RelationshipDeclaration.__post_init__`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** kind `AGGREGATES`, keys and tolerance, `compare=()`
- **Expected:** constructed — only `RECONCILES_WITH` checks `compare` at this
  layer; Γ refuses it later (DER-101)
- **Why:** the compare check is kind-specific where the tolerance check is
  table-driven, and the asymmetry is not stated anywhere

### SEM-056 · `is_directional` is false for exactly four kinds
- **Area:** `semantic/relationships.py::RelationshipKind.is_directional`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** read for all thirteen
- **Expected:** false for `RECONCILES_WITH`, `SAME_ENTITY_AS`,
  `MUTUALLY_EXCLUSIVE`, `TOGETHER_COMPLETE`
- **Why:** the estate map draws an arrow or a line on this answer, and a
  reconciliation drawn as one-way misdescribes the independence it relies on

### SEM-057 · `carries_trust` is true for exactly six kinds
- **Area:** `semantic/relationships.py::RelationshipKind.carries_trust`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** read for all thirteen
- **Expected:** true for `DERIVES_FROM`, `FEEDS`, `MIRRORS`, `AGGREGATES`,
  `ENRICHES`, `TEMPORAL_SUCCESSOR`; false for the other seven
- **Why:** trust propagation decides whether an upstream incident demotes a
  downstream score; `RECONCILES_WITH` must be false or the independence that
  makes the reconciliation worth anything is destroyed

### SEM-058 · Every kind that does not carry trust has a stated reason
- **Area:** `derive/relationships.py::_NO_TRUST_BECAUSE`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** for each kind where `carries_trust is False`, build an edge
- **Expected:** no `KeyError`; seven distinct sentences, none of them a blanket
  one
- **Why:** the comment says a wrong reason on a graph edge is worse than none —
  it is the sentence quoted back when an incident did not raise an alarm
  downstream

### SEM-059 · Every kind has a business-language prompt
- **Area:** `semantic/relationships.py::_PROMPTS`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** read `.prompt` for all thirteen
- **Expected:** thirteen sentences, no `KeyError`, none containing a technical
  term
- **Why:** this is the list a business user picks from; a missing entry is an
  exception on the estate map

### SEM-060 · Every kind's `generates` matches the design table
- **Area:** `semantic/relationships.py::_GENERATES` vs
  `docs/03-business-semantic-layer.md` §2.4
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** compare the thirteen rows of the document table with the dict
- **Expected:** each control family named in the document appears; record any
  the document promises and the dict omits (the document promises "cycle
  detection" for `PARENT_OF`, which Γ explicitly cannot produce — DER-083)
- **Why:** "as built" claims all thirteen dispatch to control families, and a
  promise in the design that the generator refuses is a claim the code does not
  keep

### SEM-061 · `relationship_kinds()` offers all thirteen with five flags each
- **Area:** `semantic/services/relationships.py::relationship_kinds`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** call it
- **Expected:** thirteen dicts, each with `kind`, `prompt`, `generates`,
  `needs_match_keys`, `needs_tolerance`, `directional`, `carries_trust`
- **Why:** the estate-map form is derived from the enum rather than restated, so
  a new kind appears in the UI the moment it exists

### SEM-062 · A declaration round-trips through `to_dict`/`from_dict`
- **Area:** `semantic/relationships.py::RelationshipDeclaration.from_dict`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** a full `RECONCILES_WITH` with keys, compare, tolerance, offset,
  filter, name, description
- **Expected:** equal; `match_keys` a tuple of `MatchKey`, `tolerance` and
  `offset` value objects, not dicts
- **Why:** this is the path from the stored `sem_relationship_version` row to Γ

### SEM-063 · `from_dict` with an unknown kind raises a bare `ValueError`
- **Area:** `semantic/relationships.py::RelationshipDeclaration.from_dict`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `{"kind": "correlates_with", ...}`
- **Expected:** currently `ValueError` with no remedy and no list of the
  thirteen valid kinds
- **Why:** a hand-edited relationship YAML reaches this constructor, and the
  error contract requires a remedy

### SEM-064 · `from_dict` with a missing dataset id raises `KeyError`
- **Area:** `semantic/relationships.py::RelationshipDeclaration.from_dict`
- **Type:** negative
- **Priority:** P3
- **Precondition:** none
- **Steps:** omit `to_dataset_id`
- **Expected:** currently `KeyError`, not a `ValidationError` naming the field
- **Why:** same path, same contract

### SEM-065 · `render()` produces the sentence used in every BECAUSE clause
- **Area:** `semantic/relationships.py::RelationshipDeclaration.render`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** render a full reconciliation and a bare `FEEDS`
- **Expected:** semicolon-joined clauses; a zero offset is omitted; a `FEEDS`
  renders to its prompt alone
- **Why:** it is `Provenance.statement` for every control and comparison the
  relationship generates, and the answer to "why does this exist?"

### SEM-066 · A match key with an empty left side is refused
- **Area:** `semantic/relationships.py::MatchKey.__post_init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `MatchKey(left="")`
- **Expected:** `ValidationError`
- **Why:** an empty join column produces a comparison joining on nothing

### SEM-067 · A match key's attribute names are not validated as identifiers
- **Area:** `semantic/relationships.py::MatchKey.__post_init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `MatchKey(left="Account ID; DROP TABLE")`
- **Expected:** currently accepted — `Grain` applies `_require_identifier` and
  `MatchKey` does not; the value reaches
  `ast.ColumnRef(name=key.left)` in `derive/relationships.py::_references`
- **Why:** two declaration objects in the same layer disagree about what a
  business attribute name is, and one of them feeds a compiler

### SEM-068 · `right_or_left` defaults to the left name
- **Area:** `semantic/relationships.py::MatchKey.right_or_left`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `MatchKey("account_id").right_or_left`; then with
  `right="acct_no"`
- **Expected:** `account_id`, then `acct_no`
- **Why:** it is the target column of the generated `REFERENCES` assertion; the
  common case is the same name on both sides

### SEM-069 · `MatchKey.render` collapses an identical pair
- **Area:** `semantic/relationships.py::MatchKey.render`
- **Type:** functional
- **Priority:** P3
- **Precondition:** none
- **Steps:** `MatchKey("a", "a")`, `MatchKey("a", None)`, `MatchKey("a", "b")`
- **Expected:** `a`, `a`, `a = b`
- **Why:** the rendering goes into the relationship sentence; `a = a` reads as a
  mistake

---

## `semantic/relationships.py::Tolerance` — the convention that was wrong once

Finding **C2** of the adversarial review: `permits()` computed
`absolute_ok and relative_ok`, the intersection, while the class docstring, the
inline comment and `render()` all said "or". Under "1 EUR or 10 bps" a 500 EUR
difference on a 1,000,000 EUR position was a break, though 10 bps of that
position is 1,000 EUR. No test had exercised both bounds at once. Every case
below states which bound should decide.

### SEM-070 · Absolute only: a difference under the bound is permitted
- **Area:** `semantic/relationships.py::Tolerance.permits`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `Tolerance(absolute=1.00)`
- **Steps:** `permits(difference=0.50, magnitude=1_000_000)`
- **Expected:** `True`
- **Why:** the base case the whole reconciliation rests on

### SEM-071 · Absolute only: a difference exactly at the bound is permitted
- **Area:** `semantic/relationships.py::Tolerance.permits`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `Tolerance(absolute=1.00)`
- **Steps:** `permits(1.00, 1_000_000)`
- **Expected:** `True` — the comparison is `<=`
- **Why:** "within 1 EUR" includes 1 EUR; an exclusive bound breaks every
  rounded-to-the-penny reconciliation

### SEM-072 · Absolute only: a difference above the bound is a break
- **Area:** `semantic/relationships.py::Tolerance.permits`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `Tolerance(absolute=1.00)`
- **Steps:** `permits(1.01, 1_000_000)`
- **Expected:** `False`
- **Why:** the counterfactual — a tolerance that permits everything is not a
  tolerance

### SEM-073 · Relative only: the allowance scales with magnitude
- **Area:** `semantic/relationships.py::Tolerance.permits`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `Tolerance(relative=0.001)`
- **Steps:** `permits(900, 1_000_000)` then `permits(1100, 1_000_000)` then
  `permits(900, 100_000)`
- **Expected:** `True`, `False`, `False`
- **Why:** 10 bps of a million is 1,000; the same 900 on a hundred thousand is
  90 bps and is a break

### SEM-074 · Both bounds: a difference over the absolute but inside the relative is permitted
- **Area:** `semantic/relationships.py::Tolerance.permits`
- **Type:** regression
- **Priority:** P1
- **Precondition:** `Tolerance(absolute=1.00, relative=0.001)` — "a penny or a
  basis point, whichever is larger"
- **Steps:** `permits(500.00, 1_000_000)`
- **Expected:** `True`. The allowances are `[1.00, 1000.00]`; `max` is 1000.00;
  500 ≤ 1000
- **Why:** **this is C2 exactly.** Under the old `and` it was a break, and every
  large position generated a break its own declaration calls immaterial — the
  phantom-break flood this module exists to prevent

### SEM-075 · Both bounds: a difference over the relative but inside the absolute is permitted
- **Area:** `semantic/relationships.py::Tolerance.permits`
- **Type:** regression
- **Priority:** P1
- **Precondition:** `Tolerance(absolute=1.00, relative=0.001)`
- **Steps:** `permits(0.75, 100)` — 0.1% of 100 is 0.10, so the relative bound
  is breached
- **Expected:** `True`; the absolute allowance of 1.00 is the larger
- **Why:** the other half of "whichever is larger", and the half that protects
  small balances from a percentage that rounds to nothing

### SEM-076 · Both bounds: a difference over both is a break
- **Area:** `semantic/relationships.py::Tolerance.permits`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `Tolerance(absolute=1.00, relative=0.001)`
- **Steps:** `permits(5000, 1_000_000)`
- **Expected:** `False`
- **Why:** the union must still be able to fail; a fix for C2 that permitted
  everything would pass SEM-074 and SEM-075 and be worse than the bug

### SEM-077 · A relative bound alone against a zero magnitude permits only exactness
- **Area:** `semantic/relationships.py::Tolerance.permits`
- **Type:** regression
- **Priority:** P1
- **Precondition:** `Tolerance(relative=0.001)`
- **Steps:** `permits(0.0, 0.0)` then `permits(0.01, 0.0)`
- **Expected:** `True` then `False` — there is no percentage of nothing, so the
  bound is *not applicable* rather than satisfied
- **Why:** the old expression treated it as satisfied, which permits any
  difference at all on precisely the rows where a difference is most obviously
  real — something against nothing

### SEM-078 · An absolute bound still applies at zero magnitude
- **Area:** `semantic/relationships.py::Tolerance.permits`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `Tolerance(absolute=1.00, relative=0.001)`
- **Steps:** `permits(0.50, 0.0)`
- **Expected:** `True` — the relative allowance is skipped, the absolute one
  remains in the list
- **Why:** the "not applicable" rule must skip only the bound that cannot be
  computed, not the declaration

### SEM-079 · A negative difference is compared by magnitude
- **Area:** `semantic/relationships.py::Tolerance.permits`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `Tolerance(absolute=1.00)`
- **Steps:** `permits(-0.50, 100)` and `permits(-5.00, 100)`
- **Expected:** `True` then `False`
- **Why:** a sub-ledger below the GL is the same size of break as one above it

### SEM-080 · A negative magnitude scales the relative bound by its absolute value
- **Area:** `semantic/relationships.py::Tolerance.permits`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `Tolerance(relative=0.10)`
- **Steps:** `permits(5, -100)`
- **Expected:** `True` — `abs(magnitude)` is used
- **Why:** a short position or a credit balance is negative, and a tolerance that
  collapsed to zero on them would break every one

### SEM-081 · A tolerance with neither bound is refused
- **Area:** `semantic/relationships.py::Tolerance.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `Tolerance()`
- **Expected:** `ValidationError`, remedy "state the materiality, for example
  1.00 EUR or 0.1%"
- **Why:** an empty tolerance object would permit only exact equality while
  reading as a declared materiality

### SEM-082 · A negative absolute tolerance is refused
- **Area:** `semantic/relationships.py::Tolerance.__post_init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `Tolerance(absolute=-1.0)`
- **Expected:** `ValidationError`, context carrying the value
- **Why:** a negative allowance makes `max(allowances)` negative and every
  difference — including zero — a break

### SEM-083 · A zero absolute tolerance is accepted and means exact
- **Area:** `semantic/relationships.py::Tolerance.__post_init__`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `Tolerance(absolute=0.0)`; `permits(0, 100)`; `permits(0.01, 100)`
- **Expected:** constructed; `True`; `False`
- **Why:** "they must agree to the penny" is a legitimate declaration and the
  `< 0` check must not become `<= 0`

### SEM-084 · A relative tolerance outside [0, 1] is refused
- **Area:** `semantic/relationships.py::Tolerance.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `relative=1.5`, `relative=-0.001`, then `relative=10` (a user who
  meant "10 per cent")
- **Expected:** `ValidationError` for each, message stating the value is not a
  fraction and remedy "express 0.1% as 0.001"
- **Why:** the percent-versus-fraction confusion is a thousand-fold error in the
  permissive direction, and the remedy is the only thing standing between the
  two readings

### SEM-085 · The boundary values 0 and 1 are accepted
- **Area:** `semantic/relationships.py::Tolerance.__post_init__`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** `relative=0.0` then `relative=1.0`
- **Expected:** both accepted — the check is `0 <= relative <= 1`
- **Why:** `relative=1.0` permits a 100% difference, which is a real if unwise
  declaration; `relative=0.0` combined with a zero magnitude is SEM-077's
  neighbour

### SEM-086 · `render()` says "or", and says what `permits()` does
- **Area:** `semantic/relationships.py::Tolerance.render`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** `Tolerance(absolute=1.0, relative=0.001, currency="EUR")`
- **Steps:** read `render()`; compare against the behaviour pinned in SEM-074
- **Expected:** `within 1 EUR or 0.1%`, and the union semantics it describes are
  the ones implemented
- **Why:** three statements of intent disagreed with the code for four waves;
  the rendered sentence is the one a business owner approves against

### SEM-087 · `rounding_scale` is carried everywhere and applied nowhere
- **Area:** `semantic/relationships.py::Tolerance.rounding_scale`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** `Tolerance(absolute=0.0, rounding_scale=2)`
- **Steps:** `permits(0.004, 100)`; then grep every consumer of the field
- **Expected:** currently `False` — the field is serialised into
  `tolerance_json`, carried into `ComparisonSpec`, exposed in
  `api/schemas.py`, and read by no comparison code
- **Why:** "compare after rounding to this many decimal places" is a declaration
  a user will make and rely on; a field with no effect is worse than an absent
  one

### SEM-088 · `currency` is decorative and unvalidated
- **Area:** `semantic/relationships.py::Tolerance.currency`
- **Type:** negative
- **Priority:** P3
- **Precondition:** none
- **Steps:** `Tolerance(absolute=1.0, currency="EURO")`
- **Expected:** accepted; renders as `within 1 EURO`; never checked against the
  `iso4217` code list Γ uses everywhere else
- **Why:** the product validates currency codes in generated controls and not in
  the declaration that states the materiality's unit

### SEM-089 · A tolerance round-trips
- **Area:** `semantic/relationships.py::Tolerance.from_dict`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** all four fields set, serialise, reload, `permits()` unchanged
- **Expected:** equal, and the behaviour identical
- **Why:** the stored JSON is what a running reconciliation reads

### SEM-090 · A zero offset renders as "same period"
- **Area:** `semantic/relationships.py::TimeOffset.render`
- **Type:** functional
- **Priority:** P3
- **Precondition:** `TimeOffset()`
- **Steps:** `is_zero`, `render()`
- **Expected:** `True`, `same period`; and `RelationshipDeclaration.render`
  omits it entirely
- **Why:** "allowing that the second lags by 0 business days" is noise in a
  sentence somebody reads every day

### SEM-091 · A business-day offset with no calendar is refused
- **Area:** `semantic/relationships.py::TimeOffset.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `TimeOffset(amount=1, unit=BUSINESS_DAYS, calendar=None)`
- **Expected:** `ValidationError`, remedy naming TARGET2 and SIFMA and stating
  that "one business day" is not otherwise a defined quantity
- **Why:** a reconciliation aligned by an undefined offset breaks on every
  holiday in one jurisdiction and not the other

### SEM-092 · A zero business-day offset needs no calendar
- **Area:** `semantic/relationships.py::TimeOffset.__post_init__`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `TimeOffset(amount=0, unit=BUSINESS_DAYS)`
- **Expected:** accepted — the check is `self.amount and not self.calendar`
- **Why:** the default offset must not demand a calendar nobody needs

### SEM-093 · A calendar-day offset needs no calendar
- **Area:** `semantic/relationships.py::TimeOffset.__post_init__`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** `TimeOffset(amount=1, unit=CALENDAR_DAYS)`
- **Expected:** accepted
- **Why:** the rule is specific to business days, and over-applying it would
  block the simplest offset there is

### SEM-094 · A lagging side other than `from` or `to` is refused
- **Area:** `semantic/relationships.py::TimeOffset.__post_init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `lagging_side="left"`, `"TO"`, `""`
- **Expected:** `ValidationError` for each
- **Why:** the value decides which side the offset is applied to; a silent
  default would align the comparison backwards and break every row

### SEM-095 · A negative offset amount is accepted
- **Area:** `semantic/relationships.py::TimeOffset.__post_init__`
- **Type:** negative
- **Priority:** P3
- **Precondition:** none
- **Steps:** `TimeOffset(amount=-1, unit=CALENDAR_DAYS)`
- **Expected:** accepted; renders as "the second lags by -1 calendar day"
- **Why:** the direction is already carried by `lagging_side`, so a negative
  amount expresses the same thing twice and reads as a defect

### SEM-096 · A named calendar is not checked against the registered calendars
- **Area:** `semantic/relationships.py::TimeOffset.calendar`
- **Type:** negative
- **Priority:** P2
- **Precondition:** the banking pack's calendar registry
- **Steps:** `calendar="TARGET-2"`, `calendar="NOT_A_CALENDAR"`
- **Expected:** accepted at declaration; the failure surfaces when the
  comparison runs
- **Why:** the same hazard as `Rhythm.calendar`, which is likewise unchecked, and the
  same remedy —
  a declaration validated against the pack refuses the typo where the user is

### SEM-097 · The offset renders in the singular for one unit
- **Area:** `semantic/relationships.py::TimeOffset.render`
- **Type:** functional
- **Priority:** P3
- **Precondition:** none
- **Steps:** amounts 1, -1 and 2 with `BUSINESS_DAYS`
- **Expected:** "business day" for ±1, "business days" for 2
- **Why:** generated prose is read by people; "1 business days" is the detail
  that makes a report look machine-written

---

## `semantic/policy.py` — criticality and maker-checker

### SEM-098 · A Tier 4 declaration needs no approval
- **Area:** `semantic/policy.py::ApprovalPolicy.check`
- **Type:** functional
- **Priority:** P1
- **Precondition:** default policy
- **Steps:** `check(criticality=4, authored_by="alice", approved_by=None)`
- **Expected:** returns; no exception
- **Why:** "a governance regime that demands two signatures for a comment on a
  Tier-4 dataset trains people to click through approvals"

### SEM-099 · A Tier 3 declaration needs no approval
- **Area:** `semantic/policy.py::ApprovalPolicy.for_criticality`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** default policy
- **Steps:** tier 3 with no approver
- **Expected:** `ApprovalRequirement.NONE`; accepted
- **Why:** tier 3 is the boundary between "author's word is enough" and review

### SEM-100 · A Tier 2 declaration requires review
- **Area:** `semantic/policy.py::ApprovalPolicy.check`
- **Type:** functional
- **Priority:** P1
- **Precondition:** default policy
- **Steps:** tier 2 with `approved_by=None`
- **Expected:** `ValidationError` "requires approval before it takes effect",
  remedy explaining it is held as proposed
- **Why:** the review tier is what makes the lifecycle state meaningful

### SEM-101 · A Tier 2 declaration may be approved by its own author
- **Area:** `semantic/policy.py::ApprovalRequirement.needs_second_person`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** default policy
- **Steps:** tier 2, `authored_by == approved_by == "alice"`
- **Expected:** accepted — `REVIEW` means "someone must look, but not
  necessarily another person"
- **Why:** the difference between `REVIEW` and `MAKER_CHECKER` is exactly this,
  and conflating them makes tier 2 unusable for a one-person domain

### SEM-102 · A Tier 1 declaration cannot be approved by its own author
- **Area:** `semantic/policy.py::ApprovalPolicy.check`
- **Type:** security
- **Priority:** P1
- **Precondition:** default policy
- **Steps:** tier 1, `authored_by == approved_by == "alice"`
- **Expected:** `ValidationError` "cannot be approved by its own author",
  context carrying both ids, remedy calling segregation of duties a control
- **Why:** the module's headline claim, and the only thing making a Tier 1
  declaration an auditable record rather than one person's assertion

### SEM-103 · A Tier 1 declaration with a second approver is accepted
- **Area:** `semantic/policy.py::ApprovalPolicy.check`
- **Type:** functional
- **Priority:** P1
- **Precondition:** default policy
- **Steps:** `authored_by="alice"`, `approved_by="bob"`
- **Expected:** returns
- **Why:** the counterfactual to SEM-102 — a rule that refuses everything is not
  segregation of duties

### SEM-104 · A Tier 1 declaration with no author is approved by anyone
- **Area:** `semantic/policy.py::ApprovalPolicy.check`
- **Type:** security
- **Priority:** P1
- **Precondition:** default policy
- **Steps:** `authored_by=None`, `approved_by="alice"`
- **Expected:** currently accepted — `approved_by == authored_by` is
  `"alice" == None`, which is false
- **Why:** an anonymous author defeats maker-checker by omission, and the
  service layer's `authored_by` is optional at every call site

### SEM-105 · A Tier 1 declaration authored and approved by nobody is refused
- **Area:** `semantic/policy.py::ApprovalPolicy.check`
- **Type:** negative
- **Priority:** P1
- **Precondition:** default policy
- **Steps:** both `None`
- **Expected:** `ValidationError` on the missing approver (the first branch)
- **Why:** the empty-string and `None` cases must both fail the `not approved_by`
  test — an approver of `""` is not an approver

### SEM-106 · An unknown criticality falls through to no approval
- **Area:** `semantic/policy.py::ApprovalPolicy.for_criticality`
- **Type:** negative
- **Priority:** P1
- **Precondition:** default policy
- **Steps:** `for_criticality(0)`, `for_criticality(5)`, `for_criticality(-1)`
- **Expected:** currently `ApprovalRequirement.NONE` — the `.get(tier, NONE)`
  default fails open
- **Why:** the service layer accepts `criticality: int` unvalidated, so a
  declaration created with `criticality=0` skips maker-checker entirely; failing
  open on an unrecognised tier is the wrong direction for a governance control

### SEM-107 · A non-default policy is honoured
- **Area:** `semantic/policy.py::ApprovalPolicy`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `ApprovalPolicy(tier_three=MAKER_CHECKER)`
- **Steps:** construct a service with it; declare a tier 3 dataset self-approved
- **Expected:** refused
- **Why:** the policy is injected into every service; a service that builds its
  own default silently would ignore a configured regime

### SEM-108 · The requirement is reported, not just enforced
- **Area:** `semantic/policy.py::ApprovalPolicy.check`
- **Type:** contract
- **Priority:** P2
- **Precondition:** default policy
- **Steps:** trigger the tier 1 refusal
- **Expected:** `context` carries `criticality` and `requirement`, so a caller
  can render "this needs a second approver" before the user fills the form
- **Why:** a refusal after the work is done is the worst place to state a rule

### SEM-109 · `what` names the object in the message
- **Area:** `semantic/policy.py::ApprovalPolicy.check`
- **Type:** functional
- **Priority:** P3
- **Precondition:** default policy
- **Steps:** call with `what="journey declaration"`, `"dataset amendment"`,
  `"relationship declaration"`
- **Expected:** the phrase appears in the message
- **Why:** four services share one policy, and an unqualified "declaration"
  leaves the user hunting for which

---

## `semantic/conflict.py` — two datasets claiming one meaning

### SEM-110 · One claimant produces no conflict
- **Area:** `semantic/conflict.py::ConflictDetector.detect`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** one attribute mapped to `Party.LEI`
- **Steps:** `detect(property_id, name, [attribute])`
- **Expected:** `[]` — "one claimant cannot disagree with itself"
- **Why:** the first mapping in an estate must not raise a governance finding

### SEM-111 · Zero claimants produce no conflict
- **Area:** `semantic/conflict.py::ConflictDetector.detect`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a declared property nothing maps to
- **Steps:** `detect(..., [])`
- **Expected:** `[]`
- **Why:** an unmapped property is a coverage gap, reported elsewhere, not a
  conflict

### SEM-112 · Two attributes agreeing on everything produce no conflict
- **Area:** `semantic/conflict.py::ConflictDetector.detect`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two attributes, identical semantic type, unit, optionality,
  sensitivity, domain, both defined
- **Steps:** detect
- **Expected:** `[]`
- **Why:** the counterfactual — a detector that fires on agreement is noise

### SEM-113 · A unit mismatch is critical
- **Area:** `semantic/conflict.py::ConflictKind.severity`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two attributes with units `EUR` and `EUR_THOUSANDS`
- **Steps:** detect; read severity
- **Expected:** one `UNIT` conflict, severity `critical`
- **Why:** "two attributes that agree on everything except that one is in
  thousands will reconcile perfectly for years and be wrong by three orders of
  magnitude"

### SEM-114 · A semantic-type mismatch is critical
- **Area:** `semantic/conflict.py::ConflictDetector.COMPARED`
- **Type:** functional
- **Priority:** P1
- **Precondition:** one attribute typed `lei`, another `bic`
- **Steps:** detect
- **Expected:** one `SEMANTIC_TYPE` conflict, severity `critical`
- **Why:** two different identifiers claiming to be the same canonical property
  means one of the two mappings is wrong

### SEM-115 · An optionality mismatch is minor
- **Area:** `semantic/conflict.py::ConflictKind.severity`
- **Type:** functional
- **Priority:** P2
- **Precondition:** one `mandatory`, one `optional`
- **Steps:** detect
- **Expected:** one `OPTIONALITY` conflict, severity `minor`
- **Why:** the same property can legitimately be mandatory in one dataset and
  not another; it is worth showing and not worth escalating

### SEM-116 · A sensitivity mismatch is major
- **Area:** `semantic/conflict.py::ConflictKind.severity`
- **Type:** security
- **Priority:** P1
- **Precondition:** one attribute `pii`, another `internal`
- **Steps:** detect
- **Expected:** one `SENSITIVITY` conflict, severity `major`
- **Why:** the same real-world value masked in one dataset and exported in
  another is a disclosure, and the estate is the only place it is visible

### SEM-117 · An attribute that declares nothing is excluded from the comparison
- **Area:** `semantic/conflict.py::ConflictDetector.detect`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** one attribute with `unit="EUR"`, one with `unit=None`
- **Steps:** detect
- **Expected:** no `UNIT` conflict — `None` values are filtered before the
  distinct count
- **Why:** silence is not disagreement; treating an undeclared unit as a
  conflicting one would make every partially-described estate red

### SEM-118 · Criticality is listed as a conflict kind and never detected
- **Area:** `semantic/conflict.py::ConflictDetector.COMPARED`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** two attributes whose datasets are Tier 1 and Tier 4
- **Steps:** detect
- **Expected:** no `CRITICALITY` conflict — the enum member and its severity
  exist, and the field is not in `COMPARED`
- **Why:** the vocabulary promises a detection the detector does not perform; an
  operator reading `ConflictKind` will believe it is checked

### SEM-119 · Two code-list domains pointing at the same list agree
- **Area:** `semantic/conflict.py::_domain_signature`
- **Type:** functional
- **Priority:** P2
- **Precondition:** one domain with `codelist_ref="iso4217"`, another with the
  same ref and a different spelling of `allowed_values`
- **Steps:** detect
- **Expected:** no `VALUE_DOMAIN` conflict — the signature compares what the
  domain constrains, not how it was written
- **Why:** the docstring's claim; comparing raw dicts would report a conflict on
  every pair of equivalent declarations

### SEM-120 · Two code lists with different explicit values disagree
- **Area:** `semantic/conflict.py::_domain_signature`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `("BUY","SELL")` against `("BUY","SELL","CANCEL")`
- **Steps:** detect
- **Expected:** one `VALUE_DOMAIN` conflict, severity `major`
- **Why:** an extra permitted value in one dataset is where a downstream
  membership control starts failing on legitimate rows

### SEM-121 · Ranges and patterns are compared by their constraint
- **Area:** `semantic/conflict.py::_domain_signature`
- **Type:** functional
- **Priority:** P3
- **Precondition:** ranges `0..100` and `0..1000`; patterns `^A` and `^B`
- **Steps:** detect each pair
- **Expected:** a `VALUE_DOMAIN` conflict for each
- **Why:** the signature has a branch per kind and the fall-through returns the
  kind alone — two `free_text` domains must not conflict

### SEM-122 · Some attributes defined and some not is an information finding
- **Area:** `semantic/conflict.py::ConflictDetector.detect`
- **Type:** functional
- **Priority:** P2
- **Precondition:** three attributes on one property, one with an empty
  `definition`
- **Steps:** detect
- **Expected:** a `DEFINITION_ABSENT` conflict, severity `info`, listing only the
  undefined attribute
- **Why:** the undefined ones "are inheriting a meaning nobody checked they
  agree with"

### SEM-123 · No attribute defined produces no `DEFINITION_ABSENT`
- **Area:** `semantic/conflict.py::ConflictDetector.detect`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** two attributes, both with empty definitions
- **Steps:** detect
- **Expected:** no `DEFINITION_ABSENT` — the guard is
  `undefined and len(undefined) < len(attributes)`
- **Why:** universal silence is a maturity problem, scored by
  `MaturityStage.INTERPRETED`, not a disagreement

### SEM-124 · A whitespace-only definition counts as absent
- **Area:** `semantic/conflict.py::ConflictDetector.detect`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** one definition `"   "`, one real
- **Steps:** detect
- **Expected:** a `DEFINITION_ABSENT` conflict — `(a.definition or "").strip()`
- **Why:** a space typed into a form to dismiss it is not a definition

### SEM-125 · `worst_severity` orders info < minor < major < critical
- **Area:** `semantic/conflict.py::ConflictDetector.worst_severity`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a list holding one of each
- **Steps:** call it; then call it with `[]`
- **Expected:** `"critical"`; then `None`
- **Why:** it drives the estate scorecard's headline, and an empty list must not
  raise

### SEM-126 · A conflict renders as a sentence naming the attributes
- **Area:** `semantic/conflict.py::SemanticConflict.render`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a unit conflict across three attributes, two agreeing
- **Steps:** `render()`
- **Expected:** "2 different unit values across 3 attributes (…)", attributes
  sorted by id, names substituted where known
- **Why:** the count of *distinct* values is what tells a reader whether this is
  one outlier or a three-way argument

### SEM-127 · The detector reports and never resolves
- **Area:** `semantic/conflict.py::ConflictDetector`
- **Type:** contract
- **Priority:** P1
- **Precondition:** any conflict
- **Steps:** detect; then re-read both attributes
- **Expected:** neither attribute has been amended, no winner chosen, no
  suppression recorded
- **Why:** "which of two definitions is right is a business decision, and a tool
  that picks one silently has made that decision on the business's behalf"

---

## `semantic/maturity.py` — the estate score and what to do next

### SEM-128 · An empty estate scores zero without dividing by zero
- **Area:** `semantic/maturity.py::EstateFacts.stage_completion`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `EstateFacts()` — no datasets
- **Steps:** `assess("estate", facts)`
- **Expected:** every stage 0.0, score 0.0, stage `DISCOVERED`, no
  `ZeroDivisionError`
- **Why:** "a domain with no datasets has not failed to mature; it has nothing
  to mature" — and this is the state of every fresh install

### SEM-129 · A fully described estate scores 100%
- **Area:** `semantic/maturity.py::MaturityAssessor.assess`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** every count saturated, `relationships_confirmed >=
  datasets // 2`
- **Steps:** assess
- **Expected:** score 1.0, stage `JOURNEYED`, `actions == ()`
- **Why:** a score that cannot reach its own ceiling is a score people stop
  working towards

### SEM-130 · The weights sum to one
- **Area:** `semantic/maturity.py::STAGE_WEIGHTS`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** `sum(STAGE_WEIGHTS.values())`
- **Expected:** 1.0; `RELATED` is the heaviest at 0.30
- **Why:** relationships "weigh most because they generate the highest-value
  controls in the product, and nothing else can generate them" — a weighting
  that does not reflect that makes the next-action ranking argue with the score

### SEM-131 · `SHAPED` is 60% grain and 40% rhythm
- **Area:** `semantic/maturity.py::EstateFacts.stage_completion`
- **Type:** functional
- **Priority:** P2
- **Precondition:** 10 datasets, all with grain, none with rhythm
- **Steps:** read `completion[SHAPED]`
- **Expected:** 0.6
- **Why:** the split is the only place the relative value of the two
  declarations is stated

### SEM-132 · One confirmed relationship per two datasets is full marks
- **Area:** `semantic/maturity.py::EstateFacts.stage_completion`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** 10 datasets, 5 confirmed relationships
- **Steps:** read `completion[RELATED]`
- **Expected:** 1.0; with 6 relationships still 1.0 (the ratio is clamped)
- **Why:** relationships are declared *between* things, so the population is
  inherently smaller; demanding one per dataset would cap every estate below
  the ceiling

### SEM-133 · A single dataset expects at least one relationship
- **Area:** `semantic/maturity.py::EstateFacts.stage_completion`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** 1 dataset, 0 relationships
- **Steps:** read `completion[RELATED]`
- **Expected:** 0.0 — `max(1, datasets // 2)` makes the denominator 1
- **Why:** `datasets // 2 == 0` would divide by zero; the guard must hold for
  one dataset and for two

### SEM-134 · A stage counts as reached at 80%
- **Area:** `semantic/maturity.py::MaturityAssessor._reached_stage`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `NAMED` at 0.80 exactly, `SHAPED` at 0.79
- **Steps:** assess
- **Expected:** stage `NAMED`
- **Why:** "insisting on 100% would leave every real estate stuck at stage one
  for ever, because there is always one dataset nobody has got to"

### SEM-135 · Stages are reached in order and the walk stops at the first gap
- **Area:** `semantic/maturity.py::MaturityAssessor._reached_stage`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `NAMED` 1.0, `SHAPED` 0.2, `INTERPRETED` 1.0, `RELATED` 1.0
- **Steps:** assess
- **Expected:** stage `NAMED` — the loop `break`s at `SHAPED`
- **Why:** progressive formalisation is a ladder; claiming stage 4 while stage 2
  is undone would flatter an estate whose relationships rest on undeclared
  grains

### SEM-136 · Unmeasured stages do not count as reached
- **Area:** `semantic/maturity.py::MaturityAssessor._reached_stage`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a completion dict missing a key
- **Steps:** assess
- **Expected:** `completion.get(stage, 0.0)` yields 0.0 and the walk stops
- **Why:** a missing measurement must fail closed

### SEM-137 · Tier 1 datasets without a grain rank first
- **Area:** `semantic/maturity.py::MaturityAssessor.next_actions`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 3 Tier 1 datasets with no grain, 40 other gaps
- **Steps:** read `actions[0]`
- **Expected:** the Tier 1 grain action, `estimated_controls == 9`,
  `value_per_item == 3.0`
- **Why:** highest criticality and the most generative declaration — the answer
  to "what do I do on Monday morning"

### SEM-138 · The non-Tier-1 grain action excludes the Tier 1 ones
- **Area:** `semantic/maturity.py::MaturityAssessor.next_actions`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** 10 datasets, 3 Tier 1, none with a grain
- **Steps:** read both grain actions
- **Expected:** 3 and 7, not 3 and 10
- **Why:** double-counting the same datasets in two actions inflates the
  estimate and makes the list read as longer than the work

### SEM-139 · Actions are ranked by controls per item of effort
- **Area:** `semantic/maturity.py::MaturityAssessor.next_actions`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a mixed estate producing at least five actions
- **Steps:** read the list
- **Expected:** sorted by `-value_per_item` then `effort_items`; a grain action
  (3.0) outranks a rhythm action (2.0) outranks an interpret action (1.0)
- **Why:** "what to do next, stated in controls gained rather than forms to fill"

### SEM-140 · The unbound action is ranked last and claims no controls
- **Area:** `semantic/maturity.py::NextAction.value_per_item`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** unbound datasets present
- **Steps:** read that action
- **Expected:** `estimated_controls == 0`, `value_per_item == 0.0`, last in the
  list
- **Why:** connecting a source unblocks controls rather than creating them, and
  claiming otherwise would inflate every estimate beside it

### SEM-141 · `value_per_item` with zero effort does not divide by zero
- **Area:** `semantic/maturity.py::NextAction.value_per_item`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `NextAction(effort_items=0, estimated_controls=5)`
- **Steps:** read the property
- **Expected:** 0.0
- **Why:** the sort key reads it for every action

### SEM-142 · The concept-mapping action appears only once something is defined
- **Area:** `semantic/maturity.py::MaturityAssessor.next_actions`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** 100 attributes, 0 defined, 0 mapped
- **Steps:** read the actions
- **Expected:** no `MAPPED` action — the guard is `unmapped > 0 and
  attributes_defined > 0`
- **Why:** asking somebody to map attributes to concepts before any attribute
  has a definition is asking them to do stage 5 before stage 3

### SEM-143 · `explain()` lists every component with its weight
- **Area:** `semantic/maturity.py::MaturityScore.explain`
- **Type:** contract
- **Priority:** P2
- **Precondition:** any assessment
- **Steps:** read the list
- **Expected:** six lines, one per weighted stage, each showing percentage and
  weight
- **Why:** "so the number is never a black box" — it is a management metric and
  will be argued with

### SEM-144 · The score is a pure function of the facts
- **Area:** `semantic/maturity.py::MaturityAssessor.assess`
- **Type:** contract
- **Priority:** P2
- **Precondition:** one `EstateFacts` value
- **Steps:** assess twice, compare; assess with no database present
- **Expected:** identical, and no I/O
- **Why:** "testable without a database, and explainable without re-running a
  query"

### SEM-145 · Percent rounds rather than truncates
- **Area:** `semantic/maturity.py::MaturityScore.percent`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** score 0.005, then 0.994
- **Steps:** read `percent`
- **Expected:** 1 and 99 — `round`, not `int`
- **Why:** a score reported as 0% while work has been done is the fastest way to
  lose the audience for the metric

### SEM-146 · The control estimates are approximations, and are labelled as such
- **Area:** `semantic/maturity.py::MaturityAssessor.CONTROLS_PER_*`
- **Type:** documentation
- **Priority:** P3
- **Precondition:** none
- **Steps:** compare `CONTROLS_PER_GRAIN == 3` against what Γ actually emits for
  a two-column grain (1 uniqueness + 2 completeness = 3, before coalescing)
- **Expected:** approximately right for arity 2; wrong for arity 1 (2 controls)
  and arity 4 (5 controls)
- **Why:** the estimates are "used only to *rank* actions, so being approximately
  right is enough" — the case exists to confirm nobody has started quoting them
  as a count

---

## `semantic/services/base.py` — slugs and the audit obligation

### SEM-147 · A business name becomes a readable slug
- **Area:** `semantic/services/base.py::slugify`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `"End-of-day Positions"`, `"RISK.POSITIONS_EOD"`, `"  spaced  "`
- **Expected:** `end_of_day_positions`, `risk_positions_eod`, `spaced` — no
  leading or trailing underscore
- **Why:** the slug is the URL, the GitOps filename, the cross-reference, and
  the `target` of every control Γ writes

### SEM-148 · Accents are folded rather than dropped into nothing
- **Area:** `semantic/services/base.py::slugify`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `"Société Générale Positions"`
- **Expected:** `societe_generale_positions`
- **Why:** NFKD plus ASCII-ignore; a European estate is the target market

### SEM-149 · A name with no usable characters is refused
- **Area:** `semantic/services/base.py::slugify`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `"---"`, `"住所"`, `"  "`
- **Expected:** `ValidationError` naming the value
- **Why:** an empty slug collides with every other empty slug and produces a
  file called `.yaml`

### SEM-150 · A slug is capped at 128 characters
- **Area:** `semantic/services/base.py::slugify`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** a 300-character name; then two names differing only after
  character 128
- **Expected:** truncated to 128; the two names collide, and `declare` reports a
  `ConflictError` rather than silently overwriting
- **Why:** truncation makes uniqueness a function of a prefix, and the conflict
  path is the only thing that makes that safe

### SEM-151 · Every mutation writes an audit event
- **Area:** `semantic/services/base.py::SemanticService._audit`
- **Type:** security
- **Priority:** P1
- **Precondition:** a tenant and a principal
- **Steps:** declare, amend, correct, declare an attribute, declare and confirm
  and reject a relationship, declare a concept, map an attribute, declare a
  journey, change its steps, configure a connection, bind a dataset, record
  drift
- **Expected:** an audit row for each, with `action`, `object_kind`, `object_id`,
  `actor_id` and a detail payload
- **Why:** "a declaration nobody can attribute is a declaration an auditor will
  not accept" — enumerate every service method and find the ones that write none

### SEM-152 · `propose_discovered` writes no audit event
- **Area:** `semantic/services/relationships.py::RelationshipService.propose_discovered`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a discovered relationship
- **Steps:** call it; read the audit log
- **Expected:** currently no audit row — unlike `declare`, `confirm` and
  `reject`
- **Why:** the system acting on its own behalf is exactly what `actor_kind`
  exists to record, and a proposal that appears with no trace is the one a
  steward will ask about

### SEM-153 · `bind_attribute` writes no audit event
- **Area:** `semantic/services/graph.py::BindingService.bind_attribute`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a dataset, an attribute and a connection
- **Steps:** bind an attribute; read the audit log
- **Expected:** currently no audit row, where `bind_dataset` writes one
- **Why:** an attribute binding carries a `transform`, which is the field most
  able to change what a control measures

### SEM-154 · A system action is recorded as a system action
- **Area:** `semantic/services/base.py::SemanticService._audit`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a connection and a binding
- **Steps:** `record_health` and `record_drift`
- **Expected:** `actor_kind == "system"` and `actor_id is None`
- **Why:** "a health check or a drift detection has no human author, and
  recording one would be a small lie in a permanent record"

---

## `semantic/services/datasets.py` — declaring, amending, correcting

### SEM-155 · A dataset can be declared with a name alone
- **Area:** `semantic/services/datasets.py::DatasetService.declare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a tenant
- **Steps:** `declare(tenant_id, name="Global Positions")`
- **Expected:** created; `shape == "unbound"`, `criticality == 4`,
  `temporality == "snapshot"`, `sensitivity == "internal"`,
  `authoritativeness == "unknown"`, `lifecycle_state == "proposed"`
- **Why:** every default here is a control-generating decision made on the user's
  behalf; enumerate them so a change is visible

### SEM-156 · An unbound dataset is a first-class state
- **Area:** `semantic/services/datasets.py::DatasetService.declare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a tenant, no connection configured
- **Steps:** declare with no binding; then read the estate map, the coverage
  gaps and a relationship declared against it
- **Expected:** it appears on the map, participates in relationships, and shows
  in `coverage_gaps()["unbound"]`
- **Why:** docs/03 §2.1 — "architects map the estate first, connectivity
  follows"; a product that requires a connection to declare a dataset is a
  physical-first tool

### SEM-157 · Declaring approved makes it active; unapproved leaves it proposed
- **Area:** `semantic/services/datasets.py::DatasetService.declare`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a tenant
- **Steps:** declare a Tier 3 dataset with `approved_by=None`, then one with
  `approved_by="bob"`
- **Expected:** `lifecycle_state` `proposed` then `active`
- **Why:** the state is derived from the approval rather than passed in, so an
  unapproved declaration cannot present itself as live

### SEM-158 · A duplicate name in one tenant is refused
- **Area:** `semantic/services/datasets.py::DatasetService.declare`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `Global Positions` declared
- **Steps:** declare `global positions`, then `Global-Positions`
- **Expected:** `ConflictError` for both — the check is on the slug
- **Why:** two datasets whose names differ only in punctuation generate controls
  against the same target

### SEM-159 · The same name in two tenants is fine
- **Area:** `semantic/services/datasets.py::DatasetService.declare`
- **Type:** security
- **Priority:** P1
- **Precondition:** two tenants
- **Steps:** declare the same name in each
- **Expected:** both created; neither visible to the other
- **Why:** `by_slug` is tenant-scoped, and a cross-tenant uniqueness constraint
  would leak the existence of another estate's datasets

### SEM-160 · A Tier 1 dataset self-approved is refused before anything is written
- **Area:** `semantic/services/datasets.py::DatasetService.declare`
- **Type:** security
- **Priority:** P1
- **Precondition:** a tenant
- **Steps:** `criticality=1`, `authored_by="alice"`, `approved_by="alice"`
- **Expected:** `ValidationError`; no dataset row, no version row, no audit event
- **Why:** the policy check runs after the slug conflict check and before
  `create` — a refusal that leaves a half-written declaration is worse than none

### SEM-161 · An unvalidated criticality reaches the database
- **Area:** `semantic/services/datasets.py::DatasetService.declare`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a tenant
- **Steps:** `criticality=0`, then `criticality=9`
- **Expected:** the policy returns `NONE` (SEM-106) and the value reaches the
  `CHECK` constraint on `sem_dataset_version` — record whether that is a clean
  refusal or a raw database error
- **Why:** the service signature is `criticality: int = 4` with no coercion to
  `Criticality`, so the enum's guarantee stops at the service boundary

### SEM-162 · An unvalidated shape reaches the database
- **Area:** `semantic/services/datasets.py::DatasetService.declare`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a tenant
- **Steps:** `shape="spreadsheet"`
- **Expected:** refused by the column `CHECK` — round 1 finding Q-27 records
  this reaching the console as a 500
- **Why:** the shape decides which control family applies; an unknown one
  produces a dataset Γ treats as bound to nothing

### SEM-163 · An unvalidated temporality, sensitivity or authoritativeness
- **Area:** `semantic/services/datasets.py::DatasetService.declare`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a tenant
- **Steps:** `temporality="bitemporal"`, `sensitivity="secret"`,
  `authoritativeness="best_effort"`
- **Expected:** the database refuses each; and if one reaches storage,
  `derive/persisted.py::_enum` silently downgrades it to the default rather than
  failing the page (DER-011)
- **Why:** the fallback is deliberate at read time and makes a bad write
  invisible — the two together mean a mistyped sensitivity produces controls that
  retain samples of PII

### SEM-164 · An amendment without a reason is refused
- **Area:** `semantic/services/datasets.py::DatasetService.amend`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a declared dataset
- **Steps:** `reason=""`, then `reason="   "`
- **Expected:** `ValidationError` "an amendment must say why", remedy calling an
  unexplained change an audit finding
- **Why:** the `change_reason` column has a default of `""`, so the service is
  the only thing that makes the reason real

### SEM-165 · A correction without a reason is refused
- **Area:** `semantic/services/datasets.py::DatasetService.correct`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a declared dataset
- **Steps:** `reason=""`
- **Expected:** `ValidationError` "a correction must say what was wrong"
- **Why:** the record is permanent and the correction is the version that
  survives

### SEM-166 · An amendment checks the policy against the *new* criticality
- **Area:** `semantic/services/datasets.py::DatasetService.amend`
- **Type:** security
- **Priority:** P1
- **Precondition:** a Tier 4 dataset
- **Steps:** amend with `criticality=1`, self-approved
- **Expected:** refused — `changes.get("criticality", current.criticality)`
- **Why:** promoting a dataset to Tier 1 is the change most in need of a second
  pair of eyes, and reading the old value would let it through

### SEM-167 · An amendment that does not touch criticality uses the current one
- **Area:** `semantic/services/datasets.py::DatasetService.amend`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a Tier 1 dataset
- **Steps:** amend the description only, self-approved
- **Expected:** refused — a Tier 1 dataset's description is still a Tier 1
  declaration
- **Why:** the other half of SEM-166; demoting the check to the changed fields
  would make every Tier 1 amendment unreviewed

### SEM-168 · A correction bypasses the approval policy entirely
- **Area:** `semantic/services/datasets.py::DatasetService.correct`
- **Type:** security
- **Priority:** P1
- **Precondition:** a Tier 1 dataset
- **Steps:** `correct(dataset_id, reason="wrong grain", authored_by="alice")`
  with no approver
- **Expected:** currently succeeds — `correct` never calls `self._policy.check`,
  where `declare` and `amend` both do
- **Why:** a correction can change the grain, the criticality and the
  sensitivity of a Tier 1 declaration with one signature, which is the control
  SEM-102 exists to enforce, routed around

### SEM-169 · Amending a dataset that does not exist is a `NotFoundError`
- **Area:** `semantic/services/datasets.py::DatasetService.amend`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a tenant
- **Steps:** amend an invented id
- **Expected:** `NotFoundError` from `require_current`, with a remedy
- **Why:** `require_current` is tenant-scoped, so this is also the cross-tenant
  case: another estate's id must be indistinguishable from a missing one

### SEM-170 · Amending another tenant's dataset is a `NotFoundError`, not a 403
- **Area:** `semantic/services/datasets.py::DatasetService.amend`
- **Type:** security
- **Priority:** P1
- **Precondition:** two tenants, a dataset in each
- **Steps:** amend tenant A's dataset id while acting as tenant B
- **Expected:** `NotFoundError`; nothing written; the message does not confirm
  the id exists
- **Why:** round 1 finding Q-04 was four by-parent reads that filtered on the
  parent and never on the estate — the write paths need the same enumeration

### SEM-171 · An attribute cannot be declared on a missing dataset
- **Area:** `semantic/services/datasets.py::DatasetService.declare_attribute`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a tenant
- **Steps:** declare an attribute against an invented dataset id
- **Expected:** `NotFoundError`, remedy "declare the dataset before declaring
  its attributes"
- **Why:** an orphan attribute is invisible to Γ and to coverage, and would
  quietly never generate a control

### SEM-172 · A duplicate attribute name on one dataset is refused
- **Area:** `semantic/services/datasets.py::DatasetService.declare_attribute`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a dataset with `amount` declared
- **Steps:** declare `amount` again
- **Expected:** `ConflictError`
- **Why:** two declarations of one column produce two controls on the same rows
  with different reasons — the duplicate-alert failure `_coalesce` exists to
  prevent, arriving from the declaration side

### SEM-173 · Attribute names are matched exactly, not by slug
- **Area:** `semantic/services/datasets.py::DatasetService.declare_attribute`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a dataset with `amount`
- **Steps:** declare `Amount`, then `AMOUNT`
- **Expected:** both accepted — the check is `a.name == name`
- **Why:** attribute names are physical column names on a case-insensitive
  engine; two attributes differing only in case bind to one column

### SEM-174 · The ordinal is the declaration order
- **Area:** `semantic/services/datasets.py::DatasetService.declare_attribute`
- **Type:** functional
- **Priority:** P3
- **Precondition:** a dataset
- **Steps:** declare three attributes; read `ordinal`
- **Expected:** 0, 1, 2 — `ordinal=len(existing)`
- **Why:** it drives display order; after a retirement the count and the highest
  ordinal diverge, so confirm what a fourth declaration gets

### SEM-175 · An attribute's extra fields pass through unvalidated
- **Area:** `semantic/services/datasets.py::DatasetService.declare_attribute`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a dataset
- **Steps:** `**extra` carrying `optionality="sometimes"`,
  `value_domain_json={"kind": "colour"}`, `numeric_scale=-3`,
  `currency_attribute="no_such_column"`
- **Expected:** the first two meet a column `CHECK` or land in JSON unchecked;
  the last reaches Γ, which reports it as `Unsatisfiable attribute.currency`
  (DER-061)
- **Why:** `**extra` is the widest hole in the service layer, and the fields it
  carries are the ones that generate controls

### SEM-176 · Declaring an attribute writes the CDE mark into the audit detail
- **Area:** `semantic/services/datasets.py::DatasetService.declare_attribute`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a dataset
- **Steps:** declare with `is_cde=True`, `obligations=["FR Y-14Q"]`
- **Expected:** audit detail carries `is_cde`; the obligations are stored in
  `obligations_json`
- **Why:** a CDE raises the severity floor, blocks on failure and retains full
  evidence — three behaviours that turn on one boolean

---

## Bitemporality — amend, correct, and replaying a belief

### SEM-177 · A first declaration opens version 1, valid now, believed now
- **Area:** `db/dao/versioned.py::VersionedDao.create`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a tenant
- **Steps:** declare a dataset; read the version row
- **Expected:** `version == 1`, `valid_to is None`, `superseded_at is None`,
  `is_current is True`
- **Why:** the invariant every temporal read depends on

### SEM-178 · A declaration can be backdated
- **Area:** `db/dao/versioned.py::VersionedDao.create`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a tenant
- **Steps:** declare with `valid_from` a year ago
- **Expected:** `valid_from` honoured, `recorded_at` is now
- **Why:** an estate being mapped retrospectively is the normal case, and the
  two axes must be able to disagree from the first version

### SEM-179 · An amendment closes one validity period and opens the next
- **Area:** `db/dao/versioned.py::VersionedDao.amend`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a declared dataset
- **Steps:** amend the grain with `effective_from = T`
- **Expected:** v1 has `valid_to == T` and `superseded_at is None`; v2 has
  `valid_from == T`, both nulls open; exactly one current row
- **Why:** "the world changed" — both versions remain believed, because neither
  was ever wrong

### SEM-180 · An amendment effective before the version it replaces is refused
- **Area:** `db/dao/versioned.py::VersionedDao.amend`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a dataset whose current version began yesterday
- **Steps:** amend with `effective_from` a week ago
- **Expected:** `ConflictError`, context carrying both dates, remedy offering a
  correction instead
- **Why:** an inverted validity period makes `was_valid_at` false for every
  moment, so the declaration exists and resolves to nothing

### SEM-181 · An amendment effective exactly at the current `valid_from` is accepted
- **Area:** `db/dao/versioned.py::VersionedDao.amend`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a dataset with a known `valid_from`
- **Steps:** amend with `effective_from == current.valid_from`
- **Expected:** accepted — the check is `effective < current.valid_from`; v1
  ends up with a zero-length validity period
- **Why:** a zero-length version is queryable on neither axis; confirm whether
  that is intended or should be a correction

### SEM-182 · A correction supersedes without touching validity
- **Area:** `db/dao/versioned.py::VersionedDao.correct`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a declared dataset
- **Steps:** correct the grain
- **Expected:** v1 has `superseded_at` set and `valid_to` unchanged; v2 inherits
  `valid_from` and `valid_to` exactly
- **Why:** "we were wrong" — the mistaken version stays on the transaction-time
  axis so an evidence record from before the correction still resolves

### SEM-183 · A correction to a dataset that has none is a `NotFoundError`
- **Area:** `db/dao/versioned.py::VersionedDao.correct`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a retired dataset (no current version)
- **Steps:** correct it
- **Expected:** `NotFoundError` "has no current version to correct"
- **Why:** the brief's "a correction before a declaration existed" — the only
  honest answer is that there is nothing to correct

### SEM-184 · Retirement ends validity and destroys nothing
- **Area:** `db/dao/versioned.py::VersionedDao.retire`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a declared dataset with two versions
- **Steps:** retire it; read `history`, `current`, `valid_at` for a past moment
- **Expected:** `current` is `None`; `history` returns both versions;
  `valid_at(past)` still resolves
- **Why:** "a retired dataset's history is still needed to interpret evidence
  produced while it existed"

### SEM-185 · Retiring twice is not an error and does not change the record
- **Area:** `db/dao/versioned.py::VersionedDao.retire`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a retired dataset
- **Steps:** retire again
- **Expected:** returns `None`; the first `valid_to` is unchanged
- **Why:** idempotence on a destructive-looking verb, and the second call must
  not move the retirement date

### SEM-186 · `valid_at` answers with the benefit of corrections
- **Area:** `db/temporal.py::TemporalQuery.believed_now_valid_at`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a dataset amended in April and then corrected in June
- **Steps:** `valid_at(dataset_id, 31 March)`
- **Expected:** the March declaration **as corrected** — superseded rows are
  excluded
- **Why:** "what was the grain on 31 March?" is the usual historical question
  and is asked with everything known since

### SEM-187 · `as_of` answers what was believed at the time
- **Area:** `db/temporal.py::TemporalQuery.as_of`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the same dataset
- **Steps:** `as_of(dataset_id, valid_at=31 March, known_at=1 May)`
- **Expected:** the *pre-correction* March declaration
- **Why:** "a control that ran in March must resolve the declaration March
  believed in, not the one a correction in June produced — otherwise the replay
  silently answers a different question"

### SEM-188 · The two temporal reads differ after a correction, and agree before one
- **Area:** `db/dao/versioned.py::VersionedDao.valid_at`, `.as_of`
- **Type:** contract
- **Priority:** P1
- **Precondition:** one dataset amended but never corrected; another corrected
- **Steps:** run both reads on both
- **Expected:** identical answers on the first, different on the second
- **Why:** the counterfactual — a `known_at` that changes nothing is a parameter
  nobody can rely on, which is round 1 finding Q-25 from the other side

### SEM-189 · `known_at` alone is not silently discarded
- **Area:** `db/dao/versioned.py::VersionedDao.as_of`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a corrected dataset
- **Steps:** ask for a belief as at the year 2000 with no `valid_at`
- **Expected:** either a refusal or an empty answer — never the current version
- **Why:** round 1 finding Q-25: "a wrong answer rather than a refusal, in the
  product whose thesis is evidence replay"

### SEM-190 · `as_of` before the first `recorded_at` returns nothing
- **Area:** `db/temporal.py::TemporalQuery.as_of`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a dataset declared today
- **Steps:** `as_of(valid_at=today, known_at=yesterday)`
- **Expected:** `None` — we did not believe anything about it yesterday
- **Why:** "a correction before a declaration existed" inverted: a belief query
  predating the declaration must not invent one

### SEM-191 · History is ordered oldest first, by record time then version
- **Area:** `db/temporal.py::TemporalQuery.all_versions`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a dataset with a declaration, an amendment and a correction
- **Steps:** read `history`
- **Expected:** three rows in that order, versions 1, 2, 3; the superseded one
  still present with its `superseded_at`
- **Why:** the audit view — a history that hides the corrected version hides the
  thing the auditor came for

### SEM-192 · Version numbers increase on both paths
- **Area:** `db/dao/versioned.py::VersionedDao.amend`, `.correct`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a declared dataset
- **Steps:** amend, correct, amend
- **Expected:** versions 2, 3, 4 — a correction is not version 2 twice
- **Why:** the version number is the only thing distinguishing two rows with the
  same validity period

### SEM-193 · Exactly one current version exists at every moment
- **Area:** `schema/*.sql` partial unique index; `VersionedDao.amend`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** a declared dataset
- **Steps:** two concurrent amendments in separate units of work
- **Expected:** one succeeds, the other fails on the partial unique index rather
  than producing two current rows
- **Why:** "nothing is ever updated in place. A partial unique index in the
  schema enforces exactly one current version per entity, on both engines" — the
  flush ordering in `amend` exists for this and is worth proving

### SEM-194 · Provenance is recorded on every version
- **Area:** `db/temporal.py::Provenance.apply_to`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a declared, amended and corrected dataset
- **Steps:** read `authored_by`, `approved_by`, `approved_at`, `change_reason` on
  each version
- **Expected:** present on all three; the correction's `approved_by` is `None`
  because `correct` constructs `Provenance` without one (SEM-168)
- **Why:** the provenance is what a generated control cites when asked "why does
  this exist?"

### SEM-195 · A control's evidence resolves against the declaration it ran under
- **Area:** `db/dao/versioned.py::VersionedDao.as_of` + `derive/persisted.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a dataset whose grain was corrected after a control ran
- **Steps:** take the evidence record's `computed_at`; resolve the declaration
  `as_of(valid_at=computed_at, known_at=computed_at)`; regenerate
- **Expected:** the pre-correction grain and the control that actually ran
- **Why:** the entire justification for bitemporality; if this does not hold,
  one `updated_at` column would have done

---

## `semantic/services/graph.py` — concepts, journeys, connections, bindings

### SEM-196 · A concept is declared once per tenant
- **Area:** `semantic/services/graph.py::ConceptService.declare_concept`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `Party` declared
- **Steps:** declare `Party` again; then `party`
- **Expected:** `ConflictError` for the first; the second is accepted because
  the check is `by_name` and not by slug
- **Why:** two concepts differing only in case would host two vocabularies, and
  the conflict detector compares within a property rather than across concepts

### SEM-197 · A property cannot be declared on a missing concept
- **Area:** `semantic/services/graph.py::ConceptService.declare_property`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a tenant
- **Steps:** declare `ISIN` against an invented concept id
- **Expected:** `NotFoundError` with a remedy
- **Why:** an orphan property can still be mapped to, and would host a conflict
  nobody can navigate to

### SEM-198 · A duplicate property on one concept is refused
- **Area:** `semantic/services/graph.py::ConceptService.declare_property`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `Instrument.ISIN` declared
- **Steps:** declare `ISIN` again
- **Expected:** `ConflictError`
- **Why:** "author once, enforce everywhere" needs one canonical property per
  name

### SEM-199 · An attribute is mapped to a property
- **Area:** `semantic/services/graph.py::ConceptService.map_attribute`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a declared attribute and a declared property
- **Steps:** map them
- **Expected:** an amendment on the attribute setting `concept_property_id`,
  provenance reason "mapped to a canonical concept property", an audit event
- **Why:** the mapping is what makes conflict detection and estate-wide controls
  possible — stage 5 of progressive formalisation

### SEM-200 · Mapping to a missing property is refused
- **Area:** `semantic/services/graph.py::ConceptService.map_attribute`
- **Type:** negative
- **Priority:** P2
- **Precondition:** an attribute
- **Steps:** map to an invented property id
- **Expected:** `NotFoundError`
- **Why:** a dangling mapping is a claim about a meaning that does not exist

### SEM-201 · Mapping an attribute from another tenant
- **Area:** `semantic/services/graph.py::ConceptService.map_attribute`
- **Type:** security
- **Priority:** P1
- **Precondition:** two tenants with an attribute each
- **Steps:** map tenant B's attribute id while acting as tenant A, to A's
  property
- **Expected:** `NotFoundError` from the attribute amendment — the property
  check is tenant-scoped, and the amendment must be too
- **Why:** the property lookup and the attribute write are two different scopes
  in one method; only one is visibly checked in the source

### SEM-202 · `mapped_to_property` takes no tenant
- **Area:** `db/dao/semantic.py::AttributeDao.mapped_to_property`
- **Type:** security
- **Priority:** P1
- **Precondition:** two tenants whose attributes map to properties
- **Steps:** call it with a property id and inspect the estate of every row
  returned
- **Expected:** only the calling tenant's attributes; this is the read
  `EstateService.conflicts` uses to build the conflict report
- **Why:** round 1 finding Q-04 was exactly this shape — a by-parent read
  filtering on the parent and never on the estate

### SEM-203 · A journey orders datasets into a business process
- **Area:** `semantic/services/graph.py::JourneyService.declare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** three declared datasets
- **Steps:** declare a journey with three dataset steps
- **Expected:** created; steps renumbered 0, 1, 2; slug derived; audit written
- **Why:** business lineage a human declared, which is the only kind that
  crosses a mainframe

### SEM-204 · A journey step of an unknown kind is refused
- **Area:** `semantic/services/graph.py::JourneyService._validate_steps`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a tenant
- **Steps:** `kind="spreadsheet"`
- **Expected:** `ValidationError` naming the position and listing
  `dataset, black_box, manual`
- **Why:** the remedy enumerates the vocabulary, which is the only place it is
  written down

### SEM-205 · A dataset step with no dataset is refused
- **Area:** `semantic/services/graph.py::JourneyService._validate_steps`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a tenant
- **Steps:** `{"kind": "dataset"}`
- **Expected:** `ValidationError`, remedy offering `black_box` for a system
  Prama cannot read
- **Why:** the remedy is the product's answer to the mainframe, and it must be
  in the error the user hits

### SEM-206 · A dataset step naming a missing dataset is refused
- **Area:** `semantic/services/graph.py::JourneyService._validate_steps`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a tenant
- **Steps:** `dataset_id` invented; then another tenant's dataset id
- **Expected:** `NotFoundError` naming the position, for both
- **Why:** a journey that references another estate's dataset is a cross-tenant
  read through the back door

### SEM-207 · A black-box step with no description is refused
- **Area:** `semantic/services/graph.py::JourneyService._validate_steps`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a tenant
- **Steps:** `{"kind": "black_box"}`, then `{"kind": "manual",
  "description": "  "}`
- **Expected:** `ValidationError` for both
- **Why:** "a black box Prama cannot read is exactly the step that most needs a
  sentence explaining it"

### SEM-208 · Steps are renumbered to match position
- **Area:** `semantic/services/graph.py::JourneyService._validate_steps`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a journey
- **Steps:** submit steps carrying wrong `ordinal` values, out of order
- **Expected:** ordinals rewritten to 0..n-1 in list order, the caller's values
  ignored — the list order is authoritative, not the supplied ordinal
- **Why:** two sources of truth for the order of a journey is how a chain
  renders backwards

### SEM-209 · Steps are replaced wholesale, and the reason is required
- **Area:** `semantic/services/graph.py::JourneyService.set_steps`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a journey with three steps
- **Steps:** `set_steps` with two of them reordered
- **Expected:** an amendment carrying the new list; audit detail carrying the
  count and reason
- **Why:** reordering touches every step, so a per-step API would make the
  common operation the awkward one — but note `set_steps` does not refuse an
  empty `reason` where `DatasetService.amend` does

### SEM-210 · A journey's criticality is subject to the approval policy
- **Area:** `semantic/services/graph.py::JourneyService.declare`
- **Type:** security
- **Priority:** P2
- **Precondition:** a tenant
- **Steps:** a Tier 1 journey, self-approved
- **Expected:** refused
- **Why:** "the health of the FRTB journey" is a regulatory statement, and the
  journey carries its own tier

### SEM-211 · `set_steps` skips the approval policy
- **Area:** `semantic/services/graph.py::JourneyService.set_steps`
- **Type:** security
- **Priority:** P2
- **Precondition:** an approved Tier 1 journey
- **Steps:** `set_steps` removing the FINREP step, one actor
- **Expected:** currently succeeds with no approver — `set_steps` never calls
  `self._policy.check`
- **Why:** the same gap as SEM-168, on the object whose steps define an
  end-to-end SLA

### SEM-212 · A connection refuses an inline secret
- **Area:** `semantic/services/graph.py::ConnectionService._reject_inline_secrets`
- **Type:** security
- **Priority:** P1
- **Precondition:** a tenant
- **Steps:** configure with `config={"password": "hunter2"}`; then each of the
  ten `SECRET_KEYS`; then `PASSWORD` upper-case
- **Expected:** `ValidationError` listing the offending keys, remedy naming
  `credential_ref`; the upper-case form also refused (`key.lower()`)
- **Why:** "connection configuration is exported to Git and shown in the UI" —
  and the pre-commit hook that refuses a tracked secret can only be trusted if
  this holds

### SEM-213 · An empty secret value is permitted
- **Area:** `semantic/services/graph.py::ConnectionService._reject_inline_secrets`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a tenant
- **Steps:** `config={"password": ""}` and `{"password": None}`
- **Expected:** accepted — `value not in (None, "")`
- **Why:** a form that posts every field must not be refused for the field it
  left blank, and the shipped `security.session_secret` is empty on purpose for
  the same reason

### SEM-214 · A nested secret is not detected
- **Area:** `semantic/services/graph.py::ConnectionService._reject_inline_secrets`
- **Type:** security
- **Priority:** P1
- **Precondition:** a tenant
- **Steps:** `config={"auth": {"password": "hunter2"}}`, then
  `config={"jdbc_url": "…?password=hunter2"}`
- **Expected:** currently accepted — the scan is one level deep and key-based
- **Why:** the export is recursive (`gitops._compact` walks every depth) and the
  refusal is not; a credential in a nested block reaches Git

### SEM-215 · A credential reference never becomes a stored secret
- **Area:** `semantic/services/connectivity.py::ConnectivityService._resolve_credential`
- **Type:** security
- **Priority:** P1
- **Precondition:** a connection with `credential_ref="env://PG_PASSWORD"`
- **Steps:** build the connector; then re-read the stored `config_json`
- **Expected:** the resolved value is injected into the connector's
  configuration at `connector_class.credential_field`; the stored declaration is
  unchanged
- **Why:** "the configuration that gets exported to Git, diffed in a pull
  request and displayed in the UI has never held a credential"

### SEM-216 · An absent credential reference resolves to nothing rather than failing
- **Area:** `semantic/services/connectivity.py::_resolve_credential`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a connection with `credential_ref=None`
- **Steps:** build the connector
- **Expected:** `{}` merged; the connector is built and fails, if at all, at the
  source
- **Why:** a file connector needs no credential, and demanding one would block
  the simplest source there is

### SEM-217 · A connection whose source type has no connector is refused with the list
- **Area:** `semantic/services/connectivity.py::connector_for`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a connection declared `source_type="teradata"`
- **Steps:** build the connector
- **Expected:** `ValidationError` listing every installed source type, or
  `(none)`, and naming both remedies
- **Why:** a remedy that omits the answer is not a remedy — the same rule DER-051
  applies to semantic types

### SEM-218 · Binding requires both the dataset and the connection to exist
- **Area:** `semantic/services/graph.py::BindingService.bind_dataset`
- **Type:** negative
- **Priority:** P1
- **Precondition:** one of each
- **Steps:** bind with an invented dataset id; then an invented connection id
- **Expected:** `NotFoundError` naming which, with distinct remedies
- **Why:** the two failures have different fixes and a merged message sends the
  user to the wrong screen

### SEM-219 · Binding amends the dataset's shape
- **Area:** `semantic/services/graph.py::BindingService.bind_dataset`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an unbound dataset
- **Steps:** bind it with `shape="table"`; read the dataset and the coverage gaps
- **Expected:** `shape == "table"`, `is_bound is True`, and it leaves
  `coverage_gaps()["unbound"]`
- **Why:** "a bound dataset is no longer unbound: the declaration and the shape
  must agree, or the coverage report lies"

### SEM-220 · An unconfirmed binding records drift state `unknown`
- **Area:** `semantic/services/graph.py::BindingService.bind_dataset`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a dataset and a connection
- **Steps:** bind with `confirmed=False`
- **Expected:** `status == "proposed"`, `drift_state == "unknown"`; but the
  dataset's shape is amended regardless
- **Why:** a *proposed* binding marks the dataset bound and removes it from the
  coverage gap report before anybody agreed — confirm whether that is intended

### SEM-221 · An invalid shape on binding reaches the database
- **Area:** `semantic/services/graph.py::BindingService.bind_dataset`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a dataset and a connection
- **Steps:** `shape="parquet_directory"`
- **Expected:** the same unvalidated path as SEM-162, from a second entry point
- **Why:** two writers of one column, neither validating

### SEM-222 · Drift is recorded and routed to the declaration's owner
- **Area:** `semantic/services/graph.py::BindingService.record_drift`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a confirmed binding
- **Steps:** `record_drift(drift_state="missing")`, then `"changed"`
- **Expected:** `status == "broken"` for `missing`, unchanged for `changed`;
  audit `object_kind == "dataset"`, `object_id` the dataset, `actor_kind ==
  "system"`
- **Why:** docs/03 §6.4 — "these route to the business owner of the declaration,
  not to an engineer, because the declaration is theirs"; the audit object is
  the dataset for exactly that reason

### SEM-223 · An unknown drift state is accepted
- **Area:** `semantic/services/graph.py::BindingService.record_drift`
- **Type:** negative
- **Priority:** P3
- **Precondition:** a binding
- **Steps:** `drift_state="gone"`
- **Expected:** the string is stored, and `status` is left alone because it is
  not the literal `"missing"`
- **Why:** the status transition turns on one magic string compared inline

### SEM-224 · `drifted()` lists what the estate cannot reach
- **Area:** `db/dao/semantic.py::BindingDao.drifted`
- **Type:** functional
- **Priority:** P2
- **Precondition:** three bindings, one missing, one changed, one intact
- **Steps:** `coverage_gaps()["drifted_bindings"]`
- **Expected:** the drifted ones, by `dataset_id`
- **Why:** the gap report is the honest list, and a drifted binding is a control
  that is silently not running

---

## `semantic/services/estate.py` — the estate as a whole

### SEM-225 · Facts are gathered for a whole tenant
- **Area:** `semantic/services/estate.py::EstateService.gather_facts`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a described estate
- **Steps:** `gather_facts(tenant_id)`
- **Expected:** every count matches a hand count of the fixture
- **Why:** the maturity score is only as good as the counting, and the counting
  is the part with no test

### SEM-226 · Facts can be scoped to a domain
- **Area:** `semantic/services/estate.py::EstateService.gather_facts`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two domains
- **Steps:** `gather_facts(tenant_id, domain_id=…)`
- **Expected:** counts restricted to that domain; relationships filtered to
  those touching one of its datasets
- **Why:** "the health of the Credit Risk domain" is the sentence the score is
  for

### SEM-227 · An empty domain filter does not count the whole estate's relationships
- **Area:** `semantic/services/estate.py::EstateService.gather_facts`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a domain with no datasets, and confirmed relationships
  elsewhere
- **Steps:** gather facts for that domain
- **Expected:** the filter is `if not dataset_ids or …`, so an empty domain
  admits **every** confirmed relationship in the tenant while reporting zero
  datasets
- **Why:** an empty domain would score `RELATED` against `max(1, 0 // 2) == 1`
  with a non-zero numerator — a domain with nothing in it can report progress

### SEM-228 · The estate reads are capped at 10,000
- **Area:** `semantic/services/estate.py::EstateService.gather_facts`
- **Type:** performance
- **Priority:** P2
- **Precondition:** an estate above the cap
- **Steps:** gather facts
- **Expected:** the count silently reflects the first 10,000 — and the per
  dataset attribute read is a query per dataset
- **Why:** docs/03 says what is untested is scale; the score becomes wrong
  rather than slow, which is the worse failure

### SEM-229 · Conflicts are found across every concept and property
- **Area:** `semantic/services/estate.py::EstateService.conflicts`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two attributes mapped to one property with different units
- **Steps:** `conflicts(tenant_id)`
- **Expected:** one `UNIT` conflict, rendered with both attribute names
- **Why:** docs/03 §2.3 — "the platform shows the conflict instead of silently
  hosting two truths"

### SEM-230 · Coverage gaps name the datasets, not the count
- **Area:** `semantic/services/estate.py::EstateService.coverage_gaps`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a partially described estate
- **Steps:** call it
- **Expected:** six keys — `unbound`, `unowned`, `no_grain`, `no_rhythm`,
  `tier_one_without_grain`, `drifted_bindings` — each a list of names
- **Why:** "83% covered" is not a sentence somebody can act on; a list of names
  is

### SEM-231 · `tier_one_without_grain` is a subset of `no_grain`
- **Area:** `semantic/services/estate.py::EstateService.coverage_gaps`
- **Type:** contract
- **Priority:** P2
- **Precondition:** Tier 1 and Tier 4 datasets, none with a grain
- **Steps:** compare the two lists
- **Expected:** the Tier 1 names appear in both
- **Why:** a reader working the gap report top-down must not think they are
  disjoint queues

---

## `semantic/gitops.py` — the estate as reviewable files

### SEM-232 · A dataset round-trips through YAML without losing a field
- **Area:** `semantic/gitops.py::EstateSerialiser.dataset_document`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a dataset with every field of `DATASET_FIELDS` populated,
  and three attributes
- **Steps:** render, `dump`, `load`, compare against the source version
- **Expected:** every declared value present; `grain` and `rhythm` intact;
  attributes in order
- **Why:** "a serialiser that quietly drops a field turns a review into a
  data-loss event"

### SEM-233 · `DATASET_FIELDS` and the rendered document agree
- **Area:** `semantic/gitops.py::EstateSerialiser.DATASET_FIELDS`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** compare the tuple against the keys `dataset_document` actually
  emits
- **Expected:** `custodian_id`, `source_of_truth_id` and `slug` are named in the
  tuple and **absent from the spec**; `owner` and `steward` are emitted under
  different names than the tuple states
- **Why:** the field list reads as the contract and is not one; a custodian is
  the routing decision that matters at 3am (DER-005) and it does not survive an
  export

### SEM-234 · Every attribute field survives the round trip
- **Area:** `semantic/gitops.py::EstateSerialiser.attribute_document`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an attribute with definition, interpretation, semantic type,
  unit, currency attribute, precision, scale, value domain, optionality and its
  condition, CDE mark, obligations, sensitivity, concept property, glossary term
- **Steps:** render and compare
- **Expected:** all fifteen present
- **Why:** `interpretation` is "the sentence that decides whether a sign control
  is right or backwards, and it exists in no schema" — losing it in an export
  loses the thing the export was for

### SEM-235 · `_compact` drops empty values at every depth
- **Area:** `semantic/gitops.py::_compact`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a tolerance with `relative=None` and a match key with
  `right=None`
- **Steps:** render a relationship document
- **Expected:** neither null appears; the nested value objects are compacted too
- **Why:** "a document full of null is a document nobody reads, and it makes
  every diff noisier than the change it contains"

### SEM-236 · `_compact` does not drop a legitimate zero or false
- **Area:** `semantic/gitops.py::_compact`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `tolerance.absolute == 0.0`, `retention_days == 0`,
  `case_sensitive is False`, `lateness_tolerance_seconds == 0.0`
- **Steps:** render and reload
- **Expected:** the filter is `v not in (None, "", [], {})` — but `0 == False`
  and `0.0 == 0`, and Python's `in` uses equality, so **`0`, `0.0` and `False`
  all compare equal to nothing in that tuple** only if one of them is present;
  confirm each survives
- **Why:** a zero tolerance means "exact" (SEM-083) and dropping it turns a
  strict reconciliation into an undeclared one

### SEM-237 · A dataset's grain survives as a mapping, not a string
- **Area:** `semantic/gitops.py::EstateSerialiser.dataset_document`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a grain with attributes and a statement
- **Steps:** render; inspect `spec.grain`
- **Expected:** `{"attributes": [...], "statement": "..."}` — the shape
  `Grain.from_dict` expects
- **Why:** re-applying the file has to rebuild the value object, and a grain
  written as prose cannot

### SEM-238 · Dataset references are rendered as slugs
- **Area:** `semantic/gitops.py::EstateSerialiser.relationship_document`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two datasets and a relationship, with a `slug_of` mapping
- **Steps:** render
- **Expected:** `from` and `to` are slugs, not ULIDs; the journey document
  replaces `dataset_id` with `dataset`
- **Why:** a reviewer reads a pull request; a ULID tells them nothing and a diff
  of ULIDs cannot be reviewed

### SEM-239 · A missing slug falls back to the identifier
- **Area:** `semantic/gitops.py::EstateSerialiser.relationship_document`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a relationship pointing at a dataset absent from `slug_of`
- **Steps:** render
- **Expected:** the raw id appears rather than an empty string or a `KeyError`
- **Why:** an export that fails on one dangling reference exports nothing

### SEM-240 · A relationship's metadata name is stable and bounded
- **Area:** `semantic/gitops.py::EstateSerialiser.relationship_document`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two datasets with very long slugs
- **Steps:** render
- **Expected:** `{left}_{kind}_{right}` truncated at 120 characters; two
  relationships between the same long-named datasets collide after truncation
- **Why:** the name is what a reviewer scans and what a second export must
  reproduce

### SEM-241 · A connection exports its reference and never its secret
- **Area:** `semantic/gitops.py::EstateSerialiser.connection_document`
- **Type:** security
- **Priority:** P1
- **Precondition:** a connection with `credential_ref` and a config containing a
  nested `auth.password` (SEM-214)
- **Steps:** render
- **Expected:** `credential_ref` present; and the nested password **is** emitted,
  because the serialiser copies `config_json` wholesale
- **Why:** "the pre-commit hook refuses a tracked file containing one, and this
  is why that hook can be trusted" — the claim holds only as far as the
  inline-secret check reaches

### SEM-242 · The dump preserves insertion order and does not sort keys
- **Area:** `semantic/gitops.py::EstateSerialiser.dump`
- **Type:** functional
- **Priority:** P2
- **Precondition:** any document
- **Steps:** dump twice; diff
- **Expected:** identical; `name` and `owner` near the top, machinery at the
  bottom; unicode not escaped; lines wrapped at 100
- **Why:** "a diff that reorders on every export is a diff nobody reads"

### SEM-243 · `load` refuses malformed YAML with a remedy
- **Area:** `semantic/gitops.py::EstateSerialiser.load`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `"\t- not: [valid"`, then `"just a string"`, then `"[1,2,3]"`
- **Expected:** `ValidationError` for each — a parse error quoting the syntax
  message, and "a Prama document must be a mapping" for the other two
- **Why:** the hand-edited file is the whole point of GitOps and is the input
  most likely to be wrong

### SEM-244 · `load` refuses a document missing `apiVersion`, `kind` or `metadata`
- **Area:** `semantic/gitops.py::EstateSerialiser.load`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** omit each of the three in turn
- **Expected:** `ValidationError` naming the missing key, remedy "export an
  existing object to see the shape"; note `spec` is **not** required
- **Why:** a document with no spec loads as `{}` and diffs as "different" on
  every field — see SEM-252

### SEM-245 · `load` refuses a document from another layout version
- **Area:** `semantic/gitops.py::EstateSerialiser.load`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `GITOPS_VERSION == "1"`
- **Steps:** `apiVersion: prama/v2`, then `apiVersion: v1`, then
  `apiVersion: 1`
- **Expected:** the first refused with both versions in context; the second and
  third accepted, because the check strips the `prama/v` prefix and compares the
  remainder
- **Why:** a bare `1` is not the documented form, and accepting it means the
  version gate can be satisfied by a file that does not declare a layout

### SEM-246 · The manifest records what an export contained
- **Area:** `semantic/gitops.py::EstateSerialiser.manifest`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an export
- **Steps:** build the manifest
- **Expected:** tenant, `SCHEMA_VERSION`, and sorted counts by kind
- **Why:** it is the lock file a CI job compares against, and unsorted counts
  would diff on every run

### SEM-247 · Drift is reported in both directions and resolved in neither
- **Area:** `semantic/gitops.py::DriftDetector.compare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** one object only in the store, one only in Git, one different
- **Steps:** compare
- **Expected:** three `Drift` records with directions `only_in_store`,
  `only_in_git`, `different`; the third names the differing fields; nothing is
  written
- **Why:** "a UI edit and a YAML edit are both legitimate, and silently
  resolving in favour of one is how a governance tool loses a declaration
  somebody made deliberately"

### SEM-248 · Versioning and provenance fields are excluded from the comparison
- **Area:** `semantic/gitops.py::DriftDetector.IGNORED`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a store document carrying `version`, `recorded_at`,
  `authored_by`, `change_reason`
- **Steps:** compare against a Git document that has none of them
- **Expected:** no drift — ten field names are ignored
- **Why:** "history belongs to the store, which is append-only and cannot be
  reconstructed from a file anyone can edit"; including them makes every export
  drift immediately

### SEM-249 · An absent key, an explicit null and an empty list are the same thing
- **Area:** `semantic/gitops.py::_normalise`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** store `{"tags": []}` against Git `{}` against
  `{"tags": None}`
- **Steps:** compare each pair
- **Expected:** no drift in any pairing — the empty check comes first, so an
  empty list normalises to `None` rather than to an empty tuple
- **Why:** the comment says an empty list normalised as an empty tuple "would
  not equal None, and every export would show phantom drift"

### SEM-250 · Nested mappings compare by content, not by key order
- **Area:** `semantic/gitops.py::_normalise`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a tolerance written `{absolute, relative}` in one file and
  `{relative, absolute}` in the other
- **Steps:** compare
- **Expected:** no drift — dict entries are sorted, and entries whose value is
  `None` or `""` are dropped before sorting
- **Steps (counterfactual):** change `absolute` from 1.0 to 2.0
- **Expected:** drift, naming `tolerance`
- **Why:** a comparison that reports a difference on formatting trains people to
  ignore the report

### SEM-251 · A list compares in order
- **Area:** `semantic/gitops.py::_normalise`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** grain attributes `[account_id, business_date]` against
  `[business_date, account_id]`
- **Steps:** compare
- **Expected:** drift — lists are normalised element-wise, not as sets
- **Why:** the order of a grain determines the generated key's column order, so
  a reordering is a real change and must not be normalised away

### SEM-252 · A hand-edited file that adds a field drifts
- **Area:** `semantic/gitops.py::DriftDetector._differing_fields`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an exported dataset file
- **Steps:** add `criticality: 1` to a spec that had none, and change
  `owner`
- **Expected:** one `DIFFERENT` drift naming both fields, sorted
- **Why:** the review workflow is "someone edits the YAML"; a change that does
  not show is a change nobody approved

### SEM-253 · A drift summary reads as a sentence
- **Area:** `semantic/gitops.py::DriftDetector.summarise`
- **Type:** functional
- **Priority:** P2
- **Precondition:** no drift, then three
- **Steps:** summarise both
- **Expected:** "in sync: no drift between Prama and the repository"; then a
  count and one line per drift
- **Why:** it is the CLI's whole output for `prama estate diff`

### SEM-254 · `prama estate diff` exits non-zero on drift
- **Area:** `cli/estate.py::EstateDiffCommand.run`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a directory that disagrees with the store
- **Steps:** run the command; read the exit code and the `--json` output
- **Expected:** `EXIT_DRIFT` with `{"in_sync": false, "drifts": [...]}`;
  `EXIT_OK` when in sync
- **Why:** it is a CI gate, and a gate that exits 0 on failure is decoration

### SEM-255 · Export writes every declared object and nothing else
- **Area:** `cli/estate.py::_collect`
- **Type:** functional
- **Priority:** P1
- **Precondition:** datasets, relationships, journeys, connections, concepts and
  domains declared
- **Steps:** export; list the files
- **Expected:** datasets, relationships, journeys and connections are written;
  **concepts and domains are not**, though `path_for` has folders for both
- **Why:** the concept model is the shared vocabulary and the retrieval context
  for induction; an export that omits it cannot reconstruct the estate

### SEM-256 · Exported paths do not use the documented domain layout
- **Area:** `cli/estate.py::_collect` vs
  `semantic/gitops.py::EstateSerialiser.path_for`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** datasets in two domains
- **Steps:** export; inspect the paths
- **Expected:** everything lands in `prama/datasets/<slug>.yaml` — `path_for` is
  called without `domain`, so the `prama/domains/<domain>/…` branch documented
  as "the documented on-disk layout (docs/14 §5)" is dead code
- **Why:** two slugs equal across domains would collide, and the documented
  layout is not the one produced

### SEM-257 · A relationship file name changes if the identifier does
- **Area:** `cli/estate.py::_collect`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a relationship
- **Steps:** export twice; then export the same estate restored into a new
  install
- **Expected:** the name is `{kind}_{relationship_id[-8:].lower()}`; stable
  within an install, different after a restore that re-mints ULIDs
- **Why:** a diff against a repository exported from another environment would
  report every relationship as `only_in_git` and `only_in_store` at once

### SEM-258 · `--dry-run` writes nothing
- **Area:** `cli/estate.py::EstateExportCommand.run`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an estate
- **Steps:** export `--dry-run` into an empty directory
- **Expected:** the file list is printed, `written: false`, and the directory
  stays empty
- **Why:** the preview is what somebody runs against a repository they do not
  want to touch

### SEM-259 · There is no `apply`, and the absence is deliberate
- **Area:** `cli/estate.py`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** look for a command that writes a directory back into the store;
  follow every `remedy=` and document that names one
- **Expected:** none exists; the module docstring says it belongs behind the
  same approval workflow as any other change
- **Why:** round-trip fidelity is claimed as a requirement and only half of the
  trip is implemented — any document promising `prama estate apply` is a remedy
  naming a command that does not exist

### SEM-260 · Re-applying a file would produce an amendment, not a rewrite
- **Area:** `semantic/gitops.py` module docstring
- **Type:** documentation
- **Priority:** P2
- **Precondition:** an exported and edited file
- **Steps:** whatever path applies it — the API declaration routes, a future
  `apply`
- **Expected:** a new version with provenance naming the commit; the prior
  version still in `history`
- **Why:** "history belongs to the store … re-applying a file therefore produces
  an amendment, with provenance naming the commit, rather than rewriting the
  past" — the claim needs a test wherever the write actually happens

### SEM-261 · A conflicting edit on both sides is reported, not merged
- **Area:** `semantic/gitops.py::DriftDetector.compare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the same dataset amended in the UI and edited in Git, in the
  same field, differently
- **Steps:** diff
- **Expected:** one `DIFFERENT` drift naming the field; no resolution, no
  last-writer-wins
- **Why:** the module's second stated half — "the disagreement must be visible
  rather than resolved by whoever writes last"

---

## `derive/declaration.py` and `derive/persisted.py` — Γ's input

### DER-001 · An attribute declaration defaults to optional and internal
- **Area:** `derive/declaration.py::AttributeDeclaration`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `AttributeDeclaration(name="amount")`
- **Expected:** `optionality == OPTIONAL`, `sensitivity == INTERNAL`,
  `is_cde is False`, `value_domain` a free-text `ValueDomain`,
  `generates_a_domain_control is False`
- **Why:** the defaults decide that an undescribed column generates no control
  at all, which is the right answer and needs pinning

### DER-002 · `is_monetary` is true from a unit or a currency attribute
- **Area:** `derive/declaration.py::AttributeDeclaration.is_monetary`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `unit="currency"`, `"Money"`, `"AMOUNT"`, `"EUR"`; then
  `currency_attribute="ccy"` with no unit
- **Expected:** true for the first three (case-folded), **false for `"EUR"`**,
  true for the last
- **Why:** it decides whether coverage counts a consistency dimension (DER-110);
  a monetary column whose unit is the currency code itself is the common
  declaration and is not recognised

### DER-003 · `generates_a_domain_control` is true from either source
- **Area:** `derive/declaration.py::AttributeDeclaration.generates_a_domain_control`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** semantic type only; constrained domain only; both; neither
- **Expected:** true, true, true, false
- **Why:** coverage counts a validity dimension only when this is true, so a
  false negative hides a gap and a false positive invents one

### DER-004 · A dataset declaration exposes its CDEs and obligations
- **Area:** `derive/declaration.py::DatasetDeclaration.cdes`, `.obligations`
- **Type:** functional
- **Priority:** P2
- **Precondition:** three attributes, two CDEs, obligations `["FINREP"]` and
  `["FINREP", "FR Y-14Q"]`
- **Steps:** read both properties
- **Expected:** two CDEs; obligations `("FINREP", "FR Y-14Q")` — de-duplicated,
  first-seen order preserved
- **Why:** the obligations drive blocking gates and attestation, and a duplicate
  or reordered list changes what a report claims

### DER-005 · Owner, steward and custodian are three different people
- **Area:** `derive/declaration.py::DatasetDeclaration`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** a declaration with all three set
- **Steps:** generate; inspect every control's `owner`
- **Expected:** controls carry `owner_id` (falling back to the attribute's own
  owner); neither `steward_id` nor `custodian_id` reaches any generated control
- **Why:** "a broken schema goes to the custodian and a wrong definition goes to
  the steward, and sending each to the other is how an incident spends its first
  hour" — the field exists and nothing routes on it

### DER-006 · `is_live` and `LifecycleState.is_live` disagree
- **Area:** `derive/declaration.py::DatasetDeclaration.is_live`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a deprecated dataset
- **Steps:** compare `DatasetDeclaration.is_live` with
  `LifecycleState.DEPRECATED.is_live`
- **Expected:** `False` and `True` respectively
- **Why:** two definitions of "live" in one layer; a deprecated dataset is still
  read and still needs its controls

### DER-007 · `is_bound` is any shape but `unbound`
- **Area:** `derive/declaration.py::DatasetDeclaration.is_bound`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** shapes `unbound`, `table`, `feed`, `""`
- **Steps:** read the property
- **Expected:** false, true, true, **true** for the empty string
- **Why:** an empty shape reads as bound, and `_enum`-style fallbacks elsewhere
  make an empty string reachable

### DER-008 · `attribute()` and `has_attribute()` match exactly
- **Area:** `derive/declaration.py::DatasetDeclaration.attribute`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an attribute named `amount`
- **Steps:** look up `amount`, `Amount`, `" amount"`
- **Expected:** found, not found, not found
- **Why:** `_present` uses it to decide whether a grain is satisfiable; a
  case-sensitive miss produces `Unsatisfiable` on a dataset that is fine

### DER-009 · `from_row` builds the same declaration as `persisted`
- **Area:** `derive/declaration.py::DatasetDeclaration.from_row` vs
  `derive/persisted.py::dataset_declaration_of`
- **Type:** contract
- **Priority:** P1
- **Precondition:** one stored version row
- **Steps:** build both ways; compare
- **Expected:** they differ — `from_row` uses `row["name"]` where `persisted`
  uses `version.slug`, and `from_row` takes `recorded_by` where `persisted`
  takes `authored_by`
- **Why:** two constructors for one mapping is the thing `persisted.py`'s
  docstring says must exist in exactly one place; "if the mapping is wrong it is
  wrong everywhere at once, which is the failure mode you can actually fix"

### DER-010 · A control targets the slug, not the display name
- **Area:** `derive/persisted.py::dataset_declaration_of`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a dataset named `End-of-day Positions`, slug
  `end_of_day_positions`
- **Steps:** generate; render a control
- **Expected:** `CHECK end_of_day_positions…` — `CHECK End-of-day Positions`
  does not parse
- **Why:** the docstring names this exact failure; a rendered control that does
  not re-parse is the artefact class this codebase exists to refuse

### DER-011 · An unknown stored enum value degrades rather than raising
- **Area:** `derive/persisted.py::_enum`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a version row whose `temporality` is `"bitemporal"`,
  `sensitivity` is `"secret"`, `criticality` is `9`
- **Steps:** build the declaration
- **Expected:** falls back to `SNAPSHOT`, `INTERNAL`, `TIER_4` — no exception
- **Why:** "a console that 500s on one bad row hides the other nine hundred";
  but note the sensitivity fallback silently *downgrades* a secret column to
  internal, which is the permissive direction

### DER-012 · A stored value domain's `kind` is coerced to the enum
- **Area:** `derive/persisted.py::_value_domain`
- **Type:** regression
- **Priority:** P1
- **Precondition:** `value_domain_json = {"kind": "free_text", "pattern": null}`
- **Steps:** build the declaration; read `value_domain.is_constrained`
- **Expected:** `False`
- **Why:** the documented failure — `ValueDomain(**payload)` leaves `kind` a
  string, `is_constrained` is then true for *every* attribute, and the result
  was "a control on every free-text column asserting it matches the literal
  pattern `None`, which failed every row of every dataset"

### DER-013 · An unknown stored domain kind falls back to free text
- **Area:** `derive/persisted.py::_value_domain`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `{"kind": "colour", "allowed_values": ["red"]}`
- **Steps:** build
- **Expected:** `FREE_TEXT`, `is_constrained is False`, no control generated,
  no exception
- **Why:** the fallback must not produce a constrained domain with no
  constraint, which is DER-012 by another route

### DER-014 · A stored value domain with an extra key raises
- **Area:** `derive/persisted.py::_value_domain`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `{"kind": "range", "minimum": 0, "units": "EUR"}` — a
  hand-edited or older payload
- **Steps:** build the declaration
- **Expected:** currently `TypeError` from `ValueDomain(**fields)`, uncaught,
  where every neighbouring coercion falls back
- **Why:** the module's whole design is "degrade rather than fail the page", and
  this one path does the opposite

---

## `derive/generator.py` — Γ, from declarations to controls

### DER-015 · A grain generates a uniqueness control and a completeness control per column
- **Area:** `derive/generator.py::ControlGenerator._from_grain`
- **Type:** functional
- **Priority:** P1
- **Precondition:** grain `(account_id, business_date)`, both attributes declared
- **Steps:** generate
- **Expected:** one `grain.uniqueness` control with both columns, and two
  `grain.completeness` controls; every one carries the grain's sentence in
  `because`
- **Why:** docs/03 §5's first row, and the reason a business owner answers one
  question and gets several controls

### DER-016 · The grain's completeness controls are not optional
- **Area:** `derive/generator.py::ControlGenerator._from_grain`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a grain over a nullable column
- **Steps:** generate; read the `because` of the completeness control
- **Expected:** it states that a null "would slip past the uniqueness control
  because SQL does not count nulls as duplicates"
- **Why:** "without it the uniqueness control is unsound" — this is a soundness
  argument, not a nicety, and the reason must survive into the alert

### DER-017 · A grain naming a column the dataset does not have is unsatisfiable
- **Area:** `derive/generator.py::ControlGenerator._from_grain`
- **Type:** negative
- **Priority:** P1
- **Precondition:** grain names `settlement_date`; attributes are `account_id`,
  `amount`
- **Steps:** generate
- **Expected:** no controls; one `Unsatisfiable` with `rule ==
  "grain.uniqueness"`, the grain's own sentence in `declared`, a reason naming
  the missing column, and a remedy
- **Why:** "emitting the control anyway produces something that compiles,
  deploys, and fails at three in the morning … silently skipping is no better"

### DER-018 · Several missing columns are listed in one sentence
- **Area:** `derive/generator.py::_and`
- **Type:** functional
- **Priority:** P3
- **Precondition:** a grain naming three absent columns
- **Steps:** read the `Unsatisfiable.reason`
- **Expected:** "a, b and c, which **are** not in …" — the verb agrees with the
  count
- **Why:** generated prose is read by the person who wrote the declaration

### DER-019 · A declaration with no attributes is taken at its word
- **Area:** `derive/generator.py::ControlGenerator._present`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a grain, no attributes, no catalogue
- **Steps:** generate
- **Expected:** controls generated — `_present` returns `True` when there is
  nothing to check against
- **Why:** "refusing to generate anything for a dataset whose columns have not
  been profiled yet would make Γ useless at exactly the moment it is most
  wanted"

### DER-020 · With a catalogue, the schema is the authority
- **Area:** `derive/generator.py::ControlGenerator._present`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a catalogue whose schema lacks `account_id`, while the
  declaration declares it
- **Steps:** generate
- **Expected:** `Unsatisfiable` — the catalogue wins over the declaration
- **Why:** the catalogue reflects the database, and a control is going to run
  against the database

### DER-021 · A catalogue that does not know the dataset falls back
- **Area:** `derive/generator.py::ControlGenerator._present`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a catalogue with other datasets in it
- **Steps:** generate for a dataset the catalogue has never seen
- **Expected:** falls through to the declaration's attribute list
- **Why:** an unbound dataset must still generate proposals in an estate that is
  partly catalogued

### DER-022 · A generated control that does not type-check is reported back
- **Area:** `derive/generator.py::ControlGenerator._checked`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a catalogue where `amount` is text and the declared domain
  is a numeric range
- **Steps:** generate
- **Expected:** the control is dropped and an `Unsatisfiable` carries the type
  checker's message and a remedy about the mapping
- **Why:** "assert the rendered artefact, not the intent. A generator that emits
  plausible PQL and is never asked to compile it is a generator whose bugs are
  found in production"

### DER-023 · Without a catalogue Γ does not claim to have checked
- **Area:** `derive/generator.py::ControlGenerator._checked`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** no catalogue
- **Steps:** generate
- **Expected:** every control kept, no `Unsatisfiable` from type checking
- **Why:** the constructor's docstring says a catalogue-less generator "just
  cannot promise the controls will compile, and says so by not claiming to have
  checked" — confirm nothing downstream reports these as verified

### DER-024 · Every generated control re-parses
- **Area:** `derive/generator.py::DerivedControl.content`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a declaration exercising every rule — grain, business key,
  rhythm, each value-domain kind, each semantic type, a currency attribute, a
  conditional optionality
- **Steps:** render each control and feed it back to `pql.parser.parse_control`
- **Expected:** every one parses, and the re-parsed AST renders identically
- **Why:** "a generated control must be re-readable PQL"; the pattern-literal
  bug (DER-040) was found by a round-trip test "and no amount of reading the
  generator would have"

### DER-025 · Severity is derived from criticality, never defaulted
- **Area:** `derive/generator.py::severity_for`
- **Type:** functional
- **Priority:** P1
- **Precondition:** one dataset per tier
- **Steps:** generate; read each control's severity
- **Expected:** `critical`, `major`, `minor`, `info`
- **Why:** "a Tier 1 dataset cannot end up with a suite of warnings that nobody
  pages on"

### DER-026 · A CDE raises the floor by one rank
- **Area:** `derive/generator.py::severity_for`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a Tier 3 dataset with a CDE attribute; then a Tier 1 dataset
  with one
- **Steps:** read the severities
- **Expected:** the Tier 3 CDE's control is `major`; the Tier 1 CDE's stays at
  the top rank rather than overflowing the list
- **Why:** `ranks[min(len(ranks) - 1, floor.rank + 1)]` — the clamp is the whole
  boundary, and the ordering of `ast.Severity` must run low-to-high for it to
  mean "raise"

### DER-027 · A CDE with an obligation retains full evidence and blocks
- **Area:** `derive/generator.py::evidence_for`, `fail_action_for`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `is_cde=True`, `obligations=("FR Y-14Q",)`
- **Steps:** generate
- **Expected:** `EvidenceLevel.FULL` and `FailAction.BLOCK`
- **Why:** "the question asked about it later is 'show me every row', and a
  sample cannot answer that"; "submitting it wrong is worse than submitting it
  late"

### DER-028 · A CDE with no obligation neither blocks nor retains fully
- **Area:** `derive/generator.py::evidence_for`, `fail_action_for`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `is_cde=True`, `obligations=()`
- **Steps:** generate
- **Expected:** default evidence and `FailAction.ALERT`
- **Why:** the conjunction is the rule; marking every CDE blocking would stop
  pipelines for an internal dashboard

### DER-029 · A sensitive attribute retains counts only, even when it is a CDE
- **Area:** `derive/generator.py::evidence_for`
- **Type:** security
- **Priority:** P1
- **Precondition:** `sensitivity=PII`, `is_cde=True`, obligations present
- **Steps:** generate
- **Expected:** `EvidenceLevel.COUNTS` — the sensitivity branch is first and
  wins over the CDE branch
- **Why:** ordering decides whether rows of PII are retained in evidence; "a
  masked sample of a PII column tells the reader nothing they could act on
  anyway"

### DER-030 · A confidential attribute is *not* counts-only
- **Area:** `derive/generator.py::evidence_for`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `sensitivity=CONFIDENTIAL`
- **Steps:** generate
- **Expected:** default evidence, because `masked_by_default` excludes
  confidential (SEM-033)
- **Why:** the surprising half of the sensitivity model, and the one that
  decides whether confidential values are retained as samples

### DER-031 · A business key identical to the grain generates nothing extra
- **Area:** `derive/generator.py::ControlGenerator._from_business_key`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** grain `(a, b)` and business key `(b, a)`
- **Steps:** generate
- **Expected:** no `business_key.uniqueness` control — the comparison is on sets
- **Why:** "a second alert saying the same thing is how people learn to ignore
  the first"

### DER-032 · A business key different from the grain generates its own control
- **Area:** `derive/generator.py::ControlGenerator._from_business_key`
- **Type:** functional
- **Priority:** P2
- **Precondition:** grain `(account_id, business_date)`, business key
  `(trade_ref,)`
- **Steps:** generate
- **Expected:** a second uniqueness control whose `because` distinguishes the
  business key from the storage grain
- **Why:** the two are genuinely different claims and both are worth checking

### DER-033 · A business key naming a missing column is unsatisfiable
- **Area:** `derive/generator.py::ControlGenerator._from_business_key`
- **Type:** negative
- **Priority:** P2
- **Precondition:** business key naming an absent column
- **Steps:** generate
- **Expected:** `Unsatisfiable business_key.uniqueness`; note the reason says
  "which is not present" in the singular regardless of the count
- **Why:** the grain path pluralises and this one does not — the same defect the
  review found in generated prose elsewhere

### DER-034 · A rhythm with an arrival time generates a freshness control
- **Area:** `derive/generator.py::ControlGenerator._from_rhythm`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `arrival_by="06:30"`, `calendar="TARGET2"`,
  `lateness_tolerance_seconds=900`
- **Steps:** generate
- **Expected:** a `rhythm.freshness` control with `due_time`, `calendar` and
  `tolerance_minutes == 15`; the `because` quotes the arrival clause **only**
- **Why:** "quoting the whole rhythm puts the expected record count in the
  reason for a timeliness alert, and a reason that includes an irrelevant number
  reads as boilerplate"

### DER-035 · Lateness tolerance truncates to whole minutes
- **Area:** `derive/generator.py::ControlGenerator._from_rhythm`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** tolerances of 59, 60, 61 and 0 seconds
- **Steps:** generate
- **Expected:** 0, 1, 1, 0 minutes — `int(seconds // 60)`; a 59-second grace
  becomes no grace at all
- **Why:** a declared tolerance that silently rounds to zero is a control that
  fires a minute earlier than declared, every day

### DER-036 · A rhythm with volume bounds generates a row-count control one rank lower
- **Area:** `derive/generator.py::ControlGenerator._from_rhythm`, `_one_below`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a Tier 1 dataset with volume bounds
- **Steps:** generate
- **Expected:** a `rhythm.volume` control at `major`, not `critical`; and on a
  Tier 4 dataset the rank does not fall below the first member
- **Why:** "a volume miss is real but rarely as urgent as a broken key", and the
  `max(0, …)` clamp is the boundary

### DER-037 · Only one volume bound still generates a control
- **Area:** `derive/generator.py::ControlGenerator._from_rhythm`, `_volume`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** minimum only; then maximum only
- **Steps:** generate; read the `because`
- **Expected:** "at least 1,000 records" and "at most 5,000 records", thousands
  separated
- **Why:** "we never get fewer than a thousand rows" is a real declaration, and
  the sentence is what the alert quotes

### DER-038 · Volume drivers are deferred, not dropped
- **Area:** `derive/generator.py::ControlGenerator._from_rhythm`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `volume_drivers=("month_end",)`
- **Steps:** generate
- **Expected:** a `Deferred` naming the driver and the seasonal monitor it
  belongs to; no control
- **Why:** "a fixed threshold wide enough for a month-end spike cannot detect an
  ordinary day collapsing to half its usual size" — and the declarer must see
  that their declaration was understood

### DER-039 · A continuous feed with no cut-off is deferred to a lag monitor
- **Area:** `derive/generator.py::ControlGenerator._from_rhythm`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `frequency=CONTINUOUS`, no `arrival_by`
- **Steps:** generate
- **Expected:** a `Deferred` for `rhythm.freshness`; and with an `arrival_by`
  set, a freshness control and no deferral
- **Why:** "a continuous feed has no cut-off to be late against"

### DER-040 · Five of six temporalities defer and generate nothing
- **Area:** `derive/generator.py::ControlGenerator._from_temporality`
- **Type:** functional
- **Priority:** P1
- **Precondition:** one declaration per temporality
- **Steps:** generate
- **Expected:** `SNAPSHOT` produces neither control nor deferral;
  `APPEND_ONLY`, `EVENT_STREAM`, `SLOWLY_CHANGING`, `AS_OF_DATED` and `MUTABLE`
  each produce exactly one `Deferred` with a distinct destination
- **Why:** "emitting a within-scan approximation of it would report green on a
  table being silently rewritten, and that is worse than emitting nothing"

### DER-041 · A mutable table's deferral says plainly that nothing can be checked
- **Area:** `derive/generator.py::ControlGenerator._from_temporality`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** `temporality=MUTABLE`
- **Steps:** read the deferral
- **Expected:** "no control at all until an as-at column exists" — an honest
  refusal rather than something that looks like coverage
- **Why:** the declaration that generates the least is the one whose explanation
  matters most

### DER-042 · A mandatory attribute generates an unconditional completeness control
- **Area:** `derive/generator.py::ControlGenerator._completeness`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `optionality=MANDATORY`, a definition written
- **Steps:** generate
- **Expected:** an `attribute.completeness` control with no `WHERE`; the
  `because` is "`amount` is mandatory. <the definition>"
- **Why:** the commonest declaration in the product, and the definition is
  appended so the alert says what the field is

### DER-043 · An optional attribute generates nothing
- **Area:** `derive/generator.py::ControlGenerator._completeness`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `optionality=OPTIONAL`
- **Steps:** generate
- **Expected:** no completeness control, no `Unsatisfiable`, no `Deferred`
- **Why:** the declaration has answered the question — a control the declarer did
  not ask for is worse than no control

### DER-044 · A conditional attribute generates a filtered control
- **Area:** `derive/generator.py::ControlGenerator._completeness`,
  `_parse_condition`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `optionality=CONDITIONAL`,
  `optionality_condition="product_type = 'BOND'"`
- **Steps:** generate; render
- **Expected:** `WHERE product_type = 'BOND'`; the `because` reads "mandatory
  when product_type = 'BOND'"
- **Why:** the shape most business rules actually have, and the one a global
  miner cannot express (MIN-037)

### DER-045 · A conditional attribute with no condition is unsatisfiable
- **Area:** `derive/generator.py::ControlGenerator._condition_problem`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `optionality=CONDITIONAL`, `optionality_condition=""`
- **Steps:** generate
- **Expected:** `Unsatisfiable attribute.completeness`, remedy stating that the
  only control generable without one is the unconditional version, which is
  stricter than declared
- **Why:** "falling through with no filter produces an *unconditional* control:
  stricter than declared, alerting on rows the business explicitly said were
  fine, and switched off within a week — taking the real coverage with it"

### DER-046 · A conditional attribute with an unparseable condition is unsatisfiable
- **Area:** `derive/generator.py::_parse_condition`
- **Type:** negative
- **Priority:** P1
- **Precondition:** conditions `"when it is a bond"`, `"product_type ="`,
  `"1; DROP TABLE t"`
- **Steps:** generate
- **Expected:** `Unsatisfiable` for each, quoting the condition and saying the
  rows it applies to cannot be identified
- **Why:** the same failure as DER-045 by the other route; a `PqlError` must
  become a reported gap rather than an exception or a silent widening

### DER-047 · A condition that parses to something other than an expression is refused
- **Area:** `derive/generator.py::_parse_condition`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a condition that makes `CHECK x SATISFIES <cond>` parse into
  a non-`ExpressionAssertion`
- **Steps:** generate
- **Expected:** `None` returned, and therefore `Unsatisfiable`
- **Why:** the function returns `None` on two different paths and both must lead
  to the refusal, not to an unfiltered control

### DER-048 · A known semantic type generates a validity control
- **Area:** `derive/generator.py::ControlGenerator._semantic_type`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `semantic_type="isin"`, with the default validator registry
- **Steps:** generate; render
- **Expected:** `IS VALID 'isin'`, dimension `validity`, `because` quoting
  `validator.describe()`
- **Why:** docs/03 §5 — "attribute is `Instrument.ISIN` → format + check digit"

### DER-049 · A validator whose screen is incomplete says so in the reason
- **Area:** `derive/generator.py::ControlGenerator._semantic_type`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** a semantic type whose validator has
  `screen_is_complete is False` (an LEI: shape and check digit, not GLEIF
  registration)
- **Steps:** read the `because`
- **Expected:** the validator's `beyond_shape` sentence appended, capitalised
- **Why:** round 1's "what held" records that fabricated LEIs with valid shape
  produced `indeterminate` with the unrun residual named — the reason in the
  control is where that residual is stated

### DER-050 · A semantic type that is a code list generates a membership control
- **Area:** `derive/generator.py::ControlGenerator._semantic_type`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `semantic_type="iso4217"` with no validator of that name
- **Steps:** generate
- **Expected:** `IN CODELIST 'iso4217'` with the list's label in the reason
- **Why:** the fallback from validator to code list is how one field serves two
  registries

### DER-051 · An unknown semantic type is unsatisfiable, and the remedy lists them all
- **Area:** `derive/generator.py::ControlGenerator._semantic_type`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `semantic_type="isin_code"`
- **Steps:** generate; read the remedy
- **Expected:** `Unsatisfiable`; **every** registered validator and code-list
  name listed, not a truncated sample; and the warning that an unknown type
  "would compile to a check that passes everything"
- **Why:** "an alphabetical truncation hides isin and lei — the two anybody
  hitting this message is most likely to have meant — and a remedy that omits
  the answer is not a remedy"

### DER-052 · A code-list domain with a registered reference generates membership
- **Area:** `derive/generator.py::ControlGenerator._value_domain`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `ValueDomain(kind=CODELIST, codelist_ref="iso4217")`
- **Steps:** generate
- **Expected:** `IN CODELIST 'iso4217'`
- **Why:** "a membership control that updates when the code list updates", and
  replays against the list as it stood on the day

### DER-053 · An unregistered code list is unsatisfiable
- **Area:** `derive/generator.py::ControlGenerator._value_domain`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `codelist_ref="internal_product_codes"`
- **Steps:** generate
- **Expected:** `Unsatisfiable attribute.value_domain`, remedy about replay
  against the list as it stood
- **Why:** "a domain that silently tracks 'latest' is not replayable, and
  therefore is not evidence"

### DER-054 · Explicit allowed values generate an `IN (...)` control
- **Area:** `derive/generator.py::ControlGenerator._value_domain`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `allowed_values=("BUY", "SELL")`, no reference
- **Steps:** generate; render; re-parse
- **Expected:** `IN ('BUY', 'SELL')`; the `because` reads "may only be BUY and
  SELL"
- **Why:** the two-value enumeration, and the rendering must re-parse

### DER-055 · A range domain generates the right comparison for each bound shape
- **Area:** `derive/generator.py::ControlGenerator._range`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** min+max; min only; max only
- **Steps:** generate; render
- **Expected:** `BETWEEN a AND b`, `>= a`, `<= b`
- **Why:** three branches, and the last is reached only when `minimum is None`

### DER-056 · Numeric bounds render as numbers, not strings
- **Area:** `derive/generator.py::_number`
- **Type:** regression
- **Priority:** P1
- **Precondition:** `ValueDomain(kind=RANGE, minimum=0)`
- **Steps:** render
- **Expected:** `market_value >= 0`, never `>= '0'`
- **Why:** "the engines mostly coerce it, which is worse than failing: the
  control runs, and on a dialect that compares lexically it reports that -5 is
  above zero"

### DER-057 · A pattern domain with no pattern is unsatisfiable
- **Area:** `derive/generator.py::ControlGenerator._value_domain`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a stored domain `{"kind": "pattern"}` with no pattern —
  reachable through `persisted._value_domain`, which bypasses
  `ValueDomain.__post_init__`
- **Steps:** generate
- **Expected:** `Unsatisfiable`, not `MATCHES /None/`; note the `Unsatisfiable`
  on this branch carries **no `dataset`**, unlike every other
- **Why:** "a control that parses, compiles, runs and fails every row, which is
  the exact class of artefact this codebase exists to refuse"

### DER-058 · A pattern renders as a pattern literal
- **Area:** `derive/generator.py::ControlGenerator._value_domain`
- **Type:** regression
- **Priority:** P1
- **Precondition:** `pattern=r"^[A-Z]{2}\d{10}$"`
- **Steps:** render; re-parse
- **Expected:** `MATCHES /^[A-Z]{2}\d{10}$/` — a pattern literal, not a text one
- **Why:** "a text literal here renders to something the parser refuses — which
  a round-trip test found and no amount of reading the generator would have";
  include a pattern containing a `/` as the boundary

### DER-059 · A pattern domain is a conformity dimension, not validity
- **Area:** `derive/generator.py::ControlGenerator._value_domain`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a pattern domain
- **Steps:** read `dimensions`
- **Expected:** `CONFORMITY`; a code list or range yields `VALIDITY`
- **Why:** coverage counts validity and not conformity (DER-110), so an
  attribute whose only control is a pattern reads as having no validity control

### DER-060 · A monetary attribute generates a control on its currency column
- **Area:** `derive/generator.py::ControlGenerator._currency`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `amount` with `currency_attribute="settlement_ccy"`, and
  that column declared
- **Steps:** generate
- **Expected:** an `attribute.currency` control checking `settlement_ccy IN
  CODELIST 'iso4217'`, with dimensions `validity` **and** `consistency`, and a
  `because` explaining that an invalid code makes every total meaningless
- **Why:** docs/03 §5 — the declaration is about the amount and the control is
  on the column beside it

### DER-061 · A currency attribute naming a missing column is unsatisfiable
- **Area:** `derive/generator.py::ControlGenerator._currency`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `currency_attribute="ccy"`, no such column
- **Steps:** generate
- **Expected:** `Unsatisfiable attribute.currency`, remedy about adding euros to
  yen
- **Why:** the aggregate over the amount is what breaks, not the row

### DER-062 · A monetary attribute with no currency column generates nothing
- **Area:** `derive/generator.py::ControlGenerator._currency`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `unit="currency"`, `currency_attribute=""`
- **Steps:** generate; then measure coverage
- **Expected:** no currency control and no `Unsatisfiable` — yet
  `CoverageAnalyser._applicable` counts a `CONSISTENCY` dimension for it
  (`is_monetary`), so it is a permanent gap nothing can close
- **Why:** two modules disagree about what a monetary attribute implies, and the
  disagreement shows up as an uncloseable coverage gap

### DER-063 · A replica with no source of truth is unsatisfiable
- **Area:** `derive/generator.py::ControlGenerator._from_authoritativeness`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `authoritativeness=REPLICA`, `source_of_truth=""`
- **Steps:** generate
- **Expected:** `Unsatisfiable authoritativeness.parity`, remedy "a perfect copy
  of wrong data is a perfect copy"
- **Why:** a replica's own quality score flatters it, and the parity control
  cannot be built without naming the origin

### DER-064 · A replica with a source of truth defers to a `MIRRORS` relationship
- **Area:** `derive/generator.py::ControlGenerator._from_authoritativeness`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `authoritativeness=EXTRACT`, `source_of_truth="positions"`
- **Steps:** generate
- **Expected:** a `Deferred` naming the `MIRRORS` relationship and the three
  controls it would produce; no control
- **Why:** "those are cross-dataset controls and belong to the relationship
  rather than to either side of it" — and the deferral is the instruction the
  declarer needs

### DER-065 · A golden source and a derived dataset generate nothing here
- **Area:** `derive/generator.py::ControlGenerator._from_authoritativeness`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `GOLDEN_SOURCE`, then `DERIVED`, then `VENDOR_SUPPLIED`,
  then `UNKNOWN`
- **Steps:** generate
- **Expected:** nothing from this rule for any of them
- **Why:** the rule turns on `is_copy` (SEM-035); a vendor-supplied file is not
  a copy of anything Prama can see

### DER-066 · Identity is stable across regeneration and across edits
- **Area:** `core/provenance.py::identity`; `derive/generator.py::_control`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a declaration
- **Steps:** generate; change the grain's *statement* only; generate again;
  change a threshold; generate again
- **Expected:** the identity is unchanged in all three; the `content_hash`
  changes on the threshold edit only
- **Why:** "editing a threshold updates the existing control; deriving identity
  from the text would orphan one and create another, so re-running Γ after any
  edit would produce an estate of duplicates nobody recognises"

### DER-067 · Identity is unique per rule and subject
- **Area:** `core/provenance.py::identity`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** one dataset, two attributes, both mandatory
- **Steps:** compare the two identities; then compare across two datasets with
  the same attribute names
- **Expected:** all four distinct
- **Why:** a collision means one proposal silently replaces another in the queue

### DER-068 · Identity uses the declaration reference when there is one
- **Area:** `derive/generator.py::ControlGenerator._control`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a declaration with `reference` set, and one without
- **Steps:** generate both
- **Expected:** the first keys on the dataset id, the second on the name — so
  the identity of a control changes if a declaration acquires a reference
- **Why:** the fallback is silent, and an estate re-generated after its
  declarations were persisted would produce a fresh set of identities

### DER-069 · Provenance points at the attribute that produced the control
- **Area:** `derive/generator.py::ControlGenerator._provenance`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an attribute-derived control and a dataset-derived one
- **Steps:** read `source_ref`
- **Expected:** `<dataset_id>#<attribute>` and `<dataset_id>`
- **Why:** "the answer to a question about counterparty_lei is a page describing
  exposures, and the reader has to hunt for the line that matters"

### DER-070 · Provenance cannot be absent, and carries the declarer and the date
- **Area:** `derive/generator.py::ControlGenerator._provenance`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a declaration with `declared_by` and `declared_at`
- **Steps:** read every control's `provenance.sentence()`
- **Expected:** "alice declared it on 2026-03-04. “<the statement>”"
- **Why:** "the user can always ask 'why does this control exist?' and get
  'because you declared X on 4 March'"

### DER-071 · Two rules reaching the same check produce one control with both reasons
- **Area:** `derive/generator.py::_coalesce`, `_fold`
- **Type:** functional
- **Priority:** P1
- **Precondition:** grain `(account_id, business_date)` where `account_id` is
  also declared `MANDATORY`
- **Steps:** generate
- **Expected:** one `account_id IS NOT NULL` control; `rule ==
  "attribute.completeness+grain.completeness"`; a `because` containing both
  sentences, each terminated with a full stop
- **Why:** "emitting both produces two identical alerts on the same rows …
  dropping one loses a reason the owner declared"

### DER-072 · A fold keeps the strictest severity, evidence and failure action
- **Area:** `derive/generator.py::_fold`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** the same pair where the attribute is a CDE with an
  obligation, so one member blocks and retains full evidence
- **Steps:** generate
- **Expected:** the folded control blocks, retains `FULL`, and takes the higher
  severity; the provenance is the strongest member's
- **Why:** a merge that takes the first member would silently relax a blocking
  control on a regulatory CDE

### DER-073 · Controls are merged on what they do, not on what they are called
- **Area:** `derive/generator.py::_coalesce`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** two controls with the same target, assertion and filter but
  different names and reasons; then two with the same assertion and *different*
  `WHERE` clauses
- **Steps:** generate
- **Expected:** the first pair merges, the second does not
- **Why:** "that is what determines whether two alerts would land on the same
  rows" — merging on name would fold two genuinely different checks

### DER-074 · Nothing Γ emits is active
- **Area:** `derive/generator.py` module docstring; `propose/adapt.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** any generation
- **Steps:** inspect every `DerivedControl`; follow it through
  `propose.adapt.from_control` into the queue
- **Expected:** it becomes a `Proposal` with `status == PROPOSED`; nothing is
  written to the control estate without a decision
- **Why:** docs/03 §5 "proposed, never silently activated" — "an estate that
  appeared without anybody agreeing to it is an estate nobody owns, and unowned
  alerts get muted rather than fixed"

### DER-075 · Generation is deterministic
- **Area:** `derive/generator.py::ControlGenerator.generate`
- **Type:** contract
- **Priority:** P1
- **Precondition:** one declaration
- **Steps:** generate twice; compare identities, content hashes and order
- **Expected:** identical, including the order of controls, unsatisfiables and
  deferrals
- **Why:** the review diff is computed on the content hash, and a generator that
  reorders produces a diff on every run

### DER-076 · A declaration that generates nothing says so
- **Area:** `derive/generator.py::Generation`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a named, owned dataset with no grain, rhythm, attributes or
  authoritativeness
- **Steps:** generate
- **Expected:** `len(generation) == 0`, `is_complete is True`, no deferrals —
  and nothing in the output distinguishes "nothing was declared" from "nothing
  could be derived"
- **Why:** the empty result is the one a user reads as a failure; the maturity
  score is what should answer it, and the two are not linked

### DER-077 · `Generation.merge` preserves all three lists
- **Area:** `derive/generator.py::Generation.merge`
- **Type:** contract
- **Priority:** P2
- **Precondition:** two generations with controls, unsatisfiables and deferrals
- **Steps:** merge
- **Expected:** concatenation in order, nothing dropped; `by_rule` and `rules()`
  reflect the merged set
- **Why:** the six rules are merged pairwise and a lost list is a silently
  smaller estate

### DER-078 · `is_complete` is false when anything is unsatisfiable
- **Area:** `derive/generator.py::Generation.is_complete`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a generation with controls and one unsatisfiable
- **Steps:** read the property
- **Expected:** `False` — deferrals do **not** make it false
- **Why:** a deferral is not a failure and an unsatisfiable is, and the console
  renders the difference

---

## `derive/relationships.py` — Γ for the thirteen kinds

### DER-079 · `REFERENCES` lowers to a correlated `EXISTS`, not a null check
- **Area:** `derive/relationships.py::RelationshipGenerator._references`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a `REFERENCES` with one match key
- **Steps:** generate; render; lower
- **Expected:** a `ReferenceAssertion` naming the target dataset and column;
  never `IS NOT NULL`
- **Why:** "an earlier implementation compiled it to `IS NOT NULL`, which passes
  on every orphan there has ever been"

### DER-080 · One control per match key
- **Area:** `derive/relationships.py::RelationshipGenerator._references`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two match keys
- **Steps:** generate
- **Expected:** two integrity controls, one per key, each with its own identity
- **Why:** a composite foreign key checked one column at a time is weaker than
  the declaration — record whether that is the intent

### DER-081 · `ENRICHES` reuses the reference mechanism with its own sentence
- **Area:** `derive/relationships.py::RelationshipGenerator._enriches`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an `ENRICHES` with one key
- **Steps:** generate
- **Expected:** the same assertion shape, `rule == "enriches.coverage"`,
  dimension `COMPLETENESS`, and a reason about "a value that came from nowhere,
  which is worse than a missing one because it will be used"
- **Why:** "saying so, rather than inventing a second mechanism, is why the same
  executor runs both"

### DER-082 · `PARENT_OF` generates the orphan check on the child side
- **Area:** `derive/relationships.py::RelationshipGenerator._parent_of`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a `PARENT_OF` from parents to children with one key
- **Steps:** generate; read the control's `target`
- **Expected:** the **to** dataset is the target, referencing back to the
  **from** dataset
- **Why:** the direction is inverted relative to `_references` and an inversion
  here checks the wrong population entirely

### DER-083 · `PARENT_OF` does not generate a cycle check, and says why
- **Area:** `derive/relationships.py::RelationshipGenerator._parent_of`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** a hierarchy
- **Steps:** generate; compare with docs/03 §2.4, which promises "cycle
  detection"
- **Expected:** no cycle control and no `Deferred` explaining its absence — the
  reasoning lives only in a docstring
- **Why:** "emitting a one-level approximation would report a clean hierarchy
  containing a loop three levels down"; the design promises the check and the
  output never mentions it

### DER-084 · `PARENT_OF` with no match key is unsatisfiable
- **Area:** `derive/relationships.py::RelationshipGenerator._parent_of`
- **Type:** negative
- **Priority:** P2
- **Precondition:** the declaration permitted by SEM-047
- **Steps:** generate
- **Expected:** `Unsatisfiable parent_of.orphan_node`, remedy "parent_id =
  node_id"
- **Why:** the declaration layer allows it and Γ refuses it; the user meets the
  refusal a step later than they should

### DER-085 · `RECONCILES_WITH` produces a comparison, not a control
- **Area:** `derive/relationships.py::RelationshipGenerator._reconciles`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a complete reconciliation declaration
- **Steps:** generate
- **Expected:** `controls == ()`; one `ComparisonSpec` of kind `RECONCILIATION`
  carrying both sides, keys, compare, tolerance, offset, cardinality, filter and
  a `workflow` describing classification, ageing and the closing certificate
- **Why:** "'the sub-ledger and the GL agree to a euro' is not a row predicate
  and never will be. Compiling it into one would produce something that runs and
  answers a different question"

### DER-086 · A reconciliation declaration produces nothing on a control-only path
- **Area:** `derive/relationships.py::as_generation`; `web/routes/proposal_routes.py`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a confirmed `RECONCILES_WITH`
- **Steps:** open the proposal queue; run the console's `_generate`
- **Expected:** currently nothing at all — the queue runs the dataset
  `ControlGenerator` only and never `RelationshipGenerator`, so no proposal, no
  unsatisfiable, no explanation
- **Why:** round 1 finding **Q-48**: "declaring a `reconciles_with` relationship
  generates nothing, though the console instructs you to do it" — `as_generation`
  is documented as deliberately lossy, and the caller that uses that view offers
  the user no sign of it

### DER-087 · `DERIVES_FROM` and `AGGREGATES` both produce aggregate parity
- **Area:** `derive/relationships.py::_derives_from`, `_aggregates`
- **Type:** functional
- **Priority:** P2
- **Precondition:** one of each with keys, compare and tolerance
- **Steps:** generate
- **Expected:** both `ComparisonKind.AGGREGATE_PARITY`, with different `rule`
  strings (`derives_from.aggregate_parity`, `aggregates.rollup_parity`)
- **Why:** the rule string is what lets a systematically bad family be found
  once; identical kinds with one rule name would hide which declaration produced
  the noise

### DER-088 · `MIRRORS` produces three comparisons, not one
- **Area:** `derive/relationships.py::RelationshipGenerator._mirrors`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a `MIRRORS` with keys and `compare=("amount",)`
- **Steps:** generate
- **Expected:** `ROW_COUNT_PARITY`, `VALUE_PARITY`, `STALENESS`
- **Why:** "row-count parity alone passes a replica that copied the right number
  of rows with stale values in them; content parity alone passes one that is
  missing a thousand rows it never received"

### DER-089 · `MIRRORS` content parity demands no tolerance
- **Area:** `derive/relationships.py::RelationshipGenerator._mirrors`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a `MIRRORS` with compare and **no** tolerance
- **Steps:** generate
- **Expected:** the value-parity comparison is produced anyway
  (`require_tolerance=False`); its `tolerance` is `None`
- **Why:** "asking what difference is acceptable in a copy invites an answer,
  and any answer above zero makes the control unable to detect the thing it
  exists for"

### DER-090 · `MIRRORS` with no compared attribute produces two comparisons
- **Area:** `derive/relationships.py::RelationshipGenerator._mirrors`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `compare=()`
- **Steps:** generate
- **Expected:** row-count parity and staleness only; no content parity, no
  unsatisfiable
- **Why:** a replica declared without naming a compared field silently gets no
  content check — record whether that should be a `Deferred`

### DER-091 · `SUPERSEDES` produces a dual-run comparison with a workflow
- **Area:** `derive/relationships.py::RelationshipGenerator._supersedes`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a `SUPERSEDES` with keys and compare
- **Steps:** generate
- **Expected:** `VALUE_PARITY` with the workflow about running both while the
  old system is still authoritative
- **Why:** "a migration verified only after the cutover is a migration verified
  by the people who have to live with it"

### DER-092 · `SUPERSEDES` with no keys is unsatisfiable
- **Area:** `derive/relationships.py::_comparison_problem`
- **Type:** negative
- **Priority:** P2
- **Precondition:** the declaration permitted by SEM-044
- **Steps:** generate
- **Expected:** `Unsatisfiable`, reason "no match key joins the two datasets"
- **Why:** "without them every row on the left matches every row on the right"

### DER-093 · `SAME_ENTITY_AS` produces identifier consistency
- **Area:** `derive/relationships.py::RelationshipGenerator._same_entity`
- **Type:** functional
- **Priority:** P2
- **Precondition:** keys and `compare=("lei",)`
- **Steps:** generate
- **Expected:** `IDENTIFIER_CONSISTENCY`; the sentence reads "where A and B
  describe the same thing, matched on …, they carry the same lei"
- **Why:** docs/03 §5 — "entity resolution; duplicate parties; identifier
  consistency"

### DER-094 · `TEMPORAL_SUCCESSOR` needs a tolerance Γ demands and the declaration does not
- **Area:** `derive/relationships.py::ComparisonKind.ROLL_FORWARD`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a `TEMPORAL_SUCCESSOR` accepted by SEM-046 with no tolerance
- **Steps:** generate
- **Expected:** `Unsatisfiable`, reason "no materiality tolerance was given"
- **Why:** the declaration layer and the comparison layer disagree about the
  same relationship, so a user can save a roll-forward that can never run

### DER-095 · A roll-forward's sentence names opening, movements and closing
- **Area:** `derive/relationships.py::_COMPARISON_SENTENCES`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** a complete `TEMPORAL_SUCCESSOR`
- **Steps:** `describe()`
- **Expected:** "the opening balance in A plus the movements equals the closing
  balance in B"
- **Why:** docs/03 §5's row for this relationship, and the sentence an approver
  reads

### DER-096 · `MUTUALLY_EXCLUSIVE` produces overlap detection with no tolerance
- **Area:** `derive/relationships.py::_mutually_exclusive`
- **Type:** functional
- **Priority:** P2
- **Precondition:** keys only
- **Steps:** generate
- **Expected:** `OVERLAP`; no tolerance demanded, no compared attribute demanded
- **Why:** a record being in both populations is a boolean, and demanding a
  materiality for it would be nonsense

### DER-097 · `TOGETHER_COMPLETE` produces population coverage
- **Area:** `derive/relationships.py::_together_complete`
- **Type:** functional
- **Priority:** P2
- **Precondition:** keys only
- **Steps:** generate
- **Expected:** `COVERAGE`; the sentence names "the population"
- **Why:** docs/03 §2.4 promises a control "against a declared universe", and
  the spec names no universe — record what supplies it

### DER-098 · `FEEDS` produces an edge and deliberately no check
- **Area:** `derive/relationships.py::RelationshipGenerator._feeds`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a `FEEDS`
- **Steps:** generate
- **Expected:** no controls, no comparisons, one `Edge` with
  `carries_trust is True`
- **Why:** "that control already exists — it is the target's own rhythm — and
  generating a second one produces two alerts for one late file, from two
  different declarations, which is how an estate becomes unowned"

### DER-099 · Every kind produces exactly one edge
- **Area:** `derive/relationships.py::RelationshipGenerator.generate`
- **Type:** contract
- **Priority:** P1
- **Precondition:** one declaration per kind, each minimally valid
- **Steps:** generate all thirteen
- **Expected:** thirteen generations, each with exactly one edge, `source` and
  `target` in declaration order, and a reason ending in a sentence that starts
  with a capital
- **Why:** the edge is what impact analysis and trust propagation walk; a kind
  that produced none would be invisible to both

### DER-100 · An edge is produced even when the generation is unsatisfiable
- **Area:** `derive/relationships.py::RelationshipGenerator.generate`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a `RECONCILES_WITH` with no tolerance
- **Steps:** generate
- **Expected:** one unsatisfiable **and** one edge — the merge happens
  unconditionally
- **Why:** a relationship that cannot be checked is still a relationship that
  describes the estate, and the map should show it

### DER-101 · A comparison with nothing to compare is refused
- **Area:** `derive/relationships.py::_comparison_problem`
- **Type:** negative
- **Priority:** P1
- **Precondition:** each kind whose `needs_compared_attributes` is true, with
  `compare=()`
- **Steps:** generate
- **Expected:** `Unsatisfiable`, remedy "a comparison with nothing to compare
  reports a clean result over any two datasets at all"
- **Why:** the failure mode is a green reconciliation, which is the most
  expensive possible wrong answer

### DER-102 · The three refusals are checked in a fixed order
- **Area:** `derive/relationships.py::_comparison_problem`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a declaration missing compare, tolerance and keys at once
- **Steps:** generate
- **Expected:** exactly one `Unsatisfiable`, naming the compared attribute —
  the first check wins
- **Why:** a user fixing one gap at a time meets three round trips; record
  whether one combined message would be better

### DER-103 · A comparison renders a canonical, diffable line
- **Area:** `derive/relationships.py::ComparisonSpec.render`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a full reconciliation
- **Steps:** render twice; then change the tolerance and render again
- **Expected:** `COMPARE a WITH b ON (…) MATCHING amount WITHIN 1 EUR OR 0.1%
  OFFSET … WHERE … AS RECONCILIATION`; stable between runs; the `content_hash`
  moves only on the change
- **Why:** the review queue diffs on this string, and it is the only rendering a
  comparison has

### DER-104 · Only kinds that need them carry compared attributes
- **Area:** `derive/relationships.py::RelationshipGenerator._comparison`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a `MUTUALLY_EXCLUSIVE` declared with `compare=("amount",)`
- **Steps:** generate
- **Expected:** the spec's `compare` is empty — `kind.needs_compared_attributes`
  gates it
- **Why:** carrying an irrelevant field into the executor invites it to be used

### DER-105 · A comparison's severity is passed in, not guessed
- **Area:** `derive/relationships.py::RelationshipGenerator.__init__`
- **Type:** contract
- **Priority:** P2
- **Precondition:** two datasets of different tiers
- **Steps:** generate with the default severity, then with the higher of the two
- **Expected:** the default is `MAJOR`; the caller's value is honoured
  throughout
- **Why:** "the honest default is the *higher* of the two — which the caller
  knows and this class does not"; find the caller and confirm it computes it

### DER-106 · A comparison's identity is stable and distinct per rule
- **Area:** `derive/relationships.py::RelationshipGenerator._comparison`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a `MIRRORS`, which produces three comparisons
- **Steps:** read the three identities; regenerate
- **Expected:** three distinct, stable identities — the rule is part of the key
- **Why:** a `MIRRORS` whose three comparisons collided would present one
  proposal where three checks are meant

### DER-107 · An unnamed relationship falls back to its kind for identity
- **Area:** `derive/relationships.py::RelationshipGenerator._comparison`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two `MIRRORS` relationships between different dataset pairs,
  neither named
- **Steps:** compare identities
- **Expected:** distinct, because the dataset ids are also in the key; but two
  unnamed relationships of the same kind between the *same* pair collide
- **Why:** two declarations between one pair — a reconciliation on amount and
  one on quantity — is a real estate shape

---

## `derive/coverage.py` — what is protected, and what only looks it

### DER-108 · Coverage is counted per attribute-dimension pair
- **Area:** `derive/coverage.py::CoverageAnalyser.analyse`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a LEI attribute, mandatory and semantically typed, with a
  completeness control only
- **Steps:** analyse
- **Expected:** `covered == 1`, `applicable == 2`, and one `Gap` naming the
  validity dimension
- **Why:** "a single `IS NOT NULL` on a column makes it 'covered' while its
  format, its domain and its consistency go unchecked"

### DER-109 · The flattering number is kept beside the honest one
- **Area:** `derive/coverage.py::Coverage.touched_fraction`
- **Type:** contract
- **Priority:** P1
- **Precondition:** ten attributes each with one control of four applicable
  dimensions
- **Steps:** read `fraction` and `touched_fraction`; read `describe()`
- **Expected:** 0.25 and 1.0; the summary says which one flatters, when the gap
  exceeds ten points
- **Why:** keeping both makes the difference visible "rather than a choice
  somebody made about which to report"

### DER-110 · Only applicable dimensions are counted
- **Area:** `derive/coverage.py::CoverageAnalyser._applicable`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a free-text, optional, non-monetary, non-CDE attribute
- **Steps:** analyse
- **Expected:** zero applicable dimensions, no gaps, and it does not drag the
  fraction down
- **Why:** "counting dimensions an attribute cannot have would make a
  well-covered estate look sparse and would hide the real gaps in the noise"

### DER-111 · An optional attribute has no completeness dimension
- **Area:** `derive/coverage.py::CoverageAnalyser._applicable`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** one optional attribute, one conditional, one mandatory
- **Steps:** analyse
- **Expected:** completeness applicable for the last two only
- **Why:** "an estate could only reach 100% by declaring every column mandatory,
  which … pushes people into false declarations to move a metric" — and note the
  default *is* optional, so an unconsidered column looks answered

### DER-112 · A CDE earns an accuracy dimension and nothing else does
- **Area:** `derive/coverage.py::CoverageAnalyser._applicable`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a CDE and a non-CDE, otherwise identical
- **Steps:** analyse
- **Expected:** `ACCURACY` applicable only for the CDE
- **Why:** "for anything else there is nothing to compare against that is not
  equally unverified"

### DER-113 · An integrity control satisfies the accuracy expectation
- **Area:** `derive/coverage.py::CoverageAnalyser._protected`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a CDE with a `REFERENCES` control against a master
- **Steps:** analyse
- **Expected:** `ACCURACY` counted as covered
- **Why:** "reporting a CDE with a master-data check as having no accuracy
  control … is not true in any sense a reviewer would recognise"

### DER-114 · A currency control on the code column covers the amount's consistency
- **Area:** `derive/coverage.py::CoverageAnalyser._is_covered`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `exposure_amount` denominated in `exposure_ccy`, with the
  generated currency control on `exposure_ccy`
- **Steps:** analyse
- **Expected:** the amount's consistency dimension is covered
- **Why:** "requiring the control to sit on the amount would report a correctly
  controlled pair as a gap, and the remedy would be to write a second control
  that checks the same thing"

### DER-115 · A control with no declared dimension covers nothing
- **Area:** `derive/coverage.py::CoverageAnalyser._protected`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a hand-written control with `dimensions=()`
- **Steps:** analyse
- **Expected:** the attribute reads as touched but not covered on any dimension
- **Why:** "quietly assuming a dimension for them would produce a coverage
  number that is wrong and confident"

### DER-116 · Every assertion shape is attributed to its columns
- **Area:** `derive/coverage.py::_subjects`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** one control of each shape — predicate, reference, unique
  key, functional dependency, row count, freshness
- **Steps:** analyse
- **Expected:** subjects extracted for the first four; the row-count and
  freshness controls attribute to no attribute at all
- **Why:** the dataset-level dimensions are excluded by design
  (`DATASET_DIMENSIONS`), and a shape that falls through silently makes a real
  control invisible to coverage

### DER-117 · Gap risk stays separable all the way to the end
- **Area:** `derive/coverage.py::Gap.risk`
- **Type:** regression
- **Priority:** P1
- **Precondition:** four gaps on one Tier 1 dataset: a CDE with an obligation on
  completeness, a CDE without, a non-CDE on completeness, a non-CDE on validity
- **Steps:** sort by risk
- **Expected:** four distinct values, strictly ordered
- **Why:** "an earlier version took `min(1.0, …)` at each step, and on a Tier 1
  dataset *every* gap scored exactly 1.00 — so 'sort by risk' degenerated into
  alphabetical order, which is the one thing a ranked list must not silently
  become"

### DER-118 · Risk is normalised into [0, 1]
- **Area:** `derive/coverage.py::MAXIMUM_RISK`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** the maximal gap — Tier 1, CDE, obligation, completeness
- **Steps:** read `risk`
- **Expected:** exactly 1.0; the minimal gap (Tier 4, nothing else) is 0.25/2.3
- **Why:** a score that can exceed one is a score nobody can put on a dashboard

### DER-119 · Criticality is clamped rather than trusted
- **Area:** `derive/coverage.py::Gap.risk`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** gaps with criticality 0 and 9 (reachable via SEM-161)
- **Steps:** read `risk`
- **Expected:** treated as 1 and 4 — `max(1, min(4, …))`
- **Why:** an unclamped tier would produce a negative or outsized risk and
  invert the ranking

### DER-120 · The wave's target is measured honestly
- **Area:** `derive/coverage.py::Coverage.meets_target`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a dataset at 85% overall and 90% on CDEs
- **Steps:** read `meets_target`
- **Expected:** `False` — both thresholds must hold (≥ 0.8 and ≥ 0.95)
- **Why:** the acceptance criterion is a conjunction, and reporting on the
  overall number alone is precisely the flattering failure the module is about

### DER-121 · A dataset with no attributes reports full coverage
- **Area:** `derive/coverage.py::Coverage.fraction`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a declared dataset with no attributes
- **Steps:** analyse
- **Expected:** `fraction == 1.0`, `cde_fraction == 1.0`, `meets_target is True`
- **Why:** an undescribed dataset reporting 100% coverage is the flattering
  direction; the maturity score is what is supposed to catch it, and nothing
  links the two

### DER-122 · The estate view is ordered worst-covered first
- **Area:** `derive/coverage.py::CoverageAnalyser.analyse_estate`
- **Type:** functional
- **Priority:** P2
- **Precondition:** three datasets with different CDE and overall fractions
- **Steps:** analyse the estate
- **Expected:** sorted by CDE fraction, then overall, then name — so a dataset
  with uncovered CDEs comes first regardless of its overall number
- **Why:** "the purpose of the list is to be worked from the top"

### DER-123 · A gap names the remedy, and the remedy fits the dimension
- **Area:** `derive/coverage.py::CoverageAnalyser._remedy`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a gap on each of the four attribute dimensions, with and
  without a semantic type
- **Steps:** read each remedy
- **Expected:** four distinct sentences; the validity remedy names the declared
  semantic type when there is one
- **Why:** "a gap report that names the problem and not the fix is a list
  somebody reads once"

### DER-124 · `worst()` is deterministic under ties
- **Area:** `derive/coverage.py::Coverage.worst`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** several gaps with identical risk
- **Steps:** call twice
- **Expected:** the same order — ties break on attribute name
- **Why:** a list that reshuffles between refreshes looks broken even when it is
  not

---

## `derive/suggestions.py` — inferred, and never confirmed by inference

### DER-125 · A single key candidate is offered pre-filled
- **Area:** `derive/suggestions.py::_grain`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a representative profile with exactly one key candidate
- **Steps:** `defaults_from(profile)`
- **Expected:** one suggestion for `grain`, `value` set, `prefill is True`,
  `because` reading "distinct in every row and never null"
- **Why:** "the form should arrive already filled in with what the data
  suggests"

### DER-126 · Several candidates are offered as a list and never as a combination
- **Area:** `derive/suggestions.py::_grain`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a profile with three key candidates
- **Steps:** read the suggestion
- **Expected:** `value == ""`, `prefill is False`, and the sentence says the
  profile "has not tested whether any combination does"
- **Why:** "'account_id and as_of_date together are unique' is a claim it has
  not made, and inventing it would be the one suggestion here nobody could
  check"

### DER-127 · An unrepresentative profile pre-fills nothing
- **Area:** `derive/suggestions.py::defaults_from`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a head-sample profile with one key candidate
- **Steps:** read `anything_prefilled` and the suggestion
- **Expected:** the candidate is offered, `prefill is False`, and `describe()`
  says nothing is pre-filled because the profile read the first rows only
- **Why:** "a pre-filled form that a person clicks through has produced a
  *declaration nobody made*, and every control derived from it inherits an
  authority it never earned"

### DER-128 · Every suggestion carries its evidence and the profile's own confidence
- **Area:** `derive/suggestions.py::Suggestion`
- **Type:** contract
- **Priority:** P1
- **Precondition:** any suggestion
- **Steps:** read `because` and `confidence`
- **Expected:** a sentence with a number in it, and the profile's confidence
  note carried rather than restated
- **Why:** "a default whose basis is invisible is a default nobody can disagree
  with, and a default nobody can disagree with is not confirmed when they accept
  it"

### DER-129 · A profile with no key candidates suggests nothing, and says so
- **Area:** `derive/suggestions.py::Defaults.describe`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a profile with no candidates and no warnings
- **Steps:** `describe()`
- **Expected:** "was profiled and suggested nothing. That is a statement about
  the profile, not about the dataset"
- **Why:** the empty result is the one a user reads as a verdict on their data

### DER-130 · An all-null column warns and does not suggest
- **Area:** `derive/suggestions.py::_warnings`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a column null in every row read
- **Steps:** read the warnings
- **Expected:** one `Warning_`, consequence explaining that a control on it
  fails everything or passes everything, and that the source probably stopped
  populating it
- **Why:** "warnings are separate from defaults … presenting it as one would
  mean the reader either takes it or dismisses it, when what they need to do is
  look"

### DER-131 · At most one warning per column, and the true one wins
- **Area:** `derive/suggestions.py::_warnings`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a column 70% null whose populated values are all one value —
  sparse *and* constant *and* dominant
- **Steps:** read the warnings
- **Expected:** exactly one, the sparse one; never "holds one value in every
  row", which is false about that column
- **Why:** "a false statement that happens to be reachable from a true
  predicate"

### DER-132 · A constant column is described by distinct count, not by row coverage
- **Area:** `derive/suggestions.py::_warnings`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a column with one distinct value and 10% nulls
- **Steps:** read the message
- **Expected:** "holds one distinct value in the rows read" — not "one value in
  every row"
- **Why:** "the distinct count ignores nulls, so a column with some nulls would
  otherwise be described as full of a value it lacks"

### DER-133 · A dominant value warns below the constant threshold
- **Area:** `derive/suggestions.py::DOMINANT_SHARE`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** columns at 89%, 90% and 91% dominance, none sparse or
  constant
- **Steps:** read the warnings
- **Expected:** the threshold is `dominant_value`'s, quoted here as 0.9 "so the
  two cannot drift" — confirm the two agree
- **Why:** a duplicated constant is a constant that will drift; the comment says
  it is quoted rather than rediscovered

### DER-134 · The sparse threshold is half
- **Area:** `derive/suggestions.py::SPARSE_RATE`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** columns at 49% and 50% null
- **Steps:** read the warnings
- **Expected:** only the second warns — `>=`
- **Why:** "the point is to prompt a look, not to make a ruling"

### DER-135 · An empty column is skipped entirely
- **Area:** `derive/suggestions.py::_warnings`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a profile whose column reports `rows == 0`
- **Steps:** read the warnings
- **Expected:** none — no division by zero
- **Why:** an empty table must produce an empty suggestion set rather than an
  exception on a preview screen

### DER-136 · Only a grain is ever suggested
- **Area:** `derive/suggestions.py::defaults_from`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** a rich profile — semantic types inferred, ranges observed,
  a plausible rhythm
- **Steps:** read the suggestions
- **Expected:** one field only, `grain`; nothing suggests criticality, semantic
  type, value domain or optionality
- **Why:** the module is named for declaration defaults in general and
  implements one; a declaration form that pre-fills one field of twenty is where
  people stop

---

## `propose/` — the single mutation channel

### PRP-001 · A derived control becomes a proposal without losing anything
- **Area:** `propose/adapt.py::from_control`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a generated control
- **Steps:** adapt it
- **Expected:** identity, content, content hash, provenance, description,
  dataset, subject, rule and severity all carried
- **Why:** "the generators know how to derive controls and nothing about review;
  the queue knows about review and nothing about PQL" — everything a reviewer
  needs crosses here or nowhere

### PRP-002 · A comparison becomes a proposal of the same shape
- **Area:** `propose/adapt.py::from_comparison`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a `RECONCILES_WITH` comparison spec
- **Steps:** adapt it
- **Expected:** `content` is the `COMPARE …` line; `subject` is the compared
  attributes, or the right-hand dataset when there are none
- **Why:** "a reviewer should not have to learn a second screen because the
  check happens to span two datasets"

### PRP-003 · A proposal's subject is extracted from every assertion shape
- **Area:** `propose/adapt.py::from_control`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a predicate control, a reference control and a unique-key
  control
- **Steps:** adapt each
- **Expected:** subject from `subject`, then `column`; the unique-key control
  falls through to `""`
- **Why:** the subject drives `subject_already_covered` in the utility score, so
  an empty one scores a uniqueness proposal as though nothing were covered

### PRP-004 · `from_relationship` carries both controls and comparisons
- **Area:** `propose/adapt.py::from_relationship`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a `MIRRORS` generation — no controls, three comparisons
- **Steps:** adapt
- **Expected:** three proposals
- **Why:** the path `from_generation` cannot see; a caller using the wrong one
  produces the Q-48 silence (DER-086)

### PRP-005 · A rejection must state a reason
- **Area:** `propose/proposal.py::Decision.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** build a `REJECTED` decision with `reason=None`
- **Expected:** `ValueError` explaining that the reason decides whether the rule
  comes back and whether the generator has a defect
- **Why:** "a free-text reason would be easier and would be worth much less"

### PRP-006 · Only two rejection reasons indict the rule
- **Area:** `propose/proposal.py::RejectionReason.indicts_the_rule`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** read the property for all six
- **Expected:** true for `INCORRECT` and `COINCIDENTAL` only
- **Why:** "forty from the same rule is a bug somebody should fix once rather
  than forty reviewers dismissing it one at a time"

### PRP-007 · Three reasons may be reconsidered, three may not
- **Area:** `propose/proposal.py::RejectionReason.may_be_reconsidered`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** read for all six
- **Expected:** true for `NOT_MATERIAL`, `TOO_NOISY`, `PENDING_REMEDIATION`;
  false for `INCORRECT`, `COINCIDENTAL`, `DUPLICATE`
- **Why:** "a rule rejected as *incorrect* is wrong however the data changes" —
  re-offering it on new data re-asks a question about the rule using evidence
  about the data

### PRP-008 · A backtest states what the control would have done
- **Area:** `propose/proposal.py::Backtest.describe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 1,000 rows, 410 violations, 30 days, two segments
- **Steps:** read `describe()`, `violation_rate`, `alerts_per_day`
- **Expected:** "would have flagged 410 of 1,000 rows (41.00%), about 14 a day,
  concentrated in …"
- **Why:** "'this would have failed 41% of rows every day last month' answers
  the approve-or-not question outright, and no amount of reading the rule does"

### PRP-009 · An unactionable backtest is marked before anybody looks
- **Area:** `propose/proposal.py::Backtest.is_unactionable`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** violation rates of 0.20 and 0.21 over 1,000 rows
- **Steps:** read the property
- **Expected:** false then true — strictly greater than a fifth
- **Why:** "a control failing more than a fifth of rows is not identifying
  exceptions; it is describing the data"

### PRP-010 · A backtest that could not run is not a clean backtest
- **Area:** `propose/proposal.py::Backtest.ran`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `unavailable="the column does not exist in retained
  snapshots"`; then `scanned=0` with no `unavailable`
- **Steps:** read `ran`, `would_pass_today`, `is_unactionable`, `describe()`
- **Expected:** `ran` false in both; `would_pass_today` false; not unactionable;
  distinct sentences for the two cases
- **Why:** "not backtested" and "backtested and clean" must never render the
  same, or an untested control is approved as a proven one

### PRP-011 · Zero days does not divide by zero
- **Area:** `propose/proposal.py::Backtest.alerts_per_day`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `days=0`, `violations=5`
- **Steps:** read the property
- **Expected:** 5.0
- **Why:** it is read by `describe()` on every proposal card

### PRP-012 · Only a declaration may run without review
- **Area:** `core/provenance.py::Origin.may_auto_activate`;
  `propose/proposal.py::Proposal.needs_review`
- **Type:** security
- **Priority:** P1
- **Precondition:** one proposal per origin
- **Steps:** read `needs_review`
- **Expected:** false for `DECLARATION` only; true for `IMPORT`, `DOCUMENT`,
  `MINING`, `EXAMPLE`, `INDUCTION`
- **Why:** **nothing mined may auto-activate** — "a column that happens to be
  unique in today's extract is not a declared key, and enforcing it turns the
  first legitimate duplicate into an incident"

### PRP-013 · A declaration whose backtest would drown the queue still needs review
- **Area:** `propose/proposal.py::Proposal.needs_review`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a declaration-origin proposal with a 41% backtest
- **Steps:** read `needs_review`
- **Expected:** `True` — the backtest check precedes the origin check
- **Why:** "it means the data does not match the declaration, and that is a
  conversation rather than an alert"

### PRP-014 · Origins are ranked, and the ranking is total
- **Area:** `core/provenance.py::Origin.authority`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** read for all six
- **Expected:** declaration 100 > document 80 > import 60 > mining 40 > example
  30 > induction 20; no ties
- **Why:** it decides which of two proposals for the same thing survives a merge

### PRP-015 · A document-origin provenance without a citation is refused
- **Area:** `core/provenance.py::Provenance.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** build one with `origin=DOCUMENT`, `citation=None`
- **Expected:** `ValueError` — "an unfalsifiable rule will not be approved"
- **Why:** `FR-IND-012`; the citation is the only thing that makes a document
  rule disputable

### PRP-016 · An identical re-offer of a live control is not a duplicate proposal
- **Area:** `propose/queue.py::ProposalQueue.offer`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an identity registered live with the same content hash
- **Steps:** offer it
- **Expected:** `outcome == "already_live"`, `proposal is None`, not admitted
- **Why:** a nightly regeneration must not re-ask about every control already
  running

### PRP-017 · A changed re-offer of a live control is a revision
- **Area:** `propose/queue.py::ProposalQueue.offer`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the same identity registered live with a different hash
- **Steps:** offer it
- **Expected:** admitted with `outcome == "superseded"`, `supersedes` set to the
  live hash, and a detail saying approving it replaces rather than adds
- **Why:** "a proposal that changes an existing control is a different decision
  from one that adds a new control, and a queue that renders them identically
  gets the first waved through"

### PRP-018 · A rejected proposal is suppressed
- **Area:** `propose/queue.py::ProposalQueue.offer`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a proposal rejected as `NOT_MATERIAL` at a 3% violation rate
- **Steps:** offer the identical proposal again
- **Expected:** not admitted; `outcome == "suppressed"`; the detail names the
  reason, the reviewer and the date
- **Why:** "a miner that re-proposes 'this column should be non-null' every
  Tuesday … teaches them that the queue is noise, and then the one proposal that
  mattered goes unread with the rest"

### PRP-019 · A materially worse violation rate reopens a suppression
- **Area:** `propose/queue.py::Suppression.reopened_by`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** rejected as `NOT_MATERIAL` at 3%
- **Steps:** offer again at 5.9%, then at 6.0%, then at 40%
- **Expected:** suppressed, reopened, reopened — the ratio threshold is 2.0; the
  reopening detail says "you rejected this when 3.0% of rows failed it; 40.0%
  fail it now"
- **Why:** "a rate that has doubled is describing a different situation, while
  one that has drifted by a point is describing the same one"

### PRP-020 · A `TOO_NOISY` rejection also reopens when the rate falls
- **Area:** `propose/queue.py::Suppression.reopened_by`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** rejected as `TOO_NOISY` at 40%
- **Steps:** offer again at 19%, then at 21%
- **Expected:** reopened, then suppressed — the falling branch is
  `TOO_NOISY`-only
- **Why:** the objection was the noise, and the noise has gone; the same fall on
  a `NOT_MATERIAL` rejection changes nothing about materiality

### PRP-021 · A permanent rejection never reopens
- **Area:** `propose/queue.py::Suppression.is_permanent`
- **Type:** security
- **Priority:** P1
- **Precondition:** rejected as `INCORRECT` at 3%
- **Steps:** offer again at 90%
- **Expected:** suppressed
- **Why:** re-offering it "would be re-asking a question about the rule using
  evidence about the data"

### PRP-022 · A suppression with no rate on either side does not reopen
- **Area:** `propose/queue.py::Suppression.reopened_by`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** rejected with no backtest; re-offered with one, and
  vice versa
- **Steps:** offer
- **Expected:** suppressed in both directions
- **Why:** there is nothing to compare, and reopening on an absent measurement
  would re-ask on every regeneration

### PRP-023 · A rejection at zero violations reopens the moment anything fails
- **Area:** `propose/queue.py::Suppression.reopened_by`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** rejected as `NOT_MATERIAL` when nothing failed it
- **Steps:** offer at 0%, then at 0.5%
- **Expected:** suppressed, then reopened with "it was rejected when nothing
  failed it"
- **Why:** the ratio is undefined at zero and the branch that handles it is the
  one that fires on a newly broken feed

### PRP-024 · The same proposal from the same origin is a duplicate
- **Area:** `propose/queue.py::ProposalQueue.offer`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an open proposal
- **Steps:** offer it again from the same origin with the same hash
- **Expected:** `outcome == "duplicate"`; the existing proposal returned; the
  queue unchanged
- **Why:** a second copy in the list is the queue's own noise

### PRP-025 · The same proposal from a different origin is corroboration
- **Area:** `propose/queue.py::ProposalQueue._keep_stronger`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a declaration-origin proposal open; a mining-origin proposal
  with the same identity and hash
- **Steps:** offer the second
- **Expected:** `outcome == "corroborated"`; the surviving proposal keeps the
  declaration's provenance and gains a `Corroboration` naming mining
- **Why:** "the naive move is to drop one; that discards the most interesting
  thing that can happen here" — and the reviewer approves in a second

### PRP-026 · Corroboration keeps the higher authority whichever order they arrive in
- **Area:** `propose/queue.py::ProposalQueue._keep_stronger`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** the same pair, mining offered first
- **Steps:** offer mining, then the declaration
- **Expected:** the declaration survives and mining is the corroboration
- **Why:** arrival order is an accident of scheduling and must not decide
  authority

### PRP-027 · A second corroboration from an origin already recorded is ignored
- **Area:** `core/provenance.py::Provenance.corroborated_by`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a proposal already corroborated by mining
- **Steps:** offer another mining proposal for the same identity
- **Expected:** one corroboration, not two
- **Why:** a provenance sentence listing "confirmed by it holds in the data and
  it holds in the data" reads as a defect

### PRP-028 · A changed proposal for the same open identity supersedes it
- **Area:** `propose/queue.py::ProposalQueue.offer`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an open proposal
- **Steps:** offer one with the same identity and a different hash
- **Expected:** admitted, `supersedes` set to the old hash, the old proposal
  replaced in the open map
- **Why:** the reviewer must see one current version of a question, with what it
  replaced

### PRP-029 · Deciding a proposal that is not open fails with a useful message
- **Area:** `propose/queue.py::ProposalQueue._require_open`
- **Type:** negative
- **Priority:** P2
- **Precondition:** one decided proposal and one never offered
- **Steps:** accept each
- **Expected:** `KeyError` in both, distinguishing "it was already decided" from
  "it was never offered, or was suppressed"
- **Why:** the two send an operator to different places

### PRP-030 · Accepting and rejecting both move the proposal out of the queue
- **Area:** `propose/queue.py::ProposalQueue._settle`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two open proposals
- **Steps:** accept one, reject the other; read `pending`, `decided`,
  `suppressions`
- **Expected:** neither pending; both decided; only the rejected one suppressed;
  both recorded in the acceptance history
- **Why:** a decided proposal that stays in the queue is a question asked twice

### PRP-031 · A deferred proposal stays open and out of the ranked list
- **Area:** `propose/queue.py::ProposalQueue.defer`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an open proposal
- **Steps:** defer it with a reason; read `pending` and `deferred`
- **Expected:** absent from `pending`, present in `deferred`, `is_open` true,
  `deferred_because` carried
- **Why:** "a deferred proposal comes back and a rejected one does not"

### PRP-032 · `auto_activatable` is almost always empty
- **Area:** `propose/queue.py::ProposalQueue.auto_activatable`
- **Type:** security
- **Priority:** P1
- **Precondition:** a queue holding proposals of every origin, including a
  mined key with perfect evidence
- **Steps:** read it
- **Expected:** declaration-origin proposals only, and only those whose backtest
  is not unactionable
- **Why:** the one place the auto-activation rule is applied in aggregate; a
  mined proposal appearing here is the failure the whole propose package exists
  to prevent

### PRP-033 · A reloaded queue remembers its rejections
- **Area:** `propose/queue.py::suppression_from`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a decided, rejected proposal read back from storage
- **Steps:** build a suppression from it and register it on a fresh queue; offer
  the proposal again
- **Expected:** suppressed; and `suppression_from` on an *accepted* proposal
  raises `ValueError`
- **Why:** the memory has to survive a restart or it is not a memory

### PRP-034 · The queue summary counts what a person should act on
- **Area:** `propose/queue.py::ProposalQueue.summary`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a queue with pending, deferred, decided and suppressed
  proposals, some noisy, and a rule with five `INCORRECT` rejections
- **Steps:** read the summary
- **Expected:** every count correct; `by_origin` totals the pending list;
  `suspect_rules` names the indicted rule; `top` is the ten best identities
- **Why:** it is the report put in front of somebody, and a count that includes
  suppressed proposals in "pending" would misstate the backlog

### PRP-035 · Utility weights and the prior ceiling are what the docstring says
- **Area:** `propose/utility.py::WEIGHTS`, `PRIOR_CEILING`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** read them
- **Expected:** criticality 0.35, coverage gap 0.25, confidence 0.20, acceptance
  prior 0.20; the ceiling equals the prior weight
- **Why:** "they sum to more than 1 before the noise penalty, which is
  deliberate: the ranking only has to be an order"

### PRP-036 · Criticality scores a tier, and a CDE counts as one up
- **Area:** `propose/utility.py::UtilityScorer._criticality`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** contexts for tiers 1–4, with and without `is_cde`
- **Steps:** score
- **Expected:** 1.0, 0.75, 0.5, 0.25; a Tier 2 CDE scores 1.0; a Tier 1 CDE is
  clamped at 1.0
- **Why:** the clamp `max(1, min(4, …))` is the boundary, and an unclamped CDE
  on Tier 1 would score above the ceiling

### PRP-037 · A covered subject scores no coverage value
- **Area:** `propose/utility.py::UtilityScorer._coverage_gap`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `subject_already_covered=True` on an otherwise unprotected
  dataset
- **Steps:** score
- **Expected:** 0.0 — "not because the proposal is wrong, but because a second
  control on a covered column adds far less than a first control on an uncovered
  one, and the queue has to choose"
- **Why:** it is the term that surfaces the unprotected ground

### PRP-038 · Confidence is set by origin and a declaration does not reach 1.0
- **Area:** `propose/utility.py::UtilityScorer._confidence`
- **Type:** contract
- **Priority:** P1
- **Precondition:** one proposal per origin
- **Steps:** score
- **Expected:** declaration 0.9, document 0.85, import 0.7, mining 0.55, example
  0.45, induction 0.35; corroboration adds 0.15, clamped at 1.0
- **Why:** "the ceiling is reserved rather than wasted. Scoring it 1.0 would make
  corroboration invisible precisely where it is worth the most"

### PRP-039 · An origin with no entry in the confidence table raises
- **Area:** `propose/utility.py::UtilityScorer._confidence`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a new `Origin` member added to the enum
- **Steps:** score a proposal with it
- **Expected:** `KeyError` — the dict lookup is unguarded, so a new origin
  breaks ranking rather than defaulting
- **Why:** the propose package is designed so "a new source of rules can reach
  the queue without either side learning about the other"; this is the one place
  it must be edited

### PRP-040 · The noise penalty scales with how badly
- **Area:** `propose/utility.py::UtilityScorer._noise_penalty`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** backtests at 0%, 5%, 5.1%, 30% and 60%
- **Steps:** score
- **Expected:** 0, 0, -0.051, -0.3, -0.5 (clamped)
- **Why:** "there is a real difference between a control that flags 5% of rows —
  plausibly a genuine backlog — and one that flags 60%, which is describing the
  data"

### PRP-041 · A proposal with no backtest is not penalised
- **Area:** `propose/utility.py::UtilityScorer._noise_penalty`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `backtest=None`, then a backtest with `unavailable` set
- **Steps:** score
- **Expected:** 0.0 in both
- **Why:** an unmeasured control must not be ranked below a measured bad one

### PRP-042 · The total score never goes negative
- **Area:** `propose/utility.py::UtilityScorer.score`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a Tier 4 proposal on a fully covered dataset with a 90%
  backtest
- **Steps:** score
- **Expected:** `max(0.0, total)` — zero, not negative
- **Why:** the sort is stable at zero and a negative score would rank below
  proposals that have not been measured at all

### PRP-043 · The prior is Laplace-smoothed, so one rejection does not kill a rule
- **Area:** `propose/utility.py::AcceptanceHistory.rate`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a rule with no history, then one rejection
- **Steps:** read `rate("rule:x")`
- **Expected:** 0.5, then 0.333… — never 0.0
- **Why:** "reject the first proposal a rule ever makes and its rate is 0/1;
  every later proposal from that rule sorts to the bottom, where nobody reads
  it … the rule is dead on one reviewer's Tuesday afternoon, permanently"

### PRP-044 · The learned term is bounded
- **Area:** `propose/utility.py::UtilityScorer.score`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a rule with twenty acceptances and no rejections
- **Steps:** score a Tier 4 proposal from it against a Tier 1 CDE proposal from
  a rule with a poor record
- **Expected:** the prior is capped at `PRIOR_CEILING`, and the Tier 1 CDE still
  outranks
- **Why:** "learning which rules produce good proposals is worth having;
  learning it so hard that the estate stops improving is not"

### PRP-045 · Two rejection reasons are not counted against the rule
- **Area:** `propose/utility.py::NOT_THE_RULES_FAULT`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a rule whose proposals are rejected as
  `PENDING_REMEDIATION` and `DUPLICATE`
- **Steps:** record both; read the rate and the observation count
- **Expected:** unchanged from no history at all
- **Why:** "counting it against the rule that correctly identified the problem
  would teach the ranker to bury exactly the findings that led to a remediation
  — the ones that worked"

### PRP-046 · History is keyed by origin and by rule
- **Area:** `propose/utility.py::AcceptanceHistory._keys`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** proposals with and without a `rule`
- **Steps:** record; read `prior`
- **Expected:** the prior is the mean over the keys present; a proposal with no
  rule is scored on its origin alone
- **Why:** an unruled proposal must not divide by zero, and must not inherit
  another rule's record

### PRP-047 · Undecided proposals teach nothing
- **Area:** `propose/utility.py::AcceptanceHistory.record`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a proposed and a deferred proposal
- **Steps:** record both; read the rates
- **Expected:** unchanged
- **Why:** a deferred proposal is a decision postponed, and counting it as a
  rejection would punish the rules whose proposals are hardest to judge

### PRP-048 · Five indicting rejections make a rule suspect
- **Area:** `propose/utility.py::AcceptanceHistory.suspect_rules`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** one rule with four `INCORRECT` rejections, another with five
- **Steps:** read `suspect_rules()` and `indicted_rules(history)`
- **Expected:** only the second, sorted, with its count
- **Why:** "a rule rejected as *incorrect* five times is producing wrong
  proposals systematically, and the fix is in the generator rather than in the
  queue"

### PRP-049 · The ranking explains itself
- **Area:** `propose/utility.py::UtilityScorer._explain`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a Tier 1 CDE proposal on a 20%-covered dataset from a rule
  with three decisions, whose backtest flags 30%
- **Steps:** read `utility.explanation`
- **Expected:** four clauses — the tier and CDE, the unprotected share, the
  rule's acceptance rate with its count, and the noise mark-down
- **Why:** "a reviewer asking 'why is this at the top?' deserves 'because it is
  a Tier 1 CDE with no control on it and the evidence is a check digit' and not
  '0.87'"

### PRP-050 · The explanation is assembled, never stored
- **Area:** `propose/utility.py::UtilityScorer._explain`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a scored proposal, then a changed context
- **Steps:** re-score; compare the explanation with the components
- **Expected:** it moves with the score
- **Why:** "a stored explanation drifts from the score it explains — and a wrong
  explanation of a ranking is worse than none, because it is the one somebody
  repeats"

### PRP-051 · A rule's record is only mentioned once there is one
- **Area:** `propose/utility.py::UtilityScorer._explain`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a rule with two decisions, then three
- **Steps:** read the explanation
- **Expected:** the acceptance clause appears at three, not at two
- **Why:** "50% of proposals from this rule have been accepted (2 decided)" is a
  statistic that misleads more than it informs

### PRP-052 · Ranking is stable between runs
- **Area:** `propose/utility.py::rank`
- **Type:** contract
- **Priority:** P1
- **Precondition:** several proposals with identical scores
- **Steps:** rank twice, with the input order shuffled between
- **Expected:** identical output, ties broken on identity
- **Why:** "a ranking that reshuffles equal items between refreshes looks broken
  even when it is not, and a reviewer working down a list cannot lose their
  place in it"

### PRP-053 · Ranking without a context does not fail
- **Area:** `propose/utility.py::rank`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** proposals whose `dataset` is absent from the context map
- **Steps:** rank
- **Expected:** scored against the default `Context()` — Tier 4, no coverage, no
  CDE
- **Why:** the default is the pessimistic one, which is the right direction, but
  it means an unmapped dataset's Tier 1 proposals sort as Tier 4

---

## `learn/` — the loop, and whether it helped

### PRP-054 · Arm assignment is deterministic
- **Area:** `learn/loop.py::assign`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** assign the same identity ten times; then re-assign after a
  re-proposal
- **Expected:** the same arm every time
- **Why:** "a re-run of a period reproduces the experiment exactly … an item
  cannot drift between arms when it is re-proposed, which would contaminate both
  sides at once and in opposite directions"

### PRP-055 · The holdout is roughly the requested fraction
- **Area:** `learn/loop.py::assign`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** ten thousand identities
- **Steps:** assign at `holdout=0.1`, then 0.0, then 1.0
- **Expected:** about a tenth control; none; all
- **Why:** the split has to be the split the cost statement quotes

### PRP-056 · The salt changes the split
- **Area:** `learn/loop.py::assign`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** the same identities
- **Steps:** assign with two salts
- **Expected:** different assignments, each internally stable
- **Why:** restarting an experiment must be possible without renaming every item

### PRP-057 · Pending items are counted as neither accepted nor rejected
- **Area:** `learn/loop.py::_summarise`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an arm with five accepted, three rejected, ten pending
- **Steps:** summarise
- **Expected:** `surfaced == 18`, `reviewed == 8`, `accepted == 5`,
  `pending == 10`, `precision == 0.625`
- **Why:** "treating unreviewed items as rejected understates both arms and
  treating them as accepted overstates both, and the bias is not equal between
  arms when one surfaces more items than the other"

### PRP-058 · Precision is `None` before anything is reviewed
- **Area:** `learn/loop.py::ArmResult.precision`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** an arm with items surfaced and none reviewed
- **Steps:** read `precision` and `describe()`
- **Expected:** `None`; "none reviewed yet" — not 0%
- **Why:** zero precision and no measurement are different claims, and one of
  them is defamatory about a model

### PRP-059 · Mean accepted rank is reported, because precision cannot see it
- **Area:** `learn/loop.py::ArmResult.mean_accepted_rank`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two arms accepting the same items at different ranks
- **Steps:** measure
- **Expected:** equal precision, different mean rank; the uplift sentence names
  the places gained when the difference exceeds 0.5
- **Why:** "a model that surfaces the same things in a better order has helped,
  and its precision is unchanged"

### PRP-060 · An uplift below thirty reviews per arm is not measurable
- **Area:** `learn/loop.py::Uplift.is_measurable`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 29 and 30 reviews on each side
- **Steps:** read `is_measurable` and `describe()`
- **Expected:** false then true; the false case says an interval on this much
  data is wider than any effect worth claiming
- **Why:** "a difference of five points on ninety reviews is noise, and
  publishing it as a result is how a learning loop acquires a reputation for
  claiming things"

### PRP-061 · Significance is the interval excluding zero
- **Area:** `learn/loop.py::Uplift.is_significant`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** intervals `(-0.01, 0.09)`, `(0.01, 0.09)`,
  `(-0.09, -0.01)`
- **Steps:** read the property
- **Expected:** false, true, true
- **Why:** "the only form in which 'the loop is working' is a claim rather than
  a hope" — and a significant *regression* must also be significant

### PRP-062 · The interval is a two-proportion normal approximation
- **Area:** `learn/loop.py::_difference_interval`
- **Type:** functional
- **Priority:** P2
- **Precondition:** 80/100 against 70/100
- **Steps:** compute
- **Expected:** centred on +0.10, half-width `1.96 * sqrt(p(1-p)/n + …)`; zero
  reviews on either side returns `(0.0, 0.0)`
- **Why:** the method is stated as adequate and must be the method used

### PRP-063 · The holdout cost is stated
- **Area:** `learn/loop.py::Uplift.holdout_cost`
- **Type:** contract
- **Priority:** P1
- **Precondition:** any measurement
- **Steps:** read `describe()`
- **Expected:** the number of control-arm reviews, named as "the price of
  knowing any of this"
- **Why:** "a system that hides it is one where somebody eventually turns the
  experiment off without understanding what they are giving up"

### PRP-064 · Promotion is refused when the interval covers zero
- **Area:** `learn/loop.py::consider`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a measurable uplift of +8% whose interval spans zero
- **Steps:** `consider(uplift)`
- **Expected:** not promoted; the reason says promoting on a point estimate is
  how a loop that is doing nothing accumulates a series of promotions
- **Why:** the whole reason the control arm exists

### PRP-065 · A significant regression is reported as a regression
- **Area:** `learn/loop.py::consider`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a significant uplift of **-22%**
- **Steps:** consider
- **Expected:** not promoted; the reason says the learning arm is significantly
  worse and points at the labels
- **Why:** "the other order reported a significant -22% regression as 'a real
  but small gain', which is exactly backwards and would hide a feedback loop
  teaching the model the wrong thing" — the branch order is the test

### PRP-066 · A real but small gain does not earn a refreeze
- **Area:** `learn/loop.py::consider`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** significant gains of +2.9% and +3.1% against
  `minimum_gain=0.03`
- **Steps:** consider both
- **Expected:** refused then promoted
- **Why:** refreezing restarts the experiment, and the gain has to be worth the
  restart

### PRP-067 · A promotion states its evidence
- **Area:** `learn/loop.py::consider`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a promotable uplift
- **Steps:** read the reason
- **Expected:** the difference, the interval and both review counts
- **Why:** a promotion is a change to how every queue is ordered, and the record
  of why has to survive the person who made it

---

## `induce/` — rules a model proposed, none of which reaches a person unchecked

### IND-001 · A `Validated` cannot be built without every gate
- **Area:** `induce/validate.py::Validated.__post_init__`
- **Type:** security
- **Priority:** P1
- **Precondition:** a parsed control and a plan
- **Steps:** construct `Validated(passed=(Gate.PARSE,))`
- **Expected:** `ValueError` naming the missing gates and stating that building
  one directly would reduce the guarantee to a comment
- **Why:** "100% of LLM-generated PQL is parsed, type-checked and
  sandbox-executed before display. Not 'should be' — the type below cannot be
  constructed otherwise"

### IND-002 · The five gates run in order, and the first failure stops
- **Area:** `induce/validate.py::Validator.validate`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a catalogue and sample rows
- **Steps:** submit a candidate that fails at each gate in turn
- **Expected:** a `Rejection` naming exactly that gate; `passed` never contains a
  gate after the failure
- **Why:** "in the order that makes each one's failure cheap"

### IND-003 · Prose is rejected at the parse gate
- **Area:** `induce/validate.py::Validator.validate`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** submit "Sure! Here is a control that checks the amount is
  positive."
- **Expected:** `Gate.PARSE`, detail carrying the parser's message
- **Why:** "it is PQL, not prose about PQL"

### IND-004 · A fenced control is unwrapped and nothing else is edited
- **Area:** `induce/validate.py::_strip_fencing`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** a ```` ```pql ```` fence with and without a closing fence; then a
  candidate needing a character changed to parse
- **Expected:** both fences unwrapped and parsed; the third rejected
- **Why:** "rejecting a correct control for its packaging teaches nothing and
  costs a retry"; but "whatever the edit fixed is what the next one will get
  wrong too"

### IND-005 · An invented column is rejected at the type-check gate
- **Area:** `induce/validate.py::Validator.validate`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a catalogue
- **Steps:** a control referencing a column that does not exist
- **Expected:** `Gate.TYPE_CHECK` with the checker's message
- **Why:** the model is told "inventing one makes the control fail on its first
  run", and the gate is what makes that true

### IND-006 · Type-checking is skipped without a catalogue, and the gate still records as passed
- **Area:** `induce/validate.py::Validator.validate`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `catalogue=None`
- **Steps:** validate a control naming any column
- **Expected:** `Gate.TYPE_CHECK` appears in `passed` although nothing was
  checked
- **Why:** the `Validated` type is the guarantee, and a gate recorded as passed
  when it did not run weakens the guarantee silently

### IND-007 · A candidate that cannot be lowered is rejected, not raised
- **Area:** `induce/validate.py::Validator.validate`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a control that type-checks and cannot compile
- **Steps:** validate
- **Expected:** `Gate.COMPILE` rejection; no exception escapes
- **Why:** "a model's output is untrusted input, and untrusted input that breaks
  a compiler is the compiler's ordinary Tuesday"

### IND-008 · A control that flags more than half the sample is rejected
- **Area:** `induce/validate.py::MAXIMUM_VIOLATION_RATE`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** sample rows where a candidate flags 50% and then 51%
- **Steps:** validate
- **Expected:** accepted then rejected at `Gate.SANDBOX`, with the rate in the
  detail
- **Why:** "a control that fails half the data is describing it, not checking
  it"

### IND-009 · With no rows the sandbox rate check is skipped
- **Area:** `induce/validate.py::Validator.validate`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `rows=()`
- **Steps:** validate a sound control
- **Expected:** the rate branch is guarded by `if sample`, so it passes; the
  counterfactual still runs, on probes built from an empty base row
- **Why:** the commonest real case is a dataset with no retained sample, and the
  gate that matters most must still run

### IND-010 · The sandbox is bounded at 2,000 rows
- **Area:** `induce/validate.py::SANDBOX_ROWS`
- **Type:** performance
- **Priority:** P2
- **Precondition:** 10,000 rows
- **Steps:** validate
- **Expected:** `sandbox.scanned <= 2000`
- **Why:** "this runs on every candidate a model produces, and a semantic
  problem visible on ten thousand rows is visible on two thousand"

### IND-011 · A control that cannot fail is rejected
- **Area:** `induce/validate.py::Validator.validate`
- **Type:** security
- **Priority:** P1
- **Precondition:** sample rows
- **Steps:** submit `CHECK t.x IS NOT NULL OR t.x IS NULL`, and
  `CHECK t.qty > -999999999`
- **Expected:** `Gate.COUNTERFACTUAL` for both, detail saying rows were built
  carrying values it should reject and it accepted every one
- **Why:** "it parses, type-checks, compiles, executes, reports a clean pass on
  every row, and is worth precisely nothing. Nothing in gates 1 to 4 can tell it
  from a good control"

### IND-012 · The null probe does not count as a value probe
- **Area:** `induce/validate.py::SandboxResult.is_vacuous`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a control that catches only the null probe
- **Steps:** validate
- **Expected:** `is_vacuous is True`; the rejection detail adds "it does reject a
  missing value, but so does every row predicate in the language"
- **Why:** "PQL inverts SQL's default, so an unknown is a violation, so a missing
  value breaks every row predicate ever written" — counting it would make the
  gate nearly inert

### IND-013 · A nullity assertion is probed by the null, and counted as a value probe
- **Area:** `induce/validate.py::Validator._probes`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `CHECK t.a IS NOT NULL`
- **Steps:** validate; read the sandbox result
- **Expected:** `value_probes == 1`, `value_probes_caught == 1`,
  `is_vacuous is False`
- **Why:** "'0 of 0 value probes' reads as though the control was never really
  tested, and it was"

### IND-014 · Hostile values are chosen per operator
- **Area:** `induce/validate.py::_hostile_values`
- **Type:** functional
- **Priority:** P1
- **Precondition:** one candidate per operator family — `in`, `in_codelist`,
  `matches`, `is_valid`, `between`, each comparison
- **Steps:** read the probes
- **Expected:** a non-member for membership; a non-match and an empty string for
  patterns; one value each side of a numeric bound; a perturbed string for a
  string comparison
- **Why:** "probing `IN ('BUY','SELL')` with another arbitrary string is the only
  way to learn whether the membership test is being applied at all"

### IND-015 · An assertion with no subject produces no probes and is not vacuous
- **Area:** `induce/validate.py::_subject_of`, `SandboxResult.is_vacuous`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a row-count or freshness assertion
- **Steps:** validate
- **Expected:** `value_probes == 0`, so `is_vacuous is False` and the
  counterfactual gate passes without testing anything
- **Why:** the gate the module exists for is silently inapplicable to a whole
  class of assertion, and a model can reach `Validated` through it

### IND-016 · A probe that cannot run is not a probe that was caught
- **Area:** `induce/validate.py::Validator._count_caught`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a probe whose value makes the evaluator raise
- **Steps:** validate
- **Expected:** the exception is swallowed and the probe counts as uncaught
- **Why:** counting it as caught would let a control that crashes on hostile
  input pass the gate that exists to break it

### IND-017 · The retry prompt quotes the rejection precisely
- **Area:** `induce/llm.py::_with_feedback`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a provider that fails then succeeds
- **Steps:** induce; inspect the second prompt
- **Expected:** the gate name, the parser's own message, and the gate's plain
  meaning
- **Why:** "a model given the position generally fixes it, where a model told
  'that was invalid' generally does not"

### IND-018 · Attempts are bounded at three and at least one
- **Area:** `induce/llm.py::DEFAULT_ATTEMPTS`, `Inducer.__init__`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a provider that always fails
- **Steps:** induce with the default, then with `attempts=0`
- **Expected:** three provider calls, then one — `max(1, attempts)`
- **Why:** "each retry is a paid call", and a zero configured attempt count must
  not mean no attempt

### IND-019 · A model declining is not a failure
- **Area:** `induce/llm.py::Inducer.induce`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a provider returning `NONE`, then one returning `ok=False`
- **Steps:** induce
- **Expected:** `None` in both cases, on the first attempt, with no retry
- **Why:** "an ordinary outcome and not an error: every feature that uses this
  has a deterministic path that does not need it"

### IND-020 · A failed induction reports every attempt, not just the last
- **Area:** `induce/llm.py::Inducer.induce_all`; `Rejection.attempts`
- **Type:** regression
- **Priority:** P1
- **Precondition:** three requests, each failing three times at the parse gate
- **Steps:** `induce_all`; read `rejections` and `failures_by_gate()`
- **Expected:** nine rejections, not three
- **Why:** "counting three parse errors as one understates the failure rate in
  the flattering direction, which is the direction it must never be wrong in"

### IND-021 · The failure rate is published and correct
- **Area:** `induce/llm.py::InductionReport.generation_failure_rate`
- **Type:** contract
- **Priority:** P1
- **Precondition:** ten requests, six induced, two declined, two rejected
- **Steps:** read the rate and `describe()`
- **Expected:** 0.4; the sentence separates declined from rejected; zero
  requests yields 0.0 rather than a division by zero
- **Why:** "a prompt whose output fails the gate half the time is a prompt
  somebody should fix, and without the number nobody knows"

### IND-022 · The response records whether the grammar was enforced
- **Area:** `induce/llm.py::Inducer.induce`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a constraining provider and a non-constraining one
- **Steps:** induce with each; read the provenance observations
- **Expected:** "with the grammar enforced during decoding" against "validated
  afterwards; the provider cannot constrain decoding"
- **Why:** "a grammar-constrained provider emitting unparseable PQL is a
  provider bug worth reporting, and an unconstrained one doing so is Tuesday"

### IND-023 · Retrieval carries the interpretation, not just the schema
- **Area:** `induce/llm.py::retrieve`, `Retrieved.render`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a declaration with a purpose, a grain and an attribute with
  a definition and an interpretation
- **Steps:** render the retrieval
- **Expected:** all of them present, with "How to read it:" carrying the
  interpretation
- **Why:** "'positions are reported gross of collateral' is the sentence that
  decides whether a sign control is right or backwards, and it exists in no
  schema"

### IND-024 · Values are passed in, never read here
- **Area:** `induce/llm.py::retrieve`
- **Type:** security
- **Priority:** P1
- **Precondition:** a declaration with a PII attribute
- **Steps:** call `retrieve` with no examples; inspect the rendered prompt
- **Expected:** no values; the examples are the caller's decision, and the
  sensitivity travels on the `Request`
- **Why:** "whether a value may leave the building is a residency decision and
  this module is the wrong place to make it"

### IND-025 · Existing rules are listed so the model does not repeat them
- **Area:** `induce/llm.py::Retrieved.render`
- **Type:** functional
- **Priority:** P2
- **Precondition:** three controls already in force
- **Steps:** render
- **Expected:** a "do not repeat these" block listing all three
- **Why:** a duplicate proposal costs a reviewer the same as a wrong one

### IND-026 · An induced control's provenance is checkable
- **Area:** `induce/llm.py::Inducer.induce`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a successful induction
- **Steps:** read the provenance
- **Expected:** origin `INDUCTION`, `source_ref` carrying the request
  fingerprint, and observations naming the provider, the model, the gates passed
  and the probes caught
- **Why:** origin `INDUCTION` is the weakest authority (PRP-014), so the
  observations are what a reviewer has instead of trust

### IND-027 · A document rule is rejected when its quote is not in the document
- **Area:** `induce/documents.py::DocumentInducer.extract`
- **Type:** security
- **Priority:** P1
- **Precondition:** a document and a model that returns a plausible paraphrase
- **Steps:** extract
- **Expected:** the rule is discarded and counted in `fabricated_quotes`; no
  `Extracted` produced
- **Why:** "a rule invented wholesale cannot produce a quote that is really
  there" — the check that turns the citation from decoration into a test

### IND-028 · A reflowed quote still matches
- **Area:** `induce/documents.py::Document.contains`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a passage wrapped across lines
- **Steps:** quote it with different whitespace, then with one word changed
- **Expected:** matched, then not
- **Why:** "a model that reflows a sentence across lines has still quoted it; one
  that changes a word has not, and that difference is the whole check"

### IND-029 · The fabrication rate is published
- **Area:** `induce/documents.py::ExtractionReport.fabrication_rate`
- **Type:** contract
- **Priority:** P1
- **Precondition:** ten normative passages, two fabricated quotes
- **Steps:** read the rate and `describe()`
- **Expected:** 0.2, and a sentence naming it; zero considered yields 0.0
- **Why:** "the number that matters, and the one nobody publishes"

### IND-030 · Only normative passages are sent to the model
- **Area:** `induce/documents.py::Passage.looks_normative`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a document with descriptive and obligation-bearing
  paragraphs
- **Steps:** extract; count provider calls
- **Expected:** one call per normative passage only; `considered` matches
- **Why:** "the cost of passing a descriptive passage to the model is one call,
  and the cost of filtering out a normative one is a rule nobody ever finds"

### IND-031 · Short passages are skipped
- **Area:** `induce/documents.py::MINIMUM_PASSAGE`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a heading of 39 characters containing "must", and one of 40
- **Steps:** read `passages()`
- **Expected:** only the second is yielded; the paragraph index still advances
  for both
- **Why:** "a heading is not an instruction" — and the locator numbering must not
  shift when a short block is skipped

### IND-032 · A locator points at something a reader can find
- **Area:** `induce/documents.py::Document._locate`
- **Type:** functional
- **Priority:** P2
- **Precondition:** passages beginning "Schedule H.1", "Field 23", "3.2.1", and
  one with no heading
- **Steps:** read the locators
- **Expected:** the first three quoted verbatim; the last "paragraph N"
- **Why:** "'Schedule H.1, field 23' sends somebody to the right page;
  'paragraph 41' sends them to a scroll bar" — and an earlier pattern without
  `field` and `item` "sent every citation in a filing manual to 'paragraph 3'"

### IND-033 · An answer carrying only one of quote and control is rejected
- **Area:** `induce/documents.py::_split`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a model returning a control with no `QUOTE:` line
- **Steps:** extract
- **Expected:** a `Gate.PARSE` rejection saying there is nothing to check the
  rule against
- **Why:** the citation is the test; a rule with no quote is unfalsifiable and
  must not reach a reviewer

### IND-034 · A quote is stripped of surrounding quotation marks
- **Area:** `induce/documents.py::_split`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a model returning a curly-quoted passage
- **Steps:** extract
- **Expected:** the marks stripped before the containment check
- **Why:** a correct quote rejected for its punctuation costs a rule and teaches
  nothing

### IND-035 · The document is hashed as read
- **Area:** `induce/documents.py::Document.content_hash`; `stale_citations`
- **Type:** functional
- **Priority:** P1
- **Precondition:** rules extracted from a document, then the document edited
- **Steps:** `stale_citations(extracted, new_document)`
- **Expected:** the rules from that document returned; rules citing a different
  document are not
- **Why:** "a rule whose source has changed underneath it is not necessarily
  wrong, but it is no longer supported by what the citation points at … somebody
  reads the new passage rather than deleting the rule"

### IND-036 · Too few labels refuse to generalise
- **Area:** `induce/examples.py::MINIMUM_LABELS`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** five labels, then six
- **Steps:** generalise
- **Expected:** a refusal naming the count and the minimum, then a real attempt
- **Why:** "below this many labels, anything found is a description of the
  labels"

### IND-037 · All-good labels refuse, and say what to do
- **Area:** `induce/examples.py::ExampleInducer.generalise`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** ten labels, all `good`
- **Steps:** generalise
- **Expected:** a refusal: "there is nothing for a rule to separate. Mark a
  value you consider wrong"
- **Why:** a rule induced from approval alone accepts everything

### IND-038 · One false alarm eliminates a candidate outright
- **Area:** `induce/examples.py::Scored.is_admissible`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a candidate catching nine of ten bad values and flagging one
  good one
- **Steps:** score
- **Expected:** inadmissible
- **Why:** "with twenty labels, one false alarm is five percent, and a control
  that flags five percent of good data is the one that gets the suite switched
  off"

### IND-039 · A candidate that catches nothing is inadmissible
- **Area:** `induce/examples.py::Scored.is_admissible`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a candidate that accepts every labelled value
- **Steps:** score
- **Expected:** inadmissible — `caught > 0` is required
- **Why:** the counterfactual again: a rule that flags nothing is perfectly
  precise and worth nothing

### IND-040 · Memorisation is refused unless a value repeats
- **Area:** `induce/examples.py::ExampleInducer._candidates`
- **Type:** regression
- **Priority:** P1
- **Precondition:** five distinct good LEIs, each seen once; then BUY and SELL
  seen five times each
- **Steps:** generalise
- **Expected:** no `IN (...)` candidate in the first; one in the second
- **Why:** "`IN ('5493001…', …)` has perfect recall on the labels and rejects
  every valid LEI in the world that is not one of those five. It is memorisation
  with a perfect score"

### IND-041 · The membership candidate is bounded at twelve values
- **Area:** `induce/examples.py::ExampleInducer._candidates`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** twelve repeated distinct good values, then thirteen
- **Steps:** generalise
- **Expected:** a candidate in the first, none in the second; and none when
  there is only one distinct value
- **Why:** a thirteen-value enumeration is a code list nobody declared, and a
  one-value one is a constant

### IND-042 · A validator candidate treats null as acceptable
- **Area:** `induce/examples.py::_validator_accepts`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** labels including a `None` marked bad
- **Steps:** generalise
- **Expected:** every `IS VALID` candidate *misses* the null — only
  `IS NOT NULL` catches it
- **Why:** the separation of concerns is deliberate, and the resulting
  generalisation proposes a completeness rule rather than a format one

### IND-043 · Length and range candidates are built from the good values only
- **Area:** `induce/examples.py::ExampleInducer._candidates`
- **Type:** functional
- **Priority:** P2
- **Precondition:** good values 10–100, bad values 5 and 500
- **Steps:** generalise
- **Expected:** `BETWEEN 10 AND 100` and `>= 10` candidates, both admissible,
  the first with higher recall
- **Why:** building the bound from all values would produce a range that accepts
  the values the steward rejected

### IND-044 · The best candidate is the highest recall, then the shortest
- **Area:** `induce/examples.py::Generalisation.best`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two admissible candidates with equal recall and different
  predicate lengths
- **Steps:** read `best`
- **Expected:** the shorter predicate
- **Why:** a tie broken on length prefers the general rule to the enumerated
  one, which is the same instinct as IND-040

### IND-045 · The next question is the value the survivors most disagree about
- **Area:** `induce/examples.py::ExampleInducer._next_question`
- **Type:** functional
- **Priority:** P1
- **Precondition:** four admissible candidates and unlabelled values on which
  they split 4-0, 3-1 and 2-2
- **Steps:** read `next_question`
- **Expected:** the 2-2 value, disagreement 1.0, with a reason saying the answer
  eliminates about half of them
- **Why:** "the difference between twenty labels and two hundred"

### IND-046 · No question is asked when there is nothing to learn
- **Area:** `induce/examples.py::ExampleInducer._next_question`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** one admissible candidate; then several but no unlabelled
  values; then unanimous survivors
- **Steps:** read `next_question`
- **Expected:** `None` in all three; `is_settled` true when a best exists and no
  question remains
- **Why:** "a value they all agree about teaches nothing, whichever way the
  steward answers"

### IND-047 · When nothing separates the labels, the refusal suggests why
- **Area:** `induce/examples.py::ExampleInducer.generalise`
- **Type:** functional
- **Priority:** P2
- **Precondition:** labels where the bad values are indistinguishable from the
  good ones by any candidate
- **Steps:** generalise
- **Expected:** `scored` non-empty, `best is None`, and a refusal saying the
  distinction "may depend on another column"
- **Why:** the honest answer to an unlearnable labelling, and the one that sends
  the steward somewhere useful

### IND-048 · A generalisation's provenance quotes the label counts
- **Area:** `induce/examples.py::generalisation_provenance`
- **Type:** contract
- **Priority:** P2
- **Precondition:** twenty labels, six bad, a candidate catching four
- **Steps:** read the provenance
- **Expected:** origin `EXAMPLE`; observations naming both counts and stating
  that it flags none of the accepted values
- **Why:** the reviewer is being asked to trust a rule induced from twenty
  judgements, and the counts are the whole basis

---

## `mine/` — what the data obeys, offered as candidates

Finding **T9**: an acceptance test asserted `findings.dependencies or
findings.discarded` and passed entirely on the second disjunct — mining found
**0 dependencies and discarded 2**, and the loop body that checked the result
never executed. Every case below says what "it worked" means in numbers.

### MIN-001 · A sample below 200 rows mines nothing, and says so
- **Area:** `mine/sample.py::MINIMUM_ROWS`; every miner's `mine`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** samples of 199 and 200 rows
- **Steps:** run the key, dependency and constraint miners on each
- **Expected:** at 199, empty findings with a `skipped` entry naming the row
  count; at 200, a real search
- **Why:** "a constraint that holds across two hundred rows holds across two
  hundred rows" — and the skip must be visible, not silent

### MIN-002 · Every mined finding carries the sample's caveats
- **Area:** `mine/sample.py::Sample.caveats`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a 500-row sample of a 4,000,000-row partitioned table,
  spanning one partition
- **Steps:** mine keys, dependencies and invariants
- **Expected:** every `Evidence.caveats` carries all three notes — one
  partition, 0.0% coverage, small sample
- **Why:** "assembled here rather than at each miner, so a new miner cannot ship
  without them. Every one of these has been the reason a mined constraint was
  wrong in production"

### MIN-003 · Caveats are computed from the sample, not written as boilerplate
- **Area:** `mine/sample.py::Sample.caveats`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a full scan of a 5,000-row table with several partitions
- **Steps:** read the caveats
- **Expected:** none — coverage is 1.0, more than one partition is seen, the
  sample is over 1,000 rows
- **Why:** the counterfactual to MIN-002; a caveat attached unconditionally
  tells a reviewer nothing and is ignored within a week

### MIN-004 · One partition is the classic false key, and is named as such
- **Area:** `mine/sample.py::Sample.spans_one_partition`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a sample with `partition_column="business_date"` and one
  distinct value
- **Steps:** mine a key
- **Expected:** the caveat says anything found holds *within* one business_date
  and may not hold across them
- **Why:** "`(account_id)` is perfectly unique within Monday and is not the key;
  `(account_id, business_date)` is"

### MIN-005 · An undeclared partition column produces no partition caveat
- **Area:** `mine/sample.py::Sample.partitions_seen`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a single-day sample with `partition_column=""`
- **Steps:** read the caveats
- **Expected:** `partitions_seen == 0`, `spans_one_partition is False`, no
  partition caveat — the danger is real and unreportable
- **Why:** the most dangerous sample produces the fewest warnings, because
  nobody declared what it is partitioned by

### MIN-006 · An unknown table size is stated rather than assumed
- **Area:** `mine/sample.py::Sample.coverage`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `total_rows=None`
- **Steps:** read `coverage`, `is_representative`, the caveats
- **Expected:** `None`, `False`, and a caveat saying the fraction cannot be
  stated
- **Why:** "without it a miner cannot tell a full read from a 1% sample, and the
  two support very different claims"

### MIN-007 · Representative means at least 90% of the table
- **Area:** `mine/sample.py::REPRESENTATIVE_FRACTION`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** coverage of 0.89, 0.90 and 1.20 (a stale row count)
- **Steps:** read `is_representative` and `coverage`
- **Expected:** false, true, true with coverage clamped at 1.0
- **Why:** a stale `total_rows` must not produce a coverage above one in a
  report

### MIN-008 · Evidence separates nulls from violations
- **Area:** `mine/sample.py::Evidence`
- **Type:** contract
- **Priority:** P1
- **Precondition:** 1,000 rows, 900 supporting, 0 violating, 100 null-excluded
- **Steps:** read `support`, `null_fraction`, `is_exact`, `describe()`
- **Expected:** support over the *applicable* rows, not all rows; the sentence
  names the excluded count and its percentage
- **Why:** "SQL's aggregate functions silently skip them, and a 'unique' column
  that is ninety percent null is not a key — it is an empty column with a few
  values in it"

### MIN-009 · Evidence with no applicable rows does not divide by zero
- **Area:** `mine/sample.py::Evidence.support`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `rows_examined == null_excluded`
- **Steps:** read `support`
- **Expected:** 0.0
- **Why:** it is read by every `describe()` and every provenance sentence

### MIN-010 · A key mined across a whole table is proposed with its evidence
- **Area:** `mine/keys.py::KeyMiner.mine`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 1,000 rows where `(trade_id)` is unique and never null
- **Steps:** mine
- **Expected:** exactly one candidate; `columns == ("trade_id",)`;
  `is_exact is True`; evidence naming 1,000 rows examined and 1,000 distinct
- **Why:** the positive control — "a mining acceptance test once passed while
  mining found nothing"; this case states the number

### MIN-011 · Supersets of a key are not proposed
- **Area:** `mine/keys.py::KeyMiner.mine`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `(trade_id)` unique, five other eligible columns
- **Steps:** mine at `max_arity=3`
- **Expected:** one candidate, not twenty-one — "if `account_id` is unique then
  so is every pair containing it"
- **Why:** "proposing all of them buries the one that matters"

### MIN-012 · A mostly-null column cannot be part of a key
- **Area:** `mine/keys.py::MAXIMUM_NULL_FRACTION`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a column with four distinct values and 996 nulls
- **Steps:** mine
- **Expected:** the column is in `excluded` with its null percentage and the
  sentence about looking unique to any test that skips nulls; no candidate
- **Why:** "that has fooled every profiler that did not check"

### MIN-013 · The null threshold is 5%
- **Area:** `mine/keys.py::MAXIMUM_NULL_FRACTION`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** columns at exactly 5% and 5.1% null, both otherwise unique
- **Steps:** mine
- **Expected:** the first eligible, the second excluded
- **Why:** the comparison is `>`, and a key column with a handful of nulls is a
  key with a data problem

### MIN-014 · A continuous numeric column is excluded with a reason
- **Area:** `mine/keys.py::_is_continuous`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a float `market_value` column, unique by accident
- **Steps:** mine
- **Expected:** excluded, with "its values are distinct because they are
  measurements, not because they identify a row"
- **Why:** "proposing a market value as a candidate key is the kind of finding
  that makes people stop reading them"

### MIN-015 · An integer identifier column is not excluded as continuous
- **Area:** `mine/keys.py::_is_continuous`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an integer account number column
- **Steps:** mine
- **Expected:** eligible — the test requires *all* populated values to be floats
- **Why:** the counterfactual; excluding integers would exclude most real keys

### MIN-016 · A near-unique column is an approximate key, not a non-key
- **Area:** `mine/keys.py::APPROXIMATE_THRESHOLD`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 10,000 rows with 3 duplicates (0.9997), then with 20
  (0.998)
- **Steps:** mine
- **Expected:** the first is a candidate with `approximate is True` and a
  description saying "which is what a key with a duplicate problem looks like,
  not what a non-key looks like"; the second is not proposed
- **Why:** "a column that is 99.99% unique is usually a key with a data problem
  rather than a non-key" — and the finding is the duplicates

### MIN-017 · A surrogate key is ranked last, not excluded
- **Area:** `mine/keys.py::KeyFindings.best`, `_is_surrogate`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a dense integer `row_id` and a business key
  `(account_id, business_date)`
- **Steps:** mine; read `best` and `business_key_found`
- **Expected:** the business key is `best` although it is wider;
  `business_key_found is True`
- **Why:** "'one row per row_id' answers 'what does one row represent?' with 'a
  row', and offering it as the answer is worse than offering nothing, because it
  looks like one"

### MIN-018 · A table whose only key is a surrogate says its grain was not found
- **Area:** `mine/keys.py::KeyFindings.business_key_found`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** only a UUID column is unique
- **Steps:** read `best` and `business_key_found`
- **Expected:** `best` is the surrogate, `business_key_found is False`
- **Why:** the report has to be able to say "nothing here answers what a row is"

### MIN-019 · Surrogate detection needs a shape, not just a name
- **Area:** `mine/keys.py::_is_surrogate`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `instrument_id` holding ISINs; `ref` holding 1..n;
  `trade_id` holding fixed-width digits; `trade_id` holding variable-width
  digits; a UUID column called `counterparty`
- **Steps:** mine
- **Expected:** not a surrogate; a surrogate; a surrogate; not a surrogate; a
  surrogate
- **Why:** "a column called `id` holding ISINs is not a surrogate, and a column
  called `ref` holding 1..n is"

### MIN-020 · Dense integers are surrogates and sparse ones are not
- **Area:** `mine/keys.py::_is_surrogate`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** values 1..1000; then 1000 account numbers drawn from a range
  of 100,000
- **Steps:** mine
- **Expected:** the first is a surrogate (density > 0.9), the second is not
- **Why:** "a sequence does; an account number drawn from a wider space does
  not"

### MIN-021 · What was not searched is reported
- **Area:** `mine/keys.py::KeyFindings.skipped`
- **Type:** contract
- **Priority:** P1
- **Precondition:** eight eligible columns at `max_arity=3`
- **Steps:** mine
- **Expected:** a `skipped` note naming the arity ceiling and the eligible count
- **Why:** "a report that says 'found two keys' while having skipped every
  three-column combination reads as completeness and is not"

### MIN-022 · A mined key's provenance is re-runnable
- **Area:** `mine/keys.py::as_provenance`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a candidate over a partitioned sample
- **Steps:** read the provenance
- **Expected:** origin `MINING`; an observation stating the columns, the row
  count and the duplicates; every sample caveat appended
- **Why:** "'unique across 4.2m rows spanning 90 days' is checkable, where
  'confidence 0.97' is not"

### MIN-023 · A mined key is never auto-activated
- **Area:** `mine/keys.py::as_provenance` → `propose.queue`
- **Type:** security
- **Priority:** P1
- **Precondition:** a perfect exact key over a full scan
- **Steps:** adapt it into the queue; read `auto_activatable`
- **Expected:** absent — origin `MINING` may not auto-activate
- **Why:** "a miner cannot distinguish 'this is the key' from 'nothing has
  happened yet that would break it', and pretending otherwise turns the first
  legitimate duplicate into an incident"

### MIN-024 · A key candidate's identity is stable across runs
- **Area:** `mine/keys.py::key_identity`
- **Type:** contract
- **Priority:** P2
- **Precondition:** the same key mined from two different samples
- **Steps:** compare identities
- **Expected:** equal — the key is dataset, rule and column list
- **Why:** a re-mined key must land on the existing proposal or on its
  suppression, not appear as new every night

### MIN-025 · A real functional dependency is found, with its number
- **Area:** `mine/dependencies.py::DependencyMiner.mine`
- **Type:** regression
- **Priority:** P1
- **Precondition:** 1,000 rows where each `counterparty_lei` has exactly one
  `rating`, over 50 distinct counterparties
- **Steps:** mine
- **Expected:** at least one dependency; `counterparty_lei -> rating` among
  them; `is_exact is True`; support 1.0
- **Why:** finding T9 — the acceptance test must assert the dependency it
  expects, not `dependencies or discarded`

### MIN-026 · The counterfactual corpus yields nothing
- **Area:** `mine/dependencies.py::DependencyMiner.mine`
- **Type:** regression
- **Priority:** P1
- **Precondition:** the same table with `rating` drawn at random
- **Steps:** mine
- **Expected:** no dependency involving `rating`; `discarded` non-empty
- **Why:** "the old corpus is kept as the counterfactual: a miner reporting a
  rule *there* would be inventing them"

### MIN-027 · A key determines everything, and none of it is reported
- **Area:** `mine/dependencies.py::NEAR_KEY_FRACTION`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a table with a unique `trade_id` and eight other columns
- **Steps:** mine
- **Expected:** no dependency with `trade_id` as determinant;
  `discarded["near_key_determinant"]` counts them
- **Why:** "a miner without this filter reports one dependency per column and
  none of them is a rule — they are a restatement of the key"

### MIN-028 · The near-key threshold is 90% distinct
- **Area:** `mine/dependencies.py::DependencyMiner._is_near_key`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** determinants at 89% and 90% distinct over 1,000 rows
- **Steps:** mine
- **Expected:** the first searched, the second discarded
- **Why:** "a determinant with 4.19m distinct values in 4.2m rows determines
  every column to within 0.2% — support that reads as overwhelming evidence and
  is entirely an artefact of the cardinality. It would be true of a column of
  random numbers"

### MIN-029 · A constant column is dropped before the search
- **Area:** `mine/dependencies.py::DependencyMiner._useful_columns`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `record_type` is `'P'` on every row
- **Steps:** mine
- **Expected:** no dependency naming it on either side;
  `discarded["constant_column"]` incremented
- **Why:** "a constant is determined by everything. Same arithmetic, same
  worthlessness"

### MIN-030 · A dependency implied by a narrower one is not reported
- **Area:** `mine/dependencies.py::DependencyMiner.mine`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `a -> c` holds, and `b` is another eligible column
- **Steps:** mine at `max_determinant=2`
- **Expected:** `(a, b) -> c` not reported; `discarded["implied"]` counts it
- **Why:** "if a → c holds then (a, b) → c holds for free, and reporting both
  buries the one that says something"

### MIN-031 · Rows with a null on either side are excluded, not counted as agreeing
- **Area:** `mine/dependencies.py::DependencyMiner._evaluate`
- **Type:** regression
- **Priority:** P1
- **Precondition:** 1,000 rows where `rating` is null in 600
- **Steps:** mine
- **Expected:** `null_excluded == 600`; support computed over 400; the evidence
  sentence says so
- **Why:** "counting such rows as agreeing is how a column that is mostly null
  gets reported as perfectly determined"

### MIN-032 · Support below 95% is not a dependency
- **Area:** `mine/dependencies.py::MINIMUM_SUPPORT`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** dependencies holding on 94% and 96% of rows
- **Steps:** mine
- **Expected:** only the second reported, `is_exact is False`, the description
  naming the exceptions
- **Why:** "an approximate dependency below this support is not a dependency
  with exceptions; it is a pattern that does not hold"

### MIN-033 · The g3 measure counts rows to remove, not groups
- **Area:** `mine/dependencies.py::DependencyMiner._evaluate`
- **Type:** functional
- **Priority:** P1
- **Precondition:** one determinant value with 90 rows of `A` and 10 of `B`
- **Steps:** mine
- **Expected:** 90 agreeing and 10 violating — the majority value per group
  survives
- **Why:** a measure that counted the whole group as violating would reject
  every real dependency with a handful of bad rows, which is the finding worth
  having

### MIN-034 · A conditional dependency true globally is not re-reported
- **Area:** `mine/dependencies.py::DependencyMiner._conditional`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `instrument -> issuer` holds globally, and a twelve-valued
  `status` column is passed as a condition
- **Steps:** mine with conditions
- **Expected:** no conditional copies; `discarded["conditional_restates_global"]`
  counts them
- **Why:** "a table with a twelve-valued status column produces twelve copies of
  every real finding. The conditional ones worth a reviewer's time are exactly
  the ones that are *false globally*"

### MIN-035 · A conditional dependency false globally is reported
- **Area:** `mine/dependencies.py::DependencyMiner._conditional`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `product -> settlement_days` holds within `region = 'US'`
  and not overall, over at least 50 US rows and 5% of the sample
- **Steps:** mine with `conditions=("region",)`
- **Expected:** one conditional dependency, exact, rendering as
  `product -> settlement_days WHERE region = 'US'`
- **Why:** the discovery the filter exists to preserve

### MIN-036 · A condition covering too few rows is discarded
- **Area:** `mine/dependencies.py::MINIMUM_CONDITION_COVERAGE`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a condition value covering 49 rows, then 50 but 4% of the
  sample, then 50 and 6%
- **Steps:** mine
- **Expected:** discarded, discarded, searched — both guards apply
- **Why:** "'the rule holds for the eleven rows where country = AD' is a
  description of eleven rows"

### MIN-037 · Conditional completeness is mined as its own shape
- **Area:** `mine/dependencies.py::DependencyMiner._conditional_completeness`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `state` populated on every US row and null on some others
- **Steps:** mine with `conditions=("country",)`
- **Expected:** a `Dependency` with `is_completeness is True`, rendering as
  `state IS NOT NULL WHERE country = 'US'` and describing itself as mandatory
  under that condition
- **Why:** "the alternative a global miner offers is `state IS NOT NULL`, which
  fails on every non-US row and gets switched off"

### MIN-038 · A column mandatory everywhere is not narrowed to a condition
- **Area:** `mine/dependencies.py::DependencyMiner._conditional_completeness`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a column with no nulls at all
- **Steps:** mine with conditions
- **Expected:** no conditional completeness finding
- **Why:** "dressing it as a conditional one narrows a true rule for no reason"

### MIN-039 · A conditional completeness finding proposes a declaration Γ can use
- **Area:** `mine/dependencies.py::Dependency.is_completeness` → `derive`
- **Type:** contract
- **Priority:** P2
- **Precondition:** the finding from MIN-037
- **Steps:** follow it to a conditional optionality declaration and generate
- **Expected:** an `attribute.completeness` control with
  `WHERE country = 'US'` (DER-044)
- **Why:** "it is worth mining because it lands somewhere specific" — the claim
  needs an end-to-end case, not a miner-only one

### MIN-040 · An inclusion dependency is a foreign key nobody declared
- **Area:** `mine/dependencies.py::InclusionMiner.mine`
- **Type:** functional
- **Priority:** P1
- **Precondition:** every `counterparty_id` in trades exists in a
  near-unique `parties.id`
- **Steps:** mine
- **Expected:** one `Inclusion`, exact, describing itself as a foreign key
  nobody declared
- **Why:** `FR-PRF-008`, and the input to a proposed `REFERENCES` relationship

### MIN-041 · A partial inclusion is the interesting one
- **Area:** `mine/dependencies.py::InclusionMiner.mine`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 97% containment with three distinct orphan values
- **Steps:** mine
- **Expected:** an `Inclusion` with `is_exact is False`, up to five orphan
  examples, and a description ending "this is a foreign key with a live defect
  in it, not a coincidence"
- **Why:** "that is a live defect somebody wants to know about today"

### MIN-042 · Containment below 90% is coincidence
- **Area:** `mine/dependencies.py::InclusionMiner.__init__`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** containment at 89% and 90%
- **Steps:** mine
- **Expected:** nothing, then a finding
- **Why:** "two columns of country codes overlap heavily without one referencing
  the other"

### MIN-043 · A reference target must be near-unique
- **Area:** `mine/dependencies.py::InclusionMiner._is_key`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a right-hand `status` column with three distinct values over
  200 rows
- **Steps:** mine
- **Expected:** no inclusion; `discarded["target_is_not_a_key"]` counts it
- **Why:** "every column in the world is 'contained' in it"

### MIN-044 · A foreign key with orphans is not rejected for having more distinct values
- **Area:** `mine/dependencies.py::InclusionMiner._is_key`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a left column with 103 distinct values, 100 of them in a
  unique right column
- **Steps:** mine
- **Expected:** the partial inclusion is reported
- **Why:** "an earlier version compared distinct counts instead … and that
  destroyed the finding this miner exists for: a foreign key *with orphans* has
  more distinct values on the left, because the orphans are exactly the extra
  ones"

### MIN-045 · The target's near-uniqueness threshold is 99%
- **Area:** `mine/dependencies.py::InclusionMiner._is_key`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a dimension table with 3 duplicate rows in 1,000
- **Steps:** mine
- **Expected:** still a valid target — "refusing to notice the foreign key
  because of them would hide two findings instead of one"
- **Why:** the duplicate rows are themselves a finding, reported by the key
  miner

### MIN-046 · An ordering invariant is found with counterexamples
- **Area:** `mine/constraints.py::ConstraintMiner._orderings`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 1,000 rows where `trade_date <= settlement_date` on 985
- **Steps:** mine
- **Expected:** one ordering invariant, support 0.985, up to three
  counterexample rows carrying only the involved columns
- **Why:** "three concrete wrong rows beat any statistic"

### MIN-047 · An arithmetic identity is tested with a tolerance, never exactly
- **Area:** `mine/constraints.py::IDENTITY_TOLERANCE`
- **Type:** regression
- **Priority:** P1
- **Precondition:** `quantity * price = notional` computed in floating point, so
  no row is bit-exact
- **Steps:** mine
- **Expected:** the identity is found
- **Why:** "an identity miner testing exact equality finds nothing at all and
  reports a clean table with no invariants in it — which is the most misleading
  possible output, because it looks like a thorough search"

### MIN-048 · The identity tolerance is relative to the magnitude
- **Area:** `mine/constraints.py::_identity`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** values of order 1e9 differing in the twelfth significant
  digit; and values of order 1e-6 differing by 1e-7
- **Steps:** mine
- **Expected:** the first holds, the second does not — the scale is
  `max(|computed|, |target|, 1.0)`
- **Why:** an absolute tolerance would accept a real difference on large numbers
  and reject a rounding one on small

### MIN-049 · One relationship is not reported three ways
- **Area:** `mine/constraints.py::ConstraintMiner._identities`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `fees + net = notional` holding exactly
- **Steps:** mine
- **Expected:** one invariant, the `+` form; `discarded["algebraic_restatement"]`
  counts the `-` restatements; `discarded["commutative_duplicate"]` counts
  `net + fees`
- **Why:** "a reviewer reading the second one has to work out that it is the
  first before they can dismiss it"

### MIN-050 · An ordering entailed by an identity is dropped
- **Area:** `mine/constraints.py::ConstraintMiner._not_implied`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `fees + net = notional` with both parts non-negative
- **Steps:** mine
- **Expected:** `net <= notional` and `fees <= notional` discarded with
  `discarded["implied_by_identity"]`; `fees <= net` kept
- **Why:** "reporting the consequence next to the premise gives a reviewer three
  findings where there is one fact, and the two weak ones make the strong one
  harder to see"

### MIN-051 · The entailment floor differs for additive and multiplicative identities
- **Area:** `mine/constraints.py::ConstraintMiner._not_implied`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `price * quantity = notional` with a quantity below 1
- **Steps:** mine
- **Expected:** the ordering is **not** dropped — the multiplicative floor is
  1.0, not 0.0
- **Why:** a factor below one shrinks rather than grows, so the entailment does
  not hold and dropping the ordering would lose a real check

### MIN-052 · Disjoint ranges produce no ordering
- **Area:** `mine/constraints.py::ConstraintMiner._disjoint_ranges`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `fees` in 0..100 and `quantity` in 10,000..1,000,000
- **Steps:** mine
- **Expected:** no `fees <= quantity` invariant;
  `discarded["disjoint_ranges"]` counts it
- **Why:** "that is a fact about units, not a rule about the business, and a
  control built on it can only fail if somebody changes the scale of a column"

### MIN-053 · A strict ordering suppresses its weaker form
- **Area:** `mine/constraints.py::ConstraintMiner._orderings`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `valid_from < valid_to` holding on every row
- **Steps:** mine
- **Expected:** one invariant, the strict one; `discarded["weaker_ordering"]`
  counts `<=`
- **Why:** "the strict one is already the stronger claim and is found first" —
  which depends on the operator loop order

### MIN-054 · Columns of different families are not compared
- **Area:** `mine/constraints.py::ConstraintMiner._same_family`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a numeric quantity and a date string
- **Steps:** mine
- **Expected:** no invariant between them
- **Why:** "comparing a quantity to a date raises in Python and would compare
  lexically in some engines, which is worse — it produces an invariant that
  holds on the sample and means nothing"

### MIN-055 · A predicate that raises abandons the candidate rather than the run
- **Area:** `mine/constraints.py::ConstraintMiner._test`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** mixed types in one column so the comparison raises
- **Steps:** mine
- **Expected:** that candidate returns `None`; the rest of the search completes
- **Why:** one unmineable column pair must not empty the findings for a table

### MIN-056 · Fewer than fifty applicable rows is not an invariant
- **Area:** `mine/constraints.py::MINIMUM_APPLICABLE`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a 300-row sample where only 49 rows have both columns
  populated
- **Steps:** mine
- **Expected:** nothing; and the sparse column is counted in
  `discarded["too_sparse"]`
- **Why:** "a comparison that holds on every row because one side is always null
  … is not an invariant"

### MIN-057 · Invariant support below 97% is not reported
- **Area:** `mine/constraints.py::MINIMUM_SUPPORT`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** orderings at 96% and 98%
- **Steps:** mine
- **Expected:** only the second
- **Why:** "set lower than the dependency threshold on purpose: an ordering that
  holds on 97% of rows is a real rule and a real backlog of 3% bad rows"

### MIN-058 · The identity search is capped and the cap is reported
- **Area:** `mine/constraints.py::ConstraintMiner.mine`
- **Type:** contract
- **Priority:** P2
- **Precondition:** twelve numeric columns
- **Steps:** mine
- **Expected:** identities searched over the first eight; a `skipped` note
  naming the count and the cubic cost
- **Why:** the same rule as MIN-021 — a search that silently stopped early reads
  as a complete one

### MIN-059 · Every mined finding's provenance carries the observation and the caveats
- **Area:** `mine/constraints.py::invariant_provenance`;
  `dependency_provenance`; `inclusion_provenance`
- **Type:** contract
- **Priority:** P1
- **Precondition:** one finding of each kind over a caveated sample
- **Steps:** read each provenance
- **Expected:** origin `MINING`; a rule name of the form `mine.<kind>`; the
  evidence sentence first; counterexample rows second for an invariant; every
  sample caveat after
- **Why:** the reviewer's only basis for a mined proposal, and the ordering is
  what they read first

### MIN-060 · Mined identities are stable and distinct
- **Area:** `mine/dependencies.py::dependency_identity`, `inclusion_identity`;
  `mine/constraints.py::invariant_identity`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a dependency and its conditional variant; two inclusions
  from one column to two targets
- **Steps:** compare identities
- **Expected:** all distinct; the conditional variant's key includes the
  condition
- **Why:** a collision would let a conditional finding suppress the global one
  it was meant to complement

---

## `er/match.py` — deciding whether two records are one thing

### ER-001 · Agreement weight is the log-ratio, and it has units
- **Area:** `er/match.py::Comparison.agreement_weight`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `Comparison(m=0.9, u=0.1)` and `Comparison(m=0.9, u=0.001)`
- **Steps:** read the weights
- **Expected:** about +3.17 and +9.8 bits
- **Why:** "a matching surname is weak evidence in a population of Smiths and
  strong evidence in a population of Nakagawas, and the arithmetic says so on
  its own rather than needing somebody to notice"

### ER-002 · Disagreement weight is negative and separately derived
- **Area:** `er/match.py::Comparison.disagreement_weight`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `m=0.9, u=0.1`
- **Steps:** read it
- **Expected:** about -3.17; a field with `m=0.5, u=0.5` weighs zero both ways
- **Why:** a disagreement on a reliable field is strong evidence *against*, and
  a model that only rewards agreement cannot express it

### ER-003 · Probabilities are clamped away from zero and one
- **Area:** `er/match.py::_clamp`, `EPSILON`
- **Type:** regression
- **Priority:** P1
- **Precondition:** `Comparison(m=1.0, u=0.0)`
- **Steps:** read both weights
- **Expected:** finite — no `inf`, no `ZeroDivisionError`
- **Why:** "a field that agreed on every training pair produces an infinite
  weight and one disagreement outvotes every other piece of evidence forever"

### ER-004 · A missing value contributes nothing, not disagreement
- **Area:** `er/match.py::Comparison.weigh`
- **Type:** regression
- **Priority:** P1
- **Precondition:** two records, one with an empty `lei`
- **Steps:** weigh
- **Expected:** `None`, and the field listed in `uninformative`
- **Why:** "the single most common implementation error here, and it
  systematically separates exactly the records most likely to be duplicates —
  the sparse ones"

### ER-005 · An empty string counts as missing
- **Area:** `er/match.py::Comparison.agrees`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `""` on one side, a value on the other, then `""` on both
- **Steps:** weigh
- **Expected:** `None` in both cases — two blanks do not agree
- **Why:** two records both missing a LEI are not evidence that they are the
  same party

### ER-006 · `agrees` is separate from the sign of the weight
- **Area:** `er/match.py::Comparison.agrees`
- **Type:** regression
- **Priority:** P1
- **Precondition:** `Comparison(m=0.5, u=0.5)` — weight exactly zero
- **Steps:** call `agrees` on an agreeing pair
- **Expected:** `True`, although `weight > 0` is false
- **Why:** "with `m == u` the weight is zero, `weight > 0` is False, and every
  agreement is counted as a disagreement — so EM initialised at 0.5/0.5 drives
  both parameters to the floor and returns a field worth nothing"

### ER-007 · A judgement records every contribution
- **Area:** `er/match.py::Resolver.judge`
- **Type:** contract
- **Priority:** P1
- **Precondition:** seven comparisons, two of them uninformative
- **Steps:** judge a pair
- **Expected:** five contributions, two uninformative fields, the score their
  sum; `describe()` names the three strongest and says the match rests on less
  evidence than it looks like
- **Why:** "a disputed match can be argued with rather than appealed to", and "a
  match resting on two fields out of seven is a different claim from one resting
  on seven"

### ER-008 · Three decisions, not two
- **Area:** `er/match.py::MATCH_THRESHOLD`, `NON_MATCH_THRESHOLD`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** scores of 4.0, 3.9, -2.0, -2.1
- **Steps:** judge
- **Expected:** match, review, non-match, non-match — both bounds inclusive
- **Why:** "a single threshold forces every uncertain pair into a decision
  nobody made, and the uncertain ones are exactly the ones worth a person"

### ER-009 · The review band is returned, not discarded
- **Area:** `er/match.py::Resolution.review`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a population producing matches and borderline pairs
- **Steps:** resolve
- **Expected:** both lists populated and sorted by descending score; non-matches
  are not retained
- **Why:** the band is the queue; a resolver that returns only matches has made
  the uncertain decisions silently

### ER-010 · Blocking reduces the comparisons and the reduction is reported
- **Area:** `er/match.py::Resolution.reduction`
- **Type:** performance
- **Priority:** P1
- **Precondition:** 1,000 records, blocking on postcode
- **Steps:** resolve
- **Expected:** `compared` far below `total_possible == 499,500`; `reduction`
  close to 1.0; an empty population yields 0.0 rather than a division by zero
- **Why:** "blocking is the only reason this runs at all"

### ER-011 · A pair is compared once however many keys find it
- **Area:** `er/match.py::Resolver._candidates`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** two blocking keys that both group the same pair
- **Steps:** resolve
- **Expected:** one entry in `pairs`; `by_key` counts it for both keys;
  `unique_by_key` credits only the first
- **Why:** "crediting only the first key makes every redundant key look broken,
  and that is how somebody deletes the one carrying a population nobody had
  thought about"

### ER-012 · A key that brings nothing together is named as useless
- **Area:** `er/match.py::Resolution.useless_keys`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a blocking key returning `None` for every record
- **Steps:** resolve; read `describe()`
- **Expected:** the key listed, with "which usually means the key is wrong
  rather than that there is nothing to find"
- **Why:** "a pair never compared can never match, so a blocking key that is
  wrong loses records silently and no amount of downstream cleverness recovers
  them"

### ER-013 · A redundant key is reported as redundant, not as useless
- **Area:** `er/match.py::Resolution.redundant_keys`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a key whose every pair another key already found
- **Steps:** resolve
- **Expected:** listed under `redundant_keys` and **not** `useless_keys`, with
  the sentence about keeping it if the population might grow
- **Why:** the two have different remedies and the same symptom

### ER-014 · A blocking key returning an empty string is skipped
- **Area:** `er/match.py::Resolver._candidates`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** records whose blocking value is `""`
- **Steps:** resolve
- **Expected:** no bucket formed — the guard is `if value:`
- **Why:** an empty bucket would compare every record with a missing postcode
  against every other, which is the opposite of blocking

### ER-015 · `estimate_u` is measured from random pairs and is deterministic
- **Area:** `er/match.py::estimate_u`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 1,000 records where surnames agree about 1% of the time
- **Steps:** estimate twice with the same seed, then with another
- **Expected:** about 0.01; identical for one seed, close for the other; fewer
  than two records returns 0.5
- **Why:** "almost every random pair from a population is a non-match … so a
  random sample is a non-match sample to within a rounding error"

### ER-016 · `estimate_m` falls back honestly with no labelled pairs
- **Area:** `er/match.py::estimate_m`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an empty pair list, then pairs where the field is always
  missing
- **Steps:** estimate
- **Expected:** 0.9 in both — the stated default, not a computed value
- **Why:** a fabricated estimate would be indistinguishable from a measured one
  in the weight it produces

### ER-017 · EM breaks the `m == u` symmetry before it starts
- **Area:** `er/match.py::expectation_maximisation`
- **Type:** regression
- **Priority:** P1
- **Precondition:** comparisons initialised at `m = u = 0.5`
- **Steps:** run EM for twenty rounds
- **Expected:** they are re-initialised to 0.9/0.1 and move from there; the
  returned comparisons have non-zero weights
- **Why:** "m == u is a saddle point … the algorithm sits there for as many
  rounds as it is given — returning fields worth zero bits and no indication
  that anything went wrong"

### ER-018 · EM recovers plausible parameters from a synthetic population
- **Area:** `er/match.py::expectation_maximisation`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a generated population with a known duplicate rate and known
  per-field agreement rates
- **Steps:** run EM over blocked pairs; compare the recovered `m` and `u` with
  the planted ones
- **Expected:** within a stated tolerance, and `m > u` for every field
- **Why:** the positive control — "it ran without raising" is not evidence that
  it estimated anything

### ER-019 · EM with no pairs returns the comparisons unchanged
- **Area:** `er/match.py::expectation_maximisation`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an empty pair list
- **Steps:** run EM
- **Expected:** the initialised comparisons returned, no exception
- **Why:** a population with no candidate pairs is a blocking problem, and EM
  must report it as unchanged rather than as converged

### ER-020 · A field that is never comparable keeps its prior
- **Area:** `er/match.py::expectation_maximisation`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a field null on every record
- **Steps:** run EM
- **Expected:** `m` and `u` unchanged — the guards are
  `if match_weight else comparison.m`
- **Why:** a field with no observations must not be updated to zero and then
  dominate every score

### ER-021 · Conditional independence is documented as an assumption
- **Area:** `er/match.py::expectation_maximisation` docstring
- **Type:** documentation
- **Priority:** P2
- **Precondition:** comparisons on first name and last name, which co-vary
- **Steps:** run EM; compare with a labelled ground truth
- **Expected:** estimates biased in the direction the docstring predicts
- **Why:** "it is routinely violated — first name and last name agree together
  more often than chance because of families — so the estimates are approximate,
  and treating them as exact is where this method gets a bad name"

### ER-022 · Legal-form noise is normalised away
- **Area:** `er/match.py::normalised`, `_LEGAL_FORMS`
- **Type:** functional
- **Priority:** P1
- **Precondition:** "ACME Ltd.", "Acme Limited", "ACME Holdings Group"
- **Steps:** compare each pair
- **Expected:** the first two agree; check what the third does — every one of its
  words but "acme" is a stripped legal form
- **Why:** "a comparison that says otherwise makes every entity resolution over
  company names useless before the arithmetic starts"; but a name that
  normalises to a single common token is where it over-matches

### ER-023 · A name that normalises to nothing does not match everything
- **Area:** `er/match.py::_normalise_name`
- **Type:** negative
- **Priority:** P1
- **Precondition:** "Group Holdings Ltd" and "Co Limited" — both normalise to
  `""`
- **Steps:** compare
- **Expected:** currently `True`, because two empty strings are equal
- **Why:** two unrelated shell companies would be judged in perfect agreement on
  their strongest field

### ER-024 · Trigram similarity has a defined answer for short strings
- **Area:** `er/match.py::_trigram_similarity`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `""` against `""`; `"a"` against `"a"`; `""` against `"a"`
- **Steps:** compare at threshold 0.85
- **Expected:** 1.0, 1.0, 0.0 — the padded form always yields trigrams, so
  confirm which branch is taken
- **Why:** the fallback `1.0 if left == right else 0.0` exists for a case the
  padding may make unreachable

### ER-025 · `exact` is case- and whitespace-insensitive
- **Area:** `er/match.py::exact`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `" gb00b03mlx29 "` against `"GB00B03MLX29"`; then `1` against
  `"1"`
- **Steps:** compare
- **Expected:** both agree — values are stringified before comparison
- **Why:** an identifier read from two sources differs in case and padding far
  more often than in substance; the numeric coercion is the surprising half

### ER-026 · Transitivity is not assumed, and nothing clusters
- **Area:** `er/match.py::Resolver.resolve`
- **Type:** contract
- **Priority:** P1
- **Precondition:** A matches B, B matches C, A does not match C
- **Steps:** resolve
- **Expected:** two match judgements and no cluster — the resolver returns
  pairs, never entity groups
- **Why:** the pairwise output is honest and the transitive closure is a
  decision nobody has made here; a caller that unions matched pairs into
  entities would merge A and C on evidence that says they are different

### ER-027 · The identity field is configurable and missing ids degrade
- **Area:** `er/match.py::Resolver.judge`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** records with no `id` key; then `identity="party_id"`
- **Steps:** judge
- **Expected:** `"?"` for both sides in the first; the named field used in the
  second
- **Why:** a judgement between two `?` records cannot be acted on, and the
  blocking dedupe key uses the same field — so every id-less record collides in
  `seen`

### ER-028 · A resolution describes itself in numbers
- **Area:** `er/match.py::Resolution.describe`
- **Type:** functional
- **Priority:** P2
- **Precondition:** any resolution with a useless and a redundant key
- **Steps:** read `describe()`
- **Expected:** matches, review count, pairs compared, the reduction percentage,
  and both key sentences
- **Why:** the summary is what a steward reads before deciding whether to trust
  the match list

