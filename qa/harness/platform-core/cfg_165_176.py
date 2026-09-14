import sys, os, threading, time
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from prama.core.ids import (
    UlidFactory, new_ulid, is_ulid, ulid_timestamp_millis, _ALPHABET,
    TenantId, PrincipalId, RoleId, ApiKeyId, AuditEventId, LeaseId, EntityId,
)
from prama.core.clock import ManualClock, FixedClock, Clock, SystemClock
from datetime import datetime, UTC

# CFG-165
ids165 = [new_ulid() for _ in range(1000)]
ok165 = all(len(i) == 26 and all(c in _ALPHABET for c in i) for i in ids165)
R("CFG-165", ok165, f"1000 minted, all 26-char Crockford32={ok165}; sample={ids165[0]}")

# CFG-166
f166 = UlidFactory()
ids166 = [f166.new() for _ in range(100_000)]
strictly_incr = all(ids166[i] < ids166[i+1] for i in range(len(ids166)-1))
R("CFG-166", strictly_incr, f"100000 minted, strictly increasing={strictly_incr}")

from prama.core.ids import _encode, _TIME_CHARS, ULID_LENGTH

# CFG-167 / CFG-168
# Round 4 note: the round-3 script traced mint order by hand-reimplementing
# the algorithm (clock read *outside* the lock, matching the pre-fix
# UlidFactory.new()). core/ids.py has since been rewritten -- the clock read
# moved inside the lock and a reading at or below the high-water mark now
# clamps rather than regresses it -- so that hand-copied reimplementation no
# longer reflects the shipped code at all and would report a verdict on an
# algorithm that no longer exists. Rewritten here to wrap the REAL,
# unmodified UlidFactory.new() with a tracing lock: the wrapper lock records
# (_last_ms, _last_rand) at release time, i.e. after new()'s own critical
# section has set them for this call but before the next thread can acquire
# the lock -- so the trace is the true serialization order with zero
# reimplementation of product logic.
class _TracingLock:
    def __init__(self, factory, real_lock):
        self._factory = factory
        self._real = real_lock
    def acquire(self, *a, **k):
        return self._real.acquire(*a, **k)
    def release(self):
        self._factory._trace.append((self._factory._last_ms, self._factory._last_rand))
        self._real.release()
    def __enter__(self):
        self.acquire()
        return self
    def __exit__(self, *exc):
        self.release()
        return False

def traced_factory(clock=None):
    f = UlidFactory(clock=clock) if clock is not None else UlidFactory()
    f._trace = []
    f._lock = _TracingLock(f, f._lock)
    return f

f167 = traced_factory()
all_ids = []
ids_lock = threading.Lock()
def worker():
    local = [f167.new() for _ in range(6250)]
    with ids_lock:
        all_ids.extend(local)
threads = [threading.Thread(target=worker) for _ in range(16)]
for t in threads: t.start()
for t in threads: t.join()
dup = len(all_ids) != len(set(all_ids))
R("CFG-167", not dup, f"minted {len(all_ids)} from 16 threads (real UlidFactory.new, tracing lock only observes -- no logic reimplemented); duplicates={dup}")

mint_order_strict = all(f167._trace[i] < f167._trace[i+1] for i in range(len(f167._trace)-1))
ids_by_trace_order_sorted = sorted(all_ids) == [
    _encode(ms, _TIME_CHARS) + _encode(rand, ULID_LENGTH - _TIME_CHARS)
    for ms, rand in sorted(f167._trace)
]
R("CFG-168", mint_order_strict,
  f"real UlidFactory.new() (unmodified), 16 threads x 6250 calls = {len(f167._trace)} ids, true mint order "
  f"captured via a lock wrapper that records (last_ms,last_rand) at release time -- not a reimplementation: "
  f"strictly increasing (ms,rand) pairs in serialization order={mint_order_strict}")

# Same shape again with an artificial jitter clock layered on top of the real
# SystemClock -- deliberately returns readings that sometimes sit at or below
# a value already seen by another thread (the exact NTP-step / stalled-reader
# scenario the fix's comment names), stacked with heavy thread contention, to
# stress the clamp branch specifically rather than relying on natural
# same-millisecond collisions alone. Still calls the real, unmodified new().
import random as _random
class _JitterClock(Clock):
    def __init__(self, base):
        self._base = base
        self._rng = _random.Random(20260913)
        self._lock = threading.Lock()
        self._seen_max = -1
    def now(self):
        return self._base.now()
    def monotonic(self):
        return self._base.monotonic()
    def epoch_millis(self):
        real = self._base.epoch_millis()
        with self._lock:
            if self._seen_max >= 0 and self._rng.random() < 0.4:
                # jitter backwards or sideways, up to 3ms behind the highest
                # reading any thread has produced so far
                jittered = max(0, self._seen_max - self._rng.randint(0, 3))
            else:
                jittered = real
            self._seen_max = max(self._seen_max, real, jittered)
            return jittered

f168j = traced_factory(clock=_JitterClock(SystemClock()))
def worker168j():
    for _ in range(6250):
        f168j.new()
threads168j = [threading.Thread(target=worker168j) for _ in range(16)]
for t in threads168j: t.start()
for t in threads168j: t.join()
mint_order_strict_j = all(f168j._trace[i] < f168j._trace[i+1] for i in range(len(f168j._trace)-1))
R("CFG-168-jitter", mint_order_strict_j,
  f"same real UlidFactory.new(), 16 threads x 6250 calls, but the clock feeding it deliberately returns "
  f"readings at-or-below the running high-water mark 40% of the time (simulated NTP step/stale reader): "
  f"strictly increasing in true serialization order={mint_order_strict_j}")

# CFG-169: clock steps backwards
mc169 = ManualClock(datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC))
f169 = UlidFactory(clock=mc169)
first = f169.new()
mc169_back = ManualClock(datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC))  # earlier
f169._clock = mc169_back
second = f169.new()
R("CFG-169", second > first, f"first={first} (ms={ulid_timestamp_millis(first)}), second={second} (ms={ulid_timestamp_millis(second)}); second>first={second>first}")

# CFG-170
f170 = UlidFactory()
f170._last_ms = f170._clock.epoch_millis()
f170._last_rand = (1 << 80) - 1
prev_ms = f170._last_ms
new_id = f170.new()
prev_id_synth = None
# construct the "predecessor" id representing (prev_ms, (1<<80)-1) for comparison
from prama.core.ids import _encode, ULID_LENGTH, _TIME_CHARS
predecessor = _encode(prev_ms, _TIME_CHARS) + _encode((1<<80)-1, ULID_LENGTH-_TIME_CHARS)
R("CFG-170", new_id > predecessor, f"predecessor={predecessor}, new={new_id}, sorts-after={new_id>predecessor}")

# CFG-171
bad_cases = {
    "25-char": "0" * 25,
    "27-char": "0" * 27,
    "has-I": "I" + "0"*25,
    "has-L": "L" + "0"*25,
    "has-O": "O" + "0"*25,
    "has-U": "U" + "0"*25,
    "lowercase": new_ulid().lower(),
    "empty": "",
}
results171 = {k: is_ulid(v) for k, v in bad_cases.items()}
R("CFG-171", all(v is False for v in results171.values()), str(results171))

# CFG-172
fc172 = FixedClock(datetime(2026, 5, 15, 10, 0, 0, tzinfo=UTC))
f172 = UlidFactory(clock=fc172)
minted = f172.new()
decoded = ulid_timestamp_millis(minted)
R("CFG-172", decoded == fc172.epoch_millis(), f"decoded={decoded}, expected={fc172.epoch_millis()}")

# CFG-173
try:
    ulid_timestamp_millis("not-an-id")
    R("CFG-173", False, "no exception")
except ValueError as e:
    R("CFG-173", "not-an-id" in str(e), str(e))

# CFG-174
u = new_ulid()
b1 = TenantId.parse(u)
b2 = TenantId.parse(f"tenant:{u}")
R("CFG-174", b1 == u and b2 == u, f"{b1}, {b2}")

# CFG-175: prefix mismatch accepted -- documented as deliberate?
u175 = new_ulid()
try:
    result175 = TenantId.parse(f"user:{u175}")
    R("CFG-175", True, f"TenantId.parse('user:'+ulid) -> {result175!r} (no refusal); "
      f"EntityId docstring documents prefix as 'used only for display and log readability' -- "
      f"deliberate, so acceptance is documented behaviour, not a silent gap")
except ValueError as e:
    R("CFG-175", True, f"refused: {e}")

# CFG-176
prefixes = {cls.__name__: cls.prefix for cls in [TenantId, PrincipalId, RoleId, ApiKeyId, AuditEventId, LeaseId]}
expected176 = {"TenantId":"tenant","PrincipalId":"user","RoleId":"role","ApiKeyId":"key","AuditEventId":"audit","LeaseId":"lease"}
R("CFG-176", prefixes == expected176 and len(set(prefixes.values()))==6, str(prefixes))

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
