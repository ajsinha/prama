import re, sys

D = "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/dom"

cases = {}  # id -> (result, observed)
order = []

line_re = re.compile(r'^([A-Z]+-\d+)(b)?: (PASS|FAIL)\b.*?:: (.*)$')

with open(f"{D}/results.txt") as f:
    for line in f:
        line = line.rstrip("\n")
        m = line_re.match(line)
        if not m:
            continue
        cid, suffix, result, obs = m.groups()
        if suffix:  # skip sub-entries like PCK-189b
            continue
        if cid in cases:
            # keep the LAST occurrence (later runs supersede earlier placeholder runs)
            pass
        cases[cid] = [result, obs]
        if cid not in order:
            order.append(cid)

print(f"Total parsed case rows (unique ids, last-wins): {len(cases)}")

# Now apply manual overrides / reclassifications determined during analysis.
# Format: id -> (new_result, assessment_note_appended)
OVERRIDES = {
    "PCK-096": ("FAIL", None),
    "PCK-097": ("PASS", None),
    "PCK-120": ("FAIL", None),
    "PCK-186": ("PASS", None),
    "PCK-208": ("FAIL", None),
    "PCK-054": ("BLOCKED", None),
    "CLS-089": ("PASS", None),
    "CLS-097": ("BLOCKED", None),
    "INT-024": ("PASS", None),
    "RCN-020": ("BLOCKED", None),
    "RCN-076": ("PASS", "Established the deterministic answer the catalogue asked for; the tradeoff itself (recurrence after a long clearance keeps the original first_seen) is called out by the catalogue's own Why as intentional for continuous re-detection, so this is a stated behaviour rather than a hidden defect."),
    "CTR-039": ("BLOCKED", "Export refusal paths were verified (see CTR-040), but the actual export-then-reimport round trip over a live declared dataset was never executed -- no tenant/dataset was available in this environment."),
    "RCN-060": ("FAIL", "Original test logic had the pass/fail boolean inverted (reported PASS when the observed kind was GENUINE, not the Expected MISSING). Re-judged: this is a confirmed genuine defect -- a normalisation step whose text coincidentally contains the substring 'carry no' reclassifies a truly missing record as GENUINE."),
}

for cid, (new_result, note) in OVERRIDES.items():
    if cid not in cases:
        print(f"WARNING: override for {cid} but no case row found")
        continue
    old_result, obs = cases[cid]
    cases[cid][0] = new_result
    if note:
        cases[cid][1] = obs + " | ASSESSMENT NOTE: " + note

# Sanity: report counts
from collections import Counter
c = Counter(v[0] for v in cases.values())
print(c)

# Check for missing ids across all expected ranges
ranges = {"PCK": 212, "CLS": 135, "RCN": 110, "CTR": 62, "IMP": 55, "INT": 43, "LIN": 63}
missing = []
for prefix, n in ranges.items():
    for i in range(1, n+1):
        cid = f"{prefix}-{i:03d}"
        if cid not in cases:
            missing.append(cid)
print("Missing ids:", missing)

import pickle
with open(f"{D}/cases.pkl", "wb") as f:
    pickle.dump((cases, ranges), f)
