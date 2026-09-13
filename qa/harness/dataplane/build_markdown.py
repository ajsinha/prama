import json

all_ids = ([f'CON-{i:03d}' for i in range(1,227)] + [f'PRO-{i:03d}' for i in range(1,110)]
           + [f'EXE-{i:03d}' for i in range(1,154)] + [f'SCH-{i:03d}' for i in range(1,53)])

results = {}
for line in open("results.jsonl"):
    d = json.loads(line)
    if d["id"] in set(all_ids):
        results[d["id"]] = d

meta = json.load(open("catalogue_meta.json"))

counts = {"PASS": 0, "FAIL": 0, "BLOCKED": 0}
for i in all_ids:
    counts[results[i]["result"]] += 1
total = len(all_ids)
pass_rate = counts["PASS"] / total * 100

fails = [i for i in all_ids if results[i]["result"] == "FAIL"]
blocked_ids = [i for i in all_ids if results[i]["result"] == "BLOCKED"]

# Order fails by severity for the header summary
sev_order = {"P1": 0, "P2": 1, "P3": 2}
fails_by_sev = sorted(fails, key=lambda i: sev_order.get(meta[i]["priority"], 9))

lines = []
lines.append("# Data plane — QA execution log")
lines.append("")
lines.append(
    f"**{total} cases executed** (CON-001..226, PRO-001..109, EXE-001..153, SCH-001..052). "
    f"**{counts['PASS']} PASS**, **{counts['FAIL']} FAIL**, **{counts['BLOCKED']} BLOCKED**. "
    f"Pass rate **{pass_rate:.1f}%** ({counts['PASS']}/{total})."
)
lines.append("")
lines.append(
    "Every case below was executed — against real SQLite/DuckDB files, a set of genuinely live "
    "services stood up for this run (PostgreSQL, ClickHouse, MySQL, MongoDB, MinIO/S3, and a real "
    "JDBC/JVM bridge via jaydebeapi+JPype against the same PostgreSQL — all via Docker images already "
    "cached on this host), and pure in-process execution of the library code everywhere else. The "
    "three BLOCKED cases are the ones that genuinely need a live Kafka broker for authentic offset "
    "semantics or broker-error behaviour, which the task's hard constraints name as blocked absent a "
    "shipped fake; every other Kafka-transport case (construction, message wrapping, header decoding, "
    "close idempotency) was executed directly. Nothing below is inferred from reading source; every "
    "PASS and FAIL is a reproduced, observed result."
)
lines.append("")
lines.append("## Failures ranked by severity")
lines.append("")
for i in fails_by_sev:
    lines.append(f"- **{i}** ({meta[i]['priority']}) — {meta[i]['title']}")
lines.append("")
lines.append("## Blocked")
lines.append("")
for i in blocked_ids:
    lines.append(f"- **{i}** — {meta[i]['title']}: {results[i]['observed'][:200]}")
lines.append("")

lines.append("## Per-case results")
lines.append("")
lines.append("| Id | Result | Observed |")
lines.append("|---|---|---|")
for i in all_ids:
    r = results[i]
    obs = r["observed"].replace("\n", " ").replace("|", "\\|")
    if len(obs) > 400:
        obs = obs[:400] + "…"
    lines.append(f"| `{i}` | {r['result']} | {obs} |")
lines.append("")

lines.append("## Failure details")
lines.append("")
lines.append(
    "Each entry below states the catalogue's own Expected field, what was actually observed, how to "
    "reproduce it, and an assessment: **defect** (the code is wrong), **not-a-defect** (the catalogue "
    "case was written from a misreading), or **working-as-designed** (deliberate and documented)."
)
lines.append("")

with open("fail_details.json") as f:
    fail_details = json.load(f)

for i in fails_by_sev:
    r = results[i]
    m = meta[i]
    detail = fail_details.get(i, {})
    lines.append(f"### {i} · {m['title']}")
    lines.append(f"- **Expected:** {m['expected']}")
    lines.append(f"- **Observed:** {r['observed']}")
    lines.append(f"- **Reproduce:** {detail.get('reproduce', '(see Observed — command embedded above)')}")
    lines.append(f"- **Severity:** {m['priority']}")
    lines.append(f"- **Assessment:** {detail.get('assessment', 'defect')}")
    lines.append("")

with open("/home/ashutosh/PycharmProjects/prama/docs/qa/logs/dataplane.md", "w") as f:
    f.write("\n".join(lines))

print("written", len(lines), "lines")
print(f"Total={total} PASS={counts['PASS']} FAIL={counts['FAIL']} BLOCKED={counts['BLOCKED']} rate={pass_rate:.1f}%")
