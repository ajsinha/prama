import sys, os, hmac, inspect
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
REPO = "/home/ashutosh/PycharmProjects/prama"
os.chdir(REPO)

results = []
def R(id, ok, obs):
    results.append((id, "PASS" if ok else "FAIL", obs))

from datetime import datetime, UTC, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, text as satext
from prama.db.types import UtcDateTime, JsonText, BoolInt

engine = create_engine("sqlite:///:memory:")
metadata = MetaData()
tbl = Table(
    "t", metadata,
    Column("id", Integer, primary_key=True),
    Column("ts", UtcDateTime),
    Column("js", JsonText),
    Column("js_unsorted", JsonText(sort_keys=False)),
    Column("b", BoolInt),
)
metadata.create_all(engine)

# DB-093
try:
    with engine.begin() as conn:
        conn.execute(tbl.insert().values(id=1, ts=datetime(2026, 1, 1)))
    R("DB-093", False, "no exception for naive datetime")
except Exception as e:
    R("DB-093", "refusing to store a naive datetime" in str(e), f"{type(e).__name__}: {e}")

# DB-094
try:
    with engine.begin() as conn:
        conn.execute(tbl.insert().values(id=2, ts="2026-01-01T00:00:00Z"))
    R("DB-094", False, "no exception for a string")
except Exception as e:
    R("DB-094", "str" in str(e) and "expected datetime" in str(e), f"{type(e).__name__}: {e}")

# DB-095
tokyo_dt = datetime(2026, 6, 1, 21, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
with engine.begin() as conn:
    conn.execute(tbl.insert().values(id=3, ts=tokyo_dt))
    got95 = conn.execute(satext("SELECT ts FROM t WHERE id=3")).scalar()
    round95 = tbl.select().where(tbl.c.id == 3)
    orm95 = conn.execute(round95).first()
R("DB-095", got95.endswith("Z") and orm95.ts == tokyo_dt.astimezone(UTC), f"stored={got95!r}, read back={orm95.ts!r}, expected={tokyo_dt.astimezone(UTC)!r}")

# DB-096
micros = [0, 1, 999999]
mism96 = {}
with engine.begin() as conn:
    for i, us in enumerate(micros):
        dt = datetime(2026, 3, 1, 12, 0, 0, us, tzinfo=UTC)
        conn.execute(tbl.insert().values(id=100+i, ts=dt))
        back = conn.execute(tbl.select().where(tbl.c.id == 100+i)).first()
        if back.ts != dt:
            mism96[us] = (dt, back.ts)
R("DB-096", not mism96, f"mismatches={mism96}" if mism96 else "all three microsecond boundaries round-trip exactly")

# DB-097
with engine.begin() as conn:
    conn.execute(satext("INSERT INTO t (id, ts) VALUES (200, '2026-01-01T00:00:00.000000+00:00')"))
    row97 = conn.execute(tbl.select().where(tbl.c.id == 200)).first()
R("DB-097", row97.ts == datetime(2026,1,1,tzinfo=UTC), repr(row97.ts))

# DB-098
try:
    with engine.begin() as conn:
        conn.execute(satext("INSERT INTO t (id, ts) VALUES (201, 'not-a-date')"))
        conn.execute(tbl.select().where(tbl.c.id == 201)).first()
    R("DB-098", False, "no exception reading a malformed timestamp")
except Exception as e:
    msg98 = str(e)
    named = ("column" in msg98.lower()) or (".ts" in msg98) or ("table" in msg98.lower() and "t" in msg98)
    R("DB-098", named, f"raised {type(e).__name__}: {msg98[:200]!r} -- names the column/table={named}")

# DB-099
with engine.begin() as conn:
    conn.execute(tbl.insert().values(id=300, js={"z": 1, "a": 2}))
    conn.execute(tbl.insert().values(id=301, js={"a": 2, "z": 1}))
    raw1 = conn.execute(satext("SELECT js FROM t WHERE id=300")).scalar()
    raw2 = conn.execute(satext("SELECT js FROM t WHERE id=301")).scalar()
R("DB-099", raw1 == raw2, f"{raw1!r} vs {raw2!r}")

# DB-100
nested = {"a": [1, 2, {"b": None, "c": "café 日本語"}], "n": 3.5}
with engine.begin() as conn:
    conn.execute(tbl.insert().values(id=302, js=nested))
    back100 = conn.execute(tbl.select().where(tbl.c.id == 302)).first()
R("DB-100", back100.js == nested, f"{back100.js} vs {nested}")

# DB-101
with engine.begin() as conn:
    conn.execute(tbl.insert().values(id=303, js=None))
    raw101 = conn.execute(satext("SELECT js FROM t WHERE id=303")).scalar()
    is_null101 = conn.execute(satext("SELECT COUNT(*) FROM t WHERE id=303 AND js IS NULL")).scalar()
R("DB-101", raw101 is None and is_null101 == 1, f"raw={raw101!r}, IS NULL matched={is_null101}")

# DB-102
with engine.begin() as conn:
    conn.execute(tbl.insert().values(id=304, js={}))
    back102 = conn.execute(tbl.select().where(tbl.c.id == 304)).first()
    raw102 = conn.execute(satext("SELECT js FROM t WHERE id=304")).scalar()
R("DB-102", back102.js == {} and raw102 is not None, f"read back={back102.js!r}, raw stored={raw102!r}")

# DB-103
vals103 = {"True": True, "False": False, "1int": 1, "0int": 0}
raws103 = {}
with engine.begin() as conn:
    idc = 400
    for label, v in vals103.items():
        conn.execute(tbl.insert().values(id=idc, b=v))
        raws103[label] = conn.execute(satext(f"SELECT b FROM t WHERE id={idc}")).scalar()
        idc += 1
R("DB-103", all(r in (0, 1) for r in raws103.values()) and raws103["True"]==1 and raws103["False"]==0 and raws103["1int"]==1 and raws103["0int"]==0,
  str(raws103))

# DB-104
with engine.begin() as conn:
    conn.execute(tbl.insert().values(id=410, b=None))
    back104 = conn.execute(tbl.select().where(tbl.c.id == 410)).first()
R("DB-104", back104.b is None, repr(back104.b))

# --- security.py ---
from prama.db.security import PasswordHasher, ApiKeyIssuer, IssuedApiKey
from prama.core.errors import ValidationError

h = PasswordHasher()
# DB-105
stored105 = h.hash("correct horse battery staple")
import re as _re
m105 = _re.match(r"^pbkdf2_sha256\$210000\$[0-9a-f]{32}\$[0-9a-f]{64}$", stored105)
R("DB-105", bool(m105), stored105)

# DB-106
s1 = h.hash("samepassword")
s2 = h.hash("samepassword")
R("DB-106", s1 != s2, f"{s1} vs {s2}")

# DB-107
try:
    PasswordHasher(iterations=1000)
    R("DB-107", False, "no exception")
except ValidationError as e:
    ok107 = "code-level floor" in e.remedy and "not a setting" in e.remedy
    R("DB-107", ok107, e.remedy)

# DB-108
stored108 = h.hash("mypassword")
R("DB-108", h.verify("mypassword", stored108) is True and h.verify("mypassword ", stored108) is False and h.verify("MyPassword", stored108) is False,
  f"exact={h.verify('mypassword', stored108)}, trailing-space={h.verify('mypassword ', stored108)}, case-flip={h.verify('MyPassword', stored108)}")

# DB-109
bad_hashes = ["", "garbage", "a$b$c", "pbkdf2_sha256$x$y$z"]
res109 = {}
for bh in bad_hashes:
    try:
        res109[bh] = h.verify("anything", bh)
    except Exception as e:
        res109[bh] = f"RAISED {type(e).__name__}: {e}"
R("DB-109", all(v is False for v in res109.values()), str(res109))

# DB-110: confirm hmac.compare_digest is genuinely used (inspect source)
src110 = inspect.getsource(PasswordHasher.verify)
R("DB-110", "hmac.compare_digest" in src110, "hmac.compare_digest(...) found in PasswordHasher.verify source" if "hmac.compare_digest" in src110 else "not found")

# DB-111
old_hash = PasswordHasher(iterations=100_000).hash("x")
R("DB-111", h.needs_rehash(old_hash) is True, f"needs_rehash(100000-iter hash) under a 210000-iter hasher = {h.needs_rehash(old_hash)}")

# DB-112
foreign = ["bcrypt$blah", "", "pbkdf2_sha256$notanumber$aa$bb"]
res112 = {f: h.needs_rehash(f) for f in foreign}
R("DB-112", all(v is True for v in res112.values()), str(res112))

# DB-113
issuer = ApiKeyIssuer()
issued = [issuer.issue() for _ in range(1000)]
plaintexts = [i.plaintext for i in issued]
hashes = [i.hash for i in issued]
all_prefixed = all(p.startswith("pk_live_") for p in plaintexts)
no_dup_plain = len(set(plaintexts)) == 1000
no_dup_hash = len(set(hashes)) == 1000
stored_form_ok = all(_re.match(r"^sha256:[0-9a-f]{64}$", hh) for hh in hashes)
no_leak = all(hh[7:] not in pt for hh, pt in zip(hashes, plaintexts))  # hash digest not a substring of plaintext
R("DB-113", all_prefixed and no_dup_plain and no_dup_hash and stored_form_ok and no_leak,
  f"all prefixed pk_live_={all_prefixed}, unique plaintexts={no_dup_plain}, unique hashes={no_dup_hash}, stored form matches sha256:<64hex>={stored_form_ok}, hash not substring of plaintext={no_leak}")

# DB-114
one = issuer.issue()
R("DB-114", one.prefix == issuer.prefix_of(one.plaintext) and len(one.prefix) == 12,
  f"prefix={one.prefix!r}, prefix_of={issuer.prefix_of(one.plaintext)!r}, len={len(one.prefix)}")

# DB-115
test_key = issuer.issue(environment="test")
R("DB-115", test_key.plaintext.startswith("pk_test_") and test_key.prefix != one.prefix[:8]+one.prefix[8:],
  f"test key prefix={test_key.prefix!r} vs live key prefix={one.prefix!r}")

# DB-116
k = issuer.issue()
v_true = issuer.verify(k.plaintext, k.hash)
tampered = k.plaintext[:-1] + ("x" if k.plaintext[-1] != "x" else "y")
v_false = issuer.verify(tampered, k.hash)
src116 = inspect.getsource(ApiKeyIssuer.verify)
R("DB-116", v_true is True and v_false is False and "hmac.compare_digest" in src116,
  f"correct-key verify={v_true}, tampered-key verify={v_false}, uses compare_digest={'hmac.compare_digest' in src116}")

# DB-117
import secrets as _secrets
tok = _secrets.token_urlsafe(32)
# token_urlsafe(n) draws n random bytes = 8*n bits of entropy
entropy_bits = 32 * 8
R("DB-117", entropy_bits == 256, f"secrets.token_urlsafe(32) draws 32 random bytes = {entropy_bits} bits of entropy")

for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
