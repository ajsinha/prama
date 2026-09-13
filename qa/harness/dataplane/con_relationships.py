import sys, re, random
sys.path.insert(0, ".")
from qa_common import log
from prama.discover.relationships import (
    RelationshipDiscoverer, CandidateRelationship, Evidence, Signal, rank, _is_generic,
)
from prama.mine.sample import Sample
from prama.semantic.relationships import MatchKey, RelationshipKind

def pro099():
    left = Sample.of("orders", [{"id": i, "status": "open", "created_at": "2026-01-01"} for i in range(50)])
    right = Sample.of("shipments", [{"id": i, "status": "sent", "created_at": "2026-01-01"} for i in range(50)])
    disc = RelationshipDiscoverer()
    report = disc.discover(left, right)
    ok = len(report.candidates) == 0 and report.suppressed == {"generic_name": 3}
    log("PRO-099", "PASS" if ok else "FAIL", f"n_candidates={len(report.candidates)} suppressed={report.suppressed}")

def pro100():
    from prama.discover.relationships import DiscoveryReport
    report = DiscoveryReport(candidates=(), suppressed={"generic_name": 412})
    ok = report.suppressed == {"generic_name": 412}
    log("PRO-100", "PASS" if ok else "FAIL", str(report.suppressed))

def pro101():
    obs = {n: _is_generic(n) for n in ("id", "ID", "Id", "i-d", "account_id", "id2", "_id")}
    ok = (obs["id"] and obs["ID"] and obs["Id"] and obs["i-d"]
          and not obs["account_id"] and not obs["id2"] and not obs["_id"])
    log("PRO-101", "PASS" if ok else "FAIL", str(obs))

def pro102():
    def mk(*strengths):
        return CandidateRelationship(left="a", right="b", kind=RelationshipKind.REFERENCES,
            match_keys=(MatchKey("x", "y"),),
            evidence=tuple(Evidence(signal="s", strength=s, detail="") for s in strengths))
    c1 = mk(0.8)
    c2 = mk(0.35, 0.35)
    c3 = mk(0.8, 0.35)
    obs = {"one_0.8": round(c1.confidence, 4), "two_0.35": round(c2.confidence, 4), "0.8_and_0.35": round(c3.confidence, 4)}
    ok = obs["one_0.8"] == 0.8 and obs["two_0.35"] == 0.5775 and obs["0.8_and_0.35"] == 0.87
    log("PRO-102", "PASS" if ok else "FAIL", str(obs))

def pro103():
    def mk(s):
        return CandidateRelationship(left="a", right="b", kind=RelationshipKind.REFERENCES,
            match_keys=(MatchKey("x", "y"),), evidence=(Evidence(signal="s", strength=s, detail=""),))
    obs = {1.0: mk(1.0).confidence, 2.0: mk(2.0).confidence, -1.0: mk(-1.0).confidence}
    ok = obs[1.0] == 0.95 and obs[2.0] == 0.95 and obs[-1.0] == 0.0
    log("PRO-103", "PASS" if ok else "FAIL", str(obs))

def pro104():
    single = CandidateRelationship(left="a", right="b", kind=RelationshipKind.REFERENCES,
        match_keys=(MatchKey("x", "y"),), evidence=(Evidence(signal="naming", strength=0.35, detail="both have x"),))
    double = CandidateRelationship(left="a", right="b", kind=RelationshipKind.REFERENCES,
        match_keys=(MatchKey("x", "y"),),
        evidence=(Evidence(signal="naming", strength=0.35, detail="both have x"),
                  Evidence(signal="containment", strength=0.8, detail="values contained")))
    d1, d2 = single.describe(), double.describe()
    ok = d1.endswith("which is a question rather than a finding") and "single signal" in d1 and "question rather than a finding" not in d2
    log("PRO-104", "PASS" if ok else "FAIL", f"single={d1!r} double={d2!r}")

def pro105():
    c = CandidateRelationship(left="positions", right="accounts", kind=RelationshipKind.REFERENCES,
        match_keys=(MatchKey("account_no", "account_no"),),
        evidence=(Evidence(signal="containment", strength=0.8, detail="contained"),))
    d = c.describe()
    ok = d.startswith("positions → accounts may be references: records here point at records there, matched on")
    log("PRO-105", "PASS" if ok else "FAIL", d)

def pro106():
    disc = RelationshipDiscoverer()
    def sample_with(cols):
        return Sample.of("d", [{c: i for c in cols} for i in range(10)])
    # 2 distinctive columns each side -> None regardless of overlap
    left2 = sample_with(["colA", "colB"])
    right2 = sample_with(["colA", "colB"])
    r2 = disc._signature(left2, right2)
    # 3 distinctive columns, overlap computed to hit 59% then 61%
    # union of 5 with 3 shared -> shared/union = 3/5 = 0.6 exactly -> need <0.6 and >=0.6 cases
    leftA = sample_with(["c1", "c2", "c3"])
    rightA = sample_with(["c1", "c2", "c4"])  # shared={c1,c2}=2, union={c1,c2,c3,c4}=4, overlap=0.5 -> below
    rA = disc._signature(leftA, rightA)
    leftB = sample_with(["c1", "c2", "c3"])
    rightB = sample_with(["c1", "c2", "c3", "c4"])  # shared=3, union=4, overlap=0.75 -- try to hit ~0.61
    rB = disc._signature(leftB, rightB)
    # find overlap exactly 0.61-ish: shared=? union=? Let's try shared=11,union=18 => 0.611
    leftC = sample_with([f"c{i}" for i in range(11)] + ["l1", "l2", "l3", "l4", "l5", "l6", "l7"])  # 18 distinctive
    rightC = sample_with([f"c{i}" for i in range(11)] + ["r1", "r2", "r3", "r4", "r5", "r6", "r7"])
    rC = disc._signature(leftC, rightC)
    overlap_C = 11/25
    ok = (r2 is None and rA is None
          and (rB is not None and abs(rB.strength - (0.5 + 0.3*0.75)) < 1e-9))
    log("PRO-106", "PASS" if ok else "FAIL",
        f"2_distinctive_cols->None: {r2 is None}; 3cols/50%overlap->None: {rA is None}; "
        f"3cols/75%overlap->Evidence(strength={rB.strength if rB else None}, expected {0.5+0.3*0.75})")

def pro107():
    left = Sample.of("a", [{"x": i} for i in range(5)])
    right = Sample.of("b", [{"x": i} for i in range(5)])
    disc = RelationshipDiscoverer()
    r1 = disc.discover(left, right, co_access=40, co_access_total=200)
    r2 = disc.discover(left, right, co_access=0, co_access_total=200)
    r3 = disc.discover(left, right, co_access=40, co_access_total=0)
    def co_strength(report):
        for c in report.candidates:
            for e in c.evidence:
                if e.signal == Signal.CO_ACCESS:
                    return e.strength
        return None
    s1, s2, s3 = co_strength(r1), co_strength(r2), co_strength(r3)
    ok = s1 is not None and abs(s1 - 0.6) < 1e-9 and s2 is None and s3 is None
    log("PRO-107", "PASS" if ok else "FAIL", f"co_access=40/200 -> strength={s1} (expected 0.6); co_access=0/200 -> {s2}; co_access=40/0 -> {s3}")

def pro108():
    import subprocess
    out = subprocess.run(["grep", "-rn", "KEY_OVERLAP", "/home/ashutosh/PycharmProjects/prama/src"], capture_output=True, text=True).stdout
    lines = [l for l in out.strip().splitlines() if l]
    ok = len(lines) == 1 and "relationships.py" in lines[0]
    log("PRO-108", "PASS" if ok else "FAIL", f"{len(lines)} reference(s): {lines}")

def pro109():
    from prama.discover.relationships import DiscoveryReport
    def mk(left, right, conf):
        return CandidateRelationship(left=left, right=right, kind=RelationshipKind.REFERENCES,
            match_keys=(MatchKey(left, right),), evidence=(Evidence(signal="s", strength=conf, detail=""),))
    cands = [mk("z", "a", 0.5), mk("a", "z", 0.5), mk("a", "a", 0.5), mk("m", "n", 0.9)]
    r1 = DiscoveryReport(candidates=tuple(cands))
    r2 = DiscoveryReport(candidates=tuple(reversed(cands)))
    out1 = rank([r1])
    out2 = rank([r2])
    pairs1 = [(c.left, c.right) for c in out1]
    pairs2 = [(c.left, c.right) for c in out2]
    ok = pairs1 == pairs2
    log("PRO-109", "PASS" if ok else "FAIL", f"order1={pairs1} order2={pairs2} identical={ok}")

for fn in (pro099, pro100, pro101, pro102, pro103, pro104, pro105, pro106, pro107, pro108, pro109):
    fn()
