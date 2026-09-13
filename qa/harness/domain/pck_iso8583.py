import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from prama.packs.banking import iso8583 as m8583

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

def bitmap_hex(fields):
    bits = [0]*64
    for f in fields:
        bits[f-1] = 1
    hexstr = ""
    for i in range(0, 64, 4):
        nib = (bits[i]<<3)|(bits[i+1]<<2)|(bits[i+2]<<1)|bits[i+3]
        hexstr += format(nib, 'X')
    return hexstr

def build_msg(mti, field_values, secondary_fields=None):
    """field_values: dict field->(value, kind, size). Fields >64 handled via secondary bitmap."""
    primary_fields = sorted(f for f in field_values if f<=64)
    text = mti
    pbm = list(primary_fields)
    has_secondary = bool(secondary_fields)
    bmbits = pbm.copy()
    if has_secondary:
        bmbits = [1] + bmbits  # bit1 marks secondary present
    text += bitmap_hex(bmbits)
    if has_secondary:
        text += bitmap_hex([f-64 for f in secondary_fields])
    allfields = sorted(list(field_values.keys()))
    for f in allfields:
        value, kind, size = field_values[f]
        if kind == "LLVAR":
            text += f"{len(value):02d}{value}"
        elif kind == "LLLVAR":
            text += f"{len(value):03d}{value}"
        else:
            text += value
    return text

FIELDS = m8583.FIELDS

@block("PCK-087")
def _():
    fv = {
        2: ('4111111111111111','LLVAR',19),
        3: ('000000','n',6),
        4: ('000000012345','n',12),
        7: ('0301120000','n',10),
        11: ('123456','n',6),
        41: ('TERM0001','ans',8),
        49: ('840','n',3),
    }
    text = build_msg('0100', fv)
    msg = m8583.parse(text)
    ok = msg.mti=='0100' and msg.is_well_formed and all(f in msg.present for f in fv)
    R("PCK-087", ok, f"mti={msg.mti} present={msg.present} defects={[d.render() for d in msg.defects]}")

@block("PCK-088")
def _():
    fv = {2: ('4111111111111111','LLVAR',19), 3:('000000','n',6)}
    secondary = [70]
    fv[70] = ('001','n',3)  # arbitrary field >64; but 70 not in FIELDS, will cause defect. Use field defined >64? none defined.
    # Since no field >64 is defined in FIELDS table, parsing a secondary-bitmap field will hit "not defined" defect.
    # Still tests: secondary bitmap consumed (16 bytes), and PAN correct (not corrupted).
    text = build_msg('0100', {2: fv[2], 3: fv[3]}, secondary_fields=[70])
    msg = m8583.parse(text)
    pan_ok = msg.unmasked(2) == '4111111111111111'
    has_gt64 = any(f>64 for f in [d.field for d in msg.defects if d.field])
    R("PCK-088", pan_ok, f"unmasked(2)={msg.unmasked(2)} present={msg.present} defects={[d.render() for d in msg.defects]} (secondary bitmap consumed correctly since PAN intact)")

@block("PCK-089")
def _():
    # bit1 set, secondary bitmap all zero (no bits present above 64)
    fv = {2: ('4111111111111111','LLVAR',19), 3:('000000','n',6)}
    text = build_msg('0100', fv, secondary_fields=[])
    msg = m8583.parse(text)
    R("PCK-089", msg.has_secondary_bitmap is True, f"has_secondary_bitmap={msg.has_secondary_bitmap} (secondary bitmap present, all-zero; property is any(f>64 for f in present))")

@block("PCK-090")
def _():
    fv = {2: ('4111111111111111','LLVAR',19)}
    text = build_msg('0100', fv)
    msg = m8583.parse(text)
    ok = msg.unmasked(2) == '4111111111111111' and len(msg.unmasked(2))==16
    R("PCK-090", ok, f"unmasked(2)={msg.unmasked(2)!r} len={len(msg.unmasked(2) or '')}")

@block("PCK-091")
def _():
    # field 2 LLVAR with non-numeric length prefix
    text = '0100' + bitmap_hex([2]) + 'XX' + '4111111111111111'
    msg = m8583.parse(text)
    d = [x for x in msg.defects if x.field==2]
    R("PCK-091", len(d)==1 and "XX" in d[0].problem, f"defects={[x.render() for x in msg.defects]}")

@block("PCK-092")
def _():
    fv = {43: ('A'*40,'ans',40)}
    text = build_msg('0100', fv)
    truncated = text[:-12]  # cut mid field 43
    msg = m8583.parse(truncated)
    d = [x for x in msg.defects if x.field==43]
    ok = len(d)==1 and "declares 40 characters" in d[0].problem and "remain" in d[0].problem
    R("PCK-092", ok, f"defects={[x.render() for x in msg.defects]}")

@block("PCK-093")
def _():
    m1 = m8583.parse('0100')
    m2 = m8583.parse('')
    m3 = m8583.parse('0100'+'0'*15)
    ok = all("too short" in m.defects[0].problem for m in (m1,m2,m3) if m.defects)
    ok = ok and len(m1.defects)==1 and len(m2.defects)==1 and len(m3.defects)==1
    R("PCK-093", ok, f"m1={[d.render() for d in m1.defects]} m2={[d.render() for d in m2.defects]} m3={[d.render() for d in m3.defects]}")

@block("PCK-094")
def _():
    fv = {2: ('4111111111111111','LLVAR',19), 48: ('X'*5,'ans',5)}
    text = build_msg('0100', fv)
    msg = m8583.parse(text)
    d = [x for x in msg.defects if x.field==48]
    ok = len(d)==1 and "not defined in this dialect" in d[0].problem
    R("PCK-094", ok, f"defects={[x.render() for x in msg.defects]} present={msg.present}")

@block("PCK-095")
def _():
    fv = {2: ('4111111111111111','LLVAR',19), 35: ('4111111111111111=25121010000000000000','LLVAR',37), 52: ('0123456789ABCDEF','b',16)}
    text = build_msg('0100', fv)
    msg = m8583.parse(text)
    values_ok = all('4111111111111111' not in str(v) for v in msg.values.values())
    named_ok = all('4111111111111111' not in str(v) for v in msg.named().values())
    repr_ok = '4111111111111111' not in repr(msg) and '_raw' not in repr(msg)
    R("PCK-095", values_ok and named_ok and repr_ok, f"values={msg.values} named={msg.named()} repr_excludes_raw={'_raw' not in repr(msg)}")

@block("PCK-096")
def _():
    a = m8583.mask_pan('4111111111111111')
    b = m8583.mask_pan('1234')
    c = m8583.mask_pan('')
    d = m8583.mask_pan('4111-1111-1111-1111')
    ok = a=='************1111' and b=='****' and c==''
    R("PCK-096", ok, f"a={a!r} b={b!r} c={c!r} d(separated)={d!r} (len(d)={len(d)} vs original len 19 -- strips non-digits, changing preserved length)")

@block("PCK-097")
def _():
    track2 = '4111111111111111=25121010000000000000'
    masked = m8583.mask_pan(track2)
    digits = ''.join(c for c in track2 if c.isdigit())
    ok_no_recoverable_pan = masked[:12].count('*')==12 or True
    R("PCK-097", None, f"masked track2 = {masked!r}; total digit run length={len(digits)}; last 4 kept = {masked[-4:]!r} which are last 4 of discretionary data, not a PAN boundary -- confirms mask applied to wrong field shape as catalogue describes (not a pass/fail per se, judged FAIL against 'no digit run recoverable as a PAN')")

@block("PCK-098")
def _():
    fv = {4: ('000000012345','n',12)}
    text = build_msg('0100', fv)
    msg = m8583.parse(text)
    from decimal import Decimal
    ok = msg.amount() == Decimal('123.45')
    R("PCK-098", ok, f"amount()={msg.amount()}")

@block("PCK-099")
def _():
    fv = {4: ('000000012345','n',12), 49: ('392','n',3)}
    text = build_msg('0100', fv)
    msg = m8583.parse(text)
    from decimal import Decimal
    got = msg.amount()
    ok = got == Decimal('12345')  # expected per catalogue if currency-aware; actual likely 123.45
    R("PCK-099", ok, f"amount()={got} (JPY field49=392); unconditional scaleb(-2) means this is likely 123.45 regardless of currency")

@block("PCK-100")
def _():
    fv = {4: ('    000000','n',12)}
    # field4 must be exactly 12 chars with spaces (non-digit)
    fv = {4: ('  spaces!!  ','n',12)}
    text = build_msg('0100', fv)
    msg = m8583.parse(text)
    ok = msg.amount() is None
    R("PCK-100", ok, f"amount()={msg.amount()} for non-numeric field4={msg.values.get(4)!r}")

print("=== PCK ISO8583 087-100 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
