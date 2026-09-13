import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.evidence.record import EvidenceRecord, GENESIS
from prama.evidence.retention import Archivist
from prama.core.clock import Clock

SCR = "/tmp/claude-1000/-home-ashutosh-PycharmProjects-prama/627f9f20-9efa-4027-844d-fc42d0ff016b/scratchpad/r3/plat2/ops/bundle_dir"

records = []
prev = GENESIS
for i in range(10):
    r = EvidenceRecord(
        plan_id="ir:sha256:abc", control_id=f"CTRL{i}", dataset="positions_eod",
        verdict="pass" if i % 3 else "fail",
        metrics={"scanned_rows": 1000.0 + i, "violating_rows": 0.0},
        started_at="2026-09-08T06:00:00Z", finished_at="2026-09-08T06:00:03Z", duration_ms=3000,
        sequence=i, previous_hash=prev,
    )
    prev = r.record_hash
    records.append(r)

arch = Archivist()
bundle = arch.bundle(records, tenant_id="t1")
import os
os.makedirs(SCR, exist_ok=True)
for name, content in bundle.files().items():
    with open(f"{SCR}/{name}", "w") as f:
        f.write(content)
print("wrote", list(bundle.files().keys()))
ok, msg = bundle.check()
print("self-check:", ok, msg)
