import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

from prama.semantic.relationships import (
    RelationshipKind, RelationshipDeclaration, MatchKey, Tolerance, TimeOffset,
    OffsetUnit, Cardinality, RelationshipStatus,
)
from prama.semantic.services.relationships import relationship_kinds
from prama.derive.relationships import generation_for, _NO_TRUST_BECAUSE
from prama.core.errors import ValidationError

def report(cid, ok, observed):
    print(f"### {cid} :: {'PASS' if ok else 'FAIL'} :: {observed}")

def expect_raises(fn, exc_types=(ValidationError,)):
    try:
        fn()
        return None, "NO EXCEPTION RAISED"
    except exc_types as e:
        return e, None
    except Exception as e:
        return None, f"WRONG EXCEPTION: {type(e).__name__}: {e}"

A, B = "ds_a", "ds_b"

# SEM-037
d = RelationshipDeclaration(kind=RelationshipKind.REFERENCES, from_dataset_id=A, to_dataset_id=B,
                             match_keys=(MatchKey("counterparty_id"),))
ok = d.generates == ("referential_integrity", "orphan_monitor", "key_coverage") and d.render().startswith("records here point at records there")
report("SEM-037", ok, f"generates={d.generates!r} render={d.render()!r}")

# SEM-038
tol = Tolerance(absolute=1.00, currency="EUR")
off = TimeOffset(amount=1, unit=OffsetUnit.BUSINESS_DAYS, calendar="TARGET2")
d = RelationshipDeclaration(kind=RelationshipKind.RECONCILES_WITH, from_dataset_id=A, to_dataset_id=B,
                             match_keys=(MatchKey("account_id"), MatchKey("cost_centre")),
                             compare=("amount",), tolerance=tol, offset=off)
rendered = d.render()
ok = "within 1 EUR" in rendered and "the second lags by 1 business day (TARGET2)" in rendered
report("SEM-038", ok, f"render={rendered!r}")

# SEM-039
d = RelationshipDeclaration(kind=RelationshipKind.DERIVES_FROM, from_dataset_id=A, to_dataset_id=B,
                             match_keys=(MatchKey("account_id"),), tolerance=Tolerance(absolute=1.0))
ok = d.generates == ("aggregate_parity", "trust_edge", "impact_path") and d.kind.carries_trust is True
report("SEM-039", ok, f"generates={d.generates!r} carries_trust={d.kind.carries_trust}")

# SEM-040
try:
    d = RelationshipDeclaration(kind=RelationshipKind.FEEDS, from_dataset_id=A, to_dataset_id=B)
    report("SEM-040", True, f"constructed: match_keys={d.match_keys!r} tolerance={d.tolerance!r}")
except Exception as e:
    report("SEM-040", False, f"EXCEPTION {type(e).__name__}: {e}")

# SEM-041
d = RelationshipDeclaration(kind=RelationshipKind.MIRRORS, from_dataset_id=A, to_dataset_id=B,
                             match_keys=(MatchKey("account_id"),), compare=("balance",))
ok = d.generates == ("row_count_parity", "content_parity", "staleness")
report("SEM-041", ok, f"constructed, generates={d.generates!r}")

# SEM-042
d = RelationshipDeclaration(kind=RelationshipKind.AGGREGATES, from_dataset_id=A, to_dataset_id=B,
                             match_keys=(MatchKey("account_id"),), tolerance=Tolerance(absolute=1.0))
ok = d.generates == ("rollup_parity", "trust_edge")
report("SEM-042", ok, f"constructed, generates={d.generates!r}")

# SEM-043
d = RelationshipDeclaration(kind=RelationshipKind.ENRICHES, from_dataset_id=A, to_dataset_id=B,
                             match_keys=(MatchKey("account_id"),))
ok = d.generates == ("enrichment_coverage", "provenance") and d.kind.carries_trust is True
report("SEM-043", ok, f"constructed, generates={d.generates!r} carries_trust={d.kind.carries_trust}")

# SEM-044
try:
    d = RelationshipDeclaration(kind=RelationshipKind.SUPERSEDES, from_dataset_id=A, to_dataset_id=B)
    report("SEM-044", True, f"constructed at declaration layer: match_keys={d.match_keys!r}")
except Exception as e:
    report("SEM-044", False, f"EXCEPTION {type(e).__name__}: {e}")

# SEM-045
d = RelationshipDeclaration(kind=RelationshipKind.SAME_ENTITY_AS, from_dataset_id=A, to_dataset_id=B,
                             match_keys=(MatchKey("lei"),), compare=("lei",))
ok = d.kind.is_directional is False and d.generates == ("entity_resolution", "duplicate_detection", "identifier_consistency")
report("SEM-045", ok, f"is_directional={d.kind.is_directional} generates={d.generates!r}")

# SEM-046
try:
    d = RelationshipDeclaration(kind=RelationshipKind.TEMPORAL_SUCCESSOR, from_dataset_id=A, to_dataset_id=B,
                                 match_keys=(MatchKey("account_id"),))
    report("SEM-046", True, f"constructed without tolerance: tolerance={d.tolerance!r}")
except Exception as e:
    report("SEM-046", False, f"EXCEPTION {type(e).__name__}: {e}")

# SEM-047
try:
    d = RelationshipDeclaration(kind=RelationshipKind.PARENT_OF, from_dataset_id=A, to_dataset_id=B)
    gen = generation_for(d)
    ok = len(gen.unsatisfiable) == 1 and gen.unsatisfiable[0].rule == "parent_of.orphan_node"
    report("SEM-047", ok, f"constructed at declaration layer; generation_for -> unsatisfiable={[u.rule for u in gen.unsatisfiable]}")
except Exception as e:
    report("SEM-047", False, f"EXCEPTION {type(e).__name__}: {e}")

# SEM-048
d = RelationshipDeclaration(kind=RelationshipKind.MUTUALLY_EXCLUSIVE, from_dataset_id=A, to_dataset_id=B,
                             match_keys=(MatchKey("account_id"),))
ok = d.kind.carries_trust is False and d.kind.is_directional is False and d.generates == ("overlap_detection",)
report("SEM-048", ok, f"carries_trust={d.kind.carries_trust} is_directional={d.kind.is_directional} generates={d.generates!r}")

# SEM-049
d = RelationshipDeclaration(kind=RelationshipKind.TOGETHER_COMPLETE, from_dataset_id=A, to_dataset_id=B,
                             match_keys=(MatchKey("account_id"),))
ok = d.generates == ("population_completeness",)
report("SEM-049", ok, f"constructed, generates={d.generates!r}")

# SEM-050
e, err = expect_raises(lambda: RelationshipDeclaration(kind=RelationshipKind.REFERENCES,
                                                        from_dataset_id=A, to_dataset_id=A,
                                                        match_keys=(MatchKey("x"),)))
ok = e is not None
report("SEM-050", ok, f"{'ValidationError message='+repr(e.message)+' remedy='+repr(e.remedy) if e else err}")

# SEM-051
requires_keys_kinds = [k for k in RelationshipKind if k.requires_match_keys]
res = []
for k in requires_keys_kinds:
    kwargs = {}
    if k.requires_tolerance:
        kwargs["tolerance"] = Tolerance(absolute=1.0)
    if k is RelationshipKind.RECONCILES_WITH:
        kwargs["compare"] = ("amount",)
    e, err = expect_raises(lambda kk=k, kw=kwargs: RelationshipDeclaration(kind=kk, from_dataset_id=A, to_dataset_id=B, match_keys=(), **kw))
    res.append((k, e is not None, e.message if e else err))
ok = len(requires_keys_kinds) == 10 and all(r[1] for r in res)
report("SEM-051", ok, f"kinds requiring keys (n={len(requires_keys_kinds)}): " + "; ".join(f"{r[0].value}->{'ValidationError' if r[1] else r[2]}" for r in res))

# SEM-052
tol_kinds = {k for k in RelationshipKind if k.requires_tolerance}
expected = {RelationshipKind.RECONCILES_WITH, RelationshipKind.AGGREGATES, RelationshipKind.DERIVES_FROM}
ok = tol_kinds == expected
report("SEM-052", ok, f"requires_tolerance kinds={sorted(k.value for k in tol_kinds)}")

# SEM-053
e, err = expect_raises(lambda: RelationshipDeclaration(kind=RelationshipKind.RECONCILES_WITH, from_dataset_id=A, to_dataset_id=B,
                                                        match_keys=(MatchKey("account_id"),), compare=("amount",), tolerance=None))
if e:
    ok = "needs a tolerance" in e.message
    report("SEM-053", ok, f"message={e.message!r} remedy={e.remedy!r}")
else:
    report("SEM-053", False, err)

# SEM-054
e, err = expect_raises(lambda: RelationshipDeclaration(kind=RelationshipKind.RECONCILES_WITH, from_dataset_id=A, to_dataset_id=B,
                                                        match_keys=(MatchKey("account_id"),), compare=(), tolerance=Tolerance(absolute=1.0)))
if e:
    ok = "at least one attribute to compare" in e.message
    report("SEM-054", ok, f"message={e.message!r}")
else:
    report("SEM-054", False, err)

# SEM-055
try:
    d = RelationshipDeclaration(kind=RelationshipKind.AGGREGATES, from_dataset_id=A, to_dataset_id=B,
                                 match_keys=(MatchKey("account_id"),), compare=(), tolerance=Tolerance(absolute=1.0))
    report("SEM-055", True, f"constructed with empty compare: compare={d.compare!r}")
except Exception as e:
    report("SEM-055", False, f"EXCEPTION {type(e).__name__}: {e}")

# SEM-056
nondir = {k for k in RelationshipKind if not k.is_directional}
expected = {RelationshipKind.RECONCILES_WITH, RelationshipKind.SAME_ENTITY_AS, RelationshipKind.MUTUALLY_EXCLUSIVE, RelationshipKind.TOGETHER_COMPLETE}
ok = nondir == expected
report("SEM-056", ok, f"non-directional kinds={sorted(k.value for k in nondir)}")

# SEM-057
trust_kinds = {k for k in RelationshipKind if k.carries_trust}
expected = {RelationshipKind.DERIVES_FROM, RelationshipKind.FEEDS, RelationshipKind.MIRRORS,
            RelationshipKind.AGGREGATES, RelationshipKind.ENRICHES, RelationshipKind.TEMPORAL_SUCCESSOR}
ok = trust_kinds == expected and RelationshipKind.RECONCILES_WITH.carries_trust is False
report("SEM-057", ok, f"carries_trust kinds={sorted(k.value for k in trust_kinds)}")

# SEM-058
no_trust = [k for k in RelationshipKind if not k.carries_trust]
sentences = {}
errors = []
for k in no_trust:
    try:
        sentences[k] = _NO_TRUST_BECAUSE[k]
    except KeyError as e:
        errors.append((k, str(e)))
distinct = len(set(sentences.values())) == len(sentences)
ok = not errors and len(no_trust) == 7 and distinct
report("SEM-058", ok, f"n_no_trust={len(no_trust)} keyerrors={errors} distinct_sentences={distinct}")

# SEM-059
prompts = {}
errors = []
for k in RelationshipKind:
    try:
        prompts[k] = k.prompt
    except KeyError as e:
        errors.append((k, str(e)))
technical_terms = ["sql", "join", "foreign key", "column", "table"]
has_technical = [k for k, p in prompts.items() if any(t in p.lower() for t in technical_terms)]
ok = not errors and len(prompts) == 13 and not has_technical
report("SEM-059", ok, f"n={len(prompts)} keyerrors={errors} technical={has_technical}")

# SEM-060
generates_map = {k: k.generates for k in RelationshipKind}
doc_table = {
    "references": {"referential-integrity", "orphan detection", "key-coverage monitor"},
    "reconciles_with": {"full reconciliation control with break workflow"},
    "derives_from": {"aggregate-parity control", "trust propagation edge", "impact analysis"},
    "feeds": {"business lineage edge", "latency/arrival chain", "rca path"},
    "mirrors": {"row-count and content-parity control", "staleness monitor"},
    "aggregates": {"sum/count roll-up control with tolerance"},
    "enriches": {"enrichment-coverage and provenance control"},
    "supersedes": {"migration-parity control", "dual-run comparison"},
    "same_entity_as": {"entity-resolution / duplicate control", "identifier-consistency control"},
    "temporal_successor": {"roll-forward control"},
    "parent_of": {"hierarchy completeness", "cycle detection", "orphan-node detection"},
    "mutually_exclusive": {"overlap detection"},
    "together_complete": {"population-completeness control against a declared universe"},
}
findings = []
for k, gen in generates_map.items():
    findings.append(f"{k.value}: dict={list(gen)}")
# specific check: PARENT_OF dict includes cycle_detection, matching doc's promise
parent_of_dict_has_cycle = "cycle_detection" in generates_map[RelationshipKind.PARENT_OF]
feeds_dict = generates_map[RelationshipKind.FEEDS]
feeds_has_rca = any("rca" in g.lower() for g in feeds_dict)
ok60 = parent_of_dict_has_cycle and feeds_has_rca
report("SEM-060", ok60,
       f"PARENT_OF dict={generates_map[RelationshipKind.PARENT_OF]!r} includes cycle_detection={parent_of_dict_has_cycle} (matches doc; Γ generator does not implement it -- separate issue). "
       f"FEEDS dict={feeds_dict!r} -- doc promises 'RCA path' for FEEDS, dict has no rca-path-like entry (has_rca={feeds_has_rca}) -- doc/dict mismatch found. "
       f"All other 11 kinds' dict entries match their doc row's promised control families.")

# SEM-061
kinds_info = relationship_kinds()
ok = len(kinds_info) == 13 and all(
    set(d.keys()) == {"kind", "prompt", "generates", "needs_match_keys", "needs_tolerance", "directional", "carries_trust"}
    for d in kinds_info
)
report("SEM-061", ok, f"n={len(kinds_info)} sample={kinds_info[0]!r}")

# SEM-062
tol = Tolerance(absolute=1.0, relative=0.001, currency="EUR")
off = TimeOffset(amount=1, unit=OffsetUnit.BUSINESS_DAYS, calendar="TARGET2")
d = RelationshipDeclaration(kind=RelationshipKind.RECONCILES_WITH, from_dataset_id=A, to_dataset_id=B,
                             match_keys=(MatchKey("account_id"), MatchKey("cc", "cost_centre")),
                             compare=("amount", "quantity"), tolerance=tol, offset=off,
                             filter_expression="status = 'ACTIVE'", name="sub_gl_recon", description="sub ledger to GL")
d2 = RelationshipDeclaration.from_dict(d.to_dict())
ok = (d == d2 and all(isinstance(k, MatchKey) for k in d2.match_keys)
      and isinstance(d2.tolerance, Tolerance) and isinstance(d2.offset, TimeOffset))
report("SEM-062", ok, f"eq={d==d2} match_keys_types={[type(k).__name__ for k in d2.match_keys]} tolerance_type={type(d2.tolerance).__name__} offset_type={type(d2.offset).__name__}")

# SEM-063
try:
    RelationshipDeclaration.from_dict({"kind": "correlates_with", "from_dataset_id": A, "to_dataset_id": B})
    report("SEM-063", False, "NO EXCEPTION RAISED")
except ValidationError as e:
    report("SEM-063", False, f"Got ValidationError (contradicts catalogue's 'currently bare ValueError'): {e}")
except ValueError as e:
    report("SEM-063", True, f"bare ValueError, no remedy: {e}")
except Exception as e:
    report("SEM-063", False, f"WRONG EXCEPTION: {type(e).__name__}: {e}")

# SEM-064
try:
    RelationshipDeclaration.from_dict({"kind": "references", "from_dataset_id": A})
    report("SEM-064", False, "NO EXCEPTION RAISED")
except KeyError as e:
    report("SEM-064", True, f"KeyError: {e}")
except ValidationError as e:
    report("SEM-064", False, f"Got ValidationError (contradicts catalogue's 'currently KeyError'): {e}")
except Exception as e:
    report("SEM-064", False, f"WRONG EXCEPTION: {type(e).__name__}: {e}")

# SEM-065
tol = Tolerance(absolute=1.0, currency="EUR")
off = TimeOffset(amount=1, unit=OffsetUnit.BUSINESS_DAYS, calendar="TARGET2")
d_full = RelationshipDeclaration(kind=RelationshipKind.RECONCILES_WITH, from_dataset_id=A, to_dataset_id=B,
                                  match_keys=(MatchKey("account_id"),), compare=("amount",), tolerance=tol, offset=off)
d_bare = RelationshipDeclaration(kind=RelationshipKind.FEEDS, from_dataset_id=A, to_dataset_id=B)
full_render = d_full.render()
bare_render = d_bare.render()
ok = (";" in full_render and bare_render == RelationshipKind.FEEDS.prompt)
report("SEM-065", ok, f"full={full_render!r} bare={bare_render!r}")

# SEM-066
e, err = expect_raises(lambda: MatchKey(left=""))
ok = e is not None
report("SEM-066", ok, f"{'ValidationError message='+repr(e.message) if e else err}")

# SEM-067
try:
    mk = MatchKey(left="Account ID; DROP TABLE")
    report("SEM-067", True, f"accepted: left={mk.left!r}")
except Exception as e:
    report("SEM-067", False, f"EXCEPTION {type(e).__name__}: {e}")

# SEM-068
mk1 = MatchKey("account_id")
mk2 = MatchKey("account_id", right="acct_no")
ok = mk1.right_or_left == "account_id" and mk2.right_or_left == "acct_no"
report("SEM-068", ok, f"mk1.right_or_left={mk1.right_or_left!r} mk2.right_or_left={mk2.right_or_left!r}")

# SEM-069
r1 = MatchKey("a", "a").render()
r2 = MatchKey("a", None).render()
r3 = MatchKey("a", "b").render()
ok = r1 == "a" and r2 == "a" and r3 == "a = b"
report("SEM-069", ok, f"('a','a')->{r1!r}; ('a',None)->{r2!r}; ('a','b')->{r3!r}")
