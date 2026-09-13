import re, collections

SP = "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/plat1"
raw = open(f"{SP}/results.tsv", encoding="utf-8").read().splitlines()

# alias sub-case ids to their parent
ALIAS = {
    "CFG-021-default": "CFG-021",
    "CFG-099b": "CFG-099",
    "CFG-100a": "CFG-100",
    "CFG-100b": "CFG-100",
    "CFG-116a": "CFG-116",
    "CFG-116b": "CFG-116",
    "DB-076-exec": "DB-076",
    "DB-215a": "DB-215",
    "DB-215b": "DB-215",
    "DB-258-persist": "DB-258",
    "DB-259b": "DB-259",
    "DB-264b": "DB-264",
    "DB-287b": "DB-287",
}

entries = collections.defaultdict(list)  # id -> list of (result, observed)
pattern = re.compile(r"^([A-Z]+-[0-9]+[a-zA-Z-]*): (PASS|FAIL|BLOCKED|None) :: (.*)$")
unparsed = []
for line in raw:
    line = line.rstrip("\n")
    if not line.strip():
        continue
    m = pattern.match(line)
    if not m:
        unparsed.append(line)
        continue
    raw_id, result, obs = m.groups()
    real_id = ALIAS.get(raw_id, raw_id)
    entries[real_id].append((result, obs, raw_id))

print("UNPARSED LINES:", len(unparsed))
for u in unparsed[:20]:
    print("  ", u[:150])

# Build final per-id result: if any sub-entry FAIL -> FAIL; if any None(blocked)->BLOCKED unless also FAIL; else PASS
final = {}
for id_, items in entries.items():
    results_seen = [r for r, o, rid in items]
    if any(r == "FAIL" for r in results_seen):
        final_result = "FAIL"
    elif any(r == "BLOCKED" or r == "None" for r in results_seen):
        final_result = "BLOCKED"
    else:
        final_result = "PASS"
    # observed: concatenate distinct observations (dedup consecutive same-id sub-checks)
    obs_parts = []
    for r, o, rid in items:
        label = f"[{rid}] " if rid != id_ else ""
        obs_parts.append(f"{label}{o}")
    final[id_] = (final_result, " || ".join(obs_parts))

# verify coverage
expected_cfg = {f"CFG-{i:03d}" for i in range(1, 321)}
expected_db = {f"DB-{i:03d}" for i in range(1, 296)}
expected = expected_cfg | expected_db
got = set(final.keys())
missing = sorted(expected - got, key=lambda x: (x.split("-")[0], int(x.split("-")[1])))
extra = sorted(got - expected)
print("MISSING:", len(missing), missing[:40])
print("EXTRA (not in expected range):", len(extra), extra[:40])
print("TOTAL FINAL IDS:", len(got))

# write consolidated tsv sorted by id order
def sortkey(id_):
    area, num = id_.split("-")
    return (area, int(num))

with open(f"{SP}/consolidated.tsv", "w", encoding="utf-8") as f:
    for id_ in sorted(final.keys(), key=sortkey):
        result, obs = final[id_]
        obs_clean = obs.replace("\t", " ").replace("\n", " ")
        f.write(f"{id_}\t{result}\t{obs_clean}\n")

counts = collections.Counter(r for r, o in final.values())
print("COUNTS:", counts)
