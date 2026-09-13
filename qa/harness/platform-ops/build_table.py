import re

SCRATCH = "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/plat2"

with open(f"{SCRATCH}/all_scripted.txt", encoding="utf-8") as f:
    text = f.read()

rows = {}
pattern = re.compile(r"^([A-Z]+-\d+): (PASS|FAIL) :: (.*)$")
for line in text.splitlines():
    m = pattern.match(line)
    if m:
        id_, result, observed = m.groups()
        # keep the LAST occurrence (in case of reruns appended multiple times)
        rows[id_] = (result, observed)

print(f"total scripted rows: {len(rows)}")
for prefix, count in [("MON", 140), ("INC", 73), ("RPT", 95), ("BCH", 61)]:
    have = sum(1 for k in rows if k.startswith(prefix + "-"))
    print(prefix, have, "expected", count)

import pickle
with open(f"{SCRATCH}/rows.pkl", "wb") as f:
    pickle.dump(rows, f)
