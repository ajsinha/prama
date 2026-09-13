import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from decimal import Decimal
from prama.packs.banking import cobol
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

@block("PCK-140")
def _():
    book = cobol.parse_copybook("""
01 REC.
   05 NAME    PIC X(10).
   05 AMOUNT  PIC S9(7)V99 COMP-3.
   05 CODE    PIC 9(4).
""")
    offsets = {f.name: f.offset for f in book.fields}
    ok = offsets.get('NAME')==0 and offsets.get('AMOUNT')==10 and offsets.get('CODE')==15 and book.record_length==19
    R("PCK-140", ok, f"offsets={offsets} record_length={book.record_length} fields={[(f.name,f.length,f.usage) for f in book.fields]}")

@block("PCK-141")
def _():
    cases = [("S9(7)V99",9,5), ("S9(5)",5,3), ("9(4)",4,3), ("9(8)V99",10,6)]
    detail=[]
    ok=True
    for pic, digits, exp_len in cases:
        kind,d,scale,signed = cobol._picture(pic)
        got = cobol._stored_length(d, "comp3")
        ok &= (got==exp_len)
        detail.append(f"{pic}: digits={d} stored={got} exp={exp_len}")
    R("PCK-141", ok, "; ".join(detail))

@block("PCK-142")
def _():
    cases = [(4,2),(5,4),(9,4),(10,8)]
    detail=[]
    ok=True
    for digits, exp in cases:
        got = cobol._stored_length(digits, "binary")
        ok &= (got==exp)
        detail.append(f"{digits}digits->{got} exp={exp}")
    R("PCK-142", ok, "; ".join(detail))

@block("PCK-143")
def _():
    a = cobol.unpack_comp3(b'\x12\x34\x5C', scale=2)
    b = cobol.unpack_comp3(b'\x12\x34\x5D', scale=2)
    c = cobol.unpack_comp3(b'\x12\x34\x5F', scale=2)
    ok = a==Decimal('123.45') and b==Decimal('-123.45') and c==Decimal('123.45')
    R("PCK-143", ok, f"C={a} D={b} F={c}")

@block("PCK-144")
def _():
    a = cobol.unpack_comp3(b'\xA2\x34\x5C')
    b = cobol.unpack_comp3(b'\x12\x34\x5A')
    ok = a is None and b is None
    R("PCK-144", ok, f"bad_nibble={a} bad_sign={b}")

@block("PCK-145")
def _():
    a = cobol.unpack_comp3(b'')
    b = cobol.unpack_comp3(b'\x0C')
    c = cobol.unpack_comp3(b'\x5C')
    ok = a is None and b==Decimal(0) and c==Decimal(5)
    R("PCK-145", ok, f"empty={a} single_0C={b} single_5C={c}")

@block("PCK-146")
def _():
    book2 = cobol.parse_copybook("01 REC.\n  05 AMT PIC S9(7)V99.\n")
    rec = cobol.read_record('123456789'.encode('cp037'), book2, codepage='cp037')
    R("PCK-146", rec.get('AMT')=='1234567.89', f"read_record(display,S9(7)V99)={rec}")

@block("PCK-147")
def _():
    cases = [('1234}', Decimal('-12340')), ('1234J', Decimal('-12341')), ('1234R', Decimal('-12349')),
             ('1234{', Decimal('12340')), ('1234A', Decimal('12341')), ('1234-', Decimal('-1234')), ('1234+', Decimal('1234'))]
    detail=[]
    ok=True
    for text, exp in cases:
        got = cobol._display_number(text, 0, True)
        ok &= (got==exp)
        detail.append(f"{text!r}->{got} exp={exp}")
    R("PCK-147", ok, "; ".join(detail))

@block("PCK-148")
def _():
    got = cobol._display_number('1234}', 0, False)
    R("PCK-148", got is None, f"unsigned overpunch -> {got}")

@block("PCK-149")
def _():
    book = cobol.parse_copybook("""
01 REC.
   05 GRP OCCURS 12.
      10 A PIC X(2).
      10 B PIC X(3).
   05 AFTER PIC X(4).
""")
    after = book.field('AFTER')
    ok = after is not None and after.offset == 5*12
    R("PCK-149", ok, f"AFTER.offset={after.offset if after else None} expected={5*12} record_length={book.record_length}")

@block("PCK-150")
def _():
    book = cobol.parse_copybook("""
01 REC.
   05 NAME PIC X(10).
   05 BAL PIC 9(2) OCCURS 12.
""")
    ok = book.record_length == 10 + 2*12
    R("PCK-150", ok, f"record_length={book.record_length} expected={10+2*12} (Field.end for BAL is offset+length for ONE occurrence)")

@block("PCK-151")
def _():
    book = cobol.parse_copybook("""
01 REC.
   05 BAL PIC 9(2) OCCURS 12.
""")
    data = "".join(f"{i:02d}" for i in range(12)).encode('cp037')
    rec = cobol.read_record(data, book, codepage='cp037')
    R("PCK-151", None, f"read_record for OCCURS field BAL={rec} -- only one value returned per the chunk=record[field.offset:field.end] slice, not twelve")

@block("PCK-152")
def _():
    book = cobol.parse_copybook("""
01 REC.
   05 A PIC X(5).
   05 B REDEFINES A PIC 9(5).
   05 C PIC X(3).
""")
    fa = book.field('A'); fb=book.field('B'); fc=book.field('C')
    ok = fb.offset == fa.offset and fc.offset == fa.offset + fa.length
    R("PCK-152", ok, f"A.offset={fa.offset} B.offset={fb.offset} C.offset={fc.offset} (expected C.offset={fa.offset+fa.length})")

@block("PCK-153")
def _():
    book = cobol.parse_copybook("""
01 REC.
   05 A PIC X(5).
   05 B REDEFINES NOSUCH PIC X(4).
""")
    ok = len(book.warnings)==1 and 'B' in book.warnings[0] and 'NOSUCH' in book.warnings[0]
    fb = book.field('B')
    R("PCK-153", ok, f"warnings={book.warnings} B.offset={fb.offset if fb else None}")

@block("PCK-154")
def _():
    book = cobol.parse_copybook("""
01 REC.
   05 A PIC X(5).
   05 GRPREDEF REDEFINES A.
      10 X1 PIC X(2).
      10 X2 PIC X(3).
   05 AFTER PIC X(4).
""")
    fa = book.field('A'); after = book.field('AFTER')
    ok = after is not None and after.offset == fa.offset + fa.length
    R("PCK-154", ok, f"A.offset={fa.offset} AFTER.offset={after.offset if after else None} expected={fa.offset+fa.length}")

@block("PCK-155")
def _():
    book = cobol.parse_copybook("""
01 REC.
   05 STATUS-CODE PIC X(1).
      88 STATUS-OPEN VALUE 'O'.
   05 NEXTF PIC X(4).
""")
    sc = book.field('STATUS-CODE'); nf = book.field('NEXTF')
    ok = nf.offset == sc.offset + sc.length
    R("PCK-155", ok, f"STATUS-CODE.offset={sc.offset} NEXTF.offset={nf.offset} expected={sc.offset+sc.length}")

@block("PCK-156")
def _():
    book = cobol.parse_copybook("""000100* THIS IS A COMMENT
000200 05 A PIC X(5).
""")
    ok = not any('THIS IS A COMMENT' in w for w in book.warnings) or True
    is_ignored = any('ignored' in w for w in book.warnings)
    has_field = book.field('A') is not None
    R("PCK-156", not is_ignored, f"warnings={book.warnings} field_A_found={has_field} (fixed-format column-7 comment: line kept its sequence-number prefix so _LINE regex likely misparses '000100' as the level number)")

@block("PCK-157")
def _():
    try:
        cobol.parse_copybook("01 REC.\n  05 A PIC A(5).\n")
        R("PCK-157", False, "no exception for PIC A(5)")
    except ValidationError as e:
        R("PCK-157", True, f"ValidationError raised: {e}")
    except Exception as e:
        R("PCK-157", False, f"wrong exception type: {type(e).__name__}: {e}")

@block("PCK-158")
def _():
    book = cobol.parse_copybook("01 REC.\n  05 A PIC X(5).\n")
    try:
        cobol.read_record(b'ABCDE', book, codepage="")
        R("PCK-158", False, "no exception for empty codepage")
    except ValidationError as e:
        ok = all(cp in str(e) for cp in cobol.COMMON_CODEPAGES)
        R("PCK-158", ok, f"{e}")

@block("PCK-159")
def _():
    # EBCDIC bytes for @ # $ differ between cp037 (US) and cp273 (German)
    # 0x7C is '@' in cp037; find bytes that decode differently
    diffs = []
    for b in range(0x40, 0x50):
        c37 = bytes([b]).decode('cp037', errors='replace')
        c273 = bytes([b]).decode('cp273', errors='replace')
        if c37 != c273:
            diffs.append((hex(b), c37, c273))
    R("PCK-159", len(diffs)>0, f"differing byte->char mappings cp037 vs cp273: {diffs[:5]}")

@block("PCK-160")
def _():
    book = cobol.parse_copybook("01 REC.\n  05 A PIC X(5).\n")
    try:
        cobol.read_record(b'ABCDE', book, codepage="cp9999")
        R("PCK-160", False, "no exception")
    except ValidationError as e:
        ok = 'A' in str(e) and 'cp9999' in str(e)
        R("PCK-160", ok, f"{e}")
    except LookupError as e:
        R("PCK-160", False, f"bare LookupError reached caller: {e}")

@block("PCK-161")
def _():
    book = cobol.parse_copybook("01 REC.\n  05 A PIC X(5).\n  05 B PIC X(5).\n")
    short = 'ABCDE12'.encode('cp037')  # only 2 bytes of B's 5
    rec = cobol.read_record(short, book, codepage='cp037')
    ok = rec.get('B') is None and rec.get('A')=='ABCDE'
    R("PCK-161", ok, f"rec={rec}")

@block("PCK-162")
def _():
    book = cobol.parse_copybook("01 REC.\n  05 A PIC X(4).\n")
    data = 'AAAA'.encode('cp037') * 2 + 'AA'.encode('cp037')  # 2.5 records
    rows, complaints = cobol.read_records(data, book, codepage='cp037')
    ok = len(rows)==2 and len(complaints)==1 and 'record 3' in complaints[0]
    R("PCK-162", ok, f"rows={len(rows)} complaints={complaints}")

@block("PCK-163")
def _():
    book = cobol.parse_copybook("01 REC.\n  05 GRP.\n")  # group only, no elementary items -> no fields
    try:
        cobol.read_records(b'123', book, codepage='cp037')
        R("PCK-163", False, "no exception")
    except ValidationError as e:
        R("PCK-163", True, f"{e}")

@block("PCK-164")
def _():
    book = cobol.parse_copybook("01 REC.\n  05 A PIC S9(4) COMP.\n")
    rec = cobol.read_record((0xFFFF).to_bytes(2,'big'), book, codepage='cp037')
    ok = rec.get('A') == '-1'
    R("PCK-164", ok, f"rec={rec}")

print("=== PCK COBOL 140-164 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
