
import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
if len(sys.argv) > 1 and sys.argv[1] == "--no-orjson":
    import builtins
    real_import = builtins.__import__
    def fake_import(name, *a, **kw):
        if name == "orjson":
            raise ImportError("masked")
        return real_import(name, *a, **kw)
    builtins.__import__ = fake_import
from prama.evidence.record import EvidenceRecord, SnapshotRef
from prama.core.pjson import HAVE_ORJSON
r = EvidenceRecord(
    plan_id="p", control_id="c", dataset="d", binding="b", engine="pg",
    snapshot=SnapshotRef(kind="lsn", identifier="x", exact=True),
    verdict="pass",
    metrics={"a": 1e16, "b": 0.1 + 0.2, "c": float(2**60)},
    tenant_id="münchen",
)
print(HAVE_ORJSON, r.content_hash)
