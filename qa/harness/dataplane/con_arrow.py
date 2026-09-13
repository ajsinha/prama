import sys, decimal
sys.path.insert(0, ".")
from qa_common import log
from prama.connect.arrow import to_array
import pyarrow as pa

def con035():
    r1 = to_array([1, 2, 3])
    r2 = to_array(["a", "b"])
    r3 = to_array([1.5, 2.5])
    r4 = to_array([True, False])
    types = [str(r1.type), str(r2.type), str(r3.type), str(r4.type)]
    ok = types == ["int64", "string", "double", "bool"]
    log("CON-035", "PASS" if ok else "FAIL", str(types))

def con036():
    a = to_array([18446744073709551615])
    ok = str(a.type) == "uint64" and a[0].as_py() == 18446744073709551615
    log("CON-036", "PASS" if ok else "FAIL", f"type={a.type} value={a[0].as_py()}")

def con037():
    a = to_array([100, "one hundred"])
    ok = str(a.type) == "string" and a.to_pylist() == ["100", "one hundred"]
    log("CON-037", "PASS" if ok else "FAIL", f"type={a.type} values={a.to_pylist()}")

def con038():
    d = decimal.Decimal("1953193.464900000000")
    a = to_array([d, "x"])
    ok = str(a.type) == "string" and a.to_pylist()[0] == "1953193.464900000000"
    log("CON-038", "PASS" if ok else "FAIL", f"type={a.type} values={a.to_pylist()}")

def con039():
    a1 = to_array([None, None])
    a2 = to_array([None, 18446744073709551615])
    a3 = to_array([None, 1, "x"])
    lens = [len(a1), len(a2), len(a3)]
    nulls_ok = a1.null_count == 2 and a2[0].as_py() is None and a3[0].as_py() is None
    no_string_none = "None" not in [x for x in a3.to_pylist() if x is not None]
    ok = lens == [2, 2, 3] and nulls_ok
    log("CON-039", "PASS" if ok else "FAIL", f"lens={lens} a1_nulls={a1.null_count} a2[0]={a2[0].as_py()} a3={a3.to_pylist()}")

def con040():
    a = to_array([])
    ok = len(a) == 0
    log("CON-040", "PASS" if ok else "FAIL", f"len={len(a)} type={a.type}")

def con041():
    class Bad:
        def __str__(self):
            raise ValueError("cannot stringify")
    try:
        to_array([Bad()])
        log("CON-041", "FAIL", "no exception propagated")
    except ValueError as e:
        log("CON-041", "PASS", f"ValueError propagated: {e}")
    except Exception as e:
        log("CON-041", "FAIL", f"wrong exception type: {type(e).__name__}: {e}")

def con042():
    try:
        a = to_array([-1, 18446744073709551615])
        is_uint64_wrapped = str(a.type) == "uint64"
        vals = a.to_pylist()
        log("CON-042", "FAIL" if is_uint64_wrapped else "PASS",
            f"type={a.type} values={vals} (uint64-wrapped={is_uint64_wrapped})")
    except Exception as e:
        log("CON-042", "PASS", f"{type(e).__name__}: {e} (exception, not silent reinterpretation)")

con035(); con036(); con037(); con038(); con039(); con040(); con041(); con042()
