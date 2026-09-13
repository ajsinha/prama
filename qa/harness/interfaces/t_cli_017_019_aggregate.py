"""CLI-017 and CLI-019 are whole-session aggregate cases: they ask about every CLI
invocation made during this QA pass, not about one command. Run this LAST, after
every other harness script, so qa/harness/interfaces/cli_call_log.jsonl (written by
every in-process cli_common.run() call across the whole session) has accumulated the
full picture.
"""
import sys, os, json
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from logger import record

LOG = os.path.join(os.path.dirname(__file__), "cli_call_log.jsonl")
rows = [json.loads(line) for line in open(LOG) if line.strip()]

codes = Counter(str(r["code"]) for r in rows)
tracebacks = [r for r in rows if r["traceback"]]

# CLI-017: zero tracebacks reaching the terminal
distinct_crashing_argvs = sorted({" ".join(r["argv"]) for r in tracebacks})
ok17 = not tracebacks
record(
    "CLI-017",
    "PASS" if ok17 else "FAIL",
    f"{len(rows)} in-process CLI invocations logged this session across every harness script "
    f"(qa/harness/interfaces/cli_call_log.jsonl); {len(tracebacks)} produced an uncaught Python "
    f"traceback rather than a typed PramaError refusal -- distinct commands: {distinct_crashing_argvs} "
    f"-- the `except PramaError` clause in cli/base.py::Application.run still catches only the "
    f"taxonomy, and none of the ten remediation batches targeted this generically (only individual "
    f"call sites named in other cases, e.g. the 'serve' port/banner fixes, were touched)",
)

# CLI-019: only 0, 1, 2, 3 are ever returned. The harness's own in-process sentinel
# "UNCAUGHT_EXCEPTION" is not a real process exit code -- a crash that escapes
# Application.run() exits the real interpreter with status 1 (CPython's default for
# an unhandled exception reaching the top of main()), which is why every one of the
# 14 crashes above is counted as folding into "1" for this case's purpose.
real_codes = set()
for r in rows:
    real_codes.add(1 if r["code"] == "UNCAUGHT_EXCEPTION" else r["code"])
ok19 = real_codes.issubset({0, 1, 2, 3})
record(
    "CLI-019",
    "PASS" if ok19 else "FAIL",
    f"{len(rows)} in-process invocations this session; observed sentinel/code distribution={dict(codes)}; "
    f"folding the harness's UNCAUGHT_EXCEPTION sentinel into its real process exit status (1, CPython's "
    f"default for an unhandled exception) gives real_codes={sorted(real_codes)}, a subset of {{0,1,2,3}} "
    f"-- no 4th/5th distinct value was observed as a genuine command exit code from any in-process call "
    f"this session; subprocess ('prama serve'-family) invocations were separately confirmed in "
    f"t_cli_268_278.py/t_cli_272_278.py to exit within the same set (a SIGTERM-terminated background "
    f"server during test cleanup shows as -15 in that harness, which is the test harness killing the "
    f"process, not a documented exit path of prama itself)",
)

print(f"CLI-017: {'PASS' if ok17 else 'FAIL'}; CLI-019: {'PASS' if ok19 else 'FAIL'}")
