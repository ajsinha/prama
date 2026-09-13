import sys, os, asyncio
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
os.chdir("/home/ashutosh/PycharmProjects/prama")

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from prama.core.concurrency.supervisor import run_sync
from prama.core.errors import ValidationError

# CFG-211: no running loop (top-level synchronous script context)
async def coro_ok():
    return 42
val = run_sync(coro_ok())
R("CFG-211", val == 42, f"run_sync(coro) with no loop running -> {val}")

# CFG-213a: exception propagation with no loop running
async def coro_raises():
    raise ValidationError("bad213", remedy="fix213")
try:
    run_sync(coro_raises())
    R("CFG-213a", False, "no exception (no-loop case)")
except ValidationError as e:
    R("CFG-213a", e.code == "INPUT.INVALID" and e.remedy == "fix213", f"{e.code}: {e.remedy}")
except Exception as e:
    R("CFG-213a", False, f"wrong exception type: {type(e).__name__}: {e}")

# CFG-212: from inside a running loop
async def outer():
    async def coro_ok2():
        return 99
    return run_sync(coro_ok2())
val2 = asyncio.run(outer())
R("CFG-212", val2 == 99, f"run_sync(coro) from inside a running loop -> {val2}")

# CFG-213b: exception propagation from inside a running loop
async def outer_raises():
    async def coro_raises2():
        raise ValidationError("bad213b", remedy="fix213b")
    return run_sync(coro_raises2())
try:
    asyncio.run(outer_raises())
    R("CFG-213b", False, "no exception (inside-loop case)")
except ValidationError as e:
    R("CFG-213b", e.code == "INPUT.INVALID" and e.remedy == "fix213b", f"{e.code}: {e.remedy}")
except Exception as e:
    R("CFG-213b", False, f"wrong exception type: {type(e).__name__}: {e}")

R("CFG-213", results[1][1]=="PASS" and results[3][1]=="PASS", f"both loop states preserve the typed error: {[r[1] for r in results if r[0].startswith('CFG-213')]}")

for id_, res, obs in results:
    if id_ in ("CFG-211", "CFG-212", "CFG-213"):
        print(f"{id_}: {res} :: {obs}")
