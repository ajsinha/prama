"""MIN-025..MIN-045: dependencies.py"""
import random
from prama.mine.sample import Sample
from prama.mine.dependencies import (
    DependencyMiner, InclusionMiner, Dependency, Inclusion,
    dependency_provenance, inclusion_provenance, dependency_identity, inclusion_identity,
    NEAR_KEY_FRACTION, MINIMUM_SUPPORT, MINIMUM_CONDITION_COVERAGE,
)

random.seed(1)

def hdr(cid):
    print(f"\n=== {cid} ===")

dm = DependencyMiner()

# ---------------- MIN-025 ----------------
hdr("MIN-025")
random.seed(10)
counterparties = [f"LEI{i:04d}" for i in range(50)]
lei_to_rating = {lei: random.choice(["AAA", "AA", "A", "BBB", "BB"]) for lei in counterparties}
rows25 = []
for i in range(1000):
    lei = counterparties[i % 50]
    rows25.append({"trade_id": i, "counterparty_lei": lei, "rating": lei_to_rating[lei]})
s25 = Sample.of("trades", rows25)
f25 = dm.mine(s25)
deps25 = [(d.determinant, d.dependent, d.is_exact, d.evidence.support) for d in f25.dependencies]
print("dependencies:", deps25)
print("discarded:", f25.discarded)
has_lei_rating = any(d.determinant == ("counterparty_lei",) and d.dependent == "rating" for d in f25.dependencies)
print("has counterparty_lei->rating:", has_lei_rating)

# ---------------- MIN-026 ----------------
hdr("MIN-026")
random.seed(11)
rows26 = []
for i in range(1000):
    lei = counterparties[i % 50]
    rows26.append({"trade_id": i, "counterparty_lei": lei, "rating": random.choice(["AAA", "AA", "A", "BBB", "BB"])})
s26 = Sample.of("trades", rows26)
f26 = dm.mine(s26)
print("dependencies:", [(d.determinant, d.dependent) for d in f26.dependencies])
print("discarded:", f26.discarded)
has_rating_dep = any(d.dependent == "rating" or "rating" in d.determinant for d in f26.dependencies)
print("has any dependency involving rating:", has_rating_dep)

# ---------------- MIN-027 ----------------
hdr("MIN-027")
random.seed(12)
rows27 = []
for i in range(1000):
    row = {"trade_id": i}
    for j in range(8):
        row[f"col{j}"] = random.choice(["X", "Y", "Z"])
    rows27.append(row)
s27 = Sample.of("trades", rows27)
f27 = dm.mine(s27)
has_trade_id_determinant = any("trade_id" in d.determinant for d in f27.dependencies)
print("any dependency with trade_id as determinant:", has_trade_id_determinant)
print("discarded['near_key_determinant']:", f27.discarded.get("near_key_determinant"))

# ---------------- MIN-028 ----------------
hdr("MIN-028")
def col_with_distinct_fraction(n, frac):
    n_distinct = round(n * frac)
    vals = list(range(n_distinct))
    while len(vals) < n:
        vals.append(random.choice(range(n_distinct)))
    random.shuffle(vals)
    return vals[:n]

random.seed(13)
n = 1000
colA = col_with_distinct_fraction(n, 0.89)
colB = col_with_distinct_fraction(n, 0.90)
depv = [random.choice(["p", "q"]) for _ in range(n)]
rows28 = [{"a": colA[i], "b": colB[i], "dep": depv[i]} for i in range(n)]
s28 = Sample.of("t", rows28)
actual_a = len(set(colA)) / n
actual_b = len(set(colB)) / n
print("actual distinct fraction a,b:", actual_a, actual_b)
is_near_a = dm._is_near_key(s28, ("a",))
is_near_b = dm._is_near_key(s28, ("b",))
print("is_near_key(a):", is_near_a, "is_near_key(b):", is_near_b)
f28 = dm.mine(s28)
print("discarded:", f28.discarded)
a_determinant_deps = [d for d in f28.dependencies if d.determinant == ("a",)]
b_determinant_deps = [d for d in f28.dependencies if d.determinant == ("b",)]
print("a-determinant deps found (searched, may or may not pass support):", len(a_determinant_deps))
print("b-determinant deps found:", len(b_determinant_deps))

# ---------------- MIN-029 ----------------
hdr("MIN-029")
rows29 = []
random.seed(14)
for i in range(1000):
    rows29.append({"record_type": "P", "other": random.choice(["X", "Y"]), "other2": random.choice(["A", "B", "C"])})
s29 = Sample.of("t", rows29)
f29 = dm.mine(s29)
has_record_type = any("record_type" in d.determinant or d.dependent == "record_type" for d in f29.dependencies)
print("any dependency naming record_type:", has_record_type)
print("discarded['constant_column']:", f29.discarded.get("constant_column"))

# ---------------- MIN-030 ----------------
hdr("MIN-030")
random.seed(15)
rows30 = []
for i in range(1000):
    a = random.choice(["a1", "a2", "a3", "a4", "a5"])
    c = "C-" + a  # a -> c holds
    b = random.choice(["b1", "b2"])
    rows30.append({"a": a, "b": b, "c": c})
s30 = Sample.of("t", rows30)
dm2 = DependencyMiner(max_determinant=2)
f30 = dm2.mine(s30)
has_ab_c = any(set(d.determinant) == {"a", "b"} and d.dependent == "c" for d in f30.dependencies)
has_a_c = any(d.determinant == ("a",) and d.dependent == "c" for d in f30.dependencies)
print("has (a,b)->c:", has_ab_c, "has a->c:", has_a_c)
print("discarded['implied']:", f30.discarded.get("implied"))

# ---------------- MIN-031 ----------------
hdr("MIN-031")
random.seed(16)
rows31 = []
for i in range(1000):
    lei = counterparties[i % 50]
    rating = lei_to_rating[lei] if i % 10 < 4 else None  # 600 null (60%)
    rows31.append({"counterparty_lei": lei, "rating": rating})
n_null = sum(1 for r in rows31 if r["rating"] is None)
print("actual null count:", n_null)
s31 = Sample.of("t", rows31)
f31 = dm.mine(s31)
dep31 = [d for d in f31.dependencies if d.determinant == ("counterparty_lei",) and d.dependent == "rating"]
if dep31:
    d = dep31[0]
    print("null_excluded:", d.evidence.null_excluded, "support computed over:", d.evidence.rows_examined - d.evidence.null_excluded)
    print("describe:", d.describe())
    print("evidence describe:", d.evidence.describe())
else:
    print("NOT FOUND", [(x.determinant, x.dependent) for x in f31.dependencies])

# ---------------- MIN-032 ----------------
hdr("MIN-032")
def make_dependency_rows(n, support_frac):
    determinants = [f"D{i}" for i in range(20)]
    det_to_val = {d: f"V{i}" for i, d in enumerate(determinants)}
    rows = []
    n_violate = round(n * (1 - support_frac))
    violate_idx = set(random.sample(range(n), n_violate))
    for i in range(n):
        d = determinants[i % 20]
        if i in violate_idx:
            val = "WRONG"
        else:
            val = det_to_val[d]
        rows.append({"det": d, "dep": val})
    return rows

random.seed(17)
rows32_94 = make_dependency_rows(1000, 0.94)
rows32_96 = make_dependency_rows(1000, 0.96)
s32a = Sample.of("t", rows32_94)
s32b = Sample.of("t", rows32_96)
f32a = dm.mine(s32a)
f32b = dm.mine(s32b)
print("94% support -> found:", [(d.determinant, d.dependent, d.is_exact, round(d.evidence.support,4)) for d in f32a.dependencies])
print("96% support -> found:", [(d.determinant, d.dependent, d.is_exact, round(d.evidence.support,4)) for d in f32b.dependencies])

# ---------------- MIN-033 ----------------
hdr("MIN-033")
rows33 = []
for i in range(100):
    val = "A" if i < 90 else "B"
    rows33.append({"det": "K1", "dep": val})
# need >=200 rows total and other det values to not be near-key; pad with distinct det values w/ consistent dep
for i in range(200):
    rows33.append({"det": f"K{i+2}", "dep": "Z"})
s33 = Sample.of("t", rows33)
f33 = dm.mine(s33)
dep33 = [d for d in f33.dependencies if d.determinant == ("det",) and d.dependent == "dep"]
if dep33:
    d = dep33[0]
    print("supporting (agreeing):", d.evidence.supporting, "violating:", d.evidence.violating)
else:
    print("NOT FOUND", f33.discarded)

# ---------------- MIN-034 ----------------
hdr("MIN-034")
random.seed(18)
instruments = [f"INST{i:03d}" for i in range(30)]
inst_to_issuer = {inst: f"ISSUER{i%10}" for i, inst in enumerate(instruments)}
statuses = [f"S{i}" for i in range(12)]
rows34 = []
for i in range(1200):
    inst = instruments[i % 30]
    rows34.append({"instrument": inst, "issuer": inst_to_issuer[inst], "status": statuses[i % 12]})
s34 = Sample.of("t", rows34)
f34 = dm.mine(s34, conditions=("status",))
global_ok = any(d.determinant == ("instrument",) and d.dependent == "issuer" and d.condition is None for d in f34.dependencies)
conditional_copies = [d for d in f34.dependencies if d.determinant == ("instrument",) and d.dependent == "issuer" and d.condition is not None]
print("global instrument->issuer found:", global_ok)
print("conditional copies count:", len(conditional_copies))
print("discarded['conditional_restates_global']:", f34.discarded.get("conditional_restates_global"))

# ---------------- MIN-035 ----------------
hdr("MIN-035")
random.seed(19)
products = [f"P{i}" for i in range(10)]
rows35 = []
for i in range(1000):
    region = "US" if i < 600 else random.choice(["GB", "DE", "FR"])
    product = products[i % 10]
    if region == "US":
        settlement = 2 if product in products[:5] else 3  # deterministic within US
    else:
        settlement = random.choice([1, 2, 3, 4])  # random elsewhere -> not global
    rows35.append({"product": product, "settlement_days": settlement, "region": region})
s35 = Sample.of("t", rows35)
f35 = dm.mine(s35, conditions=("region",))
cond35 = [d for d in f35.dependencies if d.determinant == ("product",) and d.dependent == "settlement_days" and d.condition == ("region", "US")]
print("conditional deps found:", len(cond35))
if cond35:
    d = cond35[0]
    print("is_exact:", d.is_exact, "render:", d.render())
global35 = [d for d in f35.dependencies if d.determinant == ("product",) and d.dependent == "settlement_days" and d.condition is None]
print("global product->settlement_days found (should be none/approx):", len(global35))

# ---------------- MIN-036 ----------------
hdr("MIN-036")
def build_condition_sample(covering_rows, total, seed):
    random.seed(seed)
    rows = []
    dets = ["d1", "d2", "d3", "d4", "d5"]
    det_to_dep_in_target = {d: f"v{i}" for i, d in enumerate(dets)}
    for i in range(covering_rows):
        d = dets[i % 5]
        rows.append({"cc": "TARGET", "det": d, "dep": det_to_dep_in_target[d]})
    remaining = total - covering_rows
    for i in range(remaining):
        d = random.choice(dets)
        dep = random.choice([f"v{j}" for j in range(5)])  # uncorrelated outside TARGET
        rows.append({"cc": f"other{i % 30}", "det": d, "dep": dep})
    return rows

# case 1: 49 rows, total large enough that % doesn't matter (still <50 rows fails)
rows36_1 = build_condition_sample(49, 2000, seed=20)
s36_1 = Sample.of("t", rows36_1)
f36_1 = dm.mine(s36_1, conditions=("cc",))
print("case1 (49 rows) discarded condition_too_narrow:", f36_1.discarded.get("condition_too_narrow"))
cond36_1 = [d for d in f36_1.dependencies if d.condition and d.condition[1] == "TARGET"]
print("case1 conditional deps for TARGET:", len(cond36_1))

# case 2: 50 rows but 4% of sample -> total = 50/0.04 = 1250
rows36_2 = build_condition_sample(50, 1250, seed=21)
s36_2 = Sample.of("t", rows36_2)
f36_2 = dm.mine(s36_2, conditions=("cc",))
print("case2 (50 rows, 4%) discarded condition_too_narrow:", f36_2.discarded.get("condition_too_narrow"))
cond36_2 = [d for d in f36_2.dependencies if d.condition and d.condition[1] == "TARGET"]
print("case2 conditional deps for TARGET:", len(cond36_2))

# case 3: 50 rows and 6% of sample -> total = 50/0.06 ~ 834 (use 833 -> 50/833=6.0%)
total3 = 833
rows36_3 = build_condition_sample(50, total3, seed=22)
s36_3 = Sample.of("t", rows36_3)
f36_3 = dm.mine(s36_3, conditions=("cc",))
print("case3 coverage:", 50/total3, "discarded condition_too_narrow:", f36_3.discarded.get("condition_too_narrow"))
cond36_3 = [d for d in f36_3.dependencies if d.condition and d.condition[1] == "TARGET"]
print("case3 conditional deps for TARGET:", len(cond36_3))
if cond36_3:
    print("case3 conditional dep detail:", [(d.determinant, d.dependent, d.is_exact) for d in cond36_3])

print(f"\nAll scripts complete\n")
