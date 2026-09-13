"""MIN-037..MIN-045: dependencies.py (conditional completeness, inclusion)"""
import random
from prama.mine.sample import Sample
from prama.mine.dependencies import (
    DependencyMiner, InclusionMiner, dependency_provenance, inclusion_provenance,
)

def hdr(cid):
    print(f"\n=== {cid} ===")

dm = DependencyMiner()

# ---------------- MIN-037 ----------------
hdr("MIN-037")
random.seed(30)
rows37 = []
for i in range(1000):
    country = "US" if i < 600 else random.choice(["GB", "DE", "FR"])
    if country == "US":
        state = random.choice(["CA", "NY", "TX"])
    else:
        state = random.choice(["CA", "NY", None, None])  # null on some non-US rows
    rows37.append({"country": country, "state": state})
s37 = Sample.of("t", rows37)
f37 = dm.mine(s37, conditions=("country",))
comp37 = [d for d in f37.dependencies if d.is_completeness and d.condition == ("country", "US")]
print("completeness findings for US:", len(comp37))
if comp37:
    d = comp37[0]
    print("render:", d.render())
    print("describe:", d.describe())

# ---------------- MIN-038 ----------------
hdr("MIN-038")
random.seed(31)
rows38 = []
for i in range(1000):
    country = random.choice(["US", "GB", "DE"])
    rows38.append({"country": country, "always_present": f"v{i%5}"})  # no nulls at all
s38 = Sample.of("t", rows38)
f38 = dm.mine(s38, conditions=("country",))
comp38 = [d for d in f38.dependencies if d.is_completeness and d.dependent == "always_present"]
print("completeness findings for always_present:", len(comp38))

# ---------------- MIN-039 ----------------
hdr("MIN-039")
# Follow MIN-037's finding to a conditional optionality declaration and generate via derive.
from prama.derive.generator import ControlGenerator
from prama.derive.declaration import AttributeDeclaration, DatasetDeclaration
from prama.semantic.values import Optionality

attribute39 = AttributeDeclaration(
    name="state",
    optionality=Optionality.CONDITIONAL,
    optionality_condition="country = 'US'",
)
decl39 = DatasetDeclaration(
    name="addresses",
    attributes=(attribute39,),
)
gen39 = ControlGenerator()
generation39 = gen39.generate(decl39)
completeness_controls = generation39.by_rule("attribute.completeness")
print("controls generated:", len(completeness_controls))
for c in completeness_controls:
    print("rendered where clause present:", c.control.where is not None)
    print("control to_dict where:", c.to_dict().get("control", {}).get("where") if hasattr(c, "to_dict") else None)
    print(c.control)
print("unsatisfiable:", generation39.unsatisfiable)

# ---------------- MIN-040 ----------------
hdr("MIN-040")
im = InclusionMiner()
random.seed(32)
party_ids = [f"PTY{i:04d}" for i in range(300)]
rows_parties = [{"id": pid} for pid in party_ids]
rows_trades = [{"counterparty_id": random.choice(party_ids)} for _ in range(1000)]
s_parties = Sample.of("parties", rows_parties)
s_trades = Sample.of("trades", rows_trades)
f40 = im.mine(s_trades, s_parties)
print("inclusions:", [(i.left_column, i.right_column, i.is_exact) for i in f40.inclusions])

# ---------------- MIN-041 ----------------
hdr("MIN-041")
random.seed(33)
n = 1000
orphan_values = ["ORPHAN1", "ORPHAN2", "ORPHAN3"]
left_vals = []
for i in range(n):
    if i < round(n * 0.03):
        left_vals.append(orphan_values[i % 3])
    else:
        left_vals.append(random.choice(party_ids))
rows_trades41 = [{"counterparty_id": v} for v in left_vals]
s_trades41 = Sample.of("trades", rows_trades41)
f41 = im.mine(s_trades41, s_parties)
incl41 = [i for i in f41.inclusions if i.left_column == "counterparty_id"]
print("inclusions:", [(i.is_exact, i.orphan_examples, i.evidence.support) for i in incl41])
if incl41:
    print("describe:", incl41[0].describe())

# ---------------- MIN-042 ----------------
hdr("MIN-042")
random.seed(34)
def build_containment(support_frac, n=1000):
    n_target = round(n * support_frac)
    vals = []
    for i in range(n):
        if i < n_target:
            vals.append(random.choice(party_ids))
        else:
            vals.append(f"NOTIN{i}")
    return vals

for frac in (0.89, 0.90):
    vals = build_containment(frac)
    rows = [{"counterparty_id": v} for v in vals]
    s = Sample.of("trades", rows)
    f = im.mine(s, s_parties)
    print(f"containment~{frac}: inclusions found:", len(f.inclusions))

# ---------------- MIN-043 ----------------
hdr("MIN-043")
random.seed(35)
statuses = ["OPEN", "CLOSED", "PENDING"]
rows_status = [{"status": random.choice(statuses)} for _ in range(200)]
s_status = Sample.of("orders", rows_status)
rows_left = [{"order_status": random.choice(statuses)} for _ in range(500)]
s_left = Sample.of("orders_fact", rows_left)
f43 = im.mine(s_left, s_status)
print("inclusions:", [(i.left_column, i.right_column) for i in f43.inclusions])
print("discarded['target_is_not_a_key']:", f43.discarded.get("target_is_not_a_key"))

# ---------------- MIN-044 ----------------
hdr("MIN-044")
random.seed(36)
right_vals_unique = [f"KEY{i}" for i in range(100)]
rows_right44 = [{"id": v} for v in right_vals_unique]
s_right44 = Sample.of("dim", rows_right44)
left_vals44 = []
for i in range(300):
    if i < 100:
        left_vals44.append(f"ORPHAN{i}")  # 100 orphans not in right -> not counted as part of the 103
    else:
        left_vals44.append(right_vals_unique[i % 100])
# ensure left has 103 distinct values total: 100 unique orphans + 100 right values already... let's recompute precisely
left_vals44 = [f"ORPHANX{i}" for i in range(3)] + [right_vals_unique[i % 100] for i in range(100)] + \
              [right_vals_unique[i % 100] for i in range(197)]
print("distinct left values:", len(set(left_vals44)))
rows_left44 = [{"fk": v} for v in left_vals44]
s_left44 = Sample.of("fact", rows_left44)
f44 = im.mine(s_left44, s_right44)
print("inclusions:", [(i.left_column, i.right_column, i.is_exact, i.evidence.support) for i in f44.inclusions])

# ---------------- MIN-045 ----------------
hdr("MIN-045")
random.seed(37)
dim_vals = [f"D{i}" for i in range(1000)]
# introduce 3 duplicate rows
dim_rows = [{"id": v} for v in dim_vals] + [{"id": dim_vals[0]}, {"id": dim_vals[1]}, {"id": dim_vals[2]}]
s_dim45 = Sample.of("dim", dim_rows)
fact_rows45 = [{"fk": random.choice(dim_vals)} for _ in range(500)]
s_fact45 = Sample.of("fact", fact_rows45)
is_key45 = InclusionMiner._is_key(s_dim45, "id")
print("dim has", len(dim_rows), "rows,", len(set(dim_vals)), "distinct; is_key:", is_key45)
f45 = im.mine(s_fact45, s_dim45)
print("inclusions:", [(i.left_column, i.right_column, i.is_exact) for i in f45.inclusions])

print("\nAll scripts complete\n")
