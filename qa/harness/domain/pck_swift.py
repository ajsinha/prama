import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from decimal import Decimal
from prama.packs.banking import swift, iso20022

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

MT940 = """{1:F01BANKGB2LAXXX0000000000}{2:O940BANKDEFFXXXXN}{4:
:20:STMT-2026-09-09
:25:GB33BUKB20201555555555
:28C:00251/001
:60F:C260908EUR10000,00
:61:2609090909C1500,50NTRFCUST-REF-1//BANKREF1
:86:Incoming payment from Acme
:61:260909D250,25NCHGFEE-REF//BANKREF2
:62F:C260909EUR11250,25
-}"""

MT103 = """{1:F01COBADEFFAXXX0000000000}{2:I103BNPAFRPPXXXXN}{4:
:20:PAY-2026-0001
:23B:CRED
:32A:260910EUR1000,00
:50K:/DE89370400440532013000
ACME GMBH
BERLIN
:52A:COBADEFFXXX
:57A:BNPAFRPPXXX
:59:/FR1420041010050500013M02606
BETA SARL
:70:INVOICE 4471
:71A:SHA
-}"""

@block("PCK-112")
def _():
    stmt = swift.statement(swift.parse(MT940))
    ok = stmt.lines[0].amount > 0 and stmt.lines[1].amount < 0 and stmt.balances is True and stmt.discrepancy == Decimal("0")
    R("PCK-112", ok, f"lines={[l.amount for l in stmt.lines]} balances={stmt.balances} discrepancy={stmt.discrepancy}")

@block("PCK-113")
def _():
    a = swift._amount('1234,56')
    b = swift._amount('1234')
    c = swift._amount('0,01')
    ok = a==Decimal('1234.56') and b==Decimal('1234') and c==Decimal('0.01')
    R("PCK-113", ok, f"a={a} b={b} c={c}")

@block("PCK-114")
def _():
    a = swift._amount('12,34,56')
    b = swift._amount('abc')
    c = swift._amount('')
    ok = a is None and b is None and c is None
    R("PCK-114", ok, f"'12,34,56'->{a} 'abc'->{b} ''->{c}")

@block("PCK-115")
def _():
    defects=[]
    v, d, ccy = swift._balance('D250301EUR1000,00', '60F', 'ref', defects)
    ok = v == Decimal('-1000.00')
    R("PCK-115", ok, f"opening_balance={v} defects={defects}")

@block("PCK-116")
def _():
    defects=[]
    rc = swift._line('2503020303RC1000,00NTRFREF', 'ref', defects)
    rd = swift._line('2503020303RD1000,00NTRFREF', 'ref', defects)
    ok = rc is not None and rd is not None and not rc.is_credit and rd.is_credit
    R("PCK-116", ok, f"RC: is_credit={rc.is_credit if rc else None} amount={rc.amount if rc else None}; RD: is_credit={rd.is_credit if rd else None} amount={rd.amount if rd else None}")

@block("PCK-117")
def _():
    defects=[]
    line = swift._line('2512310102C1000,00NTRFREF', 'ref', defects)
    ok = line is not None and line.entry_date == '2026-01-02'
    R("PCK-117", ok, f"value_date(251231)+entry_day(0102) -> entry_date={line.entry_date if line else None} (expected 2026-01-02)")

@block("PCK-118")
def _():
    got = swift._date('990101')
    ok = got == '2099-01-01'
    R("PCK-118", ok, f"_date('990101')={got!r}")

@block("PCK-119")
def _():
    no_closing = MT940.replace(':62F:C260909EUR11250,25\n', '')
    stmt = swift.statement(swift.parse(no_closing))
    ok = stmt.balances is None and stmt.discrepancy is None and any('62F' in d.field or 'absent' in d.problem for d in stmt.defects)
    R("PCK-119", ok, f"balances={stmt.balances} discrepancy={stmt.discrepancy} defects={[d.render() for d in stmt.defects]}")

@block("PCK-120")
def _():
    mismatched = MT940.replace(':62F:C260909EUR11250,25', ':62F:C260909USD11250,25')
    stmt = swift.statement(swift.parse(mismatched))
    has_defect = any('EUR' in d.problem and 'USD' in d.problem for d in stmt.defects)
    R("PCK-120", has_defect, f"defects={[d.render() for d in stmt.defects]} discrepancy_computed={stmt.discrepancy} balances={stmt.balances} (catalogue: arithmetic is still computed and quoted as a discrepancy despite defect -- checking)")

@block("PCK-121")
def _():
    interim = MT940.replace(':60F:', ':60M:').replace(':62F:', ':62M:')
    stmt = swift.statement(swift.parse(interim))
    ok = stmt.opening_balance == Decimal('10000.00') and stmt.closing_balance == Decimal('11250.25')
    R("PCK-121", ok, f"opening={stmt.opening_balance} closing={stmt.closing_balance} currency={stmt.currency} -- no field distinguishing interim from final visible in Statement")

@block("PCK-122")
def _():
    m = swift.parse(MT940)
    v = m.first('86')
    ok = v is not None and 'Incoming payment from Acme' in v
    no_defect_about_content = not any('content before' in d.problem for d in m.defects)
    R("PCK-122", ok and no_defect_about_content, f"first('86')={v!r} defects={m.defects}")

@block("PCK-123")
def _():
    with_blank = MT940.replace(":86:Incoming payment from Acme", ":86:Incoming\n\npayment")
    parts = swift.split(with_blank)
    R("PCK-123", len(parts)==1, f"split count={len(parts)}")

@block("PCK-124")
def _():
    with_empty70 = MT103.replace(':70:INVOICE 4471', ':70:')
    m = swift.parse(with_empty70)
    empty = m.first('70')
    absent = m.first('71B')
    ok = empty == '' and absent is None
    R("PCK-124", ok, f"first('70')={empty!r} first('71B' absent)={absent!r}")

@block("PCK-125")
def _():
    short32a = MT103.replace(':32A:260910EUR1000,00', ':32A:260910EU')
    m = swift.parse(short32a)
    p = swift.payment(m)
    has_defect_about_32a = any('32A' in d.field for d in m.defects)
    R("PCK-125", has_defect_about_32a, f"payment={p} message_defects={[d.render() for d in m.defects]} (a 9-char 32A value)")

@block("PCK-126")
def _():
    m = swift.parse(MT103)
    ok = m.sender_bic == 'COBADEFFAXXX'
    short_block1 = swift.parse("{1:F01BANK}{2:I103X}{4:\n:20:X\n-}")
    ok2 = short_block1.sender_bic == ''
    R("PCK-126", ok and ok2, f"sender_bic={m.sender_bic!r} short_block1_sender_bic={short_block1.sender_bic!r}")

@block("PCK-127")
def _():
    broken = swift.parse("{1:F01BANKGB2LAXXX0000000000}{2:O940BANKDEFFXXXXN}")
    ok = not broken.is_well_formed and 'missing or unterminated' in broken.defects[0].problem and broken.blocks.get('1') and broken.blocks.get('2')
    R("PCK-127", ok, f"defects={[d.render() for d in broken.defects]} blocks_found={list(broken.blocks.keys())}")

print("=== PCK SWIFT 112-127 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
