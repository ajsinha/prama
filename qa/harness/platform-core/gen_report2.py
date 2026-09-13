# -*- coding: utf-8 -*-
import json

SP = "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/plat1"

titles = json.load(open(f"{SP}/titles.json", encoding="utf-8"))

rows = []
for line in open(f"{SP}/consolidated.tsv", encoding="utf-8"):
    id_, result, obs = line.rstrip("\n").split("\t", 2)
    rows.append((id_, result, obs))

def sortkey(id_):
    area, num = id_.split("-")
    return (area, int(num))
rows.sort(key=lambda r: sortkey(r[0]))

total = len(rows)
counts = {"PASS": 0, "FAIL": 0, "BLOCKED": 0}
for _, r, _ in rows:
    counts[r] += 1

exec("open('%s/failure_details.py').read()" % SP) if False else None
import importlib.util
spec = importlib.util.spec_from_file_location("failure_details", f"{SP}/failure_details.py")
fd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fd)
F = fd.F

lines = []
lines.append("# Platform & core — QA execution log")
lines.append("")
lines.append(f"**{total} cases executed** (CFG-001..320, DB-001..295). "
             f"**{counts['PASS']} PASS**, **{counts['FAIL']} FAIL**, **{counts['BLOCKED']} BLOCKED**. "
             f"Pass rate **{counts['PASS']/total*100:.1f}%** ({counts['PASS']}/{total}).")
lines.append("")
lines.append("Every case below was executed: real SQLite files (file-backed, matching the "
             "async/sync engine split the codebase actually uses) throughout, and a live "
             "PostgreSQL 16 server (`postgresql://prama:prama@127.0.0.1:55433/prama`, via a "
             "Docker container already running on this host) for every case naming PostgreSQL "
             "specifically. Nothing below is inferred from reading source; every PASS and FAIL "
             "is a reproduced, observed result. Four PostgreSQL-async cases (DB-070, DB-072, "
             "DB-148, DB-279) are FAIL rather than BLOCKED: they were run against the live "
             "server, and what running them found is that the async PostgreSQL engine cannot be "
             "constructed at all in this build — a genuine, reproduced defect (root-caused under "
             "DB-070), not an absent test. MON-, INC-, RPT-, BCH- and OPS- are out of scope for "
             "this log.")
lines.append("")
lines.append("## Failures ranked by severity")
lines.append("")
sev_order = {"P1": 0, "P2": 1, "P3": 2}
fail_ids = [id_ for id_, r, _ in rows if r == "FAIL"]
fail_ids_sorted = sorted(fail_ids, key=lambda i: (sev_order.get(F[i]["severity"], 9), sortkey(i)))
for id_ in fail_ids_sorted:
    d = F[id_]
    title = titles.get(id_, "")
    lines.append(f"- **{id_}** ({d['severity']}) — {title}")
lines.append("")
lines.append("## Per-case results")
lines.append("")
lines.append("| Id | Result | Observed |")
lines.append("|---|---|---|")
for id_, result, obs in rows:
    obs_md = obs.replace("|", "\\|").replace("\n", " ").strip()
    if len(obs_md) > 500:
        obs_md = obs_md[:500] + "…"
    lines.append(f"| `{id_}` | {result} | {obs_md} |")
lines.append("")
lines.append("## Failure details")
lines.append("")
for id_ in sorted(fail_ids, key=sortkey):
    d = F[id_]
    title = titles.get(id_, "")
    lines.append(f"### {id_} · {title}")
    lines.append(f"- **Expected:** {d['expected']}")
    obs_row = next(o for i, r, o in rows if i == id_)
    obs_row = obs_row.replace("\n", " ")
    lines.append(f"- **Observed:** {obs_row}")
    repro = " ".join(d["reproduce"].split())
    lines.append(f"- **Reproduce:** {repro}")
    lines.append(f"- **Severity:** {d['severity']}")
    lines.append(f"- **Assessment:** {d['assessment']}. {d['note']}")
    lines.append("")

open("/home/ashutosh/PycharmProjects/prama/docs/qa/logs/platform-core.md", "w", encoding="utf-8").write("\n".join(lines))
print("WROTE", len(lines), "lines; counts", counts, "total", total)
