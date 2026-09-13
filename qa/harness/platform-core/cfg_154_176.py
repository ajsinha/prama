import sys, os, threading, time, re, subprocess
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from datetime import datetime, timezone, UTC
from zoneinfo import ZoneInfo
from prama.core.clock import SystemClock, FixedClock, ManualClock, utc_now

# CFG-154 -- run in a subprocess with TZ=Asia/Kolkata
proc = subprocess.run(
    [sys.executable, "-c",
     "import sys; sys.path.insert(0,'src'); from prama.core.clock import SystemClock; "
     "from datetime import datetime, UTC; c=SystemClock().now(); n=datetime.now(UTC); "
     "print(c.tzinfo, abs((c-n).total_seconds()) < 2)"],
    capture_output=True, text=True, env={**os.environ, "TZ": "Asia/Kolkata"}, cwd=REPO,
)
R("CFG-154", "utc" in proc.stdout.lower() and "True" in proc.stdout, f"stdout={proc.stdout.strip()!r} stderr={proc.stderr.strip()[:200]!r}")

# CFG-155
iso = SystemClock().isoformat()
R("CFG-155", iso.endswith("Z") and "+00:00" not in iso, repr(iso))

# CFG-156
fc = FixedClock(datetime(2026, 3, 1, 12, 30, 45, 123456, tzinfo=UTC))
em = fc.epoch_millis()
expected_em = int(fc.now().timestamp() * 1000)
R("CFG-156", em == expected_em and em % 1000 == 123, f"epoch_millis={em}, timestamp*1000={fc.now().timestamp()*1000}")

# CFG-157
try:
    FixedClock(datetime(2026, 1, 1))
    R("CFG-157", False, "no exception for naive datetime")
except ValueError as e:
    R("CFG-157", True, str(e))

# CFG-158
ny = datetime(2026, 6, 1, 12, 0, 0, tzinfo=ZoneInfo("America/New_York"))
fc158 = FixedClock(ny)
R("CFG-158", fc158.now().tzinfo == UTC and fc158.now() == ny.astimezone(UTC), f"{fc158.now()} vs expected {ny.astimezone(UTC)}")

# CFG-159
mc = ManualClock(datetime(2026, 1, 1, tzinfo=UTC))
before_now, before_mono = mc.now(), mc.monotonic()
mc.advance(30)
R("CFG-159", (mc.now()-before_now).total_seconds()==30 and mc.monotonic()-before_mono==30.0,
  f"now delta={(mc.now()-before_now).total_seconds()}, mono delta={mc.monotonic()-before_mono}")

# CFG-160
try:
    mc.advance(-1)
    R("CFG-160", False, "no exception")
except ValueError as e:
    R("CFG-160", "backwards" in str(e), str(e))

# CFG-161
fc161 = FixedClock(datetime(2026,1,1,tzinfo=UTC))
R("CFG-161", fc161.monotonic()==0.0 and fc161.monotonic()==0.0, f"{fc161.monotonic()}, {fc161.monotonic()}")

# CFG-162 -- grep for bare datetime.now( outside core/clock.py
import glob
src_files = glob.glob(REPO + "/src/prama/**/*.py", recursive=True)
bad_datetime_now = []
utc_now_sites = []
for path in src_files:
    text = open(path, encoding="utf-8").read()
    if path.endswith("core/clock.py") or path.endswith("core\\clock.py"):
        continue
    for m in re.finditer(r'(?<!\.)\bdatetime\.now\s*\(', text):
        # allow datetime.now(UTC) / datetime.now(tz=...) explicit tz? catalogue says "no bare datetime.now() outside clock.py"
        bad_datetime_now.append((path, text[:m.start()].count("\n")+1))
    for m in re.finditer(r'\butc_now\s*\(', text):
        utc_now_sites.append(path)
R("CFG-162", not bad_datetime_now, f"bare datetime.now() call sites outside core/clock.py: {bad_datetime_now}" if bad_datetime_now else f"none found; utc_now() used in {len(set(utc_now_sites))} files")

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
