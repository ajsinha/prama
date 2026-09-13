import pickle, re

D = "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/dom"
cases, ranges = pickle.load(open(f"{D}/cases.pkl", "rb"))
catinfo = pickle.load(open(f"{D}/catinfo.pkl", "rb"))
repro = pickle.load(open(f"{D}/repro.pkl", "rb"))

PREFIX_ORDER = ["PCK", "CLS", "RCN", "CTR", "IMP", "INT", "LIN"]

def all_ids():
    for p in PREFIX_ORDER:
        for i in range(1, ranges[p]+1):
            yield f"{p}-{i:03d}"

total = len(cases)
n_pass = sum(1 for r,_ in cases.values() if r == "PASS")
n_fail = sum(1 for r,_ in cases.values() if r == "FAIL")
n_blocked = sum(1 for r,_ in cases.values() if r == "BLOCKED")
pass_rate = n_pass / total * 100

# severity counts for fails, ranked
fail_ids = [cid for cid in all_ids() if cases[cid][0] == "FAIL"]
def sev(cid):
    return catinfo.get(cid, {}).get("priority", "P9")
fail_ids_ranked = sorted(fail_ids, key=lambda c: (sev(c), c))

lines = []
lines.append("# Domain knowledge QA execution log")
lines.append("")
lines.append(f"**Total:** {total} · **Passed:** {n_pass} · **Failed:** {n_fail} · **Blocked:** {n_blocked} "
              f"· **Pass rate:** {pass_rate:.1f}%")
lines.append("")
lines.append("Executed against the tree as it stands (branch `develop`), following "
              "docs/qa/catalogue/domain.md and docs/qa/logs/README.md. Every PASS below was "
              "run; every FAIL was reproduced a second time before being recorded; every BLOCKED "
              "states why it could not be executed. Nothing here was marked PASS on the strength "
              "of the code looking correct.")
lines.append("")
lines.append("## Failures ranked by severity")
lines.append("")
lines.append("| Id | Severity | Title | Assessment |")
lines.append("|---|---|---|---|")
for cid in fail_ids_ranked:
    title = catinfo.get(cid, {}).get("title", "")
    lines.append(f"| [{cid}](#{cid.lower()}) | {sev(cid)} | {title} | defect |")
lines.append("")
lines.append(f"Blocked cases (not counted as pass or fail): {', '.join(sorted(cases.keys() & set(c for c in cases if cases[c][0]=='BLOCKED'), key=lambda c: (c.split('-')[0], int(c.split('-')[1]))))}")
lines.append("")
lines.append("## Per-case results")
lines.append("")
lines.append("| Id | Result | Observed |")
lines.append("|---|---|---|")
for cid in all_ids():
    result, obs = cases[cid]
    # escape pipes in observed text for markdown table
    obs_short = obs.replace("|", "\\|").replace("\n", " ")
    if len(obs_short) > 400:
        obs_short = obs_short[:400] + "…"
    lines.append(f"| `{cid}` | {result} | {obs_short} |")
lines.append("")

lines.append("## Failures, in detail")
lines.append("")
lines.append("Each reproduction snippet below is the exact block executed against this tree "
              "(`prama.__file__` under `src/prama`, via the project venv). Snippets marked "
              "`(executed as part of ...)` reference a few shared helpers defined earlier in "
              "that same harness script -- most commonly `pyref(name, args)` "
              "(`FUNCS[name].evaluate(list(args))`, where `FUNCS` maps a banking cross-field "
              "function name to its `prama.pql.functions.Function`), and `run_sql_all(template, args)` "
              "(renders the function's SQL template with literal arguments and executes it on "
              "SQLite, DuckDB and PostgreSQL in turn). Where a snippet calls `R(id, ok, msg)`, "
              "that is this log's own recorder, not part of the product; `ok` is the pass/fail "
              "condition being asserted and `msg` is exactly the Observed text above it.")
lines.append("")

for cid in fail_ids_ranked:
    info = catinfo.get(cid, {})
    title = info.get("title", "")
    expected = info.get("expected", "")
    priority = info.get("priority", "?")
    result, obs = cases[cid]
    lines.append(f"### {cid} · {title}")
    lines.append(f"- **Expected:** {expected}")
    lines.append(f"- **Observed:** {obs}")
    if cid in repro:
        script, code = repro[cid]
        if script == "manual CLI":
            lines.append(f"- **Reproduce:** run from the repo root (`cd /home/ashutosh/PycharmProjects/prama`):")
            lines.append("  ```bash")
            for cl in code.splitlines():
                lines.append(f"  {cl}")
            lines.append("  ```")
        else:
            lines.append(f"- **Reproduce:** (executed as part of `{script}`, block `{cid}`, run from the repo root with `src` on `PYTHONPATH` against the venv at `.venv/bin/python`)")
            lines.append("  ```python")
            for cl in code.splitlines():
                lines.append(f"  {cl}")
            lines.append("  ```")
    else:
        lines.append(f"- **Reproduce:** see the CLI commands quoted in Observed above; run directly against the repo with `PATH=.venv/bin:$PATH`.")
    lines.append(f"- **Severity:** {priority}")
    lines.append("- **Assessment:** defect")
    lines.append("")

lines.append("Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.")

out = "\n".join(lines)
open(f"{D}/domain_log_draft.md", "w").write(out)
print(f"Wrote {len(out)} bytes, {len(lines)} lines")
print(f"PASS={n_pass} FAIL={n_fail} BLOCKED={n_blocked} rate={pass_rate:.1f}%")
