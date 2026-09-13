import sys, dataclasses
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.integrate.catalog import Badge, Standing, WriteReport, CatalogTarget, RecordingTarget, badges_from
from prama.core.errors import ValidationError

results = []
def R(id_, ok, obs):
    results.append((id_, "PASS" if ok else "FAIL", obs))

def block(id_):
    def deco(fn):
        try:
            fn()
        except AssertionError as e:
            R(id_, False, f"AssertionError: {e}")
        except Exception as e:
            R(id_, False, f"{type(e).__name__}: {e}")
    return deco

@dataclasses.dataclass
class FakeRecord:
    dataset: str
    verdict: str
    coverage: str = "full"
    record_hash: str = "hash1"

@block("INT-001")
def _():
    try:
        Badge(dataset='x', standing=Standing.HEALTHY, established_at='')
        R("INT-001", False, "no exception")
    except ValidationError as e:
        R("INT-001", True, f"{e}")

@block("INT-002")
def _():
    full = Badge(dataset='x', standing=Standing.HEALTHY, established_at='2026-01-01', coverage='full')
    partial = Badge(dataset='x', standing=Standing.HEALTHY, established_at='2026-01-01', coverage='sampled')
    ok = '2026-01-01' in full.render() and ', over the rows examined (sampled)' in partial.render() and ', over the rows examined' not in full.render()
    R("INT-002", ok, f"full={full.render()!r} partial={partial.render()!r}")

@block("INT-003")
def _():
    b = Badge(dataset='x', standing=Standing.FAILING, established_at='t', controls=11, failing_controls=3)
    r = b.render()
    ok = 'checked and failing' in r and '3 of 11 control(s) failing' in r
    R("INT-003", ok, f"{r}")

@block("INT-004")
def _():
    reassuring = {s: s.is_reassuring for s in Standing}
    ok = reassuring == {Standing.HEALTHY:True, Standing.FAILING:False, Standing.NOT_ESTABLISHED:False, Standing.UNPROVEN:False, Standing.UNCOVERED:False}
    labels_full = all(len(s.label.split())>=2 for s in Standing)
    R("INT-004", ok and labels_full, f"{reassuring} labels={[s.label for s in Standing]}")

@block("INT-005")
def _():
    latest = {f"c{i}": FakeRecord(dataset=f"d{i}", verdict="pass") for i in range(9)}
    badges = badges_from(latest, datasets=[f"d{i}" for i in range(10)], established_at="t")
    tenth = next(b for b in badges if b.dataset=="d9")
    ok = len(badges)==10 and tenth.standing==Standing.UNCOVERED and tenth.detail=="no control covers this dataset"
    R("INT-005", ok, f"tenth={tenth}")

@block("INT-006")
def _():
    # dataset whose controls exist (records present) but have "not run in the window" -- no verdict shape for that in badges_from's inputs
    # badges_from only sees latest verdicts; a control that "has not run" is simply absent from `latest`, indistinguishable from UNCOVERED
    latest = {}
    badges = badges_from(latest, datasets=["d1"], established_at="t")
    only_standing = {b.standing for b in badges}
    R("INT-006", Standing.UNPROVEN in only_standing, f"badges={badges} -- UNPROVEN is never producible by badges_from; a dataset with controls that haven't run reads identically to one with none at all (UNCOVERED)")

@block("INT-007")
def _():
    latest = {
        "c1": FakeRecord(dataset="d1", verdict="fail"),
        "c2": FakeRecord(dataset="d1", verdict="indeterminate"),
        "c3": FakeRecord(dataset="d1", verdict="pass"),
        "c4": FakeRecord(dataset="d1", verdict="pass"),
        "c5": FakeRecord(dataset="d1", verdict="pass"),
    }
    badges = badges_from(latest, datasets=["d1"], established_at="t")
    b = badges[0]
    ok = b.standing==Standing.FAILING and b.failing_controls==1 and b.controls==5
    R("INT-007", ok, f"{b}")

@block("INT-008")
def _():
    latest = {
        "c1": FakeRecord(dataset="d1", verdict="pass", coverage="full"),
        "c2": FakeRecord(dataset="d1", verdict="pass", coverage="sampled"),
    }
    badges = badges_from(latest, datasets=["d1"], established_at="t")
    ok = badges[0].coverage=="partial"
    R("INT-008", ok, f"{badges[0]}")

@block("INT-009")
def _():
    latest = {}
    for i in range(5):
        verdict = "fail" if i==3 else "pass"
        latest[f"c{i}"] = FakeRecord(dataset="d1", verdict=verdict, record_hash=f"hash_of_c{i}")
    badges = badges_from(latest, datasets=["d1"], established_at="t")
    b = badges[0]
    points_at_failing = b.evidence_reference == "hash_of_c3"
    R("INT-009", points_at_failing, f"badge.evidence_reference={b.evidence_reference!r} (dict-iteration-order gives the first record inserted, not necessarily the failing one)")

@block("INT-010")
def _():
    class NoDate(CatalogTarget):
        name = "nodate"
        supports = frozenset({"standing"})
        def write(self, badge): pass
    t = NoDate()
    badges = [Badge(dataset=f"d{i}", standing=Standing.HEALTHY, established_at="t") for i in range(40)]
    report = t.publish(badges)
    ok = report.written==0 and len(report.refused)==40 and len({w for _,w in report.refused})==1
    ok2 = "Nothing was written — all 40 refused for the same reason" in report.describe()
    R("INT-010", ok and ok2, f"written={report.written} refused_count={len(report.refused)} describe={report.describe()}")

@block("INT-011")
def _():
    t = RecordingTarget(supports=frozenset({"standing","established_at"}))
    badges = [Badge(dataset="d1", standing=Standing.HEALTHY, established_at="t", evidence_reference="ev1")]
    report = t.publish(badges)
    ok = report.dropped_fields==("coverage","detail","evidence_reference") or "evidence_reference" in report.dropped_fields
    absent_not_blank = "absent from it rather than shown as blank" in report.describe()
    R("INT-011", ok and absent_not_blank, f"dropped_fields={report.dropped_fields} describe={report.describe()}")

@block("INT-012")
def _():
    t = RecordingTarget(refuse={"d17"})
    badges = [Badge(dataset=f"d{i}", standing=Standing.HEALTHY, established_at="t") for i in range(40)]
    report = t.publish(badges)
    ok = report.written==39 and len(report.refused)==1 and report.refused[0][0]=="d17" and not report.complete
    R("INT-012", ok, f"written={report.written} refused={report.refused} complete={report.complete}")

@block("INT-013")
def _():
    t = RecordingTarget()
    refuse_set = {f"d{i}" for i in [3,7,12,19,25,31,38]}
    t2 = RecordingTarget(refuse=refuse_set)
    badges = [Badge(dataset=f"d{i}", standing=Standing.HEALTHY, established_at="t", detail=f"reason{i}" if f"d{i}" in refuse_set else "") for i in range(40)]
    report = t2.publish(badges)
    d = report.describe()
    stale_first = d.index("NOT updated") < d.index("written") if "written" in d else True
    R("INT-013", stale_first and "…" in d, f"{d}")

@block("INT-014")
def _():
    t = RecordingTarget()
    report = t.publish([])
    ok_desc = report.describe()=="nothing was written, because nothing was offered"
    ok_complete = report.complete is True
    R("INT-014", not (ok_desc and ok_complete) , f"describe={report.describe()!r} complete={report.complete} -- both being true simultaneously is the tension the catalogue flags: 'nothing was offered' reported as a complete write")

@block("INT-015")
def _():
    from prama.security.egress import Gate
    gate = Gate.for_tenant("EU")  # tenant's data must stay in EU
    t = RecordingTarget()
    t.region = "EU"  # destination itself is fine
    badges = []
    for i in range(40):
        j = "US" if i < 3 else "EU"   # 3 badges are US-jurisdiction data, refused; 37 EU-jurisdiction pass
        badges.append(Badge(dataset=f"d{i}", standing=Standing.HEALTHY, established_at="t", jurisdiction=j))
    report = t.publish(badges, gate=gate)
    ok = report.written==37 and len(report.refused)==3
    R("INT-015", ok, f"written={report.written} refused={len(report.refused)} refused_datasets={[d for d,_ in report.refused]}")

@block("INT-016")
def _():
    from prama.security.egress import Gate
    gate = Gate.for_tenant("EU")
    t = RecordingTarget()
    t.region = ""  # unstated
    badges = [Badge(dataset="d1", standing=Standing.HEALTHY, established_at="t", jurisdiction="EU")]
    report = t.publish(badges, gate=gate)
    ok = report.written==0 and len(report.refused)==1
    R("INT-016", ok, f"written={report.written} refused={report.refused} (an unstated destination must NOT be treated as domestic/allowed)")

@block("INT-017")
def _():
    from prama.security.egress import Gate
    gate = Gate.for_tenant("EU")
    t = RecordingTarget()
    t.region = "US"
    b_no_jurisdiction = Badge(dataset="d1", standing=Standing.HEALTHY, established_at="t", jurisdiction="")
    report = t.publish([b_no_jurisdiction], gate=gate)
    # also: badges_from() never sets jurisdiction at all
    latest = {"c1": FakeRecord(dataset="d2", verdict="pass")}
    generated = badges_from(latest, datasets=["d2"], established_at="t")
    never_set = generated[0].jurisdiction == ""
    R("INT-017", None, f"no-jurisdiction badge publish: written={report.written} refused={report.refused}; badges_from() never sets jurisdiction at all (always ''): {never_set}")

print("=== INT catalog 001-015 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
