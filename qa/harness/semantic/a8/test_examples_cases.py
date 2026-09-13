"""IND-036..048 -- induce/examples.py"""
from __future__ import annotations

from prama.core.provenance import Origin
from prama.induce.examples import ExampleInducer, Label, generalisation_provenance

GOOD_LEIS = [
    "5493001KJTIIGC8Y1R12",
    "213800LBQA1Y9L22JB70",
    "HWUPKR0MPOU8FGXBT394",
    "7LTWFZYICNSX8D621K86",
    "ZXTILKJKG63JELOEG630",
]
BAD_LEIS = ["AAAAAAAAAAAAAAAAAA00", "not-an-lei", "", "549300"]


def leis():
    return [Label(v, True) for v in GOOD_LEIS] + [Label(v, False) for v in BAD_LEIS]


def sep(cid):
    print(f"\n=== {cid} ===")


# IND-036
sep("IND-036")
five_labels = [Label("a", True), Label("b", True), Label("c", False), Label("d", False), Label("e", True)]
result5 = ExampleInducer().generalise("t", "x", five_labels)
print("5 labels refusal:", result5.refusal)
print("5 labels best is None:", result5.best is None)

six_labels = five_labels + [Label("f", True)]
result6 = ExampleInducer().generalise("t", "x", six_labels)
print("6 labels refusal:", repr(result6.refusal))
print("6 labels attempted (scored non-empty):", len(result6.scored) > 0)

# IND-037
sep("IND-037")
all_good = [Label(f"v{i}", True) for i in range(10)]
result_good = ExampleInducer().generalise("t", "x", all_good)
print("refusal:", result_good.refusal)
print("mentions 'nothing for a rule to separate':", "nothing for a rule to separate" in result_good.refusal)
print("mentions 'Mark a value you consider wrong':", "Mark a value you consider wrong" in result_good.refusal)

# IND-038
sep("IND-038")
from prama.induce.examples import Candidate, Scored
exact_scored_038 = Scored(
    candidate=Candidate(predicate="X", description="d", accepts=lambda v: True),
    caught=9, missed=1, false_alarms=1,
)
print("catches 9/10 bad, flags 1 good -> is_admissible:", exact_scored_038.is_admissible, "(expect False)")

result38 = ExampleInducer().generalise("exposures", "counterparty_lei", leis())
false_alarm_candidates = [s for s in result38.scored if s.false_alarms > 0]
print("(broader check) candidates with false_alarms > 0 exist:", len(false_alarm_candidates) > 0)
print("(broader check) all such candidates inadmissible:", all(not s.is_admissible for s in false_alarm_candidates))

# IND-039
sep("IND-039")
exact_scored_039 = Scored(
    candidate=Candidate(predicate="Y", description="d", accepts=lambda v: True),
    caught=0, missed=4, false_alarms=0,
)
print("accepts every labelled value (caught=0) -> is_admissible:", exact_scored_039.is_admissible, "(expect False)")

result39 = ExampleInducer().generalise("t", "x", leis())
zero_catch = [s for s in result39.scored if s.caught == 0]
print("(broader check) zero-catch candidates exist:", len(zero_catch) > 0)
print("(broader check) zero-catch candidates all inadmissible:", all(not s.is_admissible for s in zero_catch))

# IND-040
sep("IND-040")
result40a = ExampleInducer().generalise("exposures", "counterparty_lei", leis())
print("no IN(...) memorisation candidate for distinct-once LEIs:", all("IN ('5493001" not in s.candidate.predicate for s in result40a.scored))
labels40b = [Label(v, True) for v in ["BUY", "SELL", "BUY", "SELL", "BUY"]] + [Label(v, False) for v in ["B", "buy", "PURCHASE"]]
result40b = ExampleInducer().generalise("trades", "side", labels40b)
print("best predicate for repeated values:", result40b.best.candidate.predicate if result40b.best else None)

# IND-041
sep("IND-041")
twelve_good = [f"V{i:02d}" for i in range(12)]
labels12 = [Label(v, True) for v in twelve_good] * 2 + [Label("BAD1", False), Label("BAD2", False)]
result12 = ExampleInducer().generalise("t", "x", labels12)
has_in12 = any(s.candidate.predicate.startswith("IN (") for s in result12.scored)
print("12 distinct repeated values -> IN candidate exists:", has_in12)

thirteen_good = [f"V{i:02d}" for i in range(13)]
labels13 = [Label(v, True) for v in thirteen_good] * 2 + [Label("BAD1", False), Label("BAD2", False)]
result13 = ExampleInducer().generalise("t", "x", labels13)
has_in13 = any(s.candidate.predicate.startswith("IN (") for s in result13.scored)
print("13 distinct repeated values -> IN candidate exists:", has_in13, "(expect False)")

one_distinct = [Label("ONLY", True)] * 6 + [Label("BAD1", False), Label("BAD2", False)]
result_one = ExampleInducer().generalise("t", "x", one_distinct)
has_in_one = any(s.candidate.predicate.startswith("IN (") for s in result_one.scored)
print("1 distinct value -> IN candidate exists:", has_in_one, "(expect False)")

# IND-042
sep("IND-042")
labels42 = [Label(v, True) for v in GOOD_LEIS] + [Label(None, False)] + [Label(v, False) for v in BAD_LEIS]
result42 = ExampleInducer().generalise("t", "x", labels42)
is_valid_candidates = [s for s in result42.scored if s.candidate.predicate.startswith("IS VALID")]
print("num IS VALID candidates:", len(is_valid_candidates))
for s in is_valid_candidates:
    accepts_none = s.candidate.accepts(None)
    print(f"  {s.candidate.predicate}: accepts(None)={accepts_none} (expect True, i.e. misses the null)")
not_null = [s for s in result42.scored if s.candidate.predicate == "IS NOT NULL"]
print("IS NOT NULL rejects None:", not not_null[0].candidate.accepts(None) if not_null else "MISSING")

# IND-043
sep("IND-043")
numeric_labels = [Label(v, True) for v in [10, 20, 50, 100]] + [Label(v, False) for v in [5, 500]]
result43 = ExampleInducer().generalise("t", "x", numeric_labels)
between_cands = [s for s in result43.scored if s.candidate.predicate.startswith("BETWEEN")]
min_cands = [s for s in result43.scored if s.candidate.predicate.startswith(">=")]
print("BETWEEN candidate:", [s.candidate.predicate for s in between_cands])
print("BETWEEN admissible:", [s.is_admissible for s in between_cands])
print(">= candidate:", [s.candidate.predicate for s in min_cands])
print(">= admissible:", [s.is_admissible for s in min_cands])
if between_cands and min_cands:
    print("BETWEEN recall >= >= recall:", between_cands[0].recall, min_cands[0].recall)

# IND-044
sep("IND-044")
from prama.induce.examples import Candidate, Scored
short_c = Candidate(predicate="IS NOT NULL", description="d1", accepts=lambda v: True)
long_c = Candidate(predicate="IS NOT NULL AND HAS LENGTH BETWEEN 1 AND 100", description="d2", accepts=lambda v: True)
s_short = Scored(candidate=short_c, caught=5, missed=0, false_alarms=0)
s_long = Scored(candidate=long_c, caught=5, missed=0, false_alarms=0)
from prama.induce.examples import Generalisation
gen = Generalisation(dataset="t", column="x", scored=(s_short, s_long))
print("best is shorter predicate:", gen.best.candidate.predicate == "IS NOT NULL")

# IND-045 -- exact 4-0 / 3-1 / 2-2 split, direct call to _next_question
sep("IND-045")
def mk(name, accept_set):
    return Scored(candidate=Candidate(predicate=name, description=name, accepts=lambda v, s=accept_set: v in s), caught=1, missed=0, false_alarms=0)

# four admissible candidates; unlabelled values v1..v4 split 4-0, 3-1, 2-2
c1 = mk("c1", {"v1", "v2", "v3", "v4"})
c2 = mk("c2", {"v1", "v2", "v3"})
c3 = mk("c3", {"v1", "v2"})
c4 = mk("c4", {"v1"})
admissible45 = [c1, c2, c3, c4]
for value in ["v1", "v2", "v3", "v4"]:
    votes = [s.candidate.accepts(value) for s in admissible45]
    print(f"  {value}: accept={sum(votes)}, reject={len(votes) - sum(votes)}")
q = ExampleInducer()._next_question(admissible45, ["v1", "v2", "v3", "v4"])
print("next_question value:", q.value if q else None, "(expect v3, the 2-2 split)")
print("disagreement:", q.disagreement if q else None, "(expect 1.0)")
print("reason mentions 'eliminates about half':", "eliminates about half" in (q.reason if q else ""))

# IND-046
sep("IND-046")
single = [mk("only", {"v1", "v2", "v3", "v4"})]
q_single = ExampleInducer()._next_question(single, ["v1", "v2"])
print("one admissible candidate -> next_question:", q_single, "(expect None)")

q_no_unlabelled = ExampleInducer()._next_question(admissible45, [])
print("several candidates, no unlabelled -> next_question:", q_no_unlabelled, "(expect None)")

unanimous_candidates = [mk("a", {"v1", "v2"}), mk("b", {"v1", "v2"})]
q_unanimous = ExampleInducer()._next_question(unanimous_candidates, ["v1", "v2"])
print("unanimous survivors -> next_question:", q_unanimous, "(expect None)")

# is_settled property, end to end
one_candidate_labels = [
    Label(1.0, True), Label(2.0, True), Label(3.0, True),
    Label(-1.0, False), Label(-2.0, False), Label(-9.0, False),
]
r_settled = ExampleInducer().generalise("t", "x", one_candidate_labels, unlabelled=())
print("is_settled (best exists, no unlabelled so no question):", r_settled.is_settled, "(expect True)")

# IND-047
sep("IND-047")
labels47 = [Label("A", True), Label("A", False)] * 4
result47 = ExampleInducer().generalise("t", "x", labels47)
print("scored non-empty:", len(result47.scored) > 0)
print("best is None:", result47.best is None)
print("refusal mentions 'may depend on another column':", "may depend on another column" in result47.refusal)

# IND-048
sep("IND-048")
labels48 = leis() + [Label("549300E9PC51EN656011", True)]  # 10 labels: 5 good original + 1 more good + 4 bad = 10, 4 bad... need 20 labels, 6 bad
# Build 20 labels, 6 bad, matching catalog precondition
good20 = [f"GOOD{i:02d}" for i in range(14)]
bad20 = [f"BAD{i:02d}" for i in range(6)]
labels20 = [Label(v, True) for v in good20] + [Label(v, False) for v in bad20]
result20 = ExampleInducer().generalise("exposures", "counterparty_lei", labels20)
best20 = result20.best
print("best found:", best20 is not None)
if best20:
    prov = generalisation_provenance("exposures", "counterparty_lei", best20, labels20)
    print("origin:", prov.origin)
    print("observations:", prov.observations)
    print("mentions 20:", "20 values" in prov.observations[0])
    print("mentions 6:", "6 of them" in prov.observations[0])
    print("mentions catches N of 6:", f"{best20.caught} of 6" in prov.observations[1])
    print("mentions flags none of accepted:", "flags none of the values you accepted" in prov.observations[1])

print("\nDONE")
