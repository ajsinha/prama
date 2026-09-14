import json

all_ids = ([f'CON-{i:03d}' for i in range(1,227)] + [f'PRO-{i:03d}' for i in range(1,110)]
           + [f'EXE-{i:03d}' for i in range(1,154)] + [f'SCH-{i:03d}' for i in range(1,53)])

results = {}
for line in open("results.jsonl"):
    d = json.loads(line)
    if d["id"] in set(all_ids):
        results[d["id"]] = d  # last write wins

missing = [i for i in all_ids if i not in results]
assert not missing, f"missing: {missing}"

meta = json.load(open("catalogue_meta.json"))
fail_details = json.load(open("fail_details.json"))

counts = {"PASS": 0, "FAIL": 0, "BLOCKED": 0}
for i in all_ids:
    counts[results[i]["result"]] += 1
total = len(all_ids)
pass_rate = counts["PASS"] / total * 100

fails = [i for i in all_ids if results[i]["result"] == "FAIL"]
blocked_ids = [i for i in all_ids if results[i]["result"] == "BLOCKED"]

sev_order = {"P1": 0, "P2": 1, "P3": 2}
fails_by_sev = sorted(fails, key=lambda i: sev_order.get(meta[i]["priority"], 9))

lines = []
lines.append("# Data plane — QA execution log (round 4)")
lines.append("")
lines.append(
    "`prama.connect` (every connector: sqlite, filesystem, objectstore, mongo, rest, the SQL family — "
    "postgres/clickhouse/mysql/jdbc/dialects) · `prama.profile` (sketches, statistics, profiler, "
    "incremental planning, segmentation, relationships) · `prama.execute` (the run/worker/queue/stream/ "
    "inflight/preview machinery, Kafka transport) · `prama.schedule` (calendars, budgets, shedding)."
)
lines.append("")
lines.append(
    f"All {total} cases in `qa/catalogue/dataplane.md` (`CON-001..226`, `PRO-001..109`, `EXE-001..153`, "
    "`SCH-001..052`) were re-attempted against the tree after batches **A–D**, following "
    "`qa/logs-round4/README.md`. **The baseline is round 3** (`qa/logs-round3/dataplane.md`: 504 PASS, "
    "33 FAIL, 3 BLOCKED — 93.3%). The harness is the 37 case-scripts kept in `qa/harness/dataplane/` "
    "from round 3, reused as-is and re-executed fresh (a cleared `results.jsonl`, no carried-over rows) "
    "against real services: PostgreSQL (`127.0.0.1:55432` for platform-adjacent cases, `127.0.0.1:55433` "
    "for the SQL connector's own cases), ClickHouse (`127.0.0.1:58123`), MySQL (`127.0.0.1:33061`), "
    "MongoDB (`127.0.0.1:37019`), MinIO/S3 (`127.0.0.1:59000`) and a real JDBC/JVM bridge via "
    "jaydebeapi+JPype against the same PostgreSQL — all already running as Docker containers on this "
    "host. Kafka was checked (`127.0.0.1:19092`) and is **not** reachable, so `EXE-094`/`EXE-095` are "
    "BLOCKED, matching round 3; `CON-114` is BLOCKED for the same streaming-replication reason as round "
    "3. No `src/`, `tests/`, `schema/`, `config/`, `qa/catalogue/` or `qa/regression-suite/` file was "
    "modified in the course of this run; every harness change lives in `qa/harness/dataplane/`."
)
lines.append("")
lines.append(
    "**An infrastructure gap, not a product one.** The PostgreSQL container backing "
    "`127.0.0.1:55433` (`prama-qa-pg`) had been recreated this morning (`docker inspect`: "
    "`StartedAt 2026-09-13T10:10:34Z`, a fresh anonymous volume) — round 3's `positions` fixture "
    "(25,000 rows; `id`, `ccy`, `amount` columns, per CON-094's own stated precondition and CON-099's "
    "recorded column order) never made it into a checked-in setup script, the same "
    "never-saved-back pattern round 3's own README documented repeatedly for ad-hoc corrections. The "
    "first mechanical run of `con_sql_pg.py` against the empty container surfaced as three apparent "
    "regressions (`CON-083`, `CON-084`, `CON-091`) and a mid-script crash that would have silently "
    "orphaned `CON-092..105`/`115..121`/`101`/`100` unreported. A new, checked-in `seed_pg55433.py` "
    "reconstructs the fixture from the catalogue's own Precondition text and the harness scripts' own "
    "column/row requirements (never tuned to any one case's outcome), after which every one of "
    "`con_sql_pg.py`'s cases reproduced round 3's own recorded numbers exactly, `CON-096`'s "
    "`bytes=3100` included — strong evidence the reconstruction is faithful, and that nothing in "
    "`connect/sources/sql/postgres.py` moved (confirmed independently: the file carries zero commits "
    "across batches A–D)."
)
lines.append("")
lines.append(
    "**Three cases have no owning harness script** (round 3 built them by hand too, outside "
    "`qa_common.log()`): `CON-043`/`CON-044` are a direct `grep`/live repro against `src/` (both files "
    "involved carry zero commits in batches A–D), and `EXE-102` is `con_exe_stream.py`'s own "
    "`exe102()` — which logs `EXE-102-PASS`/`EXE-102-FAIL` per policy word but never the bare id — "
    "combined by hand exactly as round 3 did. `compile_log.py` catches a missing id as a hard assertion "
    "failure rather than a silent gap, which is how this was caught before the table was built."
)
lines.append("")

lines.append("## Counts")
lines.append("")
lines.append("| | Count |")
lines.append("|---|---:|")
lines.append(f"| Total cases | {total} |")
lines.append(f"| PASS | {counts['PASS']} |")
lines.append(f"| FAIL | {counts['FAIL']} |")
lines.append(f"| BLOCKED | {counts['BLOCKED']} |")
lines.append(f"| **Pass rate** | **{pass_rate:.1f}%** ({counts['PASS']}/{total}) |")
lines.append("")
lines.append(
    f"Round 3: 504 PASS, 33 FAIL, 3 BLOCKED — 93.3%. Round 4: {counts['PASS']} PASS, {counts['FAIL']} "
    f"FAIL, {counts['BLOCKED']} BLOCKED — {pass_rate:.1f}%."
)
lines.append("")

lines.append("## Regressions — a case that passed round 3 and fails now")
lines.append("")
lines.append(
    "**0.** A programmatic id-by-id diff of this round's 540 verdicts against round 3's own per-case "
    "table (`qa/logs-round3/dataplane.md`'s `## Per-case results` section, parsed mechanically, not by "
    "eye) found **zero** PASS→FAIL transitions, zero FAIL→PASS transitions, and zero cases whose "
    "recorded verdict changed at all — every one of the 540 ids carries the identical `PASS`/`FAIL`/"
    "`BLOCKED` verdict this round as round 3 recorded. This is consistent with the batch A–D diff: "
    "`git diff --stat` from round 3's finalisation commit to `HEAD` touches 13 files, and **none** of "
    "`src/prama/connect/**`, `src/prama/profile/**`, `src/prama/execute/**` or `src/prama/schedule/**` "
    "— the four packages this catalogue exercises — appear in it. The two changed files with any "
    "plausible reach into this area were checked directly:"
)
lines.append("")
lines.append(
    "- `src/prama/backend/execute.py` gained `unanswerable(plan)` and the `VERDICT_METRICS` table "
    "between `judge_segments` and `_verdict`. Diffed directly against pre-batch-A: `_verdict` and "
    "`judge_segments`'s own bodies are byte-identical; the only change is two new top-level names "
    "inserted between them. Purely additive, confirmed by reading the diff rather than assuming it."
)
lines.append(
    "- `src/prama/core/ids.py` — `UlidFactory.new()` now reads the clock *inside* the lock (the fix "
    "for a monotonicity race under clock skew/scheduling; see the file's own comment). "
    "`src/prama/execute/worker.py` is the only dataplane module that touches `core.ids` (via "
    "`new_ulid`), and the catalogue has no case asserting on ULID ordering, minted-id sequencing, or "
    "deterministic paging keyed by id — grepped for `ulid`, `monoton`, `page order`, `deterministic "
    "paging` and found nothing. The observable behaviour is identical for any single-threaded, "
    "forward-clock caller, which is every dataplane case; nothing here was reachable to break."
)
lines.append("")

lines.append("## Fixed since round 3 — a case that failed round 3 and passes now")
lines.append("")
lines.append(
    "**0.** All 33 of round 3's failures reproduce identically this round — same code path, and in "
    "every case checked, the same or an equivalent Observed value (see **Per-case detail for every "
    "FAIL** below). None of the files any of the 33 exercise appear in the batch A–D diff."
)
lines.append("")

lines.append("## Harness notes")
lines.append("")
lines.append(
    "**0 harness artefacts found** (round 3 found and fixed 15). Every one of the 37 case-scripts ran "
    "unmodified and reproduced round 3's own recorded numbers; the only harness-side additions this "
    "round are `seed_pg55433.py` (environment/fixture setup — see above, not a correction to any "
    "assertion) and `build_markdown_r4.py` (this file's generator). One genuine harness limitation was "
    "re-confirmed rather than fixed: `con_exe_stream.py`'s `exe102()` still logs only "
    "`EXE-102-{PASS,FAIL}`, never the bare `EXE-102` id round 3 also had to construct by hand — left "
    "as-is since round 3 made the same choice and the underlying two sub-results are unambiguous "
    "(both PASS)."
)
lines.append("")
lines.append(
    "**A saved-script crash, caught before it could hide anything.** `con_sql_pg.py` run "
    "against the not-yet-reseeded PostgreSQL container crashed inside `con091()` on `CON-091` "
    "(`ConnectorError: CONNECT.OBJECT_MISSING`, uncaught) — which would have silently orphaned "
    "`CON-092` through `CON-105`, `CON-115..121`, `CON-101` and `CON-100` (23 cases) exactly the way "
    "round 3's own README describes for `con_spi.py`/`con014.py`/etc. Caught here because "
    "`compile_log.py`'s `assert not missing` on the full 540-id set fails loudly rather than letting a "
    "partial run pass silently — the exact discipline this round's briefing asked for. After reseeding, "
    "the full script ran to completion with no changes to the script itself."
)
lines.append("")
lines.append(
    "**The `except ValueError` risk did not reach this area.** grepped all 37 scripts for "
    "`except ValueError`: 6 hits, all wrapping calls into `prama.core.concurrency.BoundedQueue`/"
    "`claim_unit` (`EXE-055`, `EXE-063`, part of `EXE-`-series claim tests) and pure Arrow/sketch "
    "boundary checks (`con_arrow.py`, `con_sketches.py`) — none of them wrap a call reachable from "
    "`prama.bench.corpus` (which is not imported anywhere under `prama.connect`, `prama.profile`, "
    "`prama.execute` or `prama.schedule`, confirmed by grep), so the `ValidationError`-is-not-a-"
    "`ValueError` regression that hit `BCH-015`/`BCH-016` elsewhere has no equivalent here."
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
    lines.append(f"- **{i}** — {meta[i]['title']}: {results[i]['observed'][:250]}")
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
    "All 33 are **unchanged from round 3** — same root cause, same code path, reproduced again on the "
    "current tree; none of the files any of them exercise appear in the batch A–D diff. Each entry "
    "states the catalogue's own Expected field, this round's own freshly reproduced Observed value, "
    "how to reproduce it, and an assessment carried forward from round 3 (re-verified, not assumed): "
    "**defect** (the code is wrong) or **not-a-defect** (the catalogue case itself was written from a "
    "misreading — `CON-006`, `CON-009`, `PRO-009`, `PRO-058`, `SCH-041`, carried over unchanged)."
)
lines.append("")

for i in fails_by_sev:
    r = results[i]
    m = meta[i]
    detail = fail_details.get(i, {})
    lines.append(f"### {i} · {m['title']}")
    lines.append(f"- **Expected:** {m['expected']}")
    lines.append(f"- **Observed (round 4):** {r['observed']}")
    lines.append(f"- **Reproduce:** {detail.get('reproduce', '(see Observed — command embedded above)')}")
    lines.append(f"- **Severity:** {m['priority']}")
    lines.append(f"- **Assessment:** {detail.get('assessment', 'defect')}")
    lines.append("")

out_path = "/home/ashutosh/PycharmProjects/prama/qa/logs-round4/dataplane.md"
with open(out_path, "w") as f:
    f.write("\n".join(lines))

print("written", len(lines), "lines to", out_path)
print(f"Total={total} PASS={counts['PASS']} FAIL={counts['FAIL']} BLOCKED={counts['BLOCKED']} rate={pass_rate:.1f}%")
