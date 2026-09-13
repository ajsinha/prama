import sys, os
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
os.chdir("/home/ashutosh/PycharmProjects/prama")

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from prama.core.provenance import Origin, Citation, Corroboration, Provenance, identity, content_hash

# CFG-308
authorities = {o: o.authority for o in Origin}
expected308 = {
    Origin.DECLARATION: 100, Origin.DOCUMENT: 80, Origin.IMPORT: 60,
    Origin.MINING: 40, Origin.EXAMPLE: 30, Origin.INDUCTION: 20,
}
R("CFG-308", authorities == expected308, str({k.name: v for k, v in authorities.items()}))

# CFG-309
auto = {o: o.may_auto_activate for o in Origin}
R("CFG-309", auto[Origin.DECLARATION] is True and all(v is False for k,v in auto.items() if k is not Origin.DECLARATION),
  str({k.name: v for k,v in auto.items()}))

# CFG-310
stated = {o for o in Origin if o.is_stated}
R("CFG-310", stated == {Origin.DECLARATION, Origin.IMPORT, Origin.DOCUMENT}, str({o.name for o in stated}))

# CFG-311
try:
    Provenance(origin=Origin.DOCUMENT, rule="r", citation=None)
    R("CFG-311", False, "no exception")
except ValueError as e:
    R("CFG-311", "unfalsifiable" in str(e), str(e))

# CFG-312
p312 = Provenance(origin=Origin.DECLARATION, rule="r", declared_by="Alice", declared_at="2026-03-04T10:00:00Z")
p312b = p312.corroborated_by(Provenance(origin=Origin.MINING, rule="miner"), "observed in Q1 profile")
p312c = p312b.corroborated_by(Provenance(origin=Origin.MINING, rule="miner2"), "observed again")
R("CFG-312", len(p312b.corroborations)==1 and p312c is p312b, f"after 1st corroboration: {len(p312b.corroborations)}; second call same object={p312c is p312b}")

# CFG-313
R("CFG-313", len(p312.corroborations)==0 and p312b is not p312, f"original unchanged corroborations={len(p312.corroborations)}; new instance={p312b is not p312}")

# CFG-314
s314 = p312.sentence()
R("CFG-314", s314.startswith("Alice declared it on 2026-03-04") and "10:00" not in s314, repr(s314))

# CFG-315
p315 = Provenance(origin=Origin.MINING, rule="miner", observations=("seen in 30/30 days",))
s315 = p315.sentence()
R("CFG-315", s315.startswith("It holds in the data") and "seen in 30/30 days" in s315, repr(s315))

# CFG-316
p316 = Provenance(origin=Origin.DECLARATION, rule="r", declared_by="Bob", declared_at="2026-01-01T00:00:00Z")
before = p316.sentence()
d316 = p316.to_dict()
d316["sentence"] = "TOTALLY DIFFERENT TEXT THAT SHOULD BE IGNORED"
p316b = Provenance.from_dict(d316)
after = p316b.sentence()
R("CFG-316", before == after and after != d316["sentence"], f"before={before!r} after={after!r}")

# CFG-317
i1 = identity("decl-1", "rule-a", "subject-x")
i2 = identity("decl-1", "rule-a", "subject-x")
R("CFG-317", i1 == i2, f"{i1} == {i2}")

# CFG-318
ia = identity("a", "b")
ib = identity("b", "a")
R("CFG-318", ia != ib, f"{ia} vs {ib}")

# CFG-319
h1 = content_hash("CHECK t.a IS NOT NULL")
h2 = content_hash("CHECK t.a IS NOT NULL ")  # one extra space
R("CFG-319", h1 != h2, f"{h1} vs {h2}")

# CFG-320
R("CFG-320", len(i1) == 32 and len(h1) == 32 and all(c in "0123456789abcdef" for c in i1+h1),
  f"identity len={len(i1)}, content_hash len={len(h1)}")

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
