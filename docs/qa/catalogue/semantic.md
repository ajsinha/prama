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

<!--SUMMARY-->

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
- **Why:** the alternative is `MATCHES /None/` — see DER-039, the artefact this
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
- **Expected:** both accepted; Γ emits `>=` and `<=` respectively (DER-037)
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
- **Why:** it drives `evidence_for` (DER-025) and every sample surface; the
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
- **Why:** `is_copy` gates the whole `_from_authoritativeness` rule (DER-042); a
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
  (DER-057) — record which layer should hold the rule

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
  layer, though `ComparisonKind.ROLL_FORWARD.needs_tolerance` is true (DER-059)
- **Why:** the two layers disagree about the same relationship, and the
  disagreement decides whether a roll-forward is offered or refused

### SEM-047 · `PARENT_OF` declared without match keys
- **Area:** `semantic/relationships.py::RelationshipKind.requires_match_keys`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** two declared datasets
- **Steps:** kind `PARENT_OF`, no keys
- **Expected:** constructed here; Γ returns `Unsatisfiable
  parent_of.orphan_node` naming the missing parent pointer (DER-051)
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
  layer; Γ refuses it later (DER-060)
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
  detection" for `PARENT_OF`, which Γ explicitly cannot produce — DER-052)
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
- **Why:** the same hazard as `Rhythm.calendar` (SEM-019) and the same remedy —
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
  (DER-041)
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
  ignored
- **Type note:** the list order is authoritative, not the supplied ordinal
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
- **Why:** a remedy that omits the answer is not a remedy — the same rule DER-034
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
  every field — see SEM-248

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
- **Why:** it decides whether coverage counts a consistency dimension (DER-070);
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

