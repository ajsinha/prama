import sys, subprocess, inspect
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/trust")
from reclib import line
from prama.security.residency import Policy, Decision, Verdict, refusals
from prama.security.egress import Gate, EGRESS_POINTS, ResidencyRefused, point, _remedy_for

# SEC-015: no rule -> unrestricted, describes correctly
p = Policy.of(None)
d = p.decide(destination="US")
ok = d.verdict is Verdict.UNRESTRICTED and d.may_proceed and "absence of a" in d.describe()
line("SEC-015", "PASS" if ok else "FAIL", f"verdict={d.verdict} may_proceed={d.may_proceed} describe={d.describe()!r}")

# SEC-016: movement inside rule permitted, names both
p = Policy.of("EU,EEA")
d = p.decide(destination="eu", jurisdiction="EU")
ok = d.verdict is Verdict.PERMITTED and "eu".upper() in d.describe().upper() and "EU" in d.describe()
line("SEC-016", "PASS" if ok else "FAIL", f"verdict={d.verdict} describe={d.describe()!r}")

# SEC-017: destination outside rule refused
p = Policy.of("EU")
d = p.decide(destination="US", jurisdiction="EU")
ok = d.verdict is Verdict.REFUSED and "US" in d.describe() and "EU" in d.describe()
line("SEC-017", "PASS" if ok else "FAIL", f"verdict={d.verdict} describe={d.describe()!r}")

# SEC-018: destination in, jurisdiction out (and vice versa) both refused
p = Policy.of("EU")
d1 = p.decide(destination="EU", jurisdiction="US")
d2 = p.decide(destination="US", jurisdiction="EU")
ok = not d1.may_proceed and not d2.may_proceed
line("SEC-018", "PASS" if ok else "FAIL", f"dest=EU,jur=US -> {d1.verdict} may_proceed={d1.may_proceed}; dest=US,jur=EU -> {d2.verdict} may_proceed={d2.may_proceed}")

# SEC-019: undeclared jurisdiction refused, not unrestricted
p = Policy.of("EU")
d = p.decide(destination="EU", jurisdiction="")
ok = d.verdict is Verdict.UNDECLARED and not d.may_proceed and d.is_undeclared
line("SEC-019", "PASS" if ok else "FAIL", f"verdict={d.verdict} may_proceed={d.may_proceed} is_undeclared={d.is_undeclared}")

# SEC-020: undeclared refusal carries different remedy from destination refusal
p = Policy.of("EU")
d_undeclared = p.decide(destination="EU", jurisdiction="")
d_dest_refused = p.decide(destination="US", jurisdiction="EU")
d_no_dest = p.decide(destination="")
try:
    Gate(policy=p, tenant_id="t").require("evidence-export", destination="", jurisdiction="EU")
    r_no_dest = None
except ResidencyRefused as e:
    r_no_dest = e.remedy
try:
    Gate(policy=p, tenant_id="t").require("evidence-export", destination="EU", jurisdiction="")
    r_undecl = None
except ResidencyRefused as e:
    r_undecl = e.remedy
try:
    Gate(policy=p, tenant_id="t").require("evidence-export", destination="US", jurisdiction="EU")
    r_dest = None
except ResidencyRefused as e:
    r_dest = e.remedy
distinct = len({r_no_dest, r_undecl, r_dest}) == 3
line("SEC-020", "PASS" if distinct else "FAIL", f"undeclared_remedy={r_undecl!r} dest_refused_remedy={r_dest!r} no_dest_remedy={r_no_dest!r} all_distinct={distinct}")

# SEC-021: no destination refused, not passed
p = Policy.of("EU")
d = p.decide(destination="")
ok = d.verdict is Verdict.REFUSED and d.destination == "(unstated)" and d.destination_unstated
line("SEC-021", "PASS" if ok else "FAIL", f"verdict={d.verdict} destination={d.destination!r} destination_unstated={d.destination_unstated}")

# SEC-022: no destination under no rule is permitted (asymmetry with SEC-021)
p = Policy.of(None)
d = p.decide(destination="")
ok = d.verdict is Verdict.UNRESTRICTED and d.destination == "(unstated)"
line("SEC-022", "PASS" if ok else "FAIL", f"verdict={d.verdict} destination={d.destination!r} -- asymmetry with SEC-021 confirmed: unrestricted branch runs before the missing-destination branch")

# SEC-023: comma string and list form both accepted, identical result
p1 = Policy.of("eu, eea ")
p2 = Policy.of(["EU", "EEA"])
ok = p1 == p2 and p1.allowed == ("EEA", "EU")
line("SEC-023", "PASS" if ok else "FAIL", f"p1.allowed={p1.allowed} p2.allowed={p2.allowed} equal={p1==p2}")

# SEC-024: empty or whitespace rule is unrestricted
p1 = Policy.of("")
p2 = Policy.of(" , ")
p3 = Policy.of([])
ok = p1.is_unrestricted and p2.is_unrestricted and p3.is_unrestricted
line("SEC-024", "PASS" if ok else "FAIL", f"Policy.of('').is_unrestricted={p1.is_unrestricted} Policy.of(' , ').is_unrestricted={p2.is_unrestricted} Policy.of([]).is_unrestricted={p3.is_unrestricted}")

# SEC-025: case/whitespace insensitive
p = Policy.of("EU")
d = p.decide(destination=" eu ", jurisdiction="Eu")
ok = d.verdict is Verdict.PERMITTED
line("SEC-025", "PASS" if ok else "FAIL", f"verdict={d.verdict}")

# SEC-026: every decision carries a distinct sentence naming subject/destination/rule
p = Policy.of("EU")
d_unres = Policy.of(None).decide(destination="US", subject="the export")
d_perm = p.decide(destination="EU", jurisdiction="EU", subject="the export")
d_ref = p.decide(destination="US", jurisdiction="EU", subject="the export")
d_undecl = p.decide(destination="EU", jurisdiction="", subject="the export")
sentences = [d_unres.describe(), d_perm.describe(), d_ref.describe(), d_undecl.describe()]
ok = len(set(sentences)) == 4 and all("the export" in s for s in sentences)
line("SEC-026", "PASS" if ok else "FAIL", f"n_distinct={len(set(sentences))} all_name_subject={all('the export' in s for s in sentences)}")

# SEC-027: refusals() returns only what was blocked, in order
decisions = [d_unres, d_perm, d_ref, d_undecl]
r = refusals(decisions)
ok = r == (d_ref, d_undecl)
line("SEC-027", "PASS" if ok else "FAIL", f"refusals={[x.verdict for x in r]} expected=[REFUSED, UNDECLARED]")

# SEC-028: decision serialises with everything needed to argue
d_dict = d_ref.to_dict()
ok = set(d_dict.keys()) == {"verdict","may_proceed","destination","rule","jurisdiction","subject","message"}
line("SEC-028", "PASS" if ok else "FAIL", f"keys={sorted(d_dict.keys())}")

# SEC-029: no bypass predicate for "internal"/"self-hosted"
r = subprocess.run(["grep", "-rniE", "self.hosted|internal.*bypass|is_internal", "/home/ashutosh/PycharmProjects/prama/src/prama/security/residency.py", "/home/ashutosh/PycharmProjects/prama/src/prama/security/egress.py"], capture_output=True, text=True)
ok = not r.stdout.strip()
line("SEC-029", "PASS" if ok else "FAIL", f"grep hits: {r.stdout.strip() or '(none)'}")

# SEC-030: policy describes itself in one line
p_none = Policy.of(None)
p_rule = Policy.of("EU,EEA")
d1 = p_none.describe()
d2 = p_rule.describe()
ok = d1 == "no residency rule: data may go anywhere" and d2 == "data must stay in EEA, EU"
line("SEC-030", "PASS" if ok else "FAIL", f"unrestricted={d1!r} with_rule={d2!r}")

print("SECTION SEC-015..030 DONE")
