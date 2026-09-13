"""Harness for ER-001..ER-028 against src/prama/er/match.py"""
import math
import random
import sys

from prama.er.match import (
    Comparison, Judgement, Decision, BlockingKey, Resolution, Resolver,
    estimate_u, estimate_m, expectation_maximisation,
    exact, normalised, similar, _normalise_name, _trigram_similarity, _trigrams,
    _clamp, EPSILON, MATCH_THRESHOLD, NON_MATCH_THRESHOLD,
)

results = {}

def report(id_, ok, observed):
    results[id_] = (ok, observed)
    print(f"{id_}: {'PASS' if ok else 'FAIL'} :: {observed}")

# ---------------- ER-001 ----------------
c1 = Comparison(field="surname", compare=exact, m=0.9, u=0.1)
c2 = Comparison(field="surname", compare=exact, m=0.9, u=0.001)
w1 = c1.agreement_weight
w2 = c2.agreement_weight
ok = math.isclose(w1, 3.169925, abs_tol=0.01) and math.isclose(w2, 9.8137, abs_tol=0.01)
report("ER-001", ok, f"w(m=.9,u=.1)={w1:.6f}, w(m=.9,u=.001)={w2:.6f}")

# ---------------- ER-002 ----------------
c = Comparison(field="x", compare=exact, m=0.9, u=0.1)
dw = c.disagreement_weight
c0 = Comparison(field="x", compare=exact, m=0.5, u=0.5)
ok = math.isclose(dw, -3.169925, abs_tol=0.01) and c0.agreement_weight == 0.0 and c0.disagreement_weight == 0.0
report("ER-002", ok, f"disagreement_weight(m=.9,u=.1)={dw:.6f}; m=.5,u=.5 -> agree={c0.agreement_weight}, disagree={c0.disagreement_weight}")

# ---------------- ER-003 ----------------
c = Comparison(field="x", compare=exact, m=1.0, u=0.0)
try:
    aw = c.agreement_weight
    dw = c.disagreement_weight
    ok = math.isfinite(aw) and math.isfinite(dw)
    observed = f"agreement_weight={aw}, disagreement_weight={dw}"
except Exception as e:
    ok = False
    observed = f"raised {type(e).__name__}: {e}"
report("ER-003", ok, observed)

# ---------------- ER-004 ----------------
c = Comparison(field="lei", compare=exact, m=0.9, u=0.1)
left = {"id": "1"}  # missing lei entirely
right = {"id": "2", "lei": "GB00B03MLX29"}
w = c.weigh(left, right)
ok = w is None
report("ER-004", ok, f"weigh(missing lei, present lei) = {w!r}")

# ---------------- ER-005 ----------------
c = Comparison(field="lei", compare=exact, m=0.9, u=0.1)
left1 = {"lei": ""}
right1 = {"lei": "GB00B03MLX29"}
w1 = c.weigh(left1, right1)
left2 = {"lei": ""}
right2 = {"lei": ""}
w2 = c.weigh(left2, right2)
ok = w1 is None and w2 is None
report("ER-005", ok, f"weigh('' vs value)={w1!r}, weigh('' vs '')={w2!r}")

# ---------------- ER-006 ----------------
c = Comparison(field="x", compare=exact, m=0.5, u=0.5)
left = {"x": "ABC"}
right = {"x": "abc"}
a = c.agrees(left, right)
ok = a is True and not (c.agreement_weight > 0)
report("ER-006", ok, f"agrees={a!r}, weight={c.agreement_weight}, weight>0 is {c.agreement_weight > 0}")

# ---------------- ER-007 ----------------
fields7 = ["a", "b", "c", "d", "e", "f", "g"]
comparisons7 = [Comparison(field=f, compare=exact, m=0.9, u=0.1) for f in fields7]
left7 = {"id": "L", "a": "1", "b": "1", "c": "1", "d": "1", "e": "1"}  # f,g missing
right7 = {"id": "R", "a": "1", "b": "1", "c": "1", "d": "1", "e": "1"}  # f,g missing on both -> uninformative
resolver7 = Resolver(comparisons7, [])
j7 = resolver7.judge(left7, right7)
desc7 = j7.describe()
ok = (len(j7.contributions) == 5 and len(j7.uninformative) == 2
      and set(j7.uninformative) == {"f", "g"}
      and math.isclose(j7.score, sum(w for _, w in j7.contributions))
      and "less evidence than it looks like" in desc7)
report("ER-007", ok, f"contributions={len(j7.contributions)}, uninformative={j7.uninformative}, score={j7.score:.4f}, describe={desc7!r}")

# ---------------- ER-008 ----------------
def make_score_comparison(target_score, agree):
    if agree:
        u = 0.01
        m = u * (2 ** target_score)
        assert EPSILON < m < 1 - EPSILON, m
        comp = Comparison(field="x", compare=lambda a, b: True, m=m, u=u)
        computed = comp.agreement_weight
    else:
        u = 0.5
        one_minus_m = (1 - u) * (2 ** target_score)
        m = 1 - one_minus_m
        assert EPSILON < m < 1 - EPSILON, m
        comp = Comparison(field="x", compare=lambda a, b: False, m=m, u=u)
        computed = comp.disagreement_weight
    return comp, computed

cases8 = [(4.0, True), (3.9, True), (-2.0, False), (-2.1, False)]
expected_decisions = [Decision.MATCH, Decision.REVIEW, Decision.NON_MATCH, Decision.NON_MATCH]
observed8 = []
ok8 = True
for (target, agree), exp_dec in zip(cases8, expected_decisions):
    comp, computed = make_score_comparison(target, agree)
    resolver = Resolver([comp], [])
    j = resolver.judge({"id": "L", "x": "v"}, {"id": "R", "x": "v"})
    observed8.append(f"target={target} computed_weight={computed:.4f} score={j.score:.4f} decision={j.decision.value}")
    if j.decision is not exp_dec:
        ok8 = False
report("ER-008", ok8, "; ".join(observed8))

# ---------------- ER-009 ----------------
# Build 3 comparisons with controllable per-pair scores using a shared 'group' field
def cmp_from_group(field_name, agree_groups):
    def fn(a, b):
        return a == b
    return Comparison(field=field_name, compare=fn, m=0.95, u=0.05)

comparisons9 = [Comparison(field=f"f{i}", compare=exact, m=0.95, u=0.05) for i in range(6)]
records9 = [
    {"id": "A", "f0": "1", "f1": "1", "f2": "1", "f3": "1", "f4": "1", "f5": "1"},  # will match B on all -> high score
    {"id": "B", "f0": "1", "f1": "1", "f2": "1", "f3": "1", "f4": "1", "f5": "1"},
    {"id": "C", "f0": "1", "f1": "1", "f2": "9", "f3": "9", "f4": "1", "f5": "9"},  # partial agree with A -> review band
    {"id": "D", "f0": "9", "f1": "9", "f2": "9", "f3": "9", "f4": "9", "f5": "9"},  # disagrees with A on everything -> non-match
]
blocking9 = [BlockingKey(name="all", of=lambda r: "x")]
resolver9 = Resolver(comparisons9, blocking9)
res9 = resolver9.resolve(records9)
scores_matches = [j.score for j in res9.matches]
scores_review = [j.score for j in res9.review]
sorted_ok = scores_matches == sorted(scores_matches, reverse=True) and scores_review == sorted(scores_review, reverse=True)
non_match_pairs = {(j.left, j.right) for j in list(res9.matches) + list(res9.review)}
ok9 = len(res9.matches) >= 1 and len(res9.review) >= 1 and sorted_ok
report("ER-009", ok9, f"matches={[(j.left,j.right,round(j.score,2)) for j in res9.matches]}, review={[(j.left,j.right,round(j.score,2)) for j in res9.review]}, sorted_ok={sorted_ok}")

# ---------------- ER-010 ----------------
rng10 = random.Random(42)
postcodes = [f"PC{i%50}" for i in range(1000)]
rng10.shuffle(postcodes)
records10 = [{"id": str(i), "postcode": postcodes[i], "name": f"name{i%50}"} for i in range(1000)]
comparisons10 = [Comparison(field="name", compare=exact, m=0.9, u=0.1)]
blocking10 = [BlockingKey(name="postcode", of=lambda r: r["postcode"])]
resolver10 = Resolver(comparisons10, blocking10)
res10 = resolver10.resolve(records10)
total_possible_expected = 1000 * 999 // 2
ok10a = res10.total_possible == total_possible_expected and res10.compared < res10.total_possible and res10.reduction > 0.9
# empty population
res10_empty = resolver10.resolve([])
ok10b = res10_empty.total_possible == 0 and res10_empty.reduction == 0.0
ok10 = ok10a and ok10b
report("ER-010", ok10, f"compared={res10.compared}, total_possible={res10.total_possible}, reduction={res10.reduction:.6f}; empty: total_possible={res10_empty.total_possible}, reduction={res10_empty.reduction}")

# ---------------- ER-011 ----------------
records11 = [
    {"id": "A", "k1": "same", "k2": "same"},
    {"id": "B", "k1": "same", "k2": "same"},
    {"id": "C", "k1": "other", "k2": "other2"},
]
blocking11 = [
    BlockingKey(name="k1", of=lambda r: r["k1"]),
    BlockingKey(name="k2", of=lambda r: r["k2"]),
]
comparisons11 = [Comparison(field="k1", compare=exact, m=0.9, u=0.1)]
resolver11 = Resolver(comparisons11, blocking11)
res11 = resolver11.resolve(records11)
ok11 = (res11.compared == 1 and res11.by_key["k1"] == 1 and res11.by_key["k2"] == 1
        and (res11.unique_by_key["k1"] + res11.unique_by_key["k2"] == 1))
report("ER-011", ok11, f"compared={res11.compared}, by_key={dict(res11.by_key)}, unique_by_key={dict(res11.unique_by_key)}")

# ---------------- ER-012 ----------------
records12 = [
    {"id": "A", "k1": "same"},
    {"id": "B", "k1": "same"},
]
blocking12 = [
    BlockingKey(name="k1", of=lambda r: r["k1"]),
    BlockingKey(name="dead", of=lambda r: None),
]
comparisons12 = [Comparison(field="k1", compare=exact, m=0.9, u=0.1)]
resolver12 = Resolver(comparisons12, blocking12)
res12 = resolver12.resolve(records12)
desc12 = res12.describe()
ok12 = res12.useless_keys == ("dead",) and "dead" in desc12 and "usually means the key is wrong" in desc12
report("ER-012", ok12, f"useless_keys={res12.useless_keys}, describe={desc12!r}")

# ---------------- ER-013 ----------------
records13 = [
    {"id": "A", "k1": "same", "k2": "same"},
    {"id": "B", "k1": "same", "k2": "same"},
]
blocking13 = [
    BlockingKey(name="k1", of=lambda r: r["k1"]),
    BlockingKey(name="k2", of=lambda r: r["k2"]),  # finds exact same pair, fully redundant
]
comparisons13 = [Comparison(field="k1", compare=exact, m=0.9, u=0.1)]
resolver13 = Resolver(comparisons13, blocking13)
res13 = resolver13.resolve(records13)
ok13 = ("k2" in res13.redundant_keys and "k2" not in res13.useless_keys)
report("ER-013", ok13, f"redundant_keys={res13.redundant_keys}, useless_keys={res13.useless_keys}, by_key={dict(res13.by_key)}, unique_by_key={dict(res13.unique_by_key)}")

# ---------------- ER-014 ----------------
records14 = [
    {"id": "A", "postcode": ""},
    {"id": "B", "postcode": ""},
    {"id": "C", "postcode": ""},
]
blocking14 = [BlockingKey(name="postcode", of=lambda r: r["postcode"])]
comparisons14 = [Comparison(field="postcode", compare=exact, m=0.9, u=0.1)]
resolver14 = Resolver(comparisons14, blocking14)
res14 = resolver14.resolve(records14)
ok14 = res14.compared == 0 and res14.by_key["postcode"] == 0
report("ER-014", ok14, f"compared={res14.compared}, by_key={dict(res14.by_key)}")

# ---------------- ER-015 ----------------
rng15 = random.Random(123)
surname_pool = [f"Surname{i}" for i in range(200)]
records15 = []
for i in range(1000):
    if rng15.random() < 0.1:
        s = "CommonSurname"  # designed so random pairs agree ~1% of time (0.1*0.1 = 1%)
    else:
        s = rng15.choice(surname_pool)
    records15.append({"id": str(i), "surname": s})
comp15 = Comparison(field="surname", compare=exact, m=0.9, u=0.1)
u_a = estimate_u(records15, comp15, sample=5000, seed=7)
u_b = estimate_u(records15, comp15, sample=5000, seed=7)
u_c = estimate_u(records15, comp15, sample=5000, seed=99)
u_two = estimate_u(records15[:1], comp15, sample=5000, seed=7)  # <2 records
ok15 = (math.isclose(u_a, 0.01, abs_tol=0.02) and u_a == u_b and abs(u_a - u_c) < 0.03 and u_two == 0.5)
report("ER-015", ok15, f"seed7={u_a:.4f}, seed7-repeat={u_b:.4f}, seed99={u_c:.4f}, <2 records={u_two}")

# ---------------- ER-016 ----------------
comp16 = Comparison(field="lei", compare=exact, m=0.9, u=0.1)
m_empty = estimate_m([], comp16)
pairs_missing = [({"lei": ""}, {"lei": ""}) for _ in range(10)]
m_missing = estimate_m(pairs_missing, comp16)
ok16 = m_empty == 0.9 and m_missing == 0.9
report("ER-016", ok16, f"estimate_m([])={m_empty}, estimate_m(all-missing)={m_missing}")

# ---------------- ER-017 ----------------
comparisons17 = [Comparison(field="x", compare=exact, m=0.5, u=0.5)]
pairs17 = [
    ({"x": "a"}, {"x": "a"}),
    ({"x": "a"}, {"x": "b"}),
    ({"x": "b"}, {"x": "b"}),
    ({"x": "c"}, {"x": "d"}),
] * 20
result17 = expectation_maximisation(comparisons17, pairs17, rounds=20)
c17 = result17[0]
ok17 = (c17.m != 0.5 or c17.u != 0.5) and c17.agreement_weight != 0.0
report("ER-017", ok17, f"m={c17.m:.4f}, u={c17.u:.4f}, agreement_weight={c17.agreement_weight:.4f}")

# ---------------- ER-018 ----------------
rng18 = random.Random(2026)
TRUE_M = {"name": 0.9, "dob": 0.85, "address": 0.6}
TRUE_U = {"name": 0.05, "dob": 0.02, "address": 0.1}
DUP_RATE = 0.3

def gen_pair18():
    is_match = rng18.random() < DUP_RATE
    rec = {}
    for field in TRUE_M:
        p = TRUE_M[field] if is_match else TRUE_U[field]
        agree = rng18.random() < p
        rec[field] = agree
    left = {f: ("V1" if not rec[f] else "SAME") for f in TRUE_M}
    right = {f: ("SAME" if rec[f] else "V2") for f in TRUE_M}
    return left, right, is_match

pairs18 = []
labels18 = []
for _ in range(4000):
    l, r, is_match = gen_pair18()
    pairs18.append((l, r))
    labels18.append(is_match)

comparisons18 = [Comparison(field=f, compare=exact, m=0.5, u=0.5) for f in TRUE_M]
result18 = expectation_maximisation(comparisons18, pairs18, rounds=30)
ok18 = True
detail18 = []
for c in result18:
    tm, tu = TRUE_M[c.field], TRUE_U[c.field]
    detail18.append(f"{c.field}: recovered m={c.m:.3f} u={c.u:.3f} (true m={tm}, u={tu})")
    if not (abs(c.m - tm) < 0.1 and abs(c.u - tu) < 0.1 and c.m > c.u):
        ok18 = False
report("ER-018", ok18, "; ".join(detail18))

# ---------------- ER-019 ----------------
comparisons19 = [Comparison(field="x", compare=exact, m=0.9, u=0.1)]
result19 = expectation_maximisation(comparisons19, [], rounds=20)
c19 = result19[0]
ok19 = c19.m == 0.9 and c19.u == 0.1
report("ER-019", ok19, f"m={c19.m}, u={c19.u} (input was m=0.9,u=0.1)")

# ---------------- ER-020 ----------------
comparisons20 = [
    Comparison(field="present", compare=exact, m=0.7, u=0.2),
    Comparison(field="nullfield", compare=exact, m=0.7, u=0.2),
]
pairs20 = [({"present": "a", "nullfield": None}, {"present": "a", "nullfield": None})] * 20 + \
          [({"present": "b", "nullfield": None}, {"present": "c", "nullfield": None})] * 20
result20 = expectation_maximisation(comparisons20, pairs20, rounds=20)
null_comp = [c for c in result20 if c.field == "nullfield"][0]
ok20 = null_comp.m == 0.7 and null_comp.u == 0.2
report("ER-020", ok20, f"nullfield m={null_comp.m}, u={null_comp.u} (initial m=0.7, u=0.2)")

# ---------------- ER-021 ----------------
rng21 = random.Random(555)
# Families: siblings share both first and last name together (correlated), creating
# conditional-dependence between the two fields.
families = [(f"First{i}", f"Last{i}") for i in range(50)]
def gen_pair21():
    is_match = rng21.random() < 0.3
    if is_match:
        fam = rng21.choice(families)
        first_agree = True
        last_agree = True
    else:
        # non-match pair: sometimes both from same family (siblings) -> correlated agreement
        if rng21.random() < 0.2:
            fam = rng21.choice(families)
            first_agree = rng21.random() < 0.3  # elevated vs base rate due to shared family naming
            last_agree = True  # siblings share last name -> correlated with first-name draw
        else:
            fam = rng21.choice(families)
            first_agree = rng21.random() < 0.02
            last_agree = rng21.random() < 0.02
    left = {"first": fam[0] if first_agree else "OTHERFIRST", "last": fam[1] if last_agree else "OTHERLAST"}
    right = {"first": fam[0], "last": fam[1]}
    return left, right, is_match

pairs21 = []
labels21 = []
for _ in range(4000):
    l, r, is_match = gen_pair21()
    pairs21.append((l, r))
    labels21.append(is_match)

comp_first = Comparison(field="first", compare=exact, m=0.5, u=0.5)
comp_last = Comparison(field="last", compare=exact, m=0.5, u=0.5)
result21 = expectation_maximisation([comp_first, comp_last], pairs21, rounds=30)

# ground truth u computed directly from labelled non-match pairs
def true_u(field):
    agree = total = 0
    for (l, r), is_match in zip(pairs21, labels21):
        if is_match:
            continue
        total += 1
        agree += 1 if l[field] == r[field] else 0
    return agree / total if total else None

true_u_first = true_u("first")
true_u_last = true_u("last")
em_u = {c.field: c.u for c in result21}
# Because first/last co-vary (siblings), EM (which assumes independence) is expected
# to mis-estimate u for 'first' upward relative to the true labelled non-match rate,
# since some of that correlated agreement gets attributed as if independent.
bias_first = em_u["first"] - true_u_first
detail21 = f"true_u(first)={true_u_first:.4f}, EM u(first)={em_u['first']:.4f}, bias={bias_first:+.4f}; true_u(last)={true_u_last:.4f}, EM u(last)={em_u['last']:.4f}"
ok21 = abs(bias_first) > 0.01  # demonstrable bias exists due to violated independence
report("ER-021", ok21, detail21)

# ---------------- ER-022 ----------------
n1, n2, n3 = "ACME Ltd.", "Acme Limited", "ACME Holdings Group"
norm1, norm2, norm3 = _normalise_name(n1), _normalise_name(n2), _normalise_name(n3)
r12 = normalised(n1, n2)
r13 = normalised(n1, n3)
r23 = normalised(n2, n3)
ok22 = r12 is True  # first two agree
observed22 = f"normalised({n1!r})={norm1!r}, normalised({n2!r})={norm2!r}, normalised({n3!r})={norm3!r}; (1,2)={r12}, (1,3)={r13}, (2,3)={r23}"
report("ER-022", ok22, observed22)

# ---------------- ER-023 ----------------
na, nb = "Group Holdings Ltd", "Co Limited"
norm_a, norm_b = _normalise_name(na), _normalise_name(nb)
result23 = normalised(na, nb)
ok23 = norm_a == "" and norm_b == "" and result23 is True
report("ER-023", ok23, f"normalise({na!r})={norm_a!r}, normalise({nb!r})={norm_b!r}, normalised(...)={result23}")

# ---------------- ER-024 ----------------
t_empty_empty = _trigrams("")
t_a = _trigrams("a")
sim_ee = _trigram_similarity("", "")
sim_aa = _trigram_similarity("a", "a")
sim_ea = _trigram_similarity("", "a")
branch_ee = "fallback" if (not t_empty_empty or not t_empty_empty) else "real"
branch_ea = "fallback" if (not t_empty_empty or not t_a) else "real"
ok24 = sim_ee == 1.0 and sim_aa == 1.0 and sim_ea == 0.0
observed24 = (f"trigrams('')={t_empty_empty!r} trigrams('a')={t_a!r}; "
              f"sim('','')={sim_ee} (branch={branch_ee}), sim('a','a')={sim_aa}, sim('','a')={sim_ea} (branch={branch_ea})")
report("ER-024", ok24, observed24)

# ---------------- ER-025 ----------------
e1 = exact(" gb00b03mlx29 ", "GB00B03MLX29")
e2 = exact(1, "1")
ok25 = e1 is True and e2 is True
report("ER-025", ok25, f"exact(' gb00b03mlx29 ','GB00B03MLX29')={e1}, exact(1,'1')={e2}")

# ---------------- ER-026 ----------------
comparisons26 = [Comparison(field="x", compare=exact, m=0.95, u=0.05)]
records26 = [
    {"id": "A", "x": "1"},
    {"id": "B", "x": "1"},  # A-B agree -> match
    {"id": "C", "x": "9"},  # B-C: need B,C to also match via a different comparison
]
# Design: A matches B (share x=1), B matches C via a second field y, A does not match C.
# Each record carries only the field relevant to its neighbour so that the field
# absent for a pair is genuinely missing (uninformative), not a disagreement that
# would cancel out the agreement on the other field.
comparisons26 = [
    Comparison(field="x", compare=exact, m=0.98, u=0.02),
    Comparison(field="y", compare=exact, m=0.98, u=0.02),
]
records26 = [
    {"id": "A", "x": "1"},           # shares x with B; no y
    {"id": "B", "x": "1", "y": "8"},  # shares x with A, y with C
    {"id": "C", "y": "8"},           # shares y with B; no x -> A,C share nothing
]
blocking26 = [BlockingKey(name="all", of=lambda r: "same")]
resolver26 = Resolver(comparisons26, blocking26)
res26 = resolver26.resolve(records26)
match_pairs = {frozenset((j.left, j.right)) for j in res26.matches}
review_pairs = {frozenset((j.left, j.right)) for j in res26.review}
ab_match = frozenset(("A", "B")) in match_pairs
bc_match = frozenset(("B", "C")) in match_pairs
ac_not_match = frozenset(("A", "C")) not in match_pairs
no_cluster_attr = not hasattr(res26, "clusters") and not hasattr(res26, "entities")
ok26 = ab_match and bc_match and ac_not_match and len(res26.matches) == 2 and no_cluster_attr
report("ER-026", ok26, f"matches={[(j.left,j.right,round(j.score,2)) for j in res26.matches]}, review={[(j.left,j.right,round(j.score,2)) for j in res26.review]}, no clustering attr present={no_cluster_attr}")

# ---------------- ER-027 ----------------
comparisons27 = [Comparison(field="x", compare=exact, m=0.9, u=0.1)]
resolver27 = Resolver(comparisons27, [])
left27a = {"x": "1"}  # no 'id' key
right27a = {"x": "1"}
j27a = resolver27.judge(left27a, right27a)
left27b = {"x": "1", "party_id": "P1"}
right27b = {"x": "1", "party_id": "P2"}
j27b = resolver27.judge(left27b, right27b, identity="party_id")
ok27 = j27a.left == "?" and j27a.right == "?" and j27b.left == "P1" and j27b.right == "P2"
report("ER-027", ok27, f"no-id: left={j27a.left!r} right={j27a.right!r}; party_id: left={j27b.left!r} right={j27b.right!r}")

# ---------------- ER-028 ----------------
j28a = Judgement(left="A", right="B", score=5.0, decision=Decision.MATCH, contributions=(("x", 5.0),))
j28b = Judgement(left="C", right="D", score=1.0, decision=Decision.REVIEW, contributions=(("x", 1.0),))
res28 = Resolution(
    matches=(j28a,),
    review=(j28b,),
    compared=10,
    total_possible=100,
    by_key={"k1": 0, "k2": 5},
    unique_by_key={"k1": 0, "k2": 0},
)
desc28 = res28.describe()
ok28 = ("1 matches" in desc28 and "1 for review" in desc28 and "10" in desc28
        and "90.00%" in desc28 and "k1" in desc28 and "k2" in desc28
        and "wrong rather than that there is" in desc28
        and "redundant rather than wrong" in desc28)
report("ER-028", ok28, desc28)

print("\n--- SUMMARY ---")
for k, (ok, obs) in results.items():
    print(k, "PASS" if ok else "FAIL")
