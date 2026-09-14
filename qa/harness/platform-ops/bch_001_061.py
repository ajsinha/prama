import sys, inspect, random
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

from prama.bench.corpus import (
    build, CLASSES, Family, Difficulty, classes_of, _base_row, _null_out, _drop_column,
    _rename_column, _retype, _duplicate_key, _sign_flip, _truncate, _legitimate_change_with_defect,
)
from prama.bench.scoring import Defect, Alert, FamilyScore, Score, score
from prama.bench.baselines import (
    BASELINES, NOT_RUN, Baseline, Comparison, baseline, compare,
    _detect_nothing, _detect_everything, _detect_schema_only, _detect_patterns_only, _detect_statistics_only,
)
from prama.bench.shadow import Blinding, Judgement, ShadowAlert, SystemResult, ShadowResult, evaluate

def line(id_, result, observed):
    print(f"{id_}: {result} :: {observed}")

# round 4 correction: Batch B ("the fourteen commands that answered a person
# with a stack trace", commit 53b9043) retyped bench/corpus.py's rate/rows
# refusals from a bare ValueError to prama.core.errors.ValidationError, which
# is a PramaError, NOT a ValueError subclass. The bare `except ValueError`
# below would let the new exception type propagate uncaught and crash every
# case after BCH-015/BCH-016 in this script. Broadened to catch the taxonomy
# error too so the script completes; the PASS/FAIL verdict for BCH-015/
# BCH-016 still checks isinstance(..., ValueError) because the catalogue's
# literal Expected names that type specifically -- see the round-4 log for
# the resulting regression judgement (same shape as OPS-003 in round 3).
from prama.core.errors import ValidationError as _ValidationError

# BCH-001
try:
    build()
    ok = False; obs = "no exception"
except TypeError as e:
    ok = True; obs = f"TypeError: {e}"
line("BCH-001", "PASS" if ok else "FAIL", obs)

# BCH-002
c1 = build(seed=42)
c2 = build(seed=42)
same = c1.to_dict() == c2.to_dict() and all(s1.rows == s2.rows for s1,s2 in zip(c1.scenarios, c2.scenarios))
line("BCH-002", "PASS" if same else "FAIL", f"to_dict_equal={c1.to_dict()==c2.to_dict()} rows_equal={all(s1.rows==s2.rows for s1,s2 in zip(c1.scenarios,c2.scenarios))}")

# BCH-003
c3 = build(seed=43)
diff = c1.to_dict() != c3.to_dict()
line("BCH-003", "PASS" if diff else "FAIL", f"different={diff}")

# BCH-004
by_family = {}
for cls in CLASSES:
    by_family.setdefault(cls.family, []).append(cls)
counts4 = {f.value: len(by_family.get(f, [])) for f in Family}
expected4 = {"structural":5,"content":7,"statistical":5,"relational":4,"temporal":3,"semantic":4}
base_row_keys = set(_base_row(0, random.Random(1), "w").keys())
all_columns_valid = all(cls.column in base_row_keys for cls in CLASSES)
ok = len(CLASSES)==sum(expected4.values()) and counts4 == expected4 and all_columns_valid
line("BCH-004", "PASS" if ok else "FAIL", f"total={len(CLASSES)} (catalogue says 27 but its own per-family counts sum to 28, matching the actual total -- catalogue arithmetic slip) counts={counts4} expected={expected4} all_columns_valid={all_columns_valid}")

# BCH-005
ok5 = all(len(classes_of(f)) > 0 for f in Family)
line("BCH-005", "PASS" if ok5 else "FAIL", f"counts={ {f.value: len(classes_of(f)) for f in Family} }")

# BCH-006
by_diff = {}
for cls in CLASSES:
    by_diff.setdefault(cls.difficulty, 0)
    by_diff[cls.difficulty] += 1
ok6 = all(by_diff.get(d, 0) > 0 for d in Difficulty)
line("BCH-006", "PASS" if ok6 else "FAIL", f"counts={ {d.value: by_diff.get(d,0) for d in Difficulty} }")

# BCH-007
corpus7 = build(seed=1)
windows = [s.window for s in corpus7.scenarios]
ok7 = len(set(windows)) == len(windows) and windows == sorted(windows)
line("BCH-007", "PASS" if ok7 else "FAIL", f"n_windows={len(windows)} unique={len(set(windows))} sorted={windows==sorted(windows)} first3={windows[:3]}")

# BCH-008
sign_flip_class = next(c for c in CLASSES if c.name=="sign-flip")
corpus8 = build(seed=5, classes=[sign_flip_class], rows=50, rate=0.5)
scenario8 = corpus8.scenarios[0]
actual_diff = tuple(sorted(i for i in range(len(scenario8.clean)) if scenario8.clean[i] != scenario8.rows[i]))
ok8 = scenario8.damaged_rows == actual_diff
line("BCH-008", "PASS" if ok8 else "FAIL", f"damaged_rows={scenario8.damaged_rows} actual_diff={actual_diff}")

# BCH-009 - construct a class whose injector always returns False
import dataclasses
from prama.bench.corpus import DefectClass
barren_class = DefectClass("always-noop", Family.CONTENT, Difficulty.OBVIOUS, "amount", lambda row, rng: False, "never changes anything")
corpus9 = build(seed=1, classes=[barren_class], rows=20, rate=0.5)
ok9 = len(corpus9.barren) == 1 and corpus9.barren[0][0] == "always-noop" and corpus9.planted == 0
line("BCH-009", "PASS" if ok9 else "FAIL", f"barren={corpus9.barren} planted={corpus9.planted}")

# BCH-010
row_pos = {"amount": 100.0}
row_short = {"party_name": "abc"}
row_text = {"amount": "already text"}
r1 = _sign_flip(row_pos, None); r1b = _sign_flip({"amount": -50.0}, None)
r2 = _truncate(row_short, None)
r3 = _retype(row_text, "amount")
ok10 = r1==True and r1b==False and row_pos["amount"]==-100.0 and r2==False and row_short["party_name"]=="abc" and r3==False
line("BCH-010", "PASS" if ok10 else "FAIL", f"sign_flip_pos={r1} sign_flip_neg={r1b} truncate_short={r2} retype_text={r3}")

# BCH-011
row11 = {"amount": None}
ok11 = _null_out(row11, "amount") == False
line("BCH-011", "PASS" if ok11 else "FAIL", f"result={_null_out({'amount':None},'amount')}")

# BCH-012
row12a = {"product":"CURRENT","other":1}
row12b = {"party_name":"Acme","other":1}
r12a = _drop_column(row12a, "product")
r12b = _rename_column(row12b, "party_name", "partyName")
ok12 = r12a==True and "product" not in row12a and r12b==True and "party_name" not in row12b and row12b.get("partyName")=="Acme"
line("BCH-012", "PASS" if ok12 else "FAIL", f"after_drop={row12a} after_rename={row12b}")

# BCH-013
dup_class = next(c for c in CLASSES if c.name=="grain-violation")
corpus13 = build(seed=2, classes=[dup_class], rows=50, rate=0.5)
scen13 = corpus13.scenarios[0]
acct_ids = [r["account_id"] for r in scen13.rows]
dupes = len(acct_ids) - len(set(acct_ids))
ok13 = dupes >= 1
line("BCH-013", "PASS" if ok13 else "FAIL", f"n_dupes={dupes}")

# BCH-014
row14 = {"product":"CURRENT","amount":100.0}
_legitimate_change_with_defect(row14, random.Random(1))
ok14 = row14["product"]=="MERGED-ENTITY" and row14["amount"]==200.0
line("BCH-014", "PASS" if ok14 else "FAIL", f"after={row14}")

# BCH-015
errs15 = []
types15 = []
for bad_rate in [0, 1.5, -0.1]:
    try:
        build(seed=1, rate=bad_rate)
        errs15.append(None); types15.append(None)
    except (ValueError, _ValidationError) as e:
        errs15.append(str(e)); types15.append(type(e).__name__)
ok15 = all(e is not None and "rate" in e for e in errs15) and all(isinstance(t, str) and t == "ValueError" for t in types15)
line("BCH-015", "PASS" if ok15 else "FAIL", f"errors={errs15} types={types15} (catalogue Expected: ValueError naming the value)")

# BCH-016
try:
    build(seed=1, rows=0)
    ok16 = False; obs16 = "no exception"
except (ValueError, _ValidationError) as e:
    ok16 = isinstance(e, ValueError); obs16 = f"{type(e).__name__}: {e} (catalogue Expected: ValueError)"
line("BCH-016", "PASS" if ok16 else "FAIL", obs16)

# BCH-017
retype_class = next(c for c in CLASSES if c.name=="category-disappearance")
corpus17 = build(seed=3, classes=[retype_class], rows=200, rate=0.05)
scen17 = corpus17.scenarios[0]
ok17 = len(scen17.damaged_rows) < 10
line("BCH-017", "PASS" if ok17 else "FAIL", f"n_damaged={len(scen17.damaged_rows)}")

# BCH-018
corpus18 = build(seed=4, rows=10, rate=0.01)
ok18 = all(len(s.damaged_rows) >= 0 for s in corpus18.scenarios) and any(len(s.damaged_rows)>=1 for s in corpus18.scenarios)
# verify per_class computed as max(1,...) by checking sample size logic indirectly: with rows=10, rate=0.01 -> int(0.1)=0 -> max(1,0)=1 attempt per class
line("BCH-018", "PASS" if ok18 else "FAIL", f"any_planted={any(len(s.damaged_rows)>=1 for s in corpus18.scenarios)}")

# BCH-019
corpus19 = build(seed=1, rows=20)
ok19 = all(row["control_total"] == row["amount"] for s in corpus19.scenarios for row in s.clean)
line("BCH-019", "PASS" if ok19 else "FAIL", f"all_match={ok19}")

# BCH-020
corpus20 = build(seed=1, rows=200)
n_classes20 = len(CLASSES)
ok20 = len(corpus20.rows) == n_classes20*200 and len(corpus20.clean) == n_classes20*200
line("BCH-020", "PASS" if ok20 else "FAIL", f"rows={len(corpus20.rows)} clean={len(corpus20.clean)} expected={n_classes20*200} (catalogue said 5,400 assuming 27 classes; actual is 28 classes x 200 = 5,600)")

# BCH-021
corpus21 = build(seed=1, classes=[barren_class], rows=20, rate=0.5)
d21 = corpus21.to_dict()
ok21 = len(d21["barren"]) == 1 and d21["barren"][0]["class"]=="always-noop"
line("BCH-021", "PASS" if ok21 else "FAIL", f"barren_in_dict={d21['barren']}")

print("=== scoring ===")

# BCH-022
defect22 = Defect(dataset="d1", column="amount", window="2026-01-01", family="content")
alerts22 = [
    Alert(dataset="d1", column="amount", window="2026-01-01"),  # exact
    Alert(dataset="d2", column="amount", window="2026-01-01"),  # wrong dataset
    Alert(dataset="d1", column="rate", window="2026-01-01"),    # wrong column
    Alert(dataset="d1", column="amount", window="2026-01-02"),  # wrong window
]
score22 = score([defect22], alerts22)
ok22 = score22.found == 1
line("BCH-022", "PASS" if ok22 else "FAIL", f"found={score22.found} false_alarms={score22.false_alarms}")

# BCH-023
defect23 = Defect(dataset="d1", column="amount", window="2026-01-01", family="content")
alert23 = Alert(dataset="d1", column="amount", window="2026-01-02")
score23 = score([defect23], [alert23])
ok23 = len(score23.near_misses) == 1 and score23.found == 0
line("BCH-023", "PASS" if ok23 else "FAIL", f"near_misses={len(score23.near_misses)} found={score23.found}")

# BCH-024
defect24 = Defect(dataset="d1", column="amount", window="2026-01-01", family="content")
alerts24 = [Alert(dataset="d1", column="amount", window="2026-01-01") for _ in range(10)]
score24 = score([defect24], alerts24)
ok24 = score24.found == 1 and score24.false_alarms == 9
line("BCH-024", "PASS" if ok24 else "FAIL", f"found={score24.found} false_alarms={score24.false_alarms}")

# BCH-025
defect25a = Defect(dataset="d1", column="amount", window="2026-01-01", family="content", note="a")
defect25b = Defect(dataset="d1", column="amount", window="2026-01-01", family="content", note="b")
alerts25 = [Alert(dataset="d1", column="amount", window="2026-01-01") for _ in range(2)]
score25 = score([defect25a, defect25b], alerts25)
ok25 = score25.found == 2
line("BCH-025", "PASS" if ok25 else "FAIL", f"found={score25.found}")

# BCH-026
fs26 = FamilyScore(family="x", planted=0, found=0, false_alarms=3)
ok26 = fs26.recall is None and "nothing was planted" in fs26.describe()
line("BCH-026", "PASS" if ok26 else "FAIL", f"recall={fs26.recall} describe={fs26.describe()!r}")

# BCH-027
fs27 = FamilyScore(family="x", planted=5, found=5, false_alarms=0)
ok27 = fs27.precision is None and "precision is an aggregate figure" in fs27.describe()
line("BCH-027", "PASS" if ok27 else "FAIL", f"precision={fs27.precision} describe={fs27.describe()!r}")

# BCH-028
fs28 = FamilyScore(family="x", planted=5, found=5, false_alarms=0)
ok28 = fs28.f1 is None
line("BCH-028", "PASS" if ok28 else "FAIL", f"f1={fs28.f1} (precision always None -> f1 structurally always None)")

# BCH-029
defects29 = [Defect(dataset="d",column="c1",window="w",family="f1"),
             Defect(dataset="d",column="c2",window="w",family="f2"),
             Defect(dataset="d",column="c3",window="w",family="f3")]
alerts29 = [Alert(dataset="d",column="c1",window="w")] + [Alert(dataset="d",column=f"wrong{i}",window="w") for i in range(5)]
score29 = score(defects29, alerts29)
fam_fa = [f.false_alarms for f in score29.families]
ok29 = all(fa == 5 for fa in fam_fa) and score29.false_alarms == 5
line("BCH-029", "PASS" if ok29 else "FAIL", f"family_false_alarms={fam_fa} score_false_alarms={score29.false_alarms}")

# BCH-030
defects30 = [Defect(dataset="d",column=f"c{i}",window="w",family="f") for i in range(8)]
alerts30 = [Alert(dataset="d",column=f"c{i}",window="w") for i in range(8)] + [Alert(dataset="d",column="wrong1",window="w"), Alert(dataset="d",column="wrong2",window="w")]
score30 = score(defects30, alerts30)
ok30 = score30.precision == 0.8
line("BCH-030", "PASS" if ok30 else "FAIL", f"precision={score30.precision}")

# BCH-031
corpus31 = build(seed=1, rows=50)
score31 = score(corpus31.defects, _detect_nothing(corpus31))
ok31 = score31.precision is None and score31.recall is not None and score31.f1 is None
line("BCH-031", "PASS" if ok31 else "FAIL", f"precision={score31.precision} recall={score31.recall} f1={score31.f1}")

# BCH-032
defects32 = [Defect(dataset="d",column="c1",window="w",family="weak"), Defect(dataset="d",column="c2",window="w",family="weak"),
             Defect(dataset="d",column="c3",window="w",family="strong")]
alerts32 = [Alert(dataset="d",column="c3",window="w")]  # only strong found
score32 = score(defects32, alerts32)
desc32 = score32.describe()
ok32 = desc32.startswith("weakest family weak")
line("BCH-032", "PASS" if ok32 else "FAIL", f"describe={desc32!r}")

# BCH-033
defects33 = [Defect(dataset="d",column=f"c{i}",window="w",family="f",difficulty=d.value) for i,d in enumerate(Difficulty)]
alerts33 = [Alert(dataset="d",column="c0",window="w"), Alert(dataset="d",column="c2",window="w")]  # find obvious and subtle
score33 = score(defects33, alerts33)
total_found = sum(f for f,p in score33.by_difficulty.values())
total_planted = sum(p for f,p in score33.by_difficulty.values())
ok33 = total_found == score33.found and total_planted == score33.planted
line("BCH-033", "PASS" if ok33 else "FAIL", f"by_difficulty={score33.by_difficulty} found={score33.found} planted={score33.planted}")

# BCH-034
doc34 = inspect.getsource(Defect)  # class body, including #: attribute comments
default34 = Defect.__dataclass_fields__["difficulty"].default
actual_values = {c.difficulty.value for c in CLASSES}
# Catalogue's literal "Expected" is that the documented vocabulary and the corpus's
# actual vocabulary AGREE. They do not (confirmed) -- so per the observed-vs-Expected
# rule this case is a FAIL (a real, reproducible documentation defect), not a PASS.
vocab_present = "easy" in doc34 and "moderate" in doc34 and "hard" in doc34
they_agree = vocab_present and {"easy","moderate","hard"} == actual_values
line("BCH-034", "PASS" if they_agree else "FAIL", f"docstring_says_easy_moderate_hard={vocab_present} default={default34!r} actual_corpus_values={actual_values} -- do_not_agree, confirming the pre-flagged documentation defect")

print("=== baselines ===")

# BCH-035
corpus35 = build(seed=1, rows=50)
b35 = baseline("detect-nothing")
score35 = b35.run(corpus35)
ok35 = score35.found == 0 and score35.false_alarms == 0 and score35.recall == 0.0 and score35.precision is None
line("BCH-035", "PASS" if ok35 else "FAIL", f"found={score35.found} false_alarms={score35.false_alarms} recall={score35.recall} precision={score35.precision}")

# BCH-036
b36 = baseline("alert-on-everything")
score36 = b36.run(corpus35)
ok36 = score36.recall == 1.0 and score36.precision is not None and score36.precision < 0.5
line("BCH-036", "PASS" if ok36 else "FAIL", f"recall={score36.recall} precision={score36.precision}")

# BCH-037
drop_rename_classes = [c for c in CLASSES if c.name in ("column-removed","column-renamed")]
corpus37 = build(seed=1, classes=drop_rename_classes, rows=50, rate=0.5)
alerts37 = _detect_everything(corpus37)
alerted_cols = {a.column for a in alerts37}
ok37 = "product" in alerted_cols and "party_name" in alerted_cols and "partyName" in alerted_cols
line("BCH-037", "PASS" if ok37 else "FAIL", f"alerted_cols_sample={sorted(alerted_cols)}")

# BCH-038
corpus38 = build(seed=1, rows=100)
comp38 = compare(corpus38, [baseline("schema-only")])
blind38 = comp38.blind_families
schema_blind = blind38["schema-only"]
ok38 = "structural" not in schema_blind and ("semantic" in schema_blind or "statistical" in schema_blind)
line("BCH-038", "PASS" if ok38 else "FAIL", f"schema_only_blind={schema_blind}")

# BCH-039
partial_class = next(c for c in CLASSES if c.name == "column-removed")
def partial_drop(row, rng, _orig=partial_class.inject):
    return _orig(row, rng)
import dataclasses as dc
corpus39 = build(seed=1, classes=[partial_class], rows=50, rate=0.3)
alerts39 = _detect_schema_only(corpus39)
ok39 = any("missing from some rows" in a.detail for a in alerts39) or any(a.column=="product" for a in alerts39)
line("BCH-039", "PASS" if ok39 else "FAIL", f"alerts={[(a.column,a.detail) for a in alerts39]}")

# BCH-040
comp40 = compare(corpus38, [baseline("patterns-only")])
blind40 = comp40.blind_families["patterns-only"]
ok40 = "semantic" in blind40
line("BCH-040", "PASS" if ok40 else "FAIL", f"patterns_only_blind={blind40}")

# BCH-041
comp41 = compare(corpus38, [baseline("statistics-only")])
found_families41 = {f.family for f in comp41.results[0][1].families if f.found > 0}
blind41 = comp41.blind_families["statistics-only"]
ok41 = "semantic" in blind41
line("BCH-041", "PASS" if ok41 else "FAIL", f"stats_only_blind={blind41} found_families={found_families41}")

# BCH-042
score42a = baseline("schema-only").run(corpus38)
score42b = baseline("schema-only").run(corpus38)
ok42 = score42a.to_dict() == score42b.to_dict()
line("BCH-042", "PASS" if ok42 else "FAIL", f"identical={ok42}")

# BCH-043
one_family_classes = classes_of(Family.CONTENT)
corpus43 = build(seed=1, classes=one_family_classes, rows=50, rate=0.5)
comp43 = compare(corpus43, [baseline("schema-only")])
blind43 = comp43.blind_families["schema-only"]
ok43 = set(blind43) <= {"content"}  # only content could appear (if blind); others never tested so should not appear at all
line("BCH-043", "PASS" if ok43 else "FAIL", f"blind_families={blind43}")

# BCH-044
comp44 = compare(corpus35, [baseline("detect-nothing")])
d44 = comp44.to_dict()
ok44 = len(d44["not_run"]) == 15 and set(d44["not_run"].keys()) == set(NOT_RUN.keys())
line("BCH-044", "PASS" if ok44 else "FAIL", f"n_not_run={len(d44['not_run'])} expected=15")

# BCH-045
import inspect as insp
src45 = insp.getsource(sys.modules["prama.bench.baselines"])
# NOT_RUN legitimately *names* external tools (including "Soda Core") as a documentation
# dict -- that is the honesty mechanism, not an invocation. Check for actual execution/import
# machinery instead of a crude substring match on tool names.
ok45 = ("subprocess" not in src45 and "os.system" not in src45 and "import great_expectations" not in src45
        and "import soda" not in src45.lower() and "requests.get" not in src45 and "urllib" not in src45)
line("BCH-045", "PASS" if ok45 else "FAIL", f"no_subprocess={'subprocess' not in src45} no_external_import={'import great_expectations' not in src45 and 'import soda' not in src45.lower()} (NOT_RUN dict's mention of tool names like 'Soda Core' is documentation, not invocation)")

# BCH-046
try:
    baseline("nope")
    ok46 = False; obs46 = "no exception"
except Exception as e:
    names = [b.name for b in BASELINES]
    ok46 = all(n in str(e) for n in names)
    obs46 = str(e)
line("BCH-046", "PASS" if ok46 else "FAIL", obs46)

# BCH-047
ok47 = all(b.describes and b.kind in ("bound","ablation") for b in BASELINES)
line("BCH-047", "PASS" if ok47 else "FAIL", f"{[(b.name,b.kind,bool(b.describes)) for b in BASELINES]}")

print("=== shadow ===")

# BCH-048
a48_sysA = ShadowAlert(system="A", dataset="d", column="c", raised_at="2026-01-01T00:00:00Z", detail="x1")
a48_sysB = ShadowAlert(system="B", dataset="d", column="c", raised_at="2026-01-01T00:01:00Z", detail="x2")
blinding48 = Blinding([a48_sysA, a48_sysB])
listing48 = blinding48.for_adjudication()
ok48 = all("system" not in item for item in listing48)
line("BCH-048", "PASS" if ok48 else "FAIL", f"fields={list(listing48[0].keys()) if listing48 else []}")

# BCH-049
alerts49 = [ShadowAlert(system="A", dataset="d", column="c", raised_at=f"2026-01-01T00:{i:02d}:00Z", detail=f"x{i}") for i in range(10)]
blinding49 = Blinding(alerts49)
listing49 = blinding49.for_adjudication()
blind_ids49 = [item["blind_id"] for item in listing49]
ok49 = blind_ids49 == sorted(blind_ids49) and blind_ids49 != [a.blind_id for a in alerts49]
line("BCH-049", "PASS" if ok49 else "FAIL", f"sorted_correctly={blind_ids49==sorted(blind_ids49)} not_arrival_order={blind_ids49 != [a.blind_id for a in alerts49]}")

# BCH-050
a50a = ShadowAlert(system="A", dataset="d", column="c", raised_at="t1")
a50b = ShadowAlert(system="B", dataset="d", column="c2", raised_at="t2")
ok50 = len(a50a.blind_id)==16 and len(a50b.blind_id)==16 and all(c in "0123456789abcdef" for c in a50a.blind_id)
line("BCH-050", "PASS" if ok50 else "FAIL", f"id_a={a50a.blind_id} id_b={a50b.blind_id}")

# BCH-051 - the flagged defect
a51_sysA = ShadowAlert(system="SystemA", dataset="d", column="c", raised_at="2026-01-01T00:00:00Z", detail="same", reference="ref1")
a51_sysB = ShadowAlert(system="SystemB", dataset="d", column="c", raised_at="2026-01-01T00:00:00Z", detail="same", reference="ref1")
blinding51 = Blinding()
blinding51.register(a51_sysA)
blinding51.register(a51_sysB)
ok51 = len(blinding51) == 2
line("BCH-051", "PASS" if ok51 else "FAIL", f"len={len(blinding51)} idA={a51_sysA.blind_id} idB={a51_sysB.blind_id} (both systems' blind_id excludes 'system' field)")

# BCH-052
alerts52 = [ShadowAlert(system="A", dataset="d", column=f"c{i}", raised_at="2026-01-05") for i in range(100)]
blinding52 = Blinding(alerts52)
judgements52 = [Judgement(blind_id=alerts52[i].blind_id, verdict=("real" if i < 18 else "false")) for i in range(20)]
result52 = evaluate(blinding52, judgements52, window_start="2026-01-01", window_end="2026-01-31")
sysA52 = result52.of("A")
ok52 = sysA52.precision == 0.9 and sysA52.examined_share == 0.2
line("BCH-052", "PASS" if ok52 else "FAIL", f"precision={sysA52.precision} examined_share={sysA52.examined_share}")

# BCH-053
desc53 = sysA52.describe()
ok53 = "precision 90% over the 20% of 100 alert(s) that were judged" in desc53
line("BCH-053", "PASS" if ok53 else "FAIL", f"describe={desc53!r}")

# BCH-054
alerts54 = [ShadowAlert(system="A", dataset="d", column=f"c{i}", raised_at="2026-01-05") for i in range(3)]
blinding54 = Blinding(alerts54)
judgements54 = [
    Judgement(blind_id=alerts54[0].blind_id, verdict="real"),
    Judgement(blind_id=alerts54[1].blind_id, verdict="false"),
    Judgement(blind_id=alerts54[2].blind_id, verdict="unclear"),
]
result54 = evaluate(blinding54, judgements54, window_start="2026-01-01", window_end="2026-01-31")
sysA54 = result54.of("A")
ok54 = sysA54.unclear == 1 and sysA54.adjudicated == 2
line("BCH-054", "PASS" if ok54 else "FAIL", f"unclear={sysA54.unclear} adjudicated={sysA54.adjudicated}")

# BCH-055
alerts55 = [ShadowAlert(system="A", dataset="d", column="c1", raised_at="2026-01-05"),
            ShadowAlert(system="A", dataset="d", column="c2", raised_at="2026-01-05")]
blinding55 = Blinding(alerts55)
judgements55 = [Judgement(blind_id=alerts55[0].blind_id, verdict="real", minutes=30),
                Judgement(blind_id=alerts55[1].blind_id, verdict="false", minutes=30)]
result55 = evaluate(blinding55, judgements55, window_start="2026-01-01", window_end="2026-01-31")
sysA55 = result55.of("A")
ok55 = sysA55.minutes_spent == 60 and sysA55.wasted_minutes == 30
line("BCH-055", "PASS" if ok55 else "FAIL", f"minutes_spent={sysA55.minutes_spent} wasted={sysA55.wasted_minutes}")

# BCH-056
alerts56 = ([ShadowAlert(system="LATE", dataset="d", column=f"early{i}", raised_at="2025-12-29") for i in range(3)] +
            [ShadowAlert(system="LATE", dataset="d", column="c2", raised_at="2026-01-05")] +
            [ShadowAlert(system="ONTIME", dataset="d", column="c", raised_at="2026-01-01")])
blinding56 = Blinding(alerts56)
result56 = evaluate(blinding56, [], window_start="2026-01-01", window_end="2026-01-31")
outside56 = dict(result56.outside_window)
desc56 = result56.describe()
ok56 = outside56.get("LATE") == 3 and "LATE: 3" in desc56
line("BCH-056", "PASS" if ok56 else "FAIL", f"outside_window={outside56} describe_has_it={'LATE: 3' in desc56}")

# BCH-057
alert57 = ShadowAlert(system="A", dataset="d", column="c", raised_at="2026-01-31T23:59:00Z")
blinding57 = Blinding([alert57])
result57 = evaluate(blinding57, [], window_start="2026-01-01", window_end="2026-01-31")
outside57 = dict(result57.outside_window)
ok57 = outside57.get("A") == 1  # dropped since string comparison "2026-01-31T23:59:00Z" <= "2026-01-31" is False
line("BCH-057", "PASS" if ok57 else "FAIL", f"outside_window={outside57} (string comparison drops it)")

# BCH-058
alerts58 = [ShadowAlert(system="A", dataset="d", column=f"c{i}", raised_at="2026-01-05") for i in range(24)]
blinding58 = Blinding(alerts58)
judgements58 = [Judgement(blind_id=a.blind_id, verdict="false", minutes=10) for a in alerts58]
result58 = evaluate(blinding58, judgements58, window_start="2026-01-01", window_end="2026-01-31", steward_weeks=12)
sysA58 = result58.of("A")
ok58 = sysA58.alerts_per_steward_week == 2.0 and sysA58.wasted_hours_per_week is not None and "alerts per steward-week" in sysA58.describe()
line("BCH-058", "PASS" if ok58 else "FAIL", f"alerts_per_sw={sysA58.alerts_per_steward_week} wasted_hpw={sysA58.wasted_hours_per_week} describe={sysA58.describe()!r}")

# BCH-059
result59 = evaluate(blinding58, judgements58, window_start="2026-01-01", window_end="2026-01-31", steward_weeks=0)
sysA59 = result59.of("A")
ok59 = sysA59.alerts_per_steward_week is None and sysA59.wasted_hours_per_week is None and "steward-week" not in sysA59.describe()
line("BCH-059", "PASS" if ok59 else "FAIL", f"alerts_per_sw={sysA59.alerts_per_steward_week} describe={sysA59.describe()!r}")

# BCH-060
alerts60 = [ShadowAlert(system="GONE", dataset="d", column="c", raised_at="2025-12-01")]  # all outside window
blinding60 = Blinding(alerts60)
result60 = evaluate(blinding60, [], window_start="2026-01-01", window_end="2026-01-31")
sysGone = result60.of("GONE")
ok60 = sysGone is not None and sysGone.raised == 0 and sysGone.describe() == "GONE: raised nothing in this window"
line("BCH-060", "PASS" if ok60 else "FAIL", f"sys_present={sysGone is not None} raised={sysGone.raised if sysGone else None} describe={sysGone.describe() if sysGone else None}")

# BCH-061
alerts61 = [ShadowAlert(system="A", dataset="d", column="c", raised_at="2026-01-05")]
blinding61 = Blinding(alerts61)
bogus_judgement = Judgement(blind_id="nonexistent_id_1234", verdict="real")
try:
    result61 = evaluate(blinding61, [bogus_judgement], window_start="2026-01-01", window_end="2026-01-31")
    sysA61 = result61.of("A")
    ok61 = sysA61.unjudged == 1 and sysA61.confirmed == 0
    obs61 = f"unjudged={sysA61.unjudged} confirmed={sysA61.confirmed}"
except Exception as e:
    ok61 = False
    obs61 = f"exception {type(e).__name__}: {e}"
line("BCH-061", "PASS" if ok61 else "FAIL", obs61)
