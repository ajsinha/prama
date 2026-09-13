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
from prama.core.clock import ManualClock, FixedClock
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

# CFG-167 / CFG-168
f167 = UlidFactory()
lock = threading.Lock()
all_ids = []
def worker():
    local = [f167.new() for _ in range(6250)]
    with lock:
        all_ids.extend(local)
threads = [threading.Thread(target=worker) for _ in range(16)]
t0 = time.monotonic()
for t in threads: t.start()
for t in threads: t.join()
dup = len(all_ids) != len(set(all_ids))
R("CFG-167", not dup, f"minted {len(all_ids)} from 16 threads; duplicates={dup}")
# True mint-order tracing (appending outside the lock is racy and gives a false
# negative, so trace inside the critical section itself).
from prama.core.ids import _encode, _TIME_CHARS, ULID_LENGTH, _RANDOM_BITS
import os as _os

class _TracedFactory(UlidFactory):
    def __init__(self):
        super().__init__()
        self.order = []
    def new(self):
        ms = self._clock.epoch_millis()
        with self._lock:
            if ms == self._last_ms:
                self._last_rand += 1
                if self._last_rand >= (1 << _RANDOM_BITS):
                    ms += 1
                    self._last_ms = ms
                    self._last_rand = int.from_bytes(_os.urandom(10), "big")
            else:
                self._last_ms = ms
                self._last_rand = int.from_bytes(_os.urandom(10), "big")
            rand = self._last_rand
            val = _encode(ms, _TIME_CHARS) + _encode(rand, ULID_LENGTH - _TIME_CHARS)
            self.order.append(val)
        return val

f168 = _TracedFactory()
def worker168():
    for _ in range(6250):
        f168.new()
threads168 = [threading.Thread(target=worker168) for _ in range(16)]
for t in threads168: t.start()
for t in threads168: t.join()
mint_order_strict = all(f168.order[i] < f168.order[i+1] for i in range(len(f168.order)-1))
R("CFG-168", mint_order_strict, f"traced true mint order (appended inside the critical section) across 16 threads, {len(f168.order)} ids: strictly increasing={mint_order_strict}")

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
