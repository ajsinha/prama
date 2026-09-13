import sys, pickle
sys.path.insert(0, "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/plat2")
from ops_rows import OPS_ROWS

SCRATCH = "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/plat2"

with open(f"{SCRATCH}/rows.pkl", "rb") as f:
    scripted = pickle.load(f)

def id_key(id_):
    prefix, num = id_.rsplit("-", 1)
    return (prefix, int(num))

all_rows = {}
for id_, (result, observed) in scripted.items():
    all_rows[id_] = (result, observed)
for id_, result, observed in OPS_ROWS:
    all_rows[id_] = (result, observed)

assert len(all_rows) == 443, len(all_rows)

order = ["MON", "INC", "RPT", "BCH", "OPS"]
sorted_ids = sorted(all_rows.keys(), key=lambda i: (order.index(i.split("-")[0]), int(i.split("-")[1])))

total = len(sorted_ids)
n_pass = sum(1 for i in sorted_ids if all_rows[i][0] == "PASS")
n_fail = sum(1 for i in sorted_ids if all_rows[i][0] == "FAIL")
n_blocked = sum(1 for i in sorted_ids if all_rows[i][0] == "BLOCKED")
assert n_pass + n_fail + n_blocked == total
pass_rate = n_pass / total * 100

print(f"total={total} pass={n_pass} fail={n_fail} blocked={n_blocked} rate={pass_rate:.1f}%")

def esc(s):
    return s.replace("|", "\\|").replace("\n", " ")

lines = []
lines.append("# Platform Ops — QA execution log")
lines.append("")
lines.append(
    f"**{total} cases executed** (MON-001..140, INC-001..073, RPT-001..095, BCH-001..061, "
    f"OPS-001..074). **{n_pass} PASS**, **{n_fail} FAIL**, **{n_blocked} BLOCKED**. "
    f"Pass rate **{pass_rate:.1f}%** ({n_pass}/{total})."
)
lines.append("")
lines.append(
    "Every case below was executed, not inferred from reading source. Drift, detector and "
    "scoring cases are pure functions driven directly with fixed seeds; the monitor, coldstart, "
    "cards, tournament and benchmark cases exercise the real classes end to end; the incident "
    "correlator and RCA cases build real lineage graphs; the alert router cases dispatch real "
    "`Alert`/`Router` objects; the report cases render real Jinja templates, real SVG charts and "
    "real WCAG contrast arithmetic; the benchmark-corpus cases build the real 28-class corpus and "
    "score real baselines against it; the deployment cases render the chart with a real `helm` "
    "binary (fetched into the scratchpad, since none was preinstalled), build and run "
    "`run_prama_web.py` as a real subprocess against real SQLite and PostgreSQL databases "
    "(including a throwaway `postgres:16-alpine` container started for this pass), send real "
    "POSIX signals to a real running server, and scan the real git history. "
    "CFG-, DB- and the round-1 surface cases are out of scope for this log; see "
    "`qa/logs/platform-core.md` for the former."
)
lines.append("")
lines.append(
    "**A note on the repository move.** Partway through this pass, `docs/qa/` was renamed to "
    "`qa/` by a concurrent session (confirmed: the catalogue content is unchanged, only its path "
    "and a handful of internal links moved). This log is written to the new location, "
    "`qa/logs/platform-ops.md`, rather than the `docs/qa/logs/platform-ops.md` this pass was "
    "originally pointed at, since that directory no longer exists."
)
lines.append("")

# Failures ranked by severity -- infer severity heuristically by ordering: OPS/RPT security-ish
# items first is not available (no explicit priority captured in observed text), so rank by
# a fixed manual list built from the catalogue's own Priority field for each FAIL id.
PRIORITY = {
    "MON-014": "P2", "MON-018": "P3", "MON-064": "P1", "MON-092": "P2", "MON-105": "P2",
    "MON-114": "P2", "MON-135": "P1",
    "INC-010": "P1", "INC-011": "P1", "INC-071": "P1", "INC-072": "P1",
    "RPT-025": "P1", "RPT-072": "P1", "RPT-075": "P2", "RPT-091": "P1",
    "BCH-034": "P2", "BCH-041": "P1", "BCH-051": "P1",
    "OPS-014": "P1", "OPS-048": "P1", "OPS-063": "P2", "OPS-074": "P1",
}
TITLE = {
    "MON-014": "Wasserstein's materiality threshold at an exact float tie",
    "MON-018": "The Wilson-Hilferty chi-square threshold is not the 5% it is compared against",
    "MON-064": "A declared driver does not survive the final relaxation fallback",
    "MON-092": "An observation for an unknown segment is dropped with no record",
    "MON-105": "A one-sided volume prior's explanation prints literal `inf`",
    "MON-114": "`with_outcome` lets `confirmed` exceed `reviewed`",
    "MON-135": "The changepoint mechanism does not beat weighting on a level shift",
    "INC-010": "`_shared_ancestor` picks the ancestor more findings share, not the deepest",
    "INC-011": "`_by_ancestor` never applies the time window to a directly shared ancestor",
    "INC-071": "`resolve` bypasses the residency gate",
    "INC-072": "`Router` carries no tenant field; a shared instance collides across tenants",
    "RPT-025": "`rdarr.build` stores the `(root, count)` tuple, not the root",
    "RPT-072": "The raw (unthemed) fill palette fails WCAG 1.4.11 for five of eight dimensions",
    "RPT-075": "`accessible_on`'s 7:1 boundary case does not reach literal black",
    "RPT-091": "`percent()` stops growing decimals as soon as the value is distinguishable, short of the catalogue's `0.0100%`",
    "BCH-034": "`Defect.difficulty`'s documented vocabulary does not match the corpus",
    "BCH-041": "`statistics-only`'s blind-family claim does not hold at the family level",
    "BCH-051": "`Blinding.register` collides two systems' identical alerts into one",
    "OPS-014": "A read-only-root, single-replica SQLite deployment has nowhere to write its database",
    "OPS-048": "`--prepare` applies the schema to a real PostgreSQL, contradicting its own docstring",
    "OPS-063": "An unknown lineage verdict silently ranks as `pass`",
    "OPS-074": "Two commits in history carry the forbidden assistant-attribution trailer",
}
ASSESSMENT = {
    "MON-014": "not-a-defect",
    "MON-018": "defect",
    "MON-064": "defect",
    "MON-092": "defect",
    "MON-105": "defect",
    "MON-114": "defect",
    "MON-135": "defect",
    "INC-010": "defect",
    "INC-011": "defect",
    "INC-071": "defect",
    "INC-072": "defect",
    "RPT-025": "defect",
    "RPT-072": "defect",
    "RPT-075": "not-a-defect",
    "RPT-091": "not-a-defect",
    "BCH-034": "defect",
    "BCH-041": "not-a-defect",
    "BCH-051": "defect",
    "OPS-014": "defect",
    "OPS-048": "defect",
    "OPS-063": "defect",
    "OPS-074": "defect",
}

fail_ids = [i for i in sorted_ids if all_rows[i][0] == "FAIL"]
fail_ids_ranked = sorted(fail_ids, key=lambda i: (PRIORITY.get(i, "P3"), i))

lines.append("## Failures ranked by severity")
lines.append("")
for fid in fail_ids_ranked:
    prio = PRIORITY.get(fid, "?")
    title = TITLE.get(fid, fid)
    assess = ASSESSMENT.get(fid, "?")
    lines.append(f"- **{fid}** ({prio}, {assess}) — {title}")
lines.append("")

blocked_ids = [i for i in sorted_ids if all_rows[i][0] == "BLOCKED"]
if blocked_ids:
    lines.append("## Blocked")
    lines.append("")
    for bid in blocked_ids:
        lines.append(f"- **{bid}** — {all_rows[bid][1][:140]}")
    lines.append("")

lines.append("## Per-case results")
lines.append("")
lines.append("| Id | Result | Observed |")
lines.append("|---|---|---|")
for id_ in sorted_ids:
    result, observed = all_rows[id_]
    lines.append(f"| `{id_}` | {result} | {esc(observed)} |")
lines.append("")

with open(f"{SCRATCH}/report_body.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("wrote report_body.md,", len(lines), "lines")
