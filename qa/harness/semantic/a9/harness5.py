"""MIN-054..MIN-060"""
import random
import datetime
from prama.mine.sample import Sample, Evidence
from prama.mine.constraints import ConstraintMiner, InvariantKind, Invariant, invariant_provenance, invariant_identity
from prama.mine.dependencies import (
    DependencyMiner, InclusionMiner, Dependency, Inclusion,
    dependency_provenance, inclusion_provenance, dependency_identity, inclusion_identity,
)
from prama.mine.keys import KeyMiner, as_provenance as key_as_provenance, key_identity

def hdr(cid):
    print(f"\n=== {cid} ===")

cm = ConstraintMiner()

# ---------------- MIN-054 ----------------
hdr("MIN-054")
random.seed(50)
rows54 = []
for i in range(300):
    qty = random.uniform(1, 1000)
    date_str = f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}"
    rows54.append({"quantity": qty, "settlement_date_str": date_str})
s54 = Sample.of("t", rows54)
f54 = cm.mine(s54)
has_cross = any(set(i.columns) == {"quantity", "settlement_date_str"} for i in f54.invariants)
print("invariant between quantity and date string:", has_cross)
print("discarded:", f54.discarded)

# ---------------- MIN-055 ----------------
hdr("MIN-055")
random.seed(51)
rows55 = []
for i in range(1000):
    a_val = i if i % 2 == 0 else datetime.date(2024, 1, 1)  # mixed types within one column
    rows55.append({"mixed": a_val, "other_nonnumeric": "s" + str(i % 3)})
# also include unrelated numeric columns that should still be minable
for row, i in zip(rows55, range(1000)):
    row["amount_a"] = float(i)
    row["amount_b"] = float(i) + 5.0  # amount_a <= amount_b always -> real ordering
s55 = Sample.of("t", rows55)
try:
    f55 = cm.mine(s55)
    crashed = False
except Exception as e:
    crashed = True
    print("CRASHED:", repr(e))
if not crashed:
    has_mixed_invariant = any("mixed" in i.columns for i in f55.invariants)
    print("crashed:", crashed)
    print("any invariant involving 'mixed' column:", has_mixed_invariant)
    has_amount_ordering = any(set(i.columns) == {"amount_a", "amount_b"} for i in f55.invariants)
    print("rest of search completed -- amount_a<=amount_b found:", has_amount_ordering)
    print("all invariants:", [i.expression for i in f55.invariants])

# ---------------- MIN-056 ----------------
hdr("MIN-056")
random.seed(52)
rows56 = []
for i in range(300):
    if i < 49:
        left, right = float(i), float(i) + 1.0
    else:
        left, right = None, None
    rows56.append({"sparse_a": left, "sparse_b": right})
s56 = Sample.of("t", rows56)
f56 = cm.mine(s56)
has_sparse = any(set(i.columns) == {"sparse_a", "sparse_b"} for i in f56.invariants)
print("invariant found for sparse pair (49 applicable rows):", has_sparse)
print("discarded['too_sparse']:", f56.discarded.get("too_sparse"))

# ---------------- MIN-057 ----------------
hdr("MIN-057")
def make_ordering_rows(n, support_frac, seed):
    random.seed(seed)
    n_violate = round(n * (1 - support_frac))
    violate_idx = set(random.sample(range(n), n_violate))
    rows = []
    for i in range(n):
        left = float(i)
        if i in violate_idx:
            right = left - 1.0  # violates left <= right
        else:
            right = left + 1.0
        rows.append({"lo": left, "hi": right})
    return rows

rows57_96 = make_ordering_rows(1000, 0.96, 53)
rows57_98 = make_ordering_rows(1000, 0.98, 54)
s57_96 = Sample.of("t", rows57_96)
s57_98 = Sample.of("t", rows57_98)
f57_96 = cm.mine(s57_96)
f57_98 = cm.mine(s57_98)
has96 = any(set(i.columns) == {"lo", "hi"} for i in f57_96.invariants)
has98 = any(set(i.columns) == {"lo", "hi"} for i in f57_98.invariants)
print("96% support ordering found:", has96)
print("98% support ordering found:", has98)

# ---------------- MIN-058 ----------------
hdr("MIN-058")
random.seed(55)
rows58 = []
for i in range(300):
    row = {f"n{j}": random.uniform(0, 1000) for j in range(12)}
    rows58.append(row)
s58 = Sample.of("t", rows58)
f58 = cm.mine(s58)
print("skipped:", f58.skipped)

# ---------------- MIN-059 ----------------
hdr("MIN-059")
# a caveated sample: partitioned, one partition, small
random.seed(56)
rows59 = []
for i in range(300):
    rows59.append({
        "business_date": "2024-01-01",
        "trade_id": i,
        "counterparty_lei": f"LEI{i % 30:04d}",
        "rating": f"R{i % 30}",
        "quantity": float(i + 1),
        "price": 2.0 + (i % 5) * 0.01,
    })
for row, i in zip(rows59, range(300)):
    row["notional"] = row["quantity"] * row["price"]
s59 = Sample.of("trades", rows59, partition_column="business_date")

km59 = KeyMiner()
dm59 = DependencyMiner()
cm59 = ConstraintMiner()
kf59 = km59.mine(s59)
c59 = next(c for c in kf59.candidates if c.columns == ("trade_id",))
prov_key = key_as_provenance("trades", c59, s59)
print("KEY provenance origin:", prov_key.origin, "rule:", prov_key.rule)
print("KEY observations[0] (evidence sentence):", prov_key.observations[0])
print("KEY observations rest (caveats):", prov_key.observations[1:])

df59 = dm59.mine(s59)
dep59 = next((d for d in df59.dependencies if d.determinant == ("counterparty_lei",) and d.dependent == "rating"), None)
print("dependency found:", dep59 is not None)
if dep59:
    prov_dep = dependency_provenance("trades", dep59, s59)
    print("DEP provenance origin:", prov_dep.origin, "rule:", prov_dep.rule)
    print("DEP observations[0]:", prov_dep.observations[0])
    print("DEP observations rest:", prov_dep.observations[1:])

cf59 = cm59.mine(s59)
inv59 = next((i for i in cf59.invariants if i.kind == InvariantKind.IDENTITY), None)
print("invariant found:", inv59.expression if inv59 else None)
if inv59:
    prov_inv = invariant_provenance("trades", inv59, s59)
    print("INV provenance origin:", prov_inv.origin, "rule:", prov_inv.rule)
    print("INV observations:", prov_inv.observations)

# inclusion
rows_left59 = [{"counterparty_id": f"LEI{i % 30:04d}"} for i in range(300)]
rows_right59 = [{"id": f"LEI{i:04d}"} for i in range(30)]
s_left59 = Sample.of("trades", rows_left59)
s_right59 = Sample.of("parties", rows_right59)
im59 = InclusionMiner()
inf59 = im59.mine(s_left59, s_right59)
incl59 = inf59.inclusions[0] if inf59.inclusions else None
print("inclusion found:", incl59 is not None)
if incl59:
    prov_incl = inclusion_provenance(incl59, s_left59)
    print("INCL provenance origin:", prov_incl.origin, "rule:", prov_incl.rule)
    print("INCL observations:", prov_incl.observations)

# ---------------- MIN-060 ----------------
hdr("MIN-060")
random.seed(57)
rows60 = []
statuses60 = [f"S{i}" for i in range(10)]
instruments60 = [f"INST{i:03d}" for i in range(30)]
inst_to_issuer60 = {inst: f"ISSUER{i%8}" for i, inst in enumerate(instruments60)}
for i in range(1200):
    inst = instruments60[i % 30]
    rows60.append({"instrument": inst, "issuer": inst_to_issuer60[inst], "status": statuses60[i % 10]})
s60 = Sample.of("t", rows60)
dm60 = DependencyMiner()
f60 = dm60.mine(s60, conditions=("status",))
global_dep = next(d for d in f60.dependencies if d.determinant == ("instrument",) and d.dependent == "issuer" and d.condition is None)
cond_deps = [d for d in f60.dependencies if d.determinant == ("instrument",) and d.dependent == "issuer" and d.condition is not None]
print("global dep id:", dependency_identity("t", global_dep))
if cond_deps:
    cd = cond_deps[0]
    print("conditional dep id:", dependency_identity("t", cd))
    print("ids equal (global vs conditional):", dependency_identity("t", global_dep) == dependency_identity("t", cd))
else:
    print("NOTE: no conditional dependency variant found in this sample; constructing one manually for identity test")
    manual_cond = Dependency(determinant=("instrument",), dependent="issuer", condition=("status", "S0"), evidence=global_dep.evidence)
    print("conditional dep id:", dependency_identity("t", manual_cond))
    print("ids equal (global vs conditional):", dependency_identity("t", global_dep) == dependency_identity("t", manual_cond))

# two inclusions from one column to two targets
im60 = InclusionMiner()
random.seed(58)
left_vals60 = [f"V{i % 100}" for i in range(1000)]
right1 = [{"id": f"V{i}"} for i in range(100)]
right2 = [{"code": f"V{i}"} for i in range(100)]
s_left60 = Sample.of("fact", [{"fk": v} for v in left_vals60])
s_right1 = Sample.of("dim1", right1)
s_right2 = Sample.of("dim2", right2)
f60a = im60.mine(s_left60, s_right1)
f60b = im60.mine(s_left60, s_right2)
i1 = f60a.inclusions[0]
i2 = f60b.inclusions[0]
id1 = inclusion_identity(i1)
id2 = inclusion_identity(i2)
print("inclusion1 id:", id1)
print("inclusion2 id:", id2)
print("distinct:", id1 != id2)

print("\nAll scripts complete\n")
