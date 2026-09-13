import json, re

all_ids = ([f'CON-{i:03d}' for i in range(1,227)] + [f'PRO-{i:03d}' for i in range(1,110)]
           + [f'EXE-{i:03d}' for i in range(1,154)] + [f'SCH-{i:03d}' for i in range(1,53)])

results = {}
for line in open("results.jsonl"):
    d = json.loads(line)
    if d["id"] in set(all_ids):
        results[d["id"]] = d  # last write wins

missing = [i for i in all_ids if i not in results]
print("missing:", missing)
assert not missing, "missing cases!"

counts = {"PASS": 0, "FAIL": 0, "BLOCKED": 0}
for i in all_ids:
    counts[results[i]["result"]] += 1

total = len(all_ids)
pass_rate = counts["PASS"] / total * 100

print(f"Total={total} PASS={counts['PASS']} FAIL={counts['FAIL']} BLOCKED={counts['BLOCKED']} rate={pass_rate:.1f}%")

# Save a JSON summary for building the markdown by hand/script
with open("compiled_summary.json", "w") as f:
    json.dump({"counts": counts, "total": total, "pass_rate": pass_rate}, f, indent=2)

fails = [i for i in all_ids if results[i]["result"] == "FAIL"]
blocked = [i for i in all_ids if results[i]["result"] == "BLOCKED"]
print(f"\n{len(fails)} FAILs:", fails)
print(f"\n{len(blocked)} BLOCKED:", blocked)
