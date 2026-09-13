# Semantic layer — QA execution log

`prama.semantic` · `prama.derive` · `prama.propose` · `prama.induce` · `prama.mine` · `prama.er` ·
`prama.learn`. Every case in `qa/catalogue/semantic.md` (600 cases) was executed against
the live codebase — a real SQLite database built via the same bootstrap pattern
`tests/conftest.py` uses (`ConfigurationBuilder` + `Database.from_config` + `unit_of_work()`)
for the services/gitops/bitemporal/proposal-queue cases, and direct in-process construction of
the pure-Python value objects, generators, miners and matchers everywhere else. No case was
marked PASS without being run; the one BLOCKED case names why.

## Counts

| | Count |
|---|---:|
| Total cases | 600 |
| PASS | 586 |
| FAIL | 13 |
| BLOCKED | 1 |
| **Pass rate** | **97.7%** (586/600) |

BLOCKED: **SEM-260** — no `apply`/re-apply code path exists anywhere in the codebase to run
against (its own sibling case SEM-259 confirms the absence is deliberate and documented); there
is nothing to execute.

## Failures ranked by severity

**P1 (6)**
1. **SEM-215** — defect. A `credential_ref`-based connection can never build a live connector for
   any connector whose credential field is schema-marked secret (the norm): `connector_for()`
   injects the resolved secret, then the config-schema validator refuses the very field it just
   populated.
2. **SEM-222** — defect. `BindingService.record_drift(drift_state="changed")` — an entirely
   ordinary value — blows up as a raw, untranslated `IntegrityError` because the DB schema's
   `ck_sem_binding_drift` CHECK enumerates five literals the service layer doesn't know about.
3. **DER-058** — defect. A `PATTERN` value-domain regex containing a literal, unescaped `/`
   (ordinary: `dd/mm/yyyy`, path-shaped codes) renders to a `MATCHES /.../ ` control that the PQL
   parser then refuses to re-parse — exactly the class of artefact this codebase exists to catch.
4. **IND-011** — defect. The counterfactual gate builds zero probes for `SATISFIES` expressions
   (`ExpressionAssertion`), so a control that can never fail (`SATISFIES 1 = 1`) is `Validated`.
   Generalises the already-known row-count/freshness gap (IND-015) to PQL's general escape hatch.
5. **DER-057** — not-a-defect (catalogue premise unreachable in Python; see entry).
6. **PRP-019** — not-a-defect (catalogue misread a documented state transition; see entry).

**P2 (5):** SEM-060 (defect, doc/code drift), SEM-163 (defect, missing CHECK constraints),
SEM-245 (not-a-defect), DER-100 (not-a-defect), PRP-020 (not-a-defect).

**P3 (2):** SEM-145 (defect, banker's-rounding edge case), SEM-223 (defect, same root cause as
SEM-222).

**Net across the 13 FAILs: 8 confirmed defects** (SEM-060, SEM-145, SEM-163, SEM-215, SEM-222,
SEM-223, DER-058, IND-011) **and 5 not-a-defect** (catalogue misreadings: SEM-245, DER-057,
DER-100, PRP-019, PRP-020), **plus 1 BLOCKED** (SEM-260).

Beyond the 13 catalogued FAILs, two further defects were confirmed by direct execution per this
exercise's explicit instruction to verify the catalogue author's list of likely defects, even
where no single catalogued case isolates them:

- **Proposal routes never invoke `RelationshipGenerator` — confirmed, P1, real defect.**
  `RelationshipGenerator`/`ComparisonSpec`/`propose/adapt.py::from_relationship` are correctly
  implemented and unit-tested in isolation, but `grep` finds zero callers outside their own
  module; confirming a relationship through the live `RelationshipService` (declare, or
  propose-then-confirm) never calls the generator, `UnitOfWork` has no `proposals` DAO at all,
  and the live `/proposals` route only ever calls the single-dataset `ControlGenerator`. No
  control or comparison a relationship "generates" ever reaches a reviewer through any live path.
- **`DatasetService.correct()` and `JourneyService.set_steps()` bypass approval policy —
  confirmed, governance gap.** `correct()` never calls `ApprovalPolicy.check(...)`, so a Tier-1
  dataset declared with proper maker-checker can be corrected — including its criticality — by
  its sole author with no approver (SEM-168, executed). `set_steps()`'s signature has no
  `approved_by` parameter at all, so a Tier-1 journey's steps can always be replaced unilaterally.

## The catalogue's full flagged-defect list, verified by execution

Every item the catalogue author called out as a likely defect was independently executed. Nine
of the eleven were confirmed present exactly as the catalogue's own `Expected` field already
anticipated — meaning their individual cases scored **PASS** (the catalogue expected the current,
imperfect behaviour) even though the underlying gap is real and worth a reader's attention:

| Flagged item | Verified | Case(s) |
|---|---|---|
| `correct()`/`set_steps()` bypass approval policy | **Confirmed, real gap** | SEM-168 (PASS, catalogue expected it) |
| Maker-checker fails open on unknown criticality / `authored_by=None` | **Confirmed, real gap** | SEM-104, SEM-106 (PASS) |
| PARENT_OF/SUPERSEDES/TEMPORAL_SUCCESSOR accepted at declaration, refused by Γ | **Confirmed, working-as-designed** — Γ refuses gracefully (`Unsatisfiable`), never crashes | SEM-044/047, DER-084/092/094 (all PASS) |
| Proposal routes never run `RelationshipGenerator` | **Confirmed, real defect (P1)** — see above | (no single case isolates it; verified separately) |
| Inline-secret rejection one level deep vs. recursive GitOps export | **Confirmed, real gap** | SEM-214, SEM-241 (PASS) |
| GitOps drops `custodian_id`/`source_of_truth_id`, never exports concepts/domains | **Confirmed, real gap** | SEM-233, SEM-255 (PASS) |
| `rounding_scale` / `ValueDomain.case_sensitive` carried, never applied | **Confirmed, real gap** | SEM-028, SEM-087 (PASS) |
| `ConflictKind.CRITICALITY` absent from `COMPARED` | **Confirmed, real gap** | SEM-118 (PASS) |
| `ValueDomain` accepts an inverted range | **Confirmed, real gap** | SEM-027 (PASS) |
| `persisted._value_domain` raises on an extra JSON key | **Confirmed, real gap** | DER-014 (PASS) |
| Counterfactual gate inapplicable to row-count/freshness controls | **Confirmed, and worse than catalogued** — also inapplicable to any `SATISFIES` expression | IND-015 (PASS), IND-011 (**FAIL**, new) |


## Per-case results (id order, 600 rows)

| Id | Result | Observed |
|---|---|---|
| SEM-001 | PASS | arity=1, render()='one row per account' |
| SEM-002 | PASS | ValidationError, remedy quotes "what does one row represent?" |
| SEM-003 | PASS | ValidationError "a grain repeats an attribute", context={'attributes': ['account_id','account_id']} |
| SEM-004 | PASS | All 6 bad names ("Account ID","ACCOUNT_ID","1st_leg","_hidden","","account-id") raised ValidationError |
| SEM-005 | PASS | 63-char name accepted, 64-char refused |
| SEM-006 | PASS | render()='one record per account id per business date' |
| SEM-007 | PASS | statement with special chars, non-ASCII returned byte-for-byte |
| SEM-008 | PASS | round-trip equal, attributes stayed a tuple, order preserved |
| SEM-009 | PASS | both from_dict({}) and from_dict({"statement":"x"}) raised ValidationError |
| SEM-010 | PASS | g1==g2 -> False; statement DOES participate in equality (docstring's "same grain" claim is false); both hashable, hashes differ |
| SEM-011 | PASS | frequency=DAILY, arrival_by=None, has_arrival_expectation=False, lateness=0.0 |
| SEM-012 | PASS | "06:30","00:00","23:59" all accepted |
| SEM-013 | PASS | all 7 bad formats raised ValidationError, remedy names 06:30 |
| SEM-014 | PASS | ValidationError, remedy "Swap the two bounds...", context={'min':100,'max':10} |
| SEM-015 | PASS | min==max==5000 constructed |
| SEM-016 | PASS | constructed with lateness=-3600; int(-3600//60)==-60 |
| SEM-017 | PASS | expected_volume_min=-1 constructed |
| SEM-018 | PASS | full sentence matches exactly; missing bound rendered as ? |
| SEM-019 | PASS | volume_drivers round-trip, tuple, order preserved |
| SEM-020 | PASS | bare ValueError ("'fortnightly' is not a valid Frequency"), no remedy |
| SEM-021 | PASS | ValidationError naming both remedies (codelist ref or values) |
| SEM-022 | PASS | constructed, is_constrained=True |
| SEM-023 | PASS | ValidationError, remedy offers a different domain kind |
| SEM-024 | PASS | ValidationError quoting re.error, cause chained (PatternError) |
| SEM-025 | PASS | ValidationError, remedy "Supply a minimum, a maximum, or both." |
| SEM-026 | PASS | both minimum-only and maximum-only accepted |
| SEM-027 | PASS | ValueDomain(RANGE,min=100,max=1) constructed unchecked (inverted range bug confirmed) |
| SEM-028 | PASS | case_sensitive used only in classify/codelists.py's own class; never read by any consumer of ValueDomain.case_sensitive; conflict._domain_signature ignores it entirely (confirms flagged defect) |
| SEM-029 | PASS | round-trip: kind is enum, allowed_values is tuple |
| SEM-030 | PASS | TIER_1<TIER_4=True, int(TIER_1)=1 |
| SEM-031 | PASS | all 4 labels returned, no KeyError |
| SEM-032 | PASS | Criticality(0) and Criticality(5) both raise ValueError |
| SEM-033 | PASS | masked_by_default True only for pii, mnpi, restricted |
| SEM-034 | PASS | may_reach_external_model True only for public, internal |
| SEM-035 | PASS | is_copy True only for replica, extract |
| SEM-036 | PASS | is_live True for active, deprecated; False for proposed, retired |
| SEM-037 | PASS | generates=('referential_integrity','orphan_monitor','key_coverage'); render starts "records here point at records there" |
| SEM-038 | PASS | render contains "within 1 EUR" and "the second lags by 1 business day (TARGET2)" |
| SEM-039 | PASS | generates matches; kind.carries_trust=True |
| SEM-040 | PASS | FEEDS constructed with no keys, no tolerance |
| SEM-041 | PASS | generates=('row_count_parity','content_parity','staleness') |
| SEM-042 | PASS | generates=('rollup_parity','trust_edge') |
| SEM-043 | PASS | generates=('enrichment_coverage','provenance'); carries_trust=True |
| SEM-044 | PASS | SUPERSEDES with no keys constructed at declaration layer |
| SEM-045 | PASS | is_directional=False; generates matches |
| SEM-046 | PASS | TEMPORAL_SUCCESSOR constructed without tolerance |
| SEM-047 | PASS | constructed at declaration layer; generation_for returns Unsatisfiable rule="parent_of.orphan_node" |
| SEM-048 | PASS | carries_trust=False, is_directional=False, generates=('overlap_detection',) |
| SEM-049 | PASS | generates=('population_completeness',) |
| SEM-050 | PASS | ValidationError "a relationship must join two different datasets" |
| SEM-051 | PASS | all 10 kinds requiring keys raised ValidationError when match_keys=() |
| SEM-052 | PASS | requires_tolerance True only for reconciles_with, aggregates, derives_from |
| SEM-053 | PASS | ValidationError "needs a tolerance" |
| SEM-054 | PASS | ValidationError "a reconciliation needs at least one attribute to compare" |
| SEM-055 | PASS | AGGREGATES with compare=() constructed |
| SEM-056 | PASS | is_directional False for exactly reconciles_with, same_entity_as, mutually_exclusive, together_complete |
| SEM-057 | PASS | carries_trust True for exactly the 6 named kinds; RECONCILES_WITH False |
| SEM-058 | PASS | 7 kinds without trust, all resolve in _NO_TRUST_BECAUSE, no KeyError, 7 distinct sentences |
| SEM-059 | PASS | all 13 kinds have a .prompt, none contain a technical term |
| SEM-060 | FAIL | see FAIL section |
| SEM-061 | PASS | 13 dicts, each with exactly the 7 required keys |
| SEM-062 | PASS | round-trip equal; match_keys tuple of MatchKey, tolerance/offset are value objects |
| SEM-063 | PASS | bare ValueError ("'correlates_with' is not a valid RelationshipKind"), no remedy |
| SEM-064 | PASS | KeyError('to_dataset_id') |
| SEM-065 | PASS | full reconciliation renders semicolon-joined 5-clause sentence; bare FEEDS renders to its prompt alone |
| SEM-066 | PASS | ValidationError "a match key needs an attribute on the left-hand side" |
| SEM-067 | PASS | MatchKey(left="Account ID; DROP TABLE") accepted unchecked |
| SEM-068 | PASS | right_or_left = "account_id" then "acct_no" |
| SEM-069 | PASS | ("a","a")->"a", ("a",None)->"a", ("a","b")->"a = b" |
| SEM-070 | PASS | permits(0.50,1e6)=True |
| SEM-071 | PASS | permits(1.00,1e6)=True |
| SEM-072 | PASS | permits(1.01,1e6)=False |
| SEM-073 | PASS | True, False, False |
| SEM-074 | PASS | permits(500,1e6)=True (C2 regression confirmed fixed) |
| SEM-075 | PASS | permits(0.75,100)=True |
| SEM-076 | PASS | permits(5000,1e6)=False |
| SEM-077 | PASS | permits(0,0)=True, permits(0.01,0)=False |
| SEM-078 | PASS | permits(0.50,0.0)=True |
| SEM-079 | PASS | True, False |
| SEM-080 | PASS | permits(5,-100)=True |
| SEM-081 | PASS | ValidationError, remedy states "1.00 EUR or 0.1%" |
| SEM-082 | PASS | ValidationError, context={'absolute':-1.0} |
| SEM-083 | PASS | constructed; permits(0,100)=True, permits(0.01,100)=False |
| SEM-084 | PASS | all 3 (1.5,-0.001,10) raised ValidationError with "Express 0.1% as 0.001." remedy |
| SEM-085 | PASS | relative=0.0 and relative=1.0 both constructed |
| SEM-086 | PASS | render()='within 1 EUR or 0.1%' |
| SEM-087 | PASS | permits(0.004,100)=False (rounding_scale ignored); grep confirms field consumed nowhere but to_dict/from_dict/api schema (confirms flagged defect) |
| SEM-088 | PASS | accepted; renders 'within 1 EURO'; not validated against iso4217 |
| SEM-089 | PASS | round-trip equal, permits() behaviour identical |
| SEM-090 | PASS | is_zero=True, render='same period'; declaration render omits the offset clause entirely |
| SEM-091 | PASS | ValidationError, remedy names TARGET2 and SIFMA |
| SEM-092 | PASS | amount=0 BUSINESS_DAYS with no calendar constructed |
| SEM-093 | PASS | amount=1 CALENDAR_DAYS with no calendar constructed |
| SEM-094 | PASS | "left","TO","" all raised ValidationError |
| SEM-095 | PASS | constructed; renders "the second lags by -1 calendar day" |
| SEM-096 | PASS | "TARGET-2" and "NOT_A_CALENDAR" both accepted at declaration |
| SEM-097 | PASS | "business day" singular for +/-1, "business days" plural for 2 |
| SEM-098 | PASS | check(criticality=4, authored_by="alice", approved_by=None) returned None, no exception |
| SEM-099 | PASS | for_criticality(3) -> ApprovalRequirement.NONE; check(3, "alice", None) returned, no exception |
| SEM-100 | PASS | ValidationError: "a Tier-2 declaration requires approval before it takes effect", context {'criticality': 2, 'requirement': 'review'} |
| SEM-101 | PASS | tier 2, authored_by==approved_by=="alice" -> returned, no exception |
| SEM-102 | PASS | ValidationError: "a Tier-1 declaration cannot be approved by its own author", context {'author': 'alice', 'approver': 'alice'} |
| SEM-103 | PASS | tier 1, authored_by="alice", approved_by="bob" -> returned, no exception |
| SEM-104 | PASS | authored_by=None, approved_by="alice" -> returned, no exception (confirms flagged fail-open) |
| SEM-105 | PASS | both None -> ValidationError "requires approval before it takes effect" (first branch); approved_by="" also raised the same error |
| SEM-106 | PASS | for_criticality(0),(5),(-1) all -> ApprovalRequirement.NONE; check(criticality=0,...) with no approver and with self-approval both returned with no exception (confirms flagged fail-open) |
| SEM-107 | PASS | ApprovalPolicy(tier_three=MAKER_CHECKER), tier-3 self-approved -> ValidationError "a Tier-3 declaration cannot be approved by its own author" |
| SEM-108 | PASS | tier-1 no-approver refusal -> context={'criticality': 1, 'requirement': 'maker_checker'} |
| SEM-109 | PASS | for what in "journey declaration","dataset amendment","relationship declaration": each phrase appeared verbatim in the raised message |
| SEM-110 | PASS | detect("p1","Party.LEI",[one attr]) -> [] |
| SEM-111 | PASS | detect(..., []) -> [] |
| SEM-112 | PASS | two attrs, identical everything -> [] |
| SEM-113 | PASS | units EUR/EUR_THOUSANDS -> one conflict, kind=UNIT, severity="critical" |
| SEM-114 | PASS | lei/bic -> one conflict, kind=SEMANTIC_TYPE, severity="critical" |
| SEM-115 | PASS | mandatory/optional -> one conflict, kind=OPTIONALITY, severity="minor" |
| SEM-116 | PASS | pii/internal -> one conflict, kind=SENSITIVITY, severity="major" |
| SEM-117 | PASS | unit="EUR" vs unit=None -> [] (no UNIT conflict) |
| SEM-118 | PASS | conflicts=[]; ConflictKind.CRITICALITY not in COMPARED.values(); ConflictKind.CRITICALITY.severity == "minor" -- enum member exists, never compared (confirms flagged defect) |
| SEM-119 | PASS | same codelist_ref, different allowed_values spelling -> [] |
| SEM-120 | PASS | ("BUY","SELL") vs ("BUY","SELL","CANCEL") -> one conflict, kind=VALUE_DOMAIN, severity="major" |
| SEM-121 | PASS | range 0..100/0..1000 -> one VALUE_DOMAIN conflict; pattern ^A/^B -> one VALUE_DOMAIN conflict; two free_text domains produce [] |
| SEM-122 | PASS | 3 attrs, one empty definition -> one DEFINITION_ABSENT conflict, severity info, values={'a3': ''} |
| SEM-123 | PASS | both definitions empty -> [] (no DEFINITION_ABSENT) |
| SEM-124 | PASS | one "   ", one real -> one DEFINITION_ABSENT conflict |
| SEM-125 | PASS | one-of-each list -> "critical"; [] -> None |
| SEM-126 | PASS | render() -> "Exposure.Notional: 2 different unit values across 3 attributes (first='EUR', second='USD', third='EUR')" -- sorted by id, names substituted |
| SEM-127 | PASS | attribute .unit/.definition unchanged before/after detect(); SemanticConflict has no winner/suppression field |
| SEM-128 | PASS | all stage completions 0.0, score=0.0, stage=DISCOVERED, no exception |
| SEM-129 | PASS | score=1.0, stage=JOURNEYED, actions=() |
| SEM-130 | PASS | sum(STAGE_WEIGHTS.values())==1.0; heaviest is RELATED at 0.3 |
| SEM-131 | PASS | completion[SHAPED]==0.6 |
| SEM-132 | PASS | 5 confirmed -> 1.0; 6 confirmed -> 1.0 (clamped) |
| SEM-133 | PASS | 1 dataset, 0 relationships -> completion[RELATED]==0.0 |
| SEM-134 | PASS | NAMED=0.80, SHAPED=0.79 -> _reached_stage returns MaturityStage.NAMED |
| SEM-135 | PASS | NAMED=1.0, SHAPED=0.2, INTERPRETED=1.0, RELATED=1.0 -> returns MaturityStage.NAMED |
| SEM-136 | PASS | completion dict missing keys after NAMED -> returns MaturityStage.NAMED (walk stops on missing/0.0) |
| SEM-137 | PASS | actions[0] = "Declare the grain of 3 Tier-1 dataset(s)", estimated_controls=9, value_per_item=3.0 |
| SEM-138 | PASS | Tier-1 grain action effort_items=3; further-dataset grain action effort_items=7 (3+7=10, not 3+10) |
| SEM-139 | PASS | 7 actions produced, ordering verified (-value_per_item, effort_items); grain(3.0) > rhythm(2.0) > interpret(1.0) |
| SEM-140 | PASS | unbound action: estimated_controls=0, value_per_item=0.0, is the last action in the list |
| SEM-141 | PASS | NextAction(effort_items=0, estimated_controls=5).value_per_item == 0.0 |
| SEM-142 | PASS | 100 attrs, 0 defined, 0 mapped -> no MAPPED action; with 10 defined, 0 mapped -> MAPPED action appears |
| SEM-143 | PASS | explain() -> 6 lines, each of form "<stage>: NN% (weight NN%)" |
| SEM-144 | PASS | two assess() calls on same facts -> identical score, completion, actions (pure function, no I/O) |
| SEM-145 | FAIL | score=0.005 -> percent == 0 (expected 1); score=0.994 -> percent == 99 (matches) |
| SEM-146 | PASS | ControlGenerator().generate() on grains arity 1/2/4: arity1->2 controls, arity2->3 controls, arity4->5 controls; CONTROLS_PER_GRAIN==3 approx right only for arity2, as catalogued |
| SEM-147 | PASS | slugify -> end_of_day_positions, risk_positions_eod, spaced |
| SEM-148 | PASS | "Societe Generale Positions" -> societe_generale_positions |
| SEM-149 | PASS | "---", "japanese chars", "  " each raise ValidationError naming the value |
| SEM-150 | PASS | 300-char name truncated to 128 chars; two 128-prefix-identical names collide (same slug); declare() on the second raises ConflictError (confirmed via live DB) |
| SEM-151 | PASS | All 15 enumerated mutations each produced exactly the expected for_object audit row; missing=[] |
| SEM-152 | PASS | propose_discovered -> uow.audit.for_object(...) returns [] (0 rows) |
| SEM-153 | PASS | bind_attribute -> no attribute.bound/binding.* audit row exists (only the earlier attribute.declared) |
| SEM-154 | PASS | record_health -> ('connection.health_recorded','system',None); record_drift -> ('binding.drifted','system',None) |
| SEM-155 | PASS | declare(name only) -> shape=unbound, criticality=4, temporality=snapshot, sensitivity=internal, authoritativeness=unknown, lifecycle_state=proposed |
| SEM-156 | PASS | Unbound dataset appears in list_current and in coverage_gaps()["unbound"]; a REFERENCES relationship against it declares and confirms successfully |
| SEM-157 | PASS | approved_by=None -> proposed; approved_by="bob" -> active |
| SEM-158 | PASS | "global positions dup" and "Global-Positions-Dup" both raise ConflictError naming slug global_positions_dup |
| SEM-159 | PASS | Same name declared in tenant A and B both succeed; tenant A's dataset invisible when read scoped to tenant B |
| SEM-160 | PASS | criticality=1, authored_by=approved_by="alice" -> ValidationError; dataset count unchanged (7->7), by_slug finds nothing, 0 audit rows mention the slug |
| SEM-161 | PASS | criticality=0 and criticality=9 both reach INSERT and raise a raw, untranslated sqlalchemy.exc.IntegrityError: CHECK constraint failed: ck_sem_dataset_criticality |
| SEM-162 | PASS | shape="spreadsheet" -> same pattern: raw untranslated IntegrityError: CHECK constraint failed: ck_sem_dataset_shape |
| SEM-163 | FAIL | see FAIL section |
| SEM-164 | PASS | reason="" and reason="   " both raise ValidationError: an amendment must say why |
| SEM-165 | PASS | reason="" raises ValidationError: a correction must say what was wrong |
| SEM-166 | PASS | Tier-4 dataset amended with criticality=1, self-approved -> ValidationError: ...amendment cannot be approved by its own author |
| SEM-167 | PASS | Tier-1 dataset, description-only amendment, self-approved -> same ValidationError (current criticality used since criticality wasn't in changes) |
| SEM-168 | PASS | Tier-1 dataset (maker-checker declared), correct(reason=..., authored_by="alice") with no approver at all -> succeeds, version.criticality=1, version.approved_by=None. Confirms the flagged defect exactly |
| SEM-169 | PASS | amend() on invented id -> NotFoundError: ...has no current version |
| SEM-170 | PASS | Amending tenant A's dataset while scoped to tenant B -> NotFoundError (message doesn't reveal existence); tenant A's version still at version=1, unaffected |
| SEM-171 | PASS | declare_attribute on invented dataset id -> NotFoundError: dataset ... does not exist |
| SEM-172 | PASS | Second declare_attribute(name="amount") -> ConflictError: attribute 'amount' is already declared |
| SEM-173 | PASS | "Amount" and "AMOUNT" both accepted alongside existing "amount" |
| SEM-174 | PASS | First three attributes get ordinals [0,1,2]; after retiring a1 (2 remain), a 4th attribute gets ordinal=2 (duplicating a3's ordinal -- len(existing), not max(ordinal)+1) |
| SEM-175 | PASS | optionality="sometimes" -> raw IntegrityError: CHECK constraint failed: ck_sem_attribute_optionality; value_domain_json={"kind":"colour"} -> accepted, stored verbatim; numeric_scale=-3 -> accepted; currency_attribute="no_such_column" -> accepted at declare time, ControlGenerator().generate() produced Unsatisfiable(rule='attribute.currency', ...) exactly as catalogued (DER-061) |
| SEM-176 | PASS | Audit detail = {'dataset_id':..., 'is_cde': True, 'name': 'cde_attr'}; version.obligations_json == ['FR Y-14Q'] |
| SEM-177 | PASS | version=1, valid_to=None, superseded_at=None, is_current=True |
| SEM-178 | PASS | valid_from honoured exactly (1 year backdated); recorded_at within 5s of real now |
| SEM-179 | PASS | v1: valid_to==effective, superseded_at=None; v2: valid_from==effective, valid_to=None, superseded_at=None; exactly 1 current row |
| SEM-180 | PASS | effective_from a week before current valid_from -> ConflictError, context carries both dates, remedy offers correction instead |
| SEM-181 | PASS | effective_from == current.valid_from -> accepted; v1 ends with valid_from==valid_to (zero-length period) |
| SEM-182 | PASS | v1: superseded_at set, valid_to unchanged; v2 inherits v1's exact valid_from/valid_to |
| SEM-183 | PASS | Correcting a retired (no-current-version) dataset -> NotFoundError: ...has no current version to correct |
| SEM-184 | PASS | After retire: current is None; history has both versions [1,2]; valid_at(past moment) resolves to v1 |
| SEM-185 | PASS | Second retire() -> returns None; first valid_to unchanged |
| SEM-186 | PASS | valid_at (benefit of hindsight) on an amended-then-corrected dataset returns the corrected version (v3) |
| SEM-187 | PASS | as_of(valid_at=query, known_at=real-time-before-correction) returns the pre-correction version (v2) |
| SEM-188 | PASS | Corrected dataset: as_of(before) differs from valid_at (False), as_of(after) agrees with valid_at (True); never-corrected dataset: valid_at and as_of agree (True) |
| SEM-189 | PASS | No API accepts known_at without valid_at; calling the DAO that way raises TypeError: missing 1 required positional argument: 'valid_at' -- a refusal, never the current version |
| SEM-190 | PASS | as_of(valid_at=today, known_at=yesterday) -> None |
| SEM-191 | PASS | history = 3 rows, order [1,2,3], superseded row present |
| SEM-192 | PASS | amend->correct->amend gives versions [2,3,4] |
| SEM-193 | PASS | Two concurrent amend() calls: one succeeds (version=2), the other fails with raw IntegrityError: UNIQUE constraint failed (untranslated); exactly 1 current row afterward, 2 total versions |
| SEM-194 | PASS | All 3 versions carry authored_by/approved_by/approved_at/change_reason; correction's approved_by=None (per SEM-168) |
| SEM-195 | PASS | as_of(computed_at, computed_at) after a later correction resolves to the pre-correction "grain A" |
| SEM-196 | PASS | First redeclare of Party -> ConflictError; redeclare of party (lowercase) -> accepted (by_name is case-sensitive) |
| SEM-197 | PASS | NotFoundError, remedy "Declare the concept before declaring its properties." |
| SEM-198 | PASS | Redeclaring ISIN on Instrument -> ConflictError |
| SEM-199 | PASS | Amendment's concept_property_id == mapped property id |
| SEM-200 | PASS | NotFoundError: concept property '...' does not exist |
| SEM-201 | PASS | Mapping tenant B's attribute while acting as tenant A -> NotFoundError from the attribute amendment |
| SEM-202 | PASS | mapped_to_property(prop_a)/(prop_b) each return only that tenant's attribute; no explicit tenant filter in the DAO SQL, but property_id is a unique ULID per tenant so no leak is observable |
| SEM-203 | PASS | slug=trade_lifecycle, ordinals rewritten [0,1,2], 3 steps |
| SEM-204 | PASS | ValidationError, message names position 0, remedy lists dataset, black_box, manual |
| SEM-205 | PASS | ValidationError, remedy offers black_box |
| SEM-206 | PASS | Invented id and cross-tenant id both -> NotFoundError naming the position |
| SEM-207 | PASS | Both black_box (no description) and manual (blank description) -> ValidationError |
| SEM-208 | PASS | Caller ordinals [50,10,99] rewritten to [0,1,2] in list order |
| SEM-209 | PASS | New order reflects supplied list; empty reason on set_steps was accepted (no refusal) |
| SEM-210 | PASS | Self-approved Tier-1 journey -> ValidationError (author == approver) |
| SEM-211 | PASS | set_steps on an approved Tier-1 journey succeeded with one actor and no approver -- confirms the flagged gap |
| SEM-212 | PASS | All 10 SECRET_KEYS (and PASSWORD upper-case) -> ValidationError naming the key, remedy names credential_ref |
| SEM-213 | PASS | password="" and password=None both accepted |
| SEM-214 | PASS | {"auth":{"password":...}} and jdbc_url-embedded password both accepted (one-level-deep, key-based scan) |
| SEM-215 | FAIL | see FAIL section |
| SEM-216 | PASS | credential_ref=None -> connector (FilesystemConnector) built successfully |
| SEM-217 | PASS | teradata -> ValidationError remedy listing all 9 installed source types |
| SEM-218 | PASS | Invented dataset / invented connection -> distinct NotFoundErrors |
| SEM-219 | PASS | After bind: shape=='table', is_bound=True, dataset absent from unbound gap |
| SEM-220 | PASS | confirmed=False -> status=='proposed', drift_state=='unknown', dataset still marked bound |
| SEM-221 | PASS | shape="parquet_directory" reaches the DB with no app-level check and is refused only by ck_sem_dataset_shape (same path as SEM-162) |
| SEM-222 | FAIL | see FAIL section |
| SEM-223 | FAIL | see FAIL section |
| SEM-224 | PASS | Rebuilt with DB-legal drift states (missing, retyped, intact): drifted_bindings contains the missing/retyped dataset ids, not the intact one |
| SEM-225 | PASS | Every count in gather_facts matched a hand count of the fixture |
| SEM-226 | PASS | Domain-scoped facts: datasets=2; relationship touching one domain-A dataset counted |
| SEM-227 | PASS | Empty domain: datasets=0 but relationships_confirmed=1 -- the whole tenant's confirmed relationship leaks in via `if not dataset_ids or ...` |
| SEM-228 | PASS | Confirmed list_current is called with limit=10000 from gather_facts |
| SEM-229 | PASS | Two attributes mapped to one property with different units -> exactly one UNIT conflict naming both attribute names |
| SEM-230 | PASS | coverage_gaps returns exactly the 6 documented keys, each a list of names |
| SEM-231 | PASS | tier_one_without_grain subset of no_grain |
| SEM-232 | PASS | Full round trip (dataset_document->dump->load) reproduced the document exactly; grain/rhythm intact; attribute order preserved |
| SEM-233 | PASS | custodian_id and source_of_truth_id are in DATASET_FIELDS but never rendered; owner_id->owner, steward_id->steward renamed |
| SEM-234 | PASS | All 15 documented attribute fields present in attribute_document |
| SEM-235 | PASS | relative: None tolerance bound and right: None match-key both dropped by _compact |
| SEM-236 | PASS | 0.0, 0, and False all survive _compact at every depth |
| SEM-237 | PASS | Grain rendered as {"attributes": [...], "statement": "..."}; Grain.from_dict rebuilds it |
| SEM-238 | PASS | Relationship from/to and journey step dataset rendered as slugs, not ULIDs |
| SEM-239 | PASS | Empty slug_of -> raw dataset ids appear, no KeyError |
| SEM-240 | PASS | Name truncated to 120 chars; two relationships between the same long-named datasets collide after truncation |
| SEM-241 | PASS | credential_ref present in export; nested config["auth"]["password"] also emitted verbatim (config copied wholesale) |
| SEM-242 | PASS | Two dumps identical; unicode not escaped; all lines <=100 chars |
| SEM-243 | PASS | Malformed tab-indented YAML, a bare string, and a bare list all -> ValidationError (syntax error / "must be a mapping") |
| SEM-244 | PASS | Missing apiVersion/kind/metadata each -> ValidationError naming the key with the documented remedy; a document with no spec loads fine |
| SEM-245 | FAIL | see FAIL section |
| SEM-246 | PASS | Manifest carries tenant, SCHEMA_VERSION, and sorted counts |
| SEM-247 | PASS | only_in_store, only_in_git, different (naming the differing field) all produced; nothing written |
| SEM-248 | PASS | version, recorded_at, authored_by, change_reason differences produced zero drift |
| SEM-249 | PASS | {"tags":[]} vs {} vs {"tags":None} -- all pairings drift-free |
| SEM-250 | PASS | Reordered nested tolerance keys -> no drift; changed absolute value -> drift naming tolerance |
| SEM-251 | PASS | Reordered grain attribute list -> drift naming grain |
| SEM-252 | PASS | Added criticality + changed owner -> one DIFFERENT drift naming both, sorted |
| SEM-253 | PASS | Empty list -> "in sync..."; three drifts -> count + one rendered line per drift |
| SEM-254 | PASS | Fresh export in sync (exit 0); edited copy -> EXIT_DRIFT(3) naming criticality, --json gives in_sync:false/true correctly |
| SEM-255 | PASS | Export wrote datasets/relationships/journeys/connections; concepts and domains never written despite declaring one of each |
| SEM-256 | PASS | Domain-scoped dataset still lands at flat prama/datasets/<slug>.yaml; no prama/domains/... folder produced |
| SEM-257 | PASS | Relationship filename {kind}_{id[-8:].lower()} stable across two exports of the same install |
| SEM-258 | PASS | --dry-run: "would write" printed, directory never created |
| SEM-259 | PASS | No apply/EstateApplyCommand exists; module docstring documents the deliberate absence behind the approval workflow |
| SEM-260 | BLOCKED | No apply/re-apply code path exists anywhere to execute (confirmed absent by SEM-259); only readable as a documentation claim, not runnable |
| SEM-261 | PASS | Same field (owner) edited differently in Git and via a UI amendment -> one DIFFERENT drift naming owner; no resolution, "resolved" absent from output |
| DER-001 | PASS | optionality=OPTIONAL, sensitivity=INTERNAL, is_cde=False, value_domain.kind=FREE_TEXT, generates_a_domain_control=False |
| DER-002 | PASS | {'currency': True, 'Money': True, 'AMOUNT': True, 'EUR': False, 'currency_attribute=ccy,no unit': True} |
| DER-003 | PASS | (True, True, True, False) |
| DER-004 | PASS | cdes=['a','b'], obligations=('FINREP','FR Y-14Q') |
| DER-005 | PASS | owners={'owner1'}; steward1/custodian1 absent from every control and from JSON dump |
| DER-006 | PASS | DatasetDeclaration.is_live=False, LifecycleState.DEPRECATED.is_live=True |
| DER-007 | PASS | {'unbound': False, 'table': True, 'feed': True, '': True} |
| DER-008 | PASS | amount=True, Amount=False, ' amount'=False |
| DER-009 | PASS | from_row.name='positions_table' vs persisted.name='positions'; from_row.declared_by='bob'(recorded_by) vs persisted.declared_by='alice'(authored_by) |
| DER-010 | PASS | rendered control starts CHECK end_of_day_positions HAS UNIQUE KEY (account_id) |
| DER-011 | PASS | temporality=SNAPSHOT, sensitivity=INTERNAL, criticality=TIER_4 |
| DER-012 | PASS | kind=FREE_TEXT, is_constrained=False |
| DER-013 | PASS | kind=FREE_TEXT, is_constrained=False, no exception |
| DER-014 | PASS | TypeError: ValueDomain.__init__() got an unexpected keyword argument 'units' |
| DER-015 | PASS | 1 grain.uniqueness, 2 grain.completeness, all because contain grain sentence |
| DER-016 | PASS | because contains "would slip past the uniqueness control" and "SQL does not count nulls as duplicates" |
| DER-017 | PASS | 0 controls, 1 Unsatisfiable(rule='grain.uniqueness', reason=".. settlement_date, which is not in ds", remedy set) |
| DER-018 | PASS | reason = "the grain names a, b and c, which are not in ds" |
| DER-019 | PASS | 2 controls generated, 0 unsatisfiable |
| DER-020 | PASS | 0 controls, 1 Unsatisfiable(grain.uniqueness) when catalogue lacks the column |
| DER-021 | PASS | 2 controls generated (falls through to declaration), 0 unsatisfiable |
| DER-022 | PASS | 0 controls; reason cites "amount holds text ... compared with 0/100, which is number" |
| DER-023 | PASS | 1 control kept, 0 unsatisfiable from type-checking (no catalogue) |
| DER-024 | PASS | 11 controls generated across every rule kind; all re-parsed and re-rendered identically |
| DER-025 | PASS | {'TIER_1':'critical','TIER_2':'major','TIER_3':'minor','TIER_4':'info'} |
| DER-026 | PASS | Tier-3 CDE -> major; Tier-1 CDE -> critical (top rank, no overflow) |
| DER-027 | PASS | evidence=FULL, fail_action=BLOCK |
| DER-028 | PASS | evidence=EvidenceSpec() (default SAMPLES), fail_action=ALERT |
| DER-029 | PASS | evidence=COUNTS |
| DER-030 | PASS | evidence=EvidenceSpec() default (not COUNTS); masked_by_default=False for CONFIDENTIAL |
| DER-031 | PASS | business_key.uniqueness count = 0 when key set equals grain set |
| DER-032 | PASS | 1 business_key.uniqueness control; because distinguishes "business key" vs "grain" |
| DER-033 | PASS | reason = "the business key names missing_col, which is not present" (singular, as documented) |
| DER-034 | PASS | due_time=06:30, calendar=TARGET2, tolerance_minutes=15; because quotes arrival clause only |
| DER-035 | PASS | {59:0, 60:1, 61:1, 0:0} |
| DER-036 | PASS | Tier-1 volume control severity major (not critical); Tier-4 stays info |
| DER-037 | PASS | because = "at least 1,000 records" / "at most 5,000 records" |
| DER-038 | PASS | 0 controls; 1 Deferred(rule='rhythm.seasonality', declared='month_end', ...) |
| DER-039 | PASS | no-cutoff continuous feed -> 1 Deferred(rhythm.freshness); with arrival_by -> freshness control, no deferral |
| DER-040 | PASS | SNAPSHOT->(0,0); all other 5 temporalities -> (0,1) each, with 5 distinct destination texts |
| DER-041 | PASS | destination contains "no control at all until an as-at column exists" |
| DER-042 | PASS | where=None, because = "amount is mandatory. the position's carrying value" |
| DER-043 | PASS | 0 completeness controls, 0 unsatisfiable, 0 deferred |
| DER-044 | PASS | rendered contains WHERE product_type = 'BOND'; because = "settlement_type is mandatory when product_type = 'BOND'" |
| DER-045 | PASS | 1 Unsatisfiable(rule='attribute.completeness'), remedy mentions "stricter than you declared" |
| DER-046 | PASS | all three conditions -> 1 Unsatisfiable each, reason quotes the condition text |
| DER-047 | PASS | CHECK x SATISFIES account_id DETERMINES legal_entity_id parses to FunctionalDependencyAssertion (not ExpressionAssertion); _parse_condition returns None; generate() -> 1 unsatisfiable, 0 controls |
| DER-048 | PASS | IS VALID 'isin', dimensions=(VALIDITY,), because contains validator.describe() output |
| DER-049 | PASS | LEI screen_is_complete=False; because ends with capitalised beyond_shape sentence |
| DER-050 | PASS | with empty validator registry, iso4217 falls back to IN CODELIST 'iso4217', label in because |
| DER-051 | PASS | Unsatisfiable; remedy contains all 24 registered validator/codelist names and the "passes everything" warning |
| DER-052 | PASS | IN CODELIST 'iso4217' |
| DER-053 | PASS | Unsatisfiable(attribute.value_domain), remedy mentions "replayed against the list as it stood" |
| DER-054 | PASS | IN ('BUY', 'SELL'), because = "side may only be BUY and SELL", re-parses identically |
| DER-055 | PASS | BETWEEN 0 AND 100, >= 0, <= 100 for the three bound shapes |
| DER-056 | PASS | CHECK ds.market_value >= 0 (no quotes around 0) |
| DER-057 | FAIL | see FAIL section |
| DER-058 | FAIL | see FAIL section |
| DER-059 | PASS | pattern->(CONFORMITY,), codelist->(VALIDITY,), range->(VALIDITY,) |
| DER-060 | PASS | settlement_ccy IN CODELIST 'iso4217', dimensions={VALIDITY, CONSISTENCY}, because mentions "meaningless" |
| DER-061 | PASS | Unsatisfiable(attribute.currency), remedy mentions "euros to yen" |
| DER-062 | PASS | no currency control, no unsatisfiable, for unit='currency' + empty currency_attribute |
| DER-063 | PASS | Unsatisfiable(authoritativeness.parity), remedy = "a perfect copy of wrong data is a perfect copy" |
| DER-064 | PASS | Deferred naming MIRRORS relationship; 0 controls |
| DER-065 | PASS | GOLDEN_SOURCE/DERIVED/VENDOR_SUPPLIED/UNKNOWN all -> (0,0,0) |
| DER-066 | PASS | identity identical across all 3 generations; content_hash unchanged by grain-statement edit, changed by threshold(minimum) edit |
| DER-067 | PASS | 2 distinct identities within one dataset; no overlap with a second dataset's identities |
| DER-068 | PASS | identity differs between declaration with reference set and without |
| DER-069 | PASS | attribute-derived source_ref='ds-exposures#counterparty_lei'; dataset-derived source_ref='ds-exposures2' |
| DER-070 | PASS | sentence = "alice declared it on 2026-03-04. \"x is mandatory\"" |
| DER-071 | PASS | 1 control with rule='attribute.completeness+grain.completeness', because contains both sentences terminated with full stops |
| DER-072 | PASS | folded control: on_fail=BLOCK, evidence=FULL, severity = CDE-raised value (WARNING) |
| DER-073 | PASS | same target/assertion/where with different names/reasons -> merges to 1; different WHERE -> stays 2 |
| DER-074 | PASS | propose.adapt.from_control yields Proposal(status='proposed') for every generated control |
| DER-075 | PASS | identities, content hashes, unsatisfiable and deferred lists identical across two generate() runs, in order |
| DER-076 | PASS | len(generation)==0, is_complete=True, deferred=0 |
| DER-077 | PASS | merge() concatenates controls/unsatisfiable/deferred in order; by_rule/rules() reflect merged set |
| DER-078 | PASS | generation with an unsatisfiable -> is_complete=False; generation with only a deferral -> is_complete=True |
| DER-079 | PASS | 1 control, assertion=ReferenceAssertion, target_dataset=counterparty, target_column=cpty_id |
| DER-080 | PASS | 2 controls, 2 distinct identities |
| DER-081 | PASS | rule=enriches.coverage, dimensions=(COMPLETENESS,), because contains "a value that came from nowhere..." |
| DER-082 | PASS | control.target=to_dataset (child); assertion.target_dataset=from_dataset (parent) |
| DER-083 | PASS | 1 control (parent_of.orphan_node) only; no cycle mentioned; RelationshipGeneration has no `deferred` field; docstring explains the omission |
| DER-084 | PASS | declaration with match_keys=() accepted; Unsatisfiable rule=parent_of.orphan_node, remedy contains "parent_id = node_id" |
| DER-085 | PASS | controls=(), 1 ComparisonSpec kind=RECONCILIATION, workflow mentions classification/ageing/certificate |
| DER-086 | PASS | proposal_routes.py imports only ControlGenerator; grep across src/ finds RelationshipGenerator referenced nowhere outside its own module/__init__.py |
| DER-087 | PASS | both AGGREGATE_PARITY; rules "derives_from.aggregate_parity" vs "aggregates.rollup_parity" |
| DER-088 | PASS | 3 comparisons: ROW_COUNT_PARITY, VALUE_PARITY, STALENESS |
| DER-089 | PASS | VALUE_PARITY produced with tolerance=None, no unsatisfiable |
| DER-090 | PASS | compare=() -> 2 comparisons (ROW_COUNT_PARITY, STALENESS), no unsatisfiable |
| DER-091 | PASS | VALUE_PARITY, workflow contains "run both...old system is still authoritative" |
| DER-092 | PASS | Unsatisfiable reason="no match key joins the two datasets" |
| DER-093 | PASS | IDENTIFIER_CONSISTENCY, sentence matches exactly |
| DER-094 | PASS | declaration accepted w/ tolerance=None; Unsatisfiable reason="no materiality tolerance was given" |
| DER-095 | PASS | sentence contains "the opening balance in period_open plus the movements equals the closing balance in period_close" |
| DER-096 | PASS | OVERLAP, tolerance=None, compare=(), no unsatisfiable |
| DER-097 | PASS | COVERAGE, sentence contains "the population" |
| DER-098 | PASS | controls=(), comparisons=(), 1 Edge, carries_trust=True |
| DER-099 | PASS | all 13 kinds: 1 edge each, source/target in order, ending sentence starts with capital |
| DER-100 | FAIL | see FAIL section |
| DER-101 | PASS | DERIVES_FROM/AGGREGATES/SAME_ENTITY_AS each -> Unsatisfiable "no attribute was named to compare"; RECONCILES_WITH blocked earlier at declaration (ValidationError) |
| DER-102 | PASS | (using SUPERSEDES) exactly 1 Unsatisfiable, reason="no attribute was named to compare" (compare-check wins first) |
| DER-103 | PASS | render() stable across calls; identical text; changed tolerance -> different line and different content_hash |
| DER-104 | PASS | MUTUALLY_EXCLUSIVE declared with compare=("amount",) -> spec.compare==() |
| DER-105 | PASS | default severity=MAJOR; caller-supplied CRITICAL honoured |
| DER-106 | PASS | MIRRORS -> 3 distinct identities, stable across two generation runs |
| DER-107 | PASS | different dataset pairs -> distinct identities; same unnamed kind on same pair -> identical (colliding) identity |
| DER-108 | PASS | covered=1, applicable=2, gap=[validity] |
| DER-109 | PASS | fraction=0.25, touched_fraction=1.0, describe() states "which is the number that flatters" |
| DER-110 | PASS | applicable=0, gaps=(), fraction=1.0 |
| DER-111 | PASS | applicable=2 (conditional+mandatory only); completeness gaps={a_cond, a_mand} |
| DER-112 | PASS | accuracy gap only on the CDE attribute |
| DER-113 | PASS | REFERENCES control on the CDE -> no accuracy gap |
| DER-114 | PASS | consistency control on exposure_ccy -> exposure_amount's consistency gap cleared |
| DER-115 | PASS | control with dimensions=() -> attributes_touched=1, covered=0, 1 gap |
| DER-116 | PASS | predicate/reference/unique_key/functional_dependency attributed to columns; row_count/freshness attribute to none |
| DER-117 | PASS | 4 distinct, strictly descending risks: [1.0, 0.652, 0.565, 0.435] |
| DER-118 | PASS | maximal.risk=1.0 exactly; minimal.risk=0.25/2.3=0.1087 |
| DER-119 | PASS | criticality=0 behaves as tier 1; criticality=9 behaves as tier 4 |
| DER-120 | PASS | fraction=0.85, cde_fraction=0.90, meets_target=False |
| DER-121 | PASS | fraction=1.0, cde_fraction=1.0, meets_target=True |
| DER-122 | PASS | estate order = [b_dataset(cde_fraction=0.0), a_dataset(0.5), c_dataset(1.0)] |
| DER-123 | PASS | 4 distinct remedy sentences; validity remedy names "lei" only when semantic_type is set |
| DER-124 | PASS | worst() order identical across two calls, alphabetical on tie |
| DER-125 | PASS | value="account_id", prefill=True, because contains "distinct in every row and never null" |
| DER-126 | PASS | value="", prefill=False, because contains "has not tested whether any combination does" |
| DER-127 | PASS | candidate offered, prefill=False, describe() states "nothing is pre-filled...read the first rows only" |
| DER-128 | PASS | confidence field always numeric and carried verbatim from profile.provenance.confidence_note (never restated); because contains a number in the multi-candidate form |
| DER-129 | PASS | describe() == "ds was profiled and suggested nothing. That is a statement about the profile, not about the dataset." |
| DER-130 | PASS | 1 warning, "null in every row read", consequence mentions "fail everything"/"stopped populating" |
| DER-131 | PASS | sparse+constant+dominant column -> exactly 1 warning (the sparse one), never "holds one value in every row" |
| DER-132 | PASS | message = "holds one distinct value in the rows read", not "one value in every row" |
| DER-133 | PASS | warning counts at 89/90/91% dominance = 0/1/1; DOMINANT_SHARE==0.9 |
| DER-134 | PASS | only the 50%-null column warns; SPARSE_RATE==0.5 |
| DER-135 | PASS | rows==0 column -> no warnings, no exception |
| DER-136 | PASS | suggested_fields=={"grain"} even for a rich profile |
| PRP-001 | PASS | from_control carried identity, content, content_hash, provenance, description, dataset, rule, severity all equal to source; subject fell to "" for the grain-uniqueness (unique-key) control used |
| PRP-002 | PASS | content = 'COMPARE subledger WITH gl ON (account_id) MATCHING amount WITHIN 1 AS RECONCILIATION'; subject='amount'; with compare=(), subject fell back to right='gl' |
| PRP-003 | PASS | predicate assertion subject='account_id' (from .subject); reference assertion subject='account_id' (from .column); unique-key assertion subject='' |
| PRP-004 | PASS | MIRRORS generation: 0 controls, 3 comparisons (row_count_parity, value_parity, staleness); from_relationship produced 3 proposals |
| PRP-005 | PASS | ValueError: a rejection must say why: ... |
| PRP-006 | PASS | indicts_the_rule True only for {coincidental, incorrect} |
| PRP-007 | PASS | may_be_reconsidered True only for {not_material, too_noisy, pending_remediation} |
| PRP-008 | PASS | describe() = "would have flagged 410 of 1,000 rows (41.00%), about 14 a day, concentrated in EMEA, APAC" |
| PRP-009 | PASS | 20.0%->is_unactionable=False; 21.0%->True |
| PRP-010 | PASS | both ran=False, would_pass_today=False, is_unactionable=False; distinct describe() strings |
| PRP-011 | PASS | alerts_per_day=5.0 with days=0 |
| PRP-012 | PASS | needs_review False only for declaration; True for all five others |
| PRP-013 | PASS | declaration + 41% backtest -> needs_review=True |
| PRP-014 | PASS | authorities: declaration 100, document 80, import 60, mining 40, example 30, induction 20 -- all distinct |
| PRP-015 | PASS | ValueError: a rule attributed to a document must carry the passage... |
| PRP-016 | PASS | outcome='already_live', proposal=None, admitted=False |
| PRP-017 | PASS | outcome='superseded', supersedes='h:old-content', detail contains "replaces rather than adds" |
| PRP-018 | PASS | outcome='suppressed', detail names reason, reviewer, date |
| PRP-019 | FAIL | see FAIL section |
| PRP-020 | FAIL | see FAIL section |
| PRP-021 | PASS | INCORRECT rejection at 3%, re-offered at 90% -> suppressed |
| PRP-022 | PASS | no-backtest->backtest and backtest->no-backtest both -> suppressed |
| PRP-023 | PASS | 0%->suppressed; 0.5%->reopened with "it was rejected when nothing failed it" |
| PRP-024 | PASS | outcome='duplicate', existing proposal returned, _open dict unchanged |
| PRP-025 | PASS | outcome='corroborated', survivor origin=declaration, corroborated by mining |
| PRP-026 | PASS | mining offered first, then declaration -> declaration survives as corroborated |
| PRP-027 | PASS | second mining corroboration for same identity -> still exactly 1 mining corroboration |
| PRP-028 | PASS | outcome='superseded', supersedes = old hash, open map updated |
| PRP-029 | PASS | KeyError for both, messages distinguish "already decided" vs "never offered, or was suppressed" |
| PRP-030 | PASS | both removed from pending; both decided; only rejected one suppressed |
| PRP-031 | PASS | absent from pending, present in deferred, is_open=True, deferred_because carried |
| PRP-032 | PASS | auto_activatable = ['D'] only, out of declaration/mining/import/example/induction/document |
| PRP-033 | PASS | reloaded queue suppresses re-offer; suppression_from on accepted proposal raises ValueError |
| PRP-034 | PASS | summary counts all correct: pending=2, deferred=1, decided=1, suppressed=0 (net of reopened), would_be_too_noisy=1, by_origin totals pending, suspect_rules names indicted rule |
| PRP-035 | PASS | weights = 0.35/0.25/0.20/0.20; PRIOR_CEILING==0.20==acceptance_prior weight |
| PRP-036 | PASS | tiers 1.0/0.75/0.5/0.25; Tier 2 CDE=1.0; Tier 1 CDE clamped at 1.0 |
| PRP-037 | PASS | subject_already_covered=True -> coverage_gap=0.0 |
| PRP-038 | PASS | confidence 0.9/0.85/0.7/0.55/0.45/0.35 by origin; declaration alone <1.0; corroboration -> 0.9+0.15=1.0 (clamped) |
| PRP-039 | PASS | _confidence on an origin absent from the table -> KeyError |
| PRP-040 | PASS | penalties at 0/5/5.1/30/60% = 0, 0, -0.051, -0.3, -0.5 |
| PRP-041 | PASS | backtest=None -> 0.0; unavailable set -> 0.0 |
| PRP-042 | PASS | Tier 4, fully covered, 90% backtest -> score=0.0 (not negative) |
| PRP-043 | PASS | no history -> 0.5; one rejection -> 0.3333 |
| PRP-044 | PASS | prior capped at PRIOR_CEILING=0.2 even with 20 acceptances; Tier 1 CDE from a poor-record rule (score 0.728) still outranks Tier 4 from a perfect-record rule (score 0.3975) |
| PRP-045 | PASS | PENDING_REMEDIATION + DUPLICATE rejections leave rate=0.5, observations=0 |
| PRP-046 | PASS | prior for a ruled proposal = mean(origin rate, rule rate) = 0.6786; unruled proposal = origin rate alone = 0.5 |
| PRP-047 | PASS | PROPOSED and DEFERRED decisions leave rate/observations unchanged (0.5, 0) |
| PRP-048 | PASS | 4 INCORRECT rejections -> not suspect; 5 -> suspect_rules=('rule.b',), indicted_rules=(('rule.b',5),) |
| PRP-049 | PASS | explanation contains all four clauses (tier+CDE, unprotected share, rule acceptance rate+count, noise mark-down) |
| PRP-050 | PASS | explanation changes with context, not stored |
| PRP-051 | PASS | acceptance clause absent at 2 decisions, present at 3 |
| PRP-052 | PASS | ranking identical regardless of input order |
| PRP-053 | PASS | unmapped dataset scores identically to an explicit default Context() |
| PRP-054 | PASS | same identity -> same arm across 10 calls and on re-assignment |
| PRP-055 | PASS | holdout=0.1->9.8% control; 0.0->0%; 1.0->100% |
| PRP-056 | PASS | two salts produced different splits (38/200 differ), each stable under re-assignment |
| PRP-057 | PASS | surfaced=18, reviewed=8, accepted=5, pending=10, precision=0.625 |
| PRP-058 | PASS | precision=None, describe() contains "none reviewed yet" |
| PRP-059 | PASS | equal precision (0.5/0.5), different mean rank (1.5 vs 5.5) |
| PRP-060 | PASS | 29/29 reviews -> not measurable, describe() names "wider than any effect worth claiming"; 30/30 -> measurable |
| PRP-061 | PASS | (-0.01,0.09)->False; (0.01,0.09)->True; (-0.09,-0.01)->True |
| PRP-062 | PASS | interval centred on +0.10, matches 1.96*sqrt(p(1-p)/n+...) exactly; zero-review cases -> (0.0, 0.0) |
| PRP-063 | PASS | holdout_cost=40, describe() names it "the price of knowing any of this" |
| PRP-064 | PASS | measurable +8% with interval crossing zero -> not promoted, reason cites "point estimate" |
| PRP-065 | PASS | significant -22% -> not promoted, reason says "significantly worse", points at labels |
| PRP-066 | PASS | significant +2.9% (<3% minimum_gain) -> refused ("below the 3%..."); significant +3.1% -> promoted |
| PRP-067 | PASS | promoted; reason states difference (+20.0%), interval (+10.6% to +29.4%), and both review counts (200, 200) |
| IND-001 | PASS | ValueError names type_check, compile, sandbox, counterfactual; message contains "would reduce it to a comment" |
| IND-002 | PASS | Each of 5 crafted candidates rejected at exactly its target gate: PARSE, TYPE_CHECK, COMPILE, SANDBOX, COUNTERFACTUAL, in order |
| IND-003 | PASS | Gate.PARSE, detail is the parser's own message ('!' does not belong in a control) |
| IND-004 | PASS | Closed fence and unclosed fence both Validated; edit-needing candidate rejected at PARSE |
| IND-005 | PASS | Gate.TYPE_CHECK, detail "trades has no column called counterparty_name" |
| IND-006 | PASS | Validator(catalogue=None): Validated, passed includes type_check though nothing was checked |
| IND-007 | PASS | Uncompileable codelist reference -> Gate.COMPILE, no exception raised |
| IND-008 | PASS | 50% violation rate accepted, 51% rejected at Gate.SANDBOX with "it flags 51% of rows" |
| IND-009 | PASS | rows=() -> Validated; sandbox scanned=0, but probes=3, value_probes=2, value_probes_caught=1 (ran on empty base row) |
| IND-010 | PASS | 10,000 rows -> sandbox.scanned == 2000 |
| IND-011 | FAIL | see FAIL section |
| IND-012 | PASS | is_vacuous is True; detail includes "It does reject a missing value, but so does every row predicate in the language" |
| IND-013 | PASS | value_probes==1, value_probes_caught==1, is_vacuous is False |
| IND-014 | PASS | in/in_codelist -> non-member; matches/is_valid -> non-match + ""; between -> one value each side; comparison(numeric) -> one each side; comparison(string) -> perturbed string |
| IND-015 | PASS | HAS ROW COUNT and IS FRESH controls: value_probes==0, is_vacuous is False, COUNTERFACTUAL in passed |
| IND-016 | PASS | REFERENCES probe with an evaluator lacking the related dataset raises MissingRelatedDataset; _count_caught returns 0 (swallowed, not counted) |
| IND-017 | PASS | Second prompt contains "type_check", the parser's message, and the gate's plain meaning verbatim |
| IND-018 | PASS | Default: 3 provider calls; attempts=0: 1 call |
| IND-019 | PASS | NONE -> None, 1 call; ok=False -> None, 1 call (no retry either way) |
| IND-020 | PASS | 3 requests x 3 parse failures -> len(report.rejections)==9, failures_by_gate()['parse']==9 |
| IND-021 | PASS | 10 requests, 6 induced, 2 declined, 2 rejected -> rate 0.4; describe() separates "6 at parse" from "2 declined or unreachable"; 0 requests -> rate 0.0 |
| IND-022 | PASS | Constrained provider observation: "with the grammar enforced during decoding"; unconstrained: "validated afterwards; the provider cannot constrain decoding" |
| IND-023 | PASS | Rendered prompt carries purpose, grain, definition, and "How to read it: always from the firm's perspective, never the client's" |
| IND-024 | PASS | retrieve() called with no examples -> retrieved.examples == (), no "Example values" line in rendered prompt |
| IND-025 | PASS | All 3 existing rules listed under a "do not repeat these" block |
| IND-026 | PASS | origin=Origin.INDUCTION, source_ref carries dataset+fingerprint, observations name provider/model, gates passed, and probes caught |
| IND-027 | PASS | Paraphrased quote -> extracted==0, fabricated_quotes==1 |
| IND-028 | PASS | Reflowed whitespace quote -> matched (extracted); one word changed -> not matched, fabricated |
| IND-029 | PASS | 10 normative passages, 2 fabricated -> fabrication_rate==0.2; describe() names the rate; 0 considered -> 0.0 |
| IND-030 | PASS | 1 normative passage in the fixture document -> exactly 1 provider call, considered==1 |
| IND-031 | PASS | 39-char heading skipped, 40-char kept; locator index for kept passages advances through the skip |
| IND-032 | PASS | Locators: ['Schedule H.1', 'Field 23', '3.2.1', 'paragraph 4'] |
| IND-033 | PASS | Control with no QUOTE: line -> Gate.PARSE, detail "nothing to check the rule against" |
| IND-034 | PASS | Curly-quoted passage still extracted (1 result) |
| IND-035 | PASS | stale_citations returns the rule when its own document changed; () for same-name-different-reference doc and for unchanged document |
| IND-036 | PASS | 5 labels -> refusal naming "5" and "6"; 6 labels -> real attempt (scored non-empty) |
| IND-037 | PASS | All-good labels -> refusal containing both "nothing for a rule to separate" and "Mark a value you consider wrong" |
| IND-038 | PASS | Scored(caught=9, missed=1, false_alarms=1).is_admissible is False |
| IND-039 | PASS | Scored(caught=0, ...).is_admissible is False |
| IND-040 | PASS | 5 distinct once-seen LEIs -> no IN (...) candidate; BUY/SELL seen 5x each -> best.candidate.predicate == "IN ('BUY', 'SELL')" |
| IND-041 | PASS | 12 distinct repeated values -> IN (...) candidate exists; 13 -> none; 1 distinct value -> none |
| IND-042 | PASS | All 20 IS VALID candidates accepts(None) is True (miss the null); IS NOT NULL rejects None |
| IND-043 | PASS | good=[10,20,50,100], bad=[5,500] -> BETWEEN 10 AND 100 (recall 1.0) and >= 10 (recall 0.5), both admissible |
| IND-044 | PASS | Equal recall, different predicate length -> best picks the shorter predicate |
| IND-045 | PASS | Constructed 4 candidates splitting 4-0/3-1/2-2/1-3 on 4 values -> _next_question picks the 2-2 value, disagreement==1.0, reason mentions "eliminates about half" |
| IND-046 | PASS | 1 admissible candidate -> None; >=2 candidates but no unlabelled values -> None; unanimous survivors -> None; is_settled is True when a best exists and nothing remains to ask |
| IND-047 | PASS | Indistinguishable good/bad labels -> scored non-empty, best is None, refusal mentions "may depend on another column" |
| IND-048 | PASS | 20 labels, 6 bad, candidate catching 6/6 -> origin=Origin.EXAMPLE, observations name "20 values", "6 of them", "catches 6 of 6", "flags none of the values you accepted" |
| MIN-001 | PASS | 199 rows: candidates=(), skipped=("nothing was searched: 199 rows is too few..."); 200 rows: 2 candidates found, skipped=() |
| MIN-002 | PASS | caveats() returned all 3: one-partition note, "500 of 4,000,000 rows... (0.0%)", "500 rows is a small sample" |
| MIN-003 | PASS | coverage=1.0, partitions_seen=10, size=5000 -> caveats()==() |
| MIN-004 | PASS | candidate (account_id,) evidence.caveats includes "...holds within one business_date..." |
| MIN-005 | PASS | partitions_seen=0, spans_one_partition=False, no partition caveat present |
| MIN-006 | PASS | coverage=None, is_representative=False, caveat "the table's size is unknown..." present |
| MIN-007 | PASS | 0.89->False, 0.90->True, 1.20->coverage clamped to 1.0000, True |
| MIN-008 | PASS | support=1.0, null_fraction=0.1, is_exact=True, describe() names "100 rows (10.0%)... missing" |
| MIN-009 | PASS | support=0.0 |
| MIN-010 | PASS | 1 candidate, columns=('trade_id',), is_exact=True, rows_examined=1000, distinct=1000 |
| MIN-011 | PASS | 1 candidate ('trade_id',), not 21, at max_arity=3 |
| MIN-012 | PASS | candidates=[('other',)]; excluded names "99.6% of its values are missing..." |
| MIN-013 | PASS | 5.0% null -> eligible; 5.1% null -> excluded (> comparison confirmed) |
| MIN-014 | PASS | market_value excluded: "a continuous numeric column..." |
| MIN-015 | PASS | integer account_number eligible, not excluded |
| MIN-016 | PASS | uniqueness 0.99970 -> candidate with approximate=True; 0.99800 -> no candidate |
| MIN-017 | PASS | best=('account_id','business_date') (arity 2) over row_id (arity 1); business_key_found=True |
| MIN-018 | PASS | best=('id',), surrogate=True, business_key_found=False |
| MIN-019 | PASS | ISIN->not surrogate; ref(1..n)->surrogate; fixed-width digits->surrogate; variable-width digits->not surrogate; UUID->surrogate -- all 5 exact |
| MIN-020 | PASS | dense 1..1000->surrogate=True; sparse 1000-of-100k->surrogate=False |
| MIN-021 | PASS | skipped names "8 columns were eligible" and the arity-3 ceiling |
| MIN-022 | PASS | origin=MINING; observation states columns+rows+(when approximate) duplicates; caveats appended |
| MIN-023 | PASS | Proposal.needs_review=True, origin.may_auto_activate=False; absent from queue.auto_activatable() |
| MIN-024 | PASS | key_identity() equal across two different samples of same dataset/columns |
| MIN-025 | PASS | found counterparty_lei -> rating, is_exact=True, support=1.0 |
| MIN-026 | PASS | no dependency involves rating; discarded={'near_key_determinant':3} (non-empty) |
| MIN-027 | PASS | no dependency has trade_id as determinant; discarded['near_key_determinant']=9 |
| MIN-028 | PASS | _is_near_key at 0.89->False (searched), at 0.90->True (discarded) |
| MIN-029 | PASS | no dependency names record_type; discarded['constant_column']=1 |
| MIN-030 | PASS | (a,b)->c not reported; a->c is; discarded['implied']=2 |
| MIN-031 | PASS | null_excluded=600; evidence computed over 400; describe() states both counts |
| MIN-032 | PASS | 94% support -> _evaluate returns None (nothing); 96% -> found, is_exact=False, describe names 40 exceptions |
| MIN-033 | PASS | one group's contribution: 90 agreeing / 10 violating (isolated from other perfectly-agreeing groups) |
| MIN-034 | PASS | global instrument->issuer found; 0 conditional copies; discarded['conditional_restates_global']=12 |
| MIN-035 | PASS | 1 conditional dep, exact, renders product -> settlement_days WHERE region = 'US'; no global version found |
| MIN-036 | PASS | 49 rows->discarded; 50 rows/4%->discarded; 50 rows/6%->searched and found |
| MIN-037 | PASS | 1 completeness finding; renders state IS NOT NULL WHERE country = 'US'; describe names "mandatory under that condition" |
| MIN-038 | PASS | 0 conditional-completeness findings for a column with zero nulls |
| MIN-039 | PASS | Gamma generated an attribute.completeness control with where=BinaryOp(country = 'US') |
| MIN-040 | PASS | 1 Inclusion, exact, describe(): "...a foreign key nobody declared" |
| MIN-041 | PASS | is_exact=False, 3 orphan examples, support=0.97, describe ends "...not a coincidence" |
| MIN-042 | PASS | containment 0.89->0 found; 0.90->1 found |
| MIN-043 | PASS | no inclusion; discarded['target_is_not_a_key']=1 |
| MIN-044 | PASS | left has 103 distinct values (100 in target); partial inclusion reported, support=0.99 |
| MIN-045 | PASS | dim: 1003 rows/1000 distinct, _is_key=True; inclusion still found, exact |
| MIN-046 | PASS | 1 ordering, support=0.985, 3 counterexample rows carrying only the 2 involved columns |
| MIN-047 | PASS | 0/1000 rows bit-exact vs an exact test, yet tolerance-based identity found, is_exact=True |
| MIN-048 | PASS | 1e9-scale, 1e-12 relative diff -> found; 1e-6-scale, 1e-7 absolute diff -> not found |
| MIN-049 | PASS | 1 identity fees + net = notional; discarded['algebraic_restatement']=8, ['commutative_duplicate']=6 |
| MIN-050 | PASS | orderings=['fees <= net'] only; discarded['implied_by_identity']=2 (net<=notional, fees<=notional dropped) |
| MIN-051 | PASS | _at_least(quantity,1.0)=False but _at_least(quantity,0.0)=True; manufactured price<=notional survives _not_implied (floor is 1.0, not 0.0) |
| MIN-052 | PASS | no fees<=quantity; discarded['disjoint_ranges']=1 |
| MIN-053 | PASS | orderings=['valid_from <= valid_to'] only; discarded['weaker_ordering']=1 |
| MIN-054 | PASS | no invariant between numeric and date-string column; nothing miscompared |
| MIN-055 | PASS | no crash; mixed-type column contributes no invariant; rest of search completes (amount_a <= amount_b found) |
| MIN-056 | PASS | 49 applicable rows -> no invariant; discarded['too_sparse']=2 |
| MIN-057 | PASS | 96% support -> not found; 98% -> found |
| MIN-058 | PASS | skipped names "first 8 of 12 numeric columns... cubic in that count" |
| MIN-059 | PASS | all three provenances: origin=MINING, rule=mine.<kind>, evidence sentence first, counterexamples second, caveats last |
| MIN-060 | PASS | global vs conditional dependency identities distinct; two inclusions (same left column, two targets) have distinct identities |
| ER-001 | PASS | w(m=.9,u=.1)=3.169925, w(m=.9,u=.001)=9.813781 |
| ER-002 | PASS | disagreement_weight(m=.9,u=.1)=-3.169925; m=.5,u=.5 -> agree=0.0, disagree=0.0 |
| ER-003 | PASS | agreement_weight=13.2876, disagreement_weight=-13.2876 (finite, no inf/exception) |
| ER-004 | PASS | weigh(missing lei vs present lei) = None |
| ER-005 | PASS | weigh('' vs value)=None, weigh('' vs '')=None |
| ER-006 | PASS | agrees=True, weight=0.0, weight>0 is False |
| ER-007 | PASS | contributions=5, uninformative=('f','g'), score=15.8496, describe mentions "less evidence than it looks like" |
| ER-008 | PASS | score 4.0->match, 3.9->review, -2.0->non_match, -2.1->non_match |
| ER-009 | PASS | matches=[(A,B,25.49)], review=3 pairs incl. score 0.0, both lists sorted descending, no non-matches retained |
| ER-010 | PASS | 1000 records: compared=9500 vs total_possible=499500, reduction=0.980981; empty population -> total_possible=0, reduction=0.0 |
| ER-011 | PASS | compared=1, by_key={k1:1,k2:1}, unique_by_key={k1:1,k2:0} |
| ER-012 | PASS | useless_keys=('dead',), describe names it with "usually means the key is wrong..." |
| ER-013 | PASS | redundant_keys=('k2',), useless_keys=() |
| ER-014 | PASS | compared=0, by_key={postcode:0} -- empty-string key formed no bucket |
| ER-015 | PASS | seed7=0.0164 (repeat identical), seed99=0.0136 (close); <2 records -> 0.5 |
| ER-016 | PASS | estimate_m([])=0.9, estimate_m(all-missing)=0.9 |
| ER-017 | PASS | reinitialised from 0.5/0.5, converges to m=0.9762,u=0.3361, weight=1.5384 (nonzero) |
| ER-018 | PASS | recovered m/u within tolerance of planted values for all 3 fields, m>u in each case |
| ER-019 | PASS | empty pairs -> returned m=0.9,u=0.1 unchanged, no exception |
| ER-020 | PASS | null field unchanged: m=0.7,u=0.2 (same as initial) |
| ER-021 | PASS | correlated first/last names produce biased EM estimate for "first" (bias=-0.0675 vs true labelled non-match rate) |
| ER-022 | PASS | "ACME Ltd."/"Acme Limited" both normalise to "acme" (agree=True); "ACME Holdings Group" also normalises to "acme" (over-matches, agree=True) |
| ER-023 | PASS | both "Group Holdings Ltd" and "Co Limited" normalise to ""; normalised(...)=True (confirmed current bug behaviour) |
| ER-024 | PASS | trigrams('')={'   '} (non-empty!); sim('','')=1.0 via the *real* branch (not fallback), sim('a','a')=1.0, sim('','a')=0.0 also via real branch -- fallback appears unreachable |
| ER-025 | PASS | exact(' gb00b03mlx29 ','GB00B03MLX29')=True, exact(1,'1')=True |
| ER-026 | PASS | A-B match, B-C match, A-C review (not match); `Resolution` has no clustering attribute -- pairwise only |
| ER-027 | PASS | no-id records -> left='?', right='?'; identity="party_id" -> uses P1/P2 |
| ER-028 | PASS | describe() includes match/review counts, pairs compared, 90.00% reduction, and both the useless-key and redundant-key sentences |

## Failures

### SEM-060 · Every kind's generates matches the design table
- **Expected:** each control family named in docs/03 section 2.4's row appears in _GENERATES for that kind
- **Observed:** FEEDS row in docs/03-business-semantic-layer.md line 210 promises "Business lineage edge; latency/arrival chain; RCA path", but RelationshipKind.FEEDS.generates == ('lineage_edge','arrival_chain','latency_sla') -- no entry corresponds to "RCA path"
- **Reproduce:** `grep -n "FEEDS" docs/03-business-semantic-layer.md` (line 210) vs `python3 -c "from prama.semantic.relationships import RelationshipKind; print(RelationshipKind.FEEDS.generates)"`
- **Severity:** P2
- **Assessment:** defect (documentation/code drift) -- docs promise an "RCA path" control family for FEEDS that _GENERATES never lists, distinct from the already-known PARENT_OF/cycle-detection case (where the dict does carry the promised entry).

### SEM-145 · Percent rounds rather than truncates
- **Expected:** score 0.005 -> percent 1; score 0.994 -> percent 99 ("round, not int")
- **Observed:** score 0.005 -> percent 0; score 0.994 -> percent 99. 0.005*100 evaluates to exactly 0.5 in IEEE-754, and Python round() uses round-half-to-even, so round(0.5)==0.
- **Reproduce:** `PATH=/home/ashutosh/PycharmProjects/prama/.venv/bin:$PATH python3 -c "import sys; sys.path.insert(0,'/home/ashutosh/PycharmProjects/prama/src'); from prama.semantic.maturity import MaturityScore, EstateFacts, MaturityStage; sc=MaturityScore(scope='s', facts=EstateFacts(), completion={}, score=0.005, stage=MaturityStage.DISCOVERED, actions=()); print(sc.percent)"` (prints 0)
- **Severity:** P3
- **Assessment:** defect -- MaturityScore.percent uses bare round(self.score*100), banker's-rounding tie-break understates progress at exact .5 boundary, contradicting the module's own rationale that 0% while work has been done loses the audience.

### SEM-163 · An unvalidated temporality, sensitivity or authoritativeness
- **Expected:** the database refuses each of temporality="bitemporal", sensitivity="secret", authoritativeness="best_effort"; and if one reaches storage, derive/persisted.py::_enum silently downgrades it to the default rather than failing the page (DER-011)
- **Observed:** None of the three is refused. All three are accepted by declare() and persisted verbatim -- schema/sqlite.sql's sem_dataset_version table has CHECK constraints ck_sem_dataset_criticality, ck_sem_dataset_shape, ck_sem_dataset_lifecycle, but no CHECK constraint at all on temporality, sensitivity, or authoritativeness, unlike the sibling enum-backed columns tested in SEM-161/162. The second half of the expectation is confirmed correct: reading the "secret" row back through dataset_declaration_of() yields Sensitivity.INTERNAL (silently downgraded, DER-011 behaviour).
- **Reproduce:** declare a dataset with sensitivity="secret" -- it succeeds; then `grep -n "sensitivity\|temporality\|authoritativeness" schema/sqlite.sql` shows no matching CHECK constraint.
- **Severity:** P2
- **Assessment:** defect -- criticality, shape, and lifecycle_state on the same table all have a CHECK constraint restricting them to their enum's values; temporality, sensitivity, and authoritativeness are equally enum-backed but the schema omits the constraint for these three with no comment indicating this is deliberate -- an inconsistency in an otherwise-enforced pattern, and exactly the omission the catalogue's "Why" warns about (a mistyped sensitivity produces controls that retain samples of PII).

### SEM-215 · A credential reference never becomes a stored secret
- **Expected:** the resolved credential is injected into the connector's configuration and a live connector is built; the stored declaration is unchanged.
- **Observed:** ConnectivityService.connector_for() raises ValidationError: "a secret may not be stored in connection configuration: password" and never returns a connector, for any connector whose credential_field is marked secret=True in its config schema overlay (e.g. postgresql's password).
- **Reproduce:** declare a postgresql connection with credential_ref="env://PG_PASSWORD", then call ConnectivityService(uow, registry=register_builtin(ConnectorRegistry())).connector_for(connection_id)
- **Severity:** P1
- **Assessment:** defect -- ConnectorRegistry.create() calls schema(key).validate(config) on the config after _resolve_credential has already merged the live secret in under connector_class.credential_field. ConnectorConfigSchema.validate() unconditionally refuses any populated field marked secret=True, rejecting the very credential the method just injected. Breaks connector_for() for essentially every connector that declares its credential field as secret (the norm); only connectors whose credential field isn't schema-marked secret (e.g. sqlite) work.

### SEM-222 · Drift is recorded and routed to the declaration's owner
- **Expected:** record_drift(drift_state="missing") -> status=='broken'; record_drift(drift_state="changed") -> status unchanged (still 'confirmed').
- **Observed:** "missing" behaves as expected; "changed" raises sqlalchemy.exc.IntegrityError: CHECK constraint failed: ck_sem_binding_drift (surfaced as DatabaseError), write never completes.
- **Reproduce:** call BindingService.record_drift(..., drift_state="changed") on a confirmed binding.
- **Severity:** P1
- **Assessment:** defect -- schema/sqlite.sql's ck_sem_binding_drift CHECK restricts drift_state to ('unknown','intact','missing','retyped','renamed'), but BindingService.record_drift() is written as if any string is a legal, storable drift_state. A perfectly plausible business value like "changed" reaches the database and raises a raw IntegrityError/500 rather than completing or being cleanly refused.

### SEM-223 · An unknown drift state is accepted
- **Expected:** the string "gone" is stored verbatim as drift_state, status left alone.
- **Observed:** record_drift(drift_state="gone") raises the same ck_sem_binding_drift IntegrityError; nothing is stored.
- **Reproduce:** same as SEM-222, with drift_state="gone".
- **Severity:** P3
- **Assessment:** defect -- same root cause as SEM-222: the DB schema enforces a fixed 5-literal enum the service layer doesn't validate against, so an "unknown drift state" is refused, not accepted as the catalogue (reading only the Python code) expected.

### SEM-245 · load refuses a document from another layout version
- **Expected:** apiVersion: v1 and apiVersion: 1 both accepted (check strips the prama/v prefix and compares the remainder).
- **Observed:** apiVersion: prama/v2 -> refused (OK). apiVersion: v1 -> refused: ValidationError "document uses layout version v1, this build expects 1". apiVersion: 1 -> accepted.
- **Reproduce:** `EstateSerialiser().load('apiVersion: v1\nkind: Dataset\nmetadata: {slug: x}\n')` raises ValidationError.
- **Severity:** P2
- **Assessment:** not-a-defect (catalogue misreading) -- the code is `str(document["apiVersion"]).removeprefix("prama/v")`. removeprefix only strips the literal 7-char substring when the string starts with it exactly; "v1" does not start with "prama/v", so it's compared unchanged as "v1" != "1", correctly refused. Only the full prama/vN form or a bare N equal to GITOPS_VERSION are accepted. The catalogue's claim that bare v1 is also accepted is an incorrect extrapolation of prefix-stripping semantics, not a code defect.

### DER-057 · A pattern domain with no pattern is unsatisfiable
- **Expected:** persisted._value_domain builds a ValueDomain with kind=PATTERN, pattern=None (catalogue premise: bypasses __post_init__), and ControlGenerator._value_domain's `elif not domain.pattern:` branch reports Unsatisfiable, not a raise.
- **Observed:** `persisted._value_domain({"kind": "pattern"})` raises `ValidationError: [INPUT.INVALID] a pattern domain needs a pattern` directly from ValueDomain.__post_init__ (src/prama/semantic/values.py:305). The declaration is never built, generate() is never reached; an uncaught exception propagates instead.
- **Reproduce:** `python -c "from prama.derive import persisted; persisted._value_domain({'kind': 'pattern'})"`
- **Severity:** P1
- **Assessment:** not-a-defect, with caveat -- the catalogue's premise (a dataclass "bypassing" its own __post_init__) is not physically possible in Python, so ControlGenerator's dedicated no-pattern branch is dead code, unreachable from declaration.py/persisted.py/AttributeDeclaration. That said the observed crash is real and adjacent to DER-014: persisted._value_domain does not catch ValidationError from ValueDomain.__post_init__ the way it catches other malformed payloads, so a hand-edited stored record of this shape crashes construction instead of degrading gracefully.

### DER-058 · A pattern renders as a pattern literal
- **Expected:** pattern=r"^[A-Z]{2}\d{10}$" renders as MATCHES /^[A-Z]{2}\d{10}$/ and re-parses; a pattern containing a / is the boundary case.
- **Observed:** Base case passes. Boundary case fails: pattern=r"^[A-Z]{2}/[0-9]{3}$" renders via ast.Literal.render() as `MATCHES /^[A-Z]{2}/[0-9]{3}$/` -- the internal / is not escaped. Re-parsing raises PqlSyntaxError. The PQL lexer supports an escaped slash (\/) inside a pattern literal, but the renderer never produces that escape.
- **Reproduce:** `python -c "from prama.pql.ast import Literal; from prama.pql.parser import parse_control; lit=Literal(value='^[A-Z]{2}/[0-9]{3}\$', literal_type='pattern'); r=lit.render(); print(r); parse_control(f'CHECK t.c MATCHES {r}')"`
- **Severity:** P1
- **Assessment:** defect -- any PATTERN value-domain regex containing a literal unescaped / (very ordinary: path-shaped codes, dd/mm/yyyy dates) produces a generated control that does not re-parse, exactly the artefact class this codebase exists to refuse. Fix belongs in ast.Literal.render(): escape unescaped / before wrapping in slashes.

### DER-100 · An edge is produced even when the generation is unsatisfiable
- **Expected:** generate() on "a RECONCILES_WITH with no tolerance" yields one Unsatisfiable and one Edge.
- **Observed:** Constructing RelationshipDeclaration(kind=RECONCILES_WITH, ..., tolerance=None) through the public constructor raises ValidationError: "a 'reconciles_with' relationship needs a tolerance" immediately -- the "Steps: generate" step in the catalogue can never be reached this way, because RECONCILES_WITH.requires_tolerance is True and __post_init__ enforces it before Gamma is ever invoked. Bypassing __post_init__ (via object.__new__, simulating a pre-existing declaration) and handing it to RelationshipGenerator confirms Gamma's own logic is correct: exactly one Unsatisfiable and one Edge, merged unconditionally, exactly as documented.
- **Reproduce:** `RelationshipDeclaration(kind=RelationshipKind.RECONCILES_WITH, from_dataset_id="a", to_dataset_id="b", match_keys=(MatchKey(left="id"),), compare=("amount",), tolerance=None)` raises ValidationError before generate() can be called at all.
- **Severity:** P2
- **Assessment:** not-a-defect -- the catalogue's precondition assumes a state that RECONCILES_WITH's own (stricter) declaration-time validation forecloses; it is the one kind where all three of Gamma's refusal conditions are already double-enforced at declaration time, unlike SUPERSEDES/TEMPORAL_SUCCESSOR/PARENT_OF (DER-084/092/094, which do pass and do demonstrate the accepted-then-refused pattern). Gamma's own behaviour, verified by bypassing the constructor, matches the catalogue's expectation exactly.

### PRP-019 · A materially worse violation rate reopens a suppression
- **Expected:** offering again at 5.9%, then 6.0%, then 40% against a 3%-NOT_MATERIAL rejection yields suppressed, reopened, reopened.
- **Observed:** suppressed, reopened, duplicate. The 6.0% offer correctly reopens, which deletes the suppression and moves the proposal into the open map. The subsequent 40% offer then matches on content_hash+origin against that now-open proposal and returns outcome='duplicate' -- the 40% backtest is discarded and the stale 6% one is what a reviewer would still see.
- **Reproduce:** reject a proposal at 3%, then `queue.offer()` at 5.9%, 6.0%, 40% on the same ProposalQueue instance, no decision in between.
- **Severity:** P1
- **Assessment:** not-a-defect -- the catalogue's chain assumes the suppression persists across all three offers, but "reopened" deliberately promotes the identity into the normal open/pending lifecycle per the queue's own module doc. Once open, a further identical-content same-origin offer is correctly "duplicate" per the queue's tested contract (PRP-024) -- sameness is judged on content_hash+origin, not backtest movement. The catalogue narration did not account for this state transition; worth a design note that once open, further backtest changes on unchanged content are invisible to the reviewer until content changes (triggering supersedes).

### PRP-020 · A TOO_NOISY rejection also reopens when the rate falls
- **Expected:** offering again at 19%, then 21% (after a TOO_NOISY rejection at 40%) yields reopened, suppressed.
- **Observed:** reopened, duplicate -- same root cause as PRP-019.
- **Reproduce:** reject at 40% TOO_NOISY, then offer() at 19%, 21%, same queue, no decision in between.
- **Severity:** P2
- **Assessment:** not-a-defect, same reasoning as PRP-019.

### IND-011 · A control that cannot fail is rejected
- **Expected:** Both `CHECK t.x IS NOT NULL OR t.x IS NULL` and `CHECK t.qty > -999999999` are rejected at Gate.COUNTERFACTUAL, with detail saying hostile rows were built and accepted.
- **Observed:** The literal string in the catalogue is not valid PQL (top-level PredicateAssertion cannot be OR'd -- parse_control raises a syntax error). The faithful equivalent is `SATISFIES`, producing an ast.ExpressionAssertion. Validator._subject_of only recognises .subject/.column/.columns attributes, which ExpressionAssertion has none of, so _probes returns ([], []) -- zero probes, value_probes==0, is_vacuous is False by construction. The control sails through as Validated. `Validator(catalogue=CATALOGUE).validate("CHECK trades SATISFIES 1 = 1", ROWS)` -> Validated, sandbox={'probes': 0, 'value_probes': 0, 'is_vacuous': False, ...}. The second example (qty > -999999999) behaves correctly and is rejected at Gate.COUNTERFACTUAL as expected.
- **Reproduce:** `python -c "from prama.induce.validate import Validator; from prama.pql.types import Catalogue; v = Validator(catalogue=Catalogue.of(trades={'side':'text','qty':'number','ccy':'text','lei':'text'})); rows=[{'side':'BUY','qty':10,'ccy':'EUR','lei':'x'}]*60; print(v.validate('CHECK trades SATISFIES 1 = 1', rows))"`
- **Severity:** P1
- **Assessment:** defect -- generalises the already-known row-count/freshness gap (IND-015) to SATISFIES, the language's general-purpose escape hatch: a control that cannot fail (or padding boilerplate like SATISFIES 1=1) becomes Validated, contradicting the module's own stated 100% guarantee. `_subject_of`/`_probes` needs to walk ExpressionAssertion.condition for ColumnRefs the same way it does a plain predicate's .subject.

## Additional confirmed governance gaps (not scored as catalogue failures; PASS per the catalogue's own documented-current-behaviour Expected field)

### ADDITIONAL FLAGGED DEFECT CONFIRMED: correct()/set_steps() bypassing approval policy
DatasetService.correct() never calls self._policy.check(...) (unlike declare/amend), so a Tier-1 dataset declared with proper maker-checker can be corrected -- including changing its criticality -- by its sole author with approved_by=None and no refusal (SEM-168). JourneyService.set_steps() goes further: its signature (tenant_id, journey_id, steps, reason, authored_by=None) has no approved_by parameter at all, so a Tier-1 journey's steps can always be replaced by its sole author with no possible approval path.

### Additional notes (non-failing but noteworthy, per agent)
Two flagged likely defects for this range were both directly confirmed by execution and match the catalogue's own "currently accepted"/"never exported" Expected values (so scored PASS, not FAIL): a nested secret ({"auth":{"password":...}} or jdbc_url with embedded password) passes ConnectionService._reject_inline_secrets's one-level-deep key scan and is then exported verbatim into GitOps YAML by connection_document (SEM-214/SEM-241); and custodian_id/source_of_truth_id are listed in DATASET_FIELDS but never rendered, while cli/estate.py::_collect never calls EstateSerialiser.path_for/*_document for concepts or domains even though path_for has folders for both (SEM-233/SEM-255).

### FLAGGED DEFECT CONFIRMED (beyond the 67 catalogued cases, per explicit task instruction): proposal routes never run RelationshipGenerator
- grep across src/prama for from_relationship/RelationshipGenerator( finds zero callers outside derive/relationships.py itself and propose/adapt.py's own definitions -- exercised only by tests, never by any route/service.
- Direct execution against a live sqlite DB: RelationshipService.declare() for a confirmed RECONCILES_WITH relationship -> 0 calls to RelationshipGenerator.generate; the audit event's detail["generates"] comes only from the static RelationshipKind.generates property, not from anything actually derived.
- RelationshipService.propose_discovered() + .confirm() for a MIRRORS relationship (the "steward confirms on the estate map" path the module's own docstring describes) -> 0 calls after confirmation.
- UnitOfWork exposes no `proposals` DAO at all -- ProposalQueue has no persistent backing store in the live app.
- src/prama/web/routes/proposal_routes.py::_generate (the live "/proposals" screen) only calls ControlGenerator().generate(declaration) -- never touches relationships, RelationshipGenerator, ComparisonSpec, or propose/adapt.py at all.
- **Severity:** P1 **Assessment:** defect -- RelationshipGenerator/ComparisonSpec/propose/adapt.py::from_relationship are correctly implemented and unit-tested in isolation but are dead code in the running application; confirming any relationship never generates the comparisons/controls the UI and audit trail claim it "generates", and nothing reaches a reviewer through any live path.

---

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
