"""MIN-001..MIN-024: sample.py and keys.py"""
import random
import uuid as uuidlib

from prama.mine.sample import Sample, Evidence, MINIMUM_ROWS, REPRESENTATIVE_FRACTION
from prama.mine.keys import (
    KeyMiner, KeyFindings, Candidate, as_provenance, key_identity,
    _is_continuous, _is_surrogate, APPROXIMATE_THRESHOLD, MAXIMUM_NULL_FRACTION,
)
from prama.core.provenance import Origin
from prama.propose.queue import ProposalQueue
from prama.propose.proposal import Proposal

random.seed(42)

def hdr(cid):
    print(f"\n=== {cid} ===")

# ---------------- MIN-001 ----------------
hdr("MIN-001")
def make_rows(n, ncols=3):
    return [{"c0": i, "c1": f"v{i}", "c2": i % 7} for i in range(n)]

s199 = Sample.of("t", make_rows(199))
s200 = Sample.of("t", make_rows(200))
km = KeyMiner()
f199 = km.mine(s199)
f200 = km.mine(s200)
print("199 rows: candidates=", f199.candidates, "skipped=", f199.skipped)
print("200 rows: candidates=", [c.columns for c in f200.candidates], "skipped=", f200.skipped)

# ---------------- MIN-002 ----------------
hdr("MIN-002")
rows = [{"business_date": "2024-01-01", "x": i} for i in range(500)]
samp = Sample.of("t", rows, total_rows=4_000_000, partition_column="business_date")
caveats = samp.caveats()
print("caveats:", caveats)

# ---------------- MIN-003 ----------------
hdr("MIN-003")
rows3 = [{"business_date": f"2024-01-{(i%10)+1:02d}", "x": i} for i in range(5000)]
samp3 = Sample.of("t", rows3, total_rows=5000, partition_column="business_date")
print("coverage:", samp3.coverage, "partitions_seen:", samp3.partitions_seen, "size:", samp3.size)
print("caveats:", samp3.caveats())

# ---------------- MIN-004 ----------------
hdr("MIN-004")
rows4 = [{"business_date": "2024-01-01", "account_id": i} for i in range(300)]
samp4 = Sample.of("t", rows4, partition_column="business_date")
f4 = km.mine(samp4)
print("candidates:", [(c.columns, c.evidence.caveats) for c in f4.candidates])

# ---------------- MIN-005 ----------------
hdr("MIN-005")
rows5 = [{"account_id": i} for i in range(300)]
samp5 = Sample.of("t", rows5, partition_column="")
print("partitions_seen:", samp5.partitions_seen, "spans_one_partition:", samp5.spans_one_partition)
print("caveats:", samp5.caveats())

# ---------------- MIN-006 ----------------
hdr("MIN-006")
samp6 = Sample.of("t", make_rows(300), total_rows=None)
print("coverage:", samp6.coverage, "is_representative:", samp6.is_representative)
print("caveats:", samp6.caveats())

# ---------------- MIN-007 ----------------
hdr("MIN-007")
for frac, total in [(0.89, None), (0.90, None), (1.20, None)]:
    size = 1000
    total_rows = int(size / frac)
    s = Sample.of("t", make_rows(size), total_rows=total_rows)
    print(f"frac~{frac}: coverage={s.coverage:.4f} is_representative={s.is_representative}")

# ---------------- MIN-008 ----------------
hdr("MIN-008")
ev8 = Evidence(rows_examined=1000, supporting=900, violating=0, null_excluded=100, distinct=900)
print("support:", ev8.support, "null_fraction:", ev8.null_fraction, "is_exact:", ev8.is_exact)
print("describe:", ev8.describe())

# ---------------- MIN-009 ----------------
hdr("MIN-009")
ev9 = Evidence(rows_examined=100, supporting=0, violating=0, null_excluded=100, distinct=0)
print("support:", ev9.support)

# ---------------- MIN-010 ----------------
hdr("MIN-010")
rows10 = [{"trade_id": i, "amt": i * 1.1} for i in range(1000)]
s10 = Sample.of("trades", rows10)
f10 = km.mine(s10)
print("num candidates:", len(f10.candidates))
for c in f10.candidates:
    print(c.columns, c.is_exact, c.evidence.rows_examined, c.evidence.distinct)

# ---------------- MIN-011 ----------------
hdr("MIN-011")
rows11 = []
for i in range(1000):
    v = i % 5
    rows11.append({
        "trade_id": i,
        "a": v, "b": v, "c": v, "d": v, "e": v,
    })
s11 = Sample.of("trades", rows11)
km3 = KeyMiner(max_arity=3)
f11 = km3.mine(s11)
print("num candidates:", len(f11.candidates), [c.columns for c in f11.candidates])

# ---------------- MIN-012 ----------------
hdr("MIN-012")
rows12 = []
for i in range(1000):
    val = (i % 4) if i < 4 else None
    rows12.append({"code": val, "other": i})
s12 = Sample.of("t", rows12)
f12 = km.mine(s12)
print("candidates:", [c.columns for c in f12.candidates])
print("excluded:", f12.excluded)

# ---------------- MIN-013 ----------------
hdr("MIN-013")
def null_col(n, null_frac):
    n_null = round(n * null_frac)
    vals = []
    for i in range(n):
        if i < n_null:
            vals.append(None)
        else:
            vals.append(i)
    return vals

for null_frac, label in [(0.05, "5.0%"), (0.051, "5.1%")]:
    n = 1000
    col = null_col(n, null_frac)
    rows = [{"k": col[i]} for i in range(n)]
    s = Sample.of("t", rows)
    f = km.mine(s)
    actual_null = sum(1 for v in col if v is None) / n
    print(f"target={label} actual_null_frac={actual_null:.4f} candidates={[c.columns for c in f.candidates]} excluded={f.excluded}")

# ---------------- MIN-014 ----------------
hdr("MIN-014")
rows14 = [{"market_value": float(i) + 0.5} for i in range(300)]
s14 = Sample.of("t", rows14)
f14 = km.mine(s14)
print("candidates:", [c.columns for c in f14.candidates])
print("excluded:", f14.excluded)

# ---------------- MIN-015 ----------------
hdr("MIN-015")
rows15 = [{"account_number": 100000 + i} for i in range(300)]
s15 = Sample.of("t", rows15)
f15 = km.mine(s15)
print("candidates:", [c.columns for c in f15.candidates])
print("excluded:", f15.excluded)

# ---------------- MIN-016 ----------------
hdr("MIN-016")
def dup_col(n, n_dup):
    # n rows, n_dup of them are duplicates of row 0's value
    vals = list(range(n - n_dup))
    vals += [0] * n_dup
    return vals

for n_dup in (3, 20):
    n = 10000
    col = dup_col(n, n_dup)
    rows = [{"k": col[i]} for i in range(n)]
    s = Sample.of("t", rows)
    f = km.mine(s)
    distinct = len(set(col))
    uniqueness = distinct / n
    print(f"n_dup={n_dup} uniqueness={uniqueness:.5f} candidates={[(c.columns, c.approximate) for c in f.candidates]}")

# ---------------- MIN-017 ----------------
hdr("MIN-017")
rows17 = []
for i in range(300):
    rows17.append({
        "row_id": i,
        "account_id": i // 10,
        "business_date": f"2024-01-{(i % 10) + 1:02d}",
    })
s17 = Sample.of("t", rows17)
f17 = km.mine(s17)
print("all candidates:", [(c.columns, c.surrogate, c.is_exact) for c in f17.candidates])
best = f17.best
print("best:", best.columns if best else None, "surrogate:", best.surrogate if best else None)
print("business_key_found:", f17.business_key_found)

# ---------------- MIN-018 ----------------
hdr("MIN-018")
rows18 = [{"id": str(uuidlib.UUID(int=i)), "amount": float(i % 50)} for i in range(300)]
s18 = Sample.of("t", rows18)
f18 = km.mine(s18)
print("candidates:", [(c.columns, c.surrogate) for c in f18.candidates])
best18 = f18.best
print("best:", best18.columns if best18 else None, "surrogate:", best18.surrogate if best18 else None)
print("business_key_found:", f18.business_key_found)

# ---------------- MIN-019 ----------------
hdr("MIN-019")

def isin_like(i):
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return f"US{letters[i % 26]}{letters[(i*7) % 26]}{i:07d}{i%10}"

# a) instrument_id holding ISINs
rowsA = [{"instrument_id": isin_like(i)} for i in range(300)]
sA = Sample.of("t", rowsA)
fA = km.mine(sA)
print("instrument_id/ISIN -> surrogate:", [(c.columns, c.surrogate) for c in fA.candidates])

# b) ref holding 1..n
rowsB = [{"ref": i + 1} for i in range(300)]
sB = Sample.of("t", rowsB)
fB = km.mine(sB)
print("ref/1..n -> surrogate:", [(c.columns, c.surrogate) for c in fB.candidates])

# c) trade_id fixed-width digits
rowsC = [{"trade_id": f"{i:08d}"} for i in range(300)]
sC = Sample.of("t", rowsC)
fC = km.mine(sC)
print("trade_id/fixed-width digits -> surrogate:", [(c.columns, c.surrogate) for c in fC.candidates])

# d) trade_id variable-width digits
rowsD = [{"trade_id": str(i)} for i in range(300)]
sD = Sample.of("t", rowsD)
fD = km.mine(sD)
print("trade_id/variable-width digits -> surrogate:", [(c.columns, c.surrogate) for c in fD.candidates])

# e) counterparty UUID
rowsE = [{"counterparty": str(uuidlib.UUID(int=i * 999983))} for i in range(300)]
sE = Sample.of("t", rowsE)
fE = km.mine(sE)
print("counterparty/UUID -> surrogate:", [(c.columns, c.surrogate) for c in fE.candidates])

# ---------------- MIN-020 ----------------
hdr("MIN-020")
rowsF = [{"v": i + 1} for i in range(1000)]
sF = Sample.of("t", rowsF)
fF = km.mine(sF)
print("dense 1..1000 -> surrogate:", [(c.columns, c.surrogate) for c in fF.candidates])

random.seed(7)
sample_space = random.sample(range(100_000), 1000)
rowsG = [{"account_number": v} for v in sample_space]
sG = Sample.of("t", rowsG)
fG = km.mine(sG)
print("sparse account_number -> surrogate:", [(c.columns, c.surrogate) for c in fG.candidates])

# ---------------- MIN-021 ----------------
hdr("MIN-021")
rows21 = []
for i in range(300):
    row = {f"c{j}": (i * (j + 3)) % (50 + j) for j in range(8)}
    rows21.append(row)
s21 = Sample.of("t", rows21)
km3b = KeyMiner(max_arity=3)
f21 = km3b.mine(s21)
print("candidates:", [c.columns for c in f21.candidates])
print("skipped:", f21.skipped)

# ---------------- MIN-022 ----------------
hdr("MIN-022")
rows22 = [{"business_date": "2024-01-01", "trade_id": i} for i in range(300)]
s22 = Sample.of("trades", rows22, partition_column="business_date", total_rows=300)
f22 = km.mine(s22)
c22 = f22.candidates[0]
prov22 = as_provenance("trades", c22, s22)
print("origin:", prov22.origin)
print("observations:", prov22.observations)
print("statement:", prov22.statement)

# also check an approximate candidate mentions duplicates explicitly
rows22b = [{"business_date": "2024-01-01", "trade_id": i} for i in range(9997)]
rows22b += [{"business_date": "2024-01-01", "trade_id": 0} for _ in range(3)]
s22b = Sample.of("trades", rows22b, partition_column="business_date", total_rows=9999999999)
f22b = km.mine(s22b)
approx = [c for c in f22b.candidates if c.approximate]
print("approximate candidates:", [(c.columns, c.approximate) for c in f22b.candidates])
if approx:
    prov22b = as_provenance("trades", approx[0], s22b)
    print("approx observation[0]:", prov22b.observations[0])

# ---------------- MIN-023 ----------------
hdr("MIN-023")
rows23 = [{"trade_id": i} for i in range(300)]
s23 = Sample.of("trades", rows23, total_rows=300)
f23 = km.mine(s23)
c23 = f23.candidates[0]
prov23 = as_provenance("trades", c23, s23)
ident23 = key_identity("trades", c23)
proposal23 = Proposal(
    identity=ident23,
    content=c23.render(),
    content_hash="deadbeef",
    provenance=prov23,
    description=c23.describe(),
    dataset="trades",
)
queue = ProposalQueue()
admission = queue.offer(proposal23)
print("admission outcome:", admission.outcome)
auto = queue.auto_activatable()
print("auto_activatable identities:", [p.identity for p in auto])
print("proposal in auto_activatable:", any(p.identity == ident23 for p in auto))
print("needs_review:", proposal23.needs_review, "origin.may_auto_activate:", proposal23.origin.may_auto_activate)

# ---------------- MIN-024 ----------------
hdr("MIN-024")
rowsX1 = [{"trade_id": i} for i in range(300)]
rowsX2 = [{"trade_id": i * 3 + 1000} for i in range(500)]
sX1 = Sample.of("trades", rowsX1)
sX2 = Sample.of("trades", rowsX2)
fX1 = km.mine(sX1)
fX2 = km.mine(sX2)
c_x1 = fX1.candidates[0]
c_x2 = fX2.candidates[0]
id_x1 = key_identity("trades", c_x1)
id_x2 = key_identity("trades", c_x2)
print("id1==id2:", id_x1 == id_x2, id_x1, id_x2)
