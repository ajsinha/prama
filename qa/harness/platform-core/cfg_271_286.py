import sys, os, math
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
os.chdir("/home/ashutosh/PycharmProjects/prama")

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

import prama.core.pjson as pjson
from datetime import datetime, date, time, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal

def both_backends(fn):
    """Run fn() once with orjson (if available) and once forcing stdlib."""
    out = {}
    out["orjson" if pjson.HAVE_ORJSON else "stdlib"] = fn()
    if pjson.HAVE_ORJSON:
        orig = pjson.HAVE_ORJSON
        pjson.HAVE_ORJSON = False
        try:
            out["stdlib"] = fn()
        finally:
            pjson.HAVE_ORJSON = orig
    return out

# CFG-271
R("CFG-271", pjson.BACKEND in ("orjson", "stdlib") and pjson.BACKEND == ("orjson" if pjson.HAVE_ORJSON else "stdlib"),
  f"BACKEND={pjson.BACKEND!r} HAVE_ORJSON={pjson.HAVE_ORJSON}")

# CFG-272
sample = {"b": [1, 2.5, None], "a": {"nested": True}, "dt": datetime(2026,1,1,tzinfo=timezone.utc), "dec": Decimal("1.50")}
res272 = both_backends(lambda: pjson.canonical(sample))
R("CFG-272", len(set(res272.values())) == 1 if len(res272) > 1 else True,
  f"backends={list(res272.keys())}; identical={len(set(res272.values()))==1 if len(res272)>1 else 'only one backend available'}; values={res272}")

# CFG-273
naive = {"a": {"b": datetime(2026, 1, 1)}}
def try_naive():
    try:
        pjson.dumps(naive)
        return "no-error"
    except TypeError as e:
        return str(e)
res273 = both_backends(try_naive)
R("CFG-273", all(v == "refusing to serialise a naive datetime; attach UTC" for v in res273.values()), str(res273))

# CFG-274
ny_dt = datetime(2026, 6, 1, 12, 0, 0, tzinfo=ZoneInfo("America/New_York"))
res274 = both_backends(lambda: pjson.dumps({"t": ny_dt}))
ok274 = all(("Z" in v and "+00:00" not in v) for v in res274.values())
R("CFG-274", ok274, str(res274))

# CFG-275
nonfinite = {"a": float("nan"), "b": float("inf"), "c": float("-inf")}
res275 = both_backends(lambda: pjson.dumps(nonfinite))
ok275 = all(v.count("null") == 3 for v in res275.values())
R("CFG-275", ok275, str(res275))

# CFG-276
nested_nan = {"m": {"x": [1.0, float("nan")]}}
res276 = both_backends(lambda: pjson.dumps(nested_nan))
ok276 = all("null" in v for v in res276.values())
R("CFG-276", ok276, str(res276))

# CFG-277
res277 = both_backends(lambda: pjson.dumps({"amt": Decimal("0.1")}))
ok277 = all(v == '{"amt":"0.1"}' for v in res277.values())
R("CFG-277", ok277, str(res277))

# CFG-278
res278 = both_backends(lambda: pjson.dumps({"s": {1,2,3}, "t": (1,2,3)}))
R("CFG-278", all("[" in v for v in res278.values()), str(res278))

# CFG-279
bad_bytes = b"\xff\xfe not utf8"
res279 = both_backends(lambda: pjson.dumps({"b": bad_bytes}))
R("CFG-279", all("�" in v or "?" in v for v in res279.values()), str(res279))

# CFG-280
class Weird:
    pass
def try_weird():
    try:
        pjson.dumps({"w": Weird()})
        return "no-error"
    except TypeError as e:
        return str(e)
res280 = both_backends(try_weird)
R("CFG-280", all("Weird" in v for v in res280.values()), str(res280))

# CFG-281
d1 = {"z": 1, "a": 2, "m": 3}
d2 = {"a": 2, "m": 3, "z": 1}
res281a = both_backends(lambda: pjson.canonical(d1))
res281b = both_backends(lambda: pjson.canonical(d2))
R("CFG-281", res281a == res281b, f"{res281a} vs {res281b}")

# CFG-282
n1 = {"top": {"z": 1, "a": 2}}
n2 = {"top": {"a": 2, "z": 1}}
res282a = both_backends(lambda: pjson.canonical(n1))
res282b = both_backends(lambda: pjson.canonical(n2))
R("CFG-282", res282a == res282b, f"{res282a} vs {res282b}")

# CFG-283
res283 = both_backends(lambda: pjson.dumps({"a": 1}))
R("CFG-283", all(v == '{"a":1}' for v in res283.values()), str(res283))

# CFG-284
structure = {"n": 1, "f": 1.5, "s": "text", "l": [1,2,3], "b": True, "nil": None}
res284 = both_backends(lambda: pjson.loads(pjson.dumps(structure)))
R("CFG-284", all(v == structure for v in res284.values()), str(res284))

# CFG-285
doc = pjson.dumps({"a": 1})
res285_str = both_backends(lambda: pjson.loads(doc))
res285_bytes = both_backends(lambda: pjson.loads(doc.encode("utf-8")))
R("CFG-285", res285_str == res285_bytes, f"str={res285_str} bytes={res285_bytes}")

# CFG-286
unicode_val = {"name": "café 日本語 🎉"}
res286_dumps = both_backends(lambda: pjson.dumps(unicode_val))
res286_loads = both_backends(lambda: pjson.loads(pjson.dumps(unicode_val))["name"])
identical_bytes = len(set(res286_dumps.values())) == 1 if len(res286_dumps) > 1 else True
roundtrip_ok = all(v == "café 日本語 🎉" for v in res286_loads.values())
R("CFG-286", identical_bytes and roundtrip_ok, f"dumps identical={identical_bytes}; roundtrip={res286_loads}; raw dumps={res286_dumps}")

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
