import sys, re
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.classify.validators import REGISTRY, default_registry, ValidatorRegistry, SemanticValidator, Expressibility
from prama.core.errors import ValidationError

results = []
def R(id_, ok, obs):
    results.append((id_, "PASS" if ok else "FAIL", obs))

def block(id_):
    def deco(fn):
        try:
            fn()
        except AssertionError as e:
            R(id_, False, f"AssertionError: {e}")
        except Exception as e:
            R(id_, False, f"{type(e).__name__}: {e}")
    return deco

NAMES = REGISTRY.names()

@block("CLS-001")
def _():
    ok = len(NAMES)==20
    reg2 = default_registry()
    class Dup(SemanticValidator):
        name = 'isin'
        def check(self, value): from prama.classify.validators import VALID; return VALID
    try:
        reg2.register(Dup())
        raised = False
    except ValidationError as e:
        raised = True
        msg = str(e)
    R("CLS-001", ok and raised, f"count={len(NAMES)}; dup_registration_raised={raised}")

@block("CLS-002")
def _():
    bad = []
    for n in NAMES:
        v = REGISTRY.get(n)
        j = v.judge(None)
        if not j.valid:
            bad.append(n)
    R("CLS-002", not bad, f"validators_rejecting_None={bad}")

@block("CLS-003")
def _():
    bad = []
    for n in NAMES:
        v = REGISTRY.get(n)
        for s in ('', '   ', '\t\n'):
            j = v.judge(s)
            if not j.valid:
                bad.append((n,repr(s)))
    R("CLS-003", not bad, f"failures={bad}")

@block("CLS-004")
def _():
    v = REGISTRY.get('isin')
    a = v.judge(' US0378331005 ')
    b = v.judge('US0378331005\n')
    R("CLS-004", a.valid and b.valid, f"leading/trailing_space={a} trailing_newline={b}")

@block("CLS-005")
def _():
    v_iban = REGISTRY.get('iban')
    v_isin = REGISTRY.get('isin')
    a = v_iban.judge('GB82 WEST 1234 5698 7654 32')
    b = v_isin.judge('US 0378331005')
    ok = not a.valid and a.failed_screen and not b.valid and b.failed_screen
    R("CLS-005", ok, f"iban_grouped={a} isin_spaced={b}")

@block("CLS-006")
def _():
    v_isin = REGISTRY.get('isin'); v_iban = REGISTRY.get('iban'); v_bic = REGISTRY.get('bic')
    a = v_isin.judge('us0378331005')
    b = v_iban.judge('de89370400440532013000')
    c = v_bic.judge('deutdeff')
    ok = all(not x.valid and x.failed_screen for x in (a,b,c))
    reasons_ok = all('not shaped like' in x.reason for x in (a,b,c))
    R("CLS-006", ok and reasons_ok, f"isin={a} iban={b} bic={c}")

@block("CLS-007")
def _():
    bad = []
    tests = ['А' + 'S0378331005', '０S0378331005', 'US037833​1005', 'é']
    for n in NAMES:
        v = REGISTRY.get(n)
        for t in tests:
            try:
                j = v.judge(t)
                if j.valid:
                    bad.append((n, repr(t)))
            except Exception as e:
                bad.append((n, repr(t), f"EXC:{e}"))
    R("CLS-007", not bad, f"unexpected_valid_or_exceptions={bad}")

@block("CLS-008")
def _():
    import time
    bad = []
    for n in NAMES:
        v = REGISTRY.get(n)
        for t in ('x'*256, '9'*100000):
            t0=time.time()
            try:
                j = v.judge(t)
            except Exception as e:
                bad.append((n, 'EXC', str(e)[:60]))
                continue
            dt = time.time()-t0
            if j.valid or dt>2.0:
                bad.append((n, 'valid_or_slow', j.valid, dt))
    R("CLS-008", not bad, f"issues={bad}")

@block("CLS-009")
def _():
    import sqlite3, duckdb, psycopg2
    PG_DSN = "postgresql://prama:prama@127.0.0.1:55433/prama"
    corpus = ['US0378331005', ' US0378331005 ', 'us0378331005', 'GB82 WEST 1234 5698 7654 32',
              'АS0378331005', 'x'*256, '', 'GB0002634946']
    mismatches = []
    for n in NAMES:
        v = REGISTRY.get(n)
        pat = v.screen_pattern
        if not pat:
            continue
        for val in corpus:
            py_accept = bool(re.match(pat, val))
            # SQLite REGEXP: use python re via connection function to emulate what product's own hook likely does
            try:
                con = sqlite3.connect(':memory:')
                con.create_function('REGEXPTEST', 2, lambda p,s: 1 if (s is not None and re.match(p,s)) else 0)
                r = con.execute("SELECT REGEXPTEST(?,?)", (pat, val)).fetchone()[0]
                sqlite_accept = bool(r)
            except Exception as e:
                sqlite_accept = f"ERR:{e}"
            try:
                con = duckdb.connect(':memory:')
                r = con.execute("SELECT regexp_matches(?, ?)", (val, pat)).fetchone()[0]
                duck_accept = bool(r)
            except Exception as e:
                duck_accept = f"ERR:{e}"
            try:
                con = psycopg2.connect(PG_DSN)
                cur = con.cursor()
                cur.execute("SELECT %s ~ %s", (val, pat))
                pg_accept = bool(cur.fetchone()[0])
                con.close()
            except Exception as e:
                pg_accept = f"ERR:{e}"
            if not (py_accept == duck_accept == pg_accept):
                mismatches.append((n, repr(val), py_accept, duck_accept, pg_accept))
    R("CLS-009", not mismatches, f"mismatches(py,duckdb,postgres)={mismatches[:15]}{'...' if len(mismatches)>15 else ''} total={len(mismatches)}")

@block("CLS-010")
def _():
    from prama.classify.validators import Expressibility as Ex
    pattern_only = [REGISTRY.get(n).name for n in NAMES if REGISTRY.get(n).screen_is_complete]
    algo = [REGISTRY.get(n).name for n in NAMES if not REGISTRY.get(n).screen_is_complete]
    ok = len(pattern_only)==8 and len(algo)==12
    R("CLS-010", ok, f"screen_complete({len(pattern_only)})={pattern_only}; algorithm({len(algo)})={algo}")

@block("CLS-011")
def _():
    v = REGISTRY.get('isin')
    ids = ['US0378331005','GB0002634946','DE000BAY0017','XS0629974352']
    bad = [i for i in ids if not v.judge(i).valid]
    R("CLS-011", not bad, f"failed={bad}")

@block("CLS-012")
def _():
    v = REGISTRY.get('isin')
    a = v.judge('US0378331004')
    b = v.judge('GB0000000000')
    ok = not a.valid and not a.failed_screen and '4' in a.reason and '5' in a.reason and 'US0378331005' in a.reason
    ok2 = not b.valid and not b.failed_screen
    R("CLS-012", ok and ok2, f"US0378331004={a}; GB0000000000={b}")

@block("CLS-013")
def _():
    v = REGISTRY.get('isin')
    cases = ['US037833100','US03783310055','US037833100A','1S0378331005']
    results_ = {c: v.judge(c) for c in cases}
    ok = all(not j.valid and j.failed_screen for j in results_.values())
    R("CLS-013", ok, f"{ {c: (j.valid,j.failed_screen) for c,j in results_.items()} }")

@block("CLS-014")
def _():
    v = REGISTRY.get('sedol')
    a = v.judge('0263494')
    b = v.judge('0263495')
    ok = a.valid and not b.valid and '5' in b.reason and '4' in b.reason
    R("CLS-014", ok, f"0263494={a}; 0263495={b}")

@block("CLS-015")
def _():
    v = REGISTRY.get('sedol')
    a = v.judge('B0AKT98')
    b = v.judge('0263A94')
    ok = not a.valid and a.failed_screen and not b.valid and b.failed_screen
    R("CLS-015", ok, f"B0AKT98={a}; 0263A94={b}")

@block("CLS-016")
def _():
    v = REGISTRY.get('cusip')
    a = v.judge('037833100')
    b = v.judge('459200101')
    ok = a.valid and b.valid
    R("CLS-016", ok, f"apple={a} ibm={b}")

@block("CLS-017")
def _():
    v = REGISTRY.get('cusip')
    # need real CUSIPs containing *,@,# with correct check digit; search small space
    import itertools
    found = {}
    for ch, val in (('*','36'),('@','37'),('#','38')):
        base = f"12345{ch}67"  # 8 chars body incl special char, need check digit computed
        # brute force check digit 0-9
        for d in range(10):
            cand = base + str(d)
            j = v.judge(cand)
            if j.valid:
                found[ch] = cand
                break
    ok = len(found) >= 1  # at least confirm mechanism accepts one
    R("CLS-017", ok, f"found_valid_with_special_chars={found}")

@block("CLS-018")
def _():
    v = REGISTRY.get('cusip')
    j = v.judge('037833101')
    ok = not j.valid and not j.failed_screen and '1' in j.reason and '0' in j.reason
    R("CLS-018", ok, f"{j}")

@block("CLS-019")
def _():
    v = REGISTRY.get('figi')
    a = v.judge('BBG000BLNNH6')
    b = v.judge('BBG000B9XRY4')
    R("CLS-019", a.valid and b.valid, f"ibm={a} apple={b}")

@block("CLS-020")
def _():
    v = REGISTRY.get('figi')
    a = v.judge('ABG000BLNNH6')
    b = v.judge('BBX000BLNNH6')
    ok = not a.valid and a.failed_screen and not b.valid and b.failed_screen
    R("CLS-020", ok, f"vowel_prefix={a} wrong_third={b}")

@block("CLS-021")
def _():
    v = REGISTRY.get('lei')
    a = v.judge('HWUPKR0MPOU8FGXBT394')
    b = v.judge('7LTWFZYICNSX8D621K86')
    R("CLS-021", a.valid and b.valid, f"a={a} b={b}")

@block("CLS-022")
def _():
    v = REGISTRY.get('lei')
    a = v.judge('HWUPKR0MPOU8FGXBT395')
    b = v.judge('AAAAAAAAAAAAAAAAAA00')
    ok = not a.valid and not a.failed_screen and not b.valid and not b.failed_screen
    reason_ok = 'HWUPKR0MPOU8FGXBT' in a.reason or True
    R("CLS-022", ok, f"a={a} b={b}")

@block("CLS-023")
def _():
    v = REGISTRY.get('lei')
    a = v.judge('HWUPKR0MPOU8FGXBT39A')
    b = v.judge('HWUPKR0MPOU8FGXBT9')  # 19 chars
    c = v.judge('HWUPKR0MPOU8FGXBT3945')  # 21 chars? check length
    ok = not a.valid and a.failed_screen and not b.valid and b.failed_screen and not c.valid and c.failed_screen
    R("CLS-023", ok, f"letter_check={a} len19={b} len21={c}")

@block("CLS-024")
def _():
    import random
    from prama.classify.validators import _mod97
    random.seed(42)
    bad = []
    for _ in range(1000):
        length = random.randint(1,60)
        s = ''.join(random.choice('0123456789') for _ in range(length))
        if s=='' : continue
        expect = int(s) % 97
        got = _mod97(s)
        if got != expect:
            bad.append((s, expect, got))
    R("CLS-024", not bad, f"mismatches={bad[:5]} total={len(bad)}")

@block("CLS-025")
def _():
    v = REGISTRY.get('iban')
    ids = ['GB82WEST12345698765432','DE89370400440532013000','FR1420041010050500013M02606','NO9386011117947']
    bad = [i for i in ids if not v.judge(i).valid]
    R("CLS-025", not bad, f"failed={bad}")

@block("CLS-026")
def _():
    v = REGISTRY.get('iban')
    a = v.judge('GB82WEST12345698765433')
    b = v.judge('DE88370400440532013000')
    ok = not a.valid and not a.failed_screen and not b.valid and not b.failed_screen
    R("CLS-026", ok, f"a={a} b={b}")

@block("CLS-027")
def _():
    v = REGISTRY.get('iban')
    j = v.judge('DE8937040044053201300')  # 21 chars (one short)
    ok = not j.valid
    R("CLS-027", ok, f"{j} (len={len('DE8937040044053201300')})")

@block("CLS-028")
def _():
    v = REGISTRY.get('iban')
    a = v.judge('US64SVBKUS6S3300958879')
    ok = not a.valid
    R("CLS-028", ok, f"{a}")

@block("CLS-029")
def _():
    from prama.classify.validators import IbanValidator
    from prama.classify.codelists import ISO_3166
    lengths_countries = set(IbanValidator.LENGTHS.keys())
    iso_countries = set(ISO_3166.latest.codes)
    diff = lengths_countries - iso_countries
    R("CLS-029", None, f"in_LENGTHS_not_in_ISO_3166={sorted(diff)}")

@block("CLS-030")
def _():
    from prama.classify.validators import IbanValidator
    present = {c: (c in IbanValidator.LENGTHS) for c in ('SO','FK','MN','NI','DJ','RU')}
    R("CLS-030", None, f"presence={present}")

@block("CLS-031")
def _():
    v = REGISTRY.get('bic')
    for c in ('DEUTDEFF','DEUTDEFF500','NEDSZAJJXXX'):
        j = v.judge(c)
        if not j.valid:
            R("CLS-031", False, f"{c} -> {j}")
            return
    R("CLS-031", True, "all valid")

@block("CLS-032")
def _():
    v = REGISTRY.get('bic')
    cases = ['DEUTDEFF5','DEUTDEFF50','DEUTDEFF5000','DEUT1EFF']
    bad = [c for c in cases if v.judge(c).valid]
    R("CLS-032", not bad, f"unexpectedly_valid={bad}")

@block("CLS-033")
def _():
    v = REGISTRY.get('bic')
    ok_complete = v.screen_is_complete
    default_beyond = v.beyond_shape
    R("CLS-033", ok_complete and default_beyond=="a value of the right shape can still fail it", f"screen_is_complete={ok_complete} beyond_shape={default_beyond!r} (a PatternValidator inheriting the default is false for it)")

@block("CLS-034")
def _():
    v = REGISTRY.get('mic')
    bad = [c for c in ('XNYS','XLON','XETR','BATE') if not v.judge(c).valid]
    R("CLS-034", not bad, f"failed={bad}")

@block("CLS-035")
def _():
    v = REGISTRY.get('mic')
    a = v.judge('ZZZZ'); b = v.judge('0000')
    R("CLS-035", a.valid and b.valid, f"ZZZZ={a} 0000={b} -- these are not real MICs but pass (shape-only, no membership list)")

@block("CLS-036")
def _():
    v = REGISTRY.get('aba_routing')
    bad = [c for c in ('021000021','011000015') if not v.judge(c).valid]
    R("CLS-036", not bad, f"failed={bad}")

@block("CLS-037")
def _():
    v = REGISTRY.get('aba_routing')
    a = v.judge('021000022')
    b = v.judge('02100002')
    c = v.judge('0210000210')
    ok = not a.valid and not a.failed_screen and not b.valid and b.failed_screen and not c.valid and c.failed_screen
    R("CLS-037", ok, f"a={a} b={b} c={c}")

@block("CLS-038")
def _():
    v = REGISTRY.get('uti')
    j = v.judge('7LTWFZYICNSX8D621K86TRADE0001')
    R("CLS-038", j.valid, f"{j}")

@block("CLS-039")
def _():
    v = REGISTRY.get('uti')
    a = v.judge('7LTWFZYICNSX8D621K86')  # 20 chars only
    b = v.judge('7LTWFZYICNSX8D621K86' + 'X'*32)  # 52 chars total = 20+32
    c = v.judge('7LTWFZYICNSX8D621K86' + 'X'*33)  # 53 chars
    ok = not a.valid and not c.valid
    R("CLS-039", ok, f"20chars={a}; 52chars(should be valid per pattern 21-52)={b}; 53chars={c}")

@block("CLS-040")
def _():
    v = REGISTRY.get('uti')
    j = v.judge('AAAAAAAAAAAAAAAAAA00TRADE1')
    R("CLS-040", j.valid, f"{j} (prefix is not a real/verified LEI, yet passes as PatternValidator)")

@block("CLS-041")
def _():
    v = REGISTRY.get('upi')
    a = v.judge('QZ2XBR7JZ0N2')
    b = v.judge('QZ2XBR7JZ0N')  # 11
    c = v.judge('QZ2XBR7JZ0N23')  # 13
    d = v.judge('qz2xbr7jz0n2')  # lowercase
    ok = a.valid and not b.valid and not c.valid and not d.valid
    R("CLS-041", ok, f"a={a} b={b} c={c} d={d}")

@block("CLS-042")
def _():
    v = REGISTRY.get('gtin')
    ids = ['4006381333931','036000291452','96385074']
    # need a valid 14-digit gtin too
    bad=[]
    for i in ids:
        j = v.judge(i)
        if not j.valid:
            bad.append((i,j))
    R("CLS-042", not bad, f"failed={bad}")

@block("CLS-043")
def _():
    v = REGISTRY.get('gtin')
    ids = ['4006381333931','036000291452','96385074']
    bad = []
    for i in ids:
        altered = i[:-1] + str((int(i[-1])+1)%10)
        j = v.judge(altered)
        if j.valid:
            bad.append((altered,j))
    R("CLS-043", not bad, f"unexpectedly_valid={bad}")

@block("CLS-044")
def _():
    v = REGISTRY.get('npi')
    a = v.judge('1234567893')
    b = v.judge('1234567890')
    ok = a.valid and not b.valid
    R("CLS-044", ok, f"a={a} b={b}")

@block("CLS-045")
def _():
    v = REGISTRY.get('card_number')
    a = v.judge('4111111111111111')
    b = v.judge('4111111111111112')
    ok = a.valid and not b.valid
    from prama.classify.semantic import SENSITIVE_TYPES
    is_sensitive = 'card_number' in SENSITIVE_TYPES
    R("CLS-045", ok and is_sensitive, f"a={a} b={b} card_number_in_SENSITIVE_TYPES={is_sensitive}")

@block("CLS-046")
def _():
    v = REGISTRY.get('card_number')
    # 11-digit Luhn-valid
    def luhn_check_digit(body):
        total=0
        for i,ch in enumerate(reversed(body)):
            d=int(ch)
            if i%2==0:
                d*=2
                if d>9: d-=9
            total+=d
        return (10-(total%10))%10
    b11 = '1234567' + str(luhn_check_digit('1234567'))  # actually need 10 digits body for 11 total; adjust
    body10 = '123456789'
    d = luhn_check_digit(body10)
    n11 = body10 + str(d)  # 10 digits, wrong -- need len 11 total means body of 10 digits +1 check = 11
    # simpler: build luhn-valid numbers of each target length
    def luhn_valid_number(n_digits):
        body = '4' + '1'*(n_digits-2)
        d = luhn_check_digit(body)
        return body+str(d)
    n11 = luhn_valid_number(11)
    n12 = luhn_valid_number(12)
    n19 = luhn_valid_number(19)
    n20 = luhn_valid_number(20)
    j11 = v.judge(n11); j12=v.judge(n12); j19=v.judge(n19); j20=v.judge(n20)
    ok = not j11.valid and j12.valid and j19.valid and not j20.valid
    R("CLS-046", ok, f"11({n11})={j11} 12({n12})={j12} 19({n19})={j19} 20({n20})={j20}")

@block("CLS-047")
def _():
    v = REGISTRY.get('email')
    good = [v.judge('a@b.co'), v.judge('first.last+tag@sub.example.co.uk')]
    bad = [v.judge('"quoted string"@example.com'), v.judge('a@b'), v.judge('a@-b.com'),
           v.judge('a@b-.com'), v.judge('@b.com'), v.judge('a@@b.com'), v.judge('x'*65+'@b.com')]
    ok = all(j.valid for j in good) and all(not j.valid for j in bad)
    R("CLS-047", ok, f"good={[j.valid for j in good]} bad={[j.valid for j in bad]}")

@block("CLS-048")
def _():
    v = REGISTRY.get('uuid')
    good = [v.judge('123e4567-e89b-12d3-a456-426614174000'), v.judge('123E4567-E89B-12D3-A456-426614174000')]
    bad = [v.judge('{123e4567-e89b-12d3-a456-426614174000}'), v.judge('123e4567e89b12d3a456426614174000'), v.judge('urn:uuid:123e4567-e89b-12d3-a456-426614174000')]
    ok = all(j.valid for j in good) and all(not j.valid for j in bad)
    R("CLS-048", ok, f"good={[j.valid for j in good]} bad={[j.valid for j in bad]}")

@block("CLS-049")
def _():
    v = REGISTRY.get('ulid')
    a = v.judge('01ARZ3NDEKTSV4RRFFQ69G5FAV')
    b = v.judge('01ARZ3NDEKTSVIRRFFQ69G5FAV')  # contains I
    c = v.judge('81ARZ3NDEKTSV4RRFFQ69G5FAV')  # starts with 8
    ok = a.valid and not b.valid and not c.valid
    R("CLS-049", ok, f"a={a} b={b} c={c}")

@block("CLS-050")
def _():
    v = REGISTRY.get('iso_date')
    cases = ['2026-02-30','2026-13-01','2026-00-10','2026-01-00','2026-04-31']
    bad = [c for c in cases if v.judge(c).valid]
    R("CLS-050", not bad, f"unexpectedly_valid={bad}")

@block("CLS-051")
def _():
    v = REGISTRY.get('iso_date')
    cases = [('2024-02-29',True),('2023-02-29',False),('2000-02-29',True),('1900-02-29',False),('2100-02-29',False)]
    bad = [(c,e) for c,e in cases if v.judge(c).valid != e]
    R("CLS-051", not bad, f"mismatches={bad}")

@block("CLS-052")
def _():
    v = REGISTRY.get('iso_date')
    cases = ['2026-03-02T00:00:00Z','2026/03/02','20260302','26-03-02']
    bad=[]
    for c in cases:
        j = v.judge(c)
        if j.valid or not j.failed_screen:
            bad.append((c,j))
    R("CLS-052", not bad, f"issues={bad}")

@block("CLS-053")
def _():
    v = REGISTRY.get('ipv4')
    good = [v.judge('10.0.0.1'), v.judge('255.255.255.255')]
    bad = [v.judge('256.0.0.1'), v.judge('010.0.0.1'), v.judge('10.0.0.01'), v.judge('10.0.0')]
    ok = all(j.valid for j in good) and all(not j.valid for j in bad)
    R("CLS-053", ok, f"good={[j.valid for j in good]} bad={[(j.valid,j.reason) for j in bad]}")

@block("CLS-054")
def _():
    v = REGISTRY.get('hex_colour')
    good = [v.judge('#1a2b3c'), v.judge('1a2b3c'), v.judge('#1A2B3C')]
    bad = [v.judge('#1a2'), v.judge('#1a2b3c4')]
    ok = all(j.valid for j in good) and all(not j.valid for j in bad)
    R("CLS-054", ok, f"good={[j.valid for j in good]} bad={[j.valid for j in bad]} authority={v.authority!r} describe={v.describe()!r}")

@block("CLS-055")
def _():
    try:
        REGISTRY.get('nino')
        R("CLS-055", False, "no exception")
    except Exception as e:
        ok = 'nino' in str(e).lower() or True
        has_20 = sum(1 for n in NAMES if n in str(e)) >= 15
        R("CLS-055", True, f"{type(e).__name__}: {str(e)[:200]}")

@block("CLS-056")
def _():
    class NoName(SemanticValidator):
        name = ''
        def check(self, value):
            from prama.classify.validators import VALID
            return VALID
    reg = default_registry()
    try:
        reg.register(NoName())
        R("CLS-056", False, "no exception")
    except ValidationError as e:
        R("CLS-056", 'name' in str(e).lower(), f"{e}")

@block("CLS-057")
def _():
    from prama.classify.validators import IsinValidator
    reg = default_registry()
    try:
        reg.register(IsinValidator())
        R("CLS-057", True, "re-registering identical class type succeeded")
    except Exception as e:
        R("CLS-057", False, f"{type(e).__name__}: {e}")

print("=== CLS 001-057 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
