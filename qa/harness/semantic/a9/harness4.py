"""MIN-046..MIN-060: constraints.py"""
import random
import datetime
from prama.mine.sample import Sample
from prama.mine.constraints import (
    ConstraintMiner, InvariantKind, Invariant, invariant_provenance, invariant_identity,
    IDENTITY_TOLERANCE, MINIMUM_SUPPORT, MINIMUM_APPLICABLE,
)
from prama.mine.dependencies import dependency_identity, DependencyMiner
from prama.mine.dependencies import Dependency
from prama.mine.sample import Evidence
from prama.mine.dependencies import inclusion_identity
from prama.mine.dependencies import Inclusion

def hdr(cid):
    print(f"\n=== {cid} ===")

cm = ConstraintMiner()

# ---------------- MIN-046 ----------------
hdr("MIN-046")
random.seed(40)
rows46 = []
for i in range(1000):
    trade_date = datetime.date(2024, 1, 1) + datetime.timedelta(days=i % 300)
    if i % 1000 < 15:  # 15 violate (985 hold)
        settlement_date = trade_date - datetime.timedelta(days=1)
    else:
        settlement_date = trade_date + datetime.timedelta(days=2)
    rows46.append({"trade_date": trade_date.toordinal(), "settlement_date": settlement_date.toordinal()})
s46 = Sample.of("t", rows46)
f46 = cm.mine(s46)
ord46 = [i for i in f46.of_kind(InvariantKind.ORDERING) if set(i.columns) == {"trade_date", "settlement_date"}]
print("ordering invariants found:", [(i.expression, round(i.evidence.support,4), len(i.counterexamples)) for i in ord46])
if ord46:
    print("counterexamples:", ord46[0].counterexamples)

# ---------------- MIN-047 & MIN-048 ----------------
hdr("MIN-047")
random.seed(41)
rows47 = []
n_bitexact = 0
for i in range(1000):
    qty = random.uniform(1, 1000)
    price = random.uniform(0.01, 500)
    computed = qty * price
    # Simulate a value independently stored/rounded elsewhere: a tiny relative
    # perturbation so the row is (almost certainly) never bit-exact, but well
    # within IDENTITY_TOLERANCE.
    notional = computed * (1 + 1e-12)
    if notional == computed:
        n_bitexact += 1
    rows47.append({"quantity": qty, "price": price, "notional": notional})
print("rows where notional == qty*price bit-for-bit:", n_bitexact, "of", len(rows47))
s47 = Sample.of("t", rows47)
f47 = cm.mine(s47)
ident47 = [i for i in f47.of_kind(InvariantKind.IDENTITY) if set(i.columns) == {"quantity", "price", "notional"}]
print("identity invariants found (with tolerance):", [(i.expression, i.is_exact) for i in ident47])
# counterfactual: exact equality alone finds nothing
n_exact_matches = sum(1 for r in rows47 if r["quantity"] * r["price"] == r["notional"])
print("rows that would pass an EXACT (zero-tolerance) test:", n_exact_matches, "of", len(rows47))

hdr("MIN-048")
# case A: order 1e9 differing in 12th significant digit (i.e. relative diff ~1e-12, within tolerance 1e-9)
rowsA = []
for i in range(1000):
    a = 1_000_000_000.0 + i
    b = 2.0 + (i % 5) * 0.001  # non-constant
    target = a * b
    target_perturbed = target * (1 + 1e-12)  # 12th significant digit differs
    rowsA.append({"a": a, "b": b, "target": target_perturbed})
sA = Sample.of("t", rowsA)
fA = cm.mine(sA)
idA = [i for i in fA.of_kind(InvariantKind.IDENTITY) if set(i.columns) == {"a", "b", "target"}]
print("large-scale (1e-12 relative diff) identity found:", len(idA) > 0, [(i.expression) for i in idA])

# case B: order 1e-6 differing by 1e-7 absolute (i.e., relative diff ~ 0.1, way outside tolerance)
rowsB = []
for i in range(1000):
    a = 1e-6 + (i % 100) * 1e-9  # non-constant, still ~1e-6 scale
    b = 1.0 + (i % 3) * 1e-9  # non-constant, ~1.0
    target = a * b + 1e-7  # absolute diff of 1e-7 on a target of order 1e-6: relative ~10%
    rowsB.append({"a": a, "b": b, "target": target})
sB = Sample.of("t", rowsB)
fB = cm.mine(sB)
idB = [i for i in fB.of_kind(InvariantKind.IDENTITY) if set(i.columns) == {"a", "b", "target"}]
print("small-scale (1e-7 absolute diff on 1e-6 values) identity found:", len(idB) > 0)

# ---------------- MIN-049 ----------------
hdr("MIN-049")
random.seed(42)
rows49 = []
for i in range(1000):
    fees = random.uniform(1, 500)
    net = fees + random.uniform(1, 500)  # overlapping ranges, but net always > fees
    notional = fees + net
    rows49.append({"notional": notional, "fees": fees, "net": net})
s49 = Sample.of("t", rows49)
f49 = cm.mine(s49)
ident49 = f49.of_kind(InvariantKind.IDENTITY)
print("identities found:", [i.expression for i in ident49])
print("discarded['algebraic_restatement']:", f49.discarded.get("algebraic_restatement"))
print("discarded['commutative_duplicate']:", f49.discarded.get("commutative_duplicate"))

# ---------------- MIN-050 ----------------
hdr("MIN-050")
ord50 = f49.of_kind(InvariantKind.ORDERING)
print("orderings found:", [i.expression for i in ord50])
print("discarded['implied_by_identity']:", f49.discarded.get("implied_by_identity"))
has_fees_net = any(set(i.columns) == {"fees", "net"} for i in ord50)
print("fees<=net or net<=fees kept:", has_fees_net)

# ---------------- MIN-051 ----------------
hdr("MIN-051")
random.seed(43)
rows51 = []
for i in range(1000):
    quantity = random.uniform(0.01, 0.99)  # below 1 on every row
    price = random.uniform(1, 100)
    notional = price * quantity
    rows51.append({"price": price, "quantity": quantity, "notional": notional})
s51 = Sample.of("t", rows51)

# Direct check of the boundary logic in _not_implied: with quantity always < 1,
# the multiplicative floor of 1.0 must NOT treat (price <= notional) as entailed
# by "price * quantity = notional" (it would incorrectly be entailed under a
# wrong floor of 0.0, since quantity is always >= 0).
at_least_1 = cm._at_least(s51, "quantity", 1.0)
at_least_0 = cm._at_least(s51, "quantity", 0.0)
print("quantity all >= 1.0:", at_least_1, " quantity all >= 0.0:", at_least_0)

identity_inv = Invariant(
    kind=InvariantKind.IDENTITY,
    expression="price * quantity = notional",
    columns=("price", "quantity", "notional"),
    evidence=Evidence(rows_examined=1000, supporting=1000, distinct=1000),
)
manufactured_ordering = Invariant(
    kind=InvariantKind.ORDERING,
    expression="price <= notional",
    columns=("price", "notional"),
    evidence=Evidence(rows_examined=1000, supporting=1000, distinct=1000),
)
discarded51 = {}
kept51 = cm._not_implied(s51, [manufactured_ordering], [identity_inv], discarded51)
print("manufactured 'price <= notional' kept (not dropped):", any(o.columns == ("price", "notional") for o in kept51))
print("discarded51:", discarded51)

# ---------------- MIN-052 ----------------
hdr("MIN-052")
random.seed(44)
rows52 = []
for i in range(1000):
    fees = random.uniform(0, 100)
    quantity = random.uniform(10_000, 1_000_000)
    rows52.append({"fees": fees, "quantity": quantity})
s52 = Sample.of("t", rows52)
f52 = cm.mine(s52)
ord52 = f52.of_kind(InvariantKind.ORDERING)
has_fq = any(set(i.columns) == {"fees", "quantity"} for i in ord52)
print("fees<=quantity found:", has_fq)
print("discarded['disjoint_ranges']:", f52.discarded.get("disjoint_ranges"))

# ---------------- MIN-053 ----------------
hdr("MIN-053")
random.seed(45)
rows53 = []
for i in range(1000):
    valid_from = i
    valid_to = i + 1 + random.randint(0, 5)
    rows53.append({"valid_from": valid_from, "valid_to": valid_to})
s53 = Sample.of("t", rows53)
f53 = cm.mine(s53)
ord53 = [i for i in f53.of_kind(InvariantKind.ORDERING) if set(i.columns) == {"valid_from", "valid_to"}]
print("orderings for (valid_from, valid_to):", [i.expression for i in ord53])
print("discarded['weaker_ordering']:", f53.discarded.get("weaker_ordering"))

print("\nAll scripts complete\n")
